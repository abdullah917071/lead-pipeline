"""
Background scheduler for:
- Expiring payment sessions
- Follow-up timers (12h, 24h)
- Daily UPI rotation
- Service health checks
"""

import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select

from app.config import get_settings
from app.models.database import Lead, LeadStatus, PaymentSession, MerchantAccount, ActiveUPIConfig

logger = logging.getLogger(__name__)
settings = get_settings()


async def check_service_health(db: AsyncSession) -> dict:
    """Check health of all connected services."""
    health = {}

    # Check Dograh
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.DOGRAH_API_URL}/health")
            health["dograh"] = {"status": "healthy" if resp.status_code == 200 else "unhealthy", "latency_ms": resp.elapsed.total_seconds() * 1000}
    except Exception as e:
        health["dograh"] = {"status": "down", "error": str(e)}

    # Check WhatsApp API
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.WA_API_URL}/", headers={"Authorization": f"Bearer {settings.WA_ACCESS_TOKEN}"})
            health["whatsapp"] = {"status": "healthy" if resp.status_code in (200, 404) else "unhealthy"}
    except Exception as e:
        health["whatsapp"] = {"status": "down", "error": str(e)}

    # Check Platform API
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.PLATFORM_API_URL}/health", headers={"Authorization": f"Bearer {settings.PLATFORM_API_KEY}"})
            health["platform_api"] = {"status": "healthy" if resp.status_code in (200, 404) else "unhealthy"}
    except Exception as e:
        health["platform_api"] = {"status": "down", "error": str(e)}

    return health


async def expire_sessions_task(engine):
    """Expire old payment sessions and send fresh QR."""
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    while True:
        try:
            async with async_session() as db:
                now = datetime.utcnow()
                result = await db.execute(
                    select(PaymentSession).where(PaymentSession.status == "active")
                    .where(PaymentSession.expires_at < now)
                )
                expired = list(result.scalars().all())
                for session in expired:
                    session.status = "expired"
                    logger.info(f"Session expired: ref={session.ref_id}")
                if expired:
                    await db.commit()
        except Exception as e:
            logger.error(f"Error in expire_sessions: {e}")
        await asyncio.sleep(60)  # Check every minute


async def followup_task(engine):
    """Send follow-up messages to leads that haven't replied."""
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    while True:
        try:
            async with async_session() as db:
                cutoff_12h = datetime.utcnow() - timedelta(hours=12)
                cutoff_24h = datetime.utcnow() - timedelta(hours=24)

                # 12h follow-up
                result = await db.execute(
                    select(Lead).where(Lead.status == LeadStatus.WA_SENT)
                    .where(Lead.updated_at < cutoff_12h)
                    .where(Lead.updated_at > cutoff_24h)
                )
                leads_12h = list(result.scalars().all())
                for lead in leads_12h:
                    from app.services.whatsapp_service import WhatsAppService
                    wa = WhatsAppService()
                    await wa.send_no_reply_followup(lead.phone, lead.name or "there")
                    logger.info(f"12h follow-up sent: {lead.phone}")

                # 24h mark as cold
                result2 = await db.execute(
                    select(Lead).where(Lead.status == LeadStatus.WA_SENT)
                    .where(Lead.updated_at < cutoff_24h)
                )
                leads_24h = list(result2.scalars().all())
                for lead in leads_24h:
                    lead.status = LeadStatus.COLD
                    lead.updated_at = datetime.utcnow()
                    logger.info(f"Marked cold (24h): {lead.phone}")

                if leads_24h:
                    await db.commit()
        except Exception as e:
            logger.error(f"Error in followup: {e}")
        await asyncio.sleep(3600)  # Check every hour


async def daily_upi_rotation(engine):
    """Rotate UPI account at midnight IST (18:30 UTC)."""
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    while True:
        try:
            now = datetime.utcnow()
            # IST midnight = 18:30 UTC
            if now.hour == 18 and now.minute == 30:
                async with async_session() as db:
                    from app.services.upi_service import UPIPaymentService
                    upi = UPIPaymentService(db)
                    result = await upi.rotate_daily()
                    logger.info(f"Daily UPI rotation: {result}")
                await asyncio.sleep(60)  # Don't rotate twice
        except Exception as e:
            logger.error(f"Error in UPI rotation: {e}")
        await asyncio.sleep(3600)  # Check every hour


async def start_scheduler(engine):
    """start all background tasks."""
    tasks = [
        asyncio.create_task(expire_sessions_task(engine)),
        asyncio.create_task(followup_task(engine)),
        asyncio.create_task(daily_upi_rotation(engine)),
    ]
    logger.info(f"Scheduler started: {len(tasks)} background tasks")
    return asyncio.gather(*tasks, return_exceptions=True)
