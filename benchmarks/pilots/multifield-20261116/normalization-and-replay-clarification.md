# Pre-result normalization and repeat-comparison clarification

Recorded 2026-11-16 after source acquisition and code review, before any selected
paper was passed to the auditor. The original protocol and random draw are
unchanged. This is a local clarification, not external preregistration.

An agent code review found three implementation defects before the first run:
recursive removal of `source` keys could delete graph edge endpoints; comparison
included generated timestamps; naive XML flattening could join adjacent table
cells into false numeric tokens. All were corrected, with regression tests.

Both complete raw auditor reports are preserved, including every graph endpoint,
timestamp, source path and original reproducibility manifest. Semantic comparison
excludes only `generated_at_utc` and `input.filename` in the top-level and
reasoning-module reproducibility manifests, and the display `source` fields at
the report top level and reasoning/writing result roots. All other fields,
including source hashes, graph data, dependencies and repository provenance,
remain in the comparison. A repeat failure or per-paper exception is recorded
without replacing that paper or skipping later selected papers.

This explicitly broadens the frozen protocol's original path-only exception to
include generated timestamps. It was necessary because wall-clock metadata
are intentionally variable and not scientific findings. No outcome was available
when this clarification was recorded. Byte identity of raw timestamped reports
is not claimed.

Original JATS bytes remain unchanged. The first derived normalization and its
inventory are retained in `texts/` and `initial-sources.json`. The corrected
derivation uses `texts-v2/` and `sources.json`. It separates block/table-cell
content, preserves superscript/subscript boundaries in explicit notation and
does not certify mathematical equivalence or table reconstruction. Complete
originals are always the reference for typesetting, tables and figure links.

The complete publisher frame also exposes a scope limitation before execution:
broad taxonomy tags include e.g. statistical methods in agricultural and MRI
papers, and physical phenomena in biological papers. The predefined priorities
are retained without outcome-based resampling. These are six subject-tag strata,
not proof of six independently adjudicated scientific disciplines or appropriate
specialist-profile assignments. No exact scientific-error gold labels exist.
