import pytest

from gatehouse.cart import checkout, replay
from gatehouse.engine import GateError, IncidentEngine, digest


def test_regression_is_real_and_canary_preserves_healthy_cases():
    old, stable = replay("v2.14.0"), replay("v2.13.2")
    assert sum(not x["ok"] for x in old) == 2
    assert all(x["ok"] for x in stable)
    assert all(a["response"] == b["response"] for a, b in zip(old, stable) if a["ok"])


def test_approval_requires_exact_evidence_and_named_participant(tmp_path):
    engine = IncidentEngine(tmp_path / "state.json")
    engine.trigger()
    proof = engine.prepare()["proof"]
    with pytest.raises(GateError, match="configured on-call"):
        engine.approve(proof["sha256"], "@mallory:demo", "@priya:demo")
    with pytest.raises(GateError, match="digest"):
        engine.approve("0" * 64, "@priya:demo", "@priya:demo")
    assert engine.snapshot()["active_version"] == "v2.14.0"
    result = engine.approve(proof["sha256"], "@priya:demo", "@priya:demo")
    assert result["phase"] == "recovered"
    assert result["active_version"] == "v2.13.2"
    assert engine.verify_chain()


def test_replay_cannot_skip_investigation_or_use_unknown_candidate(tmp_path):
    engine = IncidentEngine(tmp_path / "state.json")
    with pytest.raises(GateError, match="investigation"):
        engine.prepare()
    engine.trigger()
    with pytest.raises(GateError, match="allowlisted"):
        engine.prepare("v9.0.0")
    assert engine.snapshot()["phase"] == "investigating"


def test_event_chain_detects_tampering(tmp_path):
    engine = IncidentEngine(tmp_path / "state.json")
    engine.trigger()
    assert engine.verify_chain()
    engine.state["events"][0]["body"] = "rewritten"
    assert not engine.verify_chain()


def test_proof_and_decision_digest_detect_tampering(tmp_path):
    engine = IncidentEngine(tmp_path / "state.json")
    engine.trigger()
    proof = engine.prepare()["proof"]
    engine.record_review("Codex confirmed the null-discount regression.")
    engine.approve(proof["sha256"], "@priya:demo", "@priya:demo")
    assert engine.verify_chain()
    engine.state["decision"]["target"] = "v9.0.0"
    assert not engine.verify_chain()
