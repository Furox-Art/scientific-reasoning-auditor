"""Regressions and independent numerical cross-checks for expansion modules."""
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from sra.stats import verify_stats_file
from sra.stats_extended import verify_extended_stats
from sra.writing import audit_academic_writing, writing_report_markdown
from sra.doi import normalize_doi, verify_dois, _lookup_crossref, _lookup_datacite, _title_context_overlap
from sra.benchmark import run_pmc_benchmark, _get_article
from sra.discipline import CHECKLISTS


def temporary_file(text, suffix=".md"):
    directory = tempfile.TemporaryDirectory()
    path = Path(directory.name) / ("example" + suffix)
    path.write_text(text, encoding="utf-8")
    return directory, path


def code_names(result):
    return {item["code"] for item in result["findings"]}


class NewStatisticalTests(unittest.TestCase):
    def test_one_sample_matches_scipy_reference(self):
        from scipy import stats
        values = [5, 7, 9, 11, 13]
        import statistics
        spec = {"test": "one_sample_t", "sample": {
            "mean": statistics.mean(values), "sd": statistics.stdev(values),
            "n": len(values)}, "mu0": 7}
        result = verify_extended_stats(spec)
        scipy_result = stats.ttest_1samp(values, popmean=7)
        self.assertAlmostEqual(result["calculated"]["t"], scipy_result.statistic, places=13)
        self.assertAlmostEqual(result["calculated"]["p_two_sided"], scipy_result.pvalue, places=13)
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(result["calculated"]["df"], 4)
        self.assertLess(result["calculated"]["confidence_interval_95"][0], 2)
        self.assertGreater(result["calculated"]["confidence_interval_95"][1], 2)

    def test_paired_matches_scipy_reference(self):
        from scipy import stats
        import statistics
        before = [13, 15, 11, 17, 14, 18]
        after = [12, 12, 10, 13, 12, 15]
        diffs = [a-b for a, b in zip(after, before)]
        spec = {"test": "paired_t", "differences": {
            "mean": statistics.mean(diffs),
            "sd": statistics.stdev(diffs), "n": len(diffs)}}
        result = verify_extended_stats(spec)
        scipy_result = stats.ttest_rel(after, before)
        self.assertAlmostEqual(result["calculated"]["t"], scipy_result.statistic, places=13)
        self.assertAlmostEqual(result["calculated"]["p_two_sided"], scipy_result.pvalue, places=13)

    def test_chi_square_matches_independent_scipy(self):
        from scipy.stats import chi2_contingency
        table = [[25, 15], [10, 30]]
        result = verify_extended_stats({"test": "chi_square_2x2", "table": table})
        independent = chi2_contingency(table, correction=False)
        self.assertAlmostEqual(result["calculated"]["chi_square"], independent.statistic, places=12)
        self.assertAlmostEqual(result["calculated"]["p_value"], independent.pvalue, places=12)
        self.assertEqual(result["calculated"]["df"], 1)
        self.assertEqual(result["warnings"], [])

    def test_low_expected_chi_square_warns(self):
        result = verify_extended_stats({"test": "chi_square_2x2", "table": [[1, 3], [2, 4]]})
        self.assertTrue(any("below 5" in item for item in result["warnings"]))

    def test_fisher_matches_independent_scipy(self):
        from scipy import stats
        table = [[1, 9], [11, 3]]
        result = verify_extended_stats({"test": "fisher_exact_2x2", "table": table})
        scipy_result = stats.fisher_exact(table, alternative="two-sided")
        self.assertAlmostEqual(result["calculated"]["p_two_sided"], scipy_result.pvalue, places=13)
        self.assertAlmostEqual(result["calculated"]["odds_ratio"], scipy_result.statistic, places=13)

    def test_fisher_zero_cell_never_outputs_infinity(self):
        result = verify_extended_stats({"test": "fisher_exact_2x2", "table": [[10, 0], [2, 3]]})
        self.assertIsNone(result["calculated"]["odds_ratio"])
        self.assertTrue(result["warnings"])
        json.dumps(result, allow_nan=False)

    def test_reported_value_pass_fail_and_unknown(self):
        base = {
            "test": "one_sample_t",
            "sample": {"mean": 8, "sd": 2, "n": 25}, "mu0": 7,
            "reported": {"t": 2.5, "extra": "not measured"},
        }
        result = verify_extended_stats(base)
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(result["reported_checks"][1]["status"], "NOT_VERIFIED")
        base["reported"] = {"t": 0.25}
        self.assertEqual(verify_extended_stats(base)["status"], "FAIL")
        base["reported"] = {"t": 2.5}
        self.assertEqual(verify_extended_stats(base)["status"], "PASS")

    def test_invalid_std_and_n_rejected(self):
        for pair in ((0, 10), (-1, 10), (2, 1), (2, True)):
            sd, n = pair
            with self.subTest(sd=sd, n=n):
                spec = {"test": "one_sample_t", "sample": {"mean": 3, "sd": sd, "n": n}}
                with self.assertRaises(ValueError):
                    verify_extended_stats(spec)

    def test_table_shape_nonintegers_and_empty_margins_rejected(self):
        invalid = [
            [[1, 2, 3], [2, 3, 4]],
            [[1, -1], [2, 3]],
            [[0, 0], [2, 3]],
            [[1, 0], [3, 0]],
            [[2.0, 1], [1, 3]],
            [[True, 1], [1, 2]],
            [[2**54, 0], [1, 1]],
        ]
        for table in invalid:
            with self.subTest(table=table):
                with self.assertRaises(ValueError):
                    verify_extended_stats({"test": "fisher_exact_2x2", "table": table})

    def test_rejects_zero_p_and_negative_tolerance(self):
        spec = {"test": "fisher_exact_2x2", "table": [[5, 10], [10, 5]],
                "reported": {"p_two_sided": 0}}
        with self.assertRaises(ValueError):
            verify_extended_stats(spec)
        spec = {"test": "fisher_exact_2x2", "table": [[5, 10], [10, 5]],
                "tolerances": {"default": -0.1}}
        with self.assertRaises(ValueError):
            verify_extended_stats(spec)

    def test_input_dispatch_and_sha_reproducibility(self):
        payload = json.dumps({"test": "paired_t", "differences": {"mean": 2, "sd": 3, "n": 20}})
        tmp, path = temporary_file(payload, ".json")
        with tmp:
            result = verify_stats_file(path)
        self.assertEqual(result["test"], "paired_t")
        self.assertEqual(len(result["input_sha256"]), 64)
        json.dumps(result, allow_nan=False)

    def test_randomized_t_and_contingency_properties_against_scipy(self):
        import random
        import statistics
        from scipy import stats
        rng = random.Random(20261105)
        for trial in range(50):
            n = rng.randrange(4, 100)
            sample = [rng.gauss(2.5, 3.5) for _ in range(n)]
            sd = statistics.stdev(sample)
            mu0 = rng.uniform(-1, 1)
            spec = {"test": "one_sample_t", "mu0": mu0,
                    "sample": {"mean": statistics.mean(sample), "sd": sd, "n": n}}
            result = verify_extended_stats(spec)
            expected = stats.ttest_1samp(sample, mu0)
            with self.subTest(case=trial, method="one_sample_t"):
                self.assertAlmostEqual(result["calculated"]["t"], expected.statistic, places=11)
                self.assertAlmostEqual(result["calculated"]["p_two_sided"], expected.pvalue, places=11)
            table = [[rng.randrange(1, 20), rng.randrange(1, 20)],
                     [rng.randrange(1, 20), rng.randrange(1, 20)]]
            chi = verify_extended_stats({"test": "chi_square_2x2", "table": table})
            reference = stats.chi2_contingency(table, correction=False)
            with self.subTest(case=trial, method="chi_square_2x2"):
                self.assertAlmostEqual(chi["calculated"]["chi_square"], reference.statistic, places=12)
                self.assertAlmostEqual(chi["calculated"]["p_value"], reference.pvalue, places=12)
            if trial < 20:
                fisher = verify_extended_stats({"test": "fisher_exact_2x2", "table": table})
                ref_fisher = stats.fisher_exact(table, alternative="two-sided")
                with self.subTest(case=trial, method="fisher_exact_2x2"):
                    self.assertAlmostEqual(fisher["calculated"]["p_two_sided"], ref_fisher.pvalue, places=12)

    def test_fisher_computational_limit_is_explicit(self):
        spec = {"test": "fisher_exact_2x2", "table": [[400000, 200000], [200000, 400000]]}
        with self.assertRaisesRegex(ValueError, "limit"):
            verify_extended_stats(spec)

    def test_two_proportion_matches_independent_scipy(self):
        from scipy import stats
        table = [[40, 60], [30, 90]]
        result = verify_extended_stats({"test": "two_proportion_z", "table": table})
        p_a, p_b = 40 / 100, 30 / 120
        pooled = (40 + 30) / 220
        standard_error = math.sqrt(pooled * (1 - pooled) * (1 / 100 + 1 / 120))
        z_stat = (p_a - p_b) / standard_error
        reference = 2.0 * stats.norm.sf(abs(z_stat))
        self.assertAlmostEqual(result["calculated"]["z"], z_stat, places=13)
        self.assertAlmostEqual(result["calculated"]["p_two_sided"], reference, places=13)
        self.assertAlmostEqual(result["calculated"]["difference"], 0.4 - 0.25, places=15)
        self.assertEqual(result["calculated"]["total_n"], 220)
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(result["warnings"], [])
        interval = result["calculated"]["confidence_interval_95"]
        self.assertLess(interval[0], 0.15)
        self.assertGreater(interval[1], 0.15)
        self.assertTrue(any("unpooled Wald" in item for item in result["limitations"]))
        json.dumps(result, allow_nan=False)

    def test_two_proportion_reported_pass_and_fail(self):
        from scipy import stats
        table = [[40, 60], [30, 90]]
        p_a, p_b = 40 / 100, 30 / 120
        pooled = 70 / 220
        standard_error = math.sqrt(pooled * (1 - pooled) * (1 / 100 + 1 / 120))
        z_stat = (p_a - p_b) / standard_error
        p_value = 2.0 * stats.norm.sf(abs(z_stat))
        spec = {
            "test": "two_proportion_z", "table": table,
            "reported": {"z": round(z_stat, 6), "p_two_sided": round(p_value, 6)},
            "tolerances": {"z": 1e-6, "p_two_sided": 1e-6},
        }
        self.assertEqual(verify_extended_stats(spec)["status"], "PASS")
        spec["reported"] = {"z": round(z_stat, 6) + 0.5}
        self.assertEqual(verify_extended_stats(spec)["status"], "FAIL")

    def test_two_proportion_warns_on_sparse_counts_and_degenerate_interval(self):
        low = verify_extended_stats({"test": "two_proportion_z", "table": [[1, 3], [4, 4]]})
        self.assertTrue(any("below 5" in item for item in low["warnings"]))
        degenerate = verify_extended_stats({
            "test": "two_proportion_z", "table": [[0, 10], [10, 0]],
        })
        self.assertIsNone(degenerate["calculated"]["confidence_interval_95"])
        self.assertTrue(any("degenerate" in item for item in degenerate["warnings"]))
        json.dumps(degenerate, allow_nan=False)

    def test_two_proportion_p_underflow_is_explicit(self):
        spec = {"test": "two_proportion_z", "table": [[2**51, 2**51], [0, 2**52]]}
        with self.assertRaisesRegex(ValueError, "underflowed p=0"):
            verify_extended_stats(spec)

    def test_two_proportion_table_validation_and_file_dispatch(self):
        with self.assertRaisesRegex(ValueError, "two rows of two counts"):
            verify_extended_stats({
                "test": "two_proportion_z", "table": [[1, 2], [3, 4], [5, 6]],
            })
        payload = json.dumps({"test": "two_proportion_z", "table": [[12, 8], [7, 13]]})
        tmp, path = temporary_file(payload, ".json")
        with tmp:
            result = verify_stats_file(path)
        self.assertEqual(result["test"], "two_proportion_z")
        self.assertEqual(len(result["input_sha256"]), 64)
        json.dumps(result, allow_nan=False)

    def test_unknown_test_rejected(self):
        with self.assertRaisesRegex(ValueError, "Supported extended tests"):
            verify_extended_stats({"test": "invented_test"})

    def test_extreme_mean_difference_rejected(self):
        spec = {"test": "one_sample_t",
                "sample": {"mean": 1e308, "sd": 1.0, "n": 12}, "mu0": -1e308}
        with self.assertRaisesRegex(ValueError, "outside"):
            verify_extended_stats(spec)


