"""UPI Payment Service - QR generation via Razorpay, rotation, and payment matching.

Updated to use Razorpay dynamic QR codes instead of local QR generation.
Falls back to local QR if Razorpay keys are not configured.
"""

import logging
import io
import qrcode
import base64
import httpx
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.database import (Lead, LeadStatus, PaymentSession, MerchantAccount,
                                  ActiveUPIConfig, UPIRotationLog)
from app.services.razorpay_service import RazorpayService

logger = logging.getLogger(__name__)
settings = get_settings()


class UPIPaymentService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.razorpay = RazorpayService()

    def _is_razorpay_configured(self) -> bool:
        return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)

    # ─── QR Generation ─────────────────────────────────────────────

    def generate_upi_uri(self, upi_id: str, amount: float, ref_id: str) -> str:
        merchant = settings.UPI_MERCHANT_NAME.replace(" ", "")
        return f"upi://pay?pa={upi_id}&pn={merchant}&am={amount:.2f}&cu=INR&tn=Deposit-{ref_id[:8]}"

    def generate_qr_png_bytes(self, uri: str) -> bytes:
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(uri)
        qr.make(fit=True)
        buffer = io.BytesIO()
        qr.make_image(fill_color="black", back_color="white").save(buffer, format="PNG")
        return buffer.getvalue()

    async def get_active_upi(self) -> Optional[MerchantAccount]:
        result = await self.db.execute(select(ActiveUPIConfig).where(ActiveUPIConfig.id == 1))
        config = result.scalar_one_or_none()
        if config:
            acct = await self._get_account(config.active_account_id)
            if acct and acct.is_enabled:
                return acct
        result2 = await self.db.execute(
            select(MerchantAccount).where(MerchantAccount.is_enabled == True)
            .where(MerchantAccount.current_volume_inr < MerchantAccount.daily_cap_inr)
            .order_by(MerchantAccount.id).limit(1))
        return result2.scalar_one_or_none()

    async def create_payment_session(self, lead_id: UUID, amount: float) -> PaymentSession:
        """Create a payment session with QR code.

        Uses Razorpay dynamic QR if configured, falls back to local UPI QR.
        """
        acct = await self.get_active_upi()
        if not acct and not self._is_razorpay_configured():
            raise RuntimeError("No active UPI accounts and Razorpay not configured!")

        ref_id = str(uuid4())
        qr_image_url = ""
        razorpay_qr_id = None

        # Try Razorpay dynamic QR first
        if self._is_razorpay_configured():
            try:
                qr_data = await self.razorpay.create_dynamic_qr(
                    amount_inr=amount,
                    ref_id=ref_id,
                    notes={"lead_id": str(lead_id), "ref_id": ref_id},
                )
                qr_image_url = qr_data.get("qr_image_url", "")
                razorpay_qr_id = qr_data.get("qr_id")
                logger.info(f"Using Razorpay QR: qr_id={razorpay_qr_id}")
            except Exception as e:
                logger.error(f"Razorpay QR creation failed: {e}")
                # Fall back to local QR

        # Fallback: local UPI QR
        if not qr_image_url and acct:
            upi_id = acct.upi_id
            uri = self.generate_upi_uri(upi_id, amount, ref_id)
            qr_bytes = self.generate_qr_png_bytes(uri)
            qr_image_url = f"data:image/png;base64,{base64.b64encode(qr_bytes).decode()}"
            logger.info(f"Using local UPI QR: upi={upi_id}")

        if not qr_image_url:
            raise RuntimeError("Failed to generate QR code - no Razorpay and no UPI accounts")

        session = PaymentSession(
            lead_id=lead_id, amount_inr=amount,
            upi_id=acct.upi_id if acct else "razorpay",
            bank_id=acct.id if acct else "razorpay",
            ref_id=ref_id, status="active",
            qr_image_url=qr_image_url,
            expires_at=datetime.utcnow() + timedelta(minutes=settings.PAYMENT_SESSION_EXPIRY_MINUTES),
        )
        # Store Razorpay QR ID for webhook matching
        if razorpay_qr_id:
            session.razorpay_qr_id = razorpay_qr_id
            session.gateway = "razorpay"
        elif acct:
            session.gateway = "upi"

        self.db.add(session)
        lead = await self._get_lead(lead_id)
        if lead:
            lead.status = LeadStatus.QR_GENERATED
            lead.updated_at = datetime.utcnow()

        # Update merchant volume if using local UPI
        if acct:
            await self.db.execute(
                update(MerchantAccount).where(MerchantAccount.id == acct.id)
                .values(current_volume_inr=MerchantAccount.current_volume_inr + amount))

        await self.db.commit()
        await self.db.refresh(session)
        logger.info(f"Payment session created: ref={ref_id}, amount={amount}, razorpay_qr={razorpay_qr_id}")
        return session

    # ─── Session management ────────────────────────────────────────

    async def mark_expired_sessions(self) -> List[PaymentSession]:
        now = datetime.utcnow()
        result = await self.db.execute(
            select(PaymentSession).where(PaymentSession.status == "active")
            .where(PaymentSession.expires_at < now))
        expired = list(result.scalars().all())
        for s in expired:
            s.status = "expired"
            # Close Razorpay QR if it was used
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
        """Match an incoming payment to an active session."""
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
            lead = await self._get_lead(session.lead_id)
            if lead:
                lead.status = LeadStatus.PAYMENT_RECEIVED
                lead.updated_at = datetime.utcnow()
            await self.db.commit()
            logger.info(f"Payment matched: ref={session.ref_id}, utr={utr}")
            return session
        return None

    async def match_by_ref_id(self, ref_id: str, utr: str, amount: float) -> Optional[PaymentSession]:
        """Match payment by ref_id (more reliable than amount matching)."""
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
        # Fallback to amount matching
        return await self.match_incoming_payment(amount, utr)

    # ─── Rotation ──────────────────────────────────────────────────

    async def rotate_daily(self) -> Dict:
        from sqlalchemy import update as sa_update
        now = datetime.utcnow()
        result = await self.db.execute(
            select(MerchantAccount).where(MerchantAccount.is_enabled == True).order_by(MerchantAccount.id))
        accounts = list(result.scalars().all())
        if not accounts:
            return {"error": "no_accounts"}
        current_result = await self.db.execute(select(ActiveUPIConfig).where(ActiveUPIConfig.id == 1))
        config = current_result.scalar_one_or_none()
        current_id = config.active_account_id if config else None
        next_account = None
        for acct in accounts:
            if acct.id != current_id and acct.current_volume_inr < acct.daily_cap_inr:
                next_account = acct
                break
        if not next_account:
            return {"error": "all_at_capacity"}
        if config:
            old_id = config.active_account_id
            config.active_account_id = next_account.id
            config.rotated_at = now
            config.rotated_by = "cron"
        else:
            old_id = None
            config = ActiveUPIConfig(id=1, active_account_id=next_account.id, rotated_at=now, rotated_by="cron")
            self.db.add(config)
        self.db.add(UPIRotationLog(from_account_id=old_id, to_account_id=next_account.id, reason="daily_cron"))
        await self.db.commit()
        return {"from": old_id, "to": next_account.id, "display_name": next_account.display_name, "upi_id": next_account.upi_id}

    async def manual_rotate(self) -> Dict:
        result = await self.rotate_daily()
        result["rotated_by"] = "manual"
        return result

    # ─── Helpers ───────────────────────────────────────────────────

    async def _get_account(self, account_id: str) -> Optional[MerchantAccount]:
        result = await self.db.execute(select(MerchantAccount).where(MerchantAccount.id == account_id))
        return result.scalar_one_or_none()

    async def _get_lead(self, lead_id: UUID) -> Optional[Lead]:
        result = await self.db.execute(select(Lead).where(Lead.id == lead_id))
        return result.scalar_one_or_none()
