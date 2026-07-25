"""Admin control-panel API: settings, lead controls, monitoring, logs, health.

All endpoints are mounted under /api/admin. The dashboard frontend calls these.
Settings are persisted in the pipeline_settings table (runtime-editable) and fall
back to config.py defaults.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select, func, update, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db_session import get_db
from app.models.database import (
    Lead, LeadStatus, PaymentSession, CallLog, MerchantAccount,
    ActiveUPIConfig, PipelineSetting, ProvisionedAccount,
)
from app.schemas import IncomingLead
from app.services.orchestrator import PipelineOrchestrator
from app.services.upi_service import UPIPaymentService
from app.services.whatsapp_service import WhatsAppService

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api/admin", tags=["admin"])
DASHBOARD_KEYS = {
    "min_amount_inr": settings.MIN_AMOUNT_INR,
    "max_amount_inr": settings.MAX_AMOUNT_INR,
    "wa_optin_template_name": settings.WA_OPTIN_TEMPLATE_NAME,
    "wa_optin_image_url": settings.WA_OPTIN_IMAGE_URL,
    "razorpay_enabled": bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET),
    "upi_merchant_name": settings.UPI_MERCHANT_NAME,
    "payment_session_expiry_minutes": settings.PAYMENT_SESSION_EXPIRY_MINUTES,
    "optin_body_template": (
        "Hi {name}, welcome to Sai Bhai Cricket ID - your trusted cricket betting "
        "ID provider since 2022. Get instant demo IDs, 24/7 support, and the best odds. "
        "Tap 'Interested' and our team will call you shortly to get started!"
    ),
    "call_notice_template": (
        "Great, {name}! Thanks for your interest. Our team will call you in just a few "
        "minutes to help you get started."
    ),
    "qr_caption_template": (
        "Awesome! Deposit locked at Rs {amount}. Scan this QR with PhonePe/GPay/Paytm. "
        "Pay exactly Rs {amount}. Your Sai Bhai Cricket ID demo account will be sent "
        "instantly after payment!"
    ),
    "dograh_trigger_path": getattr(settings, "DOGRAH_TRIGGER_PATH", ""),
    "dograh_telephony_config_id": getattr(settings, "DOGRAH_TELEPHONY_CONFIG_ID", 3),
}


# ─── Settings ────────────────────────────────────────────────────────

class SettingUpdate(BaseModel):
    key: str
    value: Any
    updated_by: Optional[str] = "admin"


@router.get("/settings")
async def get_admin_settings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PipelineSetting))
    rows = {r.key: r.value for r in result.scalars().all()}
    merged = dict(DASHBOARD_KEYS)
    merged.update(rows)
    return {"settings": merged, "defaults": DASHBOARD_KEYS, "overrides": rows}


@router.put("/settings")
async def put_setting(payload: SettingUpdate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(PipelineSetting).where(PipelineSetting.key == payload.key))
    row = existing.scalar_one_or_none()
    if row:
        row.value = payload.value
        row.updated_at = datetime.utcnow()
        row.updated_by = payload.updated_by
    else:
        row = PipelineSetting(key=payload.key, value=payload.value, updated_by=payload.updated_by)
        db.add(row)
    await db.commit()
    # Reflect min/max into in-memory config so the running pipeline picks it up
    if payload.key == "min_amount_inr":
        settings.MIN_AMOUNT_INR = float(payload.value)
    elif payload.key == "max_amount_inr":
        settings.MAX_AMOUNT_INR = float(payload.value)
    return {"ok": True, "key": payload.key, "value": payload.value}


@router.put("/settings/bulk")
async def put_settings_bulk(payload: List[SettingUpdate], db: AsyncSession = Depends(get_db)):
    for item in payload:
        existing = await db.execute(
            select(PipelineSetting).where(PipelineSetting.key == item.key))
        row = existing.scalar_one_or_none()
        if row:
            row.value = item.value
            row.updated_at = datetime.utcnow()
        else:
            db.add(PipelineSetting(key=item.key, value=item.value))
    await db.commit()
    return {"ok": True, "count": len(payload)}


# ─── Live monitoring ─────────────────────────────────────────────────

@router.get("/monitor")
async def monitor(db: AsyncSession = Depends(get_db)):
    now = datetime.utcnow()
    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d = now - timedelta(days=7)

    statuses = [s for s in LeadStatus]
    funnel = {}
    for st in statuses:
        c = (await db.execute(select(func.count(Lead.id)).where(Lead.status == st))).scalar() or 0
        funnel[st.value] = c

    total = (await db.execute(select(func.count(Lead.id)))).scalar() or 0
    last_24h = (await db.execute(
        select(func.count(Lead.id)).where(Lead.created_at >= cutoff_24h))).scalar() or 0
    last_7d = (await db.execute(
        select(func.count(Lead.id)).where(Lead.created_at >= cutoff_7d))).scalar() or 0

    completed = funnel.get("completed", 0) + funnel.get("credentials_delivered", 0)
    awaiting = funnel.get("awaiting_payment", 0) + funnel.get("qr_generated", 0) + funnel.get("payment_received", 0) + funnel.get("payment_verified", 0) + funnel.get("account_created", 0)

    total_revenue = (await db.execute(
        select(func.coalesce(func.sum(PaymentSession.amount_inr), 0))
        .where(PaymentSession.status == "paid"))).scalar() or 0

    revenue_24h = (await db.execute(
        select(func.coalesce(func.sum(PaymentSession.amount_inr), 0))
        .where(PaymentSession.status == "paid")
        .where(PaymentSession.paid_at >= cutoff_24h))).scalar() or 0

    revenue_7d = (await db.execute(
        select(func.coalesce(func.sum(PaymentSession.amount_inr), 0))
        .where(PaymentSession.status == "paid")
        .where(PaymentSession.paid_at >= cutoff_7d))).scalar() or 0

    active_calls = funnel.get("call_triggered", 0)
    calls_done = funnel.get("call_completed", 0)

    return {
        "funnel": funnel,
        "totals": {
            "leads_total": total,
            "leads_24h": last_24h,
            "leads_7d": last_7d,
            "completed": completed,
            "awaiting_payment": awaiting,
            "active_calls": active_calls,
            "calls_completed": calls_done,
        },
        "revenue": {
            "total": float(total_revenue),
            "24h": float(revenue_24h),
            "7d": float(revenue_7d),
        },
        "generated_at": now.isoformat(),
    }


@router.get("/revenue-timeseries")
async def revenue_timeseries(db: AsyncSession = Depends(get_db), days: int = 7):
    rows = (await db.execute(
        select(func.date_trunc("day", PaymentSession.paid_at).label("day"),
               func.coalesce(func.sum(PaymentSession.amount_inr), 0))
        .where(PaymentSession.status == "paid")
        .where(PaymentSession.paid_at >= datetime.utcnow() - timedelta(days=days))
        .group_by(text("day")).order_by(text("day")))).all()
    series = [{"date": str(r[0].date()) if r[0] else None, "revenue": float(r[1])} for r in rows]
    return {"series": series}


@router.get("/funnel-timeseries")
async def funnel_timeseries(db: AsyncSession = Depends(get_db), days: int = 7):
    rows = (await db.execute(
        select(func.date_trunc("day", Lead.created_at).label("day"),
               func.count(Lead.id))
        .where(Lead.created_at >= datetime.utcnow() - timedelta(days=days))
        .group_by(text("day")).order_by(text("day")))).all()
    series = [{"date": str(r[0].date()) if r[0] else None, "leads": int(r[1])} for r in rows]
    return {"series": series}


# ─── Leads ──────────────────────────────────────────────────────────

@router.get("/leads")
async def list_leads_admin(status: Optional[str] = None, limit: int = 100, offset: int = 0,
                           db: AsyncSession = Depends(get_db)):
    q = select(Lead).order_by(Lead.created_at.desc()).offset(offset).limit(limit)
    if status:
        try:
            q = q.where(Lead.status == LeadStatus(status))
        except ValueError:
            pass
    leads = (await db.execute(q)).scalars().all()
    return [{
        "id": str(l.id), "phone": l.phone, "name": l.name, "status": l.status.value,
        "source": l.source, "created_at": l.created_at.isoformat(),
        "updated_at": l.updated_at.isoformat(),
    } for l in leads]


@router.get("/leads/{lead_id}/detail")
async def lead_detail(lead_id: str, db: AsyncSession = Depends(get_db)):
    from uuid import UUID as U
    lead = (await db.execute(select(Lead).where(Lead.id == U(lead_id)))).scalar_one_or_none()
    if not lead:
        return JSONResponse(status_code=404, content={"error": "not found"})
    sessions = (await db.execute(
        select(PaymentSession).where(PaymentSession.lead_id == lead.id))).scalars().all()
    calls = (await db.execute(
        select(CallLog).where(CallLog.lead_id == lead.id))).scalars().all()
    prov = (await db.execute(
        select(ProvisionedAccount).where(ProvisionedAccount.lead_id == lead.id))).scalar_one_or_none()
    return {
        "id": str(lead.id), "phone": lead.phone, "name": lead.name,
        "status": lead.status.value, "source": lead.source,
        "metadata": lead.metadata_json,
        "created_at": lead.created_at.isoformat(), "updated_at": lead.updated_at.isoformat(),
        "sessions": [{
            "ref_id": s.ref_id, "amount": s.amount_inr, "status": s.status,
            "upi_id": s.upi_id, "gateway": s.gateway, "razorpay_qr_id": s.razorpay_qr_id,
            "qr_image_url": s.qr_image_url, "utr": s.utr_number,
            "created_at": s.created_at.isoformat(),
        } for s in sessions],
        "calls": [{
            "run_id": c.dograh_run_id, "status": c.status, "duration": c.duration_seconds,
            "amount": c.amount_extracted, "created_at": c.created_at.isoformat(),
        } for c in calls],
        "provisioned": {
            "user_id": prov.user_id, "password": prov.password,
            "initial_balance": prov.initial_balance,
            "credentials_sent": prov.credentials_sent,
        } if prov else None,
    }


@router.post("/leads/{lead_id}/send-optin")
async def admin_send_optin(lead_id: str, db: AsyncSession = Depends(get_db)):
    orch = PipelineOrchestrator(db)
    lead = await orch.leads._get(UUID(lead_id))
    if not lead:
        return JSONResponse(status_code=404, content={"error": "not found"})
    await orch.wa.send_optin_message(lead.phone, lead.name or "there")
    await orch.leads.advance(lead.id, LeadStatus.WA_SENT)
    return {"ok": True, "status": "wa_sent"}


@router.post("/leads/{lead_id}/trigger-call")
async def admin_trigger_call(lead_id: str, db: AsyncSession = Depends(get_db)):
    orch = PipelineOrchestrator(db)
    lead = await orch.leads._get(UUID(lead_id))
    if not lead:
        return JSONResponse(status_code=404, content={"error": "not found"})
    await orch.wa.send_call_incoming_notice(lead.phone, lead.name or "")
    await orch.leads.advance(lead.id, LeadStatus.WA_REPLIED)
    try:
        await orch.dograh.trigger_outbound_call(lead_id=lead.id, phone=lead.phone, name=lead.name or "")
    except Exception as e:
        logger.error(f"Admin call trigger failed: {e}")
        return {"ok": False, "error": str(e)[:300]}
    return {"ok": True, "status": "call_triggered"}


@router.post("/leads/{lead_id}/resend-qr")
async def admin_resend_qr(lead_id: str, amount: Optional[float] = None,
                          db: AsyncSession = Depends(get_db)):
    orch = PipelineOrchestrator(db)
    lead = await orch.leads._get(UUID(lead_id))
    if not lead:
        return JSONResponse(status_code=404, content={"error": "not found"})
    amt = amount or settings.MIN_AMOUNT_INR
    result = await orch._generate_and_send_qr(lead, amt)
    return {"ok": True, "status": result.status.value, "amount": amt}


@router.post("/leads/{lead_id}/mark-payment")
async def admin_mark_payment(lead_id: str, amount: float, utr: str = "admin-manual",
                             db: AsyncSession = Depends(get_db)):
    orch = PipelineOrchestrator(db)
    await orch.handle_payment_success(ref_id="", utr=utr, amount=amount, gateway="admin")
    return {"ok": True}


@router.post("/leads/{lead_id}/advance")
async def admin_advance(lead_id: str, status: str, db: AsyncSession = Depends(get_db)):
    orch = PipelineOrchestrator(db)
    try:
        st = LeadStatus(status)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": f"invalid status {status}"})
    lead = await orch.leads.advance(UUID(lead_id), st)
    return {"ok": True, "status": lead.status.value}


@router.post("/leads/ingest")
async def admin_ingest(payload: IncomingLead, db: AsyncSession = Depends(get_db)):
    orch = PipelineOrchestrator(db)
    lead = await orch.handle_new_lead(payload)
    return {"id": str(lead.id), "status": lead.status.value}


# ─── Payments / UPI ──────────────────────────────────────────────────

@router.get("/upi/accounts")
async def upi_accounts(db: AsyncSession = Depends(get_db)):
    accts = (await db.execute(select(MerchantAccount).order_by(MerchantAccount.id))).scalars().all()
    cfg = (await db.execute(select(ActiveUPIConfig).where(ActiveUPIConfig.id == 1))).scalar_one_or_none()
    return {
        "accounts": [{
            "id": a.id, "upi_id": a.upi_id, "display_name": a.display_name,
            "daily_cap": a.daily_cap_inr, "current_volume": a.current_volume_inr,
            "is_active": a.is_active, "is_enabled": a.is_enabled,
        } for a in accts],
        "active_account_id": cfg.active_account_id if cfg else None,
    }


@router.post("/upi/rotate")
async def upi_rotate(db: AsyncSession = Depends(get_db)):
    svc = UPIPaymentService(db)
    return await svc.manual_rotate()


@router.get("/payments")
async def payments_list(limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(PaymentSession).order_by(PaymentSession.created_at.desc())
        .offset(offset).limit(limit))).scalars().all()
    return [{
        "ref_id": s.ref_id, "amount": s.amount_inr, "status": s.status,
        "upi_id": s.upi_id, "gateway": s.gateway, "utr": s.utr_number,
        "created_at": s.created_at.isoformat(),
    } for s in rows]


# ─── Calls ───────────────────────────────────────────────────────────

@router.get("/calls")
async def calls_list(limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(CallLog).order_by(CallLog.created_at.desc())
        .offset(offset).limit(limit))).scalars().all()
    return [{
        "run_id": c.dograh_run_id, "status": c.status, "duration": c.duration_seconds,
        "amount": c.amount_extracted, "created_at": c.created_at.isoformat(),
    } for c in rows]


# ─── Dograh workflow view ────────────────────────────────────────────

@router.get("/dograh/workflow")
async def dograh_workflow():
    import json
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent.parent / "config" / "dograh_workflow_onboarding.json"
    if not path.exists():
        return JSONResponse(status_code=404, content={"error": "workflow file not found"})
    return json.loads(path.read_text())


# ─── Logs / health ───────────────────────────────────────────────────

@router.get("/health-detail")
async def health_detail(db: AsyncSession = Depends(get_db)):
    from app.tasks.scheduler import check_service_health
    health = await check_service_health(db)
    return {
        "status": "ok",
        "services": health,
        "min_amount": settings.MIN_AMOUNT_INR,
        "max_amount": settings.MAX_AMOUNT_INR,
        "razorpay_configured": bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET),
        "wa_template": settings.WA_OPTIN_TEMPLATE_NAME,
        "dograh_base": settings.DOGRAH_API_URL,
        "generated_at": datetime.utcnow().isoformat(),
    }