class AcademicStyleAndDisciplineTests(unittest.TestCase):
    def test_english_edits_are_advisory_and_source_unchanged(self):
        manuscript = ("# Introduction\n"
                      "This is a analysis of a experiment and the the response. "
                      "In order to replicate, document the details.\n")
        tmp, path = temporary_file(manuscript)
        with tmp:
            report = audit_academic_writing(path, style_language="en")
            self.assertEqual(path.read_text(encoding="utf-8"), manuscript)
        style = report["style_suggestions"]
        types = {item["code"] for item in style}
        self.assertIn("article_agreement", types)
        self.assertIn("repeated_word", types)
        self.assertIn("concision", types)
        self.assertTrue(all(item["line"] == 2 for item in style))
        self.assertTrue(all(item["suggestion"] for item in style))

    def test_turkish_profile_does_not_apply_english_rules(self):
        tmp, path = temporary_file("# Giriş\nThis is a analysis and the the issue.\n")
        with tmp:
            report = audit_academic_writing(path, style_language="tr")
        self.assertIn("repeated_word", {item["code"] for item in report["style_suggestions"]})
        self.assertNotIn("article_agreement", {item["code"] for item in report["style_suggestions"]})

    def test_turkish_spelling_hints(self):
        tmp, path = temporary_file("# Giriş\nBu yanlız bir çok her hangi örnek.\n")
        with tmp:
            report = audit_academic_writing(path, style_language="tr")
        suggestions = [item["suggestion"] for item in report["style_suggestions"]]
        self.assertIn("yalnız", suggestions)
        self.assertIn("birçok", suggestions)
        self.assertIn("herhangi", suggestions)

    def test_english_modal_grammar_and_spelling(self):
        tmp, path = temporary_file("# Introduction\nWe should of written alot more.\n")
        with tmp:
            report = audit_academic_writing(path, style_language="en")
        suggestions = [item["suggestion"] for item in report["style_suggestions"]]
        self.assertIn("should have", suggestions)
        self.assertIn("a lot", suggestions)

    def test_can_disable_style_review(self):
        tmp, path = temporary_file("# Introduction\nThis is a analysis.\n")
        with tmp:
            report = audit_academic_writing(path, style_language="none")
        self.assertEqual(report["style_suggestions"], [])

    def test_long_line_cue_not_claimed_to_be_sentence(self):
        text = "# Methods\n" + ("word " * 43) + "\n"
        tmp, path = temporary_file(text)
        with tmp:
            report = audit_academic_writing(path)
        self.assertTrue(any(item["code"] == "long_line" for item in report["style_suggestions"]))
        long_cue = next(item for item in report["style_suggestions"] if item["code"] == "long_line")
        self.assertIn("not necessarily one sentence", long_cue["message"])

    def test_style_not_run_inside_code_and_references(self):
        text = (
            "# Methods\n~~~python\na analysis and the the\n~~~\n"
            "# References\nThe the sample reference.\n")
        tmp, path = temporary_file(text)
        with tmp:
            report = audit_academic_writing(path)
        self.assertEqual(report["style_suggestions"], [])

    def test_guide_types_are_separate_advisory_profiles(self):
        for design, settings in CHECKLISTS.items():
            with self.subTest(design=design):
                tmp, path = temporary_file("# Methods\nThe method was stated.\n")
                with tmp:
                    report = audit_academic_writing(path, design=design)
                profile = report["reporting_checklist"]
                self.assertEqual(profile["design"], design)
                self.assertTrue(profile["items"])
                self.assertTrue(all(item["status"] in (
                    "TEXT_CUE_FOUND", "NOT_DETECTED_REVIEW_MANUALLY",
                ) for item in profile["items"]))
                self.assertIn("not", " ".join(profile["limitations"]).lower())

    def test_guideline_cues_have_source_location(self):
        tmp, path = temporary_file(
            "# Methods\nThe trial used randomization and sample size estimation.\n"
        )
        with tmp:
            result = audit_academic_writing(path, design="clinical-trial")
        cues = result["reporting_checklist"]["items"]
        randomization = next(item for item in cues if item["item"] == "randomization")
        self.assertEqual(randomization["line"], 2)
        self.assertEqual(randomization["status"], "TEXT_CUE_FOUND")
        self.assertTrue(any(item["line"] is None for item in cues))

    def test_rejects_invalid_design_and_style(self):
        tmp, path = temporary_file("# Introduction\nText.\n")
        with tmp:
            with self.assertRaisesRegex(ValueError, "Unsupported study design"):
                audit_academic_writing(path, design="nonexistent")
            with self.assertRaisesRegex(ValueError, "style language"):
                audit_academic_writing(path, style_language="zz")

    def test_html_in_user_text_does_not_become_markdown_html(self):
        tmp, path = temporary_file("# Introduction\nA analysis.\n")
        with tmp:
            report = audit_academic_writing(path)
        report["style_suggestions"][0]["excerpt"] = "<script>alert(1)</script>"
        markdown = writing_report_markdown(report)
        self.assertNotIn("<script>", markdown)
        self.assertIn("&lt;script&gt;", markdown)


