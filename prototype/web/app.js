// MeltWise web app: operator (live), manager, planner and buyer views.
const CAUSE_LABELS = {
  overshoot: "Temperature overshoot", holding: "Holding molten metal", lid: "Lid left open",
  underpower: "Under-powered melting", sand: "Charge quality (sand, rust)",
};
const ALERTS = new Set(["lid_open", "underpower", "holding", "over_budget", "tap_ready"]);
const fmt = (n, d = 0) => Number(n).toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d });
const charts = {};
let liveTimer = null;

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v; else if (k === "onclick") node.onclick = v; else node.setAttribute(k, v);
  }
  for (const c of children) node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return node;
}

async function api(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

function chart(id, config) {
  if (charts[id]) charts[id].destroy();
  config.options = { responsive: true, maintainAspectRatio: false, ...config.options };
  charts[id] = new Chart(document.getElementById(id), config);
  return charts[id];
}

function tile(label, value, sub, cls = "") {
  return el("div", { class: "tile" }, el("div", { class: "label" }, label),
    el("div", { class: `value ${cls}` }, value), el("div", { class: "sub" }, sub));
}

// ---------- navigation ----------
function show(view) {
  document.querySelectorAll("nav button").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === view));
  load(view);
}
document.querySelectorAll("nav button").forEach((button) => {
  button.onclick = () => { history.replaceState(null, "", `#/${button.dataset.view}`); show(button.dataset.view); };
});

function load(view) {
  clearInterval(liveTimer);
  if (view === "operator") { refreshLive(); liveTimer = setInterval(refreshLive, 700); }
  if (view === "manager") loadManager();
  if (view === "planner") loadPlanner();
  if (view === "buyer") loadBuyer();
}

// ---------- operator ----------
let liveChart = null;
async function refreshLive() {
  const lang = document.getElementById("lang").value;
  const data = await api(`/api/live?lang=${lang}`).catch(() => ({ active: false }));
  document.getElementById("live-empty").hidden = data.active;
  document.getElementById("live").hidden = !data.active;
  if (!data.active) return;
  const s = data.state, last = data.trace[data.trace.length - 1] || {};
  const latest = data.prompts[data.prompts.length - 1];
  const prompt = document.getElementById("prompt");
  document.getElementById("prompt-text").textContent = latest ? latest.message : "Melting. No action needed.";
  prompt.classList.toggle("alert", Boolean(latest && ALERTS.has(latest.code) && s.t_s - latest.t_s < 120));

  document.getElementById("t-temp").textContent = s.calibrated || s.est_temp_c > 1100 ? `${fmt(s.est_temp_c)} °C` : "Melting";
  document.getElementById("t-target").textContent = `Target ${fmt(data.spec_temp_c)} °C${s.calibrated ? " · checked by dip" : ""}`;
  document.getElementById("t-energy").textContent = `${fmt(s.energy_kwh)} kWh`;
  const share = s.budget_kwh ? s.energy_kwh / s.budget_kwh : 0;
  const bar = document.getElementById("t-bar");
  bar.style.width = `${Math.min(share, 1) * 100}%`;
  bar.classList.toggle("over", share > 1.03);
  document.getElementById("t-budget").textContent = s.budget_kwh ? `Target for this charge: ${fmt(s.budget_kwh)} kWh` : "";
  document.getElementById("t-power").textContent = last.power_kw !== undefined ? `${fmt(last.power_kw)} kW` : "–";
  document.getElementById("t-rated").textContent = `Rated ${fmt(data.rated_kw)} kW`;
  const lid = document.getElementById("t-lid");
  lid.textContent = last.lid_open ? "Open" : "Closed";
  lid.className = `value ${last.lid_open ? "hot" : ""}`;
  const c = data.charge;
  document.getElementById("t-charge").textContent =
    `${fmt(c.weight_t, 2)} t ${c.grade === "sg" ? "SG" : "grey"} iron · heat ${data.melt_no + 1}`;

  const log = document.getElementById("prompt-log");
  log.replaceChildren(...data.prompts.slice().reverse().map((p) =>
    el("li", {}, el("span", {}, `${fmt(p.t_s / 60, 1)} min`), p.message)));

  const labels = data.trace.map((r) => (r.t_s / 60).toFixed(1));
  if (!liveChart || liveChart.data.datasets[0].data.length > data.trace.length) {
    liveChart = chart("live-chart", {
      type: "line",
      data: { labels, datasets: [
        { label: "Power (kW)", data: data.trace.map((r) => r.power_kw), borderColor: "#C2410C", pointRadius: 0, yAxisID: "y", borderWidth: 2 },
        { label: "Est. bath temperature (°C)", data: data.trace.map((r) => r.est_temp_c), borderColor: "#16181D", pointRadius: 0, yAxisID: "y2", borderWidth: 2, borderDash: [6, 4] },
      ] },
      options: { animation: false, interaction: { mode: "index", intersect: false },
        scales: { x: { title: { display: true, text: "Minutes into heat" }, ticks: { maxTicksLimit: 12 } },
          y: { title: { display: true, text: "kW" }, min: 0 },
          y2: { position: "right", title: { display: true, text: "°C" }, min: 0, max: 1700, grid: { drawOnChartArea: false } } } },
    });
  } else {
    liveChart.data.labels = labels;
    liveChart.data.datasets[0].data = data.trace.map((r) => r.power_kw);
    liveChart.data.datasets[1].data = data.trace.map((r) => r.est_temp_c);
    liveChart.update();
  }
}
document.getElementById("lang").onchange = refreshLive;

