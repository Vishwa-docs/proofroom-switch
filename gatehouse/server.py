"""Dependency-free HTTP API and live companion UI for Proofroom."""

import json
import os
import queue
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .engine import GateError, IncidentEngine
from .switch_bridge import SwitchBridge


ROOT = Path(__file__).resolve().parent.parent
DEMO_MODE = os.getenv("DEMO_MODE", "1") == "1"
subscribers: list[queue.Queue] = []


def broadcast(event):
    for subscriber in list(subscribers):
        try:
            subscriber.put_nowait(event)
        except queue.Full:
            pass


engine = IncidentEngine(ROOT / "state.json", emit=broadcast)
bridge = SwitchBridge(engine)
if bridge.enabled and DEMO_MODE:
    raise SystemExit("Set DEMO_MODE=0 when connecting a live Switch room; local demo mutation routes must be disabled.")


def on_event(event):
    broadcast(event)
    bridge.post(event)


engine.emit = on_event


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)

    def send_json(self, value, status=200):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/state":
            state = engine.snapshot()
            state["switch"] = {"configured": bridge.enabled, "connected": bridge.connected, "demo_mode": DEMO_MODE, "room_name": os.getenv("SWITCH_ROOM_NAME", "checkout-release")}
            state["audit_valid"] = engine.verify_chain()
            return self.send_json(state)
        if path == "/api/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            subscriber = queue.Queue(maxsize=30)
            subscribers.append(subscriber)
            try:
                while True:
                    try:
                        event = subscriber.get(timeout=15)
                        data = json.dumps(event)
                        self.wfile.write(f"data: {data}\n\n".encode())
                    except queue.Empty:
                        self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                subscribers.remove(subscriber)
            return
        if path == "/api/evidence":
            proof = engine.snapshot().get("proof")
            return self.send_json(proof or {"error": "no proof yet"}, 200 if proof else 404)
        if path in {"/", "/index.html", "/app.css", "/app.js"}:
            name = "index.html" if path == "/" else path[1:]
            data = (ROOT / "web" / name).read_bytes()
            mime = {"index.html": "text/html", "app.css": "text/css", "app.js": "text/javascript"}[name]
            self.send_response(200)
            self.send_header("Content-Type", f"{mime}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            return self.wfile.write(data)
        self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 8192:
            return self.send_json({"error": "request too large"}, 413)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            path = urlparse(self.path).path
            if path == "/api/trigger" and DEMO_MODE:
                result = engine.trigger()
            elif path == "/api/prepare" and DEMO_MODE:
                result = engine.prepare(payload.get("candidate", "v2.13.2"))
            elif path == "/api/demo/approve" and DEMO_MODE:
                result = engine.approve(payload.get("sha256", ""), "@priya:demo", "@priya:demo")
            elif path == "/api/reset" and DEMO_MODE:
                result = engine.reset()
            else:
                return self.send_json({"error": "route unavailable"}, 404)
            self.send_json(result)
        except (GateError, ValueError, TypeError) as exc:
            self.send_json({"error": str(exc)}, 409)


def main():
    bridge.start()
    port = int(os.getenv("PORT", "8765"))
    print(f"Proofroom listening on http://127.0.0.1:{port} (demo={DEMO_MODE}, Switch={bridge.enabled})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