class DOIRegistryTests(unittest.TestCase):
    def test_doi_normalization_balanced_and_case(self):
        self.assertEqual(normalize_doi("https://doi.org/10.1234/a(b)c."), "10.1234/a(b)c")
        self.assertEqual(normalize_doi("DOI:10.1371/JOURNAL.PONE.0000217"),
                         "10.1371/journal.pone.0000217")
        self.assertIsNone(normalize_doi("10.abc/invalid"))
        self.assertIsNone(normalize_doi(42))

    def test_doi_offline_does_not_touch_network(self):
        text = "# References\nResearch doi: 10.1371/journal.pone.0000217, repeated 10.1371/journal.pone.0000217.\n"
        tmp, path = temporary_file(text)
        with tmp, patch("sra.doi._lookup_registry") as remote:
            result = verify_dois(path)
            remote.assert_not_called()
        self.assertEqual(result["found_count"], 1)
        self.assertEqual(result["results"][0]["line"], 2)
        self.assertEqual(result["results"][0]["status"], "NOT_CHECKED_OFFLINE")

    def test_online_lookup_called_only_on_explicit_opt_in(self):
        tmp, path = temporary_file("# References\nDOI: 10.1371/journal.pone.0000217\n")
        with tmp, patch("sra.doi._lookup_registry", return_value={
            "status": "REGISTERED_IN_CROSSREF", "title": "Some Source",
        }) as remote:
            report = verify_dois(path, online=True)
            remote.assert_called_once()
        self.assertEqual(report["results"][0]["status"], "REGISTERED_IN_CROSSREF")
        self.assertIn("title_comparison", report["results"][0])

    def test_crossref_not_found_falls_back_to_datacite(self):
        with patch("sra.doi._lookup_crossref", return_value={"status": "NOT_FOUND_IN_CROSSREF"}), \
             patch("sra.doi._lookup_datacite", return_value={"status": "REGISTERED_IN_DATACITE"}) as datacite:
            from sra.doi import _lookup_registry
            result = _lookup_registry("10.6084/example", timeout=3)
        datacite.assert_called_once()
        self.assertEqual(result["status"], "REGISTERED_IN_DATACITE")

    def test_crossref_success_does_not_contact_datacite(self):
        with patch("sra.doi._lookup_crossref", return_value={"status": "REGISTERED_IN_CROSSREF"}), \
             patch("sra.doi._lookup_datacite") as datacite:
            from sra.doi import _lookup_registry
            result = _lookup_registry("10.1371/example", timeout=3)
        datacite.assert_not_called()
        self.assertEqual(result["status"], "REGISTERED_IN_CROSSREF")

    def test_metadata_title_overlap_is_not_source_support(self):
        match = _title_context_overlap("Quantifying Organismal Complexity using a Population Genetic Approach",
                                        "Tenaillon (2007): Quantifying Organismal Complexity using a Population Genetic Approach 10.1234/x",
                                        "10.1234/x")
        self.assertEqual(match["status"], "TITLE_WORDS_OVERLAP")
        nonmatch = _title_context_overlap("Quantifying Organismal Complexity using a Population Genetic Approach",
                                           "This is a clearly unrelated data analysis title 10.1234/x",
                                           "10.1234/x")
        self.assertEqual(nonmatch["status"], "REVIEW_TITLE_MANUALLY")

    def test_non_matching_crossref_metadata_rejected(self):
        from unittest.mock import Mock
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *_): return None
            def read(self, *_):
                return b'{"message":{"DOI":"10.1371/OTHER","title":["Test"]}}'
        opener = Mock()
        opener.open.return_value = Response()
        with patch("sra.doi.build_opener", return_value=opener):
            result = _lookup_crossref("10.1371/example")
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertIn("different DOI", result["reason"])

    def test_crossref_missing_404_not_invalidity_claim(self):
        from unittest.mock import Mock
        opener = Mock()
        opener.open.side_effect = HTTPError("https://api.crossref.org/works/x",404,"not found",{},None)
        with patch("sra.doi.build_opener", return_value=opener):
            result = _lookup_crossref("10.1371/example")
        self.assertEqual(result["status"], "NOT_FOUND_IN_CROSSREF")

    def test_datacite_missing_404_not_invalidity_claim(self):
        from unittest.mock import Mock
        opener = Mock()
        opener.open.side_effect = HTTPError("https://api.datacite.org/dois/x",404,"not found",{},None)
        with patch("sra.doi.build_opener", return_value=opener):
            result = _lookup_datacite("10.1234/example")
        self.assertEqual(result["status"], "NOT_FOUND_IN_CROSSREF_OR_DATACITE")
        self.assertIn("not proof", result["reason"])

    def test_limits_and_invalid_timeouts(self):
        tmp, path = temporary_file("# Introduction\nSimple text.\n")
        with tmp:
            for count in (0, 201, True):
                with self.assertRaises(ValueError):
                    verify_dois(path, limit=count)
            with self.assertRaises(ValueError):
                verify_dois(path, timeout=-1)


