"""Dograh Voice AI Service - triggers outbound calls and processes call webhooks.

Uses Dograh's public trigger endpoint:
  POST /api/v1/public/agent/{trigger_path}
  Headers: X-API-Key: {DOGRAH_API_KEY}
  Body: {"phone_number": "+91...", "initial_context": {...}, "telephony_configuration_id": N}

Call completion webhooks come from Dograh's webhook node to our /api/webhooks/dograh endpoint.
"""

import logging
import httpx
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.database import Lead, LeadStatus, CallLog
from app.schemas import DograhWebhookPayload

logger = logging.getLogger(__name__)
settings = get_settings()


class DograhService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.base_url = settings.DOGRAH_API_URL
        self.api_key = settings.DOGRAH_API_KEY
        self.trigger_path = settings.DOGRAH_TRIGGER_PATH
        self.telephony_config_id = settings.DOGRAH_TELEPHONY_CONFIG_ID

    async def trigger_outbound_call(self, lead_id: UUID, phone: str, name: str = "",
                                     custom_context: Optional[dict] = None) -> dict:
        """Trigger an outbound call via Dograh's public trigger endpoint."""
        initial_context = {
            "lead_id": str(lead_id),
            "customer_name": name,
            "customer_phone": phone,
        }
        if custom_context:
            initial_context.update(custom_context)

        # Dograh requires E.164 format with leading '+' in 'phone_number'.
        # Normalize: if phone doesn't start with +, assume India (+91) for 10-digit numbers.
        if phone.startswith("+"):
            phone_e164 = phone
        elif len(phone) == 10:
            phone_e164 = f"+91{phone}"
        elif phone.startswith("91") and len(phone) == 12:
            phone_e164 = f"+{phone}"
        else:
            phone_e164 = f"+{phone}"
        payload = {
            "phone_number": phone_e164,
            "initial_context": initial_context,
            "telephony_configuration_id": int(self.telephony_config_id),
        }

        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}/api/v1/public/agent/{self.trigger_path}"

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        run_id = data.get("workflow_run_id") or data.get("run_id")
        call_sid = data.get("call_sid", data.get("call_control_id", ""))

        call_log = CallLog(
            lead_id=lead_id,
            dograh_run_id=run_id,
            twilio_call_sid=call_sid,
            status="initiated",
        )
        self.db.add(call_log)
        await self._update_lead_status(lead_id, LeadStatus.CALL_TRIGGERED)
        await self.db.commit()
        logger.info(f"Outbound call triggered: run_id={run_id}, phone={phone}")
        return data

    async def record_trigger_failure(self, lead_id: UUID, phone: str, error: str) -> None:
        """Persist a Dograh trigger failure as a call log so it is auditable."""
        call_log = CallLog(
            lead_id=lead_id,
            dograh_run_id=None,
            twilio_call_sid="",
            status="trigger_failed",
        )
        self.db.add(call_log)
        await self.db.commit()
        logger.error(f"Call trigger recorded as FAILED for lead {lead_id}: {error}")

    async def process_call_webhook(self, payload: DograhWebhookPayload) -> Optional[Lead]:
        """Process a call completion webhook from Dograh."""
        run_id = payload.run_id
        gathered = payload.gathered_context or {}
        initial = payload.initial_context or {}
        lead_id_str = initial.get("lead_id")
        if not lead_id_str:
            logger.error(f"No lead_id in Dograh webhook run {run_id}")
            return None
        lead_id = UUID(lead_id_str)

        result = await self.db.execute(select(CallLog).where(CallLog.dograh_run_id == run_id))
        call_log = result.scalar_one_or_none()
        if call_log:
            call_log.status = "completed"
            call_log.transcript_url = payload.transcript_url
            call_log.recording_url = payload.recording_url
            call_log.raw_webhook = payload.model_dump()

        amount = None
        if "confirmed_amount" in gathered:
            try:
                amount = float(gathered["confirmed_amount"])
            except (ValueError, TypeError):
                logger.warning(f"Invalid amount: {gathered.get('confirmed_amount')}")

        outcome = gathered.get("call_outcome", "completed")
        if outcome == "voicemail":
            if call_log:
                call_log.status = "voicemail"
            await self._update_lead_status(lead_id, LeadStatus.CALL_FAILED)
        elif outcome == "no_answer":
            if call_log:
                call_log.status = "no_answer"
            await self._update_lead_status(lead_id, LeadStatus.CALL_FAILED)
        elif outcome == "not_interested":
            if call_log:
                call_log.status = "not_interested"
            await self._update_lead_status(lead_id, LeadStatus.REJECTED)
        elif amount and settings.MIN_AMOUNT_INR <= amount <= settings.MAX_AMOUNT_INR:
            if call_log:
                call_log.amount_extracted = amount
            await self._update_lead_status(lead_id, LeadStatus.CALL_COMPLETED)
        else:
            await self._update_lead_status(lead_id, LeadStatus.CALL_COMPLETED)
        await self.db.commit()
        return await self._get_lead(lead_id)

    async def _update_lead_status(self, lead_id: UUID, status: LeadStatus):
        lead = await self._get_lead(lead_id)
        if lead:
            lead.status = status
            lead.updated_at = datetime.utcnow()

    async def _get_lead(self, lead_id: UUID) -> Optional[Lead]:
        result = await self.db.execute(select(Lead).where(Lead.id == lead_id))
        return result.scalar_one_or_none()

    async def _get_lead_from_initial_context(self, initial_context: Optional[dict]) -> Optional[Lead]:
        """Extract lead_id from initial_context (handles both dict and JSON string) and return the lead."""
        if not initial_context:
            return None
        ctx = initial_context
        if isinstance(ctx, str):
            try:
                import json
                ctx = json.loads(ctx)
            except (json.JSONDecodeError, TypeError):
                return None
        if not isinstance(ctx, dict):
            return None
        lead_id_str = ctx.get("lead_id")
        if not lead_id_str:
            return None
        try:
            return await self._get_lead(UUID(lead_id_str))
        except (ValueError, AttributeError):
            return None
