"""Tests for blinded validation pack creation and independent label merging."""
import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sra.cli import main
from sra.labeling import build_validation_pack, merge_adjudicated_labels
from sra.validation import evaluate_blinded_labels

HASHES = {"PMC1234567": "a" * 64, "PMC7654321": "b" * 64}


def write_benchmark(path, papers=None, kind="unlabeled_real_paper_smoke_test"):
    if papers is None:
        papers = [
            {"pmcid": "PMC1234567", "status": "PROCESSED",
             "response_sha256": HASHES["PMC1234567"],
             "writing_finding_codes": ["code_a"]},
            {"pmcid": "PMC7654321", "status": "PROCESSED",
             "response_sha256": HASHES["PMC7654321"],
             "writing_finding_codes": []},
            {"pmcid": "PMC9999999", "status": "FETCH_OR_PROCESS_FAILED"},
        ]
    path.write_text(json.dumps({"kind": kind, "paper_results": papers}), encoding="utf-8")
    return path


def fake_fetch(hashes=None):
    hashes = hashes or HASHES

    def fetch(pmcid):
        return f"# Results\nContent for {pmcid}.\n", {"response_sha256": hashes[pmcid]}

    return fetch


def build_pack(tmp, *, codes=("code_a", "code_b"),
               reviewers=("reviewer_A", "reviewer_B"), manual=True):
    benchmark = write_benchmark(Path(tmp) / "benchmark.json")
    manual_path = None
    if manual:
        manual_path = Path(tmp) / "manual.md"
        manual_path.write_text("Preregistered code definitions for the reviewers.", encoding="utf-8")
    out = Path(tmp) / "pack"
    with patch("sra.labeling._get_article", side_effect=fake_fetch()), \
            patch("sra.labeling.time.sleep") as sleep:
        pack = build_validation_pack(
            benchmark, out, list(reviewers), list(codes), online=True,
            manual_path=manual_path,
        )
    return benchmark, out, pack, sleep


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(path, value):
    Path(path).write_text(json.dumps(value), encoding="utf-8")


def set_verdicts(sheet_path, verdicts):
    sheet = load_json(sheet_path)
    for case, verdict in zip(sheet["cases"], verdicts):
        case["verdict"] = verdict
    save_json(sheet_path, sheet)


