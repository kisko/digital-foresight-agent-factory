# Security Policy

## Reporting a vulnerability

If you discover a security vulnerability in this project, **please do not
open a public issue**. Instead, report it privately through GitHub's
[Private Vulnerability Reporting](https://github.com/kisko/digital-foresight-agent-factory/security/advisories/new).

We aim to:

- Acknowledge receipt within **3 working days**
- Provide an initial assessment within **10 working days**
- Coordinate a fix and disclosure timeline with you

## Scope

This is a **prototype**. It is intended for local development and as a
reference architecture. It is **not** hardened for production use as-is.

In scope for vulnerability reports:

- Code execution flaws in the agents, API, or dashboard
- Authentication / authorization gaps if/when those are added
- Dependency vulnerabilities materially affecting the prototype
- Prompt-injection paths that would let untrusted source content escalate
  beyond agent context (relevant once a live fetcher is added — see issue #4)

Out of scope:

- Issues that require the user to deliberately disable safety features
- Vulnerabilities in upstream dependencies already tracked by their maintainers
- Reports against unmaintained example data (`data/sample_signals.json`)

## Supported versions

Only the `main` branch is supported. There are no tagged releases yet.

## Hardening for production

If you are adapting this prototype for production, please review the Azure
deployment architecture in
[`docs/architecture-presentation.html`](docs/architecture-presentation.html)
— in particular the sections on:

- Identity (Entra ID + Managed Identities)
- Network isolation (Private Endpoints, VNet integration)
- Policy & content safety (A1 + Azure Content Safety + Purview)
- Approval gates (B6 + Teams adaptive cards)

The prototype intentionally omits these so the local demo stays simple.
