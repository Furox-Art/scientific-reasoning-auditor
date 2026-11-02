import json
import tempfile
import unittest
from pathlib import Path

from sra.audit import audit_file
from sra.graph import validate_reasoning_graph
from sra.semantic_review import build_semantic_review_template, validate_semantic_review
from sra.report import to_markdown
from sra.stats import verify_stats_file, verify_welch_t_test


class AuditTests(unittest.TestCase):
    def audit_text(self, text: str):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "paper.md"
        path.write_text(text, encoding="utf-8")
        return audit_file(path)

    def test_flags_absolute_claim_and_missing_sections(self):
        report = self.audit_text(
            "# Results\nThe treatment is associated with response.\n"
            "# Conclusion\nThis study proves conclusively that treatment causes response."
        )
        ids = {finding.check_id for finding in report.findings}
        self.assertIn("language.absolute_claim", ids)
        self.assertIn("reasoning.correlation_causation_review", ids)
        self.assertIn("structure.methods_missing", ids)
        self.assertIn("structure.limitations_missing", ids)
        self.assertTrue(report.sha256)

    def test_claim_evidence_candidate_is_explicitly_heuristic(self):
        report = self.audit_text(
            "# Methods\nWe used a randomized design.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nOur findings demonstrate that the intervention increased the score."
        )
        self.assertEqual(len(report.claim_evidence_candidates), 1)
        candidate = report.claim_evidence_candidates[0]
        self.assertIn("not verified", candidate.interpretation)
        self.assertEqual(candidate.match_status, "heuristic_candidate")
        self.assertEqual(candidate.claim_line, 6)
        self.assertEqual(candidate.support_line, 4)
        self.assertEqual(candidate.claim_section, "Conclusion")
        self.assertEqual(candidate.support_section, "Results")

    def test_flags_possible_direction_conflict_between_results_and_conclusion(self):
        report = self.audit_text(
            "# Methods\nA randomized experiment was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention decreased the measured score."
        )
        ids = {finding.check_id for finding in report.findings}
        self.assertIn("reasoning.directional_contradiction", ids)
        relation = next(
            item for item in report.reasoning_map
            if item["relation"] == "possible_directional_contradiction"
        )
        self.assertEqual(relation["status"], "heuristic_review_required")

    def test_weak_lexical_overlap_is_not_presented_as_support(self):
        report = self.audit_text(
            "# Methods\nA protocol was followed.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Discussion\nThe outcome was correlated with a biomarker."
        )
        candidate = report.claim_evidence_candidates[0]
        self.assertLess(candidate.lexical_overlap, 0.15)
        self.assertEqual(candidate.match_status, "unmatched_review_required")

    def test_flags_causal_claim_in_observational_design(self):
        report = self.audit_text(
            "# Methods\nThis was a cross-sectional observational study.\n"
            "# Results\nExposure was associated with the measured outcome.\n"
            "# Conclusion\nThe exposure caused the measured outcome."
        )
        ids = {finding.check_id for finding in report.findings}
        self.assertIn("reasoning.causal_claim_observational_design", ids)
        finding = next(f for f in report.findings if f.check_id == "reasoning.causal_claim_observational_design")
        self.assertEqual(finding.evidence_locations[1]["section"], "Methods")

    def test_unmatched_conclusion_claim_gets_review_signal(self):
        report = self.audit_text(
            "# Methods\nA standard protocol was followed.\n"
            "# Results\nThe temperature remained stable throughout the experiment.\n"
            "# Conclusion\nOur findings demonstrate that the treatment improves long-term memory."
        )
        candidate = report.claim_evidence_candidates[0]
        self.assertEqual(candidate.match_status, "unmatched_review_required")
        ids = {finding.check_id for finding in report.findings}
        self.assertIn("reasoning.conclusion_without_lexical_candidate", ids)

    def test_manifest_records_source_and_environment_fingerprints(self):
        report = self.audit_text(
            "# Methods\nA test was performed.\n# Results\nThe result was stable."
        )
        manifest = report.reproducibility_manifest
        self.assertEqual(manifest["input"]["sha256"], report.sha256)
        self.assertEqual(manifest["input"]["format"], "md")
        self.assertEqual(len(manifest["configuration_sha256"]), 64)
        self.assertEqual(len(manifest["environment_fingerprint"]), 64)
        self.assertEqual(manifest["ruleset_version"], "0.3.0")
        self.assertIn("source_code_revision", manifest)
        self.assertIn("working_tree_dirty", manifest)
        self.assertIn("scipy", manifest["runtime"]["dependencies"])
        json.dumps(report.to_dict(), ensure_ascii=False)

    def test_synthetic_logic_demo_emits_the_expected_review_signals(self):
        example = Path(__file__).resolve().parents[1] / "examples" / "logic_review_demo.md"
        report = audit_file(example)
        ids = {finding.check_id for finding in report.findings}
        self.assertIn("reasoning.causal_claim_observational_design", ids)
        self.assertIn("reasoning.directional_contradiction", ids)
        self.assertIn("reasoning.correlation_causation_review", ids)

    def test_reasoning_graph_has_typed_nodes_and_linked_relations(self):
        report = self.audit_text(
            "# Methods\nWe used a randomized experiment.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score."
        )
        graph = report.reasoning_graph
        node_types = {node["node_type"] for node in graph["nodes"]}
        relations = {edge["relation"] for edge in graph["edges"]}
        self.assertTrue({"method", "evidence", "claim", "inference"}.issubset(node_types))
        self.assertIn("lexical_candidate_basis", relations)
        self.assertIn("yields_claim", relations)
        self.assertIn("method_document_context", relations)
        self.assertEqual(graph["validation"]["status"], "PASS")
        self.assertTrue(any(edge["status"] == "document_context_only" for edge in graph["edges"]))
        self.assertEqual(len(graph["graph_fingerprint"]), 64)

    def test_explicit_assumptions_and_missing_assumption_gaps_are_distinguished(self):
        report = self.audit_text(
            "# Methods\nWe assume that there is no unmeasured confounding.\n"
            "# Results\nExposure was associated with outcome.\n"
            "# Conclusion\nExposure caused the outcome."
        )
        nodes = report.reasoning_graph["nodes"]
        self.assertTrue(any(n["node_type"] == "assumption" for n in nodes))
        self.assertTrue(any(n["node_type"] == "assumption_gap" for n in nodes))
        gap = next(n for n in nodes if n["node_type"] == "assumption_gap")
        self.assertEqual(gap["status"], "not_linked_to_claim_review_required")
        self.assertIn("not proof", gap["text"])
        no_assumption = self.audit_text(
            "# Methods\nA cross-sectional study was conducted.\n"
            "# Results\nExposure was associated with outcome.\n"
            "# Conclusion\nExposure caused the outcome."
        )
        missing_gap = next(
            n for n in no_assumption.reasoning_graph["nodes"] if n["node_type"] == "assumption_gap"
        )
        self.assertEqual(missing_gap["status"], "not_extracted_review_required")

    def test_graph_integrity_validator_detects_dangling_edges_and_cycles(self):
        nodes = [
            {"node_id": "a", "node_type": "evidence"},
            {"node_id": "b", "node_type": "inference"},
        ]
        edges = [
            {"edge_id": "ab", "source": "a", "target": "b", "relation": "uses"},
            {"edge_id": "ba", "source": "b", "target": "a", "relation": "back"},
            {"edge_id": "dangling", "source": "missing", "target": "b", "relation": "bad"},
        ]
        result = validate_reasoning_graph(nodes, edges)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(result["dependency_cycle_detected"])
        self.assertIn("dangling", result["dangling_edges"])
        duplicates = validate_reasoning_graph(
            [{"node_id": "same", "node_type": "claim"}, {"node_id": "same", "node_type": "evidence"}],
            [],
        )
        self.assertEqual(duplicates["status"], "FAIL")
        self.assertIn("same", duplicates["duplicate_node_ids"])
        duplicate_edges = validate_reasoning_graph(
            [{"node_id": "x", "node_type": "claim"}, {"node_id": "y", "node_type": "evidence"}],
            [
                {"edge_id": "same-edge", "source": "x", "target": "y"},
                {"edge_id": "same-edge", "source": "x", "target": "y"},
            ],
        )
        self.assertEqual(duplicate_edges["status"], "FAIL")
        self.assertIn("same-edge", duplicate_edges["duplicate_edge_ids"])

    def test_semantic_review_json_schema_documents_the_review_contract(self):
        schema_path = Path(__file__).resolve().parents[1] / "schemas" / "semantic-review.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertIn("source_sha256", schema["properties"])
        self.assertIn("graph_fingerprint", schema["properties"])
        self.assertIn("assessments", schema["required"])
        self.assertIn("partially_supported", schema["properties"]["assessments"]["items"]["properties"]["relation"]["enum"])

    def test_semantic_review_template_is_bound_to_source_and_graph(self):
        text = (
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score."
        )
        report = self.audit_text(text).to_dict()
        template = build_semantic_review_template(report)
        self.assertEqual(template["source_sha256"], report["sha256"])
        self.assertEqual(template["graph_fingerprint"], report["reasoning_graph"]["graph_fingerprint"])
        self.assertEqual(len(template["assessments"]), 1)
        assessment = template["assessments"][0]
        evidence_id = assessment["evidence_node_ids"][0]
        evidence = next(n for n in report["reasoning_graph"]["nodes"] if n["node_id"] == evidence_id)
        assessment.update({
            "relation": "entailed",
            "confidence": 0.93,
            "rationale": "The result sentence directly reports the same direction and measured outcome as the claim.",
            "source_quotes": [evidence["text"]],
            "missing_assumptions": [],
            "counter_evidence_node_ids": [],
        })
        template["reviewer"] = {
            "name": "Test reviewer",
            "model_or_agent": "unit-test",
            "reviewed_at_utc": "2026-11-02T00:00:00Z",
        }
        accepted = validate_semantic_review(template, report, text)
        self.assertEqual(accepted["status"], "ACCEPTED_FOR_REVIEW")
        self.assertEqual(accepted["validated_assessments"][0]["validation_status"],
                         "structurally_validated_not_truth_verified")

    def test_semantic_review_rejects_wrong_claim_link_and_missing_reviewer(self):
        text = (
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score.\n"
            "The intervention decreased the measured score."
        )
        report = self.audit_text(text).to_dict()
        template = build_semantic_review_template(report)
        assessment = template["assessments"][0]
        assessment.update({
            "relation": "entailed",
            "confidence": 0.9,
            "rationale": "Direct match.",
            "source_quotes": ["The intervention increased the measured score."],
        })
        template["reviewer"] = {"name": "", "model_or_agent": "", "reviewed_at_utc": ""}
        other_claim_id = next(
            node["node_id"] for node in report["reasoning_graph"]["nodes"]
            if node["node_type"] == "claim" and node["node_id"] != assessment["claim_node_id"]
        )
        assessment["claim_node_id"] = other_claim_id
        rejected = validate_semantic_review(template, report, text)
        self.assertEqual(rejected["status"], "REJECTED")
        self.assertTrue(any("reviewer.name" in err for err in rejected["errors"]))
        self.assertTrue(any("does not match" in err for err in rejected["errors"]))

    def test_semantic_review_quote_must_match_the_selected_evidence_node(self):
        text = (
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score."
        )
        report = self.audit_text(text).to_dict()
        template = build_semantic_review_template(report)
        assessment = template["assessments"][0]
        method_node = next(
            node for node in report["reasoning_graph"]["nodes"]
            if node["node_type"] == "method"
        )
        assessment.update({
            "relation": "entailed",
            "confidence": 0.9,
            "rationale": "A quote from the methods section is not result evidence.",
            "source_quotes": [method_node["text"]],
        })
        template["reviewer"] = {
            "name": "Test reviewer",
            "model_or_agent": "unit-test",
            "reviewed_at_utc": "2026-11-02T00:00:00Z",
        }
        rejected = validate_semantic_review(template, report, text)
        self.assertEqual(rejected["status"], "REJECTED")
        self.assertTrue(any("cited evidence node" in err for err in rejected["errors"]))

    def test_semantic_review_rejects_extreme_confidence_without_crashing(self):
        text = """# Methods
A randomized study was conducted.
# Results
The intervention increased the measured score.
# Conclusion
The intervention increased the measured score.
"""
        report = self.audit_text(text).to_dict()
        template = build_semantic_review_template(report)
        template["reviewer"] = {
            "name": "Test reviewer",
            "model_or_agent": "unit-test",
            "reviewed_at_utc": "2026-11-02T00:00:00Z",
        }
        template["assessments"][0].update({
            "relation": "entailed",
            "confidence": 10**1000,
            "rationale": "Extreme value test.",
            "source_quotes": ["The intervention increased the measured score."],
        })
        rejected = validate_semantic_review(template, report, text)
        self.assertEqual(rejected["status"], "REJECTED")
        self.assertTrue(any("confidence" in err for err in rejected["errors"]))

    def test_semantic_review_rejects_unhashable_node_id_inputs_without_crashing(self):
        text = (
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score."
        )
        report = self.audit_text(text).to_dict()
        template = build_semantic_review_template(report)
        template["assessments"][0]["evidence_node_ids"] = [{"not": "an id"}]
        rejected = validate_semantic_review(template, report, text)
        self.assertEqual(rejected["status"], "REJECTED")
        self.assertTrue(any("evidence_node_ids" in err for err in rejected["errors"]))

    def test_rejected_semantic_review_still_renders_a_markdown_report(self):
        text = """# Methods
A randomized study was conducted.
# Results
The intervention increased the measured score.
# Conclusion
The intervention increased the measured score.
"""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        source = Path(tmp.name) / "paper.md"
        review_path = Path(tmp.name) / "review.json"
        source.write_text(text, encoding="utf-8")
        report = audit_file(source)
        template = build_semantic_review_template(report.to_dict())
        template["reviewer"] = {"name": "", "model_or_agent": "", "reviewed_at_utc": ""}
        assessment = template["assessments"][0]
        assessment.update({
            "relation": "entailed",
            "confidence": "not-a-number",
            "rationale": "Invalid test fixture.",
            "source_quotes": ["The intervention increased the measured score."],
        })
        review_path.write_text(json.dumps(template), encoding="utf-8")
        rejected_report = audit_file(source, str(review_path))
        markdown = to_markdown(rejected_report)
        self.assertEqual(rejected_report.semantic_review["status"], "REJECTED")
        self.assertIn("confidence invalid", markdown)

    def test_semantic_review_rejects_wrong_source_hash_and_fabricated_quote(self):
        text = (
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score."
        )
        report = self.audit_text(text).to_dict()
        template = build_semantic_review_template(report)
        assessment = template["assessments"][0]
        assessment.update({
            "relation": "partially_supported",
            "confidence": 0.8,
            "rationale": "Partially supported.",
            "source_quotes": ["A fabricated sentence not present in the document."],
        })
        template["source_sha256"] = "0" * 64
        rejected = validate_semantic_review(template, report, text)
        self.assertEqual(rejected["status"], "REJECTED")
        self.assertTrue(any("SHA-256" in err for err in rejected["errors"]))
        self.assertTrue(any("quote" in err for err in rejected["errors"]))

    def test_turkish_discussion_is_not_confused_with_results(self):
        report = self.audit_text(
            "# Yöntem\nKontrollü deney.\n"
            "# Bulgular\nUygulama ölçülen skoru artırdı.\n"
            "# Tartışma\nBulgular uygulamanın etkisini desteklemektedir."
        )
        self.assertGreaterEqual(len(report.claim_evidence_candidates), 1)
        self.assertEqual(report.section_names[:3], ["Yöntem", "Bulgular", "Tartışma"])
        self.assertEqual(report.claim_evidence_candidates[0].claim_section, "Tartışma")


