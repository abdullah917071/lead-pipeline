# Lead Pipeline — COMPLETE Agent Instruction & Reference File
# Owner: Abdullah Ansari (Bizrato / Sai Bhai Cricket ID)
# Last updated: 2026-07-20 (session: fixed Dograh call trigger, min=Rs1, webhook URL)
#
# READ THIS AFTER EVERY RESTART. It is the single source of truth. Do NOT guess.
# If something here is wrong, FIX IT HERE and in the code together.

================================================================================
0. TL;DR — WHAT WORKS / WHAT'S BROKEN (as of 2026-07-20)
================================================================================
WORKING:
  - Pipeline server (uvicorn :9000) runs and is healthy.
  - Dograh voice call triggers and the user RECEIVES the call (the `to` field bug is FIXED).
  - Min deposit = Rs 1 (code + config + dograh amount gate all fixed).
  - Razorpay UPI QR is the DEFAULT payment method, generated MID-CALL after amount confirmation.
  - WhatsApp opt-in sends (falls back to interactive message while template is PENDING).

BROKEN / NOT YET LIVE (must be done by user or approved push):
  - The LIVE Dograh voice agent still runs the OLD workflow (asks Rs 500, goes silent
    after amount confirmation). Fix = re-push config/dograh_workflow_onboarding.json to Dograh.
  - WhatsApp template "saibhai" is PENDING in Meta (user edited it). Until APPROVED, the
    opt-in template send 400s and falls back to interactive (24h window only).
  - The workflow's completion webhook URL was "http://orchestrator:9000/..." (unreachable).
    FIXED in JSON to "http://10.234.52.162:9000/api/webhooks/dograh" but NOT yet pushed live.

================================================================================
1. SYSTEM PURPOSE
================================================================================
Autonomous cricket-betting-ID sales pipeline:
  Meta ad -> WhatsApp opt-in (image + "Interested" button) -> user clicks
  -> "you'll get a call" notice -> Dograh AI voice call (Hinglish sales pitch)
  -> agent confirms deposit amount -> Razorpay dynamic UPI QR generated MID-CALL
  -> QR image sent on WhatsApp -> user pays -> Razorpay webhook
  -> instantly provision demo account + send login credentials on WhatsApp.

================================================================================
2. RUN / RESTART
================================================================================
Repo: ~/lead-pipeline  (version 3.0.0). Framework: FastAPI (app/main.py) + uvicorn.
START (background):
  cd ~/lead-pipeline && source venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 9000 --reload
(The --reload flag re-reads .env and reloads on file save.)
HEALTH: GET http://10.234.52.162:9000/health  -> {"status":"ok",...}
DASHBOARD: GET http://10.234.52.162:9000/api/dashboard  (shows min_amount, razorpay_configured)
NOTES:
  - MinIO docker binds 127.0.0.1:9000 -> localhost:9000 collides with pipeline.
    Use LAN IP 10.234.52.162:9000 (or the cloudflared-pipeline tunnel).
  - Pipeline tunnel: Docker "cloudflared-pipeline" -> port 9000.
  - Dograh runs in docker (api :8000, ui :3010). WhatsApp Cloud API = LIVE.

