# Scientific Reasoning Auditor — MCP adapter

A separate, optional MCP tool server for the Python engine in this repository.
It does **not** modify the SRA rules or make scientific truth judgments.

## Tools

| Tool | Inputs | External transmission |
|---|---|---|
| `audit_manuscript` | manuscript content, `file_format`, `encoding` | None |
| `audit_academic_writing` | manuscript, genre, language | None (rules only) |
| `check_citations` | manuscript, opt-in `online` | Crossref/DataCite only when both caller and host opt in |
| `verify_statistics` | structured `spec_json` | None |
| `verify_scientific_claims` | structured `spec_json` | None |
| `review_scientific_paper` | manuscript, `send_to_model` | Entire extractable text to configured model provider only after caller/host opt in |
| `get_review_capabilities` | none | None; supported coverage and limitations only |
| `verify_logic` | explicit formula JSON, optional manuscript content | None; local Z3 solver, separate findings only |
| `verify_toolkit` | bounded math/units/data/candidate JSON, optional manuscript content | None; local SymPy/Pint/SciPy/spaCy/RapidFuzz, separate findings |
| `prepare_inspection` | manuscript content, format, encoding | None; source-located candidates and bounded proposed specifications, never executed automatically |
| `review_manuscript` | manuscript, `study_type`, `disciplines`, optional structured JSON strings, consent flags | Offline by default; DOI/model calls require both caller and host opt-in |

`logic_spec_json` optionally supplies source-bound Z3 formulas to `review_manuscript`.
`toolkit_spec_json` optionally supplies the [local inspection toolkit](../docs/DETERMINISTIC_TOOLKIT.md)
to unified review. Sentence and passage results are candidates requiring review;
they never certify claims or semantic citation support. Install `.[toolkit]` for
these backends; neither model keys nor network enable flags are required.
`prepare_inputs=true` adds the same preparation to `review_manuscript`.
New toolkit kinds cover symbolic domain checks, regression/diagnostics,
rounding-aware reported statistics, citation source context, keyed CSV comparison
and inert SVG inspection. See [inspection expansion](../docs/INSPECTION_EXPANSION.md)
for precise limits. Source preparation requires confirmation; source retrieval
and SVG output remain review candidates.
Install the engine with `.[pdf,statistics,logic]` to enable formal verification;
it needs no model key or network enable flag. The manuscript is never modified.

The unified tool composes checks against a single source snapshot. Inspect
`result.execution_status` and each module even when the transport returns
`ok=true`: a requested optional module can fail while the other results remain
available. Supported profiles, study types and gaps are documented in
[cross-disciplinary review](../docs/CROSS_DISCIPLINARY_REVIEW.md). These additive
tools require the source checkout. PDF OCR and page vision remain unavailable
through MCP.

**Important:** These tools surface evidence-linked review signals. They cannot certify
that a manuscript is scientifically correct. The model-review tool cannot prove that
all PDF graphics, equations or page layouts have been interpreted.

## Install and test locally

Python 3.11+ is required. From the repository root:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[pdf,statistics,logic,toolkit]" -r mcp_server/requirements.txt
python -m unittest discover -s mcp_server/tests -v
python -m mcp_server.server
```

The final command starts **stdio** MCP. MCP clients must connect directly to the
process; the server writes protocol data to stdout. It is not an HTTP endpoint.

To exercise it using MCP Inspector, start it as a local stdio server with
`python -m mcp_server.server` and select that command in the Inspector.

## Inputs and upload boundaries

**No tool accepts local paths, URLs, arbitrary code, or persistent file IDs.**
Use `content` with `file_format="md"` or `"txt"` and `encoding="text"`
to submit plaintext. For binary PDFs, provide the base64-encoded original bytes
in `content`, `file_format="pdf"`, `encoding="base64"`.

There is a **20 MiB decoded document cap** and **1 MiB structured JSON cap**.
Each upload lives in an unpredictable, private temporary directory that is
removed at the end of that call. No shared document store or cross-user cache
exists. The server returns the original SRA result without silent truncation;
outputs exceeding 2 MiB produce an explicit error.

The base64 interface is a transport contract, **not automatic integration with
ChatGPT file attachments**. The host/client must explicitly supply the file
content through the MCP tool call; production-grade native file attachment
handling would require a separate supported upload integration.

The PDF parser does not execute manuscript code. PDF OCR/vision are deliberately
disabled in this MCP adapter. The CLI may provide additional document processing
capabilities, but they are not exposed over the network.

## Local HTTP demo (not publicly listed)

Set a random secret (minimum 32 printable ASCII characters) in the server host
environment and launch a local-only Streamable HTTP endpoint:

```bash
export SRA_MCP_BEARER_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
uvicorn mcp_server.http:app --host 127.0.0.1 --port 8000
```

Connect to `http://127.0.0.1:8000/mcp` using an MCP client that sends
`Authorization: Bearer <server-token>`. A request without a valid token
receives HTTP 401. `GET /healthz` is unauthenticated and discloses only
`{"status":"ok"}`.

