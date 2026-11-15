# Advanced covariance and explicit analysis replay

## Authorized continuation

Implement the next software gaps while preserving existing work, frozen pilot
inputs and draft PR status. Real independent reviewer labels cannot be created
by this implementation; they remain unfilled. No whole-paper or expert accuracy
claim follows from software tests.

1. Add optional CR2/CR3 covariance to the existing bounded OLS cluster operation.
   Keep the CR1 default and its finite-sample convention unchanged. CR2 uses
   identity working covariance; CR3 uses the unscaled cluster HC3 convention.
   Use low-rank QR/SVD adjustments and abstain on unresolved leverage blocks.
   Retain t(G-1), explicitly not Satterthwaite or certified small-cluster inference.
2. Add an explicit offline source-checkout analysis replay tool. Stage exact
   hash-checked inputs and run only in an already available, content-addressed
   local Docker image, without network, writable sources, host secrets or a
   fallback to host execution. Bound resources, output, wall time and cleanup.
   Run twice; compare finite JSON results with declared tolerances and check
   repeatability. No automatic execution during manuscript/MCP review.
3. Verify independent numerical identities, protocol failure paths, source
   immutability, existing interfaces and an actual container replay in CI.
   This workspace has no Docker and a Bubblewrap isolation probe was denied;
   do not weaken isolation or claim local container execution was verified.
4. Request read-only agent review after implementation, fix concrete findings,
   run full appropriate checks, push the existing feature branch and update PR 8.

## Explicit remaining scope

This continuation does not fit multilevel random-effects models, implement
cluster bootstrap/power procedures, authenticate inputs, recruit human reviewers,
or establish representative scientific-error accuracy. These remain documented
gaps rather than being replaced with simpler formulas or invented judgments.
