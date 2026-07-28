"""
Pydantic schemas for request/response validation.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from uuid import UUID

from app.models.database import LeadStatus


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
    confirmed_amount: float
    phone: str = ""


class DograhWebhookPayload(BaseModel):
    run_id: int
    workflow_run_id: Optional[int] = None
    workflow_id: Optional[int] = None
    workflow_name: Optional[str] = None
    workflow_run_name: Optional[str] = None
    campaign_id: Optional[int] = None
    call_time: Optional[str] = None
    initial_context: Optional[dict] = None
    gathered_context: Optional[dict] = None
    cost_info: Optional[dict] = None
    annotations: Optional[dict] = None
    recording_url: Optional[str] = None
    transcript_url: Optional[str] = None


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