To test the health endpoint:

```bash
curl --fail http://127.0.0.1:8000/healthz
```

For remote access, place the service behind a trusted **HTTPS** ingress.
Do not expose the raw HTTP endpoint or send fixed bearer tokens over plaintext.

## Docker

```bash
docker build -f mcp_server/Dockerfile -t sra-mcp .
export SRA_MCP_BEARER_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
docker run --rm --read-only --tmpfs /tmp:size=128m,mode=1777 \
  --memory=1g --cpus=2 -p 127.0.0.1:8000:8000 \
  -e SRA_MCP_BEARER_TOKEN sra-mcp
```

The image runs without root and requires the token at startup. Use a managed
secret store for production and enforce ingress request timeouts, quotas, TLS,
rate limits and OAuth/user identity before public multi-tenant use. The
in-process concurrency limit is two simultaneous analyses; this is not
a substitute for ingress rate limiting.

## External data and model consent

Default: DOI lookup and external model analysis are disabled.

To allow registry queries, set `SRA_MCP_ENABLE_NETWORK=1` **and** pass
`online=true` to `check_citations`. Only DOI metadata is sent to public
registries (not the entire manuscript). DOI registration does not establish
whether a citation supports a claim.

Model review requires ALL of the following:

* The manuscript owner has explicitly agreed to transmit their text;
* the tool receives `send_to_model=true`;
* the host sets `SRA_MCP_ENABLE_MODEL_REVIEW=1`, `SRA_MCP_MODEL` and
  `OPENAI_API_KEY` (and optionally `SRA_MCP_MODEL_BASE_URL`).

The service owner pays the configured provider. The full extracted text is
transmitted to that provider. Verify its retention policy, permissions,
available context limits, legal basis, usage quotas and billing first.
The private API key is never accepted as an MCP tool argument.

## Security boundaries and unfinished publication steps

* Request-specific temporary storage is deleted after each tool call,
  including errors. Distinct tool calls do not share data or storage IDs.
* File type, base64, decoded size, response size and structured JSON limits are
  checked. No arbitrary filesystem path, remote URL or user-supplied shell
  command is accepted.
* HTTP requires a bearer token, performs constant-time comparisons and rejects
  oversized requests; startup fails closed without a token.
* The fixed token protects a **single-owner/private** deployment. It does not
  establish separate user identities or permissions across an organization.
* The public OpenAI plugin directory currently requires a stable HTTPS
  endpoint, domain verification and supported submission authentication. Its
  connection form does not support static API-key authentication. Before
  submitting publicly, integrate a real OAuth 2.1 authorization server
  (and validate per-user tokens/scopes), enforce per-account quotas, deploy the
  HTTPS endpoint and prepare a compliant plugin ZIP/review assets. **This
  repository does not claim that public submission is complete.**
* Security tests do not prove absence of flaws, and real-expert scientific
  accuracy validation is separate from MCP transport testing.

Official guides:
- https://developers.openai.com/plugins/build/mcp-server
- https://developers.openai.com/plugins/build/plugins
- https://developers.openai.com/plugins/deploy/submission
