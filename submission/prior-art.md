# Prior art and attribution

We reviewed prior winners and Switch examples to choose a narrow, demonstrable workflow. The application was implemented from scratch; no winner repository source was copied.

| Project | What we studied | Decision in Proofroom |
| --- | --- | --- |
| [SRE Sentinel](https://github.com/aryan877/sre-sentinel), WeMakeDevs FutureStack winner · [demo video](https://www.youtube.com/watch?v=nw8W9Ik_8Og) | The demo shows the broken service, incident trigger, automated repair, and outcome in one continuous run. | Keep the incident narrative and live status, but make approval evidence-bound and local to a Switch room. |
| [MCP Sentinel](https://github.com/BashaarJavaid/MCP-Sentinel), OpenAI Build Week runner-up · [demo video](https://www.youtube.com/watch?v=0myxPyTDx2c) | The demo follows one finding through deterministic checks, model review, and executable proof, with explicit uncertainty. | Use Codex for an independent source assessment; keep five release checks in plain executable code. |
| [Switch](https://github.com/sandbox-quantum/switch) official source and demo examples | Agent Protocol, room templates, Mattermost integration, room history and rules | Use authenticated SSE/HTTP agents and a private room with three named agents and two humans. |
| [Incident Sentinel](https://github.com/ronitgupta138/Incident-Sentinel), current Switch submission | Existing broader incident-response angle | Narrow the product to the exact moment of release authorization, where a named human signs a specific canary proof. |

The user-supplied research brief included more projects and proposed capabilities. We verified the relevant public repositories and built only capabilities demonstrated in this project. We do not claim production telemetry, Docker-isolated canaries, real rollbacks, Switch core contributions, or a voice track.
