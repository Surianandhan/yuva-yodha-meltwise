"""Simulator, measurement, model, advisor and scheduler."""

import numpy as np
import pytest

from meltwise import advisor as A
from meltwise import features as F
from meltwise import scheduler
from meltwise import simulator as S
from meltwise.model import EnergyModel

KNOWN = S.Practice(overshoot_c=30, holding_min=12, lid_avoidable_min=4, underpower_min=20, sand_kg_t=10)


def baseline_melts(n, seed=0, plant=S.Plant()):
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        charge = S.random_charge(rng)
        out.append(S.simulate(charge, S.baseline_practice(rng, charge), S.random_hidden(rng, plant)))
    return out


@pytest.fixture(scope="module")
def known_melt():
    charge = S.Charge(0.95, 0.2, 0.4, 0.3, 0.1, "grey", 120)
    return S.simulate(charge, KNOWN, S.Hidden(eta_factor=1.0, seed=5))


@pytest.fixture(scope="module")
def trained():
    plant = S.random_plant(np.random.default_rng(7))
    return plant, EnergyModel().fit([F.observe(r) for r in baseline_melts(240, seed=1, plant=plant)])


def test_simulator_calibrated_to_published_figures():
    melts = baseline_melts(60)
    sec = np.mean([m.sec_kwh_t for m in melts])
    best = np.mean([S.ground_truth(m)["best_sec"] for m in melts[:20]])
    assert 610 < sec < 690          # Phase 1 baseline 650 kWh/t
    assert 560 < best < 620         # DOE best practice 593 kWh/t


def test_removing_every_gap_saves_energy(known_melt):
    truth = S.ground_truth(known_melt)
    assert truth["best_sec"] < known_melt.sec_kwh_t - 30
    assert all(truth[c] > 0 for c in ("overshoot", "holding", "lid", "underpower", "sand"))


def test_measurements_recover_known_practice(known_melt):
    m = F.measure(F.observe(known_melt))
    assert m["holding_min"] == pytest.approx(12, abs=0.5)
    assert m["lid_avoidable_min"] == pytest.approx(4, abs=0.5)
    assert m["underpower_min"] == pytest.approx(20, abs=1.0)
    assert m["overshoot_c"] == pytest.approx(30, abs=15)   # dip readings carry +-4 C noise plus step overshoot


def test_observed_melt_hides_ground_truth(known_melt):
    obs = F.observe(known_melt)
    assert all("true_temp_c" not in e for e in obs.events)
    assert not hasattr(obs, "temp_c") and not hasattr(obs, "practice")


def test_model_accuracy_on_held_out_melts(trained):
    plant, model = trained
    errors, cause_errors = [], []
    for record in baseline_melts(40, seed=9, plant=plant):
        ex, truth = model.explain(F.observe(record)), S.ground_truth(record)
        errors.append(abs(ex["predicted_kwh_t"] - record.sec_kwh_t))
        cause_errors += [abs(ex["waste_kwh_t"][c] - truth[c]) for c in ("holding", "lid", "underpower")]
    assert np.mean(errors) < 15
    assert np.mean(cause_errors) < 5


def test_advisor_prompts_in_three_languages(known_melt, trained):
    _, model = trained
    advisor = A.Advisor(known_melt.charge, model, lang="hi")
    obs, events, k = F.observe(known_melt), sorted(F.observe(known_melt).events, key=lambda e: e["t_s"]), 0
    for t, power, lid in zip(obs.t_s, obs.power_kw, obs.lid_open):
        due = []
        while k < len(events) and events[k]["t_s"] <= t:
            due.append(events[k])
            k += 1
        advisor.update(t, power, lid, due)
    codes = {p["code"] for p in advisor.prompts}
    assert {"underpower", "dip_now", "tap_ready", "lid_open", "holding"} <= codes
    for prompt in advisor.prompts:
        assert set(prompt["text"]) == {"en", "hi", "ta"} and "{" not in prompt["message"]


def test_following_tap_prompt_cuts_overshoot(trained):
    plant, model = trained
    rng = np.random.default_rng(3)
    base, advised = [], []
    for _ in range(25):
        charge = S.random_charge(rng)
        practice, hidden = S.baseline_practice(rng, charge), S.random_hidden(rng, plant)
        base.append(S.simulate(charge, practice, hidden).tap_temp_c - charge.spec_temp_c)
        advised.append(S.simulate(charge, practice, hidden, stop_superheat=A.AdvisedOperator(charge, model)).tap_temp_c
                       - charge.spec_temp_c)
    assert np.mean(advised) < 12 < np.mean(base)
    assert min(advised) > -15


def test_scheduler_cuts_holding_without_starving_moulds():
    result = scheduler.evaluate(days=60)
    assert result["holding_reduction"] > 0.3
    assert result["meltwise"]["mould_wait_min"] < result["asap"]["mould_wait_min"] + 2


def test_plan_never_starts_before_furnace_is_free():
    heat = scheduler.Heat(mould_ready_min=600, forecast_min=600, melt_min=62, melt_kwh=540)
    start = scheduler.plan_start(560, heat)
    assert start >= 560
    assert 600 - (start + 62) <= scheduler.MAX_HOLD_MIN
