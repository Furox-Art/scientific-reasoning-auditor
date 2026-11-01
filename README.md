# Scientific Reasoning Auditor

A research software project for auditing the reasoning chain in scientific manuscripts:

Hypothesis -> assumptions -> methods -> data -> analysis -> inference -> conclusion

The goal is not to assign a superficial quality score. The tool should produce traceable review signals, link claims to potential supporting evidence, expose assumptions and alternative explanations, and distinguish machine-generated observations from verified scientific conclusions.

## Current status: v0.1.0

The first implementation is a deliberately limited, deterministic screening baseline.

### Included
- Load Markdown and UTF-8 text manuscripts.
- Optional PDF text extraction with the pdf extra.
- Detect common methods, limitations, results, conclusion and references headings (English and selected Turkish labels).
- Flag selected absolute/conclusive language.
- Flag documents containing both association and causal wording for contextual review.
- Generate candidate links between conclusion claims and results sentences using lexical overlap.
- Produce JSON and Markdown reports with a SHA-256 hash of the source file.
- Run tests with Python's standard unittest framework.

### Not included yet
- Semantic entailment or scientific fact verification.
- Equation derivation or numerical recalculation.
- Statistical re-analysis or code execution from supplementary materials.
- Literature verification and citation checking.
- Discipline-specific expert review.
- LLM-based reviewer agents.

A lexical match is not evidence that a result scientifically supports a claim. A flagged phrase is not proof of an error. Absence of flags is not proof of correctness.

## Install

    git clone https://github.com/Furox-Art/scientific-reasoning-auditor.git
    cd scientific-reasoning-auditor
    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install -e .

For PDF input, install the optional dependency:

    python -m pip install -e ".[pdf]"

## Run

    sra audit examples/sample_manuscript.md --out reports/sample

The command writes reports/sample.json and reports/sample.md.

## Design principles

1. Evidence traceability: every finding should point to an inspectable passage or explicit missing evidence.
2. Calibrated language: distinguish detected, suspected, not assessed, and verified.
3. Reproducibility: retain source hashes, tool versions, parameters and execution logs.
4. Separation of concerns: parsing, deterministic checks, computational verification, literature review and LLM reasoning remain separate modules.
5. Human oversight: the software supports expert review; it does not replace peer review.

## Planned milestones

- [x] Repository bootstrap and deterministic screening baseline.
- [ ] Robust section and claim extraction across PDF/HTML/Word inputs.
- [ ] Claim-evidence graph with passage-level provenance.
- [ ] Methodology and causal-inference review checks.
- [ ] Equation and quantitative-result verification.
- [ ] Reproducibility checks for code, data, dependencies and environment.
- [ ] Literature and citation verification using authoritative sources.
- [ ] Optional multi-agent review with disagreement tracking.
- [ ] Domain-specific check packs and benchmark evaluation.

## Development

    python -m unittest discover -s tests -v
