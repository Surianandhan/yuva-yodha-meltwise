"""Physics-based simulator of one induction-furnace melt ("heat"), in 10-second steps.

It stands in for a real furnace until we have plant data. Every melt has:
  * a charge (weight, scrap mix, grade, lining age) that the operator logs,
  * a practice (overshoot, holding, avoidable lid-open time, under-powered
    melting, sand and rust) that MeltWise must infer from the signals,
  * hidden factors (coupling efficiency, supply ripple) that nobody measures.

Because we can re-run the same melt with any practice gap removed, the simulator
also gives the ground truth for every kWh of waste, which is how MeltWise's
detectors and models are scored.
"""

from dataclasses import dataclass, field, replace
import math

import numpy as np

from . import config as C
from . import physics

DT_S = 10.0
PHASES = ("melt", "dip", "superheat", "hold", "tap")
CAUSES = ("overshoot", "holding", "lid", "underpower", "sand")


@dataclass(frozen=True)
class Charge:
    weight_t: float
    pig: float
    returns: float
    steel: float
    borings: float
    grade: str
    lining_age: int

    @property
    def spec_temp_c(self):
        return C.SPEC_TAP_TEMP_C[self.grade]


@dataclass(frozen=True)
class Practice:
    overshoot_c: float = 0.0          # tap temperature above spec the operator aims for
    holding_min: float = 0.0          # molten metal waiting for moulds
    lid_avoidable_min: float = 0.0    # lid left open beyond charging, dips and tapping
    underpower_min: float = 0.0       # melting spent at 70-80% of rated power
    sand_kg_t: float = 0.0            # sand and rust in the charge
    lid_episode_cap_min: float | None = None       # set when operators close the lid on a prompt
    underpower_segment_cap_min: float | None = None  # set when operators restore power on a prompt


@dataclass(frozen=True)
class Plant:
    """A furnace's true constants. MeltWise never sees these; it learns them from the plant's own melts."""
    eta_factor: float = 1.0
    loss_factor: float = 1.0
    lid_factor: float = 1.0


@dataclass(frozen=True)
class Hidden:
    eta_factor: float                 # this melt's coupling, including the plant's own factor
    seed: int
    loss_factor: float = 1.0
    lid_factor: float = 1.0


@dataclass
class MeltRecord:
    charge: Charge
    practice: Practice
    hidden: Hidden
    t_s: np.ndarray
    power_kw: np.ndarray
    lid_open: np.ndarray
    phase: np.ndarray        # index into PHASES (ground truth, not visible to MeltWise)
    temp_c: np.ndarray       # true bath temperature (not visible to MeltWise)
    events: list = field(default_factory=list)  # operator-app log: charge, dip, tap

    @property
    def energy_kwh(self):
        return float(self.power_kw.sum() * DT_S / 3600.0)

    @property
    def sec_kwh_t(self):
        return self.energy_kwh / self.charge.weight_t

    @property
    def duration_min(self):
        return len(self.t_s) * DT_S / 60.0

    @property
    def tap_temp_c(self):
        return next(e["true_temp_c"] for e in self.events if e["kind"] == "tap")


def random_charge(rng):
    pig, returns, steel, borings = rng.dirichlet([3.0, 4.0, 3.0, 1.5])
    return Charge(
        weight_t=round(float(rng.uniform(0.80, 1.00)), 3),
        pig=float(pig), returns=float(returns), steel=float(steel), borings=float(borings),
        grade="sg" if rng.random() < 0.3 else "grey",
        lining_age=int(rng.integers(0, 400)),
    )


