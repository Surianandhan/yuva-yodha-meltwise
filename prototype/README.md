# MeltWise prototype

A working energy copilot for induction-furnace foundries, from the furnace meter to the operator's screen:

```
furnace meter (Modbus TCP) ─┐
lid switch ─────────────────┼─► edge gateway ─► MeltWise API ─► web app
operator app (charge, dips) ┘   (SQLite outbox,   (energy model,     (operator, manager,
                                 offline-first)    advisor, scheduler, planner, buyer)
                                                   carbon record)
```

There is no plant data yet, so a physics-based furnace simulator stands in for the plant and the meter. It is calibrated to the published figures in `../Supporting_Material/Research_Notes_and_Sources.md`, and re-running any melt with one practice gap removed gives the ground truth that every result below is scored against.

## Run it

Needs Python 3.11+ and Google Chrome (for screenshots only).

```bash
cd prototype
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/build_demo_data.py         # 60-day pilot at Plant A (simulated)
.venv/bin/uvicorn meltwise.api:app --port 8000       # then open http://127.0.0.1:8000
```

In a second terminal, stream live melts through the Modbus meter and the gateway (the operator view updates as they play):

```bash
.venv/bin/python scripts/live_demo.py --melts 2 --speed 40 --outage 15
```

`--outage 15` cuts the gateway's network for 15 seconds mid-melt: readings pile up in its outbox and arrive late but complete. `--lang hi` or `--lang ta` sets the prompt language (the operator screen also has a switch). Deep links: `/#/manager`, `/#/planner`, `/#/buyer`, `/#/melt-3`, `/?lang=hi#/operator`.

## Measure it

```bash
.venv/bin/python scripts/evaluate.py     # about 20 s; writes results/metrics.json and results/evaluation.md
.venv/bin/python -m pytest               # 14 tests, about 8 s
```

Headline results (all from simulation, see `results/evaluation.md`):

| What | Result |
|---|---|
| Predicting a melt's kWh/t from its signals (300 unseen melts) | 1.4% error |
| Finding each practice cause (overshoot, holding, lid, under-power) | correlation 0.91–0.99 with ground truth; precision 89–100%, recall 95–98% |
| Tap temperature above spec when operators follow "tap now" | 42 °C → 4.8 °C |
| Holding per heat with the scheduler (300 days) | 15.3 → 7.8 min (−49%) |
| Readings lost when the network is cut mid-melt | 0 |
| 60-day pilot, operators following 60% of prompts | 657.6 → 635.0 kWh/t (−22.6, 95% CI 17.1–27.7) |

## What's inside

| Path | What it does |
|---|---|
| `meltwise/config.py` | Plant, physics, tariff and carbon constants, tagged to the research notes |
| `meltwise/physics.py` | Energy balance of the bath: heat content, coil efficiency, heat losses |
| `meltwise/simulator.py` | Melt simulator in 10 s steps; hidden per-plant constants; counterfactual ground truth |
| `meltwise/features.py` | What a plant can measure: holding, avoidable lid time, under-power, tap temperature |
| `meltwise/model.py` | Physics-informed energy model: physics terms recalibrated by ridge-to-prior regression, plus gradient boosting on the charge |
| `meltwise/advisor.py` | Bath-temperature soft sensor and live prompts in English, Hindi and Tamil |
| `meltwise/scheduler.py` | Melt start times that balance holding, waiting moulds and the time-of-day tariff |
| `meltwise/pilot.py` | 30 days observing, 30 days with MeltWise, at a chosen prompt follow-through |
| `meltwise/edge/` | Simulated Modbus TCP meter and the offline-first gateway |
| `meltwise/store.py`, `meltwise/api.py` | SQLite store, per-batch carbon record, FastAPI endpoints |
| `web/` | The web app (plain JavaScript and Chart.js) |
| `scripts/` | Demo data, live demo, evaluation |

## Limits, stated plainly

- Every result is simulated. The simulator matches published averages, but a real furnace will surprise us; the first real pilot uses the same observe-then-advise design so the numbers are comparable.
- Sand and rust are not measured. MeltWise infers them as excess energy over the best heats of similar charges, so it under-counts them (correlation with the truth is only 0.24).
- Following the tap prompt put 15% of taps below spec (2% by more than 5 °C). The operator's final dip before tapping remains the safety check.
- The Hindi and Tamil prompt text are first drafts and need review by operators.
- The meter register map is the prototype's own; a real EM6400NG or PowerLogic meter needs its documented addresses.
