"""Physics-informed energy model: what each melt should have cost, and where the rest went.

Two stages, both trained on the plant's own melt history:
  1. A linear model over nominal-physics terms (heat to spec, losses while melting,
     overshoot, holding, open lid, under-powered time). Fitting the coefficients
     recalibrates textbook physics to this furnace, and keeps every kWh traceable
     to a cause.
  2. Gradient boosting on the charge (scrap mix, weight, grade, lining age) that
     learns what is left over. A low-quantile model gives the best-heat envelope for
     a charge like this one; whatever a melt uses above that envelope, and not
     explained by practice, is reported as charge quality (sand, rust, oxidised scrap).
"""

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor

from . import features as F

TERMS = ("base", "melt_loss", "overshoot", "holding", "lid", "underpower")
PRACTICE_CAUSES = ("overshoot", "holding", "lid", "underpower")
BEST_QUANTILE = 0.10
PRIOR_STRENGTH = 0.05   # pull each physics coefficient toward 1.0 (textbook) unless the data disagree


class EnergyModel:
    def fit(self, observations):
        rows = [self._row(o) for o in observations]
        X = np.array([[r["terms"][t] for t in TERMS] for r in rows])
        y = np.array([o.sec_kwh_t for o in observations])
        A = np.column_stack([np.ones(len(X)), X])
        # Ridge toward the physics prior: extra rows ask each coefficient to stay near 1.0.
        weights = np.sqrt(PRIOR_STRENGTH * (X**2).sum(axis=0))
        prior_rows = np.column_stack([np.zeros(len(TERMS)), np.diag(weights)])
        self.coef_, *_ = np.linalg.lstsq(np.vstack([A, prior_rows]), np.concatenate([y, weights]), rcond=None)
        residual = y - A @ self.coef_
        charges = np.array([F.charge_features(o.charge) for o in observations])
        params = dict(n_estimators=200, max_depth=3, learning_rate=0.05, subsample=0.8, random_state=0)
        self.best_ = GradientBoostingRegressor(loss="quantile", alpha=BEST_QUANTILE, **params).fit(charges, residual)
        self.median_ = GradientBoostingRegressor(loss="quantile", alpha=0.5, **params).fit(charges, residual)
        return self

    @staticmethod
    def _row(obs):
        measured = F.measure(obs)
        return {"measured": measured, "terms": F.physics_terms(obs.charge, measured)}

    def coefficients(self):
        return {"intercept": float(self.coef_[0]), **{t: float(c) for t, c in zip(TERMS, self.coef_[1:])}}

    def explain(self, obs):
        """Expected best-practice kWh/t for this charge, and the kWh/t lost to each cause."""
        row = self._row(obs)
        terms, coef = row["terms"], self.coefficients()
        charge_x = np.array([F.charge_features(obs.charge)])
        core = coef["intercept"] + coef["base"] * terms["base"] + coef["melt_loss"] * terms["melt_loss"]
        best = core + float(self.best_.predict(charge_x)[0])
        waste = {cause: max(coef[cause] * terms[cause], 0.0) for cause in PRACTICE_CAUSES}
        sec = obs.sec_kwh_t
        waste["sand"] = max(sec - best - sum(waste.values()), 0.0)
        predicted = core + sum(coef[c] * terms[c] for c in PRACTICE_CAUSES) + float(self.median_.predict(charge_x)[0])
        return {"sec_kwh_t": sec, "expected_best_kwh_t": best, "predicted_kwh_t": predicted,
                "waste_kwh_t": waste, "measured": row["measured"]}

    def budget_kwh(self, charge, melt_min=55.0):
        """Energy target for a charge before it is melted (the BEE 'kWh integrator' target, per heat)."""
        measured = {"melt_min": melt_min, "underpower_lost_min": 0.0, "overshoot_c": 0.0, "holding_min": 0.0,
                    "lid_avoidable_min": 0.0, "tap_temp_c": charge.spec_temp_c}
        terms, coef = F.physics_terms(charge, measured), self.coefficients()
        best = (coef["intercept"] + coef["base"] * terms["base"] + coef["melt_loss"] * terms["melt_loss"]
                + float(self.best_.predict(np.array([F.charge_features(charge)]))[0]))
        return best * charge.weight_t
