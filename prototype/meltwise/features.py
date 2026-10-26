"""What MeltWise can measure about a melt, from signals a real plant has.

Inputs per melt: meter power (kW, every 10 s), the lid limit switch, and the
operator app's log (charge details, charging events, temperature dips, tap).
Nothing here reads the simulator's hidden temperatures or practice.
"""

from dataclasses import dataclass

import numpy as np

from . import config as C
from . import physics


@dataclass
class Observed:
    charge: object
    t_s: np.ndarray
    power_kw: np.ndarray
    lid_open: np.ndarray
    events: list
    dt_s: float = 10.0

    @property
    def energy_kwh(self):
        return float(self.power_kw.sum() * self.dt_s / 3600.0)

    @property
    def sec_kwh_t(self):
        return self.energy_kwh / self.charge.weight_t


def observe(record):
    """Strip everything a plant could not measure."""
    events = [{k: v for k, v in e.items() if k != "true_temp_c"} for e in record.events]
    return Observed(record.charge, record.t_s, record.power_kw, record.lid_open, events)


def _necessary_lid(obs):
    """Lid-open time that is part of normal work: charging, dips and tapping."""
    mask = np.zeros(len(obs.t_s), dtype=bool)
    for e in obs.events:
        minutes = C.TAP_MIN if e["kind"] == "tap" else C.CHARGE_LID_MIN if e["kind"] == "charge" else C.DIP_LID_MIN
        mask |= (obs.t_s >= e["t_s"]) & (obs.t_s < e["t_s"] + minutes * 60)
    return mask


def measure(obs):
    """Measured practice for one finished melt."""
    rated, dt_min = C.RATED_POWER_KW, obs.dt_s / 60.0
    dips = [e for e in obs.events if e["kind"] == "dip"]
    tap_t = next(e["t_s"] for e in obs.events if e["kind"] == "tap")
    first_dip_t, final_dip = dips[0]["t_s"], dips[-1]

    melting = obs.t_s < first_dip_t
    low = melting & (obs.power_kw < C.UNDERPOWER_THRESHOLD * rated)
    after_dip = (obs.t_s >= first_dip_t + C.DIP_LID_MIN * 60) & (obs.t_s < tap_t)
    holding_idx = np.flatnonzero(after_dip & (obs.power_kw < 0.4 * rated))
    hold_start = obs.t_s[holding_idx[0]] if len(holding_idx) else final_dip["t_s"]
    avoidable_lid = obs.lid_open & ~_necessary_lid(obs) & (obs.t_s < tap_t)

    return {
        "melt_min": first_dip_t / 60.0,
        "underpower_min": float(low.sum() * dt_min),
        "underpower_lost_min": float(np.sum(1.0 - obs.power_kw[low] / rated) * dt_min),
        "superheat_min": max((hold_start - first_dip_t) / 60.0 - C.DIP_LID_MIN, 0.0),
        "holding_min": max((tap_t - hold_start) / 60.0 - C.DIP_LID_MIN, 0.0),
        "lid_avoidable_min": float(avoidable_lid.sum() * dt_min),
        "first_dip_c": dips[0]["temp_c"],
        "tap_temp_c": final_dip["temp_c"],
        "overshoot_c": final_dip["temp_c"] - obs.charge.spec_temp_c,
    }


def physics_terms(charge, m):
    """Nominal-physics kWh/t for each part of the melt. The energy model learns how much each term really costs."""
    w = charge.weight_t
    melt_heat = physics.required_melt_heat(w, charge.steel, 0.0)
    to_spec = physics.heat_for_temperature(charge.spec_temp_c, w, melt_heat)
    eta_solid = physics.efficiency(0.0, w, charge.borings)
    eta_liquid = physics.efficiency(charge.spec_temp_c, w, charge.borings)
    melt_loss_kw = physics.heat_loss_kw(C.LINING_HOT_FACE_MIN_C, False, charge.lining_age)
    hot_temp = max(m["tap_temp_c"], charge.spec_temp_c)
    hold_loss_kw = physics.heat_loss_kw(hot_temp, False, charge.lining_age)
    lid_extra_kw = physics.heat_loss_kw(hot_temp, True, charge.lining_age) - hold_loss_kw
    return {
        "base": (to_spec + C.LINING_SOAK_KWH) / eta_solid / w,
        "melt_loss": melt_loss_kw * max(m["melt_min"] - m["underpower_lost_min"], 0.0) / 60 / eta_solid / w,
        "overshoot": C.CP_LIQUID_KWH_T_K * max(m["overshoot_c"] - C.OVERSHOOT_TOLERANCE_C, 0.0) / eta_liquid,
        "holding": hold_loss_kw * m["holding_min"] / 60 / eta_liquid / w,
        "lid": lid_extra_kw * m["lid_avoidable_min"] / 60 / eta_liquid / w,
        "underpower": melt_loss_kw * m["underpower_lost_min"] / 60 / eta_solid / w,
    }


def charge_features(charge):
    return [charge.weight_t, charge.pig, charge.returns, charge.steel, charge.borings,
            float(charge.grade == "sg"), charge.lining_age]
