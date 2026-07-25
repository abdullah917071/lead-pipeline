"""
Database models for the lead pipeline state machine.
"""

from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Enum,
    Text, ForeignKey, Index, JSON
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid

Base = declarative_base()


class LeadStatus(PyEnum):
    PENDING_WA_OPTIN = "pending_wa_optin"
    WA_SENT = "wa_sent"
    WA_REPLIED = "wa_replied"
    CALL_TRIGGERED = "call_triggered"
    CALL_COMPLETED = "call_completed"
    CALL_FAILED = "call_failed"
    AMOUNT_CONFIRMED = "amount_confirmed"
    QR_GENERATED = "qr_generated"
    AWAITING_PAYMENT = "awaiting_payment"
    PAYMENT_RECEIVED = "payment_received"
    PAYMENT_VERIFIED = "payment_verified"
    ACCOUNT_CREATED = "account_created"
    CREDENTIALS_DELIVERED = "credentials_delivered"
    COMPLETED = "completed"
    COLD = "cold"
    REJECTED = "rejected"
    PAYMENT_FAILED = "payment_failed"
    MANUAL_REVIEW = "manual_review"


class Lead(Base):
    __tablename__ = "leads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone = Column(String(20), nullable=False, index=True)
    name = Column(String(100), nullable=True)
    source = Column(String(50), default="unknown")
    status = Column(Enum(LeadStatus), default=LeadStatus.PENDING_WA_OPTIN, index=True)
    metadata_json = Column(JSONB, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_contact_at = Column(DateTime, nullable=True)

    sessions = relationship("PaymentSession", back_populates="lead", cascade="all, delete-orphan")
    call_logs = relationship("CallLog", back_populates="lead", cascade="all, delete-orphan")
    wa_messages = relationship("WAMessage", back_populates="lead", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_leads_phone_status", "phone", "status"),
    )


class PaymentSession(Base):
    __tablename__ = "payment_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False)
    amount_inr = Column(Float, nullable=False)
    upi_id = Column(String(100), nullable=False)
    bank_id = Column(String(50), nullable=False)
    ref_id = Column(String(100), unique=True, nullable=False)
    status = Column(String(30), default="active")
    qr_image_url = Column(String(1000), nullable=True)
    razorpay_qr_id = Column(String(100), nullable=True)
    gateway = Column(String(30), default="upi")
    notes = Column(JSONB, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime, nullable=True)
    utr_number = Column(String(50), nullable=True)

    lead = relationship("Lead", back_populates="sessions")

    __table_args__ = (
        Index("ix_payment_sessions_status", "status"),
        Index("ix_payment_sessions_expires", "expires_at"),
    )


class CallLog(Base):
    __tablename__ = "call_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False)
    dograh_run_id = Column(Integer, nullable=True)
    twilio_call_sid = Column(String(50), nullable=True)
    status = Column(String(30), default="initiated")
    duration_seconds = Column(Integer, nullable=True)
    amount_extracted = Column(Float, nullable=True)
    transcript_url = Column(String(500), nullable=True)
    recording_url = Column(String(500), nullable=True)
    raw_webhook = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    lead = relationship("Lead", back_populates="call_logs")


class WAMessage(Base):
    __tablename__ = "wa_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False)
    direction = Column(String(10))
    message_type = Column(String(30))
    wa_message_id = Column(String(100), nullable=True)
    content = Column(Text, nullable=True)
    status = Column(String(20), default="sent")
    created_at = Column(DateTime, default=datetime.utcnow)

    lead = relationship("Lead", back_populates="wa_messages")


class MerchantAccount(Base):
    __tablename__ = "merchant_accounts"

    id = Column(String(50), primary_key=True)
    upi_id = Column(String(100), nullable=False, unique=True)
    display_name = Column(String(100), nullable=False)
    daily_cap_inr = Column(Float, default=100000)
    current_volume_inr = Column(Float, default=0)
    is_active = Column(Boolean, default=False)
    day_of_week = Column(String(10), nullable=True)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ActiveUPIConfig(Base):
    __tablename__ = "active_upi_config"

    id = Column(Integer, primary_key=True, default=1)
    active_account_id = Column(String(50), ForeignKey("merchant_accounts.id"))
    rotated_at = Column(DateTime, default=datetime.utcnow)
    rotated_by = Column(String(20), default="cron")


class UPIRotationLog(Base):
    __tablename__ = "upi_rotation_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_account_id = Column(String(50), nullable=True)
    to_account_id = Column(String(50), nullable=False)
    reason = Column(String(50), default="daily_cron")
    created_at = Column(DateTime, default=datetime.utcnow)


class ProvisionedAccount(Base):
    __tablename__ = "provisioned_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"), unique=True)
    user_id = Column(String(50), unique=True, nullable=False)
    password = Column(String(100), nullable=False)
    initial_balance = Column(Float, nullable=False)
    payment_session_id = Column(UUID(as_uuid=True), ForeignKey("payment_sessions.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    credentials_sent = Column(Boolean, default=False)
    credentials_sent_at = Column(DateTime, nullable=True)


class PipelineSetting(Base):
    """Mutable runtime settings, editable from the admin dashboard.
    Falls back to config.py defaults when a key is absent."""
    __tablename__ = "pipeline_settings"

    key = Column(String(100), primary_key=True)
    value = Column(JSONB, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String(50), nullable=True)
