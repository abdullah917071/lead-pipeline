#!/usr/bin/env python3
"""Fix Dograh workflow: wire webhook-1 into the edges, fix prompt templates.

The deployed workflow definition 4 has a webhook-1 node but the edges bypass it
(amount-1 -> payment-1 directly). This script:
1. Removes the direct edge amount-1 -> payment-1
2. Adds edges: amount-1 -> webhook-1 -> payment-1
3. Updates prompts to Hindi + QR-only payment
4. Fixes the payload template to use raw JSON (not stringified)
"""

import json
import psycopg2

conn = psycopg2.connect(
    host="dograh-postgres", port=5432,
    dbname="dograh", user="dograh", password="dograh_pg"
)
cur = conn.cursor()

# Get the current published workflow definition
cur.execute("SELECT workflow_json FROM workflow_definitions WHERE id = 4")
row = cur.fetchone()
if not row:
    print("ERROR: No workflow definition 4 found")
    exit(1)

raw = row[0]
data = json.loads(raw) if isinstance(raw, str) else raw

nodes = data["nodes"]
edges = data["edges"]

print(f"=== Current state: {len(nodes)} nodes, {len(edges)} edges ===")
for e in edges:
    print(f"  {e['source']} -> {e['target']}")

# ─── 1. Remove the direct edge amount-1 -> payment-1 ─────────────
edges = [e for e in edges if not (e["source"] == "amount-1" and e["target"] == "payment-1")]

# ─── 2. Add edges: amount-1 -> webhook-1 -> payment-1 ───────────
if not any(e["source"] == "amount-1" and e["target"] == "webhook-1" for e in edges):
    edges.append({
        "id": "edge-amount-to-webhook",
        "source": "amount-1",
        "target": "webhook-1",
        "data": {
            "label": "Amount confirmed",
            "condition": "Customer has confirmed a deposit amount",
            "transition_speech": "Excellent! Ab main aapke WhatsApp par QR bhej raha hoon."
        }
    })
    print("Added: amount-1 -> webhook-1")

if not any(e["source"] == "webhook-1" and e["target"] == "payment-1" for e in edges):
    edges.append({
        "id": "edge-webhook-to-payment",
        "source": "webhook-1",
        "target": "payment-1",
        "data": {
            "label": "QR sent",
            "condition": "Webhook fired successfully",
            "transition_speech": ""
        }
    })
    print("Added: webhook-1 -> payment-1")

# ─── 3. Update webhook-1 payload template to use RAW JSON ───────
for n in nodes:
    if n["id"] == "webhook-1":
        n["data"]["endpoint_url"] = "http://orchestrator:9000/api/webhooks/dograh-midcall"
        # Build a proper JSON payload — Dograh's template engine renders {{variables}}
        # Must be a JSON object, not a string.
        n["data"]["payload_template"] = {
            "run_id": "{{workflow_run_id}}",
            "lead_id": "{{initial_context.lead_id}}",
            "confirmed_amount": "{{gathered_context.confirmed_amount}}",
            "phone": "{{initial_context.customer_phone}}"
        }
        n["data"]["custom_headers"] = [{"key": "Content-Type", "value": "application/json"}]
        print("Fixed webhook-1 payload template")

    if n["id"] == "webhook-postcall":
        n["data"]["endpoint_url"] = "http://orchestrator:9000/api/webhooks/dograh"
        n["data"]["payload_template"] = {
            "run_id": "{{workflow_run_id}}",
            "initial_context": "{{initial_context | tojson}}",
            "gathered_context": "{{gathered_context | tojson}}",
            "transcript_url": "{{transcript_url}}",
            "recording_url": "{{recording_url}}",
            "call_disposition": "{{gathered_context.call_disposition}}"
        }
        n["data"]["custom_headers"] = [{"key": "Content-Type", "value": "application/json"}]
        # Ensure the edge to webhook-postcall exists
        if not any(e["source"] == "payment-1" and e["target"] == "webhook-postcall" for e in edges):
            edges.append({
                "id": "edge-payment-to-posthook",
                "source": "payment-1",
                "target": "webhook-postcall",
                "data": {
                    "label": "Call done",
                    "condition": "Payment instructions given",
                    "transition_speech": "Thank you!"
                }
            })
        if not any(e["source"] == "webhook-postcall" and e["target"] == "end-1" for e in edges):
            edges.append({
                "id": "edge-posthook-to-end",
                "source": "webhook-postcall",
                "target": "end-1",
                "data": {
                    "label": "Notified",
                    "condition": "Webhook sent",
                    "transition_speech": ""
                }
            })
        # Remove old payment-1 -> end-1 edge
        edges = [e for e in edges if not (e["source"] == "payment-1" and e["target"] == "end-1")]
        print("Fixed webhook-postcall and edges")

