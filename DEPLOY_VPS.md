# Lead Pipeline Orchestrator — VPS Deployment Guide

Complete autonomous lead-to-account conversion pipeline. This document contains ALL credentials, API keys, and configuration needed to deploy the system on a fresh VPS.

---

## Overview

Flow: Meta Ad → WhatsApp Opt-in → Dograh AI Voice Call → Razorpay/UPI Payment → Instant Account Provisioning

Current state: Fully functional on Mac Mini at home. This guide lets you clone onto any VPS with Docker.

---

## 1. System Architecture

```
[ Webhook / FB Ads / API Lead Drop ]
                 |
                 v
+---------------------------------------------+
|      ORCHESTRATOR (FastAPI State Machine)   |<-- [ Rotation DB: Today's Active UPI ]
+----+---------+---------+---------+----------+
     |         |         |         |
     v         v         v         v
[ WhatsApp ] [ Dograh  ] [ UPI QR  ] [ Platform ]
[  Cloud   ] [ Voice AI] [ Payment ] [ Provision]
```

### Containers (Docker Compose)

| Container | Port | Purpose |
|-----------|------|---------|
| orchestrator | 9000 | FastAPI state machine |
| postgres | 5432 | Lead database |
| redis | 6379 | Session state, timers |
| dograh | 8000 (API), 3010 (UI) | Voice AI platform |
| dograh-redis | - | Dograh's redis |
| dograh-postgres | - | Dograh's postgres |
| dograh-minio | 9001 | Dograh's S3-compatible storage |
| dograh-ui | 3010 | Dograh admin UI |

---

## 2. Prerequisites

- Ubuntu 22.04+ or Debian 12+
- Docker 24+ & Docker Compose v2
- Git
- Python 3.10+
- Domain or public IP (for webhooks — WhatsApp/Razorpay need HTTPS)
- Nginx + Certbot (for SSL termination — required by Meta webhooks)

---

## 3. Server Setup

```bash
# Update system
apt update && apt upgrade -y
apt install -y docker.io docker-compose-v2 git nginx certbot python3-certbot-nginx

# Start Docker
systemctl enable --now docker

# Clone repo
git clone https://github.com/abdullah917071/lead-pipeline.git /opt/lead-pipeline
cd /opt/lead-pipeline
```

---

## 4. SSL / Domain Setup

Meta WhatsApp API and Razorpay REQUIRE HTTPS webhooks.

```bash
# Set up Nginx reverse proxy
cat > /etc/nginx/sites-available/lead-pipeline << 'EOF'
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:9000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

ln -s /etc/nginx/sites-available/lead-pipeline /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

# Get SSL cert
certbot --nginx -d your-domain.com --non-interactive --agree-tos -m your@email.com
```

---

## 5. Environment File (.env)

Create `/opt/lead-pipeline/.env` with the following content:

