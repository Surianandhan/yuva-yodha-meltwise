"""End-to-end live demo: simulated meter -> Modbus TCP -> edge gateway -> MeltWise API -> operator screen.

Start the API first (uvicorn meltwise.api:app --port 8000), then:

    python scripts/live_demo.py [--melts 3] [--speed 40] [--lang en|hi|ta] [--outage 20]

--outage N cuts the gateway's network for N seconds mid-melt to show that buffered
readings arrive late but complete.

The "operator app" here is simulated: it posts the charge details, temperature
dips and the tap at the moments the simulated operator performs them.
"""

import argparse
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from meltwise import simulator as S  # noqa: E402
from meltwise.edge.gateway import Gateway  # noqa: E402
from meltwise.edge.meter_sim import MeterSimulator  # noqa: E402


def charge_dict(c):
    return {"weight_t": c.weight_t, "pig": c.pig, "returns": c.returns, "steel": c.steel,
            "borings": c.borings, "grade": c.grade, "lining_age": c.lining_age}


def operator_app(api, meter, melts, lang, stop):
    """Posts what an operator would enter on the tablet, in step with the meter."""
    current, posted = -1, 0
    while not stop.is_set() and not meter.finished.is_set():
        melt_no, step = meter.position
        if melt_no != current:
            current, posted = melt_no, 0
            httpx.post(f"{api}/api/live/start", json={"melt_no": melt_no, "lang": lang,
                                                      "charge": charge_dict(melts[melt_no].charge)}, timeout=3)
        events = melts[melt_no].events
        while posted < len(events) and events[posted]["t_s"] <= step * 10.0:
            e = {k: v for k, v in events[posted].items() if k in ("kind", "t_s", "temp_c")}
            httpx.post(f"{api}/api/events", json=e, timeout=3)
            posted += 1
        time.sleep(0.05)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--melts", type=int, default=3)
    parser.add_argument("--speed", type=float, default=40.0)
    parser.add_argument("--lang", default="en", choices=("en", "hi", "ta"))
    parser.add_argument("--port", type=int, default=5020)
    parser.add_argument("--seed", type=int, default=12)
    parser.add_argument("--outage", type=float, default=0.0, help="seconds of network outage mid-melt")
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    plant = S.random_plant(np.random.default_rng(7))
    melts = []
    for _ in range(args.melts):
        charge = S.random_charge(rng)
        melts.append(S.simulate(charge, S.baseline_practice(rng, charge), S.random_hidden(rng, plant)))

    meter = MeterSimulator(melts, port=args.port, speed=args.speed)
    meter.start()
    time.sleep(1.0)
    stop = threading.Event()
    gateway = Gateway(args.api, str(Path(tempfile.mkdtemp()) / "outbox.db"), port=args.port,
                      poll_s=min(0.25, 10.0 / args.speed / 2))
    threading.Thread(target=operator_app, args=(args.api, meter, melts, args.lang, stop), daemon=True).start()

    real_api = gateway.api_url
    gateway_thread = gateway.start(stop)
    print(f"Playing {args.melts} melts at {args.speed:g}x. Open {args.api} and choose Operator.")
    outage_done = args.outage <= 0
    while not meter.finished.is_set():
        time.sleep(1.0)
        if not outage_done and meter.position[1] > 200:
            gateway.api_url = "http://127.0.0.1:9"   # unreachable: the gateway keeps buffering
            print(f"Network cut for {args.outage:g} s ...")
            time.sleep(args.outage)
            print(f"  buffered readings waiting: {gateway.pending()}")
            gateway.api_url = real_api
            outage_done = True
        print(f"melt {meter.position[0] + 1}/{args.melts}  t={meter.position[1] * 10 / 60:5.1f} min  "
              f"sent={gateway.sent}  buffered={gateway.pending()}", end="\r")
    time.sleep(2.0)
    stop.set()
    gateway_thread.join(timeout=5)
    total = sum(len(m.t_s) for m in melts)
    print(f"\nDone. Readings sent: {gateway.sent} of {total} meter steps; still buffered: {gateway.pending()}; "
          f"failed posts retried: {gateway.failed_posts}")


if __name__ == "__main__":
    main()