// ---------- manager ----------
async function loadManager() {
  const s = await api("/api/summary");
  document.getElementById("kpis").replaceChildren(
    tile("Before MeltWise", `${fmt(s.sec_before, 1)} kWh/t`, "30 days, observing only"),
    tile("With MeltWise", `${fmt(s.sec_after, 1)} kWh/t`, "next 30 days", "good"),
    tile("Saved", `${fmt(s.saved_kwh_t, 1)} kWh/t`, `${fmt(s.saved_pct, 1)}% less electricity per tonne`, "good"),
    tile("Per year", `₹${fmt(s.annual.inr / 1e5, 2)} lakh`, `${fmt(s.annual.kwh / 1000)} MWh · ${fmt(s.annual.t_co2, 1)} t CO₂ avoided`, "good"),
  );
  const byPeriod = (period) => s.daily.map((d) => (d.period === period ? d.sec : null));
  chart("daily-chart", {
    type: "line",
    data: { labels: s.daily.map((d) => d.day.slice(5)),
      datasets: [
        { label: "Before (observing only)", data: byPeriod("before"), borderColor: "#9AA0AA", backgroundColor: "#9AA0AA", pointRadius: 3, borderWidth: 2, spanGaps: false },
        { label: "With MeltWise", data: byPeriod("after"), borderColor: "#1F7A4D", backgroundColor: "#1F7A4D", pointRadius: 3, borderWidth: 2, spanGaps: false },
      ] },
    options: { scales: { y: { title: { display: true, text: "kWh per tonne (daily average)" } } } },
  });
  const causes = Object.keys(CAUSE_LABELS);
  chart("cause-chart", {
    type: "bar",
    data: { labels: causes.map((c) => CAUSE_LABELS[c]),
      datasets: [
        { label: "Before", data: causes.map((c) => s.waste_by_cause.before[c]), backgroundColor: "#9AA0AA" },
        { label: "With MeltWise", data: causes.map((c) => (s.waste_by_cause.after || {})[c]), backgroundColor: "#1F7A4D" },
      ] },
    options: { indexAxis: "y", scales: { x: { title: { display: true, text: "kWh per tonne" } } } },
  });
  const melts = await api("/api/melts?limit=15");
  document.querySelector("#melt-table tbody").replaceChildren(...melts.map((m) => {
    const waste = Object.entries(m.waste_kwh_t).sort((a, b) => b[1] - a[1]);
    const avoidable = waste.reduce((sum, [, v]) => sum + v, 0);
    return el("tr", { onclick: () => showMelt(m.id) },
      el("td", {}, m.started_at.replace("T", " "), " ", el("span", { class: `pill ${m.period}` }, m.period === "after" ? "MeltWise" : "before")),
      el("td", {}, m.grade === "sg" ? "SG iron" : "Grey iron"),
      el("td", { class: "num" }, fmt(m.sec_kwh_t, 1)),
      el("td", { class: "num" }, fmt(m.expected_best_kwh_t, 1)),
      el("td", { class: "num" }, fmt(avoidable, 1)),
      el("td", {}, `${CAUSE_LABELS[waste[0][0]]} (${fmt(waste[0][1], 1)})`));
  }));
}

