"""MeltWise API and web app.

    uvicorn meltwise.api:app --port 8000      (after scripts/build_demo_data.py)

Views: operator (live melt with prompts), manager (kWh/t, waste by cause,
savings), planner (melt schedule), buyer (per-batch carbon records).
"""

import csv
import io
import json
import os
import threading
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config as C
from . import scheduler
from . import store
from .advisor import Advisor
from .model import EnergyModel
from .simulator import CAUSES, Charge

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("MELTWISE_DB", ROOT / "data" / "meltwise.db"))
WEB = ROOT / "web"
TONNES_PER_YEAR = 2400   # one 1 t furnace, 8 heats a day, 300 days [E4]

app = FastAPI(title="MeltWise", version="0.2.0")
db = store.connect(DB_PATH)
lock = threading.Lock()


def _train():
    rows = db.execute("SELECT * FROM melts WHERE period = 'before'").fetchall()
    return EnergyModel().fit([store.to_observed(r) for r in rows]) if len(rows) >= 50 else None


model = _train()


def _rows(where="", params=()):
    return db.execute(f"SELECT * FROM melts {where} ORDER BY started_at", params).fetchall()


def _explain(row):
    return json.loads(row["explain"]) if row["explain"] else None


# ---------------- manager view ----------------

@app.get("/api/summary")
def summary():
    rows = _rows()
    if not rows:
        raise HTTPException(404, "No melts yet. Run scripts/build_demo_data.py.")
    periods = {p: [r for r in rows if r["period"] == p] for p in ("before", "after")}
    sec = {p: float(np.mean([r["sec_kwh_t"] for r in rs])) if rs else None for p, rs in periods.items()}
    saved = sec["before"] - sec["after"] if sec["after"] is not None else 0.0
    waste = {p: {c: float(np.mean([_explain(r)["waste_kwh_t"][c] for r in rs])) for c in CAUSES}
             for p, rs in periods.items() if rs}
    daily = {}
    for r in rows:
        day = r["started_at"][:10]
        daily.setdefault(day, {"period": r["period"], "sec": []})["sec"].append(r["sec_kwh_t"])
    kwh_year = saved * TONNES_PER_YEAR
    return {
        "plant": rows[0]["plant"], "melts": len(rows),
        "sec_before": sec["before"], "sec_after": sec["after"], "saved_kwh_t": saved,
        "saved_pct": 100 * saved / sec["before"] if sec["before"] else 0.0,
        "annual": {"kwh": kwh_year, "inr": kwh_year * C.TARIFF_INR_KWH,
                   "t_co2": kwh_year * C.GRID_EF_KG_KWH / 1000, "tonnes": TONNES_PER_YEAR},
        "waste_by_cause": waste,
        "daily": [{"day": d, "period": v["period"], "sec": float(np.mean(v["sec"])), "melts": len(v["sec"])}
                  for d, v in sorted(daily.items())],
        "model": model.coefficients() if model else None,
    }


@app.get("/api/melts")
def melts(period: str | None = None, limit: int = 50):
    where, params = ("WHERE period = ?", (period,)) if period else ("", ())
    rows = _rows(where, params)[-limit:]
    out = []
    for r in reversed(rows):
        ex = _explain(r)
        out.append({"id": r["id"], "started_at": r["started_at"], "period": r["period"],
                    "grade": json.loads(r["charge"])["grade"], "sec_kwh_t": r["sec_kwh_t"],
                    "expected_best_kwh_t": ex["expected_best_kwh_t"], "waste_kwh_t": ex["waste_kwh_t"]})
    return out


