"""Native Switch Agent Protocol client: SSE down, HTTP up, heartbeat and room claims."""

import json
import os
import queue
import re
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from .engine import GateError


class SwitchBridge:
    def __init__(self, engine):
        self.engine = engine
        self.base = os.getenv("SWITCH_URL", "http://127.0.0.1:8000").rstrip("/")
        self.room = os.getenv("SWITCH_ROOM_ID", "")
        self.approver = os.getenv("SWITCH_APPROVER_ID", "")
        self.agents = {
            "triage": (os.getenv("SWITCH_TRIAGE_AGENT_ID", ""), os.getenv("SWITCH_TRIAGE_API_KEY", "")),
            "release": (os.getenv("SWITCH_RELEASE_AGENT_ID", ""), os.getenv("SWITCH_RELEASE_API_KEY", "")),
        }
        investigator = (os.getenv("SWITCH_INVESTIGATOR_AGENT_ID", ""), os.getenv("SWITCH_INVESTIGATOR_API_KEY", ""))
        if all(investigator):
            self.agents["investigator"] = investigator
        self.enabled = bool(self.room and self.approver and all(investigator) and all(all(pair) for pair in self.agents.values()))
        self.connected = {role: False for role in self.agents}
        self.room_context = {}
        self.outbox = queue.Queue()

    def _request(self, agent_id: str, key: str, method: str, path: str, body=None, connection_id=None):
        headers = {"Authorization": f"Bearer {key}"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if connection_id:
            headers["X-Switch-Connection-Id"] = connection_id
        request = urllib.request.Request(
            f"{self.base}/agents/{agent_id}{path}",
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers, method=method,
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            return json.load(response)

    def start(self):
        if not self.enabled:
            return
        threading.Thread(target=self._send_loop, daemon=True).start()
        for role in self.agents:
            threading.Thread(target=self._listen_loop, args=(role,), daemon=True).start()

    def post(self, event: dict):
        if self.enabled and event.get("speaker") in {"Signal Agent", "Release Agent"}:
            role = "triage" if event["speaker"] == "Signal Agent" else "release"
            self.outbox.put((role, event["body"]))

    def _send_loop(self):
        while True:
            role, body = self.outbox.get()
            agent_id, key = self.agents[role]
            for attempt in range(3):
                try:
                    self._request(agent_id, key, "POST", "/message", {"room_id": self.room, "content": body})
                    break
                except (urllib.error.URLError, ValueError) as exc:
                    print(f"Switch post retry {attempt + 1}: {exc}", flush=True)
                    time.sleep(2)

    def _listen_loop(self, role: str):
        agent_id, key = self.agents[role]
        connection_id = str(uuid.uuid4())
        cursor = None
        while True:
            stop_beat = threading.Event()
            try:
                params = urllib.parse.urlencode({
                    "connection_id": connection_id, "scope": "all", "filter": "all",
                    "start_from": "head", "rooms": self.room,
                })
                headers = {"Authorization": f"Bearer {key}", "Accept": "text/event-stream"}
                if cursor is not None:
                    headers["Last-Event-ID"] = str(cursor)
                request = urllib.request.Request(f"{self.base}/agents/{agent_id}/events?{params}", headers=headers)
                with urllib.request.urlopen(request, timeout=45) as response:
                    self.connected[role] = True
                    threading.Thread(target=self._beat_loop, args=(role, connection_id, stop_beat, lambda: cursor), daemon=True).start()
                    # Claim and read shared room context before handling work.
                    try:
                        self._request(agent_id, key, "POST", "/ops/connect_to_room", {"room_id": self.room}, connection_id)
                        self.room_context[role] = self._request(
                            agent_id, key, "POST", "/ops/read_context",
                            {"room_id": self.room, "limit": 20}, connection_id,
                        ).get("result", {})
                    except (urllib.error.URLError, ValueError) as exc:
                        print(f"Switch room claim ({role}): {exc}", flush=True)
                    frame = {}
                    for raw in response:
                        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                        if not line:
                            if "data" in frame:
                                data = json.loads(frame["data"])
                                if "id" in frame:
                                    cursor = int(frame["id"])
                                self._handle(role, frame.get("event", ""), data)
                            frame = {}
                        elif line.startswith("id:"):
                            frame["id"] = line[3:].strip()
                        elif line.startswith("event:"):
                            frame["event"] = line[6:].strip()
                        elif line.startswith("data:"):
                            frame["data"] = frame.get("data", "") + line[5:].strip()
            except (urllib.error.URLError, ValueError, TimeoutError) as exc:
                print(f"Switch stream reconnect ({role}): {exc}", flush=True)
            finally:
                self.connected[role] = False
                stop_beat.set()
            time.sleep(2)

    def _beat_loop(self, role, connection_id, stop, get_cursor):
        agent_id, key = self.agents[role]
        while not stop.wait(2):
            try:
                self._request(agent_id, key, "POST", "/connection/beat", {"connection_id": connection_id, "cursor": get_cursor() or 0})
            except (urllib.error.URLError, ValueError):
                return

    def _handle(self, role: str, event_type: str, data: dict):
        if os.getenv("DEBUG_SWITCH") == "1":
            print(f"Switch event {role}: {event_type} room={data.get('room_id')} payload={str(data.get('payload', {}))[:400]}", flush=True)
        if event_type != "message" or data.get("room_id") != self.room:
            return
        payload = data.get("payload", {})
        body = payload.get("body", "").strip()
        sender = payload.get("sender", "")
        try:
            if role == "triage" and re.search(r"\bINVESTIGATE\b", body, re.I):
                self.engine.trigger()
            elif role == "release" and re.search(r"\bPREPARE\b", body, re.I):
                self.engine.prepare()
            elif role == "investigator" and "@proofroom-investigator REVIEW" in body:
                threading.Thread(target=self._run_investigator, daemon=True).start()
            elif role == "release":
                match = re.fullmatch(r"(?:@\S+\s+)?APPROVE\s+([0-9a-f]{64})", body, re.I)
                if match:
                    self.engine.approve(match.group(1).lower(), sender, self.approver)
        except GateError as exc:
            self.outbox.put((role, f"Gate refused: {exc}"))

    def _run_investigator(self):
        """Run the user's Codex CLI as an independent, read-only AI teammate."""
        prompt = (
            "Read gatehouse/cart.py and gatehouse/engine.py in this repository. "
            "An incident shows two of five checkout fixtures failing on v2.14.0. "
            "Independently identify the exact cause, assess whether v2.13.2 is a safe rollback "
            "under the five deterministic checks, and name one residual risk. "
            "Reply in at most 100 words. Do not edit files or invent measurements."
        )
        try:
            result = subprocess.run(
                ["codex", "exec", "-m", "gpt-5.6-sol", "-c", 'model_reasoning_effort="low"', "--sandbox", "read-only", "--skip-git-repo-check", "-C", os.getcwd(), prompt],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode:
                message = "Independent Codex review unavailable: CLI exited without an assessment."
            else:
                message = result.stdout.strip()[-1800:] or "Independent Codex review returned no text."
        except (OSError, subprocess.TimeoutExpired):
            message = "Independent Codex review unavailable: CLI could not complete."
        self.engine.record_review(message)
        self.outbox.put(("investigator", "Independent source review: " + message))

