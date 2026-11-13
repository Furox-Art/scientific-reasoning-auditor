"""Optional local verification backends; findings never modify a manuscript."""
import importlib
import importlib.metadata
import json
import math
import platform
import sys
import warnings
from bisect import bisect_right
from decimal import Context, Decimal, localcontext
from threading import Lock

from sra.toolkit_spec import KINDS, digest, prepare_toolkit_spec

BACKENDS = dict.fromkeys(KINDS[:3],"sympy") | {"unit_conversion":"pint", "statistical_replay":"scipy.stats",
            "claim_candidates":"spacy", "citation_match":"rapidfuzz.fuzz"}
_STATISTICS_LOCK = Lock()
BACKENDS.update(dict.fromkeys(('symbolic_identity','symbolic_derivative','symbolic_antiderivative'),'sympy'))
BACKENDS.update(statistical_analysis='scipy.stats',statistic_consistency='scipy.stats',citation_context='rapidfuzz.fuzz',table_compare='csv',figure_svg='xml.etree.ElementTree')
BACKENDS.update(causal_graph='networkx',bias_assessment='json',power_analysis='statsmodels.stats.power',
                meta_analysis='statsmodels.stats.meta_analysis',
                bayesian_diagnostics='arviz_stats' if sys.version_info>=(3,12) else 'arviz',
                ml_validation='json',publication_status='json')


def _backend(name):
    return importlib.import_module(name)


def _numerical_environment():
    versions={}
    for name in ('numpy','scipy','statsmodels','networkx','arviz-stats','arviz'):
        try:
            versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name]=None
    return {'python':platform.python_version(),'system':platform.system(),'machine':platform.machine(),'packages':versions}


def _mathematics(item, sympy):
    symbols = [sympy.Symbol(v,real=True) for v in item["variables"]]
    left,right = [sympy.Poly.from_dict({k:sympy.Rational(v.numerator,v.denominator) for k,v in poly.items()},symbols,domain=sympy.QQ)
                  for poly in item["polynomials"]]
    if item["kind"] == "derivative":
        left = left.diff(symbols[item["variables"].index(item["variable"])])
    if item["kind"] == "antiderivative":
        right = right.diff(symbols[item["variables"].index(item["variable"])])
    residual = left-right
    return ("VERIFIED" if residual.is_zero else "REFUTED", {"residual":str(residual.as_expr()),
            "meaning":"Exact polynomial identity over declared real variables; refuted means not an identity, not unequal at every point."})


def _units(item, pint):
    # A fresh registry and fixed decimal context isolate callers and threads.
    with localcontext(Context(prec=50)):
        registry = pint.UnitRegistry(non_int_type=Decimal,autoconvert_offset_to_baseunit=False)
        def build(term):
            op = term[0]
            if op == "unit":
                return registry.Unit(term[1])
            if op == "pow":
                return build(term[1]) ** term[2]
            left,right = build(term[1]),build(term[2])
            return left*right if op == "mul" else left/right
        try:
            source,target = [build(term) for term in item["units"]]
            if source.dimensionality != target.dimensionality:
                return "REFUTED", {"meaning":"Source and target dimensions are incompatible."}
            computed = registry.Quantity(Decimal(item["value"]),source).to(target).magnitude
        except (pint.errors.PintError,TypeError) as exc:
            raise ValueError("Unsupported or ambiguous unit conversion.") from exc
        agrees = abs(computed-Decimal(item["reported"])) <= Decimal(item["atol"])
        return ("VERIFIED" if agrees else "REFUTED", {"computed":str(computed),"target_unit":str(target),
                "atol":item["atol"],"meaning":"Numerical conversion of supplied quantities, not validation of measurement or physical law."})


def _statistics(item, stats):
    groups = [[float(v) for v in g] for g in item["groups"]]
    # Python 3.11/3.12 warning capture uses process-global state. Serialize our
    # replay calls so a concurrent check cannot capture and lose another's warning.
    with _STATISTICS_LOCK, warnings.catch_warnings(record=True) as numerical_warnings:
        warnings.simplefilter("always")
        test = item["test"]
        if test == "welch_t":
            result = stats.ttest_ind(*groups,equal_var=False,alternative="two-sided",nan_policy="raise")
        elif test == "paired_t":
            result = stats.ttest_rel(*groups,alternative="two-sided",nan_policy="raise")
        elif test == "pearson":
            result = stats.pearsonr(*groups,alternative="two-sided")
        else:
            result = stats.f_oneway(*groups)
    computed = {"statistic":float(result.statistic),"p_value":float(result.pvalue)}
    if numerical_warnings or not all(math.isfinite(v) for v in computed.values()) or computed["p_value"] == 0:
        return "UNDETERMINED", {"meaning":"Numerical warning, degenerate data, nonfinite result or p-value underflow; no agreement verdict is issued."}
    agrees = all(math.isclose(computed[k],float(v),rel_tol=float(item["rtol"]),abs_tol=float(item["atol"])) for k,v in item["reported"].items())
    return ("CALCULATED" if not item["reported"] else "VERIFIED" if agrees else "REFUTED", {
            "computed":computed,"atol":item["atol"],"rtol":item["rtol"],"test":test,
            "meaning":"Two-sided numerical replay on supplied arrays; sampling assumptions, data authenticity and test selection remain unverified."})