@app.get("/api/melts/{melt_id}")
def melt(melt_id: int):
    row = db.execute("SELECT * FROM melts WHERE id = ?", (melt_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "No such melt")
    series = json.loads(row["series"])
    return {"id": row["id"], "started_at": row["started_at"], "period": row["period"],
            "charge": json.loads(row["charge"]), "series": series, "events": json.loads(row["events"]),
            "explain": _explain(row), "carbon": store.carbon_record(row)}


# ---------------- buyer view ----------------

@app.get("/api/carbon")
def carbon(limit: int = 100):
    return [store.carbon_record(r) for r in reversed(_rows()[-limit:])]


@app.get("/api/carbon.csv", response_class=PlainTextResponse)
def carbon_csv(since: str = "", until: str = "9999"):
    rows = [store.carbon_record(r) for r in _rows("WHERE started_at >= ? AND started_at < ?", (since, until))]
    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return PlainTextResponse(buf.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=meltwise_carbon.csv"})


# ---------------- planner view ----------------

class PlanHeat(BaseModel):
    mould_ready: str = Field(pattern=r"^\d{2}:\d{2}$", description="forecast HH:MM when moulds will be ready")


class PlanRequest(BaseModel):
    furnace_free: str = Field("06:00", pattern=r"^\d{2}:\d{2}$")
    melt_min: float = Field(62.0, gt=10, lt=240)
    melt_kwh: float = Field(540.0, gt=50, lt=2000)
    heats: list[PlanHeat] = Field(min_length=1, max_length=24)


def _minutes(clock):
    hours, minutes = clock.split(":")
    return int(hours) * 60 + int(minutes)


@app.post("/api/schedule")
def plan(request: PlanRequest):
    """Recommended start time for each heat, given the moulding line's forecast."""
    free, out = _minutes(request.furnace_free), []
    for h in request.heats:
        heat = scheduler.Heat(_minutes(h.mould_ready), _minutes(h.mould_ready), request.melt_min, request.melt_kwh)
        start = scheduler.plan_start(free, heat, melt_estimate_min=request.melt_min)
        ready = start + request.melt_min
        out.append({"start": scheduler.format_clock(start), "metal_ready": scheduler.format_clock(ready),
                    "mould_ready": h.mould_ready, "tariff_inr_kwh": round(scheduler.tariff_inr_kwh(start), 2)})
        free = max(ready, heat.mould_ready_min) + C.TAP_MIN + scheduler.TURNAROUND_MIN
    return {"plan": out}


@app.get("/api/schedule/demo")
def schedule_demo(seed: int = 3):
    heats = scheduler.random_day(np.random.default_rng(seed))
    result = {}
    for policy in ("asap", "meltwise"):
        rows = scheduler.run_day(heats, policy)
        result[policy] = {
            "heats": [{"start": scheduler.format_clock(r["start_min"]), "tap": scheduler.format_clock(r["tap_min"]),
                       "holding_min": round(r["holding_min"], 1), "mould_wait_min": round(r["mould_wait_min"], 1),
                       "cost_inr": round(r["cost_inr"])} for r in rows],
            "holding_min": round(sum(r["holding_min"] for r in rows), 1),
            "cost_inr": round(sum(r["cost_inr"] for r in rows)),
        }
    result["moulds"] = [scheduler.format_clock(h.mould_ready_min) for h in heats]
    return result


# ---------------- operator view (live) ----------------

class LiveStart(BaseModel):
    melt_no: int = 0
    lang: str = Field("en", pattern="^(en|hi|ta)$")
    charge: dict


class Event(BaseModel):
    kind: str = Field(pattern="^(charge|dip|tap)$")
    t_s: float = Field(ge=0)
    temp_c: float | None = Field(None, gt=0, lt=2000)


class Reading(BaseModel):
    device: str
    melt_no: int
    t_s: float = Field(ge=0)
    power_kw: float = Field(ge=0, lt=5000)
    energy_kwh: float = Field(ge=0)
    lid_open: bool
    read_at: float | None = None


class Ingest(BaseModel):
    readings: list[Reading] = Field(max_length=1000)


live = {"advisor": None, "melt_no": None, "charge": None, "pending": [], "trace": [], "received": 0}


@app.post("/api/live/start")
def live_start(body: LiveStart):
    try:
        charge = Charge(**body.charge)
    except TypeError as exc:
        raise HTTPException(422, f"Bad charge: {exc}") from exc
    with lock:
        live.update(advisor=Advisor(charge, model, lang=body.lang), melt_no=body.melt_no, charge=body.charge,
                    pending=[], trace=[])
    return {"ok": True, "budget_kwh": live["advisor"].budget_kwh}


@app.post("/api/events")
def live_event(event: Event):
    with lock:
        if live["advisor"] is None:
            raise HTTPException(409, "No live melt")
        live["pending"].append(event.model_dump())
        live["pending"].sort(key=lambda e: e["t_s"])
    return {"ok": True}


@app.post("/api/ingest")
def ingest(body: Ingest):
    """Readings from the edge gateway, oldest first."""
    accepted = 0
    with lock:
        for r in sorted(body.readings, key=lambda r: (r.melt_no, r.t_s)):
            live["received"] += 1
            advisor = live["advisor"]
            if advisor is None or r.melt_no != live["melt_no"]:
                continue
            due = [e for e in live["pending"] if e["t_s"] <= r.t_s]
            live["pending"] = [e for e in live["pending"] if e["t_s"] > r.t_s]
            advisor.update(r.t_s, r.power_kw, r.lid_open, due)
            state = advisor.state()
            live["trace"].append({"t_s": r.t_s, "power_kw": r.power_kw, "lid_open": r.lid_open,
                                  "est_temp_c": state["est_temp_c"], "energy_kwh": state["energy_kwh"]})
            accepted += 1
    return {"accepted": accepted}


@app.get("/api/live")
def live_state(lang: str = "en"):
    with lock:
        advisor = live["advisor"]
        if advisor is None:
            return {"active": False}
        prompts = [{"t_s": p["t_s"], "code": p["code"], "message": p["text"].get(lang, p["message"])}
                   for p in advisor.prompts]
        return {"active": True, "melt_no": live["melt_no"], "charge": live["charge"],
                "spec_temp_c": advisor.charge.spec_temp_c, "state": advisor.state(),
                "trace": live["trace"][-600:], "prompts": prompts[-12:], "rated_kw": C.RATED_POWER_KW}


# ---------------- web ----------------

@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")
