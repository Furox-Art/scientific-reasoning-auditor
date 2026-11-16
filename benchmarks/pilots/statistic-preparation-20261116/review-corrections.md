# Code-review corrections

The initial implementation and actual first development result are preserved at
commit 1c0c8f7 in initial-run.json/.md. It recovered all three frozen literals,
retained three unconfirmed abstentions and produced two agreements plus one
discrepancy only in the explicitly supplied central-chi-square scenario.
That numerical observation is not a confirmed scientific-error label.

A separate software-agent review found four issues: quadratic fallback
whitespace matching, scalar drafts truncated before percentage/range/uncertainty
suffixes, reopening sources after hash verification, and accepting an empty
analytic interval through zip(). The corrected implementation retains such
ambiguous values as full unresolved cues, consumes hash-verified snapshots once
and requires exactly two numerical interval endpoints.

The new whole-path runtime regression also exposed quadratic matching in the
existing plain-heading parser. Greedy bounded-end heading matching with a
non-whitespace boundary after an optional numbered/Roman prefix preserves normal
headings without the observed repeated whitespace rescanning. The regression
covers 190000-character whitespace runs for ordinary, Roman and numbered input.
These are measured controls, not a formal complexity proof for all inputs.

Eleven focused Python regressions and Node/MCP transport controls cover the new
behavior. The second development run uses a new output prefix. The original
0.10.0 twelve-paper report, its frame, sources and claims remain unchanged.
No source refresh, case reselection, human label or expert validation was added.

A follow-up suffix review additionally covered ASCII x/times scientific
notation, Unicode multiplication/fraction slashes and signed comma lists.
They remain full unresolved cues. The previous reviewed numerical result is
preserved as reviewed-run-v1.json/.md; the final code has its own fresh run.
