"""Controls for actual finite-frame sampling and lossless audit records."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

SPEC = importlib.util.spec_from_file_location("multifield_audit", Path(__file__).resolve().parents[1] / "tools/audit_multifield_papers.py")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def record(index, subjects):
    return {"id": f"10.1371/journal.pone.{index:07d}", "subject": subjects, "title_display": str(index)}


def jats(body="<p>Full body.</p>", license_text=None, doi="10.1371/journal.pone.0000001"):
    grant = license_text if license_text is not None else (
        "Creative Commons Attribution License, which permits unrestricted use, distribution, and reproduction.")
    return (f"<article><front><article-meta><article-id pub-id-type='doi'>{doi}</article-id>"
            f"<title-group><article-title>A title</article-title></title-group>"
            f"<permissions><license><license-p>{grant}</license-p></license></permissions>"
            f"<abstract><p>First abstract.</p><p>Second abstract.</p></abstract>"
            f"</article-meta></front><body>{body}</body><back><ref-list><ref>Ref one.</ref>"
            f"<ref>Ref two.</ref></ref-list></back></article>").encode()


class SamplingTests(unittest.TestCase):
    def test_complete_frame_priority_and_small_strata(self):
        docs = [
            record(1, ["/Physical sciences/Physics/Mechanics", "/Medicine and health sciences"]),
            record(2, ["/Physical sciences/Physics"]),
            record(3, ["/Physical sciences/Physics"]),
            record(4, ["/Physical sciences/PhysicsExtra"]),
            record(5, ["/Social sciences"]),
        ]
        pages = [{"response": {"numFound": 5, "start": 0, "docs": docs[:3]}},
                 {"response": {"numFound": 5, "start": 3, "docs": docs[3:]}}]
        result = audit.select(pages)
        self.assertEqual(result["unmatched"], 1)
        self.assertEqual(result["strata"][0]["frame_size"], 3)
        self.assertEqual(result["strata"][0]["sample_size"], 2)
        self.assertEqual(result["strata"][0]["sampling_fraction"], 2/3)
        expected = sorted(docs[:3], key=lambda row: audit.sha(
            (audit.SEED + "\nphysics\n" + row["id"]).encode()))[:2]
        self.assertEqual([r["id"] for r in result["selected"][:2]], [r["id"] for r in expected])
        self.assertEqual(result["strata"][-1]["frame_size"], 0)
        self.assertEqual(result["selected"][-1]["stratum"], "social-science")
        self.assertEqual(pages[0]["response"]["docs"][0], docs[0])

    def test_incomplete_duplicate_unsorted_or_changed_frame_rejected(self):
        docs = [record(1, []), record(2, [])]
        bad = [
            [],
            [{"response": {"numFound": 3, "start": 0, "docs": docs}}],
            [{"response": {"numFound": 2, "start": 1, "docs": docs}}],
            [{"response": {"numFound": 2, "start": 0, "docs": docs[::-1]}}],
            [{"response": {"numFound": 2, "start": 0, "docs": docs[:1]}},
             {"response": {"numFound": 3, "start": 1, "docs": docs[1:]}}],
            [{"response": {"numFound": 2, "start": 0, "docs": [docs[0], docs[0]]}}],
            [{"response": {"numFound": True, "start": 0, "docs": []}}],
        ]
        for pages in bad:
            with self.subTest(pages=pages), self.assertRaises(ValueError):
                audit.select(pages)

    def test_subject_validation_and_no_substring_domain_matching(self):
        for subjects in (None, "physics", [1]):
            with self.assertRaises(ValueError):
                audit.assign(subjects)
        self.assertIsNone(audit.assign(["/NotPhysical sciences/Physics"]))
        self.assertIsNone(audit.assign(["/Physical sciences/PhysicsExtra"]))
        self.assertEqual(audit.assign(["/Physical sciences/Chemistry", "/Computer and information sciences"]), "chemistry")


class NormalizationTests(unittest.TestCase):
    def test_cell_block_and_inline_boundaries_preserved(self):
        body = ("<sec><title>Methods</title><p>pre<italic>existing</italic> H<sub>2</sub>O; "
                "10<sup>2</sup></p><table-wrap><table><tr><td>10</td><td>20</td></tr>"
                "<tr><td>30</td><td>40</td></tr></table></table-wrap>"
                "<p>First paragraph.</p><p>Second paragraph.</p>"
                "<disp-formula><alternatives><tex-math>x=1</tex-math>"
                "<math><mi>x</mi><mo>=</mo><mn>1</mn></math></alternatives></disp-formula></sec>")
        text, info = audit.normalize(jats(body), "10.1371/journal.pone.0000001")
        value = text.decode()
        self.assertIn("10 20 30 40", value)
        self.assertNotIn("1020", value)
        self.assertIn("preexisting H_(2)O; 10^(2)", value)
        self.assertIn("First abstract. Second abstract.", value)
        self.assertIn("Ref one. Ref two.", value)
        self.assertIn("x=1 x=1", value)
        self.assertIn("## Methods", value)
        self.assertIn("First paragraph.\n\nSecond paragraph.", value)
        self.assertGreater(info["body_elements"], 10)

    def test_wrong_doi_incomplete_or_nonpermissive_sources_rejected(self):
        inputs = [
            jats(doi="10.1371/journal.pone.0000002"),
            jats(license_text="Creative Commons Attribution-NonCommercial License."),
            jats(license_text="All rights reserved."),
            b"<article><front/></article>",
            b"<other/>",
            b"<!DOCTYPE article [<!ENTITY a 'secret'>]><article/>",
        ]
        for raw in inputs:
            with self.subTest(raw=raw[:70]), self.assertRaises(ValueError):
                audit.normalize(raw, "10.1371/journal.pone.0000001")


class RepeatTests(unittest.TestCase):
    def sample(self):
        manifest = {"generated_at_utc": "first", "input": {"filename": "first.md", "sha256": "a"}}
        return {"source": "first.md", "reproducibility_manifest": copy.deepcopy(manifest),
                "modules": {
                    "reasoning": {"result": {"source": "first.md", "reproducibility_manifest": copy.deepcopy(manifest),
                        "reasoning_graph": {"edges": [{"source": "claim_1", "target": "claim_2"}]}}},
                    "writing": {"result": {"source": "first.md"}}}}

    def test_semantic_graph_endpoints_and_hashes_survive_projection(self):
        first = self.sample()
        frozen = copy.deepcopy(first)
        projected = audit.stable(first)
        self.assertEqual(first, frozen)
        self.assertEqual(projected["modules"]["reasoning"]["result"]["reasoning_graph"]["edges"][0]["source"], "claim_1")
        second = copy.deepcopy(first)
        second["modules"]["reasoning"]["result"]["reasoning_graph"]["edges"][0]["source"] = "claim_3"
        self.assertNotEqual(audit.stable(first), audit.stable(second))
        second = copy.deepcopy(first)
        second["reproducibility_manifest"]["input"]["sha256"] = "b"
        self.assertNotEqual(audit.stable(first), audit.stable(second))

    def test_only_enumerated_timestamps_and_paths_ignored(self):
        first = self.sample()
        second = copy.deepcopy(first)
        second["source"] = "second.md"
        second["modules"]["reasoning"]["result"]["source"] = "second.md"
        second["modules"]["writing"]["result"]["source"] = "second.md"
        for manifest in (second["reproducibility_manifest"],
                         second["modules"]["reasoning"]["result"]["reproducibility_manifest"]):
            manifest["generated_at_utc"] = "second"
            manifest["input"]["filename"] = "second.md"
        self.assertEqual(audit.stable(first), audit.stable(second))
        second["modules"]["writing"]["result"]["generated_at_utc"] = "meaningful unlisted field"
        self.assertNotEqual(audit.stable(first), audit.stable(second))

    def test_failed_repeat_and_later_paper_preserved_without_replacement(self):
        first = self.sample()
        first.update(execution_status="complete", criteria_matrix={"criteria": [], "summary": {}})
        first["modules"].update({"discipline:physics": {"status": "completed", "result": {"items": []}},
                                "preparation": {"status": "completed", "result": {"candidates": []}}})
        for value in first["modules"].values():
            value.setdefault("status", "completed")
        second = copy.deepcopy(first)
        second["modules"]["reasoning"]["result"]["reasoning_graph"]["edges"][0]["source"] = "different"
        row = {"doi": "10.1371/journal.pone.0000001", "stratum": "physics", "status": "available", "text": "input.md"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "input.md").write_text("# Test\n\nFull text.", encoding="utf-8")
            with patch.object(audit, "FOLDER", root), patch("sra.review.review_document", side_effect=[first, second, first, first]), \
                 patch("sra.review_report.review_markdown", return_value="Report"), \
                 patch("sra.domain_adjudication.make_domain_template", return_value={"assessments": []}):
                result = audit.execute_paper(row, root / "out")
                later = audit.execute_paper(dict(row, doi="10.1371/journal.pone.0000002"), root / "out")
            self.assertEqual(result["execution_status"], "repeat_mismatch")
            self.assertFalse(result["repeat_equal"])
            self.assertEqual(later["execution_status"], "complete")
            raw = json.loads((root / "out/papers/0000001.json").read_bytes())
            self.assertEqual(raw["modules"]["reasoning"]["result"]["reasoning_graph"]["edges"][0]["source"], "claim_1")
            self.assertTrue((root / "out/repeated/0000001.json").exists())

    def test_source_failure_denominator_and_second_run_exception_retained(self):
        unavailable = {"doi": "10.1371/journal.pone.0000001", "stratum": "physics",
                       "status": "unavailable", "failure": "HTTP 404"}
        result = audit.execute_paper(unavailable, Path("unused"))
        self.assertEqual(result["source_status"], "unavailable")
        self.assertIsNone(result["scientific_accuracy"])
        first = self.sample()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "input.md").write_text("Full text.", encoding="utf-8")
            row = dict(unavailable, status="available", text="input.md")
            with patch.object(audit, "FOLDER", root), patch("sra.review.review_document", side_effect=[first, RuntimeError("backend failed")]), \
                 patch("sra.review_report.review_markdown", return_value="Report"):
                result = audit.execute_paper(row, root / "out")
            self.assertEqual(result["execution_status"], "failed")
            self.assertTrue((root / "out/papers/0000001.json").exists())

    def test_existing_outputs_and_symlinks_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "existing"
            path.write_bytes(b"preserve")
            with self.assertRaises(FileExistsError):
                audit.save(path, b"changed")
            self.assertEqual(path.read_bytes(), b"preserve")


if __name__ == "__main__":
    unittest.main()
