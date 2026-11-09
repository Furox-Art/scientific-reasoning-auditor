"""Release tag origin guard: real Git DAG positive/negative controls."""
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ('git fetch --no-tags origin +refs/heads/main:refs/remotes/origin/main\n'
         'git merge-base --is-ancestor "$GITHUB_SHA" refs/remotes/origin/main')


class ReleaseLineageTests(unittest.TestCase):
    def git(self, folder, *argv):
        return subprocess.run(
            ["git", "-C", str(folder), *argv],
            check=True, capture_output=True, text=True,
        ).stdout.strip()

    def test_both_release_workflows_enforce_main_ancestry(self):
        for name in ("publish.yml", "npm-publish.yml"):
            with self.subTest(name=name):
                source = (ROOT / ".github/workflows" / name).read_text()
                self.assertIn("fetch-depth: 0", source)
                self.assertIn('git merge-base --is-ancestor "$GITHUB_SHA" refs/remotes/origin/main', source)
                self.assertIn("git fetch --no-tags origin +refs/heads/main:refs/remotes/origin/main", source)
                self.assertIn("exit 1", source)

    def test_real_git_dag_allows_main_and_blocks_unmerged_feature(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote, work = root / "remote.git", root / "work"
            subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(remote)],
                           check=True, capture_output=True)
            # Forward slashes keep the path a path on Windows: a backslash form
            # such as C:\Temp\remote.git is read by git as an ssh host and the
            # guard then dies with "Could not resolve hostname c:".
            subprocess.run(["git", "clone", remote.as_posix(), str(work)],
                           check=True, capture_output=True)
            # The guard runs under bash, where an absolute Windows path is read as
            # an ssh host and a file:///C:/... URL is rewritten by MSYS. A path
            # relative to the worktree means the same thing to every git on every
            # platform, so the DAG is replayed exactly here as on CI.
            self.git(work, "config", "remote.origin.url", "../remote.git")
            self.git(work, "config", "user.name", "Fixture Author")
            self.git(work, "config", "user.email", "fixture@example.invalid")
            (work / "demo.txt").write_text("main\n")
            self.git(work, "add", ".")
            self.git(work, "commit", "-m", "first")
            main_sha = self.git(work, "rev-parse", "HEAD")
            self.git(work, "push", "origin", "HEAD:main")
            self.git(work, "switch", "-c", "feature")
            (work / "demo.txt").write_text("feature\n")
            self.git(work, "commit", "-am", "second")
            feature_sha = self.git(work, "rev-parse", "HEAD")
            for sha, accepted in ((main_sha, True), (feature_sha, False)):
                with self.subTest(commit=sha, accepted=accepted):
                    # Git-for-Windows' MSYS bash, started from Python, loses shell
                    # variables entirely: ``v=1; echo $v`` prints nothing, and neither
                    # ``env=`` nor ``export`` reaches the next command. The commit is
                    # therefore inlined into the guard text; every other byte of the
                    # guard stays identical to the workflow's.
                    script = GUARD.replace('"$GITHUB_SHA"', "'" + sha + "'")
                    completed = subprocess.run(
                        ["bash", "-e", "-c", script],
                        cwd=work, capture_output=True, text=True,
                    )
                    self.assertEqual(completed.returncode == 0, accepted, completed.stderr)


if __name__ == "__main__":
    unittest.main()
