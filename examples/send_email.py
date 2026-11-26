"""Minimal sample client for calling the Mailbrix email relay service.

Uses only the Python standard library so it can be copied into any project
without extra dependencies.

Usage:
    export MAILBRIX_URL="http://localhost:3000"
    export MAILBRIX_APP_ID="my-app"
    export MAILBRIX_API_KEY="er_your_raw_api_key"
    export MAILBRIX_SIGNING_SECRET="your_hmac_signing_secret"  # optional
    python3 examples/send_email.py
"""

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, List, Optional, Union


class MailbrixClient:
    """HTTP client for sending emails through Mailbrix."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        app_id: Optional[str] = None,
        signing_secret: Optional[str] = None,
        timeout: int = 15,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.app_id = app_id
        self.signing_secret = signing_secret
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "MailbrixClient":
        """Create a client from MAILBRIX_* environment variables."""
        base_url = os.environ["MAILBRIX_URL"]
        api_key = os.environ["MAILBRIX_API_KEY"]
        app_id = os.getenv("MAILBRIX_APP_ID") or None
        signing_secret = os.getenv("MAILBRIX_SIGNING_SECRET") or None
        return cls(
            base_url=base_url,
            api_key=api_key,
            app_id=app_id,
            signing_secret=signing_secret,
        )

    def send_email(
        self,
        to_email: Union[str, List[str]],
        subject: str,
        html_content: Optional[str] = None,
        text_content: Optional[str] = None,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        attachments: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Send an email via POST /send and return the parsed JSON response."""
        payload: Dict[str, Any] = {
            "to_email": to_email,
            "subject": subject,
        }
        if html_content is not None:
            payload["html_content"] = html_content
        if text_content is not None:
            payload["text_content"] = text_content
        if from_name is not None:
            payload["from_name"] = from_name
        if reply_to is not None:
            payload["reply_to"] = reply_to
        if cc is not None:
            payload["cc"] = cc
        if bcc is not None:
            payload["bcc"] = bcc
        if attachments is not None:
            payload["attachments"] = attachments

        raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
        }
        if self.app_id:
            headers["X-App-Id"] = self.app_id

        if self.signing_secret:
            timestamp = str(int(time.time()))
            nonce = str(uuid.uuid4())
            signed_payload = f"{timestamp}.{nonce}.".encode("utf-8") + raw_body
            signature = hmac.new(
                self.signing_secret.encode("utf-8"),
                signed_payload,
                hashlib.sha256,
            ).hexdigest()
            headers["X-Timestamp"] = timestamp
            headers["X-Nonce"] = nonce
            headers["X-Signature"] = signature

        req = urllib.request.Request(
            url=f"{self.base_url}/send",
            data=raw_body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Mailbrix error {exc.code}: {detail}") from exc


def main() -> None:
    client = MailbrixClient.from_env()
    recipient = os.getenv("TEST_TO_EMAIL", "recipient@example.com")

    attachment_bytes = b"Hello from Mailbrix sample client!\n"
    result = client.send_email(
        to_email=recipient,
        subject="Hello from Mailbrix",
        html_content="<h1>Hello</h1><p>Sent via Mailbrix.</p>",
        text_content="Hello\nSent via Mailbrix.",
        attachments=[
            {
                "filename": "hello.txt",
                "content": base64.b64encode(attachment_bytes).decode("utf-8"),
                "content_type": "text/plain",
            }
        ],
    )
    print("Email sent:", json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