================================================================================
3. CREDENTIALS / IDS (live — do not change unless told)
================================================================================
WhatsApp:
  phone_id (WABA phone number ID): 1227078997152468
  WABA ID: 2202368716902450
  number: +91 87964 41870 (Sai Bhai, CLOUD_API VERIFIED)
  webhook verify_token: suppremo_wa_verify_2026
  opt-in template: "saibhai" (APPROVED historically; PENDING after user's 2026-07-20 edit)
Razorpay (LIVE):
  key id: rzp_live_TFinDozUMuqMCp
  webhook secret: suppremo_razorpay_webhook_2026
  API URL: https://api.razorpay.com/v1
Dograh:
  base URL: http://localhost:8000   (docker, reachable from host AND from dograh container via LAN IP 10.234.52.162:9000)
  API key: dgr_Y0tY4gHogYRKIo0kVvciNtBKAAHVyWskRVe3Y1shRIg
  trigger path: eb155119-43b7-4410-a94b-b9b331455fbb
  telephony config ID: 3   (ID 2 does NOT exist — "Telephony configuration not found")
  agent/workflow id: 2
  UI: http://localhost:3010
  tunnel (dograh): https://confidential-prophet-foam-farms.trycloudflare.com
UPI merchant display name: Sai Bhai

================================================================================
4. FLOW STATE MACHINE (app/services/orchestrator.py)
================================================================================
handle_new_lead        -> ingest lead, send WA opt-in (send_optin_message)
handle_wa_reply        -> "Interested" click -> send call notice + trigger Dograh call
handle_call_completed  -> Dograh webhook; extract confirmed_amount
handle_wa_amount_reply -> if amount not extracted from call, user replies amount on WA
_generate_and_send_qr -> Razorpay dynamic QR created + sent on WhatsApp (MID-CALL)
handle_payment_success -> Razorpay webhook -> provision + send credentials instantly

ENDPOINTS (app/main.py):
  POST /api/webhooks/lead              Meta ad lead ingest
  POST /api/webhooks/whatsapp          WA messages + button clicks
  GET  /api/webhooks/whatsapp          WA webhook verification
  POST /api/webhooks/dograh            Dograh call-completion webhook
  POST /api/webhooks/payment/razorpay  Razorpay payment webhook (signature verified)
  POST /api/internal/payment-success   manual/test payment success
  GET  /api/dashboard /api/leads /api/leads/{id} /api/upi/active /api/upi/rotate
  GET  /health

================================================================================
5. PAYMENT: DEFAULT = RAZORPAY UPI QR (generated MID-CALL)
================================================================================
app/services/upi_service.py create_payment_session():
  - Tries Razorpay dynamic QR FIRST (if RAZORPAY_KEY_ID/SECRET set).
  - Falls back to local UPI QR ONLY if Razorpay fails.
razorpay_service.py create_dynamic_qr payload:
  type=upi_qr, usage=single_use, fixed_amount=True,
  payment_amount=amount_inr*100 (paise), close_by = now + expiry mins.
  *** close_by MUST use time.time() (Unix ts), NOT datetime.utcnow().timestamp(). ***
The QR is generated and sent to the user MID-CALL, right after amount confirmation
(handle_call_completed -> _generate_and_send_qr). This is intended.

================================================================================
6. CONFIG CHANGES MADE ON 2026-07-20 (all DONE in code/config)
================================================================================
A) MIN DEPOSIT = Rs 1 (was Rs 5):
   - .env: MIN_AMOUNT_INR=1
   - app/config.py: MIN_AMOUNT_INR: float = 1
   - app/services/dograh_service.py ~line 135: amount gate changed from
       `elif amount and 100 <= amount <= 100000:`
     to `elif amount and settings.MIN_AMOUNT_INR <= amount <= settings.MAX_AMOUNT_INR:`
B) WhatsApp opt-in template = "saibhai" (you added IMAGE header in Meta):
   - .env + config.py: WA_OPTIN_TEMPLATE_NAME=saibhai
   - WA_OPTIN_IMAGE_URL=https://blog.suppremo.in/wp-content/uploads/wa-welcome.jpg
   - send_optin_message uses plain send_template with variables={"name":...}
     (image is baked into the template header; do NOT send an image header component).
C) Dograh calling-agent prompts allow Rs 1 (config/dograh_workflow_onboarding.json):
   - start-1: "as little as Rs 100" -> "as little as Rs 1"
   - negotiate-1: tiers start at Rs 1 (demo account)
   - confirmed_amount extraction example: 1, 100, 500, 1000, 2000
   - *** THIS FILE IS ONLY THE SOURCE. Must re-push to Dograh to take effect. ***