class PMCBenchmarkTests(unittest.TestCase):
    def test_requires_explicit_online_permission(self):
        tmp, path = temporary_file('{"pmcids":["PMC1790863"]}', ".json")
        with tmp:
            with self.assertRaisesRegex(ValueError, "explicit"):
                run_pmc_benchmark(path)

    def test_rejects_duplicate_invalid_and_empty_manifest(self):
        cases = [
            {"pmcids": []}, {"pmcids": ["PMC1790863", "PMC1790863"]},
            {"pmcids": ["http://127.0.0.1/"]}, {"pmcids": ["PMC00000"]},
            {"pmdids": ["PMC1790863"]},
        ]
        for case in cases:
            with self.subTest(case=case):
                tmp, path = temporary_file(json.dumps(case), ".json")
                with tmp:
                    with self.assertRaises(ValueError):
                        run_pmc_benchmark(path, online=True)

    def test_external_smoke_has_honest_no_expert_labels(self):
        tmp, path = temporary_file('{"pmcids":["PMC1790863"]}', ".json")
        text = "# Methods\nA study assessed an outcome.\n# Results\nObserved results.\n# Conclusion\nA conclusion.\n"
        metadata = {"pmcid": "PMC1790863", "doi": "10.1371/journal.pone.0000217",
                    "title": "External study", "source_url": "https://www.ncbi.nlm.nih.gov/"}
        with tmp, patch("sra.benchmark._get_article", return_value=(text, metadata)):
            result = run_pmc_benchmark(path, online=True)
        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["independent_expert_labels"], 0)
        self.assertIsNone(result["sensitivity"])
        self.assertIsNone(result["specificity"])
        self.assertIsNone(result["precision"])
        self.assertGreaterEqual(result["paper_results"][0]["reasoning_graph_nodes"], 0)
        self.assertIn("not independent", result["limitations"][0])

    def test_fetch_errors_not_counted_as_processed(self):
        tmp, path = temporary_file('{"pmcids":["PMC1790863"]}', ".json")
        with tmp, patch("sra.benchmark._get_article", side_effect=ValueError("unavailable")):
            result = run_pmc_benchmark(path, online=True)
        self.assertEqual(result["processed"], 0)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["paper_results"][0]["status"], "FETCH_OR_PROCESS_FAILED")


if __name__ == "__main__":
    unittest.main()
