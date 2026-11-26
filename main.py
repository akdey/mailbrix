import asyncio
import logging
import uuid
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import ValidationError

from config import Settings, get_settings
from mailer import build_mime_message, send_smtp_message, validate_limits_and_policy
from schemas import EmailRequest, EmailResponse
from security import authenticate_tenant, rate_limiter, verify_hmac_signature

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("email-relay")

_settings = get_settings()
_is_prod = _settings.env.lower() == "production"

app = FastAPI(
    title=_settings.app_name,
    description="Generic multi-app HTTP-to-SMTP email relay microservice.",
    version="2.0.0",
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)


@app.middleware("http")
async def security_and_size_middleware(request: Request, call_next):
    """Attach security headers, request ID, and enforce max request body size."""
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id

    settings = get_settings()
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > settings.max_request_bytes:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={"detail": "Request payload too large"},
                )
        except ValueError:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": "Invalid Content-Length header"},
            )

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store"
    return response


_INDEX_HTML_PATH = Path(__file__).resolve().parent / "static" / "index.html"


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index_page():
    """Serve the Mailbridge documentation and integration landing page."""
    return HTMLResponse(content=_INDEX_HTML_PATH.read_text(encoding="utf-8"))


@app.get("/health")
def health_check(settings: Settings = Depends(get_settings)):
    """Health check endpoint."""
    return {"status": "operational", "service": settings.app_name}


@app.post("/send", response_model=EmailResponse)
async def send_email(
    raw_request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    x_app_id: Optional[str] = Header(default=None, alias="X-App-Id"),
    x_timestamp: Optional[str] = Header(default=None, alias="X-Timestamp"),
    x_nonce: Optional[str] = Header(default=None, alias="X-Nonce"),
    x_signature: Optional[str] = Header(default=None, alias="X-Signature"),
    settings: Settings = Depends(get_settings),
):
    """Authenticate tenant, enforce limits, and relay email over SMTP."""
    request_id = getattr(raw_request.state, "request_id", str(uuid.uuid4()))

    # 1. Per-IP rate limit
    client_ip = raw_request.client.host if raw_request.client else "unknown"
    ip_allowed, ip_retry = rate_limiter.check_and_record(
        f"ip:{client_ip}", settings.ip_rate_limit_per_min
    )
    if not ip_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(ip_retry)},
        )

    # 2. Authenticate tenant (hashed API key + optional X-App-Id)
    tenant = authenticate_tenant(settings, raw_api_key=x_api_key, app_id=x_app_id)

    # 3. Per-tenant rate limit
    tenant_allowed, tenant_retry = rate_limiter.check_and_record(
        f"tenant:{tenant.app_id}", tenant.config.rate_limit_per_min
    )
    if not tenant_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="App rate limit exceeded",
            headers={"Retry-After": str(tenant_retry)},
        )

    # 4. Read raw body with size guard (covers chunked transfers without Content-Length)
    raw_body = await raw_request.body()
    if len(raw_body) > settings.max_request_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Request payload too large",
        )

    # 5. Verify optional/required HMAC signature & replay protection
    verify_hmac_signature(
        tenant=tenant,
        settings=settings,
        raw_body=raw_body,
        timestamp_header=x_timestamp,
        nonce_header=x_nonce,
        signature_header=x_signature,
    )

    # 6. Parse & validate request payload
    try:
        email_req = EmailRequest.model_validate_json(raw_body)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc

    # 7. Resolve SMTP credentials & sender identity
    smtp_host = tenant.config.smtp_host or settings.smtp_host
    smtp_port = tenant.config.smtp_port or settings.smtp_port
    smtp_use_ssl = (
        tenant.config.smtp_use_ssl
        if tenant.config.smtp_use_ssl is not None
        else settings.smtp_use_ssl
    )
    smtp_user = tenant.config.smtp_user or settings.smtp_user
    smtp_password = tenant.config.smtp_password or settings.smtp_password

    if not smtp_user or not smtp_password:
        logger.error("Missing SMTP credentials request_id=%s app_id=%s", request_id, tenant.app_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SMTP credentials are not configured",
        )

    from_email = tenant.config.from_email or settings.default_from_email or smtp_user
    if tenant.config.allow_custom_from_name and email_req.from_name:
        from_name = email_req.from_name
    else:
        from_name = tenant.config.from_name or settings.default_from_name

    # 8. Enforce recipient/attachment limits and build MIME message
    try:
        all_recipients = validate_limits_and_policy(email_req, settings, tenant.config)
        message = build_mime_message(
            email_req,
            from_email=from_email,
            from_name=from_name,
            settings=settings,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # 9. Deliver over SMTP without leaking internal errors
    try:
        await asyncio.to_thread(
            send_smtp_message,
            smtp_host,
            smtp_port,
            smtp_use_ssl,
            smtp_user,
            smtp_password,
            settings.smtp_timeout,
            from_email,
            all_recipients,
            message.as_string(),
        )
    except Exception:
        logger.exception(
            "SMTP delivery failed request_id=%s app_id=%s recipient_count=%d",
            request_id,
            tenant.app_id,
            len(all_recipients),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Email delivery failed",
        )

    logger.info(
        "Email delivered request_id=%s app_id=%s recipient_count=%d",
        request_id,
        tenant.app_id,
        len(all_recipients),
    )
    return EmailResponse(
        status="sent",
        request_id=request_id,
        app_id=tenant.app_id,
        recipients=all_recipients,
    )
