# Submission packet — Proofroom

**Track:** 01 · Best Business Workflow  
**Tagline:** Every release decision should carry its proof into the room where humans and agents work.

## Short description

Proofroom is an evidence-bound incident room built on Switch. A checkout regression is reported in a shared Mattermost room with two humans and three agents. Signal reproduces the failure, Release runs a deterministic five-case rollback canary, and a real Codex agent independently reviews the source. The on-call human approves the exact SHA-256 evidence digest in chat. A wrong person or changed digest cannot promote the release. A live companion UI shows the replay, policy checks, and audit trail.

## Problem and outcome

During an incident, diagnosis, canary evidence, and release approval often live in different tools. That makes it hard to tell which evidence a human approved or whether the proposed release was actually tested. Proofroom keeps the agent handoff, human discussion, and decision in one Switch room, while a deterministic engine enforces the release policy. In the included run, `v2.14.0` fails on two of five checkout fixtures; `v2.13.2` passes all five and preserves the three previously healthy responses. Sam's sign-off is refused, then Priya's exact-hash approval promotes the local release state.

## Why Switch matters

The workflow depends on Switch room membership, sender identity, shared rules, and message delivery. Signal, Release, Codex, Sam, and Priya participate in one private room. The custom agents use Switch's native SSE/HTTP Agent Protocol and read the room context. The release gate binds approval to the approver's actual Switch sender ID, not a name typed into text. Removing Switch removes the multi-party handoff and the identity-bearing approval path.

## Technology

Switch `0.31.0`; built-in Mattermost bridge; Python 3 standard library HTTP server and Agent Protocol clients; Codex CLI read-only investigation; deterministic checkout replay; SHA-256 evidence and hash-chain audit; vanilla HTML/CSS/JavaScript live UI with server-sent updates; Playwright and FFmpeg for video capture.

## Submission assets

- Public repository: [github.com/Vishwa-docs/proofroom-switch](https://github.com/Vishwa-docs/proofroom-switch).
- Downloadable packet: `submission/proofroom-submission.zip` in the local project folder.
- Demo video: [proofroom-switch-demo.mp4](https://github.com/Vishwa-docs/proofroom-switch/blob/main/demo/proofroom-switch-demo.mp4) (live Switch + Mattermost flow, captioned and narrated).
- Setup and architecture: `README.md`.
- Switch templates: `switch/live-room.yaml` and `switch/proofroom.template.yaml`.
- Tests: `tests/test_engine.py`.
- Prior art and attribution: `submission/prior-art.md`.

## Demo sequence

1. Sam reports checkout failure in the Switch Mattermost room.
2. Signal reproduces two failures and hands off to Codex and Release.
3. Release posts five policy checks and the SHA-256 of the canary evidence.
4. Codex independently identifies the null-discount error and residual fixture coverage risk.
5. Sam's attempted approval is rejected by the identity gate.
6. Priya approves the exact evidence hash; the local release state changes to `v2.13.2` and a final replay has zero errors.

## Accuracy notes for judges

The release target is an executable local checkout fixture, not a production deployment. The canary has five cases, so the demo makes no claim about real-world error rates. The UI mirrors the engine and room activity; the authoritative approval arrives through Switch. No Wispr Flow or Switch core PR claim is made.

## Suggested Devpost fields

**Project name:** Proofroom  
**One-line pitch:** A Switch incident room that binds human release approval to tested evidence.  
**Built with:** Switch, Mattermost, Codex CLI, Python, JavaScript, Playwright, FFmpeg.  
**Challenges:** Mapping Switch's event sender identity to the correct on-call human, coordinating three agents without letting the LLM own the release gate, and recording a verifiable live end-to-end demonstration.  
**What we learned:** Shared room context is most useful when a deterministic decision boundary turns conversation into a precise, reviewable action.
