"""Pydantic schemas for request/response validation.

Updated to handle Dograh webhook payloads where initial_context and
gathered_context may arrive as JSON-encoded strings (Dograh's template
engine renders them as stringified JSON).
"""

from datetime import datetime
from typing import Optional, List, Union, Any
from pydantic import BaseModel, field_validator
import json
from uuid import UUID

from app.models.database import LeadStatus


def _parse_json_field(v: Any) -> Optional[dict]:
    """Parse a field that may be a dict, JSON string, or None."""
    if v is None:
        return None
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        try:
            return json.loads(v)
        except (json.JSONDecodeError, TypeError):
            return None
    return None


class IncomingLead(BaseModel):
    name: Optional[str] = ""
    phone: str
    source: str = "unknown"
    utm_campaign: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_source: Optional[str] = None


class MidCallAmountConfirmed(BaseModel):
    """Payload from Dograh mid-call webhook node when amount is confirmed during the call."""
    run_id: int
    lead_id: str
    confirmed_amount: Optional[float] = None
    phone: str = ""

    @field_validator("confirmed_amount", mode="before")
    @classmethod
    def parse_confirmed_amount(cls, v: Any) -> Optional[float]:
        """Handle empty string or missing confirmed_amount."""
        if v is None or v == "" or v == "null":
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None


class DograhWebhookPayload(BaseModel):
    """Payload from Dograh post-call webhook.

    Fields may arrive as dicts or JSON-encoded strings (Dograh template
    engine renders them as strings).
    """
    run_id: int
    workflow_run_id: Optional[int] = None
    workflow_id: Optional[int] = None
    workflow_name: Optional[str] = None
    workflow_run_name: Optional[str] = None
    campaign_id: Optional[int] = None
    call_time: Optional[str] = None
    initial_context: Optional[Union[dict, str]] = None
    gathered_context: Optional[Union[dict, str]] = None
    cost_info: Optional[dict] = None
    annotations: Optional[dict] = None
    recording_url: Optional[str] = None
    transcript_url: Optional[str] = None

    @field_validator("initial_context", "gathered_context", mode="before")
    @classmethod
    def parse_json_fields(cls, v: Any) -> Any:
        return _parse_json_field(v) or v


class LeadResponse(BaseModel):
    id: UUID
    phone: str
    name: Optional[str]
    status: LeadStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PaymentSessionResponse(BaseModel):
    id: UUID
    lead_id: UUID
    amount_inr: float
    upi_id: str
    ref_id: str
    status: str
    qr_image_url: Optional[str]
    expires_at: datetime

    class Config:
        from_attributes = True


class DashboardStats(BaseModel):
    total_leads: int
    pending_optin: int
    calls_today: int
    payments_today: int
    completed_today: int
    active_upi: str
    active_bank: str
    pipeline_value: float


class PaymentSuccessRequest(BaseModel):
    ref_id: str
    utr: str
    amount: float
    sender_upi: Optional[str] = ""
    gateway: str = "razorpay"