"""
Background scheduler for:
- Expiring payment sessions
- Follow-up timers (12h, 24h)
- Daily UPI rotation
- Service health checks
- Mid-call QR generation via Dograh DB polling
"""

import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, text as sa_text

from app.config import get_settings
from app.models.database import Lead, LeadStatus, PaymentSession, MerchantAccount, ActiveUPIConfig, CallLog

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


async def midcall_qr_polling(engine):
    """Poll Dograh's database for active call runs that have confirmed_amount in gathered_context.

    When a call is in progress and the AI has extracted confirmed_amount,
    generate the Razorpay QR and send it on WhatsApp immediately — without waiting
    for the post-call webhook.

    This is the SECONDARY path (primary is the mid-call webhook node in the workflow).
    The poller catches cases where the webhook delivery fails.
    """
    dograh_engine = create_async_engine(
        settings.DOGRAH_DATABASE_URL,
        echo=False,
        pool_size=2,
        max_overflow=2,
        pool_recycle=120,
        pool_pre_ping=True,
    )
    pipeline_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    dograh_session = async_sessionmaker(dograh_engine, class_=AsyncSession, expire_on_commit=False)

    await asyncio.sleep(15)  # Give services time to initialize on first run

    while True:
        try:
            async with pipeline_session() as pdb, dograh_session() as ddb:
                # Find leads where call is active and QR not yet generated
                # Look for any recently triggered calls (last 30 min) that haven't reached payment stage
                active_statuses = (
                    LeadStatus.CALL_TRIGGERED,
                    LeadStatus.CALL_COMPLETED,
                    LeadStatus.WA_REPLIED,
                    LeadStatus.AMOUNT_CONFIRMED,
                )
                recently = datetime.utcnow() - timedelta(minutes=30)

                result = await pdb.execute(
                    select(CallLog).join(Lead, CallLog.lead_id == Lead.id)
                    .where(CallLog.status == "initiated")
                    .where(CallLog.dograh_run_id.isnot(None))
                    .where(Lead.status.in_(active_statuses))
                    .where(CallLog.created_at > recently)
                )
                active_call_logs = list(result.scalars().all())

                if active_call_logs:
                    logger.info(f"Mid-call poller: found {len(active_call_logs)} active call logs")

                for call_log in active_call_logs:
                    run_id = call_log.dograh_run_id

                    # Check if lead already has a QR (mid-call webhook may have already handled it)
                    lead = await pdb.execute(
                        select(Lead).where(Lead.id == call_log.lead_id)
                    )
                    lead = lead.scalar_one_or_none()
                    if not lead:
                        logger.warning(f"Mid-call poller: lead {call_log.lead_id} not found for run {run_id}")
                        continue
                    if lead.status in (LeadStatus.AWAITING_PAYMENT, LeadStatus.QR_GENERATED,
                                       LeadStatus.PAYMENT_RECEIVED, LeadStatus.PAYMENT_VERIFIED,
                                       LeadStatus.COMPLETED):
                        logger.info(f"Mid-call poller: lead {lead.id} already at {lead.status.value} — skipping")
                        continue

                    # Query Dograh workflow_runs table for gathered_context
                    dograh_result = await ddb.execute(
                        sa_text(
                            "SELECT gathered_context, state FROM workflow_runs "
                            "WHERE id = :run_id AND workflow_id = :wf_id"
                        ).bindparams(run_id=run_id, wf_id=settings.DOGRAH_WORKFLOW_ID)
                    )
                    row = dograh_result.fetchone()
                    if not row:
                        logger.debug(f"Mid-call poller: no workflow_runs row for run_id={run_id}, wf_id={settings.DOGRAH_WORKFLOW_ID}")
                        continue

                    gathered = row[0] if row[0] else {}
                    run_state = row[1] if len(row) > 1 else ""

                    # Parse gathered_context if it's a string
                    if isinstance(gathered, str):
                        try:
                            import json
                            gathered = json.loads(gathered)
                        except (json.JSONDecodeError, TypeError):
                            logger.warning(f"Mid-call poller: could not parse gathered_context for run {run_id}")
                            continue

                    if not isinstance(gathered, dict):
                        continue

                    confirmed_amount = gathered.get("confirmed_amount")
                    if not confirmed_amount:
                        logger.debug(f"Mid-call poller: no confirmed_amount for run {run_id} (state={run_state})")
                        continue

                    # Check if the call is still active or recently completed
                    # Dograh states: initialized, running, completed, failed, etc.
                    if run_state in ("failed",):
                        logger.info(f"Mid-call poller: run {run_id} failed — skipping")
                        continue

                    try:
                        amount = float(confirmed_amount)
                    except (ValueError, TypeError):
                        logger.warning(f"Mid-call poller: invalid confirmed_amount '{confirmed_amount}' for run {run_id}")
                        continue

                    # Validate amount range
                    if amount < settings.MIN_AMOUNT_INR or amount > settings.MAX_AMOUNT_INR:
                        logger.warning(f"Mid-call poller: amount Rs{amount} out of range for run {run_id}")
                        continue

                    # Generate QR mid-call!
                    from app.services.orchestrator import PipelineOrchestrator
                    orch = PipelineOrchestrator(pdb)
                    await orch.handle_midcall_amount_confirmed(
                        lead_id_str=str(lead.id),
                        amount=amount,
                        dograh_run_id=run_id,
                    )
                    logger.info(f"Mid-call QR via polling: lead={lead.id}, amount=Rs{amount}, run={run_id}")

        except Exception as e:
            logger.error(f"Error in midcall_qr_polling: {e}", exc_info=True)
        await asyncio.sleep(settings.MIDCALL_POLL_INTERVAL_SECONDS)


async def start_scheduler(engine):
    """start all background tasks."""
    tasks = [
        asyncio.create_task(expire_sessions_task(engine)),
        asyncio.create_task(followup_task(engine)),
        asyncio.create_task(daily_upi_rotation(engine)),
        asyncio.create_task(midcall_qr_polling(engine)),
    ]
    logger.info(f"Scheduler started: {len(tasks)} background tasks")
    return asyncio.gather(*tasks, return_exceptions=True)
