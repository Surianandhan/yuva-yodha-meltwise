#!/usr/bin/env python3
"""MeltWise impact model.

Reproduces every savings, emissions and payback figure used in the Yuva Yodha
application (the description and the deck). Pure Python, no dependencies.

    python3 impact_model.py

Prints markdown tables and writes impact_results.json next to this file.
Tags in brackets map to Research_Notes_and_Sources.md: F = sourced fact, E = engineering estimate.
"""

import json
from pathlib import Path

SCENARIOS = ("conservative", "likely", "stretch")

# --- Typical Indian MSME iron foundry with one 1-tonne medium-frequency furnace ---
FURNACE_T = 1.0              # clusters commonly run 500 kg to 1 t furnaces [F6]
HEATS_PER_DAY = 8            # [E4]
DAYS_PER_YEAR = 300          # [E4]
BASELINE_SEC_KWH_T = 650.0   # cluster values span 580 to 720 kWh/t [F5]
BASELINE_CYCLE_MIN = 75      # 52 min melting + 8 min under-powered + 15 min holding [E4]
GRID_EF_KG_KWH = 0.710       # CEA CO2 Baseline Database v21.0, FY2024-25 [F12]
TARIFF_INR_KWH = {"conservative": 7.55, "likely": 8.0, "stretch": 8.0}  # FY26 range 7.55-9.04 [F11]

# --- Physics that converts a change in shop-floor practice into kWh per tonne ---
FURNACE_EFFICIENCY = 0.77                               # ~97% converter x ~80% coil for iron [F17]
KWH_PER_T_PER_DEG_C = 0.228 / FURNACE_EFFICIENCY        # liquid iron cp ~0.82 kJ/kg.K [E1]
TIME_LOSS_KWH_PER_MIN = 1.0                             # lid-closed losses, 1 t furnace, per tonne [E3]
OPEN_LID_KWH_PER_MIN = 1.0                              # extra radiation with the lid open [E2]
SAND_KWH_PER_KG = 1.1                                   # 1 kg sand wastes the energy of ~2 kg iron [F9]

# lever: (baseline practice, kWh/t per unit improved, reduction achieved per scenario)
LEVERS = {
    "Temperature overshoot above spec (deg C)": (40, KWH_PER_T_PER_DEG_C, {"conservative": 15, "likely": 25, "stretch": 30}),
    "Holding molten metal (min per heat)": (15, TIME_LOSS_KWH_PER_MIN, {"conservative": 4, "likely": 8, "stretch": 11}),
    "Lid left open, avoidable (min per heat)": (6, OPEN_LID_KWH_PER_MIN, {"conservative": 2, "likely": 4, "stretch": 5}),
    "Under-powered melting, extra (min per heat)": (8, TIME_LOSS_KWH_PER_MIN, {"conservative": 3, "likely": 5, "stretch": 7}),
    "Sand and rust in charge (kg per t)": (15, SAND_KWH_PER_KG, {"conservative": 3, "likely": 8, "stretch": 10}),
}
CYCLE_LEVERS = ("Holding molten metal (min per heat)", "Under-powered melting, extra (min per heat)")

# Independent cross-checks from the BEE foundry-cluster DPR [F3, F4]
BEE_INTEGRATOR_KWH_T = 20.0          # saving from a basic kWh indicator-cum-integrator alone
BEE_HEAT_TO_HEAT_SPREAD = (50, 80)   # kWh/t variation between melts in the same furnace

# Time-of-day tariff: (share of melting kWh moved into solar hours, solar-hour discount) [F10]
TOD_SHIFT = {"conservative": (0.10, 0.10), "likely": (0.20, 0.15), "stretch": (0.30, 0.20)}