def baseline_practice(rng, charge):
    """Today's practice, centred on the gaps in Research_Notes E4 (~57 kWh/t of avoidable loss).

    Under-powered time is the time spent at 70-80% of rated power: BEE found 35-40% of heat time (F3).
    """
    def gamma(mean, sd):
        return float(rng.gamma((mean / sd) ** 2, sd**2 / mean))

    holding = 0.0 if rng.random() < 0.3 else min(float(rng.exponential(15.0 / 0.7)), 60.0)
    sand = 6.0 + 35.0 * charge.borings + 12.0 * charge.returns + float(rng.normal(0.0, 3.0))
    return Practice(
        overshoot_c=gamma(40.0, 15.0),
        holding_min=holding,
        lid_avoidable_min=gamma(6.0, 3.0),
        underpower_min=gamma(22.0, 8.0),
        sand_kg_t=max(sand, 0.0),
    )


def random_plant(rng):
    return Plant(eta_factor=float(rng.normal(1.0, 0.03)), loss_factor=float(rng.uniform(0.85, 1.15)),
                 lid_factor=float(rng.uniform(0.8, 1.2)))


def random_hidden(rng, plant=Plant()):
    return Hidden(eta_factor=plant.eta_factor * float(rng.normal(1.0, 0.015)), seed=int(rng.integers(0, 2**31)),
                  loss_factor=plant.loss_factor, lid_factor=plant.lid_factor)


def _lid_plan(practice):
    """Split avoidable lid-open minutes between 'left open after the first dip' and episodes while holding."""
    total = practice.lid_avoidable_min
    in_holding = min(total, max(practice.holding_min - 0.5, 0.0))
    after_dip = total - in_holding
    n = math.ceil(in_holding / 2.5)
    episodes = [in_holding / n] * n if n else []
    cap = practice.lid_episode_cap_min
    if cap is not None:
        after_dip = min(after_dip, cap)
        episodes = [min(e, cap) for e in episodes]
    return after_dip, episodes


