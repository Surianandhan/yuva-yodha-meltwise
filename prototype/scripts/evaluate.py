"""Measure the MeltWise prototype against the simulator's ground truth.

    python scripts/evaluate.py          (about a minute)

Writes results/metrics.json and results/evaluation.md. Every number in the
Phase 2 form and deck comes from here.
"""

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from meltwise import advisor as A  # noqa: E402
from meltwise import config as C  # noqa: E402
from meltwise import features as F  # noqa: E402
from meltwise import pilot, scheduler  # noqa: E402
from meltwise import simulator as S  # noqa: E402
from meltwise.model import EnergyModel  # noqa: E402

TRAIN_MELTS = 240        # the 30-day observe-only period: 8 heats a day
TEST_MELTS = 300
FLAG_KWH_T = 3.0         # a cause is "present" in a melt above 3 kWh/t
TONNES_PER_YEAR = 2400


def melts(rng, plant, n):
    out = []
    for _ in range(n):
        charge = S.random_charge(rng)
        out.append(S.simulate(charge, S.baseline_practice(rng, charge), S.random_hidden(rng, plant)))
    return out


def model_accuracy(plant_seed, rng):
    """Train on one plant's first 30 days, score on 300 later melts against counterfactual ground truth."""
    plant = S.random_plant(np.random.default_rng(plant_seed))
    model = EnergyModel().fit([F.observe(r) for r in melts(rng, plant, TRAIN_MELTS)])
    est = {c: [] for c in S.CAUSES}
    truth = {c: [] for c in S.CAUSES}
    best_err, pred_err, secs = [], [], []
    for record in melts(rng, plant, TEST_MELTS):
        gt, ex = S.ground_truth(record), model.explain(F.observe(record))
        best_err.append(ex["expected_best_kwh_t"] - gt["best_sec"])
        pred_err.append(ex["predicted_kwh_t"] - record.sec_kwh_t)
        secs.append(record.sec_kwh_t)
        for c in S.CAUSES:
            est[c].append(ex["waste_kwh_t"][c])
            truth[c].append(gt[c])
    causes = {}
    for c in S.CAUSES:
        e, t = np.array(est[c]), np.array(truth[c])
        flagged, present = e > FLAG_KWH_T, t > FLAG_KWH_T
        causes[c] = {
            "truth_mean_kwh_t": float(t.mean()), "estimate_mean_kwh_t": float(e.mean()),
            "mae_kwh_t": float(np.mean(np.abs(e - t))), "correlation": float(np.corrcoef(e, t)[0, 1]),
            "precision": float((flagged & present).sum() / max(flagged.sum(), 1)),
            "recall": float((flagged & present).sum() / max(present.sum(), 1)),
        }
    total_e = np.sum([est[c] for c in S.CAUSES], axis=0)
    total_t = np.sum([truth[c] for c in S.CAUSES], axis=0)
    return {
        "plant": {"eta_factor": plant.eta_factor, "loss_factor": plant.loss_factor, "lid_factor": plant.lid_factor},
        "learned_coefficients": model.coefficients(),
        "predicted_sec_mae_kwh_t": float(np.mean(np.abs(pred_err))),
        "predicted_sec_mape_pct": float(100 * np.mean(np.abs(pred_err) / np.array(secs))),
        "best_practice_mae_kwh_t": float(np.mean(np.abs(best_err))),
        "best_practice_bias_kwh_t": float(np.mean(best_err)),
        "total_avoidable_mae_kwh_t": float(np.mean(np.abs(total_e - total_t))),
        "total_avoidable_truth_mean_kwh_t": float(total_t.mean()),
        "causes": causes,
    }