class StatisticalVerificationTests(unittest.TestCase):
    def test_welch_recalculation_matches_rounded_reported_values(self):
        spec = {
            "test": "welch_t",
            "group_a": {"mean": 5.0, "sd": 1.0, "n": 25},
            "group_b": {"mean": 4.0, "sd": 1.0, "n": 25},
            "reported": {
                "mean_difference": 1.0,
                "t": 3.536,
                "df": 48.0,
                "p_two_sided": 0.001,
            },
            "tolerances": {
                "mean_difference": 0.001,
                "t": 0.01,
                "df": 0.1,
                "p_two_sided": 0.001,
            },
        }
        result = verify_welch_t_test(spec, input_sha256="a" * 64)
        self.assertEqual(result["status"], "PASS")
        self.assertAlmostEqual(result["calculated"]["mean_difference"], 1.0)
        self.assertAlmostEqual(result["calculated"]["df"], 48.0)
        self.assertEqual(len(result["input_sha256"]), 64)

    def test_welch_result_matches_scipy_reference_implementation(self):
        from scipy import stats

        spec = {
            "test": "welch_t",
            "group_a": {"mean": 8.2, "sd": 2.4, "n": 31},
            "group_b": {"mean": 6.7, "sd": 1.8, "n": 27},
        }
        result = verify_welch_t_test(spec)
        reference = stats.ttest_ind_from_stats(
            mean1=8.2, std1=2.4, nobs1=31,
            mean2=6.7, std2=1.8, nobs2=27,
            equal_var=False,
        )
        self.assertAlmostEqual(result["calculated"]["t"], float(reference.statistic), places=12)
        self.assertAlmostEqual(result["calculated"]["p_two_sided"], float(reference.pvalue), places=12)

    def test_welch_recalculation_detects_mismatched_t_statistic(self):
        spec = {
            "test": "welch_t",
            "group_a": {"mean": 5.0, "sd": 1.0, "n": 25},
            "group_b": {"mean": 4.0, "sd": 1.0, "n": 25},
            "reported": {"t": 1.2},
            "tolerances": {"t": 0.01},
        }
        result = verify_welch_t_test(spec)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["reported_checks"][0]["status"], "FAIL")

    def test_default_tolerance_uses_reported_decimal_precision(self):
        spec = {
            "test": "welch_t",
            "group_a": {"mean": 5.0, "sd": 1.0, "n": 25},
            "group_b": {"mean": 4.0, "sd": 1.0, "n": 25},
            "reported": {"p_two_sided": 0.02},
        }
        result = verify_welch_t_test(spec)
        check = result["reported_checks"][0]
        self.assertEqual(check["status"], "FAIL")
        self.assertAlmostEqual(check["absolute_tolerance"], 0.005)

    def test_welch_rejects_zero_reported_p_value(self):
        spec = {
            "test": "welch_t",
            "group_a": {"mean": 5.0, "sd": 1.0, "n": 25},
            "group_b": {"mean": 4.0, "sd": 1.0, "n": 25},
            "reported": {"p_two_sided": 0.0},
        }
        with self.assertRaises(ValueError):
            verify_welch_t_test(spec)

    def test_checked_in_welch_example_file_parses_and_passes(self):
        example = Path(__file__).resolve().parents[1] / "examples" / "welch_t_example.json"
        result = verify_stats_file(example)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(len(result["input_sha256"]), 64)

    def test_welch_rejects_invalid_sample_sizes(self):
        spec = {
            "test": "welch_t",
            "group_a": {"mean": 5.0, "sd": 1.0, "n": 1},
            "group_b": {"mean": 4.0, "sd": 1.0, "n": 25},
        }
        with self.assertRaises(ValueError):
            verify_welch_t_test(spec)


if __name__ == "__main__":
    unittest.main()