```bash
DEBUG=false
DATABASE_URL=postgresql+asyncpg://pipeline:pipeline@postgres:5432/leadpipeline
REDIS_URL=redis://:pipeline@redis:6379/0

# Dograh AI Voice Platform
DOGRAH_API_URL=http://dograh:8000
DOGRAH_API_KEY=dgr_Y0tY4gHogYRKIo0kVvciNtBKAAHVyWskRVe3Y1shRIg
DOGRAH_AGENT_ID=2
DOGRAH_TRIGGER_PATH=eb155119-43b7-4410-a94b-b9b331455fbb
DOGRAH_TELEPHONY_CONFIG_ID=3
DOGRAH_WORKFLOW_UUID=2
DOGRAH_TUNNEL_URL=https://confidential-prophet-foam-farms.trycloudflare.com

# WhatsApp Business API
WA_API_URL=https://graph.facebook.com/v21.0
WA_PHONE_NUMBER_ID=1227078997152468
WA_BUSINESS_ACCOUNT_ID=2202368716902450
WA_ACCESS_TOKEN=EAAHuFJSJqDABSI3I4O11j2G5J5GqPjcr6qTRFTHYIw4lFkjtB9gpTALPc9xQQZAnFjgS2BGYdPgFrvkfIMTkeTvmBTKa13ZBcEbDtJWOAoONZCub0MgL6ZCRQxQGwDd7p3mAFLtDMMdBFafOSE3wh7ROTy1WPAXumhxU82UtxItiysC2G1YY6ajYYffSUisriAZDZD
WA_WEBHOOK_VERIFY_TOKEN=suppremo_wa_verify_2026

# UPI Payment
UPI_MERCHANT_NAME=Sai Bhai
PAYMENT_SESSION_EXPIRY_MINUTES=15

# Platform API (account provisioning backend)
PLATFORM_API_URL=http://localhost:8000
PLATFORM_API_KEY=*** (replace with actual platform API key)
PLATFORM_APP_DOWNLOAD_URL=https://suppremo.in/download
QR_SERVICE=local

# Telnyx (telephony for Dograh voice calls)
TELNYX_API_KEY=KFY019...WHrW  (replace with full key from Dograh Telnyx settings)
TELNYX_PHONE_NUMBER=+1682****4752  (replace with actual Telnyx number)

# Razorpay (dynamic QR + payment webhook)
RAZORPAY_KEY_ID=rzp_live_TFinDozUMuqMCp
RAZORPAY_KEY_SECRET=MDMbgqTLdsvgzW7cgK66g8GI
RAZORPAY_WEBHOOK_SECRET=suppremo_razorpay_webhook_2026
RAZORPAY_API_URL=https://api.razorpay.com/v1

# Amount Limits
MIN_AMOUNT_INR=1
MAX_AMOUNT_INR=100000

# WhatsApp Opt-in Template
WA_OPTIN_TEMPLATE_NAME=saibhai
WA_OPTIN_IMAGE_URL=https://blog.suppremo.in/wp-content/uploads/wa-welcome.jpg
```

---

## 6. Dograh Setup

After running `docker compose up -d` (step 7), configure Dograh:

### 6.1 Log into Dograh UI
- URL: `http://your-vps-ip:3010`
- First-run setup creates admin credentials

### 6.2 Create Agent Workflow
Import `config/dograh_workflow_onboarding.json` into Dograh UI, or recreate manually:

**Workflow ID: 2, Agent ID: 2, Trigger Path:** `eb155119-43b7-4410-a94b-b9b331455fbb`

The workflow has 4 nodes:
1. **Welcome & Confirm** — startCall node, greets customer, asks deposit amount
2. **Negotiate Amount** — agentNode, helps undecided customers pick amount
3. **Final Confirmation** — agentNode, double-confirms the amount
4. **End Call** — endCall node, thanks customer
5. **Notify Orchestrator** — webhook node, POSTs to orchestrator at `/api/webhooks/dograh`
6. **QA Analysis** — QA node, evaluates call quality

Webhook URL (in the config): `http://10.234.52.162:9000/api/webhooks/dograh`
Change this to: `https://your-domain.com/api/webhooks/dograh`

### 6.3 Configure Telnyx Telephony
- In Dograh UI > Telephony Settings
- Telephony Config ID: 3
- Telnyx API Key and Phone Number (from .env)
- **IMPORTANT:** Do NOT send a 'to' field in the trigger payload — Dograh's Telnyx config rejects 'to' with 422 error. Only 'phone_number' + 'telephony_configuration_id' are needed.

---

## 7. Launch

```bash
cd /opt/lead-pipeline

# Build orchestrator image
docker compose build orchestrator

# Start infrastructure
docker compose up -d postgres redis dograh-redis dograh-postgres dograh-minio
sleep 10

# Start Dograh
docker compose up -d dograh dograh-ui
sleep 30  # Give Dograh time to initialize DB schema

# Start orchestrator
docker compose up -d orchestrator

# Seed initial merchant UPI accounts
docker compose exec orchestrator python -m scripts.seed_db
```

### Verify Health