def _candidates(item, spacy):
    nlp = spacy.blank(item["language"])
    nlp.add_pipe("sentencizer")
    text = item["text"]
    starts = [0]+[i+1 for i,char in enumerate(text) if char == "\n"]
    candidates = []
    for sentence in nlp(text).sents:
        if not sentence.text.strip():
            continue
        if len(candidates) == 1000:
            raise ValueError("More than 1000 sentence candidates; split the source explicitly.")
        candidates.append({"id":f"sentence_{len(candidates)+1}","text":sentence.text,
                           "start":sentence.start_char,"end":sentence.end_char,
                           "line":bisect_right(starts,sentence.start_char),"requires_review":True,
                           "formal_expression":None})
    return "CANDIDATES", {"text_sha256":digest(text),"candidates":candidates,
            "meaning":"Untrained sentence segmentation only; each sentence is a review candidate, not an extracted formal claim or truth judgment."}


def _citations(item, fuzz):
    matches = []
    for passage in item["passages"]:
        offset = passage["text"].find(item["claim"])
        matches.append({"passage_id":passage["id"],"passage_sha256":passage["sha256"],"passage":passage["text"],
                        "similarity":float(fuzz.ratio(item["claim"],passage["text"],processor=None)),
                        "exact_match":offset >= 0,"exact_start":offset if offset >= 0 else None})
    matches.sort(key=lambda row:(not row["exact_match"],-row["similarity"],row["passage_id"]))
    return "CANDIDATES", {"support_status":"NOT_ASSESSED","matches":matches[:5],
            "meaning":"Case-sensitive literal/Indel string ranking of supplied passages; score is not probability, entailment or citation validity."}


def verify_prepared_toolkit(prepared):
    results = []
    for item in prepared["checks"]:
        name = BACKENDS[item["kind"]]
        row = {"id":item["id"],"kind":item["kind"],"backend":name,"backend_version":None}
        try:
            module = _backend(name)
            row["backend_version"] = platform.python_version() if name in ('csv','xml.etree.ElementTree','json') else importlib.metadata.version(name.split(".")[0])
            if item["kind"] in KINDS[:3]:
                status,details = _mathematics(item,module)
            elif item['kind'] in ('symbolic_identity','symbolic_derivative','symbolic_antiderivative'):
                from sra.symbolic import verify_symbolic
                status,details=verify_symbolic(item,module)
            elif item['kind'] in ('causal_graph','bias_assessment','power_analysis','meta_analysis','bayesian_diagnostics','ml_validation','publication_status'):
                from sra import research_checks
                from sra.publication import publication_status
                operation=publication_status if item['kind']=='publication_status' else getattr(research_checks,item['kind'])
                status,details=operation(item,module)
            else:
                from sra.inspection_calculations import statistical_analysis,statistic_consistency,citation_context,table_compare,figure_svg
                operation = {"unit_conversion":_units,"statistical_replay":_statistics,
                             "claim_candidates":_candidates,"citation_match":_citations,
                             'statistical_analysis':statistical_analysis,'citation_context':citation_context,
                             'statistic_consistency':statistic_consistency,
                             'table_compare':table_compare,'figure_svg':figure_svg}[item["kind"]]
                status,details = operation(item,module)
        except (ImportError,OSError,ValueError,RuntimeError,ArithmeticError,TypeError) as exc:
            status = "UNAVAILABLE" if isinstance(exc,ImportError) else "FAILED"
            details = {"meaning":"Local backend did not complete; check optional dependencies and supported inputs. Details withheld."}
        row.update(status=status,details=details)
        results.append(row)
    report = {"schema_version":"deterministic-toolkit/1.0","adapter_version":"bounded-toolkit-3",
              "input_sha256":prepared["input_sha256"],"source_binding":prepared["source_binding"],
              'numerical_environment':_numerical_environment(),
              "execution_status":"partial" if any(r["status"] in ("UNAVAILABLE","FAILED","UNDETERMINED") for r in results) else "complete",
              "checks":results,"manuscript_access":"read_only","findings_destination":"separate_user_report",
              "limitations":["Execution completion is not scientific validity; VERIFIED applies only to the supplied structured check.",
                             "Input provenance hashes do not establish the correctness of prose-to-formula mapping or data authenticity.",
                             "General proofs, arbitrary analysis code, figures and semantic citation support require separate review.",
                             "Reproducibility assumes the same adapter, backend versions and numerical platform."]}
    report["report_sha256"] = digest(json.dumps(report,sort_keys=True,ensure_ascii=False,allow_nan=False))
    return report


def verify_toolkit_spec(spec, document=None):
    return verify_prepared_toolkit(prepare_toolkit_spec(spec,document))