# One-time kit per foundry (one furnace), indicative 2026 prices
KIT_ITEMS = {
    "Modbus energy meter (EM6400NG, class 0.5S)": 17_289,        # [F13]
    "CTs, wiring and enclosure": 15_000,                          # [E5]
    "Edge gateway (industrial single-board computer)": 20_000,    # [E5]
    "Shop-floor display or tablet": 15_000,                       # [E5]
    "Installation, commissioning and training": 20_000,           # [E5]
}
KIT_TOTAL = sum(KIT_ITEMS.values())
KIT_COST = {"conservative": 150_000, "likely": KIT_TOTAL, "stretch": KIT_TOTAL}
SUBSCRIPTION_INR_YR = 4_000 * 12     # per furnace [E6]

ADOPTING_FOUNDRIES = 1_000           # about 20% of ~5,000 foundry units [F1]
NATIONAL_CASTINGS_MT = 15.86         # India's castings output 2024-25 [F1]


def lever_rows(scenario):
    return [(name, base, cuts[scenario], cuts[scenario] * kwh_per_unit)
            for name, (base, kwh_per_unit, cuts) in LEVERS.items()]


def run_scenario(scenario):
    tonnes_yr = FURNACE_T * HEATS_PER_DAY * DAYS_PER_YEAR
    tariff = TARIFF_INR_KWH[scenario]
    kwh_t = sum(row[3] for row in lever_rows(scenario))
    kwh_yr = kwh_t * tonnes_yr
    remaining_kwh_yr = (BASELINE_SEC_KWH_T - kwh_t) * tonnes_yr
    share, discount = TOD_SHIFT[scenario]
    inr_energy = kwh_yr * tariff
    inr_tod = remaining_kwh_yr * share * discount * tariff
    inr_net = inr_energy + inr_tod - SUBSCRIPTION_INR_YR
    cycle_min_saved = sum(LEVERS[name][2][scenario] for name in CYCLE_LEVERS)
    return {
        "kwh_saved_per_t": round(kwh_t, 1),
        "sec_reduction_pct": round(100 * kwh_t / BASELINE_SEC_KWH_T, 1),
        "sec_after_kwh_t": round(BASELINE_SEC_KWH_T - kwh_t, 1),
        "co2_intensity_before_kg_t": round(BASELINE_SEC_KWH_T * GRID_EF_KG_KWH, 1),
        "co2_intensity_after_kg_t": round((BASELINE_SEC_KWH_T - kwh_t) * GRID_EF_KG_KWH, 1),
        "kwh_saved_per_yr": round(kwh_yr),
        "tariff_inr_kwh": tariff,
        "inr_energy_saved_per_yr": round(inr_energy),
        "inr_tod_saved_per_yr": round(inr_tod),
        "inr_subscription_per_yr": SUBSCRIPTION_INR_YR,
        "inr_net_saved_per_yr": round(inr_net),
        "kit_cost_inr": KIT_COST[scenario],
        "payback_months": round(KIT_COST[scenario] / (inr_net / 12), 1),
        "tco2_avoided_per_yr": round(kwh_yr / 1000 * GRID_EF_KG_KWH, 1),
        "cycle_min_saved_per_heat": cycle_min_saved,
        "cycle_reduction_pct": round(100 * cycle_min_saved / BASELINE_CYCLE_MIN, 1),
        "national_gwh_per_yr": round(kwh_yr * ADOPTING_FOUNDRIES / 1e6, 1),
        "national_inr_crore_per_yr": round(inr_energy * ADOPTING_FOUNDRIES / 1e7, 1),
        "national_tco2_per_yr": round(kwh_yr * ADOPTING_FOUNDRIES / 1000 * GRID_EF_KG_KWH),
    }


def lakh(inr):
    return f"Rs {inr / 1e5:.2f} lakh"