```bash
curl http://localhost:9000/health
# Expected: {"status":"ok","service":"lead-pipeline-orchestrator","version":"3.0.0"}

curl http://localhost:9000/docs
# Should show Swagger UI
```

---

## 8. Webhook Configuration

### 8.1 WhatsApp Cloud API

Register webhook in Meta Developer Dashboard:
- **Callback URL:** `https://your-domain.com/api/webhooks/whatsapp`
- **Verify Token:** `suppremo_wa_verify_2026`
- **Webhook Fields:** `messages`

After registration, the orchestrator handles:
- `GET /api/webhooks/whatsapp` — verification challenge
- `POST /api/webhooks/whatsapp` — incoming messages + button clicks

**IMPORTANT:** WhatsApp Cloud API webhook registration is ONLY possible via Meta Developer Dashboard UI (WhatsApp > Configuration > Webhook). Graph API endpoints (`/callbacks`, `/subscriptions`, `/webhooks`) return errors for Cloud API numbers.

**WhatsApp Details:**
- Phone Number ID: `1227078997152468`
- Business Account ID: `2202368716902450`
- API Version: `v21.0`
- Opt-in Template: `saibhai` (approved template with image header + body variable)
- Template Image: `https://blog.suppremo.in/wp-content/uploads/wa-welcome.jpg`

### 8.2 Razorpay Webhook

Register in Razorpay Dashboard > Settings > Webhooks:
- **Webhook URL:** `https://your-domain.com/api/webhooks/payment/razorpay`
- **Events:** `payment.captured`, `payment.failed`, `qr_code.closed`
- **Secret:** `suppremo_razorpay_webhook_2026`

The endpoint verifies `X-Razorpay-Signature` header using HMAC SHA256 before processing.

---

## 9. Pipeline State Machine (16 States)

| # | Status | Description |
|---|--------|-------------|
| 1 | `pending_wa_optin` | Lead created, awaiting WhatsApp opt-in send |
| 2 | `wa_sent` | Opt-in message sent, awaiting reply |
| 3 | `wa_replied` | User clicked "Interested" or said yes |
| 4 | `call_triggered` | Dograh outbound call initiated |
| 5 | `call_completed` | Voice call completed successfully |
| 6 | `call_failed` | Call failed (voicemail, no answer) |
| 7 | `amount_confirmed` | Deposit amount extracted from call |
| 8 | `qr_generated` | Razorpay/UPI QR code generated |
| 9 | `awaiting_payment` | QR sent, waiting for payment |
| 10 | `payment_received` | Razorpay webhook or SMS received |
| 11 | `payment_verified` | Payment matched to session |
| 12 | `account_created` | Platform account provisioned |
| 13 | `credentials_delivered` | Login credentials sent via WhatsApp |
| 14 | `completed` | Pipeline fully complete |
| 15 | `cold` | No reply after 24h |
| 16 | `rejected` | User declined / not interested |
| 17 | `payment_failed` | Payment failed |
| 18 | `manual_review` | Requires human intervention |

---

## 10. API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/webhooks/lead` | Ingest new lead (from Ads/CRM/n8n) |
| POST | `/api/webhooks/whatsapp` | WhatsApp message webhook |
| GET | `/api/webhooks/whatsapp` | WhatsApp webhook verification |
| POST | `/api/webhooks/dograh` | Dograh post-call webhook |
| POST | `/api/webhooks/payment/razorpay` | Razorpay payment webhook |
| POST | `/api/internal/bank-sms-listener` | Android SMS reconciler |
| POST | `/api/internal/payment-success` | Manual payment confirmation |
| GET | `/api/upi/active` | Current active UPI account |
| POST | `/api/upi/rotate` | Manual UPI rotation |
| GET | `/api/dashboard` | Pipeline stats |
| GET | `/api/leads` | List leads (optional ?status= filter) |
| GET | `/api/leads/{id}` | Full lead detail with sessions & calls |
| GET | `/health` | Health check |
| GET | `/docs` | Swagger UI |
| GET | `/redoc` | ReDoc UI |

