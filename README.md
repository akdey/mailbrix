# Email Relay Service

A lightweight, multi-tenant **FastAPI** HTTP-to-SMTP email relay microservice built for **Vercel** and containerized deployments.

## Features

- **Multi-App / Multi-Tenant Support**: Register calling applications via individual `TENANT_<APP>` environment variables (ideal for Vercel) or `TENANTS_JSON`, each with its own `app_id`, sender identity (`from_name`, `from_email`), rate limit, recipient domain allowlist, and optional dedicated SMTP credentials.
- **Hashed API Key Authentication**: Authenticates requests via `X-API-Key` (and optional `X-App-Id`) using SHA-256 key hashes and constant-time comparison (`hmac.compare_digest`).
- **HMAC Request Signing & Replay Protection**: Optional per-tenant or global `HMAC-SHA256` request signing (`X-Timestamp`, `X-Nonce`, `X-Signature`) with timestamp tolerance and nonce deduplication.
- **Rate Limiting & Payload Guards**: Built-in sliding-window rate limiting per IP and per `app_id`, plus configurable limits for request size, recipient count, attachment count/size, and blocked executable extensions.
- **Rich Email & Attachment Support**: Supports HTML and plain-text bodies, single or multiple recipients, `cc`, `bcc`, `reply_to`, and base64-encoded attachments over `STARTTLS` or `SMTP_SSL`.
- **Production Hardening**: Non-blocking SMTP delivery (`asyncio.to_thread`), sanitized `502` error responses, security response headers, and automatic disabling of `/docs`, `/redoc`, and `/openapi.json` when `ENV=production`.

---

## Quick Start

### 1. Generate App Credentials
Generate an API key, its SHA-256 hash, and an HMAC signing secret for each calling app:

```bash
python3 scripts/generate_key.py billing-app
```

### 2. Configure Environment
Copy `.env.example` to `.env` (or set these in your hosting provider's environment variables):

```bash
cp .env.example .env
```

Set the generated `TENANT_<APP>` variable (or `TENANTS_JSON`) and your `SMTP_*` credentials.

### 3. Run Locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 3000
```

### 4. Deploy to Vercel
The included `vercel.json` routes all requests to `main.py` using `@vercel/python`. Configure your environment variables in the Vercel dashboard and deploy with `vercel`.

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `ENV` | `development` | Set to `production` to disable `/docs`, `/redoc`, and `/openapi.json` |
| `APP_NAME` | `Email Relay Service` | Service name returned by `/health` |
| `TENANT_<APP>` | — | Per-app JSON config (auto-discovered from env; optional `app_id` overrides suffix) |
| `TENANTS_JSON` | `""` | Optional JSON object mapping `app_id` to tenant config |
| `REQUIRE_HMAC_SIGNATURE` | `false` | Require HMAC signing for all tenants |
| `HMAC_TOLERANCE_SECONDS` | `60` | Allowed clock skew for `X-Timestamp` |
| `IP_RATE_LIMIT_PER_MIN` | `120` | Max requests per minute per client IP |
| `MAX_REQUEST_BYTES` | `5242880` | Max raw request body size (5 MB) |
| `MAX_RECIPIENTS` | `50` | Max combined `to_email` + `cc` + `bcc` recipients |
| `MAX_ATTACHMENTS` | `5` | Max attachments per email |
| `MAX_ATTACHMENT_BYTES` | `3145728` | Max decoded size per attachment (3 MB) |
| `SMTP_HOST` | `smtp.gmail.com` | Default SMTP server hostname |
| `SMTP_PORT` | `587` | Default SMTP port (`465` enables `SMTP_SSL` automatically) |
| `SMTP_USE_SSL` | `false` | Force `SMTP_SSL` on non-465 ports |
| `SMTP_USER` | `""` | Default SMTP username |
| `SMTP_PASSWORD` | `""` | Default SMTP password / app password |
| `SMTP_TIMEOUT` | `15` | SMTP connection timeout in seconds |
| `DEFAULT_FROM_EMAIL` | `SMTP_USER` | Default sender email address |
| `DEFAULT_FROM_NAME` | `No-Reply` | Default sender display name |

---

## API Reference

### `GET /health` (or `GET /`)
Returns service status:

```json
{
  "status": "operational",
  "service": "Email Relay Service"
}
```

### `POST /send`

#### Headers
- `X-API-Key` *(required)*: Raw API key for the calling app.
- `X-App-Id` *(optional)*: Tenant identifier in `TENANTS_JSON`.
- `X-Timestamp`, `X-Nonce`, `X-Signature` *(required when `signing_secret` is set or `REQUIRE_HMAC_SIGNATURE=true`)*:
  `X-Signature` is the hex digest of `HMAC-SHA256(signing_secret, f"{timestamp}.{nonce}.{raw_body}")`.

#### Example Request

```bash
curl -X POST http://localhost:3000/send \
  -H "Content-Type: application/json" \
  -H "X-App-Id: billing-app" \
  -H "X-API-Key: er_your_raw_api_key" \
  -d '{
    "to_email": "recipient@example.com",
    "subject": "Invoice Ready",
    "html_content": "<p>Your invoice is attached.</p>",
    "text_content": "Your invoice is attached."
  }'
```

#### Example Response

```json
{
  "status": "sent",
  "request_id": "a1b2c3d4-...",
  "app_id": "billing-app",
  "recipients": ["recipient@example.com"]
}
```

---

## Testing

```bash
pip install -r requirements.txt pytest httpx
pytest
```
