"""Live operator advisor: a bath-temperature soft sensor plus shop-floor prompts.

Fed one meter reading at a time (power, lid switch) plus the operator app's
events, it raises short prompts in the operator's language while the metal is
still in the furnace. Translations are first drafts and need review by
Hindi- and Tamil-speaking operators before a pilot.
"""

from . import config as C
from . import physics

LID_GRACE_S = 45
UNDERPOWER_GRACE_S = 120
HOLDING_REMINDER_MIN = 5
TAP_MARGIN_C = 8.0   # aim a little above spec: a cold tap scraps castings
BUDGET_TOLERANCE = 1.03

MESSAGES = {
    "lid_open": {
        "en": "Lid open {minutes} min: about {kwh} kWh lost. Close the lid.",
        "hi": "ढक्कन {minutes} मिनट से खुला है: लगभग {kwh} kWh बर्बाद। ढक्कन बंद करें।",
        "ta": "மூடி {minutes} நிமிடமாகத் திறந்துள்ளது: சுமார் {kwh} kWh வீண். மூடியை மூடவும்.",
    },
    "underpower": {
        "en": "Power at {pct}% of rated for {minutes} min. Check the power setting.",
        "hi": "बिजली {minutes} मिनट से रेटेड की {pct}% पर है। पावर सेटिंग जाँचें।",
        "ta": "மின்சக்தி {minutes} நிமிடமாக மதிப்பிட்ட அளவின் {pct}% இல் உள்ளது. பவர் அமைப்பைச் சரிபார்க்கவும்.",
    },
    "dip_now": {
        "en": "Bath near target (about {temp} °C). Take a temperature dip and sample.",
        "hi": "धातु लक्ष्य के पास है (लगभग {temp} °C)। तापमान डिप और सैंपल लें।",
        "ta": "உலோகம் இலக்கை நெருங்குகிறது (சுமார் {temp} °C). வெப்பநிலை டிப் மற்றும் மாதிரி எடுக்கவும்.",
    },
    "tap_ready": {
        "en": "Target reached (about {temp} °C). Tap now, or drop to holding power.",
        "hi": "लक्ष्य तापमान पहुँच गया (लगभग {temp} °C)। अभी टैप करें या होल्डिंग पावर पर करें।",
        "ta": "இலக்கு வெப்பநிலை எட்டப்பட்டது (சுமார் {temp} °C). இப்போது டேப் செய்யவும் அல்லது ஹோல்டிங் பவருக்கு மாற்றவும்.",
    },
    "holding": {
        "en": "Metal held {minutes} min: about {kwh} kWh used. Are the moulds ready?",
        "hi": "धातु {minutes} मिनट से होल्ड पर है: लगभग {kwh} kWh खर्च। क्या साँचे तैयार हैं?",
        "ta": "உலோகம் {minutes} நிமிடமாகக் காத்திருக்கிறது: சுமார் {kwh} kWh செலவு. அச்சுகள் தயாரா?",
    },
    "over_budget": {
        "en": "This heat has used {kwh} kWh, over its {budget} kWh target.",
        "hi": "इस हीट में {kwh} kWh लग चुके हैं, जो {budget} kWh लक्ष्य से ज़्यादा है।",
        "ta": "இந்த ஹீட் {kwh} kWh பயன்படுத்தியுள்ளது; இலக்கு {budget} kWh ஐ விட அதிகம்.",
    },
}


class TemperatureEstimator:
    """Bath temperature from the energy balance; reset to the measured value on every dip."""

    def __init__(self, charge, eta_scale=1.0, loss_scale=1.0):
        self.charge = charge
        self.eta_scale, self.loss_scale = eta_scale, loss_scale
        self.melt_heat = physics.required_melt_heat(charge.weight_t, charge.steel, 0.0)
        self.heat = -C.LINING_SOAK_KWH
        self.calibrated = False

    @property
    def temp_c(self):
        return physics.temperature(max(self.heat, 0.0), self.charge.weight_t, self.melt_heat)

    @property
    def molten(self):
        return self.heat >= self.melt_heat

    def step(self, power_kw, lid_open, dt_s):
        temp, c = self.temp_c, self.charge
        eta = physics.efficiency(temp, c.weight_t, c.borings) * self.eta_scale
        loss = physics.heat_loss_kw(temp, lid_open, c.lining_age) * self.loss_scale
        self.heat += (eta * power_kw - loss) * dt_s / 3600.0

    def rise_per_step_c(self, power_kw, dt_s):
        """Temperature gain of a molten bath over the next reading, so prompts can lead instead of lag."""
        c = self.charge
        eta = physics.efficiency(self.temp_c, c.weight_t, c.borings) * self.eta_scale
        return eta * power_kw * dt_s / 3600.0 / (c.weight_t * C.CP_LIQUID_KWH_T_K)

    def calibrate(self, measured_temp_c):
        self.heat = physics.heat_for_temperature(measured_temp_c, self.charge.weight_t, self.melt_heat)
        self.calibrated = True


def scales_from_model(model):
    """The energy model's learned coefficients, turned into plant constants for the soft sensor."""
    if model is None:
        return 1.0, 1.0
    coef = model.coefficients()
    return 1.0 / coef["base"], coef["holding"]


