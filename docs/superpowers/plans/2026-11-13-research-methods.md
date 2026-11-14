# Research-method inspection and Python update

User authorized the seven proposed areas and then requested a Python update.
Preserve manuscript read-only behavior, separate English reports, existing APIs,
and the existing draft-PR branch. No UI, merge or package publication.

1. Update the user's Windows Python to the latest stable official release and
   create a clean project environment. Python 3.15.2 official installer/hash were
   verified. Standard installation failed in its optional stdlib test MSI; the
   same installer succeeded with Include_test=0. SSL/venv/pip and launcher/PATH
   checks passed; py now selects 3.15.2. Keep old runtimes for existing projects.
2. Add bounded structured toolkit kinds: causal_graph, bias_assessment,
   power_analysis, meta_analysis, bayesian_diagnostics, ml_validation,
   publication_status. All structured inputs validate before optional imports.
3. Integrate real libraries: NetworkX backdoor-criterion/d-separation checks;
   statsmodels power and random-effects estimation; ArviZ array diagnostics.
   Bias and ML manifests use transparent explicit rules. Crossref snapshots work
   offline; existing opt-in DOI calls expose registered updates without an extra
   request. Distinguish an updated article from a notice updating another work.
4. Add English examples/docs, capabilities and optional extras, preserving base
   zero dependencies. Add Python 3.15 CI while retaining 3.11/3.12 compatibility.
5. RED/GREEN scientific/adversarial tests, full 100% src statement coverage,
   Node/MCP round trips, one fresh whole-change review and one coherent fix pass,
   clean/reproducible packages, push and update the existing draft PR.

Rulings: DoWhy 0.14 excludes Python >=3.14 and caps SciPy; use NetworkX's explicit
graph criterion on the upgraded runtime rather than ignoring dependency limits.
This is conditional model checking, not empirical proof of causality. Bias
judgments are caller-supplied evidence reviews, not a licensed RoB2 reproduction
or automatic expert certification. MCMC diagnostics do not prove posterior
correctness. Meta-analysis operates on declared common effect scales. No update
metadata means no updates reported, never proof that a paper is unretracted.

Implementation complete. Python 3.15.2, pip, SSL, venv, launcher selection and
the clean project's dependency consistency were verified. Previous feature work
was at 941d758, with a clean working tree before this plan.

Fresh whole-change review completed. RED/GREEN regressions fixed fractional
Crossref snapshot hashing (preserve JSON numbers), ill-conditioned Egger designs
and probability underflow (abstain while retaining valid pooled estimates).
Publication classification also distinguishes full/partial retraction,
withdrawal and removal in both link directions. Conditional-extra metadata is
checked independently in wheel Requires-Dist and grouped sdist requires.txt,
retaining exact content/inventory checks. No second review loop was added.

Final local validation: 739 Python tests, 6230 runtime statements, 100% statement
coverage; 28 Node and 43 MCP tests; compileall and 10/10 synthetic heuristic
controls. The seven-kind English example executes completely on Python 3.15.2.
Remaining delivery checks: isolated reproducible packages, GitHub push/PR update
and the remote Python/Node CI matrix. Registry completeness/authenticity,
scientific model assumptions and external expert accuracy are not certified.
