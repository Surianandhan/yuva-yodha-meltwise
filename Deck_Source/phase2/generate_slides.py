"""Generate the Phase 2 deck slides from prototype/results/metrics.json.

    python3 Deck_Source/phase2/generate_slides.py && Deck_Source/build.sh Phase2_Submission Deck_Source/phase2 MeltWise_Phase2_Presentation

Screenshots in assets/ are crops of Phase2_Submission/screenshots.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DECK = ROOT / "Deck_Source" / "phase2"
M = json.loads((ROOT / "prototype" / "results" / "metrics.json").read_text())
A = M["model_accuracy_plant_a"]
P = M["pilot"]
SCH = M["scheduler"]
TAP = M["tapping"]
CAL = M["calibration"]

INK, TEXT, MUTED, PAPER, CARD, LINE, ACCENT, HOT, GOOD, SOFT = (
    "#16181D", "#2B2F36", "#5A6170", "#F6F3EE", "#FBFAF7", "#DED8CE", "#C2410C", "#FF7A1A", "#1F7A4D", "#ECE7DF")
HEAD = "font-family:'Space Grotesk', Arial, sans-serif"
TOTAL = 13


def f(x, d=1):
    return f"{x:,.{d}f}"


def section(sid, n, body, notes, dark=False, gap=36):
    bg, fg = (INK, PAPER) if dark else (PAPER, TEXT)
    foot_color = "#A7A29A" if dark else MUTED
    footer = (f'<div style="position:absolute; left:128px; right:128px; bottom:56px; display:flex; '
              f'justify-content:space-between; align-items:center; gap:32px">'
              f'<p style="font-size:22px; color:{foot_color}">MeltWise · Yuva Yodha 2026 · Phase 2 prototype</p>'
              f'<p style="font-size:22px; color:{foot_color}">{n}</p></div>') if n > 1 else ""
    return (f'<section id="{sid}" data-transition="fade" style="background:{bg}; color:{fg}; '
            f"font-family:'IBM Plex Sans', Arial, sans-serif; padding:112px 128px 144px; display:flex; "
            f'flex-direction:column; gap:{gap}px">\n{body}\n{footer}\n<aside>{notes}</aside>\n</section>\n')


def title(kicker, heading):
    return (f'<div style="display:flex; flex-direction:column; gap:12px">'
            f'<p style="font-size:24px; font-weight:600; letter-spacing:2px; text-transform:uppercase; color:{ACCENT}">{kicker}</p>'
            f'<h2 style="{HEAD}; font-size:60px; font-weight:700; line-height:1.12; color:{INK}">{heading}</h2></div>')


def card(inner, flex=1, pad=32, bg=CARD, extra=""):
    return (f'<div style="flex:{flex}; display:flex; flex-direction:column; gap:14px; background:{bg}; '
            f'border:1px solid {LINE}; border-radius:16px; padding:{pad}px; {extra}">{inner}</div>')


def stat(value, label, color=INK, size=72):
    return (f'<p style="{HEAD}; font-size:{size}px; font-weight:700; line-height:1.05; color:{color}">{value}</p>'
            f'<p style="font-size:26px; line-height:1.35; color:{TEXT}">{label}</p>')


def icon(name, color=ACCENT, size=44):
    return f'<x-icon name="{name}" style="width:{size}px; height:{size}px; color:{color}"></x-icon>'


def arrow():
    return f'<x-shape kind="arrow-right" style="width:40px; height:24px; background:{ACCENT}"></x-shape>'


def table(headers, rows, aligns, size=24):
    th = "".join(f'<th style="text-align:{a}; color:{MUTED}; font-size:{size - 2}px">{h}</th>' for h, a in zip(headers, aligns))
    body = "".join("<tr>" + "".join(f"<td style=\"font-size:{size}px\">{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table style="width:100%"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>'


slides = {}

slides["cover"] = section("cover", 1, f'''
<div style="position:absolute; left:0px; top:0px; width:1920px; height:1080px; background:radial-gradient(circle at 86% 92%, #8A3410 0%, #3A1D12 30%, #16181D 62%)"></div>
<p style="font-size:24px; font-weight:600; letter-spacing:2px; text-transform:uppercase; color:{HOT}">Yuva Yodha Energy Tech Hackathon 2026 · Challenge 04: Smart Manufacturing · Phase 2</p>
<div style="flex:1"></div>
<div style="display:flex; flex-direction:column; gap:28px">
  <h1 style="{HEAD}; font-size:120px; font-weight:700; line-height:1.05; color:{PAPER}">MeltWise</h1>
  <h2 style="{HEAD}; font-size:60px; font-weight:500; line-height:1.15; color:{HOT}">The working prototype</h2>
  <p style="font-size:38px; line-height:1.35; color:#D9D4CC; width:1300px">From the furnace meter to the operator's screen: a live energy copilot for induction-furnace foundries, with every result measured against ground truth.</p>
</div>
<div style="flex:1"></div>
<p style="font-size:30px; color:#A7A29A">Surianandhan Sridhar (Team lead) · Sameera Hussainy Pattan</p>''',
    "In Phase 1 we proposed MeltWise. In Phase 2 we built it: a working pipeline from a Modbus energy meter, through an offline-first edge gateway, to a physics-informed energy model and live prompts on the operator's screen. Because we have no plant data yet, we also built a calibrated furnace simulator, so every claim in this deck is measured against known ground truth.",
    dark=True, gap=0)

slides["problem"] = section("problem", 2, title("The problem today", "The waste happens inside every melt, and nobody sees it") + f'''
<div style="display:flex; gap:24px">
  {card(stat("50–80", "kWh per tonne swing between heats in the <b>same furnace</b>, from operating practice alone (BEE cluster study)", ACCENT))}
  {card(stat("35–40%", "of heat time runs at only 70–80% of rated power (BEE cluster study)", ACCENT))}
  {card(stat("13–21%", "above norms: induction-furnace energy per tonne in studied Indian foundries", ACCENT))}
</div>
<div style="display:flex; gap:24px">
  {card(f'<p style="font-size:28px; line-height:1.4">About <b>5,000 foundry units</b> in India, 90% of them MSMEs, made <b>15.86 Mt</b> of castings in 2024–25. Most see energy only as a monthly bill, weeks after the melts that wasted it.</p>', bg=SOFT)}
  {card(f'<p style="font-size:28px; line-height:1.4">Five causes do the damage: <b>overshooting</b> the tap temperature, <b>holding</b> metal while moulds catch up, a <b>lid left open</b>, <b>under-powered</b> melting, and <b>sand and rust</b> in the charge.</p>', bg=SOFT)}
</div>''', "These numbers are from Phase 1 research: the BEE cluster study found a 50 to 80 kWh per tonne swing between heats in the same furnace, caused by practice, not equipment. 35 to 40 percent of heat time ran at reduced power. The fix is per-melt visibility while the metal is still in the furnace.")

built = [("Link", "Edge gateway", "Reads the furnace meter over Modbus TCP; buffers every reading in SQLite and forwards when the network is up."),
         ("Search", "Energy model", "Physics terms recalibrated on the plant's own melts, plus gradient boosting on the charge mix. Explains every kWh by cause."),
         ("Chat", "Live operator advisor", "Bath-temperature soft sensor and six prompt types, in English, Hindi and Tamil, while the metal is still in the furnace."),
         ("Clock", "Melt scheduler", "Starts each heat so metal is ready when the moulds are, priced on the time-of-day tariff."),
         ("Chart", "Manager dashboard", "kWh per tonne by day and melt, avoidable kWh by cause, savings in rupees and CO₂."),
         ("Verified", "Buyer carbon record", "Scope 2 CO₂ for every batch from metered energy, CEA grid factor, CSV export.")]
cards = "".join(card(f'<div style="display:flex; gap:16px; align-items:center">{icon(i)}<h3 style="{HEAD}; font-size:32px; font-weight:700; color:{INK}">{t}</h3></div>'
                     f'<p style="font-size:25px; line-height:1.4">{d}</p>', pad=28) + ("</div><div style=\"display:flex; gap:24px\">" if k == 2 else "")
                for k, (i, t, d) in enumerate(built))
slides["built"] = section("built", 3, title("What we built", "Six working parts, one pipeline") + f'''
<div style="display:flex; flex-direction:column; gap:24px"><div style="display:flex; gap:24px">{cards}</div></div>
<p style="font-size:24px; color:{MUTED}">Running code: Python 3.13 · NumPy · scikit-learn · FastAPI · SQLite · pymodbus · Chart.js. 14 automated tests. Source: the team's GitHub repository.</p>''',
    "Six parts. The edge gateway talks Modbus, the same protocol as Schneider's EM6400NG and PowerLogic meters. The energy model is physics-informed machine learning. The advisor gives prompts in three languages. The scheduler, dashboard and carbon record serve the manager, planner and buyer.", gap=32)


def box(kicker, heading, items, bg=CARD):
    li = "".join(f"<li>{x}</li>" for x in items)
    return card(f'<p style="font-size:22px; font-weight:600; letter-spacing:2px; text-transform:uppercase; color:{ACCENT}">{kicker}</p>'
                f'<h3 style="{HEAD}; font-size:30px; font-weight:700; color:{INK}">{heading}</h3>'
                f'<ul style="font-size:23px; line-height:1.4">{li}</ul>', pad=26, bg=bg)


slides["architecture"] = section("architecture", 4, title("Solution architecture", "From the furnace meter to the operator's screen") + f'''
<div style="display:flex; gap:12px; align-items:stretch">
  {box("On the furnace", "Signals", ["Panel energy meter: kW, kWh (Modbus TCP)", "Lid limit switch (digital input)", "Operator app: charge, mix, dips, tap"])}
  <div style="display:flex; align-items:center">{arrow()}</div>
  {box("In the foundry", "Edge gateway", ["Polls meter: one snapshot per read", "SQLite outbox: nothing lost offline", "Forwards in order when online"])}
  <div style="display:flex; align-items:center">{arrow()}</div>
  {box("MeltWise API (FastAPI)", "Models", ["Energy model: physics + ML", "Soft sensor + live advisor", "Scheduler (ToD tariff, moulds)", "Carbon record (CEA factor)"])}
  <div style="display:flex; align-items:center">{arrow()}</div>
  {box("For people", "Web app", ["Operator: live prompts (en, hi, ta)", "Manager: kWh/t, causes, savings", "Planner: melt schedule", "Buyer: per-batch CO₂, CSV"])}
</div>
<div style="display:flex; gap:24px">
  {card(f'<p style="font-size:24px; line-height:1.45"><b>Test harness (stands in for a plant until the pilot):</b> a physics-based furnace simulator plays melts through a simulated Modbus meter at 40× speed. Re-running each melt with one practice gap removed gives the ground truth for every kWh of waste.</p>', bg=SOFT)}
  {card(f'<p style="font-size:24px; line-height:1.45"><b>Schneider Electric fit:</b> the gateway reads any Modbus meter, so EM6400NG or PowerLogic meters plug in by setting register addresses. Data can feed EcoStruxure or AVEVA.</p>', bg=SOFT)}
</div>''', "Data flows left to right. The meter and lid switch go to the gateway, which stores every reading locally before forwarding it, so a network cut delays data but never loses it. The API runs the energy model, the soft sensor and advisor, the scheduler and the carbon record, and serves the web app. Below: the simulator we use as a test harness until we have a plant.", gap=30)

coef, plant = A["learned_coefficients"], A["plant"]
crow = [["Losses while melting", f(coef["melt_loss"], 2), f(plant["loss_factor"], 2)],
        ["Losses while holding", f(coef["holding"], 2), f(plant["loss_factor"], 2)],
        ["Open-lid losses", f(coef["lid"], 2), f(plant["lid_factor"], 2)],
        ["Coil efficiency (inverse)", f(coef["base"], 2), f(1 / plant["eta_factor"], 2)]]
steps = [("1", "Measure practice from signals", "Holding minutes, avoidable lid-open time, under-powered minutes and tap temperature, from meter power, the lid switch and the operator's log."),
         ("2", "Recalibrate physics on this furnace", "Each physics term (heat to spec, losses, overshoot) gets a coefficient learned from the plant's first 30 days, pulled toward the textbook value unless the data disagree."),
         ("3", "Learn the charge", "Gradient boosting on scrap mix, weight, grade and lining age gives the best-heat energy for a charge like this one. What's left over is charge quality: sand and rust."),
         ("4", "Watch the bath live", "A soft sensor tracks bath temperature from the energy balance and resets on every dip, so MeltWise can say “tap now” before the overshoot happens.")]
step_html = "".join(f'<div style="display:flex; gap:20px; align-items:flex-start"><p style="{HEAD}; font-size:36px; font-weight:700; color:{ACCENT}; width:40px">{n}</p>'
                    f'<div style="display:flex; flex-direction:column; gap:4px"><p style="font-size:27px; font-weight:600; color:{INK}">{h}</p>'
                    f'<p style="font-size:23px; line-height:1.4">{d}</p></div></div>' for n, h, d in steps)
slides["ai"] = section("ai", 5, title("How the AI works", "Physics-informed machine learning, trained on the plant's own melts") + f'''
<div style="display:flex; gap:32px; align-items:stretch">
  <div style="flex:1.35; display:flex; flex-direction:column; gap:22px">{step_html}</div>
  {card(f'<p style="font-size:27px; font-weight:600; color:{INK}">It learns the furnace</p><p style="font-size:22px; line-height:1.4; color:{MUTED}">Plant A’s hidden constants (×textbook) vs what MeltWise learned from 240 melts</p>'
        + table(["Constant", "Learned", "True"], crow, ["left", "right", "right"], 24)
        + f'<p style="font-size:21px; line-height:1.4; color:{MUTED}">Every kWh stays traceable to a named cause, so operators trust the prompt and owners trust the savings.</p>', flex=1, pad=30)}
</div>''', "Four steps. Measure practice from the signals. Recalibrate the physics on this furnace: the coefficients start at the textbook value and move only as far as the plant's data justify. Learn the charge with gradient boosting. And watch the bath live with a soft sensor. On the right, the simulated plant had hidden constants; MeltWise learned them from its first 240 melts. Open-lid losses are the hardest to pin down.", gap=30)

slides["operator"] = section("operator", 6, title("The operator's screen", "Prompts while the metal is still in the furnace") + f'''
<div style="display:flex; gap:28px; align-items:flex-start">
  <img src="../assets/op_en.png" style="width:900px; border:1px solid {LINE}; border-radius:12px">
  <div style="flex:1; display:flex; flex-direction:column; gap:18px">
    <img src="../assets/op_hi.png" style="width:100%; border:1px solid {LINE}; border-radius:12px">
    <p style="font-size:24px; line-height:1.45">Live from the simulated meter, through the gateway. Six prompt types: under-power, dip now, <b>tap now</b>, lid open, holding, over budget, each with the kWh at stake. English, हिन्दी, தமிழ்.</p>
    <p style="font-size:20px; line-height:1.4; color:{MUTED}">Hindi and Tamil text are first drafts, to be checked with operators in the pilot.</p>
  </div>
</div>''', "This is the live operator screen, fed through the real pipeline. The banner is the latest prompt; the chart shows power and the estimated bath temperature. Here the target was reached at 60 minutes, but this simulated operator kept heating, which is exactly the overshoot MeltWise measures. On the right, the same screen in Hindi.", gap=28)

slides["manager"] = section("manager", 7, title("Manager, planner and buyer", "Where every kWh went, melt by melt") + f'''
<div style="display:flex; gap:28px; align-items:flex-start">
  <div style="width:940px; display:flex; flex-direction:column; gap:16px">
    <img src="../assets/mgr_charts.png" style="width:940px; border:1px solid {LINE}; border-radius:12px">
    <img src="../assets/melt_detail.png" style="width:940px; border:1px solid {LINE}; border-radius:12px">
  </div>
  <div style="flex:1; display:flex; flex-direction:column; gap:18px">
    <img src="../assets/carbon.png" style="width:100%; border:1px solid {LINE}; border-radius:12px">
    <p style="font-size:23px; line-height:1.45"><b>Manager:</b> daily kWh/t, avoidable kWh by cause, savings in ₹ and CO₂. Any melt opens its power curve and breakdown: this one used 667 kWh/t against 610 for its charge.</p>
    <p style="font-size:23px; line-height:1.45"><b>Buyer:</b> Scope 2 CO₂ per batch from metered energy (GHG Protocol, CEA 0.710 kg/kWh), as CSV. <b>Planner:</b> start times that cut holding.</p>
  </div>
</div>''', "The manager sees the daily trend and where the extra kilowatt-hours went. One melt here used 667 kWh per tonne against 610 for best practice on that charge: 18 overshoot, 13 holding, 12 charge quality, 8 lid, 6 under-power. The buyer gets a carbon record for every batch.", gap=28)

cal_rows = [["Typical melt today", f'{f(CAL["baseline_sec_kwh_t"], 0)} kWh/t', "650 kWh/t (our Phase 1 baseline, BEE cluster)"],
            ["Best practice, same charges", f'{f(CAL["best_practice_sec_kwh_t"], 0)} kWh/t', "593 kWh/t (US DOE best practice)"],
            ["Avoidable loss per melt", f'{f(sum(CAL["avoidable_kwh_t"].values()), 0)} kWh/t', "50–80 kWh/t heat-to-heat swing (BEE)"],
            ["Heat cycle", f'{f(CAL["cycle_min"], 0)} min', "75 min (Phase 1 model plant)"]]
slides["testing"] = section("testing", 8, title("How we measured", "No plant yet, so we built one we can trust") + f'''
<div style="display:flex; gap:28px; align-items:stretch">
  {card(f'<p style="font-size:27px; font-weight:600; color:{INK}">1 · A simulator calibrated to published figures</p>' + table(["", "Simulator", "Published"], cal_rows, ["left", "right", "left"], 23), flex=1.3, pad=30)}
  {card(f'<p style="font-size:27px; font-weight:600; color:{INK}">2 · Ground truth for every kWh</p><p style="font-size:24px; line-height:1.45">Each melt is re-run with one practice gap removed; the difference is the true waste from that cause. MeltWise never sees these.</p>'
        f'<p style="font-size:27px; font-weight:600; color:{INK}">3 · Unseen plants</p><p style="font-size:24px; line-height:1.45">Every simulated plant has hidden loss and efficiency constants. MeltWise learns them from its first 30 days, then is scored on later melts.</p>'
        f'<p style="font-size:27px; font-weight:600; color:{INK}">4 · 14 automated tests</p><p style="font-size:24px; line-height:1.45">Including a network cut mid-melt: the gateway must deliver every reading, in order, once.</p>', flex=1, pad=30)}
</div>''', "Honest measurement needs ground truth, so we built a furnace simulator whose numbers match published figures: 648 versus our 650 baseline, 588 versus DOE's 593 best practice, and 65 kWh per tonne of avoidable loss, inside BEE's 50 to 80. Re-running a melt without one gap tells us exactly what that gap cost.", gap=30)

cause_names = {"overshoot": "Temperature overshoot", "holding": "Holding molten metal", "lid": "Lid left open",
               "underpower": "Under-powered melting", "sand": "Sand and rust (not measured)"}
rows = [[cause_names[c], f(v["truth_mean_kwh_t"]), f(v["estimate_mean_kwh_t"]), f(v["correlation"], 2),
         f'{100 * v["precision"]:.0f}%', f'{100 * v["recall"]:.0f}%'] for c, v in A["causes"].items()]
slides["accuracy"] = section("accuracy", 9, title("Results: accuracy", "MeltWise finds the waste, cause by cause") + f'''
<div style="display:flex; gap:24px">
  {card(stat(f'{f(A["predicted_sec_mape_pct"])}%', "error predicting each melt's kWh/t from its signals (300 unseen melts)", GOOD, 64), pad=26)}
  {card(stat(f'{f(TAP["baseline_overshoot_mean_c"], 0)} → {f(TAP["advised_overshoot_mean_c"], 0)} °C', "tap temperature above spec when operators follow the “tap now” prompt", GOOD, 64), pad=26)}
  {card(stat(f'−{100 * SCH["holding_reduction"]:.0f}%', f'holding per heat with the scheduler ({f(SCH["asap"]["holding_min"])} → {f(SCH["meltwise"]["holding_min"])} min)', GOOD, 64), pad=26)}
  {card(stat("0", "readings lost when the network was cut mid-melt", GOOD, 64), pad=26)}
</div>
{card(table(["Cause (kWh per tonne)", "True mean", "MeltWise", "Correlation", "Precision", "Recall"], rows, ["left", "right", "right", "right", "right", "right"], 24)
      + f'<p style="font-size:21px; color:{MUTED}">Plant A, 300 unseen melts; a cause counts as present above 3 kWh/t. Five more plants: practice-cause error 1.9–3.4 kWh/t. Sand and rust are only inferred, so they are under-counted.</p>', pad=28)}''',
    "Accuracy on 300 melts the model never saw. It predicts each melt's energy within 1.4 percent. For the four practice causes, its estimates correlate 0.91 to 0.99 with the truth, with high precision and recall. Sand and rust are the weak spot because nothing measures them; we say so. Following the tap prompt cut overshoot from 42 to about 5 degrees.", gap=28)

prow = []
for c in ("0.4", "0.6", "0.8"):
    p = P[c]
    prow.append([f"{float(c):.0%}", f'{f(p["sec_before"])} → {f(p["sec_after"])}', f'<b>{f(p["saved_kwh_t"])}</b> ({f(p["saved_pct"])}%)',
                 f'{f(p["saved_ci95"][0])}–{f(p["saved_ci95"][1])}', f'₹{f(p["annual"]["inr_lakh"], 2)} lakh', f'{f(p["annual"]["t_co2"])} t'])
p90 = f(P["0.9"]["saved_kwh_t"])
slides["pilot"] = section("pilot", 10, title("Results: simulated pilot", "60 days at Plant A: 30 observing, 30 with MeltWise") + f'''
{card(table(["Operators follow prompts", "kWh/t before → after", "Saved kWh/t", "95% CI", "Per year", "CO₂ per year"], prow, ["left", "right", "right", "right", "right", "right"], 27), pad=30, flex="none")}
<div style="display:flex; gap:24px">
  {card(f'<p style="font-size:25px; line-height:1.45"><b>How it was measured:</b> 240 melts before and 240 after, same plant and charge mix. Each prompt is followed only with the given probability, and each lever works through its mechanism: the operator taps on the soft sensor\'s call, closes the lid 30 s after the prompt, and so on.</p>', bg=SOFT)}
  {card(f'<p style="font-size:25px; line-height:1.45"><b>Honest read:</b> the conservative Phase 1 estimate (16.7 kWh/t) holds at 40–60% follow-through. Our Phase 1 “likely” 33.2 kWh/t needs about 90% (measured: {p90} kWh/t). Sand and rust savings are still an assumption for a real pilot to test.</p>', bg=SOFT)}
</div>
<p style="font-size:21px; color:{MUTED}">Per year: one 1 t furnace, 2,400 t a year, ₹8/kWh, 0.710 kg CO₂/kWh; before subscription.</p>''',
    "The pilot simulation. At 60 percent follow-through, kilowatt-hours per tonne fall from 657.6 to 635, a saving of 22.6, with a 95 percent confidence interval of 17 to 28. That is 4.3 lakh rupees and 38 tonnes of CO2 a year for one furnace. This is below our Phase 1 likely estimate, and we say so: the mechanisms are now modelled, not assumed.", gap=26)

kit = [["Modbus energy meter (EM6400NG, class 0.5S)", "₹17,289"], ["CTs, wiring, lid switch, enclosure", "₹15,000"],
       ["Industrial edge gateway", "₹20,000"], ["Shop-floor display or tablet", "₹15,000"], ["Installation and training", "₹20,000"],
       ["<b>Kit per furnace</b>", "<b>₹87,289</b>"]]
net60 = P["0.6"]["annual"]["inr_lakh"] * 1e5 - 48000
net40 = P["0.4"]["annual"]["inr_lakh"] * 1e5 - 48000
slides["cost"] = section("cost", 11, title("Cost and business model", "Cheap to build, fast to pay back") + f'''
<div style="display:flex; gap:28px; align-items:stretch">
  {card(f'<p style="font-size:27px; font-weight:600; color:{INK}">To build the prototype</p>' + stat("₹0", "cash spent: open-source stack, our laptops, simulated meter and plant", INK, 64)
        + f'<p style="font-size:24px; line-height:1.4">Next: a real pilot needs one kit and hosting (about ₹1,000 a month for the first plants).</p>', pad=30)}
  {card(f'<p style="font-size:27px; font-weight:600; color:{INK}">To scale: per furnace</p>' + table(["Item", "Cost"], kit, ["left", "right"], 23), flex=1.25, pad=30)}
  {card(f'<p style="font-size:27px; font-weight:600; color:{INK}">Revenue and payback</p><p style="font-size:24px; line-height:1.45">Subscription <b>₹4,000 a furnace a month</b>, sold through foundry cluster associations; kit financed through SIDBI 4E or bundled with Schneider meters.</p>'
        + stat(f'{87289 / (net60 / 12):.1f} months', f"payback at the pilot's 60% result (₹{net60 / 1e5:.2f} lakh/yr net); {87289 / (net40 / 12):.1f} months at 40%", GOOD, 56), pad=30)}
</div>''', "Building the prototype cost us nothing in cash. To scale, each furnace needs an 87,289 rupee kit. We charge 4,000 rupees a furnace a month. At the pilot's 60 percent result the net saving is about 3.85 lakh a year, so the kit pays back in under three months; under five months at 40 percent.", gap=30)

phases = [("Now – Jan 2027", "First real furnace", ["One foundry via a cluster association", "Install kit; 30 days observing", "30 days with prompts: measure kWh/t", "Check translations with operators"]),
          ("Feb – Jun 2027", "10 furnaces, one cluster", ["Retrain the model per furnace", "Supplier charge-quality reports", "WhatsApp summaries for owners", "Measure follow-through, refine prompts"]),
          ("Late 2027 →", "Scale", ["Cluster associations as channel", "SIDBI 4E and BEE schemes for kits", "Schneider meters, EcoStruxure link", "Steel and aluminium melt shops"])]
pcards = "".join(card(f'<p style="font-size:22px; font-weight:600; letter-spacing:2px; text-transform:uppercase; color:{ACCENT}">{w}</p>'
                      f'<h3 style="{HEAD}; font-size:34px; font-weight:700; color:{INK}">{h}</h3><ul style="font-size:25px; line-height:1.5">'
                      + "".join(f"<li>{x}</li>" for x in items) + "</ul>", pad=30) for w, h, items in phases)
slides["next"] = section("next", 12, title("Next steps", "Who uses it, and how it rolls out") + f'''
<div style="display:flex; gap:24px">{pcards}</div>
{card(f'<p style="font-size:25px; line-height:1.45"><b>Users:</b> the furnace operator (prompts on a shop-floor screen), the shift supervisor and plant manager (dashboard and schedule), the owner (monthly savings), and buyers (carbon record per batch).</p>', bg=SOFT, flex="none")}''',
    "First, one real furnace through a cluster association, using the same 30-days-observe, 30-days-with-prompts design we simulated, so the results are comparable. Then ten furnaces in one cluster, then scale through associations, government financing and Schneider's channel.", gap=30)

s60 = P["0.6"]["saved_kwh_t"]
slides["impact"] = section("impact", 13, title("Broader impact", "If 1,000 foundries reach the pilot's 60% result") + f'''
<div style="display:flex; gap:24px">
  {card(stat(f'{s60 * 2400 * 1000 / 1e6:.0f} GWh', "electricity saved a year", GOOD))}
  {card(stat(f'₹{s60 * 2400 * 1000 * 8 / 1e7:.0f} crore', "a year back to MSME foundries", GOOD))}
  {card(stat(f'{s60 * 2400 * 1000 * 0.71 / 1000:,.0f} t', "of CO₂ avoided a year (grid factor 0.710)", GOOD))}
</div>
<div style="display:flex; gap:24px">
  {card(f'<p style="font-size:25px; line-height:1.45"><b>Economic:</b> energy is 15–30% of cost in energy-intensive SMEs; a saving that pays back in months protects thin margins and jobs.</p>', bg=SOFT)}
  {card(f'<p style="font-size:25px; line-height:1.45"><b>Environmental:</b> per-batch, metered CO₂ records help small suppliers answer buyers’ carbon-disclosure requests.</p>', bg=SOFT)}
  {card(f'<p style="font-size:25px; line-height:1.45"><b>Social:</b> prompts in the operator’s own language put the know-how of the best shifts in every operator’s hands.</p>', bg=SOFT)}
</div>
<div style="display:flex; justify-content:space-between; align-items:center; gap:32px; background:{INK}; border-radius:16px; padding:28px 40px">
  <p style="{HEAD}; font-size:38px; font-weight:700; color:{PAPER}">MeltWise · <span style="color:{HOT}">Every melt, measured.</span></p>
  <p style="font-size:26px; color:#D9D4CC">Surianandhan Sridhar (Team lead) · Sameera Hussainy Pattan</p>
</div>''', "At scale: if 1,000 foundries reach the pilot's 60 percent result, that is about 54 gigawatt-hours, 43 crore rupees and 38,500 tonnes of CO2 a year. Beyond the numbers: margins for MSMEs, carbon records for their buyers, and the best shift's know-how for every operator.", gap=28)

order = ["cover", "problem", "built", "architecture", "ai", "operator", "manager", "testing", "accuracy", "pilot", "cost", "next", "impact"]
assert len(order) == TOTAL and set(order) == set(slides)
for sid in order:
    (DECK / "slides" / f"{sid}.html").write_text(slides[sid])
(DECK / "deck.json").write_text(json.dumps({
    "title": "MeltWise Phase 2 Prototype", "order": order, "cover": "cover",
    "faces": {"space-grotesk": {"family": "Space Grotesk", "href": "https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400..700&display=swap"},
              "ibm-plex-sans": {"family": "IBM Plex Sans", "href": "https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap"}},
}, indent=2) + "\n")
print("wrote", len(order), "slides")
