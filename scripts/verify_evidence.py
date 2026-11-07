"""Verify a saved Proofroom run without starting Switch or the web server."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gatehouse.engine import IncidentEngine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="submission/live-evidence.json")
    args = parser.parse_args()
    if not Path(args.path).is_file():
        parser.error(f"evidence file not found: {args.path}")
    engine = IncidentEngine(args.path)
    state = engine.snapshot()
    valid = engine.verify_chain() and bool(state["proof"] and state["decision"])
    print(f"Audit chain: {'VALID' if valid else 'INVALID'}")
    print(f"Incident: {state['incident_id']} · phase: {state['phase']} · active release: {state['active_version']}")
    if state["proof"]:
        print(f"Evidence SHA-256: {state['proof']['sha256']}")
    if state["decision"]:
        print(f"Approved by Switch sender: {state['decision']['actor_id']}")
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main())
