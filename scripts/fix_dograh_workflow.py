"""Fix Dograh workflow: re-add webhook nodes as standalone (no edges), restore amount-1 -> payment-1 edge."""
import json
import psycopg2

conn = psycopg2.connect(
    host="dograh-postgres", port=5432,
    dbname="dograh", user="dograh", password="dograh_pg"
)
cur = conn.cursor()

# Get current workflow definition
cur.execute("SELECT workflow_json FROM workflow_definitions WHERE id = 2")
raw = cur.fetchone()[0]
data = raw if isinstance(raw, dict) else json.loads(raw)

nodes = data['nodes']
edges = data['edges']

# Remove any existing webhook nodes and edges connected to them
nodes = [n for n in nodes if n['type'] != 'webhook']
edges = [e for e in edges if not (e['source'].startswith('webhook') or e['target'].startswith('webhook'))]

# Add webhook nodes as standalone (no edges — they fire after workflow completes)
webhooks = [
    {
        'id': 'webhook-1',
        'type': 'webhook',
        'position': {'x': 800, 'y': -100},
        'data': {
            'name': 'Notify Orchestrator (mid-call)',
            'enabled': True,
            'http_method': 'POST',
            'endpoint_url': 'http://orchestrator:9000/api/webhooks/dograh-midcall',
            'payload_template': {"run_id": "{{workflow_run_id}}", "lead_id": "{{initial_context.lead_id}}", "confirmed_amount": "{{gathered_context.confirmed_amount}}", "phone": "{{initial_context.customer_phone}}"},
            'custom_headers': [{'key': 'Content-Type', 'value': 'application/json'}]
        }
    },
    {
        'id': 'webhook-postcall',
        'type': 'webhook',
        'position': {'x': 1400, 'y': -100},
        'data': {
            'name': 'Notify Orchestrator (post-call)',
            'enabled': True,
            'http_method': 'POST',
            'endpoint_url': 'http://orchestrator:9000/api/webhooks/dograh',
            'payload_template': {"run_id": "{{workflow_run_id}}", "initial_context": "{{initial_context | tojson}}", "gathered_context": "{{gathered_context | tojson}}", "transcript_url": "{{transcript_url}}", "recording_url": "{{recording_url}}"},
            'custom_headers': [{'key': 'Content-Type', 'value': 'application/json'}]
        }
    }
]
nodes = nodes + webhooks

# Restore amount-1 -> payment-1 edge if missing
has_amount_to_payment = any(e['source'] == 'amount-1' and e['target'] == 'payment-1' for e in edges)
if not has_amount_to_payment:
    edges.append({
        'id': 'edge-amount-to-payment',
        'source': 'amount-1',
        'target': 'payment-1',
        'data': {
            'label': 'Amount confirmed',
            'condition': 'Customer has confirmed a deposit amount',
            'transition_speech': 'Excellent! Let me send the payment QR to your WhatsApp.'
        }
    })

# Restore payment-1 -> end-1 edge if missing
has_payment_to_end = any(e['source'] == 'payment-1' and e['target'] == 'end-1' for e in edges)
if not has_payment_to_end:
    edges.append({
        'id': 'edge-end',
        'source': 'payment-1',
        'target': 'end-1',
        'data': {
            'label': 'Call ending',
            'condition': 'Payment instructions given',
            'transition_speech': 'Thank you for your time!'
        }
    })

# Verify we still have trigger-1 -> greet-1 edge
has_trigger_to_greet = any(e['source'] == 'trigger-1' and e['target'] == 'greet-1' for e in edges)
if not has_trigger_to_greet:
    edges.insert(0, {
        'id': 'edge-trigger',
        'source': 'trigger-1',
        'target': 'greet-1',
        'data': {'label': 'New lead', 'condition': 'Trigger received'}
    })

data['edges'] = edges
data['nodes'] = nodes

# Save to both tables
updated = json.dumps(data)
cur.execute("UPDATE workflow_definitions SET workflow_json = %s WHERE id = 2", (updated,))
cur.execute("UPDATE workflows SET workflow_definition = %s WHERE id = 1", (updated,))
conn.commit()

print(f"Nodes: {len(nodes)}, Edges: {len(edges)}")
for n in nodes:
    print(f"  {n['id']}: {n['type']}")
for e in edges:
    print(f"  {e['source']} -> {e['target']}: {e['data']['label']}")
print(f"\nWebhook nodes (standalone, no edges): {[n['id'] for n in nodes if n['type'] == 'webhook']}")

cur.close()
conn.close()