---

## 11. Ingesting a Lead (via API)

```bash
curl -X POST https://your-domain.com/api/webhooks/lead \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test User",
    "phone": "919235587822",
    "source": "facebook_ads",
    "utm_campaign": "test_campaign"
  }'
```

Response:
```json
{
  "id": "uuid",
  "phone": "919235587822",
  "name": "Test User",
  "status": "wa_sent",
  "created_at": "...",
  "updated_at": "..."
}
```

---

## 12. Background Tasks (Scheduler)

The scheduler runs 3 tasks automatically:

| Task | Interval | What it does |
|------|----------|-------------|
| `expire_sessions_task` | Every 60s | Expire old payment sessions, log them |
| `followup_task` | Every 60min | Send 12h follow-up WhatsApp, mark cold at 24h |
| `daily_upi_rotation` | Every 60min (triggers at 18:30 UTC = 00:00 IST) | Rotate active UPI merchant account |

---

## 13. UPI Rotation System

- Multiple merchant UPI accounts stored in `merchant_accounts` table
- Active account tracked in `active_upi_config` table
- Rotates daily at midnight IST (18:30 UTC)
- Each payment session records its `upi_id` and `bank_id` — if the active bank changes mid-session, payment reconciliation still resolves correctly
- Manual override: `POST /api/upi/rotate`
- Volume tracking: each account has `daily_cap_inr` and `current_volume_inr`
- Rotation log: `upi_rotation_log` table tracks every change

**Seed command** (add merchant accounts):
```bash
docker compose exec orchestrator python -c "
from app.models.database import MerchantAccount
from app.db_session import SessionLocal
import asyncio

async def seed():
    async with SessionLocal() as db:
        accounts = [
            MerchantAccount(id='icici_01', upi_id='merchant1@icici', display_name='ICICI Bank - Main', daily_cap_inr=50000),
            MerchantAccount(id='hdfc_01', upi_id='merchant2@hdfc', display_name='HDFC Bank', daily_cap_inr=75000),
            MerchantAccount(id='sbi_01', upi_id='merchant3@sbi', display_name='SBI', daily_cap_inr=100000),
        ]
        for a in accounts:
            db.add(a)
        await db.commit()
        print('Merchant accounts seeded')

asyncio.run(seed())
"
```

---

## 14. SMS Bank Reconciliation (Alternative Payment Confirm)

For non-Razorpay payment methods, set up an Android device with bank SIM cards:

1. Install MacroDroid/Tasker on Android
2. Trigger: Incoming SMS containing "Credited" + "UPI Ref"
3. Extract: Amount, UTR number, Timestamp
4. POST to: `https://your-domain.com/api/internal/bank-sms-listener`

Payload format:
```json
{
  "amount": 500.00,
  "utr": "123456789012",
  "sender": "paytm"
}
```

---

## 15. Service Architecture (Files)

### `/opt/lead-pipeline/app/`

| File | Lines | Purpose |
|------|-------|---------|
| `main.py` | 432 | FastAPI app, all webhook routes, dashboard endpoint |
| `config.py` | 18 | Pydantic settings (reads .env) |
| `db_session.py` | 16 | Async DB session factory |
| `schemas.py` | 80 | Pydantic models for request/response |

### Services (`app/services/`)

| File | Lines | Purpose |
|------|-------|---------|
| `orchestrator.py` | 225 | Central state machine — handles all pipeline transitions |
| `lead_service.py` | 106 | Lead CRUD, phone normalization, status advancement |
| `whatsapp_service.py` | 191 | 12 WhatsApp API methods (template, text, image, interactive, QR, credentials) |
| `dograh_service.py` | 154 | Trigger outbound calls, process call webhooks, record failures |
| `upi_service.py` | 242 | QR generation (Razorpay + local), payment matching, daily rotation |
| `razorpay_service.py` | 170 | Dynamic QR creation, webhook signature verification, QR management |
| `provisioning_service.py` | 80 | Generate user accounts, send credentials via WhatsApp |

