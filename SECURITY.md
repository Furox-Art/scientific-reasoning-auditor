# Security Policy

## Supported versions

Security fixes are applied to the latest released version of the Python package
and the latest released version of the Node.js adapter.

| Package | Supported |
| --- | --- |
| `scientific-reasoning-auditor` (PyPI) | 0.5.x |
| `scientific-reasoning-auditor` (npm adapter) | 0.1.x |

Older releases do not receive security fixes; upgrade to the latest release.

## Reporting a vulnerability

Report vulnerabilities privately through GitHub's private vulnerability
reporting for this repository:

https://github.com/Furox-Art/scientific-reasoning-auditor/security/advisories/new

Do not open a public issue, pull request or discussion for an unfixed
vulnerability. Please include the affected version, a minimal reproduction and
the impact you observed.

You can expect an initial acknowledgement, a decision on whether the report is
in scope, and a coordinated disclosure timeline. This is a small project without
a paid security team, so no fixed response-time guarantee is offered.

## Scope

In scope:

- The Python package source in `src/sra/`, the CLI entry point, the Node.js
  adapter (`index.js`, `index.d.ts`, `bin/`) and the published distribution
  artifacts.
- Unsafe handling of untrusted input: manuscript files, JSON audit reports,
  semantic-review documents and imported graph objects.
- Anything that breaks a behavior the test suite enforces, such as writing to a
  source manuscript or template instead of the requested output path
  (`tests/test_domain_cli.py`).

Out of scope:

- The scientific or statistical correctness of a finding for a particular
  manuscript. The tool emits review signals, not verdicts; see the
  interpretation rules in `README.md`.
- Results obtained by sending manuscript text to a third-party model provider
  that you configured yourself.
- Vulnerabilities in optional third-party dependencies (`pypdf`, `scipy`,
  `jsonschema`, Node.js) that are already fixed upstream.
- Issues that require a locally modified copy of the source.
