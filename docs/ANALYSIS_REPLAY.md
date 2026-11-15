# Explicit offline analysis replay

`tools/replay_analysis.py` is a **source-checkout tool** for explicitly running
Python analysis code in a preexisting, pinned local Docker image. It does not
run automatically during manuscript review and is not exposed as an execution
operation through Node or MCP. The ordinary toolkit APIs retain their existing
no-arbitrary-code contract. A separate numeric report is produced; original
scripts, data and manuscripts are never mounted writable or modified.

This adapter requires a trusted local Docker daemon, image and host configured
for Linux containers. It requests restrictive container settings; it is **not a
certified security boundary** or a general service for adversarial code. Review
the source and permitted data before opting in. It does not authenticate an
image, dependencies, data, authors, source mappings or scientific assumptions.

## Manifest and preparation

Install the source checkout with `python -m pip install -e .`. Put a manifest
beside its declared script/data files:

```json
{
  "schema_version": "analysis-replay/1.0",
  "image_id": "sha256:REPLACE_WITH_64_LOWERCASE_HEX_LOCAL_IMAGE_ID",
  "entrypoint": "analysis.py",
  "files": [
    {"name": "analysis.py", "sha256": "REPLACE_WITH_EXACT_SCRIPT_SHA256"},
    {"name": "data.csv", "sha256": "REPLACE_WITH_EXACT_DATA_SHA256"}
  ],
  "reported": {"estimate": "2.5"},
  "atol": "0.000001",
  "rtol": "0",
  "timeout_seconds": 60
}
```

The example placeholders deliberately do not validate. Use an already installed
image ID, obtained with `docker image inspect YOUR_IMAGE --format '{{.Id}}'`.
Image selection/preparation is an explicit operator task: the replay adapter
never pulls images, installs dependencies or uses a mutable image tag. It accepts
only Linux images with no declared `Config.Volumes`; inherited anonymous volumes
would introduce additional writable storage outside the bounded tmpfs. Inherited
healthchecks are disabled explicitly. The adapter accepts
1-16 distinct safe basename files, at most 16 MiB combined, and checks exact
SHA256 hashes before any runtime contact. Symlink inputs are rejected. The script
must be one declared `.py` file. Relative file access is from `/inputs`.

The script must print exactly one JSON object on stdout with the same 1-32 simple
numeric keys as `reported`; other diagnostics belong on stderr. Finite JSON
numbers or decimal strings preserve decimal values through comparison. No JSON
NaN/Infinity, duplicate keys, nested outputs or mismatched keys are accepted.
Each numeric token is bounded by the existing toolkit's decimal grammar.
Absolute/relative tolerances are in [0,1]; defaults are zero. Timeout is an
integer from 1 to 300 seconds per analysis trial, default 60.

```bash
python tools/replay_analysis.py path/manifest.json --out preflight.json
python tools/replay_analysis.py path/manifest.json --execute --out replay.json
```

Without `--execute`, the adapter validates inputs and returns `NOT_EXECUTED`,
without contacting Docker. Reports require a new output path whose parent
already exists; existing outputs/input aliases are never overwritten. A missing
client, inaccessible daemon or unavailable pinned image produces `UNAVAILABLE`;
there is **no host-process fallback**. Local endpoints are fixed to
`unix:///var/run/docker.sock` or Windows `npipe:////./pipe/docker_engine`, with
Docker environment overrides removed. Remote, custom and rootless endpoints are
outside this adapter. Windows requires an appropriate local Linux-container
backend; the actual container integration test currently runs on Linux CI.

## Execution and numeric meaning

Exact copied input bytes are staged under a private host parent. Only the staged
child is mounted read-only. The container is explicitly created, then started
with attached output only after creation is confirmed. It uses a nonroot UID,
no network or shared IPC, read-only root, dropped capabilities, no-new-privileges,
64 PIDs, 512 MiB memory/swap ceiling, one CPU and a 64 MiB `/tmp` tmpfs. It does
not mount the Docker socket, host home, source directory or host credentials.
Only the staged declared files are mounted. The Python entrypoint is fixed and
uses `-I -B`; no shell is invoked. Default image entrypoints are overridden.
Process-local BLAS thread limits are supplied, but arbitrary code can still have
uncontrolled randomness. `-I` does not provide a fixed Python hash seed.

Stdout and stderr share a 64 KiB capture bound. Timeout or excessive output
terminates the client and triggers explicit removal of this adapter's uniquely
named container and its anonymous volumes as a defensive cleanup measure.
Successful removal/absence is checked with an exact name
inventory. Unconfirmed creation/cleanup cannot produce agreement. Reports retain
container names so operators can inspect a failed cleanup; a daemon failure
can still leave resources requiring operator cleanup. The script does not
remove unrelated containers.

Two separate trials must finish, have confirmed container exit/cleanup and
produce matching exact numeric values for the selected outputs. Different
numeric values return `UNDETERMINED`. Equivalent decimal representations count
as equal values; raw stdout hashes are retained separately. Two matching trials
are a limited repeatability observation, **not proof of general determinism**.

For stable outputs, each comparison is exact rational arithmetic:
`abs(computed-reported) <= atol + rtol*abs(reported)`. `VERIFIED`/`REFUTED`
means agreement/disagreement with supplied numeric outputs only, not that the
method, model, original paper or underlying data is scientifically valid.
Runtime/protocol/cleanup failures remain `FAILED`; no missing result is treated
as agreement. Image/input/manifest hashes are retained, but they do not prove
source authenticity or authenticate an externally supplied receipt.

## Validation and limits

Unit tests cover actual bounded process capture, strict manifests, source changes,
exact numeric boundaries, two-run comparison, resource flags, failures and
cleanup logic. Mocked Docker responses test protocol handling, not confinement.
The `analysis-replay` CI job separately runs actual synthetic container analyses,
checks read-only mounts/root, nonroot execution, blocked outbound connection,
source preservation, reported-value mismatch, timeout/output cleanup and changed
input rejection. It records the exact local image ID selected for that run.

This workspace has no Docker client; a separate Bubblewrap probe was denied.
Local tests therefore cannot be presented as an actual container execution.
Docker's current runtime/kernel protections remain prerequisites, not a result
of this software. See the official
[run options](https://docs.docker.com/reference/cli/docker/container/run/) and
[security model](https://docs.docker.com/engine/security/).

General pipeline orchestration, arbitrary system dependencies, data retrieval,
GPU/HPC execution, imported replay receipts in the unified criteria matrix and
proof of code/data authenticity are outside this implementation. The existing
real-paper pilot and its unfilled human-review forms remain unchanged.