async function showMelt(id) {
  const m = await api(`/api/melts/${id}`);
  const box = document.getElementById("melt-detail");
  box.hidden = false;
  document.getElementById("detail-title").textContent =
    `Melt ${m.carbon.batch_id} · ${m.started_at.replace("T", " ")} · ${fmt(m.explain.sec_kwh_t, 1)} kWh/t`;
  const p = m.series.power_kw;
  chart("detail-chart", {
    type: "line",
    data: { labels: p.map((_, i) => (i * m.series.dt_s / 60).toFixed(1)),
      datasets: [
        { label: "Power (kW)", data: p, borderColor: "#C2410C", pointRadius: 0, borderWidth: 2, fill: false },
        { label: "Lid open", data: m.series.lid_open.map((x) => (x ? 700 : null)), borderColor: "#FF7A1A", pointRadius: 0, borderWidth: 6, spanGaps: false },
      ] },
    options: { animation: false, scales: { x: { ticks: { maxTicksLimit: 10 }, title: { display: true, text: "Minutes" } }, y: { min: 0, max: 750 } } },
  });
  const rows = Object.entries(m.explain.waste_kwh_t).sort((a, b) => b[1] - a[1]).map(([cause, kwh]) =>
    el("div", { class: "waste-row" }, el("span", {}, CAUSE_LABELS[cause]), el("strong", {}, `${fmt(kwh, 1)} kWh/t`)));
  const ms = m.explain.measured;
  document.getElementById("detail-waste").replaceChildren(
    el("p", { class: "sub" }, `Best practice for this charge: ${fmt(m.explain.expected_best_kwh_t, 1)} kWh/t`), ...rows,
    el("p", { class: "sub" }, `Tapped at ${fmt(ms.tap_temp_c)} °C · held ${fmt(ms.holding_min, 1)} min · lid open ${fmt(ms.lid_avoidable_min, 1)} min beyond charging · ${fmt(ms.underpower_min, 1)} min under-powered`),
    el("p", { class: "sub" }, `Carbon: ${fmt(m.carbon.scope2_kg_co2)} kg CO₂ (${fmt(m.carbon.kg_co2_per_t)} kg/t)`));
  box.scrollIntoView({ behavior: "smooth" });
}

// ---------- planner ----------
async function loadPlanner() {
  const d = await api("/api/schedule/demo");
  const today = d.asap, mw = d.meltwise;
  document.getElementById("plan-kpis").replaceChildren(
    tile("Holding today", `${fmt(today.holding_min)} min`, "metal waiting for moulds"),
    tile("Holding with MeltWise", `${fmt(mw.holding_min)} min`, `${fmt(100 * (1 - mw.holding_min / today.holding_min))}% less`, "good"),
    tile("Electricity cost", `₹${fmt(today.cost_inr - mw.cost_inr)}`, "saved today (holding and tariff)", "good"),
  );
  document.querySelector("#plan-table tbody").replaceChildren(...d.moulds.map((mould, i) => el("tr", {},
    el("td", {}, i + 1), el("td", {}, mould),
    el("td", {}, today.heats[i].start), el("td", { class: "num" }, `${fmt(today.heats[i].holding_min, 1)} min`),
    el("td", {}, mw.heats[i].start), el("td", { class: "num" }, `${fmt(mw.heats[i].holding_min, 1)} min`))));
}

// ---------- buyer ----------
async function loadBuyer() {
  const rows = await api("/api/carbon?limit=60");
  document.querySelector("#carbon-table tbody").replaceChildren(...rows.map((r) => el("tr", {},
    el("td", {}, r.batch_id), el("td", {}, r.started_at.replace("T", " ")), el("td", {}, r.grade),
    el("td", { class: "num" }, fmt(r.liquid_metal_t, 3)), el("td", { class: "num" }, fmt(r.electricity_kwh, 1)),
    el("td", { class: "num" }, fmt(r.kwh_per_t, 1)), el("td", { class: "num" }, fmt(r.scope2_kg_co2, 1)),
    el("td", { class: "num" }, fmt(r.kg_co2_per_t, 1)))));
}

// Deep links: /#/manager, /#/melt-3, /?lang=hi#/operator
const startLang = new URLSearchParams(location.search).get("lang");
if (["en", "hi", "ta"].includes(startLang)) document.getElementById("lang").value = startLang;
const hash = location.hash.replace(/^#\/?/, "");
if (/^melt-\d+$/.test(hash)) { show("manager"); showMelt(Number(hash.slice(5))); }
else show(["operator", "manager", "planner", "buyer"].includes(hash) ? hash : "operator");