def simulate(charge, practice, hidden, stop_superheat=None, max_minutes=240):
    """Run one melt. `stop_superheat(view)` lets MeltWise's advisor decide when to stop superheating."""
    rng = np.random.default_rng(hidden.seed)
    w = charge.weight_t
    spec = charge.spec_temp_c
    melt_heat = physics.required_melt_heat(w, charge.steel, practice.sand_kg_t * w)
    rated = C.RATED_POWER_KW

    split = rng.uniform(0.3, 0.7)
    seg_cap = practice.underpower_segment_cap_min
    segments = []
    for start, share in ((rng.uniform(3, 15), split), (rng.uniform(20, 35), 1 - split)):
        length = practice.underpower_min * share
        if seg_cap is not None:
            length = min(length, seg_cap)
        segments.append((start, start + length, rng.uniform(0.70, 0.80)))
    ripple = rng.normal(0.0, 0.01, size=int(max_minutes * 60 / DT_S) + 1)
    lid_after_dip, hold_episodes = _lid_plan(practice)

    heat = -C.LINING_SOAK_KWH
    t = 0.0
    phase = "melt"
    melt_clock = 0.0
    lid_until = C.CHARGE_LID_MIN * 60
    backcharges = list(C.BACKCHARGE_FRACTIONS)
    events = [{"kind": "charge", "t_s": 0.0}]
    phase_start = 0.0
    hold_target = None
    out_t, out_p, out_lid, out_phase, out_temp = [], [], [], [], []

    for step in range(len(ripple)):
        temp = physics.temperature(max(heat, 0.0), w, melt_heat)
        lid = t < lid_until

        if phase == "melt":
            if backcharges and heat >= backcharges[0] * melt_heat:
                backcharges.pop(0)
                events.append({"kind": "charge", "t_s": t})
                lid_until, lid = t + C.CHARGE_LID_MIN * 60, True
            if heat >= melt_heat and temp >= spec - 25:
                phase, phase_start = "dip", t
                events.append({"kind": "dip", "t_s": t, "temp_c": round(temp + rng.normal(0, 4), 1),
                               "true_temp_c": temp})
                lid_until, lid = t + (C.DIP_LID_MIN + lid_after_dip) * 60, True
        elif phase == "dip" and t >= phase_start + C.DIP_LID_MIN * 60:
            phase, phase_start = "superheat", t
        elif phase == "superheat":
            if stop_superheat is not None:
                done = stop_superheat({"t_s": t, "power_kw": out_p, "lid_open": out_lid, "events": events,
                                       "charge": charge, "dt_s": DT_S})
            else:
                done = temp >= spec + practice.overshoot_c
            if done or temp >= spec + 150:
                phase, phase_start, hold_target = "hold", t, temp
        if phase == "hold":
            held = (t - phase_start) / 60
            if held >= practice.holding_min + C.DIP_LID_MIN and not any(e["kind"] == "tap" for e in events):
                phase, phase_start = "tap", t
                events.append({"kind": "tap", "t_s": t, "true_temp_c": temp})
                lid_until, lid = t + C.TAP_MIN * 60, True
            else:
                start = 0.0
                for i, length in enumerate(hold_episodes):
                    start = (i + 0.5) * practice.holding_min / len(hold_episodes) - length / 2
                    if start <= held < start + length:
                        lid = True
                if held >= practice.holding_min and not any(e["kind"] == "dip" and e["t_s"] >= phase_start
                                                            for e in events):
                    events.append({"kind": "dip", "t_s": t, "temp_c": round(temp + rng.normal(0, 4), 1),
                                   "true_temp_c": temp})
                if held >= practice.holding_min:
                    lid = True  # final dip before tapping
        if phase == "tap" and t >= phase_start + C.TAP_MIN * 60:
            break

        if phase in ("melt", "superheat"):
            power = rated
            for start, end, factor in segments:
                if phase == "melt" and start <= melt_clock / 60 < end:
                    power = rated * factor
        elif phase == "dip":  # power is cut back to holding level while the operator dips and samples
            eta = physics.efficiency(temp, w, charge.borings, hidden.eta_factor)
            power = min(rated, physics.heat_loss_kw(temp, lid, charge.lining_age, hidden.loss_factor,
                                                    hidden.lid_factor) / eta)
        elif phase == "hold":
            eta = physics.efficiency(temp, w, charge.borings, hidden.eta_factor)
            power = min(rated, physics.heat_loss_kw(temp, lid, charge.lining_age, hidden.loss_factor, hidden.lid_factor) / eta)
            if temp < hold_target - 2:
                power = min(rated, power + 150.0)
        else:
            power = 0.0
        power *= 1.0 + ripple[step]

        eta = physics.efficiency(temp, w, charge.borings, hidden.eta_factor)
        loss = physics.heat_loss_kw(temp, lid, charge.lining_age, hidden.loss_factor, hidden.lid_factor)
        heat += (eta * power - loss) * DT_S / 3600.0

        out_t.append(t)
        out_p.append(power)
        out_lid.append(lid)
        out_phase.append(PHASES.index(phase))
        out_temp.append(temp)
        t += DT_S
        if phase == "melt":
            melt_clock += DT_S

    return MeltRecord(charge, practice, hidden, np.array(out_t), np.array(out_p), np.array(out_lid),
                      np.array(out_phase), np.array(out_temp), events)


def zeroed(practice, cause):
    field_name = {"overshoot": "overshoot_c", "holding": "holding_min", "lid": "lid_avoidable_min",
                  "underpower": "underpower_min", "sand": "sand_kg_t"}[cause]
    return replace(practice, **{field_name: 0.0})


def best_practice(practice):
    return Practice(lid_episode_cap_min=practice.lid_episode_cap_min,
                    underpower_segment_cap_min=practice.underpower_segment_cap_min)


def ground_truth(record):
    """kWh/t lost to each cause, from re-running the same melt with that gap removed."""
    actual = record.sec_kwh_t
    truth = {cause: actual - simulate(record.charge, zeroed(record.practice, cause), record.hidden).sec_kwh_t
             for cause in CAUSES}
    truth["best_sec"] = simulate(record.charge, best_practice(record.practice), record.hidden).sec_kwh_t
    return truth
