# MeltWise prototype: evaluation results

All results are from simulation. The simulator is calibrated to published figures (see Supporting_Material/Research_Notes_and_Sources.md); no plant data has been used yet.

## 1. Simulator calibration (nominal plant, 200 melts)

- Typical melt today: **648 kWh/t** (our Phase 1 baseline: 650)
- Best practice for the same charges: **588 kWh/t** (US DOE best practice: 593 kWh/t)
- Heat cycle: 77 min; avoidable loss 65 kWh/t (BEE observed 50-80 kWh/t between heats)

## 2. Energy model on held-out melts (Plant A: trained on 240 melts, tested on 300)

- Predicted kWh/t of a melt from its signals: MAE **9.3 kWh/t** (**1.4%**)
- Best-practice kWh/t for each charge: MAE 10.1 kWh/t (bias +6.8)
- Total avoidable kWh/t per melt: MAE 12.2 (true mean 66.3)

| Cause | True mean kWh/t | MeltWise mean | MAE | Correlation | Precision | Recall |
|---|---|---|---|---|---|---|
| overshoot | 15.1 | 11.6 | 3.5 | 0.95 | 100% | 98% |
| holding | 23.2 | 20.4 | 2.9 | 0.99 | 99% | 95% |
| lid | 5.5 | 6.5 | 1.1 | 0.99 | 89% | 97% |
| underpower | 5.3 | 5.5 | 0.7 | 0.91 | 92% | 98% |
| sand | 17.2 | 11.8 | 9.6 | 0.24 | 100% | 75% |

Precision and recall: a cause counts as present above 3 kWh/t. Sand and rust are not measured directly; MeltWise reports them as the unexplained excess over the best heats of similar charges, so their absolute size is under-estimated.

Across five more simulated plants (each with its own hidden loss and efficiency constants):

| Plant | Predicted kWh/t MAE | Practice-cause MAE (mean of 4) |
|---|---|---|
| 1 | 8.8 | 1.9 |
| 2 | 8.9 | 2.4 |
| 3 | 8.2 | 1.9 |
| 4 | 9.1 | 2.3 |
| 5 | 9.5 | 3.4 |

## 3. Tapping on the soft sensor's prompt (300 melts)

- Tap temperature above spec: today 42 C; following MeltWise 4.8 C (sd 4.6)
- Within spec to spec+15 C: 83%; below spec: 15% (more than 5 C below: 2%). The operator's final dip before tapping still confirms temperature.

## 4. Simulated 60-day pilot (30 days observing, 30 days with MeltWise)

| Operators follow prompts | kWh/t before | after | Saved kWh/t | 95% CI | Saved % | Rs lakh/yr | t CO2/yr |
|---|---|---|---|---|---|---|---|
| 40% | 657.6 | 642.6 | 14.9 | 8.8-20.4 | 2.3% | 2.87 | 25.5 |
| 60% | 657.6 | 635.0 | 22.6 | 17.1-27.7 | 3.4% | 4.33 | 38.5 |
| 80% | 657.6 | 628.6 | 29.0 | 23.7-33.8 | 4.4% | 5.56 | 49.3 |
| 90% | 657.6 | 625.0 | 32.6 | 27.5-37.3 | 5.0% | 6.26 | 55.5 |
| 100% | 657.6 | 621.8 | 35.8 | 30.9-40.4 | 5.4% | 6.87 | 61.0 |

Annual figures: 2,400 t/yr, Rs 8/kWh, 0.710 kg CO2/kWh. Gross of the subscription.

## 5. Scheduler (300 simulated days, 8 heats a day)

- Holding per heat: 15.3 min starting right after the last tap; 7.8 min with MeltWise (49% less)
- Moulds waiting for metal: 2.3 -> 2.7 min per heat
- Electricity cost per heat: Rs 3987 -> Rs 3914. Within a fixed moulding plan the time-of-day tariff adds little; most of the saving is less holding.

