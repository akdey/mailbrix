import base64
import hashlib
import hmac
import json
import time
from unittest.mock import patch

from fastapi.testclient import TestClient

from config import Settings, get_settings
from main import app
from security import hash_api_key, nonce_cache, rate_limiter

APP1_KEY = "er_app1_secret_key"
APP2_KEY = "er_app2_secret_key"
APP2_HMAC_SECRET = "super-secret-hmac-key"


def get_test_settings() -> Settings:
    tenants = {
        "app-1": {
            "key_hash": hash_api_key(APP1_KEY),
            "from_name": "App One",
            "from_email": "app1@example.com",
            "rate_limit_per_min": 3,
        },
        "app-2": {
            "key_hash": hash_api_key(APP2_KEY),
            "signing_secret": APP2_HMAC_SECRET,
            "from_name": "App Two",
            "allowed_recipient_domains": ["trusted.com"],
            "rate_limit_per_min": 10,
        },
    }
    return Settings(
        env="development",
        tenants_json=json.dumps(tenants),
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="sender@example.com",
        smtp_password="app-password",
        default_from_email="noreply@example.com",
        default_from_name="Default App",
    )


app.dependency_overrides[get_settings] = get_test_settings
client = TestClient(app)


def setup_function():
    rate_limiter.reset()
    nonce_cache.reset()


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "operational"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_index_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Mailbridge" in response.text


def test_send_unauthorized():
    response = client.post(
        "/send",
        json={"to_email": "user@example.com", "subject": "Test", "html_content": "<p>Hi</p>"},
    )
    assert response.status_code == 401


def test_multi_tenant_send_success():
    encoded = base64.b64encode(b"hello world").decode("utf-8")
    with patch("main.send_smtp_message") as mock_smtp:
        response = client.post(
            "/send",
            headers={"X-App-Id": "app-1", "X-API-Key": APP1_KEY},
            json={
                "to_email": ["user1@example.com"],
                "subject": "Welcome",
                "html_content": "<p>Welcome!</p>",
                "attachments": [
                    {"filename": "hello.txt", "content": encoded, "content_type": "text/plain"}
                ],
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "sent"
    assert body["app_id"] == "app-1"
    mock_smtp.assert_called_once()


def test_hmac_signing_and_replay_protection():
    payload = json.dumps({
        "to_email": "user@trusted.com",
        "subject": "Signed",
        "text_content": "Hello",
    }).encode("utf-8")
    ts = str(int(time.time()))
    nonce = "unique-nonce-123"
    sig = hmac.new(
        APP2_HMAC_SECRET.encode("utf-8"),
        f"{ts}.{nonce}.".encode("utf-8") + payload,
        hashlib.sha256,
    ).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-App-Id": "app-2",
        "X-API-Key": APP2_KEY,
        "X-Timestamp": ts,
        "X-Nonce": nonce,
        "X-Signature": sig,
    }

    with patch("main.send_smtp_message"):
        first = client.post("/send", headers=headers, content=payload)
        assert first.status_code == 200

        # Replaying the exact same signed request must be rejected
        replay = client.post("/send", headers=headers, content=payload)
        assert replay.status_code == 401


def test_blocked_executable_attachment():
    encoded = base64.b64encode(b"MZ").decode("utf-8")
    response = client.post(
        "/send",
        headers={"X-App-Id": "app-1", "X-API-Key": APP1_KEY},
        json={
            "to_email": "user@example.com",
            "subject": "Bad file",
            "text_content": "See attached",
            "attachments": [{"filename": "malware.exe", "content": encoded}],
        },
    )
    assert response.status_code == 400


def test_rate_limit_enforced():
    with patch("main.send_smtp_message"):
        for _ in range(3):
            ok = client.post(
                "/send",
                headers={"X-App-Id": "app-1", "X-API-Key": APP1_KEY},
                json={"to_email": "user@example.com", "subject": "Hi", "text_content": "Hi"},
            )
            assert ok.status_code == 200

        limited = client.post(
            "/send",
            headers={"X-App-Id": "app-1", "X-API-Key": APP1_KEY},
            json={"to_email": "user@example.com", "subject": "Hi", "text_content": "Hi"},
        )
        assert limited.status_code == 429
        assert "Retry-After" in limited.headers


def test_smtp_error_is_sanitized():
    with patch("main.send_smtp_message", side_effect=RuntimeError("internal-smtp-host.local:587 auth failed")):
        response = client.post(
            "/send",
            headers={"X-App-Id": "app-1", "X-API-Key": APP1_KEY},
            json={"to_email": "user@example.com", "subject": "Hi", "text_content": "Hi"},
        )
    assert response.status_code == 502
    assert response.json()["detail"] == "Email delivery failed"


def test_tenant_prefix_env_discovery(monkeypatch):
    molat_key = "er_molat_secret_key"
    billing_key = "er_billing_secret_key"
    monkeypatch.setenv(
        "TENANT_MOLAT",
        json.dumps({"key_hash": hash_api_key(molat_key), "from_name": "Molat"}),
    )
    monkeypatch.setenv(
        "TENANT_BILLING_APP",
        json.dumps({
            "app_id": "billing-app",
            "key_hash": hash_api_key(billing_key),
            "from_name": "Billing",
        }),
    )

    tenants = Settings().get_tenants()
    assert "molat" in tenants
    assert tenants["molat"].from_name == "Molat"
    assert "billing-app" in tenants
    assert tenants["billing-app"].from_name == "Billing"
