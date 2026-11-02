import json
import tempfile
import unittest
from pathlib import Path

from sra.audit import audit_file
from sra.document import load_document
from sra.checks import _direction
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

    def test_document_parser_keeps_duplicate_headings_and_ignores_fenced_code_headings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "paper.md"
            path.write_text(
                "# Methods\nA protocol was defined.\n"
                "# Results\nFirst endpoint increased.\n"
                "~~~markdown\n~~~python\n# Conclusion\nThis is only a code example.\n~~~\n"
                "# Results\nSecond endpoint decreased.\n"
                "# Conclusion\nThe second endpoint decreased."
            )
            document = load_document(path)
        self.assertIn("Results", document.sections)
        self.assertIn("Results (2)", document.sections)
        self.assertEqual(document.sections["Results"], "First endpoint increased.")
        self.assertEqual(document.sections["Results (2)"], "Second endpoint decreased.")
        self.assertEqual(document.sections["Conclusion"], "The second endpoint decreased.")
        self.assertNotIn("code example", document.sections["Results"])
        self.assertEqual(document.section_start_lines["Results (2)"], 11)
        self.assertEqual(document.section_start_lines["Conclusion"], 13)

    def test_plain_text_conventional_headings_are_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "paper.txt"
            path.write_text(
                "Methods\nThis was a cross-sectional observational study.\n"
                "Results\nExposure was associated with the outcome.\n"
                "Conclusion\nThe exposure caused the outcome."
            )
            report = audit_file(path)
        self.assertIn("Methods", report.section_names)
        self.assertIn("Results", report.section_names)
        self.assertIn("Conclusion", report.section_names)
        self.assertIn(
            "reasoning.causal_claim_observational_design",
            {finding.check_id for finding in report.findings},
        )

    def test_negated_causal_and_directional_phrases_are_not_treated_as_positive(self):
        causal_negated = self.audit_text(
            "# Methods\nThis was a cross-sectional observational study.\n"
            "# Results\nExposure was associated with the measured outcome.\n"
            "# Conclusion\nThe exposure did not cause the measured outcome."
        )
        ids = {finding.check_id for finding in causal_negated.findings}
        self.assertNotIn("reasoning.causal_claim_observational_design", ids)
        self.assertNotIn("reasoning.correlation_causation_review", ids)
        self.assertFalse(any(
            node["node_type"] == "assumption_gap"
            for node in causal_negated.reasoning_graph["nodes"]
        ))

        directional_negated = self.audit_text(
            "# Methods\nA randomized experiment was conducted.\n"
            "# Results\nThe intervention decreased the measured memory score.\n"
            "# Conclusion\nThe intervention did not increase the measured memory score."
        )
        self.assertNotIn(
            "reasoning.directional_contradiction",
            {finding.check_id for finding in directional_negated.findings},
        )
        self.assertEqual(_direction("The article described the protocol."), 0)
        self.assertEqual(_direction("The intervention did not increase the score."), 0)
        self.assertEqual(
            _direction("The intervention did not increase memory but reduced inflammation."),
            -1,
        )

    def test_non_randomized_wording_is_not_cancelled_by_a_cited_prior_trial(self):
        report = self.audit_text(
            "# Methods\nThis was a non-randomized observational cohort study.\n"
            "A previous randomized controlled trial was also discussed.\n"
            "# Results\nExposure was associated with the outcome.\n"
            "# Conclusion\nThe exposure caused the outcome."
        )
        self.assertIn(
            "reasoning.causal_claim_observational_design",
            {finding.check_id for finding in report.findings},
        )

    def test_manifest_records_source_and_environment_fingerprints(self):
        report = self.audit_text(
            "# Methods\nA test was performed.\n# Results\nThe result was stable."
        )
        manifest = report.reproducibility_manifest
        self.assertEqual(manifest["input"]["sha256"], report.sha256)
        self.assertEqual(manifest["input"]["format"], "md")
        self.assertEqual(manifest["manifest_schema_version"], "1.1")
        self.assertEqual(report.schema_version, "1.4")
        self.assertEqual(len(manifest["configuration_sha256"]), 64)
        self.assertEqual(len(manifest["environment_fingerprint"]), 64)
        self.assertEqual(manifest["ruleset_version"], "0.5.0")
        self.assertEqual(manifest["auditor_version"], "0.5.0")
        self.assertEqual(manifest["installed_package_version"], "0.5.0")
        self.assertIn("source_code_revision", manifest)
        self.assertEqual(len(manifest["source_code_sha256"]), 64)
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

    def test_document_context_graph_edges_scale_linearly(self):
        method_lines = "\n".join(
            f"Protocol step {index} was completed under the prespecified procedure."
            for index in range(12)
        )
        limitation_lines = "\n".join(
            f"Study limitation {index} affected interpretation of the subgroup estimate."
            for index in range(8)
        )
        result_lines = "\n".join(
            f"The intervention increased outcome marker {index} in the measured group."
            for index in range(10)
        )
        conclusion_lines = "\n".join(
            f"The intervention increased outcome marker {index} in the measured group."
            for index in range(10)
        )
        report = self.audit_text(
            f"# Methods\n{method_lines}\n"
            f"# Results\n{result_lines}\n"
            f"# Limitations\n{limitation_lines}\n"
            f"# Conclusion\n{conclusion_lines}"
        )
        graph = report.reasoning_graph
        method_count = sum(node["node_type"] == "method" for node in graph["nodes"])
        limitation_count = sum(node["node_type"] == "limitation" for node in graph["nodes"])
        inference_count = sum(node["node_type"] == "inference" for node in graph["nodes"])
        membership_edges = [
            edge for edge in graph["edges"]
            if edge["relation"] == "document_context_membership"
        ]
        method_context_edges = [
            edge for edge in graph["edges"]
            if edge["relation"] == "method_document_context"
        ]
        limitation_context_edges = [
            edge for edge in graph["edges"]
            if edge["relation"] == "limitation_document_context"
        ]
        self.assertEqual(len(membership_edges), method_count + limitation_count)
        self.assertEqual(len(method_context_edges), inference_count)
        self.assertEqual(len(limitation_context_edges), inference_count)
        self.assertLess(
            len(membership_edges) + len(method_context_edges) + len(limitation_context_edges),
            (method_count + limitation_count) * inference_count,
        )

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

        lexically_linked_but_inadequate = self.audit_text(
            "# Methods\nWe assume that exposure was measured accurately in adults.\n"
            "# Results\nExposure was associated with outcome in adults.\n"
            "# Conclusion\nExposure caused outcome in adults."
        )
        linked_nodes = lexically_linked_but_inadequate.reasoning_graph["nodes"]
        linked_gap = next(n for n in linked_nodes if n["node_type"] == "assumption_gap")
        self.assertEqual(linked_gap["status"], "candidate_assumptions_found_review_required")
        self.assertIn("does not establish", linked_gap["text"])

        repeated_section_assumptions = self.audit_text(
            "# Methods\nA protocol was specified.\n"
            "# Results\nWe assume that the baseline score was measured accurately.\n"
            "# Results\nThe outcome was stable."
        )
        assumption_nodes = [
            node for node in repeated_section_assumptions.reasoning_graph["nodes"]
            if node["node_type"] == "assumption"
        ]
        self.assertEqual(len(assumption_nodes), 1)

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

        malformed_node = validate_reasoning_graph([{"node_id": [], "node_type": "claim"}], [])
        self.assertEqual(malformed_node["status"], "FAIL")
        self.assertIn(0, malformed_node["invalid_node_entries"])
        malformed_edge = validate_reasoning_graph(
            [{"node_id": "claim-1", "node_type": "claim"}],
            [{"edge_id": "edge-1", "source": [], "target": "claim-1"}],
        )
        self.assertEqual(malformed_edge["status"], "FAIL")
        self.assertIn(0, malformed_edge["invalid_edge_entries"])
        malformed_shapes = validate_reasoning_graph([None], [None])
        self.assertEqual(malformed_shapes["status"], "FAIL")

    def test_semantic_review_json_schema_documents_the_review_contract(self):
        schema_path = Path(__file__).resolve().parents[1] / "schemas" / "semantic-review.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema["properties"]["schema_version"]["const"], "1.3")
        self.assertIn("review_mode", schema["required"])
        self.assertIn("evidence_catalog", schema["required"])
        self.assertIn("reviewer_selected_evidence_node_ids",
                        schema["properties"]["assessments"]["items"]["required"])
        self.assertIn("source_sha256", schema["properties"])
        self.assertIn("graph_fingerprint", schema["properties"])
        self.assertIn("assessments", schema["required"])
        self.assertIn("partially_supported", schema["properties"]["assessments"]["items"]["properties"]["relation"]["enum"])

    def test_semantic_review_mode_is_user_selectable(self):
        report = self.audit_text(
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score."
        ).to_dict()
        single = build_semantic_review_template(report)
        parallel = build_semantic_review_template(report, review_mode="parallel")
        self.assertEqual(single["review_mode"], "single")
        self.assertEqual(parallel["review_mode"], "parallel")
        self.assertIn("one model", single["instructions"][0])
        self.assertIn("parallel agents", parallel["instructions"][0])
        with self.assertRaises(ValueError):
            build_semantic_review_template(report, review_mode="automatic")

    def test_semantic_review_rejects_unlinked_evidence_and_one_word_quotes(self):
        text = (
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "The unrelated biomarker concentration decreased after storage.\n"
            "Participants showed higher values on the assessment scale following treatment.\n"
            "# Conclusion\nThe intervention increased the measured score."
        )
        report = self.audit_text(text).to_dict()
        template = build_semantic_review_template(report)
        assessment = template["assessments"][0]
        evidence_nodes = [
            node for node in report["reasoning_graph"]["nodes"]
            if node["node_type"] == "evidence"
        ]
        selected = assessment["evidence_node_ids"][0]
        unrelated = next(node for node in evidence_nodes if node["node_id"] != selected)
        assessment.update({
            "relation": "entailed",
            "confidence": 0.99,
            "rationale": "The selected sentence is claimed to entail the conclusion.",
            "source_quotes": [unrelated["text"]],
        })
        template["reviewer"] = {
            "name": "Test reviewer",
            "model_or_agent": "unit-test",
            "reviewed_at_utc": "2026-11-02T00:00:00Z",
        }
        assessment["evidence_node_ids"] = [unrelated["node_id"]]
        rejected_unlinked = validate_semantic_review(template, report, text)
        self.assertEqual(rejected_unlinked["status"], "REJECTED")
        self.assertTrue(any("not linked to its inference" in error for error in rejected_unlinked["errors"]))

        assessment["evidence_node_ids"] = [selected]
        assessment["source_quotes"] = ["The"]
        rejected_short = validate_semantic_review(template, report, text)
        self.assertEqual(rejected_short["status"], "REJECTED")
        self.assertTrue(any("too short" in error for error in rejected_short["errors"]))

        paraphrased = next(
            node for node in evidence_nodes
            if node["node_id"] not in {selected, unrelated["node_id"]}
        )
        assessment["source_quotes"] = [paraphrased["text"]]
        assessment["reviewer_selected_evidence_node_ids"] = [paraphrased["node_id"]]
        accepted_additional = validate_semantic_review(template, report, text)
        self.assertEqual(accepted_additional["status"], "ACCEPTED_FOR_REVIEW")
        self.assertEqual(
            accepted_additional["validated_assessments"][0]["reviewer_selected_evidence_node_ids"],
            [paraphrased["node_id"]],
        )

    def test_semantic_review_runtime_matches_schema_required_and_extra_fields(self):
        text = (
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score."
        )
        report = self.audit_text(text).to_dict()
        template = build_semantic_review_template(report)
        evidence_id = template["assessments"][0]["evidence_node_ids"][0]
        evidence = next(
            node for node in report["reasoning_graph"]["nodes"]
            if node["node_id"] == evidence_id
        )
        template["reviewer"] = {
            "name": "Test reviewer",
            "model_or_agent": "unit-test",
            "reviewed_at_utc": "2026-11-02T00:00:00Z",
        }
        template["assessments"][0].update({
            "relation": "entailed",
            "confidence": 0.9,
            "rationale": "The linked result matches the claim.",
            "source_quotes": [evidence["text"]],
        })
        missing = json.loads(json.dumps(template))
        missing.pop("instructions")
        missing.pop("relation_labels")
        rejected_missing = validate_semantic_review(missing, report, text)
        self.assertEqual(rejected_missing["status"], "REJECTED")
        self.assertTrue(any("instructions" in error for error in rejected_missing["errors"]))
        self.assertTrue(any("relation_labels" in error for error in rejected_missing["errors"]))

        extra = json.loads(json.dumps(template))
        extra["unrecognized"] = True
        rejected_extra = validate_semantic_review(extra, report, text)
        self.assertEqual(rejected_extra["status"], "REJECTED")
        self.assertTrue(any("Unexpected top-level" in error for error in rejected_extra["errors"]))

        tampered_catalog = json.loads(json.dumps(template))
        tampered_catalog["evidence_catalog"][0]["text"] = "Modified source passage."
        rejected_catalog = validate_semantic_review(tampered_catalog, report, text)
        self.assertEqual(rejected_catalog["status"], "REJECTED")
        self.assertTrue(any("catalog text does not match" in error for error in rejected_catalog["errors"]))

        offset = json.loads(json.dumps(template))
        offset["reviewer"]["reviewed_at_utc"] = "2026-11-02T03:00:00+03:00"
        rejected_offset = validate_semantic_review(offset, report, text)
        self.assertEqual(rejected_offset["status"], "REJECTED")
        self.assertTrue(any("must use UTC" in error for error in rejected_offset["errors"]))

    def test_legacy_semantic_review_v10_imports_as_single_mode(self):
        text = (
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score."
        )
        report = self.audit_text(text).to_dict()
        legacy = build_semantic_review_template(report)
        evidence_id = legacy["assessments"][0]["evidence_node_ids"][0]
        evidence = next(
            node for node in report["reasoning_graph"]["nodes"]
            if node["node_id"] == evidence_id
        )
        legacy["assessments"][0].update({
            "relation": "entailed",
            "confidence": 0.9,
            "rationale": "The result passage matches the conclusion claim.",
            "source_quotes": [evidence["text"]],
        })
        legacy["reviewer"] = {
            "name": "Legacy reviewer",
            "model_or_agent": "unit-test",
            "reviewed_at_utc": "2026-11-02T00:00:00Z",
        }
        legacy["schema_version"] = "1.0"
        legacy.pop("review_mode")
        legacy.pop("evidence_catalog")
        legacy["assessments"][0].pop("reviewer_selected_evidence_node_ids")
        result = validate_semantic_review(legacy, report, text)
        self.assertEqual(result["status"], "ACCEPTED_FOR_REVIEW")
        self.assertEqual(result["review_mode"], "single")

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
        self.assertEqual(
            {node["node_id"] for node in template["evidence_catalog"]},
            {
                node["node_id"] for node in report["reasoning_graph"]["nodes"]
                if node["node_type"] == "evidence"
            },
        )
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
        self.assertTrue(any("selected evidence" in err for err in rejected["errors"]))

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


