"""
Complete Lead Pipeline Orchestrator - Production Ready
Real services, real APIs, real payment tracking.

Flow:
  Meta ad -> WhatsApp opt-in (image+button) -> Interested click ->
  Call notification -> Dograh voice call -> AI confirms sale ->
  Razorpay dynamic QR -> WhatsApp QR image -> Payment captured ->
  Instant demo credentials
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import JSONB

from app.config import get_settings
from app.models.database import Base, Lead, LeadStatus, MerchantAccount, ActiveUPIConfig, CallLog, PaymentSession, ProvisionedAccount
from app.schemas import (IncomingLead, DograhWebhookPayload, LeadResponse,
                          PaymentSuccessRequest, DashboardStats)
from app.services.orchestrator import PipelineOrchestrator
from app.services.upi_service import UPIPaymentService
from app.services.razorpay_service import RazorpayService
from app.routers.admin import router as admin_router
from app.tasks.scheduler import start_scheduler

logger = logging.getLogger(__name__)

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=10,
    max_overflow=20,
)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Pipeline Orchestrator started - production mode")

    # Start background scheduler
    scheduler_task = await start_scheduler(engine)
    yield
    scheduler_task.cancel()
    await engine.dispose()


app = FastAPI(
    title="Lead Pipeline Orchestrator",
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)
app.include_router(admin_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════════
# Step 1: Lead ingestion (from Meta ad webhook)
# ═══════════════════════════════════════════════════════════════════

@app.post("/api/webhooks/lead", response_model=LeadResponse)
async def ingest_lead(data: IncomingLead, db: AsyncSession = Depends(get_db)):
    """Ingest a new lead from Meta ad and instantly send WhatsApp opt-in."""
    orchestrator = PipelineOrchestrator(db)
    lead = await orchestrator.handle_new_lead(data)
    return LeadResponse.model_validate(lead)


# ═══════════════════════════════════════════════════════════════════
# Step 2: WhatsApp webhook (incoming messages + button clicks)
# ═══════════════════════════════════════════════════════════════════

@app.post("/api/webhooks/whatsapp")
async def whatsapp_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle incoming WhatsApp messages:
    - 'Interested' button click -> send call notification + trigger voice call
    - Amount reply (after call) -> generate QR
    - Free text -> classify intent
    """
    body = await request.json()
    try:
        entry = body.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])
        if not messages:
            # Could be a status update (delivered, read, etc.)
            return {"status": "ok", "info": "no message"}

        msg = messages[0]
        phone = msg.get("from", "")
        msg_type = msg.get("type", "")

        # Extract message content based on type
        if msg_type == "interactive":
            # Button click
            interactive = msg.get("interactive", {})
            interactive_type = interactive.get("type", "")
            if interactive_type == "button_reply":
                text = interactive["button_reply"]["id"]
            elif interactive_type == "list_reply":
                text = interactive["list_reply"]["id"]
            else:
                text = ""
        elif msg_type == "text":
            text = msg["text"]["body"]
        else:
            text = ""

        logger.info(f"WA webhook: phone={phone}, type={msg_type}, text={text[:50]}")

        orchestrator = PipelineOrchestrator(db)
        lead = await orchestrator.leads.get_by_phone(phone)
        if not lead:
            # First contact from this number — send opt-in template, wait for Interested tap
            from app.schemas import IncomingLead
            data = IncomingLead(phone=phone, name="", source="whatsapp_inbound")
            lead = await orchestrator.handle_new_lead(data)
            logger.info(f"Auto-ingested new lead from inbound WA message: {phone}")
            # Do NOT process the message — wait for Interested button click
            return {"status": "ok", "lead_id": str(lead.id)}

        # Route based on lead status
        if msg_type == "interactive":
            # Button click — always treat as interested for opt-in template
            lead = await orchestrator.handle_wa_reply(phone, "interested")
        elif lead.status == LeadStatus.AMOUNT_CONFIRMED:
            # User is replying with an amount after call
            lead = await orchestrator.handle_wa_amount_reply(phone, text)
        elif lead.status == LeadStatus.WA_SENT or lead.status == LeadStatus.PENDING_WA_OPTIN:
            # Free text while waiting for opt-in — classify intent (don't hardcode 'interested')
            lead = await orchestrator.handle_wa_reply(phone, text)
        else:
            # Normal reply / free text
            lead = await orchestrator.handle_wa_reply(phone, text)

        return {"status": "ok", "lead_id": str(lead.id) if lead else None}
    except (IndexError, KeyError) as e:
        logger.error(f"WA webhook parse error: {e}")
        return {"status": "error", "detail": str(e)}


