# Cross-disciplinary Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Compose source-bound, applicability-aware scientific review through all existing interfaces.
**Architecture:** Shared parsed document, explicit capability registry, unified orchestrator and renderer; thin CLI/Node/MCP adapters.
**Tech Stack:** Python 3.11+, standard library, existing optional SciPy/pypdf/MCP; Node 18+.
**Spec:** ../specs/2026-11-12-cross-disciplinary-review-design.md (approved in chat).

## Global Constraints

- No new runtime dependency; retain legacy outputs and profile hashes.
- No manuscript/model network transmission by default; explicit consent on every external path.
- Source input is immutable; all modules bind to identical raw and extracted hashes.
- No scientific score, fabricated expert labels or accuracy claim.
- Preserve 100% Python statement coverage and existing behavior tests.

## Review Focus

- Theoretical/narrative papers: empirical heading expectations are excluded visibly.
- Mixed/unknown study type: no unearned applicability conclusion.
- Mutation between modules: use one parsed snapshot; never mix source identities.
- Optional failures: partial execution rather than complete scientific assessment.
- Invalid structured specs/consent: reject before model or DOI network requests.

### Task 1: Source-bound composition and applicability

**Files:** Create `src/sra/capabilities.py`, `src/sra/review.py`, `src/sra/review_report.py`, `tests/test_unified_review.py`; modify `src/sra/writing.py`, `src/sra/doi.py`, `src/sra/paper_review.py`.
**Interfaces:** `capabilities() -> dict`; `review_manuscript(path, *, study_type='unknown', disciplines=(), style_language='en', online=False, statistics_spec=None, scientific_spec=None, send_to_model=False, model=None, base_url=..., api_key_env=..., timeout=120, chunk_chars=12000, pdf_ocr_mode='off', ocr_languages='eng', visual_pages=False) -> dict`; `review_document(document, **options) -> dict`; `review_markdown(report) -> str`.

- [ ] Write and run failing tests for default no-network composition, theoretical exclusions, multi-profile deduplication, unknown/mixed applicability and immutable source binding.
- [ ] Add parsed-document writing, DOI and model helpers; retain public path APIs and validation behavior.
- [ ] Implement registry/catalog, configuration validation, bounded strict JSON spec preflight, module statuses, source-bound results, gaps and report rendering.
- [ ] Test supplied stats/science, optional failures, mismatched input, source mutation, invalid specs/consent and Markdown escaping. Run targeted and existing suites; inspect coverage.
- [ ] Commit source-bound unified core.

### Task 2: CLI and Node interfaces

**Files:** Modify `src/sra/cli.py`, `index.js`, `index.d.ts`; create `tests/test_unified_cli.py`, `test/unified-review.test.js`.
**Interfaces:** `sra review`, `sra capabilities`; Node `reviewManuscript(input, options)` and `capabilities(options)` return existing CommandResult.

- [ ] Write/run failing CLI and Node entry-point tests.
- [ ] Add repeated --discipline, study type, structured spec paths, explicit model/online options, source-alias checks and 0/1/2 execution exit codes.
- [ ] Node validates options before spawning and probes new Python feature availability explicitly; do not misrepresent old 0.8.0 installations as supporting new commands.
- [ ] Test all validation branches and real CLI invocation in an isolated installed engine; commit.

### Task 3: Bounded MCP interfaces

**Files:** Modify `mcp_server/bridge.py`, `mcp_server/server.py`; create `mcp_server/tests/test_unified.py`; update protocol tests for additive tools.
**Interfaces:** `get_review_capabilities()`; `review_manuscript(content, file_format='md', encoding='text', study_type='unknown', disciplines=None, style_language='en', online=False, statistics_spec_json=None, scientific_spec_json=None, send_to_model=False)`.

- [ ] Write/run failing tests for offline source-bound composition, allowed profiles and consent combinations.
- [ ] Reuse existing upload, JSON, response and concurrency limits; configure model only from host settings. Disable OCR/vision in MCP; annotate external capability accurately.
- [ ] Test protocol listing, complete/partial returns, temporary cleanup, oversized responses, invalid booleans and blocked transmissions; commit.

### Task 4: Documentation, packaging and final verification

**Files:** Update `README.md`, `CHANGELOG.md`, `mcp_server/README.md`; add `docs/CROSS_DISCIPLINARY_REVIEW.md` and synthetic examples; record baseline and evidence.

- [ ] Add tested synthetic fixtures for six study/field scenarios and schema/report contract assertions.
- [ ] Document exact supported scope, default offline behavior, example commands and missing specialist coverage.
- [ ] Run complete Python coverage, Node, MCP and packaging/provenance checks using the modified source, never a stale global install.
- [ ] Request a fresh whole-branch code review as required by executing-plans; fix substantive findings with regression tests.
- [ ] Commit final changes and provide a reviewable patch/bundle with verification evidence. Do not publish packages or deploy.
