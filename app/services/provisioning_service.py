"""Platform Provisioning Service - creates user accounts after payment."""

import logging
import secrets
import string
import httpx
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.database import Lead, LeadStatus, ProvisionedAccount

logger = logging.getLogger(__name__)
settings = get_settings()


class ProvisioningService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.headers = {"Authorization": f"Bearer {settings.PLATFORM_API_KEY}", "Content-Type": "application/json"}

    def _generate_user_id(self) -> str:
        suffix = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(6))
        return f"usr_{suffix}"

    def _generate_password(self, length: int = 12) -> str:
        chars = string.ascii_letters + string.digits + "!@#$%"
        return ''.join(secrets.choice(chars) for _ in range(length))

    async def provision_account(self, lead_id: UUID, phone: str, amount: float,
                                 payment_session_id: UUID) -> ProvisionedAccount:
        user_id = self._generate_user_id()
        password = self._generate_password()
        payload = {"phone": phone, "initial_balance": amount, "user_id": user_id,
                   "password": password, "payment_session_id": str(payment_session_id)}
        max_retries = 3
        result_data = None
        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(f"{settings.PLATFORM_API_URL}/api/v1/account/create",
                                             json=payload, headers=self.headers)
                    resp.raise_for_status()
                    result_data = resp.json()
                    break
            except Exception as e:
                logger.warning(f"Provisioning attempt {attempt} failed: {e}")
                if attempt == max_retries:
                    raise
        provisioned = ProvisionedAccount(
            lead_id=lead_id, user_id=result_data.get("user_id", user_id) if result_data else user_id,
            password=password, initial_balance=amount, payment_session_id=payment_session_id)
        self.db.add(provisioned)
        lead = await self._get_lead(lead_id)
        if lead:
            lead.status = LeadStatus.ACCOUNT_CREATED
            lead.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(provisioned)
        return provisioned

    async def mark_credentials_sent(self, provisioned_id: UUID):
        result = await self.db.execute(select(ProvisionedAccount).where(ProvisionedAccount.id == provisioned_id))
        acct = result.scalar_one_or_none()
        if acct:
            acct.credentials_sent = True
            acct.credentials_sent_at = datetime.utcnow()
            lead = await self._get_lead(acct.lead_id)
            if lead:
                lead.status = LeadStatus.COMPLETED
                lead.updated_at = datetime.utcnow()
            await self.db.commit()

    async def _get_lead(self, lead_id: UUID) -> Optional[Lead]:
        result = await self.db.execute(select(Lead).where(Lead.id == lead_id))
        return result.scalar_one_or_none()
