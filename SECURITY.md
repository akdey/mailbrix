# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this repository, please **do not** open a public GitHub issue.

Instead, report it privately via GitHub Security Advisories (or contact the repository maintainer directly) with:
- A description of the vulnerability and potential impact.
- Steps to reproduce or a minimal proof of concept.

## Security Design Notes

- **Zero Secrets in Git**: All API key hashes, HMAC signing secrets, and SMTP credentials are injected via runtime environment variables (`TENANTS_JSON`, `SMTP_PASSWORD`, etc.). Never commit `.env` or real tenant configurations.
- **Hashed API Keys**: Incoming `X-API-Key` headers are SHA-256 hashed and compared in constant time (`hmac.compare_digest`).
- **Replay Protection**: Tenants configured with `signing_secret` require `X-Timestamp`, `X-Nonce`, and `X-Signature` (HMAC-SHA256) headers.
- **Production Hardening**: Set `ENV=production` to disable `/docs`, `/redoc`, and `/openapi.json`.
