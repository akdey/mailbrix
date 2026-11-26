from typing import List, Optional, Union
from pydantic import BaseModel, EmailStr, Field, model_validator


class EmailAttachment(BaseModel):
    """Base64-encoded file attachment."""

    filename: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1, description="Base64-encoded file content")
    content_type: str = Field(
        default="application/octet-stream",
        description="MIME type, e.g. application/pdf",
    )


class EmailRequest(BaseModel):
    """Payload for sending an email via the relay."""

    to_email: Union[EmailStr, List[EmailStr]]
    subject: str = Field(..., min_length=1, max_length=998)
    html_content: Optional[str] = None
    text_content: Optional[str] = None
    from_name: Optional[str] = None
    reply_to: Optional[EmailStr] = None
    cc: Optional[List[EmailStr]] = None
    bcc: Optional[List[EmailStr]] = None
    attachments: Optional[List[EmailAttachment]] = None

    @model_validator(mode="after")
    def validate_body_present(self) -> "EmailRequest":
        if not self.html_content and not self.text_content:
            raise ValueError("At least one of 'html_content' or 'text_content' must be provided.")
        if isinstance(self.to_email, list) and len(self.to_email) == 0:
            raise ValueError("'to_email' list must contain at least one recipient.")
        return self


class EmailResponse(BaseModel):
    """Response returned after successful email delivery."""

    status: str
    request_id: str
    app_id: str
    recipients: List[str]
