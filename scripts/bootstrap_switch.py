"""Register the two deterministic agents with an existing Switch server.

The AI investigator is provisioned from switch/proofroom.template.yaml in
Switch Console, after these two agents exist. No secrets are printed.
"""

import json
import os
import urllib.request
from pathlib import Path


BASE = os.environ.get("SWITCH_URL", "http://127.0.0.1:8000").rstrip("/")
TOKEN = os.environ.get("SWITCH_REGISTRATION_TOKEN", "")


def register(name: str, description: str) -> dict:
    profile = {
        "connection_model": "always_on", "message_exchange": True,
        "pre_invocation_mediation": [], "post_invocation_mediation": [],
        "event_reporting": [],
    }
    payload = {
        "name": name, "display_name": name.replace("-", " ").title(),
        "description": description, "connector_type": "Proofroom Agent Protocol",
        "integration_profile": profile, "tools": [], "models": [],
    }
    request = urllib.request.Request(
        f"{BASE}/agents", data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def main():
    if not TOKEN:
        raise SystemExit("Set SWITCH_REGISTRATION_TOKEN from your Switch deployment first.")
    results = {
        "triage": register("proofroom-signal", "Reproduces checkout failures and hands evidence to the release agent"),
        "release": register("proofroom-release", "Runs a deterministic canary and enforces evidence-bound human approval"),
    }
    path = Path(".env")
    content = ["PORT=8765", "DEMO_MODE=0", f"SWITCH_URL={BASE}", "SWITCH_ROOM_ID=", "SWITCH_ROOM_NAME=", "SWITCH_APPROVER_ID="]
    for role in ("triage", "release"):
        upper = role.upper()
        content.extend([f"SWITCH_{upper}_AGENT_ID={results[role]['id']}", f"SWITCH_{upper}_API_KEY={results[role]['api_key']}"])
    path.write_text("\n".join(content) + "\n")
    path.chmod(0o600)
    print("Registered Proofroom Signal and Release agents. Credentials saved to .env (mode 0600).")
    print("Next: create switch/proofroom.template.yaml in Switch Console, then fill SWITCH_ROOM_ID and SWITCH_APPROVER_ID in .env.")


if __name__ == "__main__":
    main()