### Other

| File | Purpose |
|------|---------|
| `app/models/database.py` | 9 SQLAlchemy models: Lead, PaymentSession, CallLog, WAMessage, MerchantAccount, ActiveUPIConfig, UPIRotationLog, ProvisionedAccount, PipelineSetting |
| `app/tasks/scheduler.py` | 3 background tasks (session expiry, follow-ups, UPI rotation) |
| `app/routers/admin.py` | Admin dashboard routes |
| `scripts/setup.sh` | One-shot setup script |
| `scripts/seed_db.py` | Seed initial data |
| `scripts/make_call.py` | Test outbound call |
| `deploy/Dockerfile` | Docker image build |
| `config/dograh_workflow_onboarding.json` | Dograh workflow import |
| `dashboard/` | Next.js admin dashboard |

---

## 16. Monitoring & Logs

```bash
# View orchestrator logs
docker compose logs -f orchestrator

# View all services
docker compose logs -f

# Check health endpoint
curl https://your-domain.com/health

# Dashboard API
curl https://your-domain.com/api/dashboard

# List all leads
curl https://your-domain.com/api/leads
```

### Health Check Response
```json
{
  "status": "ok",
  "service": "lead-pipeline-orchestrator",
  "version": "3.0.0"
}
```

### Dashboard Response
```json
{
  "total_leads": 42,
  "pending_optin": 5,
  "wa_sent": 12,
  "calls_in_progress": 3,
  "calls_completed": 8,
  "awaiting_payment": 4,
  "payments_received": 6,
  "completed": 4,
  "cold": 2,
  "rejected": 1,
  "total_payment_value": 12500.0,
  "active_upi": "merchant1@icici",
  "active_bank": "ICICI Bank - Main",
  "service_health": {
    "dograh": {"status": "healthy"},
    "whatsapp": {"status": "healthy"},
    "platform_api": {"status": "healthy"}
  },
  "razorpay_configured": true
}
```

---

## 17. Quick Troubleshooting

| Problem | Solution |
|---------|----------|
| WhatsApp webhook verification fails | Check verify_token matches `.env` exactly (`suppremo_wa_verify_2026`) |
| Dograh call not triggering | Check Telnyx config in Dograh UI, verify `DOGRAH_API_KEY` and `DOGRAH_TRIGGER_PATH` |
| QR not generating | Verify Razorpay keys, check if payment session expiry is reasonable |
| Payment not matching | Check `ref_id` in Razorpay notes matches our payment session |
| Credentials not sending | Check `PLATFORM_API_KEY` and `PLATFORM_API_URL` |
| Container won't start | `docker compose logs <service>` for details |
| Port conflict | Change host port in `docker-compose.yaml` (e.g., `9000:9000` → `9001:9000`) |

---

## 18. Security Notes

- This repo is **private** — keep it that way (contains live API keys)
- Rotate WhatsApp access token every 60 days via Meta Dashboard
- Rotate Razorpay webhook secret periodically
- Use nginx IP whitelisting if possible for internal webhooks
- Consider changing `PLATFORM_API_KEY` to a dedicated key with minimal permissions
- The Dograh `trigger_path` (`eb155119-43b7-4410-a94b-b9b331455fbb`) is effectively a public endpoint — Dograh authenticates via `X-API-Key` header

---

**Deployment Checklist:**
- [ ] Clone repo on VPS
- [ ] Create .env with credentials above
- [ ] Set up domain + SSL via nginx + certbot
- [ ] Run `docker compose up -d`
- [ ] Configure Dograh workflow in UI (import config or recreate)
- [ ] Set up Telnyx telephony in Dograh
- [ ] Register WhatsApp webhook in Meta Dashboard
- [ ] Register Razorpay webhook in Razorpay Dashboard
- [ ] Test: POST new lead to /api/webhooks/lead
- [ ] Verify: lead receives WhatsApp opt-in
- [ ] Verify: clicking "Interested" triggers Dograh call
- [ ] Verify: payment flow works end-to-end