"""Deterministic incident state machine and tamper-evident approval gate."""

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from .cart import CASES, RELEASES, replay


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class GateError(Exception):
    pass


class IncidentEngine:
    def __init__(self, path: str | Path = "state.json", emit=None):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.emit = emit or (lambda event: None)
        self.state = self._initial()
        if self.path.exists():
            self.state = json.loads(self.path.read_text())

    @staticmethod
    def _initial() -> dict:
        return {
            "phase": "idle", "active_version": "v2.14.0", "incident_id": None,
            "baseline": [], "proof": None, "decision": None, "events": [],
        }

    def snapshot(self) -> dict:
        with self.lock:
            return json.loads(json.dumps(self.state))

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=2) + "\n")
        os.replace(tmp, self.path)

    def _event(self, speaker: str, body: str, kind: str) -> None:
        previous = self.state["events"][-1]["hash"] if self.state["events"] else "0" * 64
        entry = {"at": now(), "speaker": speaker, "body": body, "kind": kind, "previous_hash": previous}
        entry["hash"] = digest(entry)
        self.state["events"].append(entry)
        self._save()
        self.emit(entry)

    def reset(self) -> dict:
        with self.lock:
            self.state = self._initial()
            self._save()
            self.emit({"kind": "reset"})
            return self.snapshot()

    def trigger(self) -> dict:
        with self.lock:
            if self.state["phase"] != "idle":
                raise GateError("an incident is already active")
            baseline = replay(self.state["active_version"])
            failures = sum(not item["ok"] for item in baseline)
            if not failures:
                raise GateError("the current release did not reproduce a failure")
            self.state.update({"phase": "investigating", "incident_id": "INC-2048", "baseline": baseline})
            self._event("Signal Agent", f"Checkout alert: {failures}/{len(baseline)} replay cases fail on v2.14.0. Null discounts trigger TypeError. @proofroom-investigator REVIEW the source and challenge this diagnosis. @proofroom-release PREPARE the canary in this room.", "investigation")
            return self.snapshot()

    def prepare(self, candidate: str = "v2.13.2") -> dict:
        with self.lock:
            if self.state["phase"] != "investigating":
                raise GateError("investigation must precede canary replay")
            if candidate != "v2.13.2":
                raise GateError("candidate release is not allowlisted")
            canary = replay(candidate)
            baseline = self.state["baseline"]
            regressions = [a["case"] for a, b in zip(baseline, canary) if a["ok"] and (not b["ok"] or a["response"] != b["response"])]
            checks = {
                "five_cases_replayed": len(canary) == len(CASES),
                "zero_candidate_errors": all(x["ok"] for x in canary),
                "no_healthy_regression": not regressions,
                "candidate_allowlisted": candidate == "v2.13.2",
                "no_schema_change": RELEASES[self.state["active_version"]]["schema"] == RELEASES[candidate]["schema"],
            }
            if not all(checks.values()):
                raise GateError("canary failed a deterministic policy check")
            evidence = {
                "incident_id": self.state["incident_id"],
                "from": self.state["active_version"], "to": candidate,
                "baseline": baseline, "canary": canary, "checks": checks,
                "baseline_errors": sum(not x["ok"] for x in baseline),
                "canary_errors": sum(not x["ok"] for x in canary),
            }
            self.state["proof"] = {**evidence, "sha256": digest(evidence)}
            self.state["phase"] = "awaiting_approval"
            self._event("Release Agent", f"Canary passed: 2/5 errors → 0/5; 3 healthy carts unchanged. All 5 policy checks passed. Evidence SHA-256: {self.state['proof']['sha256']}. Authorized on-call: reply APPROVE {self.state['proof']['sha256']} in this Switch room.", "proof")
            return self.snapshot()

    def record_review(self, message: str) -> None:
        with self.lock:
            if self.state["phase"] not in {"investigating", "awaiting_approval"}:
                return
            self._event("Codex Investigator", message, "review")

    def approve(self, evidence_hash: str, actor_id: str, authorized_id: str) -> dict:
        with self.lock:
            if self.state["phase"] != "awaiting_approval":
                raise GateError("no canary proof is awaiting approval")
            if not authorized_id or actor_id != authorized_id:
                raise GateError("only the configured on-call participant can approve")
            if evidence_hash != self.state["proof"]["sha256"]:
                raise GateError("approval digest does not match the current canary evidence")
            if not self.verify_chain():
                raise GateError("evidence or audit chain failed integrity verification")
            target = self.state["proof"]["to"]
            if any(not case["ok"] for case in replay(target)):
                raise GateError("target release failed the final probe")
            self.state["active_version"] = target
            self.state["phase"] = "recovered"
            decision = {"actor_id": actor_id, "evidence_sha256": evidence_hash, "at": now(), "action": "promote_allowlisted_release", "target": target}
            self.state["decision"] = {**decision, "hash": digest(decision)}
            self._event("Release Agent", f"Rollback applied to {target}. Final replay: 0/5 errors. Decision recorded against evidence {evidence_hash} by {actor_id}.", "recovery")
            return self.snapshot()

    def verify_chain(self) -> bool:
        proof = self.state.get("proof")
        if proof and digest({k: v for k, v in proof.items() if k != "sha256"}) != proof.get("sha256"):
            return False
        decision = self.state.get("decision")
        if decision and (digest({k: v for k, v in decision.items() if k != "hash"}) != decision.get("hash") or not proof or decision["evidence_sha256"] != proof["sha256"]):
            return False
        previous = "0" * 64
        for event in self.state["events"]:
            if event["previous_hash"] != previous or digest({k: v for k, v in event.items() if k != "hash"}) != event["hash"]:
                return False
            previous = event["hash"]
        return True
