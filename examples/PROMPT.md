# Prompt to Integrate Mailbridge into Another App

Copy and paste the prompt below into your AI coding assistant when working in a calling application (e.g., `molat`):

---

```text
Integrate email sending into this application using our Mailbridge HTTP-to-SMTP relay service.

Configuration (read from environment variables, never hardcode):
- MAILBRIDGE_URL: Base URL of the Mailbridge service (e.g., https://mailbridge-akdey.vercel.app)
- MAILBRIDGE_APP_ID: App identifier for the X-App-Id header (e.g., molat)
- MAILBRIDGE_API_KEY: Secret API key for the X-API-Key header
- MAILBRIDGE_SIGNING_SECRET: Optional HMAC-SHA256 signing secret. When set, sign every POST /send request with:
  - X-Timestamp: current Unix epoch seconds as a string
  - X-Nonce: unique UUID per request
  - X-Signature: hex digest of HMAC-SHA256(MAILBRIDGE_SIGNING_SECRET, f"{timestamp}.{nonce}.{raw_json_body}")

API Contract (POST {MAILBRIDGE_URL}/send):
- Headers:
  - Content-Type: application/json
  - X-API-Key: <MAILBRIDGE_API_KEY>
  - X-App-Id: <MAILBRIDGE_APP_ID> (if set)
  - X-Timestamp, X-Nonce, X-Signature (if MAILBRIDGE_SIGNING_SECRET is set)
- JSON Body:
  - to_email (required): string or array of email strings
  - subject (required): string (1-998 chars)
  - html_content (optional): HTML body string
  - text_content (optional): plain-text body string (at least one of html_content or text_content is required)
  - reply_to (optional): email string
  - cc (optional): array of email strings
  - bcc (optional): array of email strings
  - attachments (optional): array of { "filename": str, "content": base64_str, "content_type": str }
- Success Response (200 OK):
  { "status": "sent", "request_id": "...", "app_id": "...", "recipients": [...] }

Requirements:
1. Create a reusable email client/helper module following this project's conventions and HTTP library.
2. Compute the HMAC signature over the exact raw JSON bytes sent in the HTTP request body.
3. Add the MAILBRIDGE_* variables to this project's .env.example.
4. Handle non-200 responses and network timeouts cleanly with clear error logging (without logging API keys or signing secrets).
5. Add unit tests mocking the HTTP call to verify headers, HMAC signature generation, and error handling.
```
