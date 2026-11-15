"""Generated metadata may use RFC CRLF; source inventory remains byte-exact."""
import json
import unittest
import tomllib
from pathlib import Path

from tools.verify_distributions import _expected_metadata_fields, _verify_metadata


class WindowsMetadataTests(unittest.TestCase):
    def test_crlf_metadata_description_is_equivalent_but_content_change_is_not(self):
        root = Path(__file__).parents[1]
        project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
        lines = []
        for field, values in _expected_metadata_fields(project).items():
            if values is None:
                continue
            for value in values if isinstance(values, list) else [values]:
                lines.append(f"{field}: {value}")
        readme = (root / "README.md").read_text(encoding="utf-8")
        metadata = ("\n".join(lines) + "\n\n" + readme).replace("\n", "\r\n").encode()
        _verify_metadata(metadata, project["name"], project["version"], "windows.whl",
                         expected_project=project, repository_root=root)
        with self.assertRaisesRegex(SystemExit, "description differs"):
            _verify_metadata(metadata + b"altered", project["name"], project["version"], "altered.whl",
                             expected_project=project, repository_root=root)


if __name__ == "__main__":
    unittest.main()
