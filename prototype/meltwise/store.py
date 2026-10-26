"""SQLite store for finished melts: signals, operator log, MeltWise's explanation and the carbon record."""

import json
import sqlite3
from datetime import datetime, timedelta

import numpy as np

from . import config as C
from .features import Observed
from .simulator import Charge

SCHEMA = """
CREATE TABLE IF NOT EXISTS melts (
    id INTEGER PRIMARY KEY,
    plant TEXT NOT NULL,
    furnace TEXT NOT NULL,
    period TEXT NOT NULL,            -- 'before' (observe only) or 'after' (MeltWise on)
    started_at TEXT NOT NULL,        -- ISO 8601, plant local time
    charge TEXT NOT NULL,            -- JSON: weight_t, pig, returns, steel, borings, grade, lining_age
    energy_kwh REAL NOT NULL,
    sec_kwh_t REAL NOT NULL,
    series TEXT NOT NULL,            -- JSON: dt_s, power_kw[], lid_open[]
    events TEXT NOT NULL,            -- JSON: operator log (charge, dip with temp_c, tap)
    explain TEXT                     -- JSON: MeltWise's expected kWh/t and waste by cause
);
"""

PILOT_START = datetime(2026, 9, 1, 6, 0)
HEAT_SPACING_MIN = 85


def connect(path):
    db = sqlite3.connect(path, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def started_at(day, heat_no):
    return (PILOT_START + timedelta(days=day, minutes=heat_no * HEAT_SPACING_MIN)).isoformat(timespec="minutes")


def insert_melt(db, *, plant, furnace, period, started, record, explain=None):
    c = record.charge
    charge = {"weight_t": c.weight_t, "pig": c.pig, "returns": c.returns, "steel": c.steel,
              "borings": c.borings, "grade": c.grade, "lining_age": c.lining_age}
    events = [{k: v for k, v in e.items() if k != "true_temp_c"} for e in record.events]
    series = {"dt_s": 10.0, "power_kw": [round(float(p), 1) for p in record.power_kw],
              "lid_open": [int(x) for x in record.lid_open]}
    db.execute(
        "INSERT INTO melts (plant, furnace, period, started_at, charge, energy_kwh, sec_kwh_t, series, events, explain)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (plant, furnace, period, started, json.dumps(charge), record.energy_kwh, record.sec_kwh_t,
         json.dumps(series), json.dumps(events, default=float), json.dumps(explain) if explain else None))


def to_observed(row):
    charge = Charge(**json.loads(row["charge"]))
    series = json.loads(row["series"])
    n = len(series["power_kw"])
    return Observed(charge, np.arange(n) * series["dt_s"], np.array(series["power_kw"]),
                    np.array(series["lid_open"], dtype=bool), json.loads(row["events"]), series["dt_s"])


def carbon_record(row):
    """Per-batch Scope 2 (location-based) electricity emissions, GHG Protocol style."""
    charge = json.loads(row["charge"])
    kwh = row["energy_kwh"]
    return {
        "batch_id": f"MW-{row['furnace']}-{row['id']:05d}",
        "plant": row["plant"], "furnace": row["furnace"], "started_at": row["started_at"],
        "grade": "SG iron" if charge["grade"] == "sg" else "Grey iron",
        "liquid_metal_t": round(charge["weight_t"], 3),
        "electricity_kwh": round(kwh, 1),
        "kwh_per_t": round(row["sec_kwh_t"], 1),
        "emission_factor_kg_per_kwh": C.GRID_EF_KG_KWH,
        "scope2_kg_co2": round(kwh * C.GRID_EF_KG_KWH, 1),
        "kg_co2_per_t": round(row["sec_kwh_t"] * C.GRID_EF_KG_KWH, 1),
        "method": "GHG Protocol Scope 2, location-based; India grid factor 0.710 kg CO2/kWh "
                  "(CEA CO2 Baseline Database v21.0, FY2024-25)",
        "data_source": "Metered: furnace panel energy meter over Modbus, 10-second readings",
    }
