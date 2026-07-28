"""Lead Service - state machine orchestration."""

import logging
from datetime import datetime, timedelta
from typing import Optional, List
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Lead, LeadStatus, CallLog, PaymentSession
from app.schemas import IncomingLead

logger = logging.getLogger(__name__)


def normalize_phone(phone: str) -> str:
    """Normalize phone to Meta's WhatsApp format: digits only, no '+'.

    Incoming WhatsApp webhooks send '919235587822' while leads may be
    stored with a '+' prefix ('+919****7822'). Both must match for
    lookups to succeed.

    Also ensures 10-digit India numbers get the 91 country code prefix
    so they match what Meta sends in webhooks.
    """
    if not phone:
        return phone
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    if len(digits) == 10:
        digits = f"91{digits}"
    return digits


class LeadService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def ingest(self, data: IncomingLead) -> Lead:
        """Ingest a new lead. Dedup by phone number."""
        norm = normalize_phone(data.phone)
        existing = await self.db.execute(
            select(Lead).where(Lead.phone == norm)
        )
        lead = existing.scalar_one_or_none()
        if lead:
            if lead.status == LeadStatus.COMPLETED:
                logger.info(f"Lead {data.phone} already converted - skipping")
                return lead
            logger.info(f"Lead {data.phone} exists at status {lead.status} - re-engaging")
            return lead

        lead = Lead(
            phone=norm,
            name=data.name or "",
            source=data.source,
            status=LeadStatus.PENDING_WA_OPTIN,
            metadata_json={
                "utm_campaign": data.utm_campaign,
                "utm_medium": data.utm_medium,
                "utm_source": data.utm_source,
            },
        )
        self.db.add(lead)
        await self.db.commit()
        await self.db.refresh(lead)
        logger.info(f"New lead ingested: {lead.id} ({data.phone})")
        return lead

    async def advance(self, lead_id: UUID, new_status: LeadStatus) -> Lead:
        """Advance a lead's status."""
        lead = await self._get(lead_id)
        if not lead:
            raise ValueError(f"Lead {lead_id} not found")
        lead.status = new_status
        lead.updated_at = datetime.utcnow()
        lead.last_contact_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(lead)
        logger.info(f"Lead {lead_id} -> {new_status.value}")
        return lead

    async def mark_cold(self, lead_id: UUID) -> Lead:
        return await self.advance(lead_id, LeadStatus.COLD)

    async def mark_rejected(self, lead_id: UUID) -> Lead:
        return await self.advance(lead_id, LeadStatus.REJECTED)

    async def _get(self, lead_id: UUID) -> Optional[Lead]:
        result = await self.db.execute(select(Lead).where(Lead.id == lead_id))
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str) -> Optional[Lead]:
        norm = normalize_phone(phone)
        result = await self.db.execute(select(Lead).where(Lead.phone == norm))
        return result.scalar_one_or_none()

    async def get_pending_sessions(self) -> List[PaymentSession]:
        now = datetime.utcnow()
        result = await self.db.execute(
            select(PaymentSession)
            .where(PaymentSession.status == "active")
            .where(PaymentSession.expires_at > now)
        )
        return list(result.scalars().all())

    async def get_leads_by_status(self, status: LeadStatus, limit: int = 100) -> List[Lead]:
        result = await self.db.execute(
            select(Lead).where(Lead.status == status).limit(limit)
        )
        return list(result.scalars().all())
