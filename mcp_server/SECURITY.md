# MCP security model

The adapter is designed for a **single trusted server owner** until public
OAuth authentication and account quotas have been configured.

- No tool accepts user-controlled file paths, network URLs, or executable code.
- Manuscripts are materialized in a dedicated temporary directory per call,
  returned only as bounded structured reports, and removed before tool return.
- Even if two analyses run concurrently, they cannot access a global manuscript
  store because the adapter has none. This is logical request isolation, **not
  an OS process sandbox**; deploy untrusted PDF processing in a locked-down
  container, with memory/CPU/time limits, for stronger isolation.
- HTTP accepts a configured 32+ character bearer secret and rejects missing,
  incorrect, and oversized requests.
- The health endpoint is unauthenticated by design and exposes no user data.
- External registry lookup and full-manuscript model transmission each require
  separate server-level and call-level opt-in. Consent and disclosure remain
  the service operator's responsibility.
- Do not publish a static-token service as a multi-tenant, OAuth-authenticated
  ChatGPT plugin. The directory's current submission connection form does not
  support API-key authentication.
- Check dependencies, container image provenance and runtime logging before
  a public deployment. Never log manuscript bodies, API keys or Bearer headers.

Please report vulnerabilities through the repository's security reporting
channel or a private message to its maintainer; do not paste private papers
or credentials in public issues.
