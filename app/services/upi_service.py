"""UPI Payment Service - Razorpay dynamic QR generation only.

All payments go through Razorpay dynamic QR codes. No local UPI, no merchant rotation.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.database import Lead, LeadStatus, PaymentSession
from app.services.razorpay_service import RazorpayService

logger = logging.getLogger(__name__)
settings = get_settings()


class PaymentService:
    """Handles Razorpay payment sessions — QR generation and payment matching.

    Razorpay-only: dynamic QR codes with 15-min expiry, single-use, fixed amount.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.razorpay = RazorpayService()

    # ─── QR Generation (Razorpay only) ──────────────────────────────

    async def create_payment_session(self, lead_id: UUID, amount: float) -> PaymentSession:
        """Create a payment session with Razorpay dynamic QR."""
        if not self.razorpay.is_configured():
            raise RuntimeError("Razorpay not configured — check RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET")

        ref_id = str(uuid4())

        # Create Razorpay dynamic QR
        qr_data = await self.razorpay.create_dynamic_qr(
            amount_inr=amount,
            ref_id=ref_id,
            notes={"lead_id": str(lead_id), "ref_id": ref_id},
        )

        qr_image_url = qr_data.get("qr_image_url", "")
        razorpay_qr_id = qr_data.get("qr_id")

        if not qr_image_url:
            raise RuntimeError("Razorpay QR creation returned no image URL")

        session = PaymentSession(
            lead_id=lead_id,
            amount_inr=amount,
            upi_id="razorpay",
            bank_id="razorpay",
            ref_id=ref_id,
            status="active",
            qr_image_url=qr_image_url,
            razorpay_qr_id=razorpay_qr_id,
            gateway="razorpay",
            expires_at=datetime.utcnow() + timedelta(minutes=settings.PAYMENT_SESSION_EXPIRY_MINUTES),
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        logger.info(f"Razorpay session created: ref={ref_id}, amount=Rs{amount}, qr_id={razorpay_qr_id}")
        return session

    # ─── Session management ────────────────────────────────────────

    async def mark_expired_sessions(self) -> List[PaymentSession]:
        """Mark expired sessions and close Razorpay QRs."""
        now = datetime.utcnow()
        result = await self.db.execute(
            select(PaymentSession).where(PaymentSession.status == "active")
            .where(PaymentSession.expires_at < now))
        expired = list(result.scalars().all())
        for s in expired:
            s.status = "expired"
            if s.razorpay_qr_id:
                try:
                    await self.razorpay.close_qr(s.razorpay_qr_id)
                except Exception as e:
                    logger.warning(f"Failed to close Razorpay QR {s.razorpay_qr_id}: {e}")
        if expired:
            await self.db.commit()
        return expired

    async def match_incoming_payment(self, amount: float, utr: str,
                                      gateway: str = "razorpay") -> Optional[PaymentSession]:
        """Match an incoming payment to an active session by amount."""
        result = await self.db.execute(
            select(PaymentSession).where(PaymentSession.status == "active")
            .where(PaymentSession.amount_inr == amount)
            .where(PaymentSession.expires_at > datetime.utcnow())
            .order_by(PaymentSession.created_at).limit(1))
        session = result.scalar_one_or_none()
        if session:
            session.status = "paid"
            session.paid_at = datetime.utcnow()
            session.utr_number = utr
            session.gateway = gateway
            lead = await self._get_lead(session.lead_id)
            if lead:
                lead.status = LeadStatus.PAYMENT_RECEIVED
                lead.updated_at = datetime.utcnow()
            await self.db.commit()
            logger.info(f"Payment matched: ref={session.ref_id}, utr={utr}")
            return session
        return None

    async def match_by_ref_id(self, ref_id: str, utr: str, amount: float) -> Optional[PaymentSession]:
        """Match payment by ref_id (most reliable)."""
        result = await self.db.execute(
            select(PaymentSession).where(PaymentSession.ref_id == ref_id)
            .where(PaymentSession.status == "active"))
        session = result.scalar_one_or_none()
        if session:
            session.status = "paid"
            session.paid_at = datetime.utcnow()
            session.utr_number = utr
            lead = await self._get_lead(session.lead_id)
            if lead:
                lead.status = LeadStatus.PAYMENT_RECEIVED
                lead.updated_at = datetime.utcnow()
            await self.db.commit()
            logger.info(f"Payment matched by ref_id: ref={ref_id}, utr={utr}")
            return session
        return await self.match_incoming_payment(amount, utr)

    # ─── Helpers ───────────────────────────────────────────────────

    async def _get_lead(self, lead_id: UUID) -> Optional[Lead]:
        result = await self.db.execute(select(Lead).where(Lead.id == lead_id))
        return result.scalar_one_or_none()