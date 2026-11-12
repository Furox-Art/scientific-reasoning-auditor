"""Exact, numerical and candidate-only toolkit contracts."""
import copy
import hashlib
import json
import unittest
import warnings
from threading import Event
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from sra.toolkit import verify_toolkit_spec
from sra.toolkit_spec import prepare_toolkit_spec


def problem(*checks):
    return {"schema_version":"1.0", "checks":list(checks)}


def polynomial(kind="polynomial_identity", left="(x+1)**2", right="x**2+2*x+1"):
    result = {"id":"math", "kind":kind, "variables":["x"], "left":left, "right":right}
    if kind != "polynomial_identity":
        result["variable"]="x"
    return result


def passage(text):
    return {"id":"source", "text":text, "sha256":hashlib.sha256(text.encode()).hexdigest()}


class ToolkitTests(unittest.TestCase):
    def check(self, item):
        return verify_toolkit_spec(problem(item))["checks"][0]

    def test_exact_polynomial_calculus_and_counterexamples(self):
        for item in (polynomial(), polynomial("derivative", "x**3/3", "x**2"),
                     polynomial("antiderivative", "2*x", "x**2+7")):
            self.assertEqual(self.check(item)["status"], "VERIFIED")
        self.assertEqual(self.check(polynomial(right="x**2+1"))["status"], "REFUTED")
        result = self.check(polynomial(left="0.1*x+0.2*x", right="0.3*x"))
        self.assertEqual(result["status"],"VERIFIED")

    def test_units_convert_prefixes_temperature_and_incompatible_dimensions(self):
        item={"id":"units", "kind":"unit_conversion", "value":"100", "from_unit":"cm", "to_unit":"m", "reported":"1"}
        self.assertEqual(self.check(item)["status"], "VERIFIED")
        self.assertEqual(self.check({**item,"reported":"2"})["status"], "REFUTED")
        self.assertEqual(self.check({**item,"value":"0","from_unit":"degC","to_unit":"kelvin","reported":"273.15"})["status"],"VERIFIED")
        self.assertEqual(self.check({**item,"to_unit":"second"})["status"], "REFUTED")
        self.assertEqual(self.check({**item,"from_unit":"kg*m/s**2","to_unit":"newton","reported":"100"})["status"],"VERIFIED")

    def test_ambiguous_offset_and_unsupported_logarithmic_calculation_are_failures(self):
        base={'id':'u','kind':'unit_conversion','value':'1','reported':'274.15'}
        for source,target in (('degC/m','kelvin/m'),('dBm','watt')):
            with self.subTest(source=source):
                report=self.check({**base,'from_unit':source,'to_unit':target})
                self.assertEqual(report['status'],'FAILED')

    def test_raw_data_replay_and_degenerate_data(self):
        for test, groups in (("welch_t",[[1,2,3],[4,5,6]]), ("paired_t",[[1,3,6],[2,5,7]]),
                             ("pearson",[[1,2,3],[2,4,6]]), ("one_way_anova",[[1,2,3],[4,5,6],[7,8,9]])):
            item={"id":"data", "kind":"statistical_replay","test":test,"groups":groups}
            result=self.check(item)
            self.assertEqual(result["status"], "CALCULATED")
            values=result["details"]["computed"]
            self.assertEqual(self.check({**item,"reported":values})["status"], "VERIFIED")
            self.assertEqual(self.check({**item,"reported":{"statistic":-999}})["status"], "REFUTED")
        item={"id":"data","kind":"statistical_replay","test":"pearson","groups":[[1,1,1],[2,2,2]]}
        self.assertEqual(self.check(item)["status"], "UNDETERMINED")

    def test_numerical_overflow_cannot_verify_a_finite_but_incorrect_p_value(self):
        groups=[[str(n)+'0'*36+'e64' for n in group] for group in ((1,2,3),(4,5,6))]
        item={'id':'large','kind':'statistical_replay','test':'welch_t','groups':groups,
              'reported':{'p_value':'0.16916841122975357'}}
        result=self.check(item)
        self.assertEqual(result['status'],'UNDETERMINED')
        self.assertNotIn('computed',result['details'])

    def test_concurrent_replays_do_not_lose_each_others_numerical_warnings(self):
        started,other_entered,emitted=Event(),Event(),Event()
        class Backend:
            def ttest_ind(self,*groups,**options):
                if groups[0][0] == 10:
                    started.set()
                    other_entered.wait(0.2)
                    warnings.warn('simulated numerical overflow',RuntimeWarning)
                    emitted.set()
                else:
                    other_entered.set()
                    emitted.wait(1)
                return SimpleNamespace(statistic=1,pvalue=0.1)
        first={'id':'a','kind':'statistical_replay','test':'welch_t','groups':[[10,11],[12,13]],'reported':{'p_value':'0.1'}}
        second={**first,'id':'b','groups':[[1,2],[3,4]]}
        with patch('sra.toolkit._backend',return_value=Backend()),ThreadPoolExecutor(2) as pool:
            a=pool.submit(self.check,first)
            self.assertTrue(started.wait(2))
            b=pool.submit(self.check,second)
            self.assertEqual(a.result(timeout=5)['status'],'UNDETERMINED')
            b.result(timeout=5)

    def test_candidate_offsets_and_passage_similarity_never_imply_truth(self):
        text="Results increased.\nThis is a second sentence."
        result=self.check({"id":"sentences","kind":"claim_candidates","text":text,"language":"xx"})
        self.assertEqual(result["status"], "CANDIDATES")
        self.assertGreaterEqual(len(result["details"]["candidates"]),2)
        for row in result["details"]["candidates"]:
            self.assertEqual(text[row["start"]:row["end"]],row["text"])
            self.assertTrue(row["requires_review"])
        result=self.check({"id":"citations","kind":"citation_match","claim":"Results increased.","passages":[passage(text)]})
        self.assertEqual(result["status"], "CANDIDATES")
        self.assertEqual(result["details"]["support_status"], "NOT_ASSESSED")
        self.assertTrue(result["details"]["matches"][0]["exact_match"])

    def test_strict_preflight_and_hostile_expressions(self):
        for expr in ("__import__('os')", "x.__class__", "x/x", "x**10000000", "x**-1", "[x]", "True", "1e999999", "x**2**3", "y"):
            with self.subTest(expr=expr), self.assertRaises(ValueError):
                prepare_toolkit_spec(problem(polynomial(left=expr)))
        for value in ('{"schema_version":"1.0","schema_version":"1.0","checks":[]}', 'NaN', '[]', problem(),
                      {**problem(polynomial()),"unknown":1}, problem({**polynomial(),"extra":1})):
            with self.subTest(value=str(value)[:60]), self.assertRaises(ValueError):
                prepare_toolkit_spec(value)
        item={"id":"citation","kind":"citation_match","claim":"Text", "passages":[{**passage("Text"),"sha256":"0"*64}]}
        with self.assertRaises(ValueError):
            prepare_toolkit_spec(problem(item))

    def test_repeatability_and_missing_dependency_preserve_other_checks(self):
        spec=problem(polynomial(),{"id":"citation","kind":"citation_match","claim":"Text","passages":[passage("Text")]})
        original=copy.deepcopy(spec)
        self.assertEqual(verify_toolkit_spec(spec),verify_toolkit_spec(json.dumps(spec)))
        from sra.toolkit import _backend
        def partial(name):
            if name == 'sympy':
                raise ImportError('private path')
            return _backend(name)
        with patch("sra.toolkit._backend", side_effect=partial):
            result=verify_toolkit_spec(spec)
        self.assertEqual(result["execution_status"],"partial")
        self.assertEqual(result["checks"][0]["status"],"UNAVAILABLE")
        self.assertEqual(result["checks"][1]["status"],"CANDIDATES")
        self.assertNotIn("private path",json.dumps(result))
        self.assertEqual(spec,original)

    def test_numeric_polynomial_and_unit_resource_limits(self):
        for expr in ('', 'x+', 'x+'*45+'x', '-'*25+'x', 'x**8*x**8', '1e64*1e64*1e64',
                     '(x+y+z+w)**6*(x+y+z+w)**6'):
            item={**polynomial(left=expr),'variables':['x','y','z','w']}
            with self.subTest(expr=expr),self.assertRaises(ValueError):
                prepare_toolkit_spec(problem(item))
        self.assertEqual(self.check(polynomial(left='-x + +x',right='0'))['status'],'VERIFIED')
        base={'id':'units','kind':'unit_conversion','value':'1','from_unit':'m','to_unit':'cm','reported':'100'}
        for expr in ('m+', '*'.join(['m']*16), 'm.__class__','m**9','m**True','__import__(m)'):
            with self.subTest(expr=expr),self.assertRaises(ValueError):
                prepare_toolkit_spec(problem({**base,'from_unit':expr}))
        self.assertEqual(self.check({**base,'from_unit':'1/s','to_unit':'s**-1','reported':'1'})['status'],'VERIFIED')
        self.assertEqual(self.check({**base,'from_unit':'nonexistentunit'})['status'],'FAILED')
        with self.assertRaises(ValueError):
            prepare_toolkit_spec(problem({**base,'atol':'-1'}))

    def test_strict_structured_fields_and_finite_data(self):
        replay={'id':'data','kind':'statistical_replay','test':'paired_t','groups':[[1,2],[2,4]]}
        sentence={'id':'sentences','kind':'claim_candidates','text':'Text.'}
        citation={'id':'citation','kind':'citation_match','claim':'Text','passages':[passage('Text')]}
        invalid=[{**polynomial(),'id':'../x'}, {**polynomial(),'kind':'unknown'},
                 {**polynomial(),'variables':[]},{**polynomial('derivative'),'variable':'y'},
                 {**replay,'test':'bootstrap'}, {**replay,'groups':[[1],[2,3]]},
                 {**replay,'groups':[[1,2,3],[2,3]]}, {**replay,'reported':{}},
                 {**replay,'reported':{'p_value':2}},{**replay,'rtol':-1},
                 {**replay,'groups':[[True,2],[2,3]]}, {**sentence,'language':'auto'},
                 {**citation,'passages':[]}, {**citation,'passages':[passage('Text'),passage('Text')]}]
        for item in invalid:
            with self.subTest(item=item),self.assertRaises(ValueError):
                prepare_toolkit_spec(problem(item))
        for spec in (' '*1048577, {'not_json':set()}, {**problem(polynomial()),'source_sha256':'bad'},
                     problem(polynomial(),polynomial())):
            with self.subTest(spec=str(spec)[:60]),self.assertRaises(ValueError):
                prepare_toolkit_spec(spec)

    def test_candidate_cap_and_literal_tie_order_and_inert_markup(self):
        self.assertEqual(self.check({'id':'s','kind':'claim_candidates','text':'A sentence. \n\n'})['status'],'CANDIDATES')
        self.assertEqual(self.check({'id':'s','kind':'claim_candidates','text':'This is a sentence. '*1002})['status'],'FAILED')
        rows=[{**passage('A passage.'),'id':name} for name in ('z','a')]
        result=self.check({'id':'c','kind':'citation_match','claim':'unrelated','passages':rows})
        self.assertEqual([r['passage_id'] for r in result['details']['matches']],['a','z'])
        self.assertFalse(result['details']['matches'][0]['exact_match'])
        from sra.toolkit_report import toolkit_markdown
        spec=problem({'id':'c','kind':'citation_match','claim':'<script>','passages':[passage('<script>')]})
        self.assertNotIn('<script>',toolkit_markdown(verify_toolkit_spec(spec)))

    def test_example_offline_and_concurrent_repeatability(self):
        spec=json.loads((Path(__file__).parents[1]/'examples/toolkit.json').read_text())
        with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('network')):
            result=verify_toolkit_spec(spec)
        self.assertEqual(result['execution_status'],'complete')
        with ThreadPoolExecutor(2) as pool:
            reports=list(pool.map(verify_toolkit_spec,[problem(polynomial())]*4))
        self.assertTrue(all(r==reports[0] for r in reports))
