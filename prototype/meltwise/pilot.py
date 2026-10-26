"""Simulated plant pilot: 30 days observing, then 30 days with MeltWise switched on.

How operators respond is the biggest unknown, so each prompt is followed only with
probability `compliance`. Each lever's effect comes from the mechanism, not a
fixed percentage:
  * tapping: the operator stops superheating when MeltWise's soft sensor says
    the target is reached, so tap temperature depends on its real accuracy;
  * open lid: prompted after 45 s, closed about 30 s later;
  * under-power: prompted after 2 min, power restored about 30 s later;
  * holding: cut by the reduction the scheduler achieved in scheduler.evaluate();
  * sand and rust: after the first week, per-supplier charge-quality reports cut
    it by SAND_CUT (an assumption to test in a real pilot; the weakest lever).
"""

from dataclasses import replace

import numpy as np

from . import advisor as A
from . import features as F
from . import scheduler
from . import simulator as S
from .model import EnergyModel

HEATS_PER_DAY = 8
LID_CAP_MIN = 0.75 + 0.5
UNDERPOWER_CAP_MIN = 2.0 + 0.5
SAND_CUT = 0.30


def advised_practice(rng, practice, compliance, day_in_pilot, holding_reduction):
    follows = {lever: rng.random() < compliance for lever in ("tap", "lid", "underpower", "holding", "sand")}
    changes = {}
    if follows["lid"]:
        changes["lid_episode_cap_min"] = LID_CAP_MIN
    if follows["underpower"]:
        changes["underpower_segment_cap_min"] = UNDERPOWER_CAP_MIN
    if follows["holding"]:
        changes["holding_min"] = practice.holding_min * (1 - holding_reduction)
    if follows["sand"] and day_in_pilot >= 7:
        changes["sand_kg_t"] = practice.sand_kg_t * (1 - SAND_CUT)
    return replace(practice, **changes), follows["tap"]


def run(compliance=0.6, days=30, seed=2026, plant_seed=7, holding_reduction=None, with_truth=False):
    """Returns per-melt rows for both periods, and the model trained on the observe-only period."""
    rng = np.random.default_rng(seed)
    plant = S.random_plant(np.random.default_rng(plant_seed))
    if holding_reduction is None:
        holding_reduction = scheduler.evaluate()["holding_reduction"]

    rows, before = [], []
    for day in range(days):
        for _ in range(HEATS_PER_DAY):
            charge = S.random_charge(rng)
            record = S.simulate(charge, S.baseline_practice(rng, charge), S.random_hidden(rng, plant))
            before.append(record)
            rows.append({"day": day, "period": "before", "record": record})
    model = EnergyModel().fit([F.observe(r) for r in before])

    for day in range(days, 2 * days):
        for _ in range(HEATS_PER_DAY):
            charge = S.random_charge(rng)
            practice, follows_tap = advised_practice(rng, S.baseline_practice(rng, charge), compliance,
                                                     day - days, holding_reduction)
            stop = A.AdvisedOperator(charge, model) if follows_tap else None
            record = S.simulate(charge, practice, S.random_hidden(rng, plant), stop_superheat=stop)
            rows.append({"day": day, "period": "after", "record": record})

    for row in rows:
        row["explain"] = model.explain(F.observe(row["record"]))
        if with_truth:
            row["truth"] = S.ground_truth(row["record"])
    return rows, model, plant


def bootstrap_diff(a, b, rng, n=2000):
    a, b = np.asarray(a), np.asarray(b)
    diffs = [rng.choice(a, len(a)).mean() - rng.choice(b, len(b)).mean() for _ in range(n)]
    return float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))


def summarise(rows):
    rng = np.random.default_rng(0)
    sec = {p: [r["record"].sec_kwh_t for r in rows if r["period"] == p] for p in ("before", "after")}
    saved = float(np.mean(sec["before"]) - np.mean(sec["after"]))
    low, high = bootstrap_diff(sec["before"], sec["after"], rng)
    causes = list(S.CAUSES)
    by_cause = {p: {c: float(np.mean([r["explain"]["waste_kwh_t"][c] for r in rows if r["period"] == p]))
                    for c in causes} for p in ("before", "after")}
    overshoot = {p: float(np.mean([r["record"].tap_temp_c - r["record"].charge.spec_temp_c
                                   for r in rows if r["period"] == p])) for p in ("before", "after")}
    return {"sec_before": float(np.mean(sec["before"])), "sec_after": float(np.mean(sec["after"])),
            "saved_kwh_t": saved, "saved_ci95": (low, high), "saved_pct": 100 * saved / np.mean(sec["before"]),
            "waste_by_cause": by_cause, "true_overshoot_c": overshoot, "melts_per_period": len(sec["before"])}
