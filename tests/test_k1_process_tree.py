"""K1 process-tree termination: deterministic and real POSIX regressions."""
from __future__ import annotations

import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from sra.pdf_visual import _resource_limiter, _run_limited


class ProcessTreeTerminationTests(unittest.TestCase):
    def test_child_group_is_killed_and_parent_reaped_after_timeout(self):
        """Actual descendant must stop executing after a parent timeout."""
        with tempfile.TemporaryDirectory(prefix="sra-tree-test-") as directory:
            pidfile = Path(directory) / "grandchild.pid"
            child_script = """
import subprocess
import sys
import time
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
with open(sys.argv[1], 'w') as stream:
    stream.write(str(child.pid))
time.sleep(30)
"""
            with self.assertRaises(subprocess.TimeoutExpired):
                _run_limited(
                    [sys.executable, "-c", child_script, str(pidfile)],
                    stdout=subprocess.DEVNULL, timeout=1.5,
                    preexec_fn=_resource_limiter(
                        1024 * 1024, 512 * 1024 * 1024, 15
                    ),
                )
            self.assertTrue(pidfile.is_file(), "Controlled descendant failed to start")
            pid = int(pidfile.read_text())
            proc = Path(f"/proc/{pid}/status")
            if proc.is_file():
                state = next(line for line in proc.read_text().splitlines()
                             if line.startswith("State:"))
                # Reparented killed children may remain kernel zombies.
                self.assertIn("Z", state, f"Descendant is still running: {state}")

    def test_timeout_uses_process_group_and_reaps_parent(self):
        process = Mock(pid=9987, returncode=-9)
        process.wait.side_effect = [
            subprocess.TimeoutExpired("fake", 0.01), -9,
        ]
        with patch("sra.pdf_visual.subprocess.Popen", return_value=process) as spawn, patch(
            "sra.pdf_visual.os.killpg"
        ) as kill_group:
            with self.assertRaises(subprocess.TimeoutExpired):
                _run_limited(
                    ["fake"], stdout=subprocess.DEVNULL, timeout=0.01,
                    preexec_fn=lambda: None,
                )
        kill_group.assert_called_once_with(9987, signal.SIGKILL)
        self.assertTrue(spawn.call_args.kwargs["start_new_session"])
        self.assertEqual(process.wait.call_count, 2)

    def test_normal_completion_also_cleans_remaining_group(self):
        process = Mock(pid=9988, returncode=0)
        process.wait.return_value = 0
        with patch("sra.pdf_visual.subprocess.Popen", return_value=process), patch(
            "sra.pdf_visual.os.killpg", side_effect=ProcessLookupError
        ):
            result = _run_limited(
                ["fake"], stdout=subprocess.DEVNULL, timeout=1.0,
                preexec_fn=lambda: None,
            )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(process.wait.call_count, 2)

    def test_unresponsive_parent_is_killed_as_fallback(self):
        process = Mock(pid=9989, returncode=-9)
        process.wait.side_effect = [
            subprocess.TimeoutExpired("fake", 0.01),
            subprocess.TimeoutExpired("fake", 3),
            -9,
        ]
        with patch("sra.pdf_visual.subprocess.Popen", return_value=process), patch(
            "sra.pdf_visual.os.killpg"
        ):
            with self.assertRaises(subprocess.TimeoutExpired):
                _run_limited(
                    ["fake"], stdout=subprocess.DEVNULL, timeout=0.01,
                    preexec_fn=lambda: None,
                )
        process.kill.assert_called_once()
        self.assertEqual(process.wait.call_count, 3)


if __name__ == "__main__":
    unittest.main()
