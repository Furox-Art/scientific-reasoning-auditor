# SRA scientific proof kernel

SRA now contains its own standalone deterministic proof kernel,
`sra-finite-interval-1`. It is an implementation of finite propositional model
checking and exact rational interval arithmetic. It is not a call to Z3, SymPy,
SciPy or a language model. It needs only the Python standard library.

The kernel proves conditional statements over an explicitly supplied formal
problem. It does not automatically translate a paper into true premises, invent
scientific laws or certify a manuscript's overall quality. This is a first
bounded kernel, not an unrestricted theorem prover or universal scientific oracle.

## Run it

```bash
sra prove-science examples/scientific-proof.json --out reports/proof
sra verify-science-certificate examples/scientific-proof.json reports/proof.json --out reports/rechecked
```

```python
from sra.science_kernel import prove_science
from sra.science_certificate import verify_science_certificate

report = prove_science(spec)
check = verify_science_certificate(spec, report)
assert check["valid"]
```

Node: `proveScience(specPath, { out: "reports/proof" })` and
`verifyScienceCertificate(specPath, certificatePath, options)`.
MCP: `prove_science(spec_json)` and
`verify_science_certificate(spec_json, certificate_json)` accept only bounded
inline JSON. No paths, network requests, model transmission or arbitrary code.
The Node adapter checks the actual kernel capability, not just a package version.

The CLI writes separate JSON/English Markdown reports, preserves input files,
and rejects symlink/hardlink output collisions. Proof-command exit 0 means the
formal calculation completed, including unresolved or inconsistent problems.
Certificate-command exit 1 means invalid; input errors exit 2. The kernel is
standalone and is not silently run by unified manuscript review.

## Formal input

Input `schema_version` is `"1.0"`. Required arrays are `atoms`, `facts`,
`arithmetic`, `rules`, `claims`; optional `sources` contains snapshots.

- `atoms`: 1..16 distinct simple names, ASCII letter first, up to 64 characters.
- `facts`: up to 32 `{id, atom, value, origin, source_refs?}` records. `value` is
  true, false or null. `origin` is `assumption` or `evidence`. Evidence facts need
  at least one source quotation. A quotation anchors a caller's interpretation;
  it does not establish that the Boolean interpretation is correct.
- `arithmetic`: up to 32 `{id, atom, relation, left, right, source_refs?}` records.
  Relations are `lt`, `le`, `eq`, `ne`, `ge`, `gt`. These observations are computed
  by the kernel; their Boolean values cannot be supplied by the caller.
- `rules`: up to 32 `{id, expression}` records. These constraints are explicit
  assumptions, not learned or authenticated scientific laws.
- `claims`: 1..32 `{id, scope, expression}` records. Scopes are `declared_problem`,
  `supplied_corpus`, `supplied_search`, `supplied_measurement_model`, `declared_method`.
  A scope label does not validate a claim's scientific interpretation.

IDs must be globally distinct across the four record arrays. Atom/source names
have separate namespaces. A problem has at most 512 expression nodes in total
and depth 16. The four record arrays and this node cap apply together.

Logical expressions are JSON objects: `{"atom":"a"}`, `{"const":true}`, or
`{"op":"and","args":[...]}`. `and`/`or` require 2..16 arguments; `not` requires
one; `implies`/`iff` require two. There are no function calls, Python expressions,
quantifiers, undeclared variables, external imports or user-defined programs.

Numeric expressions are integers, decimal/rational strings (for example
`"0.1"`, `"1/3"`), `{"interval":["0.1","0.2"]}`, or binary `add`, `sub`, `mul`,
`div` objects with `args`. Floating-point JSON literals are rejected; use exact
strings. Literals are bounded to 256 numerator/denominator bits and strings to
64 characters. Intermediate rational bounds are limited to 4096 bits. A divisor
interval containing zero or a numeric resource limit produces an unknown
observation, never a fabricated bound.

An interval comparison is proved true only if true for every point in the
computed enclosures; proved false only if false for every point. Overlap abstains.
For equality, only equal point intervals establish true; disjoint intervals
establish false. Arithmetic is exact relative to the supplied bounds. It does
not authenticate measured data, derive uncertainty bounds, check units or preserve
unwritten dependencies between repeated intervals.

