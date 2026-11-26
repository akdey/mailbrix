---
name: mailbridge
description: Integrates transactional email sending into any application using the Mailbridge HTTP-to-SMTP relay service (API key auth, optional HMAC-SHA256 signing, attachments, and error handling).
---

# Mailbridge Email Integration

Use this skill when adding transactional email sending to an application via Mailbridge (`https://mailbridge-akdey.vercel.app`).

## 1. Environment Variables

Never hardcode credentials. Read these from environment variables and document them in `.env.example`:

- `MAILBRIDGE_URL`: Base URL of the Mailbridge relay (e.g., `https://mailbridge-akdey.vercel.app`)
- `MAILBRIDGE_APP_ID`: Tenant identifier sent in `X-App-Id` (e.g., `my-app`)
- `MAILBRIDGE_API_KEY`: Secret API key sent in `X-API-Key` (`er_...`)
- `MAILBRIDGE_SIGNING_SECRET`: *(Optional)* 64-char hex HMAC-SHA256 secret for request signing

## 2. API Contract (`POST {MAILBRIDGE_URL}/send`)

### Headers
- `Content-Type: application/json`
- `X-API-Key: <MAILBRIDGE_API_KEY>`
- `X-App-Id: <MAILBRIDGE_APP_ID>` *(when set)*
- **When `MAILBRIDGE_SIGNING_SECRET` is set**, also include:
  - `X-Timestamp`: current Unix epoch seconds as a string
  - `X-Nonce`: unique UUID per request
  - `X-Signature`: hex digest of `HMAC-SHA256(MAILBRIDGE_SIGNING_SECRET, f"{timestamp}.{nonce}.{raw_json_body}")`

> **Important:** Compute `X-Signature` over the **exact raw JSON bytes** transmitted in the HTTP request body.

### JSON Body
- `to_email` *(required)*: single email string or array of email strings
- `subject` *(required)*: string (`1–998` chars)
- `html_content` *(optional)*: HTML email body
- `text_content` *(optional)*: plain-text email body *(at least one of `html_content` or `text_content` is required)*
- `reply_to` *(optional)*: reply-to email address
- `cc`, `bcc` *(optional)*: array of email strings
- `attachments` *(optional)*: array of `{ "filename": str, "content": base64_str, "content_type": str }`

### Response (`200 OK`)
```json
{
  "status": "sent",
  "request_id": "...",
  "app_id": "...",
  "recipients": ["..."]
}
```

## 3. Implementation Requirements

1. Create a reusable email client/helper module matching the host project's language and HTTP client.
2. Handle non-200 responses and network timeouts cleanly with clear error logging—never log `MAILBRIDGE_API_KEY` or `MAILBRIDGE_SIGNING_SECRET`.
3. Add unit tests mocking the HTTP layer to verify request headers, HMAC signature generation, and error handling.
