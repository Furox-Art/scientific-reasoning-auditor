# Bounded evidence checks

Implement three dependency-free toolkit operations through the existing Python,
CLI, Node and MCP contracts. Manuscripts remain read-only. Bound operations use
the document snapshot, prohibit alternate text, and validate all evidence before
execution. Source identities and exact quote offsets must be reproducible.

1. `source_overlap`: casefolded Unicode word shingles against 1..8 supplied
   sources, bounded token indexing, union token coverage and at most 100 example
   alignments per source. This is lexical screening, never plagiarism/novelty
   determination. No quotation or bibliography exclusions are inferred.
2. `protocol_consistency`: compare 1..100 caller-mapped string values supported
   by exact quotes in the supplied protocol and manuscript snapshots. Null
   mappings stay unknown. Equality is literal; mapping correctness and protocol
   authenticity/prospective registration remain unverified.
3. `checklist_evidence`: audit records for 1..100 caller-supplied requirements.
   Reported items require manuscript quotes, exclusions require rationales;
   omitted/unknown records remain explicit gaps. Quote occurrence does not prove
   relevance, adequacy or official guideline completeness.

Write failing behavior/source-binding/boundary tests first. Implement strict
preflight, computations, capabilities, criteria evidence scopes and examples.
Run full Python/Node/MCP checks, 100% statement coverage, distribution checks and
visual report/document QA. After implementation, obtain a separate agent's code
review and resolve reproduced findings. Push only the existing feature branch
and update draft PR #8 after successful validation; never merge or publish.

## Implementation and review record

- Implemented all three operations with strict preflight, existing transports,
  capabilities, source-bound criteria evidence and synthetic examples.
- Short snapshots abstain when a token window cannot be formed; other source
  results and proved protocol differences survive incomplete evidence.
- A separate read-only review agent reproduced oversized example quotes across
  long punctuation gaps. The regression failed before the fix; previews are now
  bounded to 240 characters with exact preview offsets and full window-end
  metadata. The reviewer rechecked the same input (46,585-byte report; MCP
  succeeds), all nine evidence tests, malformed-input mutations and the fix.
  No remaining demonstrated bug was reported. This was software review, not
  independent scientific expert validation.
- Linux Python 3.12.14: 775 Python tests passed, 6607/6607 runtime statements
  covered (100% statement coverage). Node 24.22.1: 28 tests passed. MCP: 45 tests
  passed. Compile, dependency, whitespace and 10 synthetic controls passed.
- Two independent wheel/normalized-sdist builds matched byte for byte. Exact
  inventories (171 source files, 59 runtime modules), isolated installation,
  CLI/audit and package metadata checks passed.
- Rendered the final synthetic report and operation document, inspected both
  visually and checked page text bounds. No overflow found.
- Windows Python 3.15 and remote CI are verified separately during delivery;
  local Linux results above do not substitute for those environments.
