# Phase 2: Prototype Details (answers to paste)

Every number below comes from `prototype/results/metrics.json` (run `prototype/scripts/evaluate.py`) or from `Supporting_Material/Research_Notes_and_Sources.md`. Deadline: **22 November 2026**.

## Before you submit

1. Record the demo video (3–5 min) with `Demo_Video_Script.md`, upload it (YouTube unlisted or Google Drive, "anyone with the link"), and paste the link into field 8.
2. Give the judges access to the code: the repo is **private**. Either make it public, or add the evaluators as collaborators if the organizers give you their GitHub accounts. Merge the `prototype` branch into `main` first.
3. Uploads: `MeltWise_Architecture.png` (field 4), `MeltWise_Phase2_Presentation.pdf` (field 11, 13 slides), `MeltWise_Screenshots.zip` (field 12).
4. Read every answer once and change anything that doesn't sound like you.

---

## 1. Project Name
MeltWise: AI Energy Copilot for India's Foundries

## 2. Prototype stage
Working prototype, end to end, validated in simulation (no plant pilot yet). Pick the dropdown option closest to this.

## 3. What the prototype does, with the key features built
MeltWise watches every melt in an induction furnace and tells the operator, while the metal is still in the furnace, what is wasting electricity. The prototype runs end to end, from a Modbus energy meter to the operator's screen:

- **Edge gateway:** polls the furnace meter over Modbus TCP and a lid switch, and stores every reading in a local SQLite outbox before forwarding it, so a network cut delays data but never loses it.
- **Physics-informed energy model:** recalibrates physics (heat to spec, losses, overshoot) on the plant's own first 30 days, plus gradient boosting on the scrap mix. It splits every melt's kWh/t into causes: overshoot, holding, open lid, under-powered melting, and charge quality.
- **Live operator advisor:** a bath-temperature soft sensor that resets on every dip, and six prompt types (under-power, dip now, tap now, lid open, holding, over budget) in English, Hindi and Tamil.
- **Melt scheduler:** start times that cut holding, priced on the time-of-day tariff.
- **Manager dashboard and buyer carbon record:** kWh/t trends, avoidable kWh by cause, savings in ₹ and CO₂, and a per-batch Scope 2 CO₂ record with CSV export.

## 4. Solution architecture or flow diagram
Upload `MeltWise_Architecture.png`.

## 5. Technologies used
- **Languages:** Python 3.13, JavaScript, HTML/CSS
- **AI/ML:** scikit-learn (gradient boosting with quantile loss), NumPy (physics-prior ridge regression, energy-balance soft sensor)
- **Backend:** FastAPI, Uvicorn, Pydantic, SQLite
- **Industrial:** pymodbus (Modbus TCP meter and gateway)
- **Frontend:** plain JavaScript, Chart.js
- **Testing:** pytest (14 automated tests, including a network outage)
- **Hardware for the pilot:** Modbus energy meter such as Schneider EM6400NG, CTs, a lid limit switch, an industrial edge gateway, a shop-floor display. The prototype uses a simulated meter.
- **Cloud:** none needed for the prototype; it runs on a laptop. The pilot plan is one small cloud server.

## 6. Third-party integrations or APIs used, if any
- **Modbus TCP:** an open industrial protocol, so any Modbus meter works by setting its register addresses. That includes Schneider EM6400NG and PowerLogic meters; we have not yet tested on real hardware.
- **Chart.js and Google Fonts:** used by the web app.
- No paid APIs.
- **Grid emission factor:** CEA CO₂ Baseline Database v21.0 (0.710 kg CO₂/kWh).

## 7. Data used: source, and whether it's real, sample or simulated
**Simulated**, calibrated to published real-world figures. We have no plant data yet. A physics-based furnace simulator generates melts at 10-second resolution: power, lid switch, operator log, and temperature dips. It matches published figures:
- Typical melt: 648 kWh/t; our Phase 1 baseline from the BEE foundry-cluster study is 650.
- Best practice: 588 kWh/t; US DOE best practice is 593.
- Avoidable loss: 65 kWh/t; BEE observed a 50–80 kWh/t heat-to-heat swing.

Each simulated plant has hidden loss and efficiency constants that MeltWise must learn. Re-running a melt with one practice gap removed gives the true waste from that cause, which we use only for scoring. Tariff and carbon inputs are real published values: ToD rules 2023, FY26 industrial tariffs, CEA grid factor.

## 8. Demo video link, 3–5 minutes
[paste your video link]

## 9. Live demo, app or website link, if any
None. It runs locally in two commands (see `prototype/README.md`).

## 10. Source code repository link
https://github.com/Surianandhan/yuva-yodha-meltwise (the code is in `prototype/`; make sure the judges can open it, see "Before you submit").

## 11. Presentation deck upload
Upload `MeltWise_Phase2_Presentation.pdf` (13 slides).

## 12. Screenshots or photos of the prototype
Upload `MeltWise_Screenshots.zip`. It contains:
- the operator screen in English and Hindi
- the manager dashboard
- a melt breakdown
- the planner
- the buyer carbon record
- the architecture diagram

## 13. The problem today, with numbers or evidence where possible
India has about 5,000 foundry units, 90% of them MSMEs, producing 15.86 Mt of castings in 2024–25. Induction-furnace energy per tonne in studied Indian foundries ran 13–21% above norms.

