# Report presentation

The unified review produces natural English Markdown by default. Fixed templates
state what ran, what failed, and what still needs review. No language model,
network request or random choice is added by rendering. Requested model review
remains a separate, explicitly consented analysis module.

```bash
sra review paper.md --report-style natural --out reports/readable
sra review paper.md --report-style technical --out reports/technical
```

```python
from sra.review import review_manuscript
from sra.review_report import review_markdown

report = review_manuscript("paper.md")
text = review_markdown(report, style="natural")
full = review_markdown(report, style="technical")
```

The natural presentation replaces repetitive criterion procedures with a compact
coverage table. Evidence requirements, procedures, support levels, applicability
reasons and criterion evidence pointers remain in the JSON report and technical
Markdown. Both presentations include module-specific findings, calculations,
source quotes/locations, hashes, exclusions and interpretation limits. Unknown
module results remain visible as fenced JSON. No manuscript is modified.

“Requested checks finished” describes execution. It does not mean a paper is
valid. Criterion verdicts remain NOT_ASSESSED. VERIFIED and REFUTED concern
explicit inputs under supplied assumptions; UNDETERMINED remains an abstention.
Text cues and model advice do not establish an error. There is no overall
scientific quality score.

Node accepts `reviewManuscript(path, { reportStyle: "natural" })` or
`reportStyle: "technical"`. npm 0.4.0 requires Python 0.11.0 or newer, installed
separately. Python's default renderer and the CLI default are natural; callers
that depend on the older Markdown headings should select technical explicitly.
Default structured JSON payloads and numerical analysis are unchanged. The review
schema additionally permits the optional MCP `readable_report` field.

MCP's `review_manuscript(..., report_style="natural")` adds a `readable_report`
field to its structured result. `"technical"` is also accepted. Without this
argument, no field is added. Rendering occurs after temporary paths are scrubbed
and the complete response still has the existing 2 MiB limit. Oversized responses
are rejected in full; evidence is never silently truncated to fit.

This is a presentation feature, not a detector of AI authorship. It makes no
claim about human authorship or passing AI detectors. It adds no scientific
validation data or independently adjudicated human labels.
