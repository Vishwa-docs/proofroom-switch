"""Provision a Mattermost Switch room after bootstrap_switch.py.

Uses the official agent protocol operations discovered from the Switch source.
Reads registration token and agent keys from environment / .env; prints no keys.
"""

import argparse
import json
import os
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def load_env():
    values = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value
    return values


def call(url, token, payload):
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--approver", required=True, help="Mattermost username of on-call human")
    parser.add_argument("--collaborator", required=True, help="Mattermost username of second human")
    parser.add_argument("--room-name", default="proofroom-checkout-release", help="New or existing Switch room name")
    args = parser.parse_args()
    values = load_env()
    base = values["SWITCH_URL"].rstrip("/")
    token = os.environ.get("SWITCH_REGISTRATION_TOKEN", "")
    if not token:
        raise SystemExit("Set SWITCH_REGISTRATION_TOKEN from the Switch stack.")
    investigator = call(f"{base}/agents/register-known", token, {
        "agent_type": "codex", "name": "proofroom-investigator", "description": "Read-only Codex source reviewer in the release room",
        "options": {"repo_dir": str(ROOT)}, "overwrite": True,
    })
    values["SWITCH_INVESTIGATOR_AGENT_ID"] = investigator["id"]
    values["SWITCH_INVESTIGATOR_API_KEY"] = investigator["api_key"]
    yaml = (ROOT / "switch" / "live-room.yaml").read_text()
    triage_id, triage_key = values["SWITCH_TRIAGE_AGENT_ID"], values["SWITCH_TRIAGE_API_KEY"]
    release_id, release_key = values["SWITCH_RELEASE_AGENT_ID"], values["SWITCH_RELEASE_API_KEY"]
    # A room participant must be allowed to address these agents; custom
    # registration defaults to owner_only, which Switch would visibly reject.
    for caller_id, caller_key, target_id in [
        (release_id, release_key, triage_id),
        (triage_id, triage_key, release_id),
        (triage_id, triage_key, investigator["id"]),
    ]:
        call(f"{base}/agents/{caller_id}/ops/update_agent_detail", caller_key, {"agent_id": target_id, "addressing": "anyone"})
    list_request = urllib.request.Request(f"{base}/agents/{triage_id}/ops/list_rooms", data=b"{}", headers={"Authorization": f"Bearer {triage_key}", "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(list_request, timeout=15) as response:
        rooms = json.load(response)["result"]
    existing = next((r for r in rooms if r.get("name") == args.room_name), None)
    room = existing or call(f"{base}/agents/{triage_id}/ops/create_room_from_yaml", triage_key, {
        "yaml": yaml, "inputs": {"room_name": args.room_name, "approver": args.approver, "collaborator": args.collaborator, "bridge": "Mattermost"},
    })["result"]
    values["SWITCH_ROOM_ID"] = room["room_id"]
    values["SWITCH_ROOM_NAME"] = args.room_name
    # read_context carries the sender ID used in live SSE messages, while
    # list_participants returns a different database UUID. Bind to the former.
    context = call(f"{base}/agents/{triage_id}/ops/read_context", triage_key, {"room_id": room["room_id"], "limit": 200})["result"]
    entries = [entry for thread in context["threads"] for entry in [thread["root"], *thread["replies"]]]
    matches = {entry["sender"] for entry in entries if entry.get("sender_name", "").lower() == args.approver.lower() and entry.get("kind") == "room_join"}
    if len(matches) != 1:
        raise SystemExit("Room created, but approver sender ID was ambiguous. Have the approver join the room, then rerun this script.")
    values["SWITCH_APPROVER_ID"] = next(iter(matches))
    path = ROOT / ".env"
    path.write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n")
    path.chmod(0o600)
    print(f"Switch room ready: {room.get('room_name', room.get('name'))} ({room['room_id']}). Approver ID stored in .env.")


if __name__ == "__main__":
    main()
