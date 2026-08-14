# Dograh Voice-Agent Recovery State

Updated: 2026-08-14

## Restored local runtime

- Local Dograh organization, admin, API key, and Telnyx telephony configuration were recreated after the Dograh database was found empty.
- The active `Sai Bhai Onboarding` workflow is published and active.
- Its public workflow UUID is configured in the orchestrator environment; it must remain private operational configuration rather than source-controlled data.
- Workflow definition has 7 nodes and 5 transitions.
- The recovered opening prompt is loaded at runtime: the agent identifies as Rohit from Sai Bhai Cricket ID and uses Hindi/Hinglish qualification flow.
- `allow_interrupt` is disabled for the opening greeting so the welcome message is not cut off.

## Application changes saved in this repository

- WhatsApp webhook malformed JSON is rejected with controlled HTTP 400 responses.
- WhatsApp template header images are uploaded to Meta and sent by media ID instead of relying on a publicly hosted asset URL.
- Dograh health requires authenticated API access, not only a bare health endpoint.
- Orchestrator calls Dograh through the workflow UUID route:
  `POST /api/v1/public/agent/workflow/{workflow_uuid}`.
- Custom Telnyx provider implements the current `validate_phone_number` contract.
- Telnyx streaming transport and Gemini Live implementation are included under `deploy/dograh/`.

## Verified call path

A real outbound verification demonstrated:

1. Dograh created the workflow run.
2. Telnyx initiated and answered the call.
3. Telnyx signed webhooks verified successfully.
4. The Telnyx WebSocket stream started with bidirectional RTP/PCMA.
5. Dograh created the Vertex realtime LLM and loaded the restored system instruction.
6. The call still produced no model audio because Vertex rejected the configured publisher model.

## Current external blockers

### Vertex Gemini Live

The supplied service account successfully obtained a Google Cloud access token. During the real call, Vertex rejected the configured publisher model:

`google/gemini-live-2.5-flash-native-audio`

Required account-side verification:

- Vertex AI API is enabled in the configured Google Cloud project.
- The service account has Vertex AI User (or equivalent) access.
- The project has access to the Gemini Live native-audio publisher model in the `global` location.

Do not replace the stored Vertex configuration with a generic Gemini API key: the previous key was restricted from Gemini Live BidiGenerate.

### Telnyx

The first verified calls were placed successfully. A later retry was rejected by Telnyx with termination error `D17`: the account used for termination was blocked/disabled. This must be resolved in Telnyx before further outbound testing.

## Secret handling and backup

- Secrets are intentionally excluded from Git: `.env*`, `.dograh-bootstrap.json`, `secrets/`, and `backups/`.
- A restrictive-permission custom-format PostgreSQL backup of the current Dograh runtime was saved under the ignored `backups/` directory.
- The backup contains operational configuration and must never be committed or copied into logs.
- Rotate any credentials that were pasted into a chat or terminal history.

## Resume checklist

1. Resolve Telnyx D17 account state.
2. Grant/confirm the Vertex Gemini Live publisher-model entitlement.
3. Trigger a test call and keep it answered long enough to confirm the opening greeting is audible.
4. Check Dograh logs for `Connected to Gemini service` and outbound audio frames.
5. Then validate the end-to-end WhatsApp inbound `Interested` button webhook and call trigger.
