"""Update Dograh workflow to add webhook node and fix extraction."""
import json
import psycopg2

conn = psycopg2.connect(
    host="dograh-postgres", port=5432,
    dbname="dograh", user="dograh", password="dograh_pg"
)
cur = conn.cursor()

# Get current workflow definition (the published one)
cur.execute("SELECT workflow_json FROM workflow_definitions WHERE id = 2")
row = cur.fetchone()
if row:
    raw = row[0]
    if isinstance(raw, str):
        data = json.loads(raw)
    else:
        data = raw
else:
    # Fallback to workflows table
    cur.execute("SELECT workflow_definition FROM workflows WHERE id = 1")
    raw = cur.fetchone()[0]
    if isinstance(raw, str):
        data = json.loads(raw)
    else:
        data = raw

nodes = data['nodes']
edges = data['edges']

# Check if webhook-1 already exists
existing_webhook = any(n['id'] == 'webhook-1' for n in nodes)
if not existing_webhook:
    # Add mid-call webhook node (fires post-call in Dograh's design)
    nodes.append({
        'id': 'webhook-1',
        'type': 'webhook',
        'position': {'x': 800, 'y': -100},
        'data': {
            'name': 'Notify Orchestrator (mid-call)',
            'enabled': True,
            'http_method': 'POST',
            'endpoint_url': 'http://orchestrator:9000/api/webhooks/dograh-midcall',
            'payload_template': {"run_id": "{{workflow_run_id}}", "lead_id": "{{initial_context.lead_id}}", "confirmed_amount": "{{gathered_context.confirmed_amount}}", "phone": "{{initial_context.customer_phone}}" },
            'custom_headers': [{'key': 'Content-Type', 'value': 'application/json'}]
        }
    })

# Add post-call webhook node (fires after workflow completes, POSTs to existing endpoint)
existing_posthook = any(n['id'] == 'webhook-postcall' for n in nodes)
if not existing_posthook:
    nodes.append({
        'id': 'webhook-postcall',
        'type': 'webhook',
        'position': {'x': 1400, 'y': -100},
        'data': {
            'name': 'Notify Orchestrator (post-call)',
            'enabled': True,
            'http_method': 'POST',
            'endpoint_url': 'http://orchestrator:9000/api/webhooks/dograh',
            'payload_template': {"run_id": "{{workflow_run_id}}", "initial_context": "{{initial_context | tojson}}", "gathered_context": "{{gathered_context | tojson}}", "transcript_url": "{{transcript_url}}", "recording_url": "{{recording_url}}" },
            'custom_headers': [{'key': 'Content-Type', 'value': 'application/json'}]
        }
    })

# Add edge payment-1 -> webhook-postcall -> end-1
existing_post_edge = any(e.get('source') == 'payment-1' and e.get('target') == 'webhook-postcall' for e in edges)
if not existing_post_edge:
    # Remove old payment-1 -> end-1 edge
    edges = [e for e in edges if not (e['source'] == 'payment-1' and e['target'] == 'end-1')]
    
    edges.append({
        'id': 'edge-payment-to-posthook',
        'source': 'payment-1',
        'target': 'webhook-postcall',
        'data': {
            'label': 'Call done',
            'condition': 'Payment instructions given',
            'transition_speech': 'Thank you!'
        }
    })
    edges.append({
        'id': 'edge-posthook-to-end',
        'source': 'webhook-postcall',
        'target': 'end-1',
        'data': {
            'label': 'Notified',
            'condition': 'Webhook sent',
            'transition_speech': ''
        }
    })

# Update payment-1 prompt
for n in nodes:
    if n['id'] == 'payment-1':
        n['data']['prompt'] = (
            "The customer confirmed the deposit amount. "
            "The system is generating the Razorpay QR code and sending it to their WhatsApp right now.\n\n"
            "SAY:\n"
            '"Sir, Rs {{confirmed_amount}} ka payment QR aapke WhatsApp par bhej raha hoon. '
            'Payment complete karte hi ID activate kar dunga."\n\n'
            "Note: QR is being sent to WhatsApp now. Do NOT claim it's already sent."
        )

# Update amount-1 prompt to be more explicit about extraction
for n in nodes:
    if n['id'] == 'amount-1':
        n['data']['prompt'] = (
            "Ask for deposit amount. Be natural.\n\n"
            'SAY: "Sir, aap kitne amount se start karna chahenge?"\n\n'
            "Wait for their response. Once they give an amount, confirm it:\n"
            '"Theek hai sir, Rs {{amount}} confirm kar doon?"\n\n'
            "CRITICAL: After they confirm, you MUST extract the exact number as confirmed_amount. "
            "Example: if they confirm Rs 500, confirmed_amount = 500.\n\n"
            "Proceed only after explicit confirmation."
        )
        # Ensure extraction is enabled
        n['data']['extraction_enabled'] = True
        n['data']['extraction_variables'] = [{
            'name': 'confirmed_amount',
            'type': 'number',
            'prompt': 'The exact deposit amount the customer confirmed in Indian Rupees. Numbers only.'
        }]
        break

# Remove old edge amount-1 -> payment-1
edges = [e for e in edges if not (e['source'] == 'amount-1' and e['target'] == 'payment-1')]

# Add edge amount-1 -> webhook-1 (only if not already exists)
if not any(e.get('source') == 'amount-1' and e.get('target') == 'webhook-1' for e in edges):
    edges.append({
        'id': 'edge-amount-to-webhook',
        'source': 'amount-1',
        'target': 'webhook-1',
        'data': {
            'label': 'Amount confirmed',
            'condition': 'Customer has confirmed a deposit amount',
            'transition_speech': 'Excellent! Let me send the payment QR to your WhatsApp.'
        }
    })

# Add edge webhook-1 -> payment-1 (only if not already exists)
if not any(e.get('source') == 'webhook-1' and e.get('target') == 'payment-1' for e in edges):
    edges.append({
        'id': 'edge-webhook-to-payment',
        'source': 'webhook-1',
        'target': 'payment-1',
        'data': {
            'label': 'QR sent',
            'condition': 'QR generated and sent',
            'transition_speech': 'The QR has been sent.'
        }
    })

data['edges'] = edges
data['nodes'] = nodes

# Save back to both tables
updated_json = json.dumps(data)

# Update the published definition
cur.execute(
    "UPDATE workflow_definitions SET workflow_json = %s WHERE id = 2",
    (updated_json,)
)
# Also update the workflow draft
cur.execute(
    "UPDATE workflows SET workflow_definition = %s WHERE id = 1",
    (updated_json,)
)
conn.commit()
cur.close()
conn.close()
print("Workflow updated successfully")
print(f"Nodes: {len(data['nodes'])}, Edges: {len(data['edges'])}")
for n in nodes:
    print(f"  {n['id']}: {n['type']}")
for e in edges:
    print(f"  {e['source']} -> {e['target']}: {e['data']['label']}")