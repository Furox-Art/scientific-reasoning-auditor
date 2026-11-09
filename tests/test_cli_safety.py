"""CLI preflight must not overwrite any input when --out collides."""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sra.cli import main


class CLISafetyTests(unittest.TestCase):
    def _run(self, args):
        errors=io.StringIO()
        with patch.object(sys, "argv", ["sra", *args]):
            with contextlib.redirect_stderr(errors):
                with self.assertRaises(SystemExit) as caught:
                    main()
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("overwrite", errors.getvalue().lower())

    def test_all_commands_reject_source_output_collision_before_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            manuscript=Path(tmp)/"paper.md"
            manuscript.write_text("# Methods\nA method.\n# Results\nA result.\n# Conclusion\nA conclusion.")
            stats=Path(tmp)/"stats.json"
            stats.write_text('{"test":"welch_t"}')
            originals=(manuscript.read_bytes(),stats.read_bytes())
            self._run(["audit",str(manuscript),"--out",str(manuscript.with_suffix(""))])
            self._run(["review-template",str(manuscript),"--out",str(manuscript)])
            self._run(["review-model",str(manuscript),"--model","test-model","--out",str(manuscript)])
            self._run(["verify-stats",str(stats),"--out",str(stats)])
            self.assertEqual((manuscript.read_bytes(),stats.read_bytes()),originals)

    def test_symlink_output_alias_to_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/"paper.md"
            source.write_text("# Methods\nA method.")
            alias=Path(tmp)/"output.md"
            try:
                alias.symlink_to(source)
            except (OSError, NotImplementedError):
                # Windows needs Developer Mode or elevation for symlinks; a hard
                # link is the other way to give one file a second name, and it is
                # the stricter case because the paths do not even resolve together.
                try:
                    os.link(source, alias)
                except OSError as error:
                    self.fail(
                        "this platform can create neither a symlink nor a hard link, so "
                        f"the alias guard cannot be exercised: {error}"
                    )
            before=source.read_bytes()
            self._run(["review-template",str(source),"--out",str(alias)])
            self.assertEqual(source.read_bytes(),before)

    def test_audit_refuses_to_overwrite_imported_semantic_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            paper=Path(tmp)/"paper.md"
            paper.write_text("# Methods\nA method.")
            review=Path(tmp)/"review.json"
            review.write_text('{"source_sha256":"x"}')
            before=review.read_bytes()
            self._run(["audit",str(paper),"--semantic-review",str(review),
                       "--out",str(review.with_suffix(""))])
            self.assertEqual(review.read_bytes(),before)


if __name__ == "__main__":
    unittest.main()
