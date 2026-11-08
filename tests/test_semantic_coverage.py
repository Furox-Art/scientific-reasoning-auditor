"""Adversarial source-bound semantic-review validation tests.

Mutations are performed on one independently verified, valid review so each
error probes a particular input contract rather than a broken initial fixture.
"""
import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sra.audit import audit_file
from sra.semantic_review import (
    build_semantic_review_template,
    load_semantic_review,
    validate_semantic_review,
)


TEXT = (
    "# Methods\nThis observational cohort included patients.\n"
    "# Results\nThe intervention increased recovery by five units.\n"
    "# Conclusion\nThe intervention increased recovery by five units."
)
QUOTE = "The intervention increased recovery by five units."


def fixture():
    folder = tempfile.TemporaryDirectory()
    path = Path(folder.name) / "paper.md"
    # newline="" keeps the bytes on disk identical to TEXT.encode() on every
    # platform: the report records the digest of the file's bytes, so a Windows
    # CRLF translation would make that digest disagree with the fixture text.
    path.write_text(TEXT, encoding="utf-8", newline="")
    audited = audit_file(path).to_dict()
    review = build_semantic_review_template(audited, source_text=TEXT)
    review["reviewer"] = {
        "name": "Synthetic fixture reviewer",
        "model_or_agent": "regression-test-only",
        "reviewed_at_utc": "2026-11-04T00:00:00Z",
    }
    review["assessments"][0].update({
        "relation": "entailed",
        "confidence": 0.85,
        "rationale": "Checks syntactic contract, not scientific inference truth.",
        "source_quotes": [QUOTE],
    })
    return folder, audited, review


class SemanticReviewBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.folder, self.audited, self.valid = fixture()
        self.addCleanup(self.folder.cleanup)
        result = validate_semantic_review(self.valid, self.audited, TEXT)
        self.assertEqual(result["status"], "ACCEPTED_FOR_REVIEW", result["errors"])

    def reject_mutation(self, name, mutation, expected):
        with self.subTest(name=name):
            changed = copy.deepcopy(self.valid)
            mutation(changed)
            result = validate_semantic_review(changed, self.audited, TEXT)
            self.assertEqual(result["status"], "REJECTED", (name, result["errors"]))
            self.assertTrue(
                any(expected in err for err in result["errors"]),
                (name, expected, result["errors"]),
            )

    def test_build_template_rejects_wrong_object_and_text(self):
        bad_graph = copy.deepcopy(self.audited)
        bad_graph["reasoning_graph"] = []
        with self.assertRaisesRegex(ValueError, "reasoning graph object"):
            build_semantic_review_template(bad_graph, source_text=TEXT)
        with self.assertRaisesRegex(ValueError, "source text must be supplied"):
            build_semantic_review_template(self.audited, source_text=None)

    def test_semantic_root_audit_and_source_error_boundaries(self):
        self.assertEqual(
            validate_semantic_review("not-json-object", self.audited, TEXT)["status"],
            "REJECTED",
        )
        self.assertEqual(
            validate_semantic_review(self.valid, [], TEXT)["errors"],
            ["Audit report root must be a JSON object."],
        )
        wrong_graph = copy.deepcopy(self.audited)
        wrong_graph["reasoning_graph"] = "invalid"
        self.assertEqual(
            validate_semantic_review(self.valid, wrong_graph, TEXT)["errors"],
            ["Audit report does not contain a reasoning graph object."],
        )
        with patch("sra.semantic_review.validate_reasoning_graph_object", side_effect=TypeError("synthetic malformed graph")):
            result = validate_semantic_review(self.valid, self.audited, TEXT)
        self.assertIn("validation could not safely process", result["errors"][0])
        result = validate_semantic_review(self.valid, self.audited, None)
        self.assertIn("must be supplied as a string", result["errors"][0])
        with patch("sra.semantic_review._rebuild_graph_from_source", side_effect=KeyError("synthetic source graph failure")):
            result = validate_semantic_review(self.valid, self.audited, TEXT)
        self.assertIn("Could not reconstruct", result["errors"][0])

    def test_legacy_text_digest_fallback(self):
        audited = copy.deepcopy(self.audited)
        audited.pop("reproducibility_manifest")
        self.assertEqual(
            audited["sha256"], hashlib.sha256(TEXT.encode()).hexdigest()
        )
        old = copy.deepcopy(self.valid)
        old["schema_version"] = "1.0"
        old.pop("review_mode")
        old.pop("evidence_catalog")
        old.pop("graph_schema_version")
        old.pop("graph_fingerprint_algorithm")
        old["assessments"][0].pop("reviewer_selected_evidence_node_ids")
        # Legacy inputs may bind only to raw text digest, not extracted-text manifest.
        result = validate_semantic_review(old, audited, TEXT)
        self.assertEqual(result["status"], "ACCEPTED_FOR_REVIEW", result["errors"])
        old["review_mode"] = "parallel"
        result = validate_semantic_review(old, audited, TEXT)
        self.assertIn("single-model mode only", " ".join(result["errors"]))

    def test_reviewer_metadata_and_schema_validation(self):
        def change_review(key, value):
            return lambda v: v.__setitem__(key, value)
        cases = [
            ("missing reviewer", change_review("reviewer", None), "reviewer metadata is required"),
            ("unexpected reviewer key", lambda v: v["reviewer"].update({"secret": "untrusted"}), "Unexpected reviewer fields"),
            ("naive timestamp", lambda v: v["reviewer"].update({"reviewed_at_utc": "2026-11-04T00:00:00"}), "timezone"),
            ("unparseable timestamp", lambda v: v["reviewer"].update({"reviewed_at_utc": "not-a-timestamp"}), "ISO-8601"),
            ("unsupported version", change_review("schema_version", "9.9"), "Unsupported semantic review schema_version"),
            ("unsupported mode", change_review("review_mode", "many"), "review_mode must"),
            ("unsupported review type", change_review("review_type", "unknown"), "Unsupported semantic review review_type"),
            ("tampered graph fingerprint", change_review("graph_fingerprint", "0" * 64), "Graph fingerprint does not match"),
        ]
        for name, mutate, error in cases:
            self.reject_mutation(name, mutate, error)

    def test_evidence_catalog_contract(self):
        def change_catalog(new):
            return lambda v: v.__setitem__("evidence_catalog", new)
        def edit_entry(key, val):
            return lambda v: v["evidence_catalog"][0].__setitem__(key, val)
        genuine = self.valid["evidence_catalog"][0]
        cases = [
            ("catalog object", change_catalog({}), "evidence_catalog must be an array"),
            ("catalog entry string", change_catalog(["bad"]), "must be an object"),
            ("catalog entry fields", change_catalog([{"node_id": genuine["node_id"]}]), "missing or unexpected fields"),
            ("unknown catalog evidence id", edit_entry("node_id", "evidence:unknown"), "unknown evidence node"),
            ("wrong catalog location", edit_entry("source_location", {"line": 999, "section": "Results"}), "location does not match"),
            ("duplicated catalog id", change_catalog([genuine, genuine]), "duplicate node IDs"),
            ("missing catalog node", change_catalog([]), "every evidence node"),
        ]
        for name, mutate, error in cases:
            self.reject_mutation(name, mutate, error)

    def test_assessment_validation_contract(self):
        assessment = self.valid["assessments"][0]
        evidence_id = assessment["evidence_node_ids"][0]
        wrong_id = "inference:not-an-inference"
        def edit(field, value):
            return lambda v: v["assessments"][0].__setitem__(field, value)
        def remove(field):
            return lambda v: v["assessments"][0].pop(field)
        def add(field, value):
            return lambda v: v["assessments"][0].update({field: value})
        cases = [
            ("assessment non-list", lambda v: v.__setitem__("assessments", {}), "assessments must be a JSON array"),
            ("assessment non-object", lambda v: v.__setitem__("assessments", ["bad"]), "must be an object"),
            ("missing assessment fields", remove("rationale"), "missing required fields"),
            ("unexpected assessment fields", add("injected", "no"), "unexpected fields"),
            ("unknown inference", edit("inference_node_id", wrong_id), "unknown inference node"),
            ("duplicate inference", lambda v: v["assessments"].append(copy.deepcopy(v["assessments"][0])), "Duplicate assessment"),
            ("invalid claim", edit("claim_node_id", evidence_id), "invalid claim node"),
            ("undeclared relation", lambda v: v.__setitem__("relation_labels", []), "not declared in relation_labels"),
            ("malformed quotes", edit("source_quotes", "not array"), "source_quotes must be an array"),
            ("invalid selected ids", edit("reviewer_selected_evidence_node_ids", ["unknown"]), "invalid or duplicate reviewer_selected"),
            ("overlapping support ids", edit("reviewer_selected_evidence_node_ids", [evidence_id]), "duplicates graph-linked"),
            ("unsupported positive assertion", lambda v: (
                v["assessments"][0].__setitem__("evidence_node_ids", []),
                v["assessments"][0].__setitem__("reviewer_selected_evidence_node_ids", []),
            ), "requires graph-linked or explicitly reviewer-selected"),
            ("invalid missing assumptions", edit("missing_assumptions", None), "missing_assumptions must be an array"),
            ("invalid counter IDs", edit("counter_evidence_node_ids", ["fake"]), "invalid or duplicate counter_evidence_node_ids"),
            ("support counter overlap", edit("counter_evidence_node_ids", [evidence_id]), "cannot classify the same node"),
            ("contradiction without counter", edit("relation", "contradicted"), "requires at least one separately identified counter-evidence"),
            ("no supporting quote", edit("source_quotes", []), "requires at least one evidence quotation"),
            ("missing assessments", lambda v: v.__setitem__("assessments", []), "Missing semantic assessments"),
        ]
        for name, mutation, error in cases:
            self.reject_mutation(name, mutation, error)

    def test_loader_rejects_nonobject_json_root(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad-review.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "JSON root must be an object"):
                load_semantic_review(path)