The waste happens inside individual melts. A BEE study of the Batala–Jalandhar–Ludhiana cluster found:
- energy per tonne in the same furnace varied by 50–80 kWh/t between heats, because of practice;
- the causes were temperature overshoot, holding metal while moulds were not ready, and waiting;
- 35–40% of heat time ran at only 70–80% of rated power.

Open lids add radiation loss, and sand and rust in the charge waste the energy of about twice their weight in iron. Yet most foundries see energy only as a monthly bill, weeks after the melts that wasted it. Energy is 15–30% of production cost in energy-intensive SMEs, and buyers increasingly ask suppliers for carbon data.

## 14. Results achieved or expected, and how they were measured
All results were measured in simulation against ground truth MeltWise never sees. For 300 unseen melts at a simulated plant (trained on its first 240 melts):
- **Energy prediction:** MeltWise predicted each melt's kWh/t within 1.4%.
- **Overshoot, holding, open lid and under-power:** its estimates correlated 0.91–0.99 with the true waste, with 89–100% precision and 95–98% recall.
- **Five more simulated plants:** practice-cause error was 1.9–3.4 kWh/t.
- **Tapping:** following the "tap now" prompt cut tap temperature above spec from 42 °C to 4.8 °C.
- **Scheduling:** over 300 simulated days, the scheduler cut holding from 15.3 to 7.8 minutes per heat.
- **Network outage:** the gateway lost 0 readings when the network was cut mid-melt.

**60-day pilot (simulated):** 30 days observing, then 30 days with MeltWise, with each prompt followed only some of the time:

| Operators follow prompts | Saving | 95% confidence interval |
|---|---|---|
| 40% | 14.9 kWh/t | 8.8–20.4 |
| 60% | 22.6 kWh/t | 17.1–27.7 |
| 80% | 29.0 kWh/t | 23.7–33.8 |

**Limits:**
- Sand and rust are only inferred (correlation 0.24), so they are under-counted.
- 15% of advised taps landed below spec (2% by more than 5 °C), so the operator's final dip stays as the check.

## 15. Key success metric and the improvement shown
**Electricity per tonne of liquid metal (kWh/t).** In the simulated 60-day pilot, with operators following 60% of prompts, it fell from 657.6 to 635.0 kWh/t: −22.6 kWh/t or −3.4% (95% CI 17.1–27.7). For one 1-tonne furnace (2,400 t a year at ₹8/kWh) that is ₹4.33 lakh and 38.5 t of CO₂ a year. At 80% follow-through it is −29.0 kWh/t (−4.4%).

## 16. Cost to build the prototype, and estimated cost to scale
**Prototype:** ₹0 in cash. We used an open-source stack on our own laptops, with a simulated meter and plant.

**Pilot and scale, per furnace:** a one-time kit costing ₹87,289:

| Item | Cost |
|---|---|
| EM6400NG Modbus meter | ₹17,289 |
| CTs, wiring, lid switch and enclosure | ₹15,000 |
| Industrial edge gateway | ₹20,000 |
| Shop-floor display | ₹15,000 |
| Installation and training | ₹20,000 |

Hosting is about ₹1,000 a month for the first plants. At scale we estimate under ₹100 per furnace per month, because one small server can handle the data from about a hundred furnaces.

At the pilot's 60% result, the kit pays back in **2.7 months** after the subscription (4.4 months at 40%).

## 17. Business model or revenue/cost model, if any
- **Subscription:** ₹4,000 per furnace per month, on top of the kit. This is under 15% of the measured gross saving at 60% follow-through.
- **Channel:** foundry cluster associations, which already run energy programmes.
- **Kit financing:** SIDBI's 4E energy-efficiency loans, or bundling with Schneider Electric meters through its channel.
- **Later:** a shared-savings option where the foundry pays from verified savings, and paid carbon reports for buyers.

## 18. Plan for next steps: who will use it and how it will be rolled out
**Users:**
- **Furnace operators:** prompts on a shop-floor screen in their language.
- **Shift supervisors and plant managers:** the dashboard and melt schedule.
- **Owners:** monthly savings.
- **Buyers:** a carbon record per batch.

**Rollout:**
1. **Now to January 2027:** one real furnace, found through a cluster association. Install the kit, observe for 30 days, then run 30 days with prompts. This is the same design as our simulated pilot, so results are comparable. Check the Hindi and Tamil prompts with operators.
2. **February to June 2027:** 10 furnaces in one cluster. Retrain the model for each furnace, add supplier charge-quality reports and WhatsApp summaries for owners, and measure how often prompts are followed.
3. **Late 2027 onward:** scale through cluster associations and SIDBI and BEE schemes, connect to Schneider meters and EcoStruxure, then extend to steel and aluminium melt shops.

## 19. Broader impact (social, environmental, or economic), if any
If 1,000 foundries reach the pilot's 60% result, that is about 54 GWh of electricity, ₹43 crore and 38,500 t of CO₂ a year.
- **Economic:** a saving that pays back in months protects thin MSME margins and the jobs that depend on them.
- **Environmental:** metered, per-batch CO₂ records let small suppliers answer buyers' carbon-disclosure requests with real data.
- **Social:** prompts in the operator's own language put the know-how of the best shifts in every operator's hands.
