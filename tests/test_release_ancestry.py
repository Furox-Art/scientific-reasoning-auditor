"""Release tag origin guard: real Git DAG positive/negative controls."""
import os
import subprocess
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
            subprocess.run(["git", "clone", str(remote), str(work)],
                           check=True, capture_output=True)
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
                    env = dict(os.environ, GITHUB_SHA=sha)
                    completed = subprocess.run(
                        ["bash", "-e", "-c", GUARD],
                        cwd=work, env=env, capture_output=True, text=True,
                    )
                    self.assertEqual(completed.returncode == 0, accepted, completed.stderr)


if __name__ == "__main__":
    unittest.main()