# ─── 4. Update prompts ──────────────────────────────────────────
for n in nodes:
    if n["id"] == "greet-1":
        n["data"]["prompt"] = (
            "You are Rohit from Sai Bhai Cricket ID, calling a potential customer.\n\n"
            'STEP 1 - GREET:\n"Haan ji, namaste! Main Rohit bol raha hoon Sai Bhai Cricket ID se. '
            'Aapko online gaming ID ke regarding call kiya tha."\n\n'
            'STEP 2 - ENGAGE:\n"Sir, aap kya online games khelte hain? Jaise Cricket satta, '
            'Casino, Rummy, Teen Patti ya Poker?"\n\n'
            "If yes -> proceed. If no -> politely end call.\n\n"
            "Be conversational in Hinglish. Greet first, wait for reply, then ask."
        )
    elif n["id"] == "intro-1":
        n["data"]["prompt"] = (
            "Customer confirmed they play betting games. Introduce Sai Bhai.\n\n"
            'SAY: "Sir, hamari ID se aap Cricket match satta, Casino, Rummy, Poker, '
            'Teen Patti — sab kuch ek hi account mein khel sakte hain. '
            'Self Deposit aur Manual Deposit dono available hain. '
            'All panel exchange IDs bhi provide karte hain."\n\n'
            'OFFER: "First deposit par 4% bonus, uske baad har deposit par 2% bonus."\n\n'
            "Wait for their reaction. Be natural."
        )
    elif n["id"] == "amount-1":
        n["data"]["prompt"] = (
            "Ask for their preferred deposit amount.\n\n"
            'SAY: "Sir, aap kitne amount se start karna chahenge? Minimum Rs 500 se start kar sakte hain."\n\n'
            "Wait for their response. Once they state an amount, confirm:\n"
            '"Theek hai sir, Rs [amount] confirm kar doon?"\n\n'
            "CRITICAL: Proceed ONLY after they explicitly confirm. "
            "Extract the confirmed amount as confirmed_amount."
        )
        n["data"]["extraction_enabled"] = True
        n["data"]["extraction_variables"] = [{
            "name": "confirmed_amount",
            "type": "number",
            "prompt": "Exact deposit amount the customer confirmed in Indian Rupees. Numbers only like 500, 1000."
        }]
    elif n["id"] == "payment-1":
        n["data"]["prompt"] = (
            "The system just sent a Razorpay QR code to the customer's WhatsApp.\n\n"
            'SAY: "Sir, Rs {{confirmed_amount}} ka payment QR aapke WhatsApp par bhej diya hai. '
            'Aap PhonePe, GPay ya Paytm mein QR scan karke payment kar dijiye. '
            'Payment confirm hote hi aapka ID activate ho jayega. Koi issue ho to WhatsApp par batayein."\n\n'
            "Let them respond if they have questions."
        )
        n["data"]["allow_interrupt"] = True
        n["data"]["wait_for_user_response"] = True
    elif n["id"] == "end-1":
        n["data"]["prompt"] = (
            'End warmly: "Shukriya sir! Payment QR aapke WhatsApp par aa gaya hai. '
            'Payment complete karte hi ID activate. Agar koi problem ho to WhatsApp par message karein. '
            'Thank you, have a great day!"'
        )

data["edges"] = edges
data["nodes"] = nodes

# ─── 5. Save to Dograh DB ───────────────────────────────────────
updated_json = json.dumps(data, indent=2)

# Update the published definition (id=4, is_current=true)
cur.execute(
    "UPDATE workflow_definitions SET workflow_json = %s WHERE id = 4",
    (updated_json,)
)
# Also update the workflow drafts
cur.execute(
    "UPDATE workflows SET workflow_definition = %s WHERE id = 1",
    (updated_json,)
)
cur.execute(
    "UPDATE workflow_definitions SET workflow_json = %s WHERE workflow_id = 1",
    (updated_json,)
)
conn.commit()

print(f"\n=== Deployed! ===")
print(f"Nodes: {len(nodes)}, Edges: {len(edges)}")
for e in edges:
    print(f"  {e['source']} -> {e['target']}: {e['data']['label']}")

cur.close()
conn.close()