"""Record the actual local Switch + Mattermost workflow as a captioned MP4.

Requires a running Switch stack, two local Mattermost demo accounts, a clean
Proofroom state, Playwright Chromium and ffmpeg. The posting accounts are local
demo fixtures; this script does not submit the hackathon entry.
"""

import argparse
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo"
MM = "http://127.0.0.1:18065"


def env_file(path):
    return dict(line.split("=", 1) for line in Path(path).read_text().splitlines() if "=" in line and not line.startswith("#"))


def api(url, payload=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, data=json.dumps(payload).encode() if payload is not None else None, headers=headers, method="POST" if payload is not None else "GET")
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response), response.headers


def login(username, password):
    _, headers = api(MM + "/api/v4/users/login", {"login_id": username, "password": password})
    return headers["Token"]


def post(channel, token, message):
    api(MM + "/api/v4/posts", {"channel_id": channel, "message": message}, token)


def state():
    return api("http://127.0.0.1:8765/api/state")[0]


def wait_for(predicate, page, timeout=50):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        current = state()
        if predicate(current):
            return current
        page.wait_for_timeout(500)
    raise RuntimeError("timed out waiting for live workflow")


def timestamp(seconds):
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def warm_login(browser, username, password):
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page.goto(MM, wait_until="domcontentloaded")
    page.get_by_text("View in Browser").click(timeout=15000)
    page.locator("input[name=loginId]").fill(username)
    page.locator("input[name=password-input]").fill(password)
    page.get_by_role("button", name="Log in").click()
    page.wait_for_url("**/channels/**", timeout=20000)
    storage = context.storage_state()
    context.close()
    return storage


def refresh_chat(page):
    """Fetch the real Mattermost transcript; headless WebSocket updates can lag."""
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    page.evaluate("""() => {
        const list = document.getElementById('postListScrollContainer');
        if (list) list.scrollTop = list.scrollHeight;
    }""")
    page.wait_for_timeout(500)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stack-env", default="/tmp/proofroom-switch/.env")
    args = parser.parse_args()
    stack, project = env_file(args.stack_env), env_file(ROOT / ".env")
    if state()["phase"] != "idle" or not state()["switch"]["configured"]:
        raise SystemExit("Start the configured Switch room with clean state.json before recording.")
    agent = project["SWITCH_TRIAGE_AGENT_ID"]
    details, _ = api(f"{project['SWITCH_URL']}/agents/{agent}/ops/get_room_detail", {"room_id": project["SWITCH_ROOM_ID"]}, project["SWITCH_TRIAGE_API_KEY"])
    channel = details["result"]["external_channel_id"]
    sam_token = login("sam", stack["MATTERMOST_SAM_PASSWORD"])
    priya_token = login(stack["MATTERMOST_USER"], stack["MATTERMOST_USER_PASSWORD"])
    DEMO.mkdir(exist_ok=True)
    (DEMO / "raw").mkdir(exist_ok=True)
    marks = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        sam_storage = warm_login(browser, "sam", stack["MATTERMOST_SAM_PASSWORD"])
        chat_context = browser.new_context(viewport={"width": 1280, "height": 900}, storage_state=sam_storage, record_video_dir=str(DEMO / "raw"), record_video_size={"width": 1280, "height": 900})
        dash_context = browser.new_context(viewport={"width": 1440, "height": 900}, record_video_dir=str(DEMO / "raw"), record_video_size={"width": 1440, "height": 900})
        chat = chat_context.new_page()
        dash = dash_context.new_page()
        chat.goto(f"{MM}/proofroom/channels/{project['SWITCH_ROOM_NAME']}", wait_until="domcontentloaded")
        dash.goto("http://127.0.0.1:8765", wait_until="domcontentloaded")
        chat.wait_for_timeout(3500)
        dash.wait_for_timeout(500)
        start = time.monotonic()
        def mark(caption):
            marks.append((time.monotonic() - start, caption))
        mark("PROOFROOM  •  A real Switch room and a live release gate")
        chat.wait_for_timeout(4000)
        post(channel, sam_token, "@proofroom-signal INVESTIGATE guest checkout is failing. Please coordinate the release in this room.")
        mark("SAM REPORTS A CHECKOUT FAILURE IN MATTERMOST")
        dash.evaluate("window.scrollTo({top: 350, behavior: 'smooth'})")
        wait_for(lambda s: s["phase"] == "awaiting_approval", chat, 25)
        refresh_chat(chat)
        mark("SIGNAL → RELEASE: FIVE REAL CASES REPLAYED; CANARY PASSED")
        wait_for(lambda s: any(e["kind"] == "review" for e in s["events"]), chat, 60)
        refresh_chat(chat)
        mark("CODEX INDEPENDENTLY REVIEWS THE SOURCE AND CHALLENGES THE CAUSE")
        chat.wait_for_timeout(3000)
        sha = state()["proof"]["sha256"]
        post(channel, sam_token, "APPROVE " + sha)
        chat.wait_for_timeout(1500)
        refresh_chat(chat)
        mark("WRONG APPROVER: THE GATE REFUSES SAM'S SIGN-OFF")
        chat.wait_for_timeout(3000)
        if state()["phase"] != "awaiting_approval":
            raise RuntimeError("unauthorized approval unexpectedly changed the release")
        post(channel, priya_token, "APPROVE " + sha)
        mark("PRIYA APPROVES THE EXACT EVIDENCE HASH IN THE SWITCH ROOM")
        wait_for(lambda s: s["phase"] == "recovered", chat, 20)
        refresh_chat(chat)
        mark("RELEASE PROMOTED; FINAL REPLAY HAS ZERO ERRORS")
        chat.wait_for_timeout(5000)
        end = time.monotonic() - start
        chat_video = chat.video
        dash_video = dash.video
        chat_context.close()
        dash_context.close()
        browser.close()
        chat_path, dash_path = chat_video.path(), dash_video.path()
    captions = []
    for i, (at, label) in enumerate(marks):
        until = marks[i+1][0] if i+1 < len(marks) else end
        captions.append(f"{i+1}\n{timestamp(at)} --> {timestamp(until)}\n{label}\n")
    (DEMO / "captions.srt").write_text("\n".join(captions))
    output = DEMO / "proofroom-switch-demo.mp4"
    filter_graph = (
        "[0:v]crop=1000:900:280:0,setsar=1[chat];"
        "[1:v]crop=1180:900:260:0,scale=1000:900,setsar=1[dash];"
        "[chat][dash]hstack=inputs=2,"
        "drawbox=x=0:y=847:w=2000:h=53:color=0x14261f@0.88:t=fill,"
        "subtitles=demo/captions.srt:force_style='FontName=Arial,FontSize=11,PrimaryColour=&H00FFFFFF&,OutlineColour=&H00201010&,BorderStyle=1,Outline=1,Alignment=2,MarginV=12'[v]"
    )
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", chat_path, "-i", dash_path, "-filter_complex", filter_graph, "-map", "[v]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)], cwd=ROOT, check=True)
    print(f"Recorded {end:.1f}s live Switch demo: {output}")


if __name__ == "__main__":
    main()