D) Dograh call trigger bug FIXED (app/services/dograh_service.py):
   - REMOVED the "to" field from the trigger payload. Dograh's Telnyx telephony
     config (id 3) REJECTS any "to" value (even valid +E164) with 422
     "Phone number must be in +E164 format". Sending ONLY phone_number +
     telephony_configuration_id works (returns {"status":"initiated"}).
   - VERIFIED: user received the real call after this fix.
E) Dograh workflow webhook URL FIXED (config/dograh_workflow_onboarding.json):
   - was "http://orchestrator:9000/api/webhooks/dograh" (unreachable; 'orchestrator'
     not resolvable from dograh container)
   - now "http://10.234.52.162:9000/api/webhooks/dograh" (dograh container CAN reach
     this LAN IP — verified 200 from inside the container).
   - *** Must re-push workflow to Dograh for this to take effect. ***

================================================================================
7. KNOWN GOTCHAS / LESSONS (do not re-discover)
================================================================================
- .env OVERRIDES config.py defaults. Edit .env for runtime values.
- Dograh webhook schema (app/schemas.py DograhWebhookPayload): run_id/workflow_run_id/
  workflow_id are INTS, not strings. Test payloads must use integers.
- Dograh trigger: NO "to" field. Only phone_number + telephony_configuration_id.
- Dograh telephony config id 3 is correct; id 2 does not exist.
- Template image headers: Meta template API example uses header_handle with a valid
  uploaded MEDIA ID; raw URLs are rejected. (Not needed for saibhai — you set image in Meta.)
- saibhaiimg template was deleted (was pending/incomplete). saibhai is the live one.
- Multi-lead-by-phone: get_by_phone returns the FIRST matching lead; re-ingesting the
  same number re-uses an old lead id. For clean tests, track the returned lead_id.
- MinIO on 127.0.0.1:9000 collides with pipeline port 9000.
- Razorpay QR close_by timestamp bug: time.time() not datetime.utcnow().timestamp().
- Re-pushing the Dograh workflow is REQUIRED after editing the JSON; the local file
  alone does not change the running agent.

================================================================================
8. HOW TO RUN A FULL FLOW TEST
================================================================================
1. Ingest: POST /api/webhooks/lead  {"phone":"+919****7822","name":"X","source":"meta_ad"}
2. Interested (triggers REAL Dograh call):
   POST /api/webhooks/whatsapp
   {"entry":[{"changes":[{"value":{"messages":[{"from":"+919****7822","type":"interactive",
     "interactive":{"type":"button_reply","button_reply":{"id":"interested","title":"Interested"}}}]}}]}]}
3. Simulate call completion + amount (after live call, Dograh posts this automatically;
   for testing without waiting, POST manually with INTEGER ids):
   POST /api/webhooks/dograh
   {"run_id":999001,"workflow_run_id":999001,"workflow_id":2,"workflow_name":"onboarding",
    "initial_context":{"lead_id":"<id from step1>","customer_name":"X","customer_phone":"+919****7822"},
    "gathered_context":{"confirmed_amount":1,"call_outcome":"completed","customer_name_confirmed":"X"}}
   -> generates Razorpay QR, sends QR image on WhatsApp.
4. Simulate payment: POST /api/internal/payment-success
   {"ref_id":"<from step3 session>","utr":"test123","amount":1,"gateway":"razorpay"}
   OR wait for real Razorpay webhook -> provisions account + sends credentials.

================================================================================
9. REMAINING ACTIONS REQUIRED FROM USER (not code-fixable by agent alone)
================================================================================
1. RE-PUSH config/dograh_workflow_onboarding.json to Dograh (UI :3010 or API) so the
   live agent uses Rs 1 minimum and the fixed webhook URL, and stops going silent
   after amount confirmation.
2. Wait for Meta to APPROVE the edited "saibhai" template (then opt-in uses the template
   with image, works 24/7; until then it falls back to interactive/24h).
3. Verify the live Dograh call now posts its completion webhook to
   http://10.234.52.162:9000/api/webhooks/dograh (after re-push).