def tapping_accuracy(rng, n=300):
    plant = S.random_plant(np.random.default_rng(7))
    model = EnergyModel().fit([F.observe(r) for r in melts(rng, plant, TRAIN_MELTS)])
    base, advised = [], []
    for _ in range(n):
        charge = S.random_charge(rng)
        practice, hidden = S.baseline_practice(rng, charge), S.random_hidden(rng, plant)
        base.append(S.simulate(charge, practice, hidden).tap_temp_c - charge.spec_temp_c)
        advised.append(S.simulate(charge, practice, hidden, stop_superheat=A.AdvisedOperator(charge, model)).tap_temp_c
                       - charge.spec_temp_c)
    advised = np.array(advised)
    return {"baseline_overshoot_mean_c": float(np.mean(base)), "advised_overshoot_mean_c": float(advised.mean()),
            "advised_overshoot_sd_c": float(advised.std()), "advised_below_spec_pct": float(100 * np.mean(advised < 0)),
            "advised_below_spec_by_5c_pct": float(100 * np.mean(advised < -5)),
            "advised_within_0_15c_pct": float(100 * np.mean((advised >= 0) & (advised <= 15)))}


def simulator_calibration(rng, n=200):
    records = melts(rng, S.Plant(), n)
    truths = [S.ground_truth(r) for r in records]
    return {"baseline_sec_kwh_t": float(np.mean([r.sec_kwh_t for r in records])),
            "best_practice_sec_kwh_t": float(np.mean([t["best_sec"] for t in truths])),
            "cycle_min": float(np.mean([r.duration_min for r in records])),
            "avoidable_kwh_t": {c: float(np.mean([t[c] for t in truths])) for c in S.CAUSES}}


def pilot_results():
    out = {}
    for compliance in (0.4, 0.6, 0.8, 0.9, 1.0):
        s = pilot.summarise(pilot.run(compliance=compliance)[0])
        kwh_year = s["saved_kwh_t"] * TONNES_PER_YEAR
        s["annual"] = {"kwh": kwh_year, "inr_lakh": kwh_year * C.TARIFF_INR_KWH / 1e5,
                       "t_co2": kwh_year * C.GRID_EF_KG_KWH / 1000}
        out[str(compliance)] = s
    return out


