#!/usr/bin/env python3
"""
Bizrato Lead Pipeline — Voice Call Trigger Script
Usage: python3 make_call.py +919XXXXXXXXX [--lead-id <id>] [--name <name>]

Starts Dograh if not running, gets the current Cloudflare tunnel URL,
triggers an outbound AI sales call via Dograh's public trigger endpoint.
The AI agent (Rohit) speaks in Hinglish with a professional sales tone.
"""
import subprocess, json, sys, time, re, argparse

DOGRAH_DIR = "/Users/abdullahansari07/ai-tools/dograh"
API_KEY = "dgr_Y0tY4gHogYRKIo0kVvciNtBKAAHVyWskRVe3Y1shRIg"
TRIGGER_PATH = "eb155119-43b7-4410-a94b-b9b331455fbb"
TELEPHONY_CONFIG_ID = 3
DOCKER_COMPOSE = f"{DOGRAH_DIR}/docker-compose.yaml"

def run(cmd, timeout=30):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

def dograh_running():
    r = run(["docker","ps","--format","{{.Names}}"])
    return "dograh-api-1" in r.stdout and "cloudflared-tunnel" in r.stdout

def start_dograh():
    print("Starting Dograh...")
    r = subprocess.run(["docker","compose","-f",DOCKER_COMPOSE,"up","-d"],
                       capture_output=True, text=True, timeout=120,
                       cwd=DOGRAH_DIR)
    # Wait for health
    for _ in range(30):
        time.sleep(2)
        h = run(["curl","-s","http://localhost:8000/api/v1/health"])
        if '"status":"ok"' in h.stdout:
            print("Dograh API healthy.")
            return True
    print("ERROR: Dograh API did not become healthy.")
    return False

def get_tunnel_url():
    for _ in range(15):
        r = run(["docker","logs","cloudflared-tunnel","--tail","10"])
        m = re.search(r"https://([a-z0-9-]+\.trycloudflare\.com)", r.stdout)
        if m:
            return f"https://{m.group(1)}"
        time.sleep(3)
    return None

def ensure_telnyx_public_key():
    """Ensure the Telnyx webhook public key is set in telephony configs."""
    sel = run(["docker","exec","dograh-postgres-1","psql","-U","postgres","-d","postgres",
               "-c","SELECT credentials->>'webhook_public_key' FROM telephony_configurations WHERE id=3;","-t","-A"])
    if sel.stdout.strip() and sel.stdout.strip() != "" and "null" not in sel.stdout:
        return True  # Already set
    # Read TELNYX API key from .env
    env_r = run(["bash","-c",
        "grep '^TELNYX_API_KEY=' /Users/abdullahansari07/lead-pipeline/.env | cut -d= -f2-"])
    telnyx_key = env_r.stdout.strip()
    if not telnyx_key:
        print("ERROR: TELNYX_API_KEY not found in .env")
        return False
    key_out = run(["curl","-s",
        "https://api.telnyx.com/v2/public_key",
        "-H",f"Authorization: Bearer {telnyx_key}"])
    try:
        pub_key = json.loads(key_out.stdout)["data"]["public"]
    except:
        print("ERROR: Could not fetch Telnyx public key.")
        return False
    for cfg_id in [1, 3]:
        creds_out = run(["docker","exec","dograh-postgres-1","psql","-U","postgres","-d","postgres",
                         "-c",f"SELECT credentials FROM telephony_configurations WHERE id={cfg_id};","-t","-A"])
        creds = json.loads(creds_out.stdout.strip())
        creds["webhook_public_key"] = pub_key
        sql = "UPDATE telephony_configurations SET credentials = '{}'::json WHERE id={};".format(
            json.dumps(creds).replace("'", "''"), cfg_id)
        run(["docker","exec","dograh-postgres-1","psql","-U","postgres","-d","postgres","-c",sql])
    print(f"Telnyx webhook public key set: {pub_key[:20]}...")
    return True