def main():
    tonnes_yr = FURNACE_T * HEATS_PER_DAY * DAYS_PER_YEAR
    results = {s: run_scenario(s) for s in SCENARIOS}

    print(f"## Plant baseline\n{tonnes_yr:,.0f} t/yr liquid metal at {BASELINE_SEC_KWH_T:.0f} kWh/t "
          f"= {BASELINE_SEC_KWH_T * tonnes_yr / 1000:,.0f} MWh/yr melting electricity\n")

    print("## Savings by lever (kWh per tonne)")
    print("| Lever | Baseline | " + " | ".join(s.title() for s in SCENARIOS) + " |")
    print("|---|---|---|---|---|")
    for i, (name, (base, _, _)) in enumerate(LEVERS.items()):
        cells = []
        for s in SCENARIOS:
            _, _, cut, kwh = lever_rows(s)[i]
            cells.append(f"-{cut} -> {kwh:.1f}")
        print(f"| {name} | {base} | " + " | ".join(cells) + " |")
    print("| **Total** | | " + " | ".join(f"**{results[s]['kwh_saved_per_t']}**" for s in SCENARIOS) + " |")
    print(f"\nCross-checks: BEE integrator alone saves {BEE_INTEGRATOR_KWH_T:.0f} kWh/t; "
          f"BEE observed {BEE_HEAT_TO_HEAT_SPREAD[0]}-{BEE_HEAT_TO_HEAT_SPREAD[1]} kWh/t heat-to-heat spread.\n")

    print("## Results per foundry and at scale")
    labels = [
        ("SEC reduction", lambda r: f"{r['kwh_saved_per_t']} kWh/t ({r['sec_reduction_pct']}%)"),
        ("SEC after", lambda r: f"{r['sec_after_kwh_t']} kWh/t"),
        ("CO2 intensity", lambda r: f"{r['co2_intensity_before_kg_t']} -> {r['co2_intensity_after_kg_t']} kg/t"),
        ("Electricity saved", lambda r: f"{r['kwh_saved_per_yr'] / 1000:,.1f} MWh/yr"),
        ("Energy cost saved", lambda r: lakh(r["inr_energy_saved_per_yr"])),
        ("ToD tariff saving", lambda r: lakh(r["inr_tod_saved_per_yr"])),
        ("Net after subscription", lambda r: lakh(r["inr_net_saved_per_yr"])),
        ("Kit cost", lambda r: lakh(r["kit_cost_inr"])),
        ("Payback", lambda r: f"{r['payback_months']} months"),
        ("CO2 avoided", lambda r: f"{r['tco2_avoided_per_yr']} t/yr"),
        ("Heat cycle shortened", lambda r: f"{r['cycle_min_saved_per_heat']} min ({r['cycle_reduction_pct']}%)"),
        (f"{ADOPTING_FOUNDRIES:,} foundries: electricity", lambda r: f"{r['national_gwh_per_yr']} GWh/yr"),
        (f"{ADOPTING_FOUNDRIES:,} foundries: energy cost", lambda r: f"Rs {r['national_inr_crore_per_yr']} crore/yr"),
        (f"{ADOPTING_FOUNDRIES:,} foundries: CO2", lambda r: f"{r['national_tco2_per_yr']:,} t/yr"),
    ]
    print("| Metric | " + " | ".join(s.title() for s in SCENARIOS) + " |")
    print("|---|---|---|---|")
    for label, fmt in labels:
        print(f"| {label} | " + " | ".join(fmt(results[s]) for s in SCENARIOS) + " |")

    national_mt = tonnes_yr * ADOPTING_FOUNDRIES / 1e6
    print(f"\nScale check: {ADOPTING_FOUNDRIES:,} foundries x {tonnes_yr:,.0f} t = {national_mt:.1f} Mt liquid metal/yr "
          f"(India's castings output: {NATIONAL_CASTINGS_MT} Mt in 2024-25).")
    print(f"Kit items (likely case): " + "; ".join(f"{k} Rs {v:,}" for k, v in KIT_ITEMS.items())
          + f"; total Rs {KIT_TOTAL:,}.")

    out = {
        "plant": {"tonnes_per_yr": tonnes_yr, "baseline_sec_kwh_t": BASELINE_SEC_KWH_T,
                  "grid_ef_kg_kwh": GRID_EF_KG_KWH, "adopting_foundries": ADOPTING_FOUNDRIES},
        "scenarios": results,
    }
    path = Path(__file__).with_name("impact_results.json")
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"\nWrote {path.name}")


if __name__ == "__main__":
    main()
