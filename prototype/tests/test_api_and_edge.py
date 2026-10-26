"""API endpoints, and the meter -> gateway path including a network outage."""

import importlib
import json
import threading
import time
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np
import pytest
from fastapi.testclient import TestClient

from meltwise import pilot, store
from meltwise import simulator as S


@pytest.fixture(scope="module")
def client(tmp_path_factory, monkeypatch_module):
    db_path = tmp_path_factory.mktemp("db") / "test.db"
    rows, _, _ = pilot.run(compliance=0.6, days=8)
    db = store.connect(db_path)
    for i, row in enumerate(rows):
        store.insert_melt(db, plant="Test", furnace="F1", period=row["period"],
                          started=store.started_at(row["day"], i % 8), record=row["record"],
                          explain=json.loads(json.dumps(row["explain"], default=float)))
    db.commit()
    monkeypatch_module.setenv("MELTWISE_DB", str(db_path))
    import meltwise.api as api
    return TestClient(importlib.reload(api).app)


@pytest.fixture(scope="module")
def monkeypatch_module():
    patch = pytest.MonkeyPatch()
    yield patch
    patch.undo()


def test_summary_and_melts(client):
    s = client.get("/api/summary").json()
    assert s["melts"] == 128 and s["sec_after"] < s["sec_before"]
    melts = client.get("/api/melts?limit=5").json()
    detail = client.get(f"/api/melts/{melts[0]['id']}").json()
    assert set(detail["explain"]["waste_kwh_t"]) == {"overshoot", "holding", "lid", "underpower", "sand"}
    assert client.get("/api/melts/999999").status_code == 404


def test_carbon_record_and_csv(client):
    record = client.get("/api/carbon?limit=1").json()[0]
    assert record["scope2_kg_co2"] == pytest.approx(record["electricity_kwh"] * 0.710, abs=0.2)
    csv_text = client.get("/api/carbon.csv").text
    assert csv_text.startswith("batch_id,") and len(csv_text.splitlines()) == 129


def test_schedule_validates_input(client):
    ok = client.post("/api/schedule", json={"heats": [{"mould_ready": "08:30"}, {"mould_ready": "10:00"}]})
    assert ok.status_code == 200 and len(ok.json()["plan"]) == 2
    assert client.post("/api/schedule", json={"heats": [{"mould_ready": "8.30"}]}).status_code == 422
    assert client.post("/api/schedule", json={"heats": []}).status_code == 422


def test_live_flow(client):
    charge = {"weight_t": 0.9, "pig": 0.3, "returns": 0.3, "steel": 0.3, "borings": 0.1, "grade": "grey",
              "lining_age": 50}
    assert client.post("/api/live/start", json={"melt_no": 0, "charge": charge}).status_code == 200
    assert client.post("/api/events", json={"kind": "charge", "t_s": 0}).status_code == 200
    assert client.post("/api/events", json={"kind": "boom", "t_s": 0}).status_code == 422
    readings = [{"device": "f1", "melt_no": 0, "t_s": 10.0 * i, "power_kw": 480.0, "energy_kwh": 0,
                 "lid_open": False} for i in range(30)]
    assert client.post("/api/ingest", json={"readings": readings}).json()["accepted"] == 30
    live = client.get("/api/live?lang=ta").json()
    assert live["active"] and any(p["code"] == "underpower" for p in live["prompts"])
    bad = dict(readings[0], power_kw=-5)
    assert client.post("/api/ingest", json={"readings": [bad]}).status_code == 422


class Receiver(BaseHTTPRequestHandler):
    """A stand-in MeltWise API that can be switched off to simulate a network outage."""
    received, online = [], True

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if not Receiver.online:
            self.send_response(503)
            self.end_headers()
            return
        Receiver.received.extend(body["readings"])
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"accepted": 1}')

    def log_message(self, *args):
        pass


def test_gateway_loses_nothing_during_outage(tmp_path):
    from meltwise.edge.gateway import Gateway
    from meltwise.edge.meter_sim import MeterSimulator

    rng = np.random.default_rng(4)
    charge = S.random_charge(rng)
    full = S.simulate(charge, S.baseline_practice(rng, charge), S.random_hidden(rng))
    steps = 80
    short = replace(full, t_s=full.t_s[:steps], power_kw=full.power_kw[:steps], lid_open=full.lid_open[:steps],
                    phase=full.phase[:steps], temp_c=full.temp_c[:steps])

    server = HTTPServer(("127.0.0.1", 0), Receiver)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    meter = MeterSimulator([short], port=5099, speed=250.0)   # one step every 40 ms
    meter.start()
    gateway = Gateway(f"http://127.0.0.1:{server.server_port}", str(tmp_path / "outbox.db"), port=5099, poll_s=0.01)
    stop = threading.Event()
    thread = gateway.start(stop)

    time.sleep(1.0)
    Receiver.online = False          # outage
    time.sleep(1.0)
    buffered = gateway.pending()
    Receiver.online = True
    meter.finished.wait(timeout=20)
    time.sleep(0.5)
    stop.set()
    thread.join(timeout=5)
    server.shutdown()

    times = [r["t_s"] for r in Receiver.received]
    assert buffered > 0                                  # readings piled up during the outage
    assert gateway.pending() == 0                        # and all of them were delivered afterwards
    assert len(times) == gateway.stored                  # nothing captured was lost
    assert times == sorted(times) and len(times) == len(set(times))  # in order, no duplicates
    assert len(times) >= 0.9 * steps                     # nearly every 40 ms meter step was polled
    # The meter's energy register is cumulative, so even a missed poll loses no kWh.
    assert Receiver.received[-1]["energy_kwh"] == pytest.approx(float(short.power_kw.sum()) * 10 / 3600, abs=0.01)
    sent = {r["t_s"]: r["power_kw"] for r in Receiver.received}
    assert all(abs(sent[t] - short.power_kw[int(t / 10)]) < 0.01 for t in sent)