class Advisor:
    def __init__(self, charge, model=None, lang="en", dt_s=10.0):
        self.charge, self.lang, self.dt_s = charge, lang, dt_s
        self.estimator = TemperatureEstimator(charge, *scales_from_model(model))
        self.budget_kwh = model.budget_kwh(charge) if model is not None else None
        self.t_s = 0.0
        self.energy_kwh = 0.0
        self.necessary_until = 0.0
        self.lid_since = self.low_since = None
        self.lid_kwh = 0.0
        self.dips = 0
        self.tapped = False
        self.hold_since = None
        self.hold_kwh = 0.0
        self.fired = set()
        self.prompts = []

    def _say(self, code, key, **values):
        if key in self.fired:
            return None
        self.fired.add(key)
        prompt = {"t_s": self.t_s, "code": code, "values": values,
                  "text": {lang: MESSAGES[code][lang].format(**values) for lang in MESSAGES[code]}}
        prompt["message"] = prompt["text"][self.lang]
        self.prompts.append(prompt)
        return prompt

    def on_event(self, event):
        kind = event["kind"]
        if kind == "charge":
            self.necessary_until = event["t_s"] + C.CHARGE_LID_MIN * 60
        elif kind == "dip":
            self.dips += 1
            self.necessary_until = event["t_s"] + C.DIP_LID_MIN * 60
            if event.get("temp_c") is not None:
                self.estimator.calibrate(event["temp_c"])
        elif kind == "tap":
            self.tapped = True
            self.necessary_until = event["t_s"] + C.TAP_MIN * 60

    def update(self, t_s, power_kw, lid_open, events=()):
        """Consume one reading; returns the prompts raised by it."""
        self.t_s = t_s
        for event in events:
            self.on_event(event)
        before = len(self.prompts)
        rated, spec = C.RATED_POWER_KW, self.charge.spec_temp_c
        est = self.estimator
        temp = est.temp_c

        if lid_open and t_s >= self.necessary_until and not self.tapped:
            self.lid_since = t_s if self.lid_since is None else self.lid_since
            extra = physics.heat_loss_kw(temp, True, self.charge.lining_age) - physics.heat_loss_kw(
                temp, False, self.charge.lining_age)
            self.lid_kwh += extra / 0.77 * self.dt_s / 3600
            if t_s - self.lid_since >= LID_GRACE_S:
                self._say("lid_open", f"lid@{self.lid_since}", minutes=round((t_s - self.lid_since) / 60 + 0.5),
                          kwh=round(self.lid_kwh, 1))
        else:
            self.lid_since, self.lid_kwh = None, 0.0

        if self.dips == 0 and 0 < power_kw < C.UNDERPOWER_THRESHOLD * rated:
            self.low_since = t_s if self.low_since is None else self.low_since
            if t_s - self.low_since >= UNDERPOWER_GRACE_S:
                self._say("underpower", f"low@{self.low_since}", pct=round(100 * power_kw / rated),
                          minutes=round((t_s - self.low_since) / 60))
        else:
            self.low_since = None

        if self.dips == 0 and est.molten and temp >= spec - 30:
            self._say("dip_now", "dip_now", temp=round(temp / 5) * 5)
        ahead = temp + est.rise_per_step_c(power_kw, self.dt_s)
        if self.dips >= 1 and est.calibrated and ahead >= spec + TAP_MARGIN_C and not self.tapped:
            self._say("tap_ready", "tap_ready", temp=round(temp / 5) * 5)

        if "tap_ready" in self.fired and not self.tapped and power_kw < 0.4 * rated:
            self.hold_since = t_s if self.hold_since is None else self.hold_since
            self.hold_kwh += power_kw * self.dt_s / 3600
            held = (t_s - self.hold_since) / 60
            if held >= HOLDING_REMINDER_MIN:
                block = int(held // HOLDING_REMINDER_MIN)
                self._say("holding", f"hold#{block}", minutes=block * HOLDING_REMINDER_MIN, kwh=round(self.hold_kwh))

        self.energy_kwh += power_kw * self.dt_s / 3600
        if self.budget_kwh and self.energy_kwh > self.budget_kwh * BUDGET_TOLERANCE and not self.tapped:
            self._say("over_budget", "over_budget", kwh=round(self.energy_kwh), budget=round(self.budget_kwh))

        est.step(power_kw, lid_open, self.dt_s)
        return self.prompts[before:]

    def state(self):
        return {"t_s": self.t_s, "energy_kwh": round(self.energy_kwh, 1), "est_temp_c": round(self.estimator.temp_c),
                "calibrated": self.estimator.calibrated, "budget_kwh": round(self.budget_kwh) if self.budget_kwh else None,
                "tapped": self.tapped}


class AdvisedOperator:
    """An operator who stops superheating when the advisor says the target is reached.

    Plugs into simulator.simulate(stop_superheat=...), so the simulated tap temperature
    depends on how accurate MeltWise's soft sensor really is.
    """

    def __init__(self, charge, model=None, margin_c=TAP_MARGIN_C):
        self.estimator = TemperatureEstimator(charge, *scales_from_model(model))
        self.spec, self.margin = charge.spec_temp_c, margin_c
        self.i, self.seen = 0, 0

    def __call__(self, view):
        powers, lids, events, dt = view["power_kw"], view["lid_open"], view["events"], view["dt_s"]
        while self.i < len(powers):
            t = self.i * dt
            for e in events[self.seen:]:
                if e["t_s"] > t:
                    break
                if e["kind"] == "dip":
                    self.estimator.calibrate(e["temp_c"])
                self.seen += 1
            self.estimator.step(powers[self.i], lids[self.i], dt)
            self.i += 1
        for e in events[self.seen:]:
            if e["kind"] == "dip":
                self.estimator.calibrate(e["temp_c"])
            self.seen += 1
        est = self.estimator
        last_power = powers[-1] if len(powers) else 0.0
        return est.calibrated and est.temp_c + est.rise_per_step_c(last_power, dt) >= self.spec + self.margin
