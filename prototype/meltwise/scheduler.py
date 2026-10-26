"""Melt scheduler: start each heat so metal is ready when the moulds are, at the cheapest tariff.

Today most furnaces start the next heat as soon as the last one is tapped. When
the moulding line is slower or breaks down, molten metal waits in the furnace
(BEE F3). MeltWise reads the moulding line's progress, forecasts when the next
moulds will be ready, and picks a start time that balances:
  * holding cost (metal kept hot, ~1.2 kWh per minute),
  * moulds waiting for metal (lost production, priced high),
  * the time-of-day tariff (solar hours cheaper, evening peak dearer) [F10].
"""

from dataclasses import dataclass

import numpy as np

from . import config as C

DAY_START_MIN = 6 * 60          # first shift starts 06:00
TURNAROUND_MIN = 5              # slag off, inspect lining, start charging
HOLD_KWH_PER_MIN = 1.2          # holding a ~0.9 t bath (simulator: ~1.3 kWh/min/t) [E3]
MOULD_WAIT_INR_PER_MIN = 60.0   # a stopped moulding line: labour and lost output [A]
MAX_HOLD_MIN = 30               # metallurgical limit on planned holding [A]
GRID_MIN = 5


def tariff_inr_kwh(minute_of_day):
    hour = (minute_of_day // 60) % 24
    if C.SOLAR_HOURS[0] <= hour < C.SOLAR_HOURS[1]:
        return C.TARIFF_INR_KWH * (1 - C.SOLAR_DISCOUNT)
    if C.PEAK_HOURS[0] <= hour < C.PEAK_HOURS[1]:
        return C.TARIFF_INR_KWH * C.PEAK_MULTIPLIER
    return C.TARIFF_INR_KWH


def energy_cost_inr(start_min, duration_min, kwh):
    """Cost of a melt whose energy is spread evenly from start to start + duration."""
    minutes = np.arange(int(start_min), int(start_min + duration_min))
    return kwh / max(len(minutes), 1) * sum(tariff_inr_kwh(m) for m in minutes)


@dataclass
class Heat:
    mould_ready_min: float      # when the moulds for this heat are actually ready
    forecast_min: float         # MeltWise's forecast at decision time
    melt_min: float             # charge to tap-ready, at full power
    melt_kwh: float


def random_day(rng, heats=8, interval_min=85.0, melt_min=62.0, melt_kwh=540.0):
    """One production day: planned mould times, delays partly visible in advance, partly breakdowns."""
    out, planned = [], DAY_START_MIN + 70.0
    for _ in range(heats):
        known = rng.exponential(8.0) if rng.random() < 0.5 else 0.0
        surprise = rng.exponential(15.0) if rng.random() < 0.25 else 0.0
        ready = planned + known + surprise
        out.append(Heat(ready, planned + known + rng.normal(0.0, 4.0), melt_min + rng.normal(0.0, 3.0), melt_kwh))
        planned += interval_min
    return out


def plan_start(earliest_min, heat, melt_estimate_min=62.0, buffer_min=3.0):
    """Best start time for one heat, given the forecast of when its moulds will be ready."""
    best, best_cost = earliest_min, float("inf")
    latest = max(earliest_min, heat.forecast_min - melt_estimate_min + MAX_HOLD_MIN)
    for start in np.arange(earliest_min, latest + GRID_MIN, GRID_MIN):
        ready = start + melt_estimate_min
        hold = max(heat.forecast_min - ready, 0.0)
        late = max(ready - (heat.forecast_min - buffer_min), 0.0)
        if hold > MAX_HOLD_MIN:
            continue
        cost = (energy_cost_inr(start, melt_estimate_min, heat.melt_kwh)
                + HOLD_KWH_PER_MIN * hold * tariff_inr_kwh(ready) + MOULD_WAIT_INR_PER_MIN * late)
        if cost < best_cost:
            best, best_cost = start, cost
    return float(best)


def run_day(heats, policy):
    """Play one day. policy: 'asap' (start right after the last tap) or 'meltwise'."""
    furnace_free, rows = DAY_START_MIN, []
    for heat in heats:
        start = furnace_free if policy == "asap" else plan_start(furnace_free, heat)
        metal_ready = start + heat.melt_min
        tap = max(metal_ready, heat.mould_ready_min)
        hold = tap - metal_ready
        cost = energy_cost_inr(start, heat.melt_min, heat.melt_kwh) + HOLD_KWH_PER_MIN * hold * tariff_inr_kwh(tap)
        rows.append({"start_min": start, "tap_min": tap, "holding_min": hold,
                     "mould_wait_min": max(metal_ready - heat.mould_ready_min, 0.0),
                     "kwh": heat.melt_kwh + HOLD_KWH_PER_MIN * hold, "cost_inr": cost})
        furnace_free = tap + C.TAP_MIN + TURNAROUND_MIN
    return rows


def evaluate(days=300, seed=11):
    rng = np.random.default_rng(seed)
    totals = {p: {"holding_min": [], "mould_wait_min": [], "kwh": [], "cost_inr": []} for p in ("asap", "meltwise")}
    for _ in range(days):
        heats = random_day(rng)
        for policy in totals:
            rows = run_day(heats, policy)
            for key in totals[policy]:
                totals[policy][key].append(np.mean([r[key] for r in rows]))
    summary = {p: {k: float(np.mean(v)) for k, v in vals.items()} for p, vals in totals.items()}
    summary["holding_reduction"] = 1 - summary["meltwise"]["holding_min"] / summary["asap"]["holding_min"]
    return summary


def format_clock(minute_of_day):
    return f"{int(minute_of_day // 60) % 24:02d}:{int(minute_of_day % 60):02d}"