def trigger_call(phone, lead_id, name):
    tunnel = get_tunnel_url()
    if not tunnel:
        print("ERROR: Could not get tunnel URL.")
        return None
    print(f"Tunnel URL: {tunnel}")

    payload = {
        "phone_number": phone,
        "initial_context": {
            "lead_id": lead_id,
            "customer_name": name or "Lead",
            "customer_phone": phone,
            "source": "manual-call"
        },
        "telephony_configuration_id": TELEPHONY_CONFIG_ID
    }
    url = f"{tunnel}/api/v1/public/agent/{TRIGGER_PATH}"
    r = run(["curl","-s","-X","POST",url,
             "-H",f"X-API-Key: {API_KEY}",
             "-H","Content-Type: application/json",
             "-d", json.dumps(payload)], timeout=45)
    try:
        data = json.loads(r.stdout)
        return data
    except:
        print(f"ERROR: {r.stdout}")
        return None

def get_transcript(run_id):
    """Fetch transcript from MinIO."""
    r = run(["docker","exec","minio","mc","cat",f"local/voice-audio/transcripts/{run_id}.txt"], timeout=15)
    return r.stdout

def get_run_info(run_id):
    """Fetch run context from Dograh DB."""
    r = run(["docker","exec","dograh-postgres-1","psql","-U","postgres","-d","postgres",
             "-c",f"SELECT gathered_context FROM workflow_runs WHERE id={run_id};","-t","-A"])
    try:
        return json.loads(r.stdout.strip())
    except:
        return {}

def main():
    parser = argparse.ArgumentParser(description="Trigger a Bizrato AI sales call")
    parser.add_argument("phone", help="Phone number in E164 format (e.g. +919XXXXXXXXX)")
    parser.add_argument("--lead-id", default=None, help="Custom lead ID")
    parser.add_argument("--name", default="", help="Customer name")
    parser.add_argument("--transcript", action="store_true", help="Wait for call to end and print transcript")
    args = parser.parse_args()

    # Validate phone
    if not re.match(r"^\+\d{10,15}$", args.phone):
        print("ERROR: Phone must be in E164 format (e.g. +919XXXXXXXXX)")
        sys.exit(1)

    lead_id = args.lead_id or f"call-{int(time.time())}"

    # Step 1: Ensure Dograh is running
    if not dograh_running():
        if not start_dograh():
            sys.exit(1)
    else:
        h = run(["curl","-s","http://localhost:8000/api/v1/health"])
        if '"status":"ok"' not in h.stdout:
            if not start_dograh():
                sys.exit(1)

    # Step 2: Ensure Telnyx webhook public key
    ensure_telnyx_public_key()

    # Step 3: Trigger the call
    print(f"\nTriggering call to {args.phone} (lead_id={lead_id})...")
    result = trigger_call(args.phone, lead_id, args.name)
    if not result or "workflow_run_id" not in result:
        print("FAILED to initiate call.")
        print(json.dumps(result, indent=2) if result else "No response.")
        sys.exit(1)

    run_id = result["workflow_run_id"]
    run_name = result.get("workflow_run_name", "")
    print(f"\nCALL INITIATED")
    print(f"  Run ID:    {run_id}")
    print(f"  Run Name:  {run_name}")
    print(f"  Phone:     {args.phone}")
    print(f"  Lead ID:   {lead_id}")
    print(f"  Agent:     Rohit (Bizrato, Hinglish, professional sales)")
    print(f"  Pipeline:  Telnyx -> Dograh -> ElevenLabs STT -> gemini-2.5-flash -> Sarvam TTS")

    if args.transcript:
        print(f"\nWaiting for call to complete...")
        for _ in range(120):
            time.sleep(5)
            info = get_run_info(run_id)
            if info.get("call_disposition"):
                break
        print(f"\nCall disposition: {info.get('call_disposition', 'unknown')}")
        print(f"Confirmed amount: {info.get('confirmed_amount', 'none')}")
        transcript = get_transcript(run_id)
        if transcript:
            print(f"\n{'='*60}")
            print("TRANSCRIPT")
            print(f"{'='*60}")
            print(transcript)
        else:
            print("Transcript not available yet.")

    return run_id

if __name__ == "__main__":
    main()
