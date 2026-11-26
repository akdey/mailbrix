import hashlib
import hmac
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional, Tuple

from fastapi import HTTPException, status

from config import Settings, TenantConfig


@dataclass
class AuthenticatedTenant:
    app_id: str
    config: TenantConfig


class SlidingWindowRateLimiter:
    """Thread-safe in-memory sliding-window rate limiter (60-second window)."""

    def __init__(self, window_seconds: int = 60) -> None:
        self._window = window_seconds
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check_and_record(self, key: str, limit: int) -> Tuple[bool, int]:
        """Return (allowed, retry_after_seconds)."""
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= limit:
                retry_after = max(1, int(self._window - (now - q[0])) + 1)
                return False, retry_after
            q.append(now)
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


class NonceCache:
    """Tracks recently seen HMAC nonces to prevent replay attacks."""

    def __init__(self) -> None:
        self._seen: Dict[str, float] = {}
        self._lock = threading.Lock()

    def check_and_store(self, key: str, ttl_seconds: int) -> bool:
        """Return True if nonce is fresh, False if already used."""
        now = time.time()
        with self._lock:
            expired = [k for k, exp in self._seen.items() if exp <= now]
            for k in expired:
                del self._seen[k]
            if key in self._seen:
                return False
            self._seen[key] = now + ttl_seconds
            return True

    def reset(self) -> None:
        with self._lock:
            self._seen.clear()


rate_limiter = SlidingWindowRateLimiter()
nonce_cache = NonceCache()


def hash_api_key(raw_key: str) -> str:
    """Compute SHA-256 hex digest of an API key."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def authenticate_tenant(
    settings: Settings,
    raw_api_key: Optional[str],
    app_id: Optional[str],
) -> AuthenticatedTenant:
    """Authenticate an incoming request against the configured tenant registry."""
    tenants = settings.get_tenants()
    if not tenants:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Relay authentication is not configured",
        )

    if not raw_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized request",
        )

    incoming_hash = hash_api_key(raw_api_key)

    if app_id:
        tenant = tenants.get(app_id)
        if tenant and hmac.compare_digest(incoming_hash, tenant.key_hash):
            return AuthenticatedTenant(app_id=app_id, config=tenant)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized request",
        )

    # Constant-time scan when X-App-Id is omitted
    matched: Optional[AuthenticatedTenant] = None
    for tid, cfg in tenants.items():
        if hmac.compare_digest(incoming_hash, cfg.key_hash):
            matched = AuthenticatedTenant(app_id=tid, config=cfg)

    if matched is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized request",
        )
    return matched


def verify_hmac_signature(
    tenant: AuthenticatedTenant,
    settings: Settings,
    raw_body: bytes,
    timestamp_header: Optional[str],
    nonce_header: Optional[str],
    signature_header: Optional[str],
) -> None:
    """Verify optional/required HMAC-SHA256 request signature and replay protection."""
    secret = tenant.config.signing_secret
    if not secret:
        if settings.require_hmac_signature:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Request signature required",
            )
        return

    if not timestamp_header or not nonce_header or not signature_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing signature headers",
        )

    try:
        ts = int(timestamp_header)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid timestamp header",
        ) from exc

    now = int(time.time())
    if abs(now - ts) > settings.hmac_tolerance_seconds:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Request timestamp expired",
        )

    nonce_key = f"{tenant.app_id}:{nonce_header}"
    if not nonce_cache.check_and_store(nonce_key, settings.hmac_tolerance_seconds * 2):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Replay detected",
        )

    payload = f"{timestamp_header}.{nonce_header}.".encode("utf-8") + raw_body
    expected_sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature_header.lower(), expected_sig):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid request signature",
        )