## Evidence identity

Up to 16 inline sources have `{id,text,sha256}`. Each is at most 100,000
characters; aggregate source text is at most 200,000. Hash the exact UTF-8
snapshot, with no implicit whitespace or line-ending normalization.

`source_refs` is an optional array of up to eight `{source_id,quote,start}`
records. Quotes have 1..2000 characters. `start` is a Python Unicode codepoint
offset, not a UTF-8 byte offset or JavaScript UTF-16 offset. The exact slice must
match. The certificate records source IDs, snapshot digests, quotes and offsets.
Hashes prove identity/integrity against supplied snapshots, not authenticity,
independent retrieval, authorship or semantic truth.

Input and the complete pretty JSON certificate are each bounded to 1 MiB.
Oversized certificates are rejected in full, not truncated. Source files and
manuscripts are never edited. There are no external solver or model credentials.

## Proof calculation

Each declared Boolean atom defines one bit in an assignment. The prover
constructs a bit-parallel truth table for all `2^n` worlds (at most 65,536).
Known facts, decisive native arithmetic and rule assumptions restrict the world
set. Null facts and unknown arithmetic do not become false; their atoms remain
free unless other explicit premises constrain them.

For each claim:

| Status | Formal meaning |
| --- | --- |
| ENTAILED | Every admissible Boolean world satisfies it. |
| CONTRADICTED | No admissible Boolean world satisfies it. |
| UNRESOLVED | Both supporting and counter-worlds exist, or premises conflict. |

Inconsistent premises produce a deletion-minimal conflict core and abstentions
for every claim, including tautologies. The kernel deliberately refuses
explosion-based scientific conclusions. With consistent premises, decisive
claims include a deletion-minimal supporting premise set. These greedy deletion
explanations are deterministic, not necessarily minimum-cardinality proofs.

Counter-worlds are assignments in the Boolean abstraction, not necessarily
jointly realizable numerical data or experiments. Unknown arithmetic atoms are
not linked by an unimplemented joint numerical feasibility theory. Model counts
are not probabilities or scientific-confidence scores; no prior is assumed.
The first supporting/counter-world is selected canonically by atom order and
world index. Atoms are sorted case-sensitively.

## Certificate verification

The JSON report includes input and kernel-source hashes, exact arithmetic
observations, admissible-world count/digest, claim counts, witness assignments,
bases, conflict core and a SHA-256 certificate digest. The digest is not a
substitute for proof verification. Rehashing a forged conclusion does not make
it valid.

The separate checker enumerates worlds with a scalar interpreter and recomputes
intervals by endpoint corner evaluation. It does not call the prover or reuse
its bit-parallel expression evaluator. It checks conclusions, canonical witnesses,
world counts/digest, and validity plus deletion-minimality of each basis/core.
Alternative genuinely valid minimal bases can be accepted. The scalar checker
is intentionally slower than the bit-parallel prover; maximum-size rechecks can
take seconds and remain bounded by the fixed input/world limits. The two implementations
share the bounded input grammar, resource bounds and static report metadata;
this is not an independent external expert assessment.

`schemas/scientific-proof.schema.json` validates report shape. It cannot validate
entailment: run `verify_science_certificate` for that. A valid certificate requires
the current kernel source/version; the source digest identifies package files,
not a signed origin or runtime-memory attestation. Fixed input and fixed kernel
code produce deterministic output without clocks, randomness or platform floats.

## Scientific use and limits

The synthetic example illustrates selected-corpus feature conditions, a missing
search premise, an exact arithmetic bound, and caller-declared target alignment.
These records are fictional and manually formalized. No real paper, search or
expert verdict is authenticated. General novelty, literature adequacy, measurement
validity and method appropriateness remain NOT_ASSESSED.

This kernel supplies a reusable reasoning/calculation engine, rather than four
fixed text-screening procedures. New scientific theories still need explicit
formalization and justified data. Unsupported mathematics, missing evidence,
open-world literature completeness and substantive scientific judgments cannot
be settled merely by naming an atom or obtaining a conditional proof.
