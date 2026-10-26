# MeltWise demo video: script and shot list (about 4 minutes)

Record your screen with voice-over (QuickTime: File → New Screen Recording, with the microphone on). Speak in your own words; the lines below are a guide. Upload as unlisted on YouTube, or to Google Drive with "anyone with the link", and paste the link into field 8 of the form.

## Before recording

Open two terminals in the `prototype` folder and prepare the demo data once:

```bash
cd prototype
.venv/bin/python scripts/build_demo_data.py
.venv/bin/uvicorn meltwise.api:app --port 8000
```

Open http://127.0.0.1:8000 in the browser, full screen, zoomed to 90% so the whole operator view fits. Have the second terminal ready with this command typed but **not run**:

```bash
.venv/bin/python scripts/live_demo.py --melts 1 --speed 30 --outage 10
```

## Shots

| Time | Show | Say |
|---|---|---|
| 0:00–0:25 | The deck's cover slide, then the problem slide | "India's 5,000 foundries waste 50 to 80 kWh per tonne between melts in the same furnace, and nobody sees it until the monthly bill. MeltWise shows it while the metal is still in the furnace." |
| 0:25–0:45 | The architecture slide | "Here is what we built: a Modbus meter feeds an offline-first edge gateway, which feeds our physics-informed model and live prompts. We have no plant yet, so a calibrated furnace simulator plays the role of the plant and the meter." |
| 0:45–1:00 | Run the `live_demo.py` command; the browser's Operator view comes alive | "This melt is streaming from a simulated Modbus meter, through the gateway, into MeltWise." |
| 1:00–1:40 | The first "Power at 75% of rated" prompt appears; point at the energy bar and the chart | "MeltWise spots under-powered melting within two minutes. It tracks energy against a target for this exact charge." |
| 1:40–1:55 | The terminal prints "Network cut for 10 s"; the screen pauses, then catches up | "Now we cut the network. The gateway keeps every reading in a local outbox and sends it when the network returns. Nothing is lost." |
| 1:55–2:30 | The "Bath near target" and "Target reached: tap now" prompts; the temperature tile shows "checked by dip" | "Our soft sensor estimates bath temperature from the energy balance and resets on every dip. It says tap now at the right moment. Today's operators overshoot by about 42 °C; following this prompt, by about 5." |
| 2:30–2:45 | Switch the language to हिन्दी, then தமிழ் | "Prompts appear in the operator's own language." |
| 2:45–3:15 | The Manager tab; click a melt in the table to show its breakdown | "The manager sees kWh per tonne before and after, and where every extra kWh went. This melt used 667 kWh per tonne against 610 for its charge: overshoot, holding, charge quality, open lid and under-power." |
| 3:15–3:30 | The Planner tab | "The scheduler starts each heat so the metal is ready when the moulds are. Over 300 simulated days, it cut holding by half." |
| 3:30–3:40 | The Buyer tab; click Download CSV | "Every batch gets a metered carbon record for buyers." |
| 3:40–4:10 | The accuracy and pilot slides | "We measured everything against ground truth. MeltWise predicts each melt's energy within 1.4%. In a simulated 60-day pilot with operators following 60% of prompts, energy per tonne fell 22.6 kWh: 4.3 lakh rupees and 38 tonnes of CO₂ a year for one furnace. Next, a real furnace through a cluster association." |
| 4:10–4:20 | The final slide | "MeltWise: every melt, measured." |

## Tips

- Do a dry run first. At `--speed 30`, one melt takes about 2.5 minutes, so the live part fits the script.
- The default melt (seed 12) raises under-power, dip, tap-ready, lid-open and holding prompts, so every line above has its moment. If a prompt is late, keep talking about the chart.
- Keep the video under 5 minutes.