class ModelClientTests(unittest.TestCase):
    def test_extracts_json_from_model_fenced_response(self):
        from sra.model_client import _extract_json_object
        self.assertEqual(_extract_json_object(chr(96)*3 + 'json\n{"ok": true}\n' + chr(96)*3), {"ok": True})

    def test_rejects_non_object_model_response(self):
        from sra.model_client import _extract_json_object
        with self.assertRaises(ValueError):
            _extract_json_object('[{"not":"an object"}]')

    def test_single_model_requires_single_template_and_api_key(self):
        from unittest.mock import patch
        from sra.model_client import request_single_model_review
        with self.assertRaises(ValueError):
            request_single_model_review({"review_mode":"parallel"}, "paper", model="m", base_url="https://example.test/v1")
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "not set"):
                request_single_model_review({"review_mode":"single"}, "paper", model="m",
                    base_url="https://example.test/v1", api_key_env="SRA_TEST_KEY")

    def test_single_model_posts_to_openai_compatible_endpoint(self):
        import json
        from unittest.mock import patch
        from sra.model_client import request_single_model_review

        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return json.dumps({"choices":[{"message":{"content":'{"review_mode":"single"}'}}]}).encode()

        template = {"review_mode":"single", "assessments":[]}
        with patch.dict("os.environ", {"SRA_TEST_KEY":"test-key"}):
            with patch("sra.model_client.urlopen", return_value=FakeResponse()) as mocked:
                result = request_single_model_review(
                    template, "Full manuscript", model="test-model",
                    base_url="https://example.test/v1", api_key_env="SRA_TEST_KEY"
                )
        self.assertEqual(result, {"review_mode":"single"})
        request = mocked.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.test/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        sent = json.loads(request.data.decode())
        self.assertEqual(sent["model"], "test-model")
        self.assertEqual(sent["temperature"], 0)
