#!/usr/bin/env python3
"""Generate an API key, its SHA-256 hash, and an optional HMAC signing secret."""

import hashlib
import json
import re
import secrets
import sys


def main() -> None:
    app_id = sys.argv[1] if len(sys.argv) > 1 else "my-app"
    raw_api_key = f"er_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_api_key.encode("utf-8")).hexdigest()
    signing_secret = secrets.token_hex(32)

    suffix = re.sub(r"[^A-Za-z0-9]+", "_", app_id).strip("_").upper() or "APP"
    env_var_name = f"TENANT_{suffix}"

    tenant_config = {
        "key_hash": key_hash,
        "signing_secret": signing_secret,
        "from_name": app_id,
        "rate_limit_per_min": 60,
    }
    if suffix.lower() != app_id:
        tenant_config = {"app_id": app_id, **tenant_config}

    print("=== Give to calling app (keep secret) ===")
    print(f"X-App-Id:       {app_id}")
    print(f"X-API-Key:      {raw_api_key}")
    print(f"Signing Secret: {signing_secret}")
    print()
    print("=== Add this single env var on Vercel / .env ===")
    print(f"{env_var_name}={json.dumps(tenant_config, separators=(',', ':'))}")


if __name__ == "__main__":
    main()
