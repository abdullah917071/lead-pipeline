# Lead Pipeline

[![Build Status](https://img.shields.io/badge/build-passing-brightgreen)](https://github.com/abdullah917071/lead-pipeline/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Production WhatsApp-to-call-to-payment conversion service.

A lead enters from CRM, ads, or WhatsApp, opts in through Meta, receives an outbound Hindi/Hinglish AI call through Dograh + Telnyx, confirms a deposit amount, receives a Razorpay QR on WhatsApp, and receives account credentials only after verified payment.

## Overview

The Lead Pipeline automates the entire lead-to-customer journey for high-value services, combining WhatsApp automation, AI-powered voice calls, and secure payment processing.

## Features

- **Meta WhatsApp Cloud API integration** with template opt-in, button handling, QR image delivery, and credentials delivery.
- **Webhook isolation**: inbound Meta payloads accepted only when `metadata.phone_number_id` matches `WA_PHONE_NUMBER_ID`.
- **Active-lead-first phone deduplication**, preventing old terminal records from blocking a new reply.
- **Dograh + Telnyx outbound calls** with Hindi/Hinglish workflow support.
- **Strict amount flow**: proposed amount → explicit confirmation → QR generation.
- **One-second mid-call poller** reads Dograh `workflow_runs.gathered_context` and sends QR without waiting for call completion.
- **Safe QR fallback**: if Dograh reaches the `Payment QR` node but omits `confirmed_amount`, the poller uses `proposed_amount` at the confirmed stage.
- **Razorpay dynamic QR creation** and signed webhook payment verification.
- **Exact paise matching** for referenced QR payments; mismatched or expired QR never credited.
- **One-time Telnyx media-start recovery** for answered calls with zero inbound/outbound audio packets.
- **Optional internal OpenAI-compatible Gemini Vertex bridge** for Dograh pipeline calls, including streamed responses and function calls.
- **Optional Gemini Live native-audio Dograh overlay** with Telnyx 8 kHz → Gemini 16 kHz audio resampling.
- **PostgreSQL state machine**, Redis, Docker Compose, and Next.js operations dashboard.

## Lead States

| Stage | Status | Meaning |
|-------|--------|---------|
| Opt-in | `PENDING_WA_OPTIN` → `WA_SENT` | Lead exists and the approved Meta opt-in was sent. |
| Consent | `WA_REPLIED` → `CALL_TRIGGERED` | Interested reply triggered the voice call. |
| Payment request | `AWAITING_PAYMENT` | Razorpay QR was successfully created and sent on WhatsApp. |
| Payment | `PAYMENT_RECEIVED` → `PAYMENT_VERIFIED` | Razorpay event was verified and matched to the active payment session. |
| Delivery | `ACCOUNT_CREATED` → `COMPLETED` | Credentials were provisioned and delivered. |

Sink/retry states include `CALL_FAILED`, `COLD`, and `REJECTED`.

## Services

| Service | Purpose |
|---------|---------|
| `orchestrator` | FastAPI API, lead state machine, Meta/Razorpay webhooks, QR coordination |
| `postgres` | Leads, call logs, payment sessions, provisioned credentials |
| `redis` | Runtime support and caching |
| `dograh` | Voice workflow engine and call-run context |
| `dograh-postgres` | Dograh workflow definitions and `workflow_runs` used by the QR poller |
| Telnyx | Outbound telephony and media transport |
| Meta WhatsApp Cloud API | Opt-in templates, QR delivery, payment/credential messages |
| Razorpay | Dynamic QR creation and payment events |
| `dashboard` | Next.js operations UI |

## Deployment

### Prerequisites

- Docker Engine (v20.10+)
- Docker Compose (v2.0+)
- Git
- Access to Meta WhatsApp Cloud API, Telnyx, and Razorpay accounts

### Quick Start

```bash
# Clone the repository
git clone https://github.com/abdullah917071/lead-pipeline.git
cd lead-pipeline

# Copy environment template and configure
cp .env.example .env
cp .env.dograh.example .env.dograh  # If available

# Edit .env and .env.dograh with your actual credentials (never commit these files)
# !! IMPORTANT: Replace all CHANGEME values !!

# Build and start all services
docker compose build
docker compose up -d

# Verify the orchestrator is healthy
curl -fsS http://localhost:9000/health
# Should return: {"status":"ok"}

# Access the dashboard at http://localhost:3000
```

### Production Notes

- The orchestrator runs on port 9000 (health endpoint at `/health`)
- Dograh API is available at port 8000
- Dograh UI is available at port 3011
- Dashboard is available at port 3000
- All services restart automatically unless stopped manually
- For production, ensure you have a proper reverse proxy (NGINX) set up with SSL termination

## Configuration

Use `.env` for orchestrator secrets and `.env.dograh` for Dograh-specific settings. Both files are gitignored.

### Core Variables (in `.env`)

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string (default: `postgresql+asyncpg://pipeline:pipeline@postgres:5432/leadpipeline`) |
| `REDIS_URL` | Redis connection string (default: `redis://:pipeline@redis:6379/0`) |
| `DEBUG` | Set to `true` for development, `false` for production |

### Dograh / Telnyx Variables (in `.env`)

| Variable | Description |
|----------|-------------|
| `DOGRAH_API_URL` | Internal Dograh API URL (default: `http://dograh:8000`) |
| `DOGRAH_API_KEY` | API key for Dograh authentication |
| `DOGRAH_TRIGGER_PATH` | Workflow trigger UUID from Dograh |
| `DOGRAH_TELEPHONY_CONFIG_ID` | Telephony configuration ID (default: `3`) |
| `DOGRAH_WORKFLOW_ID` | Workflow ID to execute (default: `1`) |
| `DOGRAH_DATABASE_URL` | Dograh's PostgreSQL connection string |
| `MIDCALL_POLL_INTERVAL_SECONDS` | How often to poll for mid-call context (default: `1`) |

### WhatsApp Variables (in `.env`)

| Variable | Description |
|----------|-------------|
| `WA_API_URL` | Meta Graph API base URL |
| `WA_PHONE_NUMBER_ID` | Your WhatsApp Business phone number ID |
| `WA_ACCESS_TOKEN` | Permanent access token for WhatsApp API |
| `WA_WEBHOOK_VERIFY_TOKEN` | Token for webhook verification |
| `WA_OPTIN_TEMPLATE_NAME` | Name of the approved opt-in template |
| `WA_OPTIN_IMAGE_URL` | URL to the opt-in image (hosted publicly) |

### Razorpay Variables (in `.env`)

| Variable | Description |
|----------|-------------|
| `RAZORPAY_KEY_ID` | Razorpay key ID |
| `RAZORPAY_KEY_SECRET` | Razorpay key secret |
| `RAZORPAY_WEBHOOK_SECRET` | Secret for verifying webhook signatures |
| `RAZORPAY_API_URL` | Razorpay API base URL |
| `MIN_AMOUNT_INR` | Minimum transaction amount in INR |
| `MAX_AMOUNT_INR` | Maximum transaction amount in INR |
| `UPI_MERCHANT_NAME` | Name displayed on UPI QR |
| `PAYMENT_SESSION_EXPIRY_MINUTES` | How long a payment session remains valid |

### Provisioning Variables (in `.env`)

| Variable | Description |
|----------|-------------|
| `PLATFORM_API_URL` | URL of the downstream account provisioning API |
| `PLATFORM_API_KEY` | API key for provisioning service |
| `PLATFORM_APP_DOWNLOAD_URL` | URL where users can download the application |

### Optional Gemini Vertex Bridge (in `.env`)

| Variable | Description |
|----------|-------------|
| `GEMINI_VERTEX_API_KEY` | API key for Gemini Vertex (if used) |
| `GEMINI_VERTEX_PROJECT_ID` | Google Cloud project ID |
| `GEMINI_VERTEX_LOCATION` | Google Cloud region (default: `us-central1`) |
| `GEMINI_VERTEX_PROXY_TOKEN` | Token for internal proxy authentication |

## HTTP Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/api/webhooks/lead` | Create/re-engage a lead and send opt-in |
| `GET`, `POST` | `/api/webhooks/whatsapp` | Meta verification and inbound WhatsApp events |
| `POST` | `/api/webhooks/dograh` | Dograh completion callback |
| `POST` | `/api/webhooks/dograh-midcall` | Optional immediate amount callback |
| `POST` | `/api/webhooks/payment/razorpay` | Razorpay payment event |
| `POST` | `/internal/gemini-vertex/v1/chat/completions` | Authenticated internal OpenAI-compatible Vertex bridge |
| `GET` | `/health` | Orchestrator liveness check |
| `GET` | `/api/admin/health-detail` | Dependency health checks |
| `POST` | `/admin/leads/{id}/resend-qr?amount=500` | Manually regenerate/send a QR |

## QR Delivery Contract

1. The customer gives a valid amount.
2. The call confirms that exact amount.
3. Dograh enters the `Payment QR` node.
4. The poller creates a single Razorpay QR and sends the image through Meta WhatsApp.
5. The payment QR is marked `AWAITING_PAYMENT` only after Meta accepts the send.

The poller is the durable path. It primarily uses `confirmed_amount`; if Dograh has entered `Payment QR` but persisted only `proposed_amount`, it safely uses that value because the workflow transition itself requires explicit confirmation. It never uses a proposed amount before that stage.

## Operations

### Service Management

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

# View logs for a service
docker compose logs -f orchestrator
docker compose logs -f dograh

# Check service status
docker compose ps

# Stop all services
docker compose down

# Start all services in detached mode
docker compose up -d
```

### Monitoring and Troubleshooting

#### Health Checks

- Orchestrator: `http://localhost:9000/health`
- Dograh API: `http://localhost:8000/api/v1/health`
- Dashboard: `http://localhost:3000` (Next.js health endpoint if configured)
- PostgreSQL: `docker compose exec postgres pg_isready -U pipeline -d leadpipeline`
- Redis: `docker compose exec redis redis-cli ping`

#### Common Issues

1. **WhatsApp webhook not received**
   - Verify `WA_WEBHOOK_VERIFY_TOKEN` matches in Meta Developer Dashboard and `.env`
   - Check that your server is publicly accessible (ngrok for local testing)
   - Ensure port 9000 is forwarded correctly if behind a router

2. **Call not connecting**
   - Verify Telnyx credentials and that the outbound profile is configured
   - Check Dograh logs for workflow trigger errors
   - Ensure `DOGRAH_TRIGGER_PATH` matches the workflow trigger in Dograh

3. **QR not sent**
   - Check orchestrator logs for `mid-call` or `QR sent` messages
   - Verify Razorpay credentials and that the API key has QR creation permissions
   - Ensure the amount is within `MIN_AMOUNT_INR` and `MAX_AMOUNT_INR`

4. **Payment not verified**
   - Confirm `RAZORPAY_WEBHOOK_SECRET` matches in Razorpay Dashboard and `.env`
   - Check webhook logs in Razorpay for delivery status
   - Ensure the orchestrator can reach `https://api.razorpay.com/v1`

#### Log Inspection

```bash
# Follow orchestrator logs for QR and payment events
docker compose logs -f orchestrator | grep -Ei '(mid-call|QR sent|razorpay|payment)'

# Check Dograh for workflow execution
docker compose logs -f dograh | grep -Ei '(workflow|call|telephony)'

# View Redis for active leads
docker compose exec redis redis-cli -a pipeline keys "lead:*"
```

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

- **Never commit** `.env`, `.env.dograh`, API keys, webhook secrets, or credentials.
- Meta webhooks are scoped to the configured WhatsApp phone-number ID.
- The internal Gemini Vertex bridge requires `Authorization: Bearer $GEMIN...KEN` and must remain internal to the Docker network/reverse-proxy access policy.
- Razorpay webhook signatures must be configured and verified before payment processing.
- All sensitive data in transit is encrypted via HTTPS/TLS.
- Regularly rotate API keys and webhook secrets.
- Implement rate limiting on public endpoints (orchestrator has basic protection; consider adding API gateway or WAF in production).

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contact

Abdullah - abdullah@suppremo.in

Project Link: [https://github.com/abdullah917071/lead-pipeline](https://github.com/abdullah917071/lead-pipeline)