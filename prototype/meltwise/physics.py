"""Energy balance of an induction furnace bath.

The simulator uses these functions with hidden per-melt factors (the "truth");
MeltWise's soft sensor uses the same physics with nominal factors, then
recalibrates on every temperature dip the operator takes.
"""

from . import config as C


def required_melt_heat(weight_t, steel_frac, sand_kg):
    """Heat (kWh) to take the whole charge, including slag from sand, to the liquidus."""
    return weight_t * (C.H_LIQUIDUS_KWH_T + steel_frac * C.STEEL_EXTRA_KWH_T) + sand_kg * C.SAND_HEAT_KWH_KG


def temperature(heat_kwh, weight_t, melt_heat_kwh):
    """Bath temperature (C) for a heat content; below the liquidus it is a surface-temperature proxy."""
    if heat_kwh <= melt_heat_kwh:
        return 25.0 + (heat_kwh / melt_heat_kwh) * (C.LIQUIDUS_C - 25.0)
    return C.LIQUIDUS_C + (heat_kwh - melt_heat_kwh) / (weight_t * C.CP_LIQUID_KWH_T_K)


def heat_for_temperature(temp_c, weight_t, melt_heat_kwh):
    """Inverse of temperature() for a liquid bath."""
    return melt_heat_kwh + max(temp_c - C.LIQUIDUS_C, 0.0) * weight_t * C.CP_LIQUID_KWH_T_K


def efficiency(temp_c, weight_t, borings_frac, eta_factor=1.0):
    """Share of electrical power that ends up as heat in the bath."""
    fill = min(weight_t / C.FURNACE_CAPACITY_T, 1.0)
    coupling = 0.94 + 0.06 * fill
    if temp_c < C.LIQUIDUS_C:
        return C.ETA_SOLID * (1.0 - 0.06 * borings_frac) * coupling * eta_factor
    return C.ETA_LIQUID * coupling * eta_factor


def heat_loss_kw(temp_c, lid_open, lining_age, loss_factor=1.0, lid_factor=1.0):
    """Heat leaving the bath (kW): conduction and lid-gap radiation, plus open-lid radiation."""
    lining_face_c = max(temp_c, C.LINING_HOT_FACE_MIN_C)  # the lining stays hot between heats
    closed = C.CLOSED_LOSS_KW_AT_1500 * (lining_face_c - 25.0) / 1475.0 * (1.0 + 0.25 * min(lining_age, 400) / 400) * loss_factor
    if not lid_open:
        return closed
    t_k, ref_k, amb_k = temp_c + 273.0, 1773.0, 298.0
    radiation = C.OPEN_LID_EXTRA_KW_AT_1500 * (t_k**4 - amb_k**4) / (ref_k**4 - amb_k**4)
    return closed + max(radiation, 0.0) * lid_factor
