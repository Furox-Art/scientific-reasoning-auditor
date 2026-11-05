"""Check provenance of explicitly structured scientific outputs."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from sra.scientific_validation import verify_scientific_file


class ScientificReportProvenance(unittest.TestCase):
    def test_standalone_output_has_reproducibility_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"checks.json"
            p.write_text(json.dumps({"schema_version":"1.0","checks":[{
                "id":"ci","kind":"semantic_ci",
                "confidence_level":0.95,"claim_type":"not_significant",
                "effect_measure":"rate_ratio",
                "estimate":0.87,"ci_lower":0.64,"ci_upper":1.18
            }]}),encoding="utf-8")
            report=verify_scientific_file(p)
            manifest=report["reproducibility_manifest"]
            self.assertEqual(manifest["input_sha256"],hashlib.sha256(p.read_bytes()).hexdigest())
            self.assertEqual(manifest["algorithm_version"],report["algorithm_version"])
            self.assertTrue(manifest["software"]["python_version"])
            self.assertTrue(manifest["software"]["auditor_version"])
            self.assertIn("scipy",manifest["software"]["dependencies"])
            self.assertIn("source_code_revision",manifest)
            self.assertIn("working_tree_dirty",manifest)
            self.assertIn("source_code_sha256",manifest)
            if manifest["source_code_sha256"] is not None:
                self.assertEqual(len(manifest["source_code_sha256"]),64)
            self.assertIn("source_code_hash_scope",manifest)


if __name__=="__main__":
    unittest.main()