class ValidationPackTests(unittest.TestCase):
    def test_pack_writes_blinded_worksheets_and_verified_texts(self):
        with tempfile.TemporaryDirectory() as tmp:
            benchmark, out, pack, sleep = build_pack(tmp)
            benchmark_sha = hashlib.sha256(Path(benchmark).read_bytes()).hexdigest()
            self.assertEqual(pack["paper_count"], 2)
            self.assertEqual(pack["unit_count"], 4)
            self.assertEqual(pack["finding_codes"], ["code_a", "code_b"])
            self.assertEqual(pack["reviewer_ids"], ["reviewer_A", "reviewer_B"])
            self.assertEqual(pack["benchmark_sha256"], benchmark_sha)
            self.assertEqual(len(pack["manual_sha256"]), 64)
            self.assertEqual(sleep.call_count, 1)
            self.assertTrue((out / "README.md").is_file())
            self.assertTrue((out / "coding_manual.md").is_file())
            self.assertTrue((out / "papers" / "PMC1234567.md").is_file())
            self.assertTrue((out / "papers" / "PMC7654321.md").is_file())
            self.assertFalse((out / "papers" / "PMC9999999.md").exists())
            self.assertEqual(len(pack["papers"]), 2)
            for entry in pack["papers"]:
                self.assertEqual(len(entry["text_sha256"]), 64)
                self.assertEqual(
                    (out / entry["text_file"]).read_text(encoding="utf-8"),
                    f"# Results\nContent for {entry['pmcid']}.\n",
                )
            for index, reviewer in enumerate(pack["reviewer_ids"], start=1):
                sheet = load_json(out / f"reviewer_{index}.json")
                self.assertEqual(sheet["kind"], "blinded_validation_worksheet")
                self.assertEqual(sheet["reviewer_id"], reviewer)
                self.assertEqual(sheet["benchmark_sha256"], benchmark_sha)
                self.assertEqual(len(sheet["cases"]), 4)
                self.assertTrue(all(case["verdict"] is None for case in sheet["cases"]))
                self.assertTrue(all(len(case["source_sha256"]) == 64 for case in sheet["cases"]))
                text = (out / f"reviewer_{index}.json").read_text(encoding="utf-8").lower()
                self.assertNotIn("writing_finding_codes", text)
                self.assertNotIn("prediction", text)

    def test_pack_without_manual_and_existing_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            benchmark = write_benchmark(Path(tmp) / "benchmark.json")
            out = Path(tmp) / "existing"
            out.mkdir()
            with patch("sra.labeling._get_article", side_effect=fake_fetch()), \
                    patch("sra.labeling.time.sleep"):
                pack = build_validation_pack(
                    benchmark, out, ["reviewer_A", "reviewer_B"], ["code_a"],
                    online=True,
                )
            self.assertIsNone(pack["manual_sha256"])
            self.assertFalse((out / "coding_manual.md").exists())
            self.assertEqual(pack["unit_count"], 2)

    def test_pack_rejects_invalid_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            valid = write_benchmark(root / "valid.json")
            cases = {
                "offline": lambda: build_validation_pack(
                    valid, root / "a", ["A", "B"], ["code_a"]
                ),
                "wrong kind": lambda: build_validation_pack(
                    write_benchmark(root / "kind.json", kind="other"),
                    root / "b", ["A", "B"], ["code_a"], online=True,
                ),
                "bad paper list": lambda: build_validation_pack(
                    write_benchmark(root / "list.json", papers={}),
                    root / "c", ["A", "B"], ["code_a"], online=True,
                ),
                "no processed": lambda: build_validation_pack(
                    write_benchmark(root / "empty.json", papers=[]),
                    root / "d", ["A", "B"], ["code_a"], online=True,
                ),
                "duplicate paper": lambda: build_validation_pack(
                    write_benchmark(root / "dupe.json", papers=[
                        {"pmcid": "PMC1234567", "status": "PROCESSED",
                         "response_sha256": "a" * 64, "writing_finding_codes": []},
                        {"pmcid": "PMC1234567", "status": "PROCESSED",
                         "response_sha256": "a" * 64, "writing_finding_codes": []},
                    ]),
                    root / "e", ["A", "B"], ["code_a"], online=True,
                ),
                "bad pmcid": lambda: build_validation_pack(
                    write_benchmark(root / "pmcid.json", papers=[
                        {"pmcid": "", "status": "PROCESSED",
                         "response_sha256": "a" * 64, "writing_finding_codes": []},
                    ]),
                    root / "f", ["A", "B"], ["code_a"], online=True,
                ),
                "bad hash": lambda: build_validation_pack(
                    write_benchmark(root / "hash.json", papers=[
                        {"pmcid": "PMC1234567", "status": "PROCESSED",
                         "response_sha256": "z" * 64, "writing_finding_codes": []},
                    ]),
                    root / "g", ["A", "B"], ["code_a"], online=True,
                ),
                "missing findings": lambda: build_validation_pack(
                    write_benchmark(root / "findings.json", papers=[
                        {"pmcid": "PMC1234567", "status": "PROCESSED",
                         "response_sha256": "a" * 64},
                    ]),
                    root / "h", ["A", "B"], ["code_a"], online=True,
                ),
                "no codes": lambda: build_validation_pack(
                    valid, root / "i", ["A", "B"], [], online=True,
                ),
                "duplicate code": lambda: build_validation_pack(
                    valid, root / "j", ["A", "B"], ["code_a", "code_a"], online=True,
                ),
                "empty code": lambda: build_validation_pack(
                    valid, root / "k", ["A", "B"], [""], online=True,
                ),
                "one reviewer": lambda: build_validation_pack(
                    valid, root / "l", ["A"], ["code_a"], online=True,
                ),
                "same reviewer": lambda: build_validation_pack(
                    valid, root / "m", ["A", "A"], ["code_a"], online=True,
                ),
                "empty reviewer": lambda: build_validation_pack(
                    valid, root / "n", ["A", ""], ["code_a"], online=True,
                ),
            }
            messages = {
                "offline": "requires explicit --online",
                "wrong kind": "smoke-test",
                "bad paper list": "paper_results",
                "no processed": "No processed papers",
                "duplicate paper": "duplicate",
                "bad pmcid": "needs a PMCID",
                "bad hash": "valid response_sha256",
                "missing findings": "writing_finding_codes",
                "no codes": "finding code",
                "duplicate code": "unique",
                "empty code": "finding code",
                "one reviewer": "Exactly two",
                "same reviewer": "distinct",
                "empty reviewer": "distinct",
            }
            for name, call in cases.items():
                with self.subTest(name=name):
                    with self.assertRaisesRegex(ValueError, messages[name]):
                        call()

    def test_pack_rejects_bad_output_paths_manual_and_changed_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark = write_benchmark(root / "benchmark.json")
            not_dir = root / "file.txt"
            not_dir.write_text("x", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not a directory"):
                build_validation_pack(
                    benchmark, not_dir, ["A", "B"], ["code_a"], online=True,
                )
            nonempty = root / "nonempty"
            nonempty.mkdir()
            (nonempty / "x").write_text("x", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "new or empty"):
                build_validation_pack(
                    benchmark, nonempty, ["A", "B"], ["code_a"], online=True,
                )
            empty_manual = root / "empty.md"
            empty_manual.write_text("  \n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "manual is empty"):
                build_validation_pack(
                    benchmark, root / "manual-out", ["A", "B"], ["code_a"],
                    online=True, manual_path=empty_manual,
                )
            with patch("sra.labeling._get_article",
                       return_value=("# Results\nText.\n", {"response_sha256": "c" * 64})):
                with self.assertRaisesRegex(ValueError, "source hash changed"):
                    build_validation_pack(
                        benchmark, root / "changed", ["A", "B"], ["code_a"],
                        online=True,
                    )


class MergeLabelTests(unittest.TestCase):
    def _prepare(self, tmp):
        benchmark, out, pack, _ = build_pack(tmp)
        return benchmark, out / "reviewer_1.json", out / "reviewer_2.json", pack

    def test_merge_agreements_disagreements_and_evaluation_compatibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            benchmark, reviewer_a, reviewer_b, pack = self._prepare(tmp)
            set_verdicts(reviewer_a, [True, False, True, False])
            set_verdicts(reviewer_b, [True, False, False, False])
            adjudications = Path(tmp) / "adjudications.json"
            save_json(adjudications, {
                "adjudicator_id": "adjudicator_X",
                "decisions": [{
                    "pmcid": "PMC7654321", "code": "code_a",
                    "expert_label": True,
                    "rationale": "The supplied results support the disputed finding.",
                }],
            })
            merged = merge_adjudicated_labels(
                benchmark, reviewer_a, reviewer_b, adjudications
            )
            merged_path = Path(tmp) / "labels.json"
            save_json(merged_path, merged)
            comparison = evaluate_blinded_labels(benchmark, merged_path)
            self.assertEqual(merged["adjudicator_id"], "adjudicator_X")
            self.assertEqual(merged["benchmark_sha256"], pack["benchmark_sha256"])
            self.assertEqual(len(merged["cases"]), 4)
            self.assertEqual(
                [case["expert_label"] for case in merged["cases"]],
                [True, False, True, False],
            )
            self.assertEqual(
                [case["reviewer_labels"] for case in merged["cases"]],
                [[True, True], [False, False], [True, False], [False, False]],
            )
            self.assertTrue(all(case["adjudicated"] is True for case in merged["cases"]))
            self.assertEqual(merged["inter_reviewer_agreement"]["agreements"], 3)
            self.assertEqual(merged["inter_reviewer_agreement"]["disagreements"], 1)
            self.assertAlmostEqual(merged["inter_reviewer_agreement"]["raw_exact_agreement"], 0.75)
            self.assertAlmostEqual(merged["inter_reviewer_agreement"]["cohen_kappa"], 0.5)
            self.assertEqual(comparison["labelled_units"], 4)
            self.assertEqual(comparison["micro_average"]["tp"], 1)
            self.assertEqual(comparison["micro_average"]["fn"], 1)
            self.assertEqual(comparison["micro_average"]["tn"], 2)

    def test_merge_all_agree_gives_null_kappa(self):
        with tempfile.TemporaryDirectory() as tmp:
            benchmark, reviewer_a, reviewer_b, _ = self._prepare(tmp)
            set_verdicts(reviewer_a, [True, True, True, True])
            set_verdicts(reviewer_b, [True, True, True, True])
            adjudications = Path(tmp) / "adjudications.json"
            save_json(adjudications, {"adjudicator_id": "adjudicator_X", "decisions": []})
            merged = merge_adjudicated_labels(
                benchmark, reviewer_a, reviewer_b, adjudications
            )
            self.assertIsNone(merged["inter_reviewer_agreement"]["cohen_kappa"])
            self.assertEqual(merged["inter_reviewer_agreement"]["disagreements"], 0)

    def test_merge_rejects_malformed_worksheets_and_adjudications(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def fresh():
                sub = Path(tempfile.mkdtemp(dir=root))
                benchmark, out, _, _ = build_pack(sub)
                return benchmark, out / "reviewer_1.json", out / "reviewer_2.json"

            def expect(message, mutate_a=None, mutate_b=None, adjudications=None,
                       valid_verdicts=False):
                benchmark, reviewer_a, reviewer_b = fresh()
                if valid_verdicts:
                    set_verdicts(reviewer_a, [True, False, True, False])
                    set_verdicts(reviewer_b, [True, False, False, False])
                if mutate_a:
                    sheet = load_json(reviewer_a)
                    mutate_a(sheet)
                    save_json(reviewer_a, sheet)
                if mutate_b:
                    sheet = load_json(reviewer_b)
                    mutate_b(sheet)
                    save_json(reviewer_b, sheet)
                if adjudications is None:
                    adjudications = {"adjudicator_id": "adj", "decisions": []}
                adjudication_path = Path(tempfile.mkdtemp(dir=root)) / "adj.json"
                save_json(adjudication_path, adjudications)
                with self.assertRaisesRegex(ValueError, message):
                    merge_adjudicated_labels(
                        benchmark, reviewer_a, reviewer_b, adjudication_path
                    )

            expect("different finding codes",
                   mutate_b=lambda s: s.__setitem__("finding_codes", ["code_a"]))
            expect("Expected a blinded", mutate_b=lambda s: s.__setitem__("kind", "other"))
            expect("does not match",
                   mutate_b=lambda s: s.__setitem__("benchmark_sha256", "c" * 64))
            expect("reviewer ID", mutate_b=lambda s: s.__setitem__("reviewer_id", ""))
            expect("finding code", mutate_b=lambda s: s.__setitem__("finding_codes", []))
            expect("list of objects", mutate_b=lambda s: s.__setitem__("cases", {}))
            expect("must be distinct",
                   mutate_b=lambda s: s.__setitem__("reviewer_id", "reviewer_A"))
            expect("Unknown or repeated",
                   mutate_b=lambda s: s["cases"].append(dict(s["cases"][0])),
                   valid_verdicts=True)
            expect("source hash",
                   mutate_b=lambda s: s["cases"][0].__setitem__("source_sha256", "c" * 64),
                   valid_verdicts=True)
            expect("boolean verdict",
                   mutate_b=lambda s: s["cases"][0].__setitem__("verdict", "true"),
                   valid_verdicts=True)
            expect("coverage incomplete", mutate_b=lambda s: s["cases"].pop(),
                   valid_verdicts=True)
            expect("JSON object", adjudications=[], valid_verdicts=True)
            expect("adjudicator_id", adjudications={"decisions": []}, valid_verdicts=True)
            expect("distinct from both", adjudications={
                "adjudicator_id": "reviewer_A", "decisions": [],
            }, valid_verdicts=True)
            expect("decisions must be a list", adjudications={
                "adjudicator_id": "adj", "decisions": {},
            }, valid_verdicts=True)
            expect("decision must be an object", adjudications={
                "adjudicator_id": "adj", "decisions": [1],
            }, valid_verdicts=True)
            expect("Unknown or repeated adjudication", adjudications={
                "adjudicator_id": "adj",
                "decisions": [{"pmcid": "PMC0000000", "code": "code_a",
                               "expert_label": True,
                               "rationale": "A sufficiently long rationale."}],
            }, valid_verdicts=True)
            expect("boolean expert_label", adjudications={
                "adjudicator_id": "adj",
                "decisions": [{"pmcid": "PMC7654321", "code": "code_a",
                               "expert_label": "true",
                               "rationale": "A sufficiently long rationale."}],
            }, valid_verdicts=True)
            expect("20\\+ character", adjudications={
                "adjudicator_id": "adj",
                "decisions": [{"pmcid": "PMC7654321", "code": "code_a",
                               "expert_label": True, "rationale": "short"}],
            }, valid_verdicts=True)
            expect("only allowed for reviewer disagreements", adjudications={
                "adjudicator_id": "adj",
                "decisions": [{"pmcid": "PMC1234567", "code": "code_a",
                               "expert_label": True,
                               "rationale": "A sufficiently long rationale."}],
            }, valid_verdicts=True)
            expect("requires an adjudication decision", adjudications={
                "adjudicator_id": "adj", "decisions": [],
            }, valid_verdicts=True)


class LabelingCliTests(unittest.TestCase):
    def call(self, *arguments):
        with patch.object(sys, "argv", ["sra", *arguments]):
            return main()

    def call_error(self, arguments, message):
        errors = io.StringIO()
        with patch.object(sys, "argv", ["sra", *arguments]):
            with contextlib.redirect_stderr(errors):
                with self.assertRaises(SystemExit) as caught:
                    main()
        self.assertEqual(caught.exception.code, 2)
        self.assertIn(message, errors.getvalue())

    def test_validation_pack_cli_success_and_failure(self):
        manifest = {"paper_count": 2, "unit_count": 4}
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            with patch("sra.cli.build_validation_pack", return_value=manifest) as build:
                with patch.object(sys, "argv", [
                    "sra", "validation-pack", "benchmark.json",
                    "--reviewer", "A", "--reviewer", "B", "--code", "code_a",
                    "--online", "--out-dir", str(Path(tmp) / "pack"),
                ]):
                    with contextlib.redirect_stdout(stdout):
                        self.assertEqual(main(), 0)
            self.assertEqual(build.call_args.args[2], ["A", "B"])
            self.assertEqual(build.call_args.args[3], ["code_a"])
        self.assertIn("2 papers, 4 units", stdout.getvalue())
        self.assertIn("NOT INCLUDED", stdout.getvalue())
        with patch("sra.cli.build_validation_pack", side_effect=ValueError("synthetic failure")):
            self.call_error(
                ["validation-pack", "benchmark.json", "--reviewer", "A",
                 "--reviewer", "B", "--code", "code_a", "--online",
                 "--out-dir", "pack"],
                "synthetic failure",
            )

    def test_adjudicate_labels_cli_success_error_and_overwrite_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            benchmark, out, _, _ = build_pack(tmp)
            reviewer_a = out / "reviewer_1.json"
            reviewer_b = out / "reviewer_2.json"
            set_verdicts(reviewer_a, [True, False, True, False])
            set_verdicts(reviewer_b, [True, False, False, False])
            adjudications = Path(tmp) / "adjudications.json"
            save_json(adjudications, {
                "adjudicator_id": "adj",
                "decisions": [{
                    "pmcid": "PMC7654321", "code": "code_a",
                    "expert_label": True,
                    "rationale": "A sufficiently long adjudication rationale.",
                }],
            })
            target = Path(tmp) / "final" / "labels.json"
            output = self.call(
                "adjudicate-labels", str(benchmark), str(reviewer_a),
                str(reviewer_b), str(adjudications), "--out", str(target),
            )
            self.assertEqual(output, 0)
            self.assertEqual(load_json(target)["cases"][2]["expert_label"], True)
            self.call_error(
                ["adjudicate-labels", str(benchmark), str(reviewer_a),
                 str(reviewer_b), str(adjudications), "--out", str(reviewer_a)],
                "must not overwrite",
            )
        with patch("sra.cli.merge_adjudicated_labels", side_effect=ValueError("synthetic failure")):
            self.call_error(
                ["adjudicate-labels", "b.json", "a.json", "b2.json", "adj.json"],
                "synthetic failure",
            )


if __name__ == "__main__":
    unittest.main()
