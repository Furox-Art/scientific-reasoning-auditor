"""Real-solver controls for conditional, deterministic formal verification."""
import copy
import hashlib
import importlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def boolean_problem():
    return {"schema_version":"1.0", "variables":{"p":"Bool","q":"Bool","r":"Bool"},
            "assumptions":[{"id":"A1","expression":"p"}, {"id":"A2","expression":"implies(p, q)"}],
            "claims":[{"id":"C1","expression":"q"}, {"id":"C2","expression":"not q"},
                      {"id":"C3","expression":"r"}]}


class LogicTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("sra.logic"), "Z3 integration is missing")
        return importlib.import_module("sra.logic")

    def test_entailment_refutation_and_independence_are_distinct(self):
        report = self.api().verify_logic_spec(boolean_problem())
        self.assertEqual(report["premises"]["status"], "CONSISTENT")
        self.assertEqual([x["status"] for x in report["claims"]], ["VERIFIED","REFUTED","UNDETERMINED"])
        self.assertEqual(report["engine"]["name"], "Z3")
        self.assertEqual(report["source_binding"]["status"], "unbound")

    def test_inconsistent_premises_never_verify_every_conclusion(self):
        problem = boolean_problem()
        problem["assumptions"].append({"id":"A3","expression":"not p"})
        report = self.api().verify_logic_spec(problem)
        self.assertEqual(report["premises"]["status"], "INCONSISTENT")
        self.assertTrue(all(x["status"] == "UNDETERMINED" for x in report["claims"]))

    def test_exact_linear_arithmetic_and_integer_real_semantics(self):
        problem = {"schema_version":"1.0","variables":{"x":"Real","n":"Int"},
                   "assumptions":[{"id":"A1","expression":"x == 0.1 + 0.2"},
                                  {"id":"A2","expression":"n == 3"}],
                   "claims":[{"id":"C1","expression":"x == 0.3"},
                             {"id":"C2","expression":"n / 2 == 1.5"},
                             {"id":"C3","expression":"0 < n < 4"},
                             {"id":"C4","expression":"2 * x < 0"}]}
        report = self.api().verify_logic_spec(problem)
        self.assertEqual([x["status"] for x in report["claims"]], ["VERIFIED"]*3 + ["REFUTED"])

    def test_repeatability_includes_stable_fingerprint_and_no_timestamps_or_witnesses(self):
        api = self.api()
        problem = boolean_problem()
        first = api.verify_logic_spec(problem)
        self.assertEqual(first, api.verify_logic_spec(copy.deepcopy(problem)))
        self.assertEqual(first["report_sha256"], api.verify_logic_spec(json.dumps(problem))["report_sha256"])
        self.assertNotIn("elapsed", json.dumps(first))
        self.assertNotIn("counterexample", first)

    def test_manuscript_binding_verifies_hashes_quotes_and_leaves_input_unchanged(self):
        api = self.api()
        from sra.document import load_document
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "paper.md"
            raw = b"# Assumptions\nThe hypothesis p is assumed to hold.\n"
            path.write_bytes(raw)
            doc = load_document(path)
            problem = boolean_problem()
            problem.update(source_sha256=doc.sha256,
                           extracted_text_sha256=hashlib.sha256(doc.text.encode()).hexdigest())
            problem["assumptions"][0].update(source_quote="The hypothesis p is assumed to hold.", line=2)
            report = api.verify_logic_spec(problem, document=doc)
            self.assertEqual(report["source_binding"]["status"], "source_matched")
            self.assertFalse(report["source_binding"]["formalization_semantics_verified"])
            self.assertEqual(report["assumptions"][0]["source"]["line"], 2)
            self.assertEqual(path.read_bytes(), raw)
            for change in ({"source_sha256":"a"*64}, {"extracted_text_sha256":"b"*64}):
                bad = {**problem, **change}
                with self.assertRaises(ValueError):
                    api.verify_logic_spec(bad, document=doc)
            problem["assumptions"][0]["line"] = 10000
            with self.assertRaises(ValueError):
                api.verify_logic_spec(problem, document=doc)
            problem["assumptions"][0]["line"] = 2
            problem["assumptions"][0]["source_quote"] = "fabricated quotation that does not appear"
            with self.assertRaises(ValueError):
                api.verify_logic_spec(problem, document=doc)

    def test_hostile_or_unsupported_expressions_are_rejected_before_solver_import(self):
        api = self.api()
        bad = ["p +", "__import__('os').system('echo bad')", "p.__class__", "[p][0]", "lambda: p",
               "x ** 999", "x * x == 2", "x / x == 1", "x / 0 == 1", "exists(p)",
               "p + 1", "implies(x, p)", "iff(p)", "1", "unknown", "x < p", "[True]",
               "implies(p, q=True)", "1e999 == x", "not "*40+"p"]
        for expression in bad:
            problem = boolean_problem()
            problem["variables"]["x"] = "Real"
            problem["claims"][0]["expression"] = expression
            with self.subTest(expression=expression[:45]), self.assertRaises(ValueError):
                api.verify_logic_spec(problem)

    def test_duplicate_keys_ids_and_unknown_fields_do_not_silently_change_the_problem(self):
        api = self.api()
        for raw in ('{"schema_version":"1.0","schema_version":"other"}', '{"x":NaN}', '[]'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                api.verify_logic_spec(raw)
        for change in ({"claims":[]}, {"variables":{"p":"String"}}, {"timeout":5},
                       {"claims":[{"id":"A1","expression":"p"}]},
                       {"variables":{"implies":"Bool"}}, {"variables":{"x.y":"Real"}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                api.verify_logic_spec({**boolean_problem(), **change})

    def test_budget_unknown_is_never_a_proof(self):
        api = self.api()
        with patch("sra.logic._check", return_value="unknown"):
            report = api.verify_logic_spec(boolean_problem())
        self.assertEqual(report["premises"]["status"], "UNDETERMINED")
        self.assertEqual(report["execution_status"], "partial")
        self.assertTrue(all(x["status"] == "UNDETERMINED" for x in report["claims"]))

    def test_independent_concurrent_contexts_produce_same_report(self):
        api = self.api()
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as pool:
            reports = list(pool.map(lambda _: api.verify_logic_spec(boolean_problem()), range(4)))
        self.assertTrue(all(report == reports[0] for report in reports))

    def test_boolean_and_linear_operator_language(self):
        api = self.api()
        expressions = ["iff(p, True)", "p == True", "p != False", "p or q", "p and q",
                       "+x == 3", "-x == -3", "x - 2 == 1", "x + 2 >= 5", "2*x > 5",
                       "x != 4", "x <= 3", "(2 + 3) * x == 15", "(6 - 2)/2 == 2"]
        problem = {"schema_version":"1.0", "variables":{"p":"Bool","q":"Bool","x":"Int"},
                   "assumptions":[{"id":"A1","expression":"p and q"},{"id":"A2","expression":"x == 3"}],
                   "claims":[{"id":f"C{i}","expression":expr} for i,expr in enumerate(expressions)]}
        self.assertTrue(all(item["status"] == "VERIFIED" for item in api.verify_logic_spec(problem)["claims"]))

    def test_resource_unknown_during_claims_is_preserved(self):
        api = self.api()
        problem = boolean_problem()
        problem["claims"] = problem["claims"][:1]
        for answers in (["sat","unknown","sat"], ["sat","sat","unknown"], ["sat","unknown","unsat"]):
            with self.subTest(answers=answers), patch("sra.logic._check", side_effect=answers):
                report = api.verify_logic_spec(problem)
            self.assertEqual(report["execution_status"], "partial")
            self.assertEqual(report["claims"][0]["status"], "REFUTED" if answers[-1] == "unsat" else "UNDETERMINED")

    def test_input_size_complexity_types_and_quote_boundaries(self):
        api = self.api()
        from sra.logic_spec import prepare_logic_spec
        invalid = ["x"*(1024*1024+1), {"bad":{1,2}},
                   {**boolean_problem(),"source_sha256":"bad"},
                   {**boolean_problem(),"variables":{f"x{i}":"Bool" for i in range(65)}}]
        bad_expressions = ["", "p "*300, " and ".join(["p"]*70), "0x10 == 16",
                           "1"*65+" == 0", "1e64 * 1e64 > 0", "None == p", "~p", "x and p", "x % 2 == 0"]
        for expr in bad_expressions:
            problem = boolean_problem()
            problem["variables"]["x"]="Int"
            problem["claims"][0]["expression"]=expr
            invalid.append(problem)
        for change in ({"line":0}, {"line":True}, {"line":2}, {"source_quote":"short"}, {"extra":1}):
            problem=boolean_problem()
            problem["claims"][0].update(change)
            invalid.append(problem)
        problem=boolean_problem()
        problem["assumptions"]=[{"id":f"A{i}","expression":" and ".join(["p"]*30)} for i in range(64)]
        problem["claims"]=[{"id":f"C{i}","expression":" and ".join(["p"]*30)} for i in range(32)]
        invalid.append(problem)
        problem=boolean_problem()
        problem["claims"][0]="not an object"
        invalid.append(problem)
        for problem in invalid:
            with self.subTest(case=str(problem)[:90]), self.assertRaises(ValueError):
                prepare_logic_spec(problem)
        quoted=boolean_problem()
        quoted["claims"][0].update(source_quote="An unbound formalization.", line=1)
        self.assertEqual(api.verify_logic_spec(quoted)["claims"][0]["source"]["status"], "unbound")

    def test_missing_optional_solver_has_an_actionable_error(self):
        self.api()
        import builtins
        original=builtins.__import__
        def missing(name,*args,**kwargs):
            if name == "z3":
                raise ImportError("missing")
            return original(name,*args,**kwargs)
        with patch("builtins.__import__",side_effect=missing), self.assertRaisesRegex(RuntimeError,"logic"):
            self.api().verify_logic_spec(boolean_problem())

    def test_fingerprint_repeats_in_separate_python_processes(self):
        self.api()
        import subprocess
        import sys
        root=Path(__file__).parents[1]
        command=[sys.executable,"-c", "from sra.logic import verify_logic_spec; from pathlib import Path; print(verify_logic_spec(Path('examples/logic_boolean.json').read_text())['report_sha256'])"]
        values=[subprocess.check_output(command,cwd=root,text=True,timeout=20).strip() for _ in range(2)]
        self.assertEqual(values[0],values[1])

    def test_extreme_decimal_exponent_is_rejected_before_exact_number_allocation(self):
        self.api()
        from sra.logic_spec import parse_expression
        with patch("sra.logic_spec.Fraction", side_effect=AssertionError("unsafe allocation")) as fraction:
            with self.assertRaises(ValueError):
                parse_expression("1e1000000000 > 0", {})
            fraction.assert_not_called()

    def test_repeated_quotes_do_not_recount_every_document_prefix(self):
        api=self.api()
        from sra.document import parse_document_text
        class TrackedText(str):
            prefix_scans=0
            def count(self, sub, *args):
                if sub == "\n" and args:
                    self.prefix_scans += 1
                return super().count(sub,*args)
        text=TrackedText("A repeated quoted premise.\n"*1000)
        doc=parse_document_text(text,sha256=hashlib.sha256(text.encode()).hexdigest())
        problem=boolean_problem()
        problem.update(source_sha256=doc.sha256,extracted_text_sha256=hashlib.sha256(text.encode()).hexdigest())
        problem["assumptions"][0].update(source_quote="A repeated quoted premise.",line=999)
        report=api.verify_logic_spec(problem,document=doc)
        self.assertEqual(report["assumptions"][0]["source"]["line"],999)
        self.assertLessEqual(text.prefix_scans,1)

    def test_overlapping_source_quote_can_start_on_a_later_line(self):
        api=self.api()
        from sra.document import parse_document_text
        text="abcdef\n"*3
        doc=parse_document_text(text,sha256=hashlib.sha256(text.encode()).hexdigest())
        problem=boolean_problem()
        problem.update(source_sha256=doc.sha256,extracted_text_sha256=hashlib.sha256(text.encode()).hexdigest())
        problem["assumptions"][0].update(source_quote="abcdef\nabcdef\n",line=2)
        self.assertEqual(api.verify_logic_spec(problem,document=doc)["assumptions"][0]["source"]["line"],2)

    def test_native_solver_exception_is_sanitized_and_chained(self):
        api=self.api()
        import z3
        with patch("sra.logic._check",side_effect=z3.Z3Exception("private backend data")):
            with self.assertRaises(RuntimeError) as caught:
                api.verify_logic_spec(boolean_problem())
        self.assertIsInstance(caught.exception.__cause__,z3.Z3Exception)
        self.assertNotIn("private backend data",str(caught.exception))


if __name__ == "__main__":
    unittest.main()
