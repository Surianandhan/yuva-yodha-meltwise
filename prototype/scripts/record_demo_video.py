"""Record the MeltWise demo video: real app frames via headless Chrome (CDP), narration via macOS `say`.

Needs the API running on :8000, the Phase 2 deck built, ffmpeg, and `pip install websockets`.
    python scripts/record_demo_video.py <work_dir> <output.mp4>
Captions are split into short lines afterwards (see Phase2_Submission/MeltWise_Demo.srt).
"""
import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[2]
PROTO = ROOT / "prototype"
SLIDES = ROOT / "Deck_Source" / "phase2" / "build"
WORK = Path(sys.argv[1])
OUT = Path(sys.argv[2])
API = "http://127.0.0.1:8000"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
VOICE, RATE = "Rishi", "172"
W, H = 1600, 900

for d in ("frames", "audio", "seg"):
    (WORK / d).mkdir(parents=True, exist_ok=True)


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def speak(name, text):
    path = WORK / "audio" / f"{name}.aiff"
    run(["say", "-v", VOICE, "-r", RATE, "-o", str(path), text])
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]))
    return path, dur


class CDP:
    def __init__(self, ws):
        self.ws, self.n = ws, 0

    async def send(self, method, **params):
        self.n += 1
        my = self.n
        await self.ws.send(json.dumps({"id": my, "method": method, "params": params}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == my:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    async def shot(self, path):
        data = (await self.send("Page.captureScreenshot", format="jpeg", quality=88))["data"]
        Path(path).write_bytes(base64.b64decode(data))

    async def js(self, expr):
        return (await self.send("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)).get("result", {}).get("value")

    async def goto(self, url, wait=2.5):
        await self.send("Page.navigate", url=url)
        await asyncio.sleep(wait)


captions = []   # (start, end, text) on the final timeline
timeline = 0.0
segments = []


def still_segment(name, image, text, scale_from_slide=False):
    """An image held for the length of its narration."""
    global timeline
    audio, dur = speak(name, text)
    length = dur + 0.8
    seg = WORK / "seg" / f"{len(segments):02d}_{name}.mp4"
    run(["ffmpeg", "-y", "-loop", "1", "-i", str(image), "-i", str(audio), "-t", f"{length:.2f}",
         "-vf", "scale=1280:720:flags=lanczos,format=yuv420p", "-r", "30", "-c:v", "libx264", "-preset", "medium",
         "-tune", "stillimage", "-crf", "20", "-af", "apad", "-c:a", "aac", "-ar", "44100", "-ac", "1", str(seg)])
    captions.append((timeline + 0.1, timeline + dur, text))
    timeline += length
    segments.append(seg)


async def live_segment(cdp):
    """Stream one melt through meter -> gateway -> API and film the operator screen, narrating real events."""
    global timeline
    lines = {
        "start": "This melt is streaming live from the simulated Modbus meter, through the gateway, into MeltWise.",
        "underpower": "Within two minutes, MeltWise spots under-powered melting, and tracks the energy used against a target for this exact charge.",
        "chart": "The red line is furnace power. The dashed line is MeltWise's live estimate of the bath temperature, from the energy balance.",
        "outage": "Now we cut the network for ten seconds. The gateway keeps every reading in a local outbox, and sends them all when the network returns. Nothing is lost.",
        "dip_now": "The bath is near target, so MeltWise asks for a temperature dip, and resets its estimate on the reading.",
        "tap_ready": "Target reached: tap now. Today, operators overshoot by about forty-two degrees. Following this prompt, by about five.",
        "lang": "The same prompts appear in the operator's own language: Hindi, and Tamil.",
        "holding": "If the metal has to wait for the moulds, MeltWise counts the cost of holding.",
    }
    clips = {k: speak(f"live_{k}", v) for k, v in lines.items()}
    await cdp.goto(f"{API}/?v=live#/operator", wait=1.0)

    demo = subprocess.Popen([str(PROTO / ".venv/bin/python"), "-u", "scripts/live_demo.py", "--melts", "1", "--speed", "40",
                             "--outage", "10", "--port", "5061", "--seed", "12"], cwd=PROTO,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    outage = threading.Event()

    def watch():
        buf = b""
        while chunk := demo.stdout.read(64):
            buf += chunk
            if b"Network cut" in buf:
                outage.set()
    threading.Thread(target=watch, daemon=True).start()

    # wait until the new melt has replaced whatever the API was showing before
    for _ in range(200):
        live = httpx.get(f"{API}/api/live").json()
        if live.get("active") and live["state"]["t_s"] < 60 and not live["prompts"] and live["trace"]:
            break
        await asyncio.sleep(0.1)
    t0 = time.time()
    frames, placed, busy_until = [], [], 0.0
    pending = {"start": 0.5}
    fired = set()
    lang_switch = []
    done_at = None
    i = 0
    while True:
        now = time.time() - t0
        path = WORK / "frames" / f"live_{i:05d}.jpg"
        await cdp.shot(path)
        frames.append((path, now))
        i += 1
        live = httpx.get(f"{API}/api/live").json()
        codes = {p["code"] for p in live.get("prompts", [])} if live.get("active") else set()
        for code in ("underpower", "dip_now", "tap_ready", "holding"):
            if code in codes and code not in fired:
                fired.add(code)
                pending[code] = now
        if outage.is_set() and "outage" not in fired:
            fired.add("outage")
            pending["outage"] = now
        if now > 30 and "chart" not in fired and busy_until < now:
            fired.add("chart")
            pending["chart"] = now
        if "tap_ready" in placed_names(placed) and "lang" not in fired:
            fired.add("lang")
            pending["lang"] = now
        for key in sorted(pending, key=pending.get):
            start = max(pending[key], busy_until + 0.3)
            if start <= now + 0.05:
                path_a, dur = clips[key]
                placed.append((key, start, dur))
                busy_until = start + dur
                del pending[key]
                if key == "lang":
                    lang_switch.append((start + 2.6, "hi"))
                    lang_switch.append((start + 3.6, "ta"))
                break
        for when, lang in list(lang_switch):
            if now >= when:
                await cdp.js(f"document.getElementById('lang').value='{lang}'; refreshLive(); 1")
                lang_switch.remove((when, lang))
        if done_at is None and "holding" in placed_names(placed) and not pending:
            done_at = busy_until + 1.5
        if done_at is not None and now >= done_at:
            break
        if now > 240:
            break
        await asyncio.sleep(0.12)
    await cdp.js("document.getElementById('lang').value='en'; refreshLive(); 1")
    demo.wait(timeout=120)

    # video from timestamped frames
    concat = WORK / "live_frames.txt"
    with concat.open("w") as f:
        for (p, t), (_, t_next) in zip(frames, frames[1:] + [(None, frames[-1][1] + 0.2)]):
            f.write(f"file '{p}'\nduration {max(t_next - t, 0.04):.3f}\n")
        f.write(f"file '{frames[-1][0]}'\n")
    length = frames[-1][1] + 0.2
    video = WORK / "live_video.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-vf",
         "scale=1280:720:flags=lanczos,fps=30,format=yuv420p", "-c:v", "libx264", "-crf", "20", "-t", f"{length:.2f}", str(video)])
    # narration track
    inputs, filters = [], []
    for n, (key, start, dur) in enumerate(placed):
        inputs += ["-i", str(clips[key][0])]
        ms = int(start * 1000)
        filters.append(f"[{n}:a]adelay={ms}|{ms},aresample=44100[a{n}]")
        captions.append((timeline + start, timeline + start + dur, lines[key]))
    mix = "".join(f"[a{n}]" for n in range(len(placed)))
    audio = WORK / "live_audio.m4a"
    run(["ffmpeg", "-y", *inputs, "-filter_complex",
         ";".join(filters) + f";{mix}amix=inputs={len(placed)}:normalize=0,apad,atrim=0:{length:.2f}[out]",
         "-map", "[out]", "-ac", "1", "-ar", "44100", "-c:a", "aac", str(audio)])
    seg = WORK / "seg" / f"{len(segments):02d}_live.mp4"
    run(["ffmpeg", "-y", "-i", str(video), "-i", str(audio), "-c:v", "copy", "-c:a", "aac", "-ar", "44100", "-ac", "1",
         "-shortest", str(seg)])
    timeline += length
    segments.append(seg)
    print("live segment", round(length, 1), "s;", [(k, round(s, 1)) for k, s, _ in placed])


def placed_names(placed):
    return {k for k, _, _ in placed}


async def capture_app(cdp, name, url, js=None):
    await cdp.goto(url, wait=3.0)
    if js:
        await cdp.js(js)
        await asyncio.sleep(1.2)
    path = WORK / "frames" / f"{name}.jpg"
    await cdp.shot(path)
    return path


async def main():
    profile = tempfile.mkdtemp()
    chrome = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                               "--no-default-browser-check", f"--user-data-dir={profile}", "--remote-debugging-port=9333",
                               f"--window-size={W},{H}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                targets = httpx.get("http://127.0.0.1:9333/json").json()
                page = next(t for t in targets if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.2)
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=50_000_000) as ws:
            cdp = CDP(ws)
            await cdp.send("Page.enable")
            await cdp.send("Emulation.setDeviceMetricsOverride", width=W, height=H, deviceScaleFactor=1, mobile=False)

            still_segment("cover", SLIDES / "slide_01.png", "MeltWise: an AI energy copilot for India's induction-furnace foundries. This is our working prototype, for Phase 2 of the Yuva Yodha Energy Tech Hackathon.")
            still_segment("problem", SLIDES / "slide_02.png", "India's five thousand foundries waste fifty to eighty kilowatt-hours per tonne between melts in the same furnace, from operating practice alone. Nobody sees it until the monthly bill. MeltWise shows it while the metal is still in the furnace.")
            still_segment("architecture", SLIDES / "slide_04.png", "Here is what we built. The furnace meter talks Modbus to an offline-first edge gateway. A physics-informed model, a live advisor, a scheduler and a carbon record run behind a web app. We have no plant yet, so a calibrated furnace simulator plays the plant and the meter, and every result is measured against its ground truth.")

            await live_segment(cdp)

            mgr = await capture_app(cdp, "manager", f"{API}/?v=m#/manager")
            still_segment("manager", mgr, "The manager sees energy per tonne for every day: thirty days before MeltWise, and thirty days with it. And where the extra kilowatt-hours went.")
            detail = await capture_app(cdp, "detail", f"{API}/?v=d#/melt-3",
                                       "document.getElementById('melt-detail').scrollIntoView({block: 'end'}); 1")
            still_segment("detail", detail, "Any melt opens its power curve and breakdown. This one used six hundred and sixty-seven kilowatt-hours per tonne, against six hundred and ten for best practice on its charge.")
            plan = await capture_app(cdp, "planner", f"{API}/?v=p#/planner")
            still_segment("planner", plan, "The planner starts each heat so the metal is ready when the moulds are. Over three hundred simulated days, it cut holding time by half.")
            buyer = await capture_app(cdp, "buyer", f"{API}/?v=b#/buyer")
            still_segment("buyer", buyer, "And every batch gets a metered carbon record, which a buyer can download.")
    finally:
        chrome.terminate()
        chrome.wait(timeout=10)
        subprocess.run(["pkill", "-f", "--", f"--user-data-dir={profile}"])
        shutil.rmtree(profile, ignore_errors=True)

    still_segment("accuracy", SLIDES / "slide_09.png", "We measured everything against ground truth. MeltWise predicts each melt's energy within one point four percent, and finds each practice cause with a correlation of point nine one to point nine nine.")
    still_segment("pilot", SLIDES / "slide_10.png", "In a simulated sixty-day pilot, with operators following sixty percent of prompts, energy per tonne fell by twenty-two point six kilowatt-hours: four point three lakh rupees, and thirty-eight tonnes of carbon dioxide a year, for one furnace. These are simulation results. Next, we test on a real furnace.")
    still_segment("end", SLIDES / "slide_13.png", "MeltWise. Every melt, measured. By Surianandhan Sridhar and Sameera Hussainy Pattan.")

    # join, then burn captions
    lst = WORK / "segments.txt"
    lst.write_text("".join(f"file '{s}'\n" for s in segments))
    joined = WORK / "joined.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)])
    srt = WORK / "captions.srt"

    def ts(t):
        h, rem = divmod(t, 3600)
        m, s = divmod(rem, 60)
        return f"{int(h):02d}:{int(m):02d}:{s:06.3f}".replace(".", ",")
    srt.write_text("".join(f"{n}\n{ts(a)} --> {ts(b)}\n{text}\n\n" for n, (a, b, text) in enumerate(captions, 1)))
    style = "FontName=Arial,FontSize=15,PrimaryColour=&H00FFFFFF,BackColour=&H99000000,BorderStyle=4,Outline=0,Shadow=0,MarginV=22"
    run(["ffmpeg", "-y", "-i", str(joined), "-vf", f"subtitles={srt}:force_style='{style}'", "-c:v", "libx264", "-crf", "22",
         "-preset", "medium", "-c:a", "copy", "-movflags", "+faststart", str(OUT)])
    shutil.copy(srt, OUT.with_suffix(".srt"))
    print("video", OUT, round(timeline, 1), "s")


asyncio.run(main())
