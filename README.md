# Lead Pipeline

Production WhatsApp-to-call-to-payment conversion service.

A lead enters from CRM, ads, or WhatsApp, opts in through Meta, receives an outbound Hindi/Hinglish AI call through Dograh + Telnyx, confirms a deposit amount, receives a Razorpay QR on WhatsApp, and receives account credentials only after verified payment.

## Current Flow

```text
Inbound lead / first WhatsApp message
  → create or re-engage active lead
  → approved Meta opt-in template with Interested button
  → customer taps Interested
  → WhatsApp call notice + Dograh/Telnyx outbound call
  → qualification → offer → proposed amount → explicit confirmation
  → Razorpay dynamic QR is created and sent to WhatsApp during the call
  → verified Razorpay payment webhook
  → downstream account provisioning → credentials sent on WhatsApp
```

The initial inbound WhatsApp message is never treated as consent. The pipeline waits for the Interested button tap.

## Features

- Meta WhatsApp Cloud API integration with template opt-in, button handling, QR image delivery, and credentials delivery.
- Webhook isolation: inbound Meta payloads are accepted only when their `metadata.phone_number_id` matches `WA_PHONE_NUMBER_ID`.
- Active-lead-first phone deduplication, preventing old terminal records from blocking a new reply.
- Dograh + Telnyx outbound calls with Hindi/Hinglish workflow support.
- Strict amount flow: proposed amount, explicit confirmation, then QR.
- One-second mid-call poller reads Dograh `workflow_runs.gathered_context` and sends the QR without waiting for call completion.
- Safe QR fallback: if Dograh reaches the `Payment QR` node but omits `confirmed_amount`, the poller uses `proposed_amount` only at that confirmed stage.
- Razorpay dynamic QR creation and signed webhook payment verification.
- Exact paise matching for referenced QR payments; a mismatched or expired QR is never credited.
- One-time Telnyx media-start recovery for answered calls with zero inbound and outbound audio packets.
- Optional internal OpenAI-compatible Gemini Vertex bridge for Dograh pipeline calls, including streamed responses and function calls.
- Optional Gemini Live native-audio Dograh overlay with Telnyx 8 kHz → Gemini 16 kHz audio resampling.
- PostgreSQL state machine, Redis, Docker Compose, and Next.js operations dashboard.

## Lead States

| Stage | Status | Meaning |
|---|---|---|
| Opt-in | `PENDING_WA_OPTIN` → `WA_SENT` | Lead exists and the approved Meta opt-in was sent. |
| Consent | `WA_REPLIED` → `CALL_TRIGGERED` | Interested reply triggered the voice call. |
| Payment request | `AWAITING_PAYMENT` | Razorpay QR was successfully created and sent on WhatsApp. |
| Payment | `PAYMENT_RECEIVED` → `PAYMENT_VERIFIED` | Razorpay event was verified and matched to the active payment session. |
| Delivery | `ACCOUNT_CREATED` → `COMPLETED` | Credentials were provisioned and delivered. |

Sink/retry states include `CALL_FAILED`, `COLD`, and `REJECTED`.

## Services

| Service | Purpose |
|---|---|
| `orchestrator` | FastAPI API, lead state machine, Meta/Razorpay webhooks, QR coordination |
| `postgres` | Leads, call logs, payment sessions, provisioned credentials |
| `redis` | Runtime support and caching |
| `dograh` | Voice workflow engine and call-run context |
| `dograh-postgres` | Dograh workflow definitions and `workflow_runs` used by the QR poller |
| Telnyx | Outbound telephony and media transport |
| Meta WhatsApp Cloud API | Opt-in templates, QR delivery, payment/credential messages |
| Razorpay | Dynamic QR creation and payment events |
| `dashboard` | Next.js operations UI |

## Deploy

```bash
cd /opt/lead-pipeline
cp .env.example .env
# Fill every CHANGEME value in .env. Never commit .env or .env.dograh.
docker compose build
docker compose up -d
curl -fsS http://localhost:9000/health
```

Production webhook endpoints are served through the public reverse proxy:

```text
https://your-domain.example/api/webhooks/whatsapp
https://your-domain.example/api/webhooks/payment/razorpay
```

## Configuration

Use `.env` or a secrets manager. `.env` and `.env.dograh` are gitignored.