def write_markdown(m, path):
    acc = m["model_accuracy_plant_a"]
    lines = ["# MeltWise prototype: evaluation results", "",
             "All results are from simulation. The simulator is calibrated to published figures "
             "(see Supporting_Material/Research_Notes_and_Sources.md); no plant data has been used yet.", "",
             "## 1. Simulator calibration (nominal plant, 200 melts)", "",
             f"- Typical melt today: **{m['calibration']['baseline_sec_kwh_t']:.0f} kWh/t** (our Phase 1 baseline: 650)",
             f"- Best practice for the same charges: **{m['calibration']['best_practice_sec_kwh_t']:.0f} kWh/t** "
             "(US DOE best practice: 593 kWh/t)",
             f"- Heat cycle: {m['calibration']['cycle_min']:.0f} min; avoidable loss "
             f"{sum(m['calibration']['avoidable_kwh_t'].values()):.0f} kWh/t (BEE observed 50-80 kWh/t between heats)", "",
             "## 2. Energy model on held-out melts (Plant A: trained on 240 melts, tested on 300)", "",
             f"- Predicted kWh/t of a melt from its signals: MAE **{acc['predicted_sec_mae_kwh_t']:.1f} kWh/t** "
             f"(**{acc['predicted_sec_mape_pct']:.1f}%**)",
             f"- Best-practice kWh/t for each charge: MAE {acc['best_practice_mae_kwh_t']:.1f} kWh/t "
             f"(bias {acc['best_practice_bias_kwh_t']:+.1f})",
             f"- Total avoidable kWh/t per melt: MAE {acc['total_avoidable_mae_kwh_t']:.1f} "
             f"(true mean {acc['total_avoidable_truth_mean_kwh_t']:.1f})", "",
             "| Cause | True mean kWh/t | MeltWise mean | MAE | Correlation | Precision | Recall |",
             "|---|---|---|---|---|---|---|"]
    for c, v in acc["causes"].items():
        lines.append(f"| {c} | {v['truth_mean_kwh_t']:.1f} | {v['estimate_mean_kwh_t']:.1f} | {v['mae_kwh_t']:.1f} | "
                     f"{v['correlation']:.2f} | {100 * v['precision']:.0f}% | {100 * v['recall']:.0f}% |")
    lines += ["", f"Precision and recall: a cause counts as present above {FLAG_KWH_T:g} kWh/t. "
              "Sand and rust are not measured directly; MeltWise reports them as the unexplained excess "
              "over the best heats of similar charges, so their absolute size is under-estimated.", "",
              "Across five more simulated plants (each with its own hidden loss and efficiency constants):", "",
              "| Plant | Predicted kWh/t MAE | Practice-cause MAE (mean of 4) |", "|---|---|---|"]
    for i, r in enumerate(m["model_accuracy_other_plants"], 1):
        practice = np.mean([r["causes"][c]["mae_kwh_t"] for c in ("overshoot", "holding", "lid", "underpower")])
        lines.append(f"| {i} | {r['predicted_sec_mae_kwh_t']:.1f} | {practice:.1f} |")
    t = m["tapping"]
    lines += ["", "## 3. Tapping on the soft sensor's prompt (300 melts)", "",
              f"- Tap temperature above spec: today {t['baseline_overshoot_mean_c']:.0f} C; following MeltWise "
              f"{t['advised_overshoot_mean_c']:.1f} C (sd {t['advised_overshoot_sd_c']:.1f})",
              f"- Within spec to spec+15 C: {t['advised_within_0_15c_pct']:.0f}%; below spec: "
              f"{t['advised_below_spec_pct']:.0f}% (more than 5 C below: {t['advised_below_spec_by_5c_pct']:.0f}%). "
              "The operator's final dip before tapping still confirms temperature.", "",
              "## 4. Simulated 60-day pilot (30 days observing, 30 days with MeltWise)", "",
              "| Operators follow prompts | kWh/t before | after | Saved kWh/t | 95% CI | Saved % | Rs lakh/yr | t CO2/yr |",
              "|---|---|---|---|---|---|---|---|"]
    for c, p in m["pilot"].items():
        lines.append(f"| {float(c):.0%} | {p['sec_before']:.1f} | {p['sec_after']:.1f} | {p['saved_kwh_t']:.1f} | "
                     f"{p['saved_ci95'][0]:.1f}-{p['saved_ci95'][1]:.1f} | {p['saved_pct']:.1f}% | "
                     f"{p['annual']['inr_lakh']:.2f} | {p['annual']['t_co2']:.1f} |")
    s = m["scheduler"]
    lines += ["", "Annual figures: 2,400 t/yr, Rs 8/kWh, 0.710 kg CO2/kWh. Gross of the subscription.", "",
              "## 5. Scheduler (300 simulated days, 8 heats a day)", "",
              f"- Holding per heat: {s['asap']['holding_min']:.1f} min starting right after the last tap; "
              f"{s['meltwise']['holding_min']:.1f} min with MeltWise ({100 * s['holding_reduction']:.0f}% less)",
              f"- Moulds waiting for metal: {s['asap']['mould_wait_min']:.1f} -> {s['meltwise']['mould_wait_min']:.1f} min per heat",
              f"- Electricity cost per heat: Rs {s['asap']['cost_inr']:.0f} -> Rs {s['meltwise']['cost_inr']:.0f}. "
              "Within a fixed moulding plan the time-of-day tariff adds little; most of the saving is less holding.", ""]
    path.write_text("\n".join(lines) + "\n")


def main():
    rng = np.random.default_rng(42)
    metrics = {
        "calibration": simulator_calibration(rng),
        "model_accuracy_plant_a": model_accuracy(7, rng),
        "model_accuracy_other_plants": [model_accuracy(seed, rng) for seed in (101, 102, 103, 104, 105)],
        "tapping": tapping_accuracy(rng),
        "pilot": pilot_results(),
        "scheduler": scheduler.evaluate(),
    }
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2, default=float) + "\n")
    write_markdown(metrics, out / "evaluation.md")
    print((out / "evaluation.md").read_text())


if __name__ == "__main__":
    main()
