"""Optimize Dograh workflow prompts: explain-first flow + mid-call QR generation.

Changes:
1. greet-1: Explain product first, get confirmation, THEN ask for amount
2. intro-1: Reinforce value, confirm readiness
3. amount-1: Ask amount, confirm it, NO payment method talk (only UPI QR)
4. payment-1: Tell customer QR sent to WhatsApp, no payment options
5. Structure: amount-1 -> webhook-1 -> payment-1 (QR generates DURING call)
"""
import json
import psycopg2

conn = psycopg2.connect(
    host="dograh-postgres", port=5432,
    dbname="dograh", user="dograh", password="dograh_pg"
)
cur = conn.cursor()

# Get workflow definition
cur.execute("SELECT workflow_json FROM workflow_definitions WHERE id = 2")
raw = cur.fetchone()[0]
data = raw if isinstance(raw, dict) else json.loads(raw)

nodes = data['nodes']
edges = data['edges']

# ──────────────────────────────────────────────────────────────────
# 1. Optimize prompts
# ──────────────────────────────────────────────────────────────────

for n in nodes:
    nid = n['id']

    # --- greet-1: Explain first, get interested, THEN ask for amount ---
    if nid == 'greet-1':
        n['data']['prompt'] = (
            "IMPORTANT RULE: Speak ONLY in Hindi/Hinglish. Not a single full English sentence.\n\n"
            "You are Rohit from Sai Bhai Cricket ID.\n\n"
            "STEP 1 - GREET & EXPLAIN:\n"
            '"Haan ji sir, main Rohit bol raha hoon. Sai Bhai Cricket ID ki taraf se call kiya hai."\n\n'
            "Sir, hamari ID mein aap Cricket, Casino, Rummy, Poker, Teen Patti — ek hi account mein "
            "saare games khel sakte hain. Self deposit aur manual deposit dono. "
            "First deposit par 4% bonus milta hai. Sabse fast withdrawal.\n\n"
            'STEP 2 - CONFIRM INTEREST:\n'
            '"Toh aapko ID lene mein interest hai?"\n\n'
            "STEP 3 - IF YES, ask for amount:\n"
            '"Theek hai sir. Batao aap kitne amount se start karna chahenge? Minimum Rs 5 se start kar sakte hain."\n\n'
            "Wait for their response. If they say no/not interested, transition to end-cold."
        )

    # --- intro-1: Reinforce value, confirm they want it, send to amount ---
    elif nid == 'intro-1':
        n['data']['prompt'] = (
            "IMPORTANT RULE: Speak ONLY in Hindi/Hinglish.\n\n"
            "Customer is interested in betting. Push for the sale naturally.\n\n"
            '"Sir, jab aap ready hain toh main aapke liye ID bana deta hoon. '
            'First deposit par 4% bonus. Aapko koi game specifically khelna hai?"\n\n'
            "Once they confirm, say:\n"
            '"Theek hai sir, batao kitna deposit karna chahenge?"\n\n'
            "If they name an amount, confirm it and proceed to amount-1."
        )

    # --- amount-1: Just ask & confirm amount. NO payment method talk. ---
    elif nid == 'amount-1':
        n['data']['prompt'] = (
            "IMPORTANT RULE: Speak ONLY in Hindi/Hinglish.\n\n"
            "Confirm the amount with the customer:\n"
            '"Sir, Rs [amount] confirm kar doon?"\n\n'
            "Once confirmed:\n"
            '"Bilkul, main abhi aapke WhatsApp par QR bhej raha hoon. '
            'PhonePe, GPay, Paytm — koi bhi UPI app se scan karke payment kar sakte hain. '
            'Payment karte hi ID activate."\n\n'
            "IMPORTANT: Do NOT ask which payment method. Only UPI QR via Razorpay is available. "
            "Just tell them to scan the QR coming on WhatsApp.\n\n"
            "Extract confirmed_amount as number. Proceed only after they explicitly confirm the amount."
        )
        n['data']['extraction_enabled'] = True
        n['data']['extraction_variables'] = [{
            'name': 'confirmed_amount',
            'type': 'number',
            'prompt': 'The exact deposit amount the customer confirmed in Indian Rupees. Numbers only.'
        }]

    # --- payment-1: Confirm QR sent, no payment options ---
    elif nid == 'payment-1':
        n['data']['prompt'] = (
            "IMPORTANT RULE: Speak ONLY in Hindi/Hinglish.\n\n"
            '"Sir, Rs [confirmed_amount] ka QR aapke WhatsApp par aa gaya hai. '
            'Koi bhi UPI app — PhonePe, GPay, ya Paytm se scan karke payment kar den. '
            'Payment complete karte hi main ID activate kar dunga. Koi aur help?"\n\n'
            "If they say no:\n"
            '"Thank you sir! Sai Bhai Cricket ID. Have a great day!"\n\n'
            "Then end the call."
        )

# ──────────────────────────────────────────────────────────────────
# 2. Fix workflow structure: amount-1 -> webhook-1 -> payment-1
# ──────────────────────────────────────────────────────────────────

# Remove the direct amount-1 -> payment-1 edge
edges = [e for e in edges if not (e['source'] == 'amount-1' and e['target'] == 'payment-1')]

# Add amount-1 -> webhook-1 edge (fires webhook DURING call, generates QR + sends on WhatsApp)
if not any(e.get('source') == 'amount-1' and e.get('target') == 'webhook-1' for e in edges):
    edges.append({
        'id': 'edge-amount-to-webhook',
        'source': 'amount-1',
        'target': 'webhook-1',
        'data': {
            'label': 'Amount confirmed',
            'condition': 'Customer has confirmed a deposit amount',
            'transition_speech': 'Theek hai sir! Abhi QR bhej raha hoon WhatsApp par.'
        }
    })

# Add webhook-1 -> payment-1 edge (proceeds AFTER QR is generated and sent)
if not any(e.get('source') == 'webhook-1' and e.get('target') == 'payment-1' for e in edges):
    edges.append({
        'id': 'edge-webhook-to-payment',
        'source': 'webhook-1',
        'target': 'payment-1',
        'data': {
            'label': 'QR sent',
            'condition': 'QR successfully generated and sent on WhatsApp',
            'transition_speech': 'Sir, QR WhatsApp par aa gaya hai. Ab aap payment kar sakte hain.'
        }
    })

# Make sure payment-1 -> end-1 edge exists
if not any(e['source'] == 'payment-1' and e['target'] == 'end-1' for e in edges):
    edges.append({
        'id': 'edge-payment-to-end',
        'source': 'payment-1',
        'target': 'end-1',
        'data': {
            'label': 'Call ending',
            'condition': 'Payment instructions given, customer satisfied',
            'transition_speech': 'Thank you for your time!'
        }
    })

data['edges'] = edges
data['nodes'] = nodes

# Save to both tables
updated = json.dumps(data)
cur.execute("UPDATE workflow_definitions SET workflow_json = %s WHERE id = 2", (updated,))
cur.execute("UPDATE workflows SET workflow_definition = %s WHERE id = 1", (updated,))
conn.commit()

print(f"=== WORKFLOW UPDATED ===")
print(f"Nodes: {len(nodes)}, Edges: {len(edges)}")
print()
for n in nodes:
    print(f"  {n['id']}: {n['type']}")
print()
for e in edges:
    print(f"  {e['source']} -> {e['target']}: {e['data']['label']} (cond: {e['data'].get('condition','')})")

# Also update the orchestrator's send_qr_payment message to not mention payment methods
# The WhatsApp caption for QR should just say "scan and pay" without listing methods

cur.close()
conn.close()
