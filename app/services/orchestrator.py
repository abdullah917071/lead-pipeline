"""Pipeline Orchestrator - the central state machine.

Flow:
1. Lead from Meta ad -> send WhatsApp opt-in (image + text + "Interested" button)
2. User clicks "Interested" -> send "you'll receive a call" message -> trigger Dograh voice call
3. AI call: introduce product, sell cricket betting ID (min Rs 5), confirm amount
4. On amount confirmed -> create Razorpay dynamic QR -> send QR image on WhatsApp
5. Payment confirmed (Razorpay webhook) -> provision account -> send demo credentials instantly
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Lead, LeadStatus, PaymentSession, ProvisionedAccount, CallLog
from app.schemas import IncomingLead, DograhWebhookPayload, MidCallAmountConfirmed
from app.services.lead_service import LeadService
from app.services.whatsapp_service import WhatsAppService
from app.services.dograh_service import DograhService
from app.services.upi_service import PaymentService
from app.services.provisioning_service import ProvisioningService
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class PipelineOrchestrator:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.leads = LeadService(db)
        self.wa = WhatsAppService()
        self.dograh = DograhService(db)
        self.payments = PaymentService(db)
        self.prov = ProvisioningService(db)

    # ─── Step 1: New lead from Meta ad ─────────────────────────────

    async def handle_new_lead(self, data: IncomingLead) -> Lead:
        """New lead from Meta ad -> instantly send WhatsApp opt-in with image + Interested button."""
        lead = await self.leads.ingest(data)
        if lead.status == LeadStatus.COMPLETED:
            return lead
        try:
            await self.wa.send_optin_message(lead.phone, lead.name or "there")
            lead = await self.leads.advance(lead.id, LeadStatus.WA_SENT)
            logger.info(f"Opt-in message sent to {lead.phone}")
        except Exception as e:
            logger.error(f"WhatsApp opt-in failed for {lead.phone}: {e}")
        return lead

    # ─── Step 2: User clicks "Interested" button ───────────────────

    async def handle_wa_reply(self, phone: str, message_text: str) -> Optional[Lead]:
        """Handle WhatsApp reply / button click.

        If user clicked 'Interested' button or said yes:
          1. Send "you'll receive a call" message
          2. Trigger Dograh voice call
        """
        lead = await self.leads.get_by_phone(phone)
        if not lead:
            return None
        if lead.status not in (LeadStatus.WA_SENT, LeadStatus.PENDING_WA_OPTIN,
                                 LeadStatus.CALL_FAILED, LeadStatus.CALL_TRIGGERED,
                                 LeadStatus.WA_REPLIED):
            return lead

        intent = self._classify_intent(message_text)
        if intent == "interested":
            # Step 2a: Tell user they'll get a call
            try:
                await self.wa.send_call_incoming_notice(lead.phone, lead.name or "")
            except Exception as e:
                logger.error(f"Failed to send call notice to {lead.phone}: {e}")

            # Step 2b: Trigger voice call FIRST, THEN advance status
            try:
                await self.dograh.trigger_outbound_call(
                    lead_id=lead.id, phone=lead.phone, name=lead.name or "")
                # trigger_outbound_call advances to CALL_TRIGGERED internally
            except Exception as e:
                # Never swallow — record the failure as a call log so it is
                # visible (calls=0 with no trace was a blind spot).
                logger.error(f"Dograh call trigger FAILED for {lead.id}: {e}")
                await self.dograh.record_trigger_failure(
                    lead_id=lead.id, phone=lead.phone, error=str(e)[:500])
                lead = await self.leads.advance(lead.id, LeadStatus.CALL_FAILED)
            return lead

        elif intent == "not_interested":
            await self.wa.send_rejection_ack(lead.phone)
            return await self.leads.mark_rejected(lead.id)
        else:
            await self.wa.send_text(lead.phone,
                "I want to make sure I understand. Would you like a call to set up your account? Reply YES or NO.")
            return lead

    def _classify_intent(self, text: str) -> str:
        """Classify message intent. Handles both button IDs and free text."""
        t = text.strip().lower()
        # Button click: "interested" button ID
        if t == "interested" or t == "yes_call":
            return "interested"
        yes_p = ["yes", "yeah", "call", "sure", "ok", "interested", "activate", "haan", "ha", "ji",
                 "interested_button", "call me"]
        no_p = ["no", "nahi", "na", "not", "don't", "stop", "cancel", "skip"]
        for p in yes_p:
            if p in t:
                return "interested"
        for p in no_p:
            if p in t:
                return "not_interested"
        return "unclear"

    # ─── Step 3: Call completed -> extract amount ──────────────────

    async def _has_unpaid_qr(self, lead: Lead) -> bool:
        """Check if the lead already has an active/unpaid QR sent (mid-call generated it)."""
        result = await self.db.execute(
            select(PaymentSession).where(PaymentSession.lead_id == lead.id)
            .where(PaymentSession.status == "active")
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def handle_call_completed(self, payload: DograhWebhookPayload) -> Optional[Lead]:
        """Dograh call completed. Extract confirmed amount and generate QR.

        If the QR was already generated mid-call (via handle_midcall_amount_confirmed),
        skip duplicate QR generation but still advance the lead status.
        """
        # Check for existing payment sessions BEFORE processing the webhook
        # (process_call_webhook changes the lead status, which would break dedup)
        lead = await self.dograh._get_lead_from_initial_context(payload.initial_context)
        if lead:
            existing_qr = await self._has_unpaid_qr(lead)
            if existing_qr:
                logger.info(f"Lead {lead.id} already has active QR — skipping post-call QR generation")
                # Still process the webhook to update call logs
                lead = await self.dograh.process_call_webhook(payload)
                return lead

        lead = await self.dograh.process_call_webhook(payload)
        if not lead:
            return None

        # If QR was already generated mid-call, skip duplicate
        if lead.status in (LeadStatus.AWAITING_PAYMENT, LeadStatus.QR_GENERATED):
            logger.info(f"Lead {lead.id} already has QR generated mid-call — skipping post-call QR")
            return lead

        gathered = payload.gathered_context or {}
        # Handle stringified JSON from Dograh's template engine
        if isinstance(gathered, str):
            import json
            try:
                gathered = json.loads(gathered)
            except (json.JSONDecodeError, TypeError):
                gathered = {}
        amount = gathered.get("confirmed_amount")

        # Validate amount against config (min Rs 5)
        min_amt = settings.MIN_AMOUNT_INR
        max_amt = settings.MAX_AMOUNT_INR

        if amount and min_amt <= float(amount) <= max_amt:
            lead = await self.leads.advance(lead.id, LeadStatus.AMOUNT_CONFIRMED)
            return await self._generate_and_send_qr(lead, float(amount))
        else:
            await self.wa.send_text(lead.phone,
                f"Great talking to you! How much would you like to deposit? "
                f"Minimum Rs {int(min_amt)}. Just reply with the amount (e.g. 500) and I'll send you the payment QR on WhatsApp.")
            return lead

    # ─── Step 3a: Mid-call amount confirmation (from Dograh webhook node) ──

    async def handle_midcall_amount_confirmed(self, lead_id_str: str, amount: float,
                                               dograh_run_id: int) -> Optional[Lead]:
        """Handle mid-call amount confirmation from Dograh's webhook node.

        Dograh fires this webhook node when the AI confirms the amount DURING the call.
        We generate the Razorpay QR and send it on WhatsApp immediately,
        so the AI can truthfully tell the customer to check WhatsApp.
        """
        from uuid import UUID
        try:
            lead_id = UUID(lead_id_str)
        except ValueError:
            logger.error(f"Invalid lead_id in mid-call webhook: {lead_id_str}")
            return None

        lead = await self.leads._get(lead_id)
        if not lead:
            logger.error(f"Lead {lead_id} not found for mid-call webhook")
            return None

        # Dedup: if QR already generated for this lead, skip
        if lead.status in (LeadStatus.AWAITING_PAYMENT, LeadStatus.QR_GENERATED):
            logger.info(f"Lead {lead.id} already has QR — skipping mid-call duplicate")
            return lead

        if lead.status in (LeadStatus.CALL_TRIGGERED, LeadStatus.CALL_COMPLETED,
                            LeadStatus.AMOUNT_CONFIRMED, LeadStatus.WA_REPLIED):
            pass  # Valid states to proceed
        else:
            logger.warning(f"Lead {lead.id} in unexpected state {lead.status} for mid-call QR — proceeding anyway")

        # Validate amount
        min_amt = settings.MIN_AMOUNT_INR
        max_amt = settings.MAX_AMOUNT_INR
        if not (min_amt <= float(amount) <= max_amt):
            logger.warning(f"Mid-call amount Rs{amount} out of range for lead {lead.id} — skipping")
            return lead

        # Advance to amount_confirmed then generate QR
        lead = await self.leads.advance(lead.id, LeadStatus.AMOUNT_CONFIRMED)
        lead = await self._generate_and_send_qr(lead, float(amount))
        logger.info(f"Mid-call QR generated and sent to {lead.phone}: Rs {amount}")
        return lead

    # ─── Step 3b: User replies with amount via WhatsApp ────────────

    async def handle_wa_amount_reply(self, phone: str, amount_text: str) -> Optional[Lead]:
        lead = await self.leads.get_by_phone(phone)
        if not lead or lead.status != LeadStatus.AMOUNT_CONFIRMED:
            return lead
        try:
            amount = float(amount_text.replace(",", "").replace("Rs", "").replace("rs", "").strip())
            min_amt = settings.MIN_AMOUNT_INR
            max_amt = settings.MAX_AMOUNT_INR
            if not (min_amt <= amount <= max_amt):
                raise ValueError(f"Amount out of range (min Rs {int(min_amt)}, max Rs {int(max_amt)})")
        except ValueError:
            await self.wa.send_text(phone,
                f"Please enter a valid amount. Minimum Rs {int(settings.MIN_AMOUNT_INR)}, "
                f"maximum Rs {int(settings.MAX_AMOUNT_INR)}.")
            return lead
        return await self._generate_and_send_qr(lead, amount)

    # ─── Step 4: Generate Razorpay dynamic QR and send on WhatsApp ─

    async def _generate_and_send_qr(self, lead: Lead, amount: float) -> Lead:
        """Create Razorpay dynamic QR and send QR image to user on WhatsApp."""
        session = await self.payments.create_payment_session(lead.id, amount)
        lead = await self.leads.advance(lead.id, LeadStatus.AWAITING_PAYMENT)
        await self.wa.send_qr_payment(lead.phone, amount, session.qr_image_url)
        logger.info(f"QR sent to {lead.phone}: Rs {amount}, gateway={session.gateway}")
        return lead

    # ─── Step 5: Payment confirmed -> provision + send credentials ─

    async def handle_payment_success(self, ref_id: str, utr: str, amount: float,
                                      gateway: str = "razorpay") -> Optional[Lead]:
        """Payment confirmed via Razorpay webhook -> instantly provision and send credentials."""
        # Try ref_id matching first (most reliable)
        if ref_id:
            session = await self.payments.match_by_ref_id(ref_id, utr, amount)
        else:
            session = await self.payments.match_incoming_payment(amount, utr, gateway=gateway)

        if not session:
            logger.error(f"Payment match failed: ref={ref_id}, utr={utr}, amount={amount}")
            return None

        lead = await self.leads.advance(session.lead_id, LeadStatus.PAYMENT_VERIFIED)

        # Send payment received confirmation
        await self.wa.send_payment_success(lead.phone)

        # Provision account and send credentials instantly
        try:
            provisioned = await self.prov.provision_account(
                lead_id=lead.id, phone=lead.phone, amount=session.amount_inr,
                payment_session_id=session.id)
            await self.wa.send_credentials(
                lead.phone, provisioned.user_id, provisioned.password, provisioned.initial_balance)
            await self.prov.mark_credentials_sent(provisioned.id)
            logger.info(f"Pipeline COMPLETE for lead {lead.id} — credentials delivered instantly")
        except Exception as e:
            logger.error(f"Provisioning failed for lead {lead.id}: {e}")
            await self.wa.send_text(lead.phone,
                "Payment received! Our team is setting up your account. You'll receive your login details shortly.")
        return lead

    # ─── Background tasks ──────────────────────────────────────────

    async def handle_expired_sessions(self):
        expired = await self.payments.mark_expired_sessions()
        for session in expired:
            lead = await self.leads._get(session.lead_id)
            if lead and lead.status == LeadStatus.AWAITING_PAYMENT:
                new_session = await self.payments.create_payment_session(lead.id, session.amount_inr)
                await self.wa.send_text(lead.phone, f"Previous QR expired. Fresh QR for Rs {int(session.amount_inr)}:")
                await self.wa.send_qr_payment(lead.phone, session.amount_inr, new_session.qr_image_url)

    async def handle_followup_timers(self):
        cutoff_12h = datetime.utcnow() - timedelta(hours=12)
        cutoff_24h = datetime.utcnow() - timedelta(hours=24)
        leads_12h = await self.leads.get_leads_by_status(LeadStatus.WA_SENT)
        for lead in leads_12h:
            if lead.updated_at < cutoff_12h and lead.updated_at > cutoff_24h:
                await self.wa.send_no_reply_followup(lead.phone, lead.name or "there")
            elif lead.updated_at < cutoff_24h:
                await self.leads.mark_cold(lead.id)
