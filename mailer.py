import base64
import binascii
import os
import re
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import List

from config import Settings, TenantConfig
from schemas import EmailRequest

BLOCKED_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".com", ".msi", ".scr",
    ".vbs", ".vbe", ".js", ".jse", ".ps1", ".sh", ".dll",
}


def _sanitize_header_value(value: str) -> str:
    """Strip CR/LF characters to prevent email header injection."""
    return value.replace("\r", "").replace("\n", "").strip()


def _sanitize_filename(filename: str) -> str:
    """Restrict attachment filenames to safe characters."""
    base = os.path.basename(_sanitize_header_value(filename))
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    return cleaned or "attachment"


def normalize_recipients(request: EmailRequest) -> tuple[List[str], List[str], List[str]]:
    """Return (to_list, cc_list, all_recipients)."""
    to_list = (
        [str(addr) for addr in request.to_email]
        if isinstance(request.to_email, list)
        else [str(request.to_email)]
    )
    cc_list = [str(addr) for addr in request.cc] if request.cc else []
    bcc_list = [str(addr) for addr in request.bcc] if request.bcc else []
    all_recipients = to_list + cc_list + bcc_list
    return to_list, cc_list, all_recipients


def validate_limits_and_policy(
    request: EmailRequest,
    settings: Settings,
    tenant: TenantConfig,
) -> List[str]:
    """Enforce recipient, domain allowlist, and attachment limits (does not inspect message body)."""
    _, _, all_recipients = normalize_recipients(request)

    if len(all_recipients) > settings.max_recipients:
        raise ValueError(f"Recipient count exceeds limit of {settings.max_recipients}")

    if tenant.allowed_recipient_domains:
        allowed = {d.lower().lstrip("@") for d in tenant.allowed_recipient_domains}
        for addr in all_recipients:
            domain = addr.rsplit("@", 1)[-1].lower()
            if domain not in allowed:
                raise ValueError(f"Recipient domain '{domain}' is not allowed for this app")

    if request.attachments and len(request.attachments) > settings.max_attachments:
        raise ValueError(f"Attachment count exceeds limit of {settings.max_attachments}")

    return all_recipients


def build_mime_message(
    request: EmailRequest,
    from_email: str,
    from_name: str,
    settings: Settings,
) -> MIMEMultipart:
    """Construct a MIME email message from an EmailRequest."""
    to_list, cc_list, _ = normalize_recipients(request)

    body_part = MIMEMultipart("alternative")
    if request.text_content:
        body_part.attach(MIMEText(request.text_content, "plain", "utf-8"))
    if request.html_content:
        body_part.attach(MIMEText(request.html_content, "html", "utf-8"))

    if request.attachments:
        message = MIMEMultipart("mixed")
        message.attach(body_part)

        for att in request.attachments:
            safe_filename = _sanitize_filename(att.filename)
            _, ext = os.path.splitext(safe_filename.lower())
            if ext in BLOCKED_EXTENSIONS:
                raise ValueError(f"Attachment extension '{ext}' is not permitted")

            try:
                file_bytes = base64.b64decode(att.content, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError(f"Invalid base64 content for attachment '{safe_filename}'") from exc

            if len(file_bytes) > settings.max_attachment_bytes:
                raise ValueError(
                    f"Attachment '{safe_filename}' exceeds max size of {settings.max_attachment_bytes} bytes"
                )

            mime_type = att.content_type or "application/octet-stream"
            if "/" in mime_type:
                maintype, subtype = mime_type.split("/", 1)
            else:
                maintype, subtype = "application", "octet-stream"

            part = MIMEBase(_sanitize_header_value(maintype), _sanitize_header_value(subtype))
            part.set_payload(file_bytes)
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="{safe_filename}"',
            )
            message.attach(part)
    else:
        message = body_part

    message["Subject"] = _sanitize_header_value(request.subject)
    message["From"] = formataddr((_sanitize_header_value(from_name), from_email))
    message["To"] = ", ".join(to_list)
    if cc_list:
        message["Cc"] = ", ".join(cc_list)
    if request.reply_to:
        message["Reply-To"] = str(request.reply_to)

    return message


def _open_and_send(
    host: str,
    port: int,
    use_ssl: bool,
    user: str,
    password: str,
    timeout: int,
    from_email: str,
    recipients: List[str],
    raw_message: str,
) -> None:
    if use_ssl or port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=timeout) as server:
            server.login(user, password)
            server.sendmail(from_email, recipients, raw_message)
    else:
        with smtplib.SMTP(host, port, timeout=timeout) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(user, password)
            server.sendmail(from_email, recipients, raw_message)


def send_smtp_message(
    host: str,
    port: int,
    use_ssl: bool,
    user: str,
    password: str,
    timeout: int,
    from_email: str,
    recipients: List[str],
    raw_message: str,
) -> None:
    """Send a serialized MIME message over SMTP (SSL or STARTTLS)."""
    clean_host = host.strip()
    clean_user = user.strip()
    clean_password = password.replace("\r", "").replace("\n", "").strip()

    try:
        _open_and_send(
            clean_host,
            port,
            use_ssl,
            clean_user,
            clean_password,
            timeout,
            from_email,
            recipients,
            raw_message,
        )
    except smtplib.SMTPServerDisconnected:
        _open_and_send(
            clean_host,
            port,
            use_ssl,
            clean_user,
            clean_password,
            timeout,
            from_email,
            recipients,
            raw_message,
        )
