# Lead Pipeline Orchestrator

Autonomous lead-to-account conversion funnel powered by Hermes agent state machine, Dograh AI voice calls, WhatsApp Business API, and dynamic UPI payment with daily bank rotation.

## Architecture

```
[ Webhook / FB Ads / API Lead Drop ]
                 │
                 ▼
┌─────────────────────────────────────────────┐
│      ORCHESTRATOR (FastAPI State Machine)   │◄── [ Rotation DB: Today's Active UPI ]
└────┬──────────┬──────────┬──────────┬───────┘
     │          │          │          │
     ▼          ▼          ▼          ▼
[ WhatsApp ]  [ Dograh  ]  [ UPI QR  ]  [ Platform ]
[  Cloud   ]  [ Voice AI]  [ Payment ]  [   API   ]
```

## Pipeline Stages

| Stage | Status | Action |
|-------|--------|--------|
| 1 | `PENDING_WA_OPTIN` → `WA_SENT` | Ingest lead, send WhatsApp opt-in with "Yes, Call Me" button |
| 2 | `WA_REPLIED` → `CALL_TRIGGERED` | Classify intent, trigger Dograh outbound voice call |
| 3 | `CALL_COMPLETED` → `AMOUNT_CONFIRMED` | Parse transcript, extract deposit amount |
| 4 | `QR_GENERATED` → `AWAITING_PAYMENT` | Generate UPI deep-link QR with locked UPI ID, send via WA |
| 5 | `PAYMENT_RECEIVED` → `PAYMENT_VERIFIED` | Match incoming payment (amount + UTR + time window) |
| 6 | `ACCOUNT_CREATED` → `COMPLETED` | Provision platform account, deliver credentials via WA |

## Quick Start

```bash
# 1. Clone and enter
cd lead-pipeline

# 2. Run setup (generates secrets, builds images, starts services)
chmod +x scripts/setup.sh
./scripts/setup.sh

# 3. Edit .env with your real credentials
# 4. Open Dograh UI to create the onboarding voice agent
# 5. Configure your WhatsApp Business API webhook URL
```

## Configuration Checklist

### Dograh AI (Voice Calls)
- [ ] Open http://localhost:3010
- [ ] Create agent using `config/dograh_workflow_onboarding.json` (or build in UI)
- [ ] Configure Twilio telephony (Indian number for outbound calls)
- [ ] Set agent ID in `.env` → `DOGRAH_AGENT_ID`
- [ ] Add webhook node pointing to `http://orchestrator:9000/api/webhooks/dograh`

### WhatsApp Business API
- [ ] Create app in Meta Developer Portal
- [ ] Add WhatsApp product, get Phone Number ID
- [ ] Create message templates (opt-in, follow-up)
- [ ] Set webhook URL to `https://your-domain.com/api/webhooks/whatsapp`
- [ ] Subscribe to `messages` webhook field
- [ ] Set `.env` values: `WA_PHONE_NUMBER_ID`, `WA_ACCESS_TOKEN`, `WA_WEBHOOK_VERIFY_TOKEN`

### Telephony (Twilio)
- [ ] Buy Indian phone number (+91)
- [ ] Configure in Dograh dashboard under Telephony settings
- [ ] Set `.env` values: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`

### Payment (Razorpay / SMS Listener)
- [ ] Create Razorpay account, get API keys
- [ ] Set webhook URL to `https://your-domain.com/api/webhooks/payment/razorpay`
- [ ] OR: Set up Android device with MacroDroid → `/api/internal/bank-sms-listener`
- [ ] Add merchant UPI accounts in database via seed script

### Platform API
- [ ] Ensure `/api/v1/account/create` endpoint exists on your backend
- [ ] Set `.env` values: `PLATFORM_API_URL`, `PLATFORM_API_KEY`

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/webhooks/lead` | Ingest new lead (from Ads/CRM/n8n) |
| POST | `/api/webhooks/whatsapp` | WhatsApp message webhook |
| GET  | `/api/webhooks/whatsapp` | WhatsApp webhook verification |
| POST | `/api/webhooks/dograh` | Dograh post-call webhook |
| POST | `/api/webhooks/payment/razorpay` | Razorpay payment webhook |
| POST | `/api/internal/bank-sms-listener` | Android SMS reconciler webhook |
| POST | `/api/internal/payment-success` | Manual payment confirmation |
| GET  | `/api/upi/active` | Get current active UPI |
| POST | `/api/upi/rotate` | Manual UPI rotation |
| GET  | `/api/dashboard` | Pipeline stats |
| GET  | `/health` | Health check |

## Daily UPI Rotation

Bank accounts rotate automatically at 00:01 IST via cron. Each payment session permanently records its `upi_id` and `bank_id` — if the global active bank changes mid-session, payment reconciliation still resolves correctly.

Override: `POST /api/upi/rotate` for manual rotation.

## SMS Reconciliation (Non-Gateway Accounts)

For personal/current accounts without payment webhooks:

1. Dedicated Android device with bank SIM cards, plugged in 24/7
2. Install MacroDroid/Tasker
3. Trigger on incoming SMS containing "Credited" + "UPI Ref"
4. Extract Amount, UTR, Timestamp
5. POST to `/api/internal/bank-sms-listener`

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Orchestrator | Python FastAPI + SQLAlchemy async |
| Database | PostgreSQL 16 |
| Cache/Locks | Redis 7 |
| Voice AI | Dograh AI (self-hosted) |
| Telephony | Twilio (Indian numbers) |
| Messaging | Meta WhatsApp Cloud API |
| Payments | Razorpay / UPI direct + SMS reconciler |
| QR Codes | python-qrcode (local) or QuickChart CDN |
| Deployment | Docker Compose |