@app.get("/api/webhooks/whatsapp")
async def whatsapp_verify(request: Request):
    """Verify WhatsApp webhook (Meta sends challenge)."""
    mode = request.query_params.get("hub.mode")
    challenge = request.query_params.get("hub.challenge")
    token = request.query_params.get("hub.verify_token")
    if mode == "subscribe" and token == settings.WA_WEBHOOK_VERIFY_TOKEN:
        return PlainTextResponse(content=challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


# ═══════════════════════════════════════════════════════════════════
# Step 3: Dograh call completion webhook
# ═══════════════════════════════════════════════════════════════════

@app.post("/api/webhooks/dograh")
async def dograh_webhook(payload: DograhWebhookPayload, db: AsyncSession = Depends(get_db)):
    """Handle Dograh call completion webhook.
    Extracts confirmed amount and triggers QR generation.
    """
    orchestrator = PipelineOrchestrator(db)
    lead = await orchestrator.handle_call_completed(payload)
    if lead:
        return {"status": "ok", "lead_id": str(lead.id), "lead_status": lead.status.value}
    return {"status": "ok", "info": "no lead matched"}


# ═══════════════════════════════════════════════════════════════════
# Step 4+5: Razorpay payment webhook (with signature verification)
# ═══════════════════════════════════════════════════════════════════

@app.post("/api/webhooks/payment/razorpay")
async def razorpay_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle Razorpay payment webhook with signature verification.

    Events handled:
    - payment.captured: Payment successful -> provision + send credentials
    - qr_code.closed: QR code expired/used
    """
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    # Verify webhook signature
    razorpay = RazorpayService()
    if not razorpay.verify_webhook_signature(raw_body, signature):
        logger.error("Razorpay webhook signature verification failed!")
        raise HTTPException(status_code=400, detail="Invalid signature")

    import json
    payload = json.loads(raw_body)
    event = payload.get("event", "")
    logger.info(f"Razorpay webhook event: {event}")

    if event == "payment.captured":
        payment = payload["payload"]["payment"]["entity"]
        amount_inr = float(payment["amount"]) / 100
        utr = payment.get("utr", payment.get("id", ""))
        notes = payment.get("notes", {})
        ref_id = notes.get("ref_id", "")

        orchestrator = PipelineOrchestrator(db)
        await orchestrator.handle_payment_success(
            ref_id=ref_id, utr=utr, amount=amount_inr, gateway="razorpay"
        )

    elif event == "qr_code.closed":
        # QR expired or used — log it
        qr_data = payload["payload"]["qr_code"]["entity"]
        logger.info(f"Razorpay QR closed: {qr_data.get('id')}")

    elif event == "payment.failed":
        payment = payload["payload"]["payment"]["entity"]
        logger.warning(f"Payment failed: {payment.get('id')}, error: {payment.get('error_description', 'unknown')}")

    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════════
# SMS listener webhook (alternative payment confirmation)
# ═══════════════════════════════════════════════════════════════════

@app.post("/api/internal/bank-sms-listener")
async def sms_listener_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Receive SMS payment confirmations from Android SMS listener."""
    payload = await request.json()
    amount = float(payload.get("amount", 0))
    utr = payload.get("utr", "")
    sender = payload.get("sender", "upi")
    if not amount or not utr:
        raise HTTPException(status_code=400, detail="Missing amount or UTR")
    orchestrator = PipelineOrchestrator(db)
    await orchestrator.handle_payment_success(
        ref_id="", utr=utr, amount=amount, gateway=f"sms_listener:{sender}"
    )
    return {"status": "ok"}


@app.post("/api/internal/payment-success")
async def internal_payment_success(data: PaymentSuccessRequest, db: AsyncSession = Depends(get_db)):
    """Internal payment success endpoint (for manual/testing)."""
    orchestrator = PipelineOrchestrator(db)
    await orchestrator.handle_payment_success(
        ref_id=data.ref_id, utr=data.utr, amount=data.amount, gateway=data.gateway
    )
    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════════
# UPI / Payment management endpoints
# ═══════════════════════════════════════════════════════════════════

@app.get("/api/upi/active")
async def get_active_upi(db: AsyncSession = Depends(get_db)):
    """Get current active UPI account."""
    upi_svc = UPIPaymentService(db)
    acct = await upi_svc.get_active_upi()
    if acct:
        return {
            "account_id": acct.id, "upi_id": acct.upi_id,
            "display_name": acct.display_name,
            "daily_cap": acct.daily_cap_inr, "current_volume": acct.current_volume_inr,
            "is_active": acct.is_active
        }
    return {"error": "no_active_upi"}


@app.post("/api/upi/rotate")
async def manual_upi_rotate(db: AsyncSession = Depends(get_db)):
    """Manually rotate UPI account."""
    upi_svc = UPIPaymentService(db)
    return await upi_svc.manual_rotate()


# ═══════════════════════════════════════════════════════════════════
# Dashboard + lead management
# ═══════════════════════════════════════════════════════════════════

@app.get("/api/dashboard")
async def dashboard(db: AsyncSession = Depends(get_db)):
    """Real-time dashboard stats."""
    total = (await db.execute(select(func.count(Lead.id)))).scalar() or 0
    pending = (await db.execute(
        select(func.count(Lead.id)).where(Lead.status == LeadStatus.PENDING_WA_OPTIN)
    )).scalar() or 0
    wa_sent = (await db.execute(
        select(func.count(Lead.id)).where(Lead.status == LeadStatus.WA_SENT)
    )).scalar() or 0
    calls = (await db.execute(
        select(func.count(Lead.id)).where(Lead.status == LeadStatus.CALL_TRIGGERED)
    )).scalar() or 0
    call_done = (await db.execute(
        select(func.count(Lead.id)).where(Lead.status == LeadStatus.CALL_COMPLETED)
    )).scalar() or 0
    awaiting = (await db.execute(
        select(func.count(Lead.id)).where(Lead.status == LeadStatus.AWAITING_PAYMENT)
    )).scalar() or 0
    payments = (await db.execute(
        select(func.count(Lead.id)).where(Lead.status == LeadStatus.PAYMENT_RECEIVED)
    )).scalar() or 0
    completed = (await db.execute(
        select(func.count(Lead.id)).where(Lead.status == LeadStatus.COMPLETED)
    )).scalar() or 0
    cold = (await db.execute(
        select(func.count(Lead.id)).where(Lead.status == LeadStatus.COLD)
    )).scalar() or 0
    rejected = (await db.execute(
        select(func.count(Lead.id)).where(Lead.status == LeadStatus.REJECTED)
    )).scalar() or 0

    total_payment_value = (await db.execute(
        select(func.coalesce(func.sum(PaymentSession.amount_inr), 0))
        .where(PaymentSession.status == "paid")
    )).scalar() or 0

    upi_config = (await db.execute(
        select(ActiveUPIConfig).where(ActiveUPIConfig.id == 1)
    )).scalar_one_or_none()
    active_upi = ""
    active_bank = ""
    if upi_config:
        acct = (await db.execute(
            select(MerchantAccount).where(MerchantAccount.id == upi_config.active_account_id)
        )).scalar_one_or_none()
        if acct:
            active_upi = acct.upi_id
            active_bank = acct.display_name

    recent = (await db.execute(
        select(Lead).order_by(Lead.created_at.desc()).limit(20)
    )).scalars().all()
    recent_list = [{
        "id": str(l.id), "phone": l.phone, "name": l.name, "status": l.status.value,
        "source": l.source, "created_at": l.created_at.isoformat(),
        "metadata": l.metadata_json
    } for l in recent]

    accounts = (await db.execute(
        select(MerchantAccount).order_by(MerchantAccount.id)
    )).scalars().all()
    acct_list = [{
        "id": a.id, "upi_id": a.upi_id, "display_name": a.display_name,
        "daily_cap": a.daily_cap_inr, "current_volume": a.current_volume_inr,
        "is_active": a.is_active, "is_enabled": a.is_enabled
    } for a in accounts]

    # Service health check
    from app.tasks.scheduler import check_service_health
    service_health = await check_service_health(db)

    return {
        "total_leads": total, "pending_optin": pending, "wa_sent": wa_sent,
        "calls_in_progress": calls, "calls_completed": call_done,
        "awaiting_payment": awaiting, "payments_received": payments,
        "completed": completed, "cold": cold, "rejected": rejected,
        "total_payment_value": float(total_payment_value),
        "active_upi": active_upi, "active_bank": active_bank,
        "recent_leads": recent_list, "merchant_accounts": acct_list,
        "service_health": service_health,
        "min_amount": settings.MIN_AMOUNT_INR,
        "max_amount": settings.MAX_AMOUNT_INR,
        "razorpay_configured": bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET),
    }


@app.get("/api/leads")
async def list_leads(status: str = None, limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db)):
    """List leads with optional status filter."""
    q = select(Lead).order_by(Lead.created_at.desc()).offset(offset).limit(limit)
    if status:
        try:
            st = LeadStatus(status)
            q = q.where(Lead.status == st)
        except ValueError:
            pass
    result = await db.execute(q)
    leads = result.scalars().all()
    return [{
        "id": str(l.id), "phone": l.phone, "name": l.name, "status": l.status.value,
        "source": l.source, "created_at": l.created_at.isoformat(),
        "updated_at": l.updated_at.isoformat()
    } for l in leads]


@app.get("/api/leads/{lead_id}")
async def get_lead(lead_id: str, db: AsyncSession = Depends(get_db)):
    """Get full lead detail with payment sessions and call logs."""
    from uuid import UUID
    result = await db.execute(select(Lead).where(Lead.id == UUID(lead_id)))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    sessions = (await db.execute(
        select(PaymentSession).where(PaymentSession.lead_id == lead.id)
    )).scalars().all()
    call_logs = (await db.execute(
        select(CallLog).where(CallLog.lead_id == lead.id)
    )).scalars().all()
    return {
        "id": str(lead.id), "phone": lead.phone, "name": lead.name, "status": lead.status.value,
        "source": lead.source, "created_at": lead.created_at.isoformat(),
        "metadata": lead.metadata_json,
        "sessions": [{
            "ref_id": s.ref_id, "amount": s.amount_inr, "status": s.status, "upi_id": s.upi_id,
            "utr": s.utr_number, "gateway": s.gateway, "razorpay_qr_id": s.razorpay_qr_id,
            "created_at": s.created_at.isoformat()
        } for s in sessions],
        "calls": [{
            "run_id": c.dograh_run_id, "status": c.status, "duration": c.duration_seconds,
            "amount": c.amount_extracted, "created_at": c.created_at.isoformat()
        } for c in call_logs],
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "lead-pipeline-orchestrator", "version": "3.0.0"}