| Area | Required variables |
|---|---|
| Core | `DATABASE_URL`, `REDIS_URL`, `DEBUG` |
| Dograh / Telnyx | `DOGRAH_API_URL`, `DOGRAH_API_KEY`, `DOGRAH_TRIGGER_PATH`, `DOGRAH_TELEPHONY_CONFIG_ID`, `DOGRAH_WORKFLOW_ID`, `DOGRAH_DATABASE_URL` |
| QR poller | `MIDCALL_POLL_INTERVAL_SECONDS=1` |
| WhatsApp | `WA_API_URL`, `WA_PHONE_NUMBER_ID`, `WA_ACCESS_TOKEN`, `WA_WEBHOOK_VERIFY_TOKEN`, `WA_OPTIN_TEMPLATE_NAME`, `WA_OPTIN_IMAGE_URL` |
| Razorpay | `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`, `RAZORPAY_API_URL` |
| Limits | `MIN_AMOUNT_INR`, `MAX_AMOUNT_INR`, `PAYMENT_SESSION_EXPIRY_MINUTES` |
| Provisioning | `PLATFORM_API_URL`, `PLATFORM_API_KEY`, `PLATFORM_APP_DOWNLOAD_URL` |
| Optional Gemini Vertex bridge | `GEMINI_VERTEX_API_KEY`, `GEMINI_VERTEX_PROJECT_ID`, `GEMINI_VERTEX_LOCATION`, `GEMINI_VERTEX_PROXY_TOKEN` |

See `.env.example` for the complete safe template.

## HTTP Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/webhooks/lead` | Create/re-engage a lead and send opt-in |
| `GET`, `POST` | `/api/webhooks/whatsapp` | Meta verification and inbound WhatsApp events |
| `POST` | `/api/webhooks/dograh` | Dograh completion callback |
| `POST` | `/api/webhooks/dograh-midcall` | Optional immediate amount callback |
| `POST` | `/api/webhooks/payment/razorpay` | Razorpay payment event |
| `POST` | `/api/admin/leads/{id}/resend-qr?amount=500` | Manually regenerate/send a QR |
| `GET` | `/health` | Orchestrator liveness |
| `GET` | `/api/admin/health-detail` | Dependency health checks |
| `POST` | `/internal/gemini-vertex/v1/chat/completions` | Authenticated internal OpenAI-compatible Vertex bridge |

## QR Delivery Contract

1. The customer gives a valid amount.
2. The call confirms that exact amount.
3. Dograh enters the `Payment QR` node.
4. The poller creates a single Razorpay QR and sends the image through Meta WhatsApp.
5. The payment QR is marked `AWAITING_PAYMENT` only after Meta accepts the send.

The poller is the durable path. It primarily uses `confirmed_amount`; if Dograh has entered `Payment QR` but persisted only `proposed_amount`, it safely uses that value because the workflow transition itself requires explicit confirmation. It never uses a proposed amount before that stage.

## Operations

```bash
# Rebuild/recreate only the orchestrator after Python changes
cd /opt/lead-pipeline
docker compose build orchestrator
docker compose rm -sf orchestrator
docker compose create orchestrator
docker compose start orchestrator
curl -fsS http://localhost:9000/health

# Rebuild/restart Dograh after deploy/dograh or workflow-runtime changes
cd /opt/lead-pipeline
docker compose build dograh
docker compose up -d --force-recreate dograh
curl -fsS http://localhost:8000/api/v1/health

# Inspect recent QR attempts
 docker logs lp-orchestrator --since 15m 2>&1 | grep -Ei 'mid-call|QR sent|razorpay'
```

Dograh workflow changes must update the released workflow definition and `workflows.released_definition_id`, then restart Dograh. Webhook nodes must be standalone; the DB poller is the QR delivery fallback.

## Tests

The production image contains application dependencies but does not copy test files. Run the suite with the source test directory mounted:

```bash
cd /opt/lead-pipeline
docker run --rm \
  -v "$PWD/tests:/app/tests:ro" \
  lead-pipeline-orchestrator \
  python3 -m unittest discover -s /app/tests -v
```

Regression coverage includes:

- WhatsApp phone-number-ID isolation and button reply behavior
- Active lead selection for duplicate phone records
- Razorpay expiry and exact-paise payment matching
- QR WhatsApp message content and confirmed-stage fallback
- Scheduler health checks and Telnyx media-start retry detection
- Gemini Vertex request/response conversion
- Gemini Live Telnyx audio resampling and workflow transition support

## Security

- Do not commit `.env`, `.env.dograh`, API keys, webhook secrets, or credentials.
- Meta webhooks are scoped to the configured WhatsApp phone-number ID.
- The internal Gemini Vertex bridge requires `Authorization: Bearer $GEMINI_VERTEX_PROXY_TOKEN` and must remain internal to the Docker network/reverse-proxy access policy.
- Razorpay webhook signatures must be configured and verified before payment processing.
