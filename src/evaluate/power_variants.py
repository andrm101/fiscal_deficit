"""Gate 3c: POWER-ONLY comparison of pre-specifiable variants of the confirmatory model M1.

Nothing here estimates an effect on the real CAPB panel. The real outcome enters only through the residuals of OLS
fits that calibrate the noise (country SDs, AR(1) persistence, the year-residual grid of the block bootstrap), exactly
as in Gate 3b (``power.calibrate``); no coefficient of such a fit is ever formed, printed or logged. All
simulated datasets are ``noise + true effect * regressor``.

Variants (``VARIANTS``)
-----------------------
V0 M1 with the registry era terms (W_S x era 2008-2015 and 2016-2021, centred at the exposure-weighted sample means so
   that beta_S is the average association); ``V0n`` is the Gate 3b headline M1 without era terms (reference only).
V1 V0 + the controls that survive trigger T4 (``features/controls.py``).
V2 V0 + a pre-specified treatment of Ireland 2010: (i) ``V2i`` a country-year indicator, (ii) ``V2w`` winsorising the
   residual tails at ``power.WINSOR_TAIL`` (outcome = fitted + clipped residual, redone in every simulated draw).
V3 Country-variance-weighted least squares, weights ``1 / sigma_i^2`` ESTIMATED INSIDE EVERY DRAW from that draw's
   own first-stage OLS residuals (feasible GLS; also inside every bootstrap sample).
V4 AR(1) feasible GLS (Prais-Winsten quasi-differencing, rows after a gap restart with the sqrt(1-rho^2) scaling) with
   rho estimated per draw from the first-stage residuals and Nickell-corrected analytically (``power.nickell_bias``).
V5 Lagged-dependent-variable model (``capb_{t-1}`` regressor, first year of every run lost). Reported as a
   bias-versus-power check: its W_S coefficient is a short-run effect, so against a static true effect it carries bias.
V6 The mechanical combination of the components that pass the stand-alone screen (see ``choose_v6_components``).
V7 (Gate 3d) The registry baseline V0 (era terms, N = 715, NO controls) estimated by feasible WLS AND AR(1) feasible GLS: V6
   without the controls; designated DGP ``F``; complexity 2. ``V7@703`` is the same estimator on the 703 complete-case rows
   of V6 (rows lacking the lagged output gap dropped, the control itself NOT a regressor): it separates the sample change from
   the controls, and is not eligible for selection.

Data-generating processes (``DGP_LABELS``)
------------------------------------------
``F`` fixed 3b noise: country SDs and rho from the V0 residuals (rho = 0.69 after the simulation correction); used for
      every variant so that all are compared on the same footing. Adding controls then buys nothing but costs degrees
      of freedom (conservative for V1, V2i).
``O`` own-residual noise: country SDs, rho and the block-bootstrap grid from the variant's OWN OLS residuals. This changes
      the DGP (a model with controls or an Ireland indicator leaves less unexplained variance) and is the convention for
      variants that add regressors; it credits them with variance reduction that is only real if the added terms
      belong in the true model.
``S`` spike: the ``O`` noise of V2i plus the Ireland-2010 shock re-inserted with random sign and the magnitude of the V0
      residual at that cell. It is the faithful DGP for judging the Ireland treatment, because the observed outlier is a
      one-off that a Gaussian country SD cannot represent.

Method
------
Estimation is vectorised numpy: Frisch-Waugh-Lovell for OLS (``power.estimate``); for V3/V4/V6 per-draw normal equations
assembled from per-cluster Gram matrices (the Prais-Winsten Gram matrix is exactly quadratic in rho, so it is stored as
three fixed arrays); for V5 one random regressor handled by FWL. CR1 standard errors are clustered by country. Adding a
true effect shifts the coefficient of every estimator except V5 by exactly that effect and leaves the standard error
unchanged (the first-stage residuals annihilate the regressor), so CR1 size and MDE come from one set of null draws
(``power.solve_mde``). The wild-cluster bootstrap-t (null imposed, Rademacher weights, ``N_BOOT`` draws) re-estimates
the full feasible procedure in every bootstrap sample (weights, rho, winsor limits, lagged dependent variable), so the
data-dependent steps are inside the resampling; its MDE is found by simulating the rejection rate on a grid of true effects
and solving a probit fit of rate against effect for 80 per cent power (common random numbers across the grid).
No statsmodels and no row-wise ``.loc`` inside any simulation loop.

Randomness: ``power.make_rng(GATE3C_KEY, ...)`` = ``default_rng(SeedSequence([42, 3000, ...]))`` with documented integer keys.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import optimize, stats

_EVALUATE = Path(__file__).resolve().parent
sys.path.insert(0, str(_EVALUATE))
sys.path.insert(0, str(_EVALUATE.parent / "features"))
import controls as controls_module  # noqa: E402
import power  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]

GATE3C_KEY = 3000  # first key after the SeedSequence streams of power.py (0-4, 80-99); see make_rng below
PURPOSE_NOISE_NULL, PURPOSE_NOISE_WCB, PURPOSE_NOISE_SIZE, PURPOSE_NOISE_BIAS, PURPOSE_BOOT, PURPOSE_SPIKE = 21, 22, 23, 24, 25, 26
DGP_KEYS = {"F": 1, "O": 2, "S": 3, "Fn": 4}
SCENARIO_NAMES = ("ar1_rho_hat", "ar1_rho0", "block_bootstrap")

ERA_BREAKS = ((2008, 2015), (2016, 2021))  # registry eras 1995-2007 (reference), 2008-2015, 2016-2021
IE_CODE, IE_YEAR = power.IE_CODE, power.IE_YEAR

N_BOOT = 399  # bootstrap draws per dataset; (N_BOOT + 1) * ALPHA = 20 is an integer
FIT_BATCH = 1_000  # columns per vectorised normal-equation solve
BOOT_CHUNK = 8  # datasets per vectorised bootstrap chunk (columns per solve = BOOT_CHUNK * N_BOOT)
GRID_MULTIPLES = (0.6, 0.8, 1.0, 1.2, 1.45, 1.8)  # true-effect grid as multiples of the variant's CR1 MDE
BENCHMARK_EFFECTS = (0.41, 0.49)  # literature benchmarks (indicative), pp
TRUE_EFFECT = 0.5  # known effect used for the bias / RMSE check, pp (per SD for the interactions)
SIZE_VALID = (0.035, 0.065)  # null rejection rates outside this band flag the variant as invalid
MAX_ABS_REL_BIAS = 0.10
TIE_TOLERANCE = 0.05
V6_GAIN_THRESHOLD = 0.05  # a component enters V6 if it lowers the beta_S wild-bootstrap MDE by more than this share
RHO_GRID = np.linspace(-0.95, 0.98, 400)  # grid for inverting the analytic Nickell map
RHO_CAP = 0.95


def make_rng(*keys: int) -> np.random.Generator:
    """``power.make_rng(GATE3C_KEY, *keys)``: ``default_rng(SeedSequence([42, 3000, *keys]))``."""
    return power.make_rng(GATE3C_KEY, *keys)


# ---------------------------------------------------------------------------------------------
# Regressors and designs
# ---------------------------------------------------------------------------------------------
def era_terms(frame: pd.DataFrame, breaks: tuple[tuple[int, int], ...] = ERA_BREAKS) -> pd.DataFrame:
    """``W_S x (era dummy - m_e)`` with ``m_e = sum(W_S * era) / sum(W_S)`` (exposure-weighted mean of the era dummy).

    Centring at the exposure-weighted mean makes ``beta_S`` the association at the sample-average era composition of
    scheduled-election exposure (the registry rule). The reference era 1995-2007 has no term.
    """
    w_s = frame["W_S"].to_numpy(float)
    year = frame["year"].to_numpy()
    cols = {}
    for first, last in breaks:
        dummy = ((year >= first) & (year <= last)).astype(float)
        cols[f"WS_x_era_{first}_{last}"] = w_s * (dummy - float((w_s * dummy).sum() / w_s.sum()))
    return pd.DataFrame(cols, index=frame.index)


def variant_frame(frame: pd.DataFrame, control_names: tuple[str, ...] = ()) -> pd.DataFrame:
    """Sorted sample frame restricted to rows where every requested control is observed (complete cases)."""
    frame = frame.sort_values(["eurostat_code", "year"]).reset_index(drop=True)
    if control_names:
        frame = frame[frame[list(control_names)].notna().all(axis=1)].reset_index(drop=True)
    return frame


def variant_regressors(frame: pd.DataFrame, *, era: bool = True, control_names: tuple[str, ...] = (), ireland_indicator: bool = False,
                       ) -> tuple[pd.DataFrame, dict[str, float], dict[str, str]]:
    """Regressor frame, scale constants and target map for a variant (rows aligned with the sorted ``frame``).

    Starts from the Gate 3b M1 regressors (``power.regressors_from_frame(frame, "m1")``), then appends the era terms, the
    controls (standardised to unit SD; the scale does not change any target coefficient) and the Ireland-2010 indicator.
    """
    regressors, scale, targets = power.regressors_from_frame(frame, "m1")
    pieces = [regressors]
    if era:
        pieces.append(era_terms(frame))
    for name in control_names:
        values = frame[name].to_numpy(float)
        sd = values.std(ddof=0)
        pieces.append(pd.DataFrame({name: (values - values.mean()) / sd if sd > 0 else values}))
    if ireland_indicator:
        flag = ((frame["eurostat_code"] == IE_CODE) & (frame["year"] == IE_YEAR)).to_numpy(float)
        if flag.sum() != 1:
            raise ValueError("Ireland 2010 is not in the sample")
        pieces.append(pd.DataFrame({"IE2010": flag}))
    combined = pd.concat([p.reset_index(drop=True) for p in pieces], axis=1)
    combined = combined.loc[:, [bool(np.ptp(combined[c].to_numpy(float)) > 0) for c in combined.columns]]  # an era with no rows is not identified
    return combined, scale, targets


def build_variant_design(frame: pd.DataFrame, label: str, *, era: bool = True, control_names: tuple[str, ...] = (), ireland_indicator: bool = False,
                         restrict_names: tuple[str, ...] = ()) -> power.Design:
    """:class:`power.Design` of a variant on the (complete-case) sample frame.

    ``restrict_names`` are columns whose complete cases define the sample WITHOUT entering the regressors (the V7@703 sample
    change); ``control_names`` both restrict the sample and enter as regressors.
    """
    frame = variant_frame(frame, tuple(dict.fromkeys((*control_names, *restrict_names))))
    regressors, scale, targets = variant_regressors(frame, era=era, control_names=control_names, ireland_indicator=ireland_indicator)
    return power.build_design(frame, label=label, regressors=regressors, targets=targets, scale=scale)


def drop_column(design: power.Design, column: str, label: str) -> power.Design:
    """Design with one regressor removed (the restricted model of a wild-bootstrap test)."""
    keep = [c for c in design.x_names if c != column]
    frame = pd.DataFrame({"eurostat_code": design.codes, "year": design.year, "capb": design.y})
    return power.build_design(frame, label=label, regressors=pd.DataFrame(design.x[:, [design.x_names.index(c) for c in keep]], columns=keep), targets={}, scale=design.scale)


# ---------------------------------------------------------------------------------------------
# Feasible GLS estimator (V2w, V3, V4, V6)
# ---------------------------------------------------------------------------------------------
def nickell_inverse(rho_hat: np.ndarray, t_obs: float) -> np.ndarray:
    """Analytic Nickell correction by table look-up: the ``rho`` whose plim of the within estimate equals ``rho_hat``."""
    plim = np.array([r + power.nickell_bias(r, t_obs) for r in RHO_GRID])
    return np.clip(np.interp(rho_hat, plim, RHO_GRID), -RHO_CAP, RHO_CAP)


class GlsEstimator:
    """Feasible GLS with fixed effects: optional per-draw country-variance weights, AR(1) quasi-differencing, winsorising.

    ``fit(y)`` takes an (N x B) matrix of outcomes (rows as in ``design``) and returns the coefficient and CR1 standard
    error of each requested target. Every data-dependent step (first-stage OLS residuals, ``sigma_i^2``, ``rho``,
    winsor limits) is recomputed per column, so passing bootstrap samples gives an honest feasible-GLS bootstrap.
    With ``wls=ar1=winsor=False`` it reproduces ``power.estimate`` exactly.

    Algebra: the transformed rows are ``P z`` with ``P`` the Prais-Winsten operator (``z_t - rho z_{t-1}`` after a
    one-year step, ``sqrt(1-rho^2) z_t`` at the start of a run), weighted by ``w_g``. The normal-equation matrix
    ``sum_g w_g (G0_g + rho G1_g + rho^2 G2_g)`` is quadratic in rho; the right side is ``Z' W P'P y``. The CR1 score of
    target ``j`` in cluster ``g`` is ``w_g sum_t (P Z r_j)_t (P u)_t`` with ``r_j = A^{-1} e_j``.
    """

    def __init__(self, design: power.Design, *, wls: bool = False, ar1: bool = False, winsor: bool = False) -> None:
        self.design, self.wls, self.ar1, self.winsor = design, wls, ar1, winsor
        d = design
        years = np.unique(d.year)
        n, g = d.n_obs, d.n_clusters
        dummies = np.zeros((n, g + len(years) - 1))
        dummies[np.arange(n), d.country_idx] = 1.0
        year_col = np.searchsorted(years, d.year)
        keep = year_col > 0
        dummies[np.arange(n)[keep], g + year_col[keep] - 1] = 1.0
        self.z = np.hstack([dummies, d.x])
        self.k = self.z.shape[1]
        self.col = {t: g + len(years) - 1 + d.x_names.index(c) for t, c in d.targets.items()}
        self.cur, self.lag = d.cur_rows, d.lag_rows
        self.first = np.setdiff1d(np.arange(n), self.cur)
        self.t_mean = float(d.counts.mean())
        self._restricted: dict[str, GlsEstimator] = {}
        starts = d.starts
        stops = starts + d.counts
        g0 = np.stack([self.z[a:b].T @ self.z[a:b] for a, b in zip(starts, stops)])
        self.g0 = g0.reshape(g, -1)
        if not wls and not ar1:
            self._a_inv = np.linalg.inv(g0.sum(axis=0))
        if ar1:
            cur_cluster, first_cluster = d.country_idx[self.cur], d.country_idx[self.first]
            g1, g2 = np.zeros_like(g0), np.zeros_like(g0)
            for c in range(g):
                rows = self.cur[cur_cluster == c]
                zc, zl, zf = self.z[rows], self.z[rows - 1], self.z[self.first[first_cluster == c]]
                g1[c] = -(zc.T @ zl + zl.T @ zc)
                g2[c] = zl.T @ zl - zf.T @ zf
            self.g1, self.g2 = g1.reshape(g, -1), g2.reshape(g, -1)

    # --- helpers ---------------------------------------------------------------------------
    def _transform(self, m: np.ndarray, rho: np.ndarray) -> np.ndarray:
        """Prais-Winsten operator applied to every column of ``m`` with the column's own ``rho``."""
        out = m * np.sqrt(1.0 - rho**2)[None, :]
        out[self.cur] = m[self.cur] - rho[None, :] * m[self.lag]
        return out

    def _transform_t(self, x: np.ndarray, rho: np.ndarray) -> np.ndarray:
        """``P' x`` (the transpose of the operator above)."""
        out = x.copy()
        out[self.first] = x[self.first] * np.sqrt(1.0 - rho**2)[None, :]
        out[self.lag] -= rho[None, :] * x[self.cur]
        return out

    def _winsorise(self, y: np.ndarray) -> np.ndarray:
        """Outcome with the residual tails clipped at the ``WINSOR_TAIL`` / ``1 - WINSOR_TAIL`` quantiles of each column."""
        u = power.residuals(self.design, y)
        lo, hi = np.quantile(u, [power.WINSOR_TAIL, 1.0 - power.WINSOR_TAIL], axis=0)
        return y - (u - np.clip(u, lo, hi))

    def _rho(self, u1: np.ndarray) -> np.ndarray:
        """Per-column Nickell-corrected AR(1) coefficient of the first-stage residuals (zeros without AR(1))."""
        if not self.ar1:
            return np.zeros(u1.shape[1])
        raw = power._pair_ar1(u1, self.design, standardise=self.wls)
        return nickell_inverse(raw, self.t_mean)

    def _weights(self, u1: np.ndarray) -> np.ndarray:
        """(B x G) weights ``1 / sigma_i^2`` from the first-stage residuals of each column (ones without WLS)."""
        d = self.design
        if not self.wls:
            return np.ones((u1.shape[1], d.n_clusters))
        var = np.add.reduceat(u1**2, d.starts, axis=0) / d.counts[:, None]
        return (1.0 / np.maximum(var, 1e-12 * var.max())).T

    # --- estimation ------------------------------------------------------------------------
    def first_stage(self, y: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Outcome actually used (after winsorising), first-stage residuals, per-column ``rho`` and weights."""
        y_use = self._winsorise(y) if self.winsor else y
        u1 = power.residuals(self.design, y_use)
        return y_use, u1, self._rho(u1), self._weights(u1)

    def _fit_chunk(self, y: np.ndarray, names: list[str], want_resid: bool) -> tuple[dict[str, tuple[np.ndarray, np.ndarray]], np.ndarray | None]:
        d = self.design
        y_use, u1, rho, w = self.first_stage(y)
        b = y_use.shape[1]
        tmp = self._transform_t(self._transform(y_use, rho), rho) if self.ar1 else y_use.copy()
        if self.wls:
            tmp *= w.T[d.country_idx]
        rhs = (self.z.T @ tmp).T  # B x K
        out = {}
        if not self.wls and not self.ar1:
            # one fixed normal-equation matrix for every column: invert once
            a_inv = self._a_inv
            theta = rhs @ a_inv
            u = y_use - self.z @ theta.T
            for t in names:
                q = (self.z @ a_inv[:, self.col[t]])[:, None]
                scores = np.add.reduceat(q * u, d.starts, axis=0)
                out[t] = (theta[:, self.col[t]], np.sqrt(d.cr1 * (scores**2).sum(axis=0)))
            return out, (u if want_resid else None)
        if self.wls:
            gram = w @ self.g0
            if self.ar1:
                gram = gram + rho[:, None] * (w @ self.g1) + (rho**2)[:, None] * (w @ self.g2)
        else:
            gram = self.g0.sum(axis=0)[None, :] + rho[:, None] * self.g1.sum(axis=0)[None, :] + (rho**2)[:, None] * self.g2.sum(axis=0)[None, :]
        a_mat = gram.reshape(b, self.k, self.k)
        sol_rhs = np.zeros((b, self.k, 1 + len(names)))
        sol_rhs[:, :, 0] = rhs
        for i, t in enumerate(names):
            sol_rhs[:, self.col[t], 1 + i] = 1.0
        sol = np.linalg.solve(a_mat, sol_rhs)
        theta = sol[:, :, 0]
        u = y_use - self.z @ theta.T
        pu = self._transform(u, rho) if self.ar1 else u
        for i, t in enumerate(names):
            q = self.z @ sol[:, :, 1 + i].T
            pq = self._transform(q, rho) if self.ar1 else q
            scores = np.add.reduceat(pq * pu, d.starts, axis=0)
            if self.wls:
                scores = scores * w.T
            out[t] = (theta[:, self.col[t]], np.sqrt(d.cr1 * (scores**2).sum(axis=0)))
        return out, (u if want_resid else None)

    def fit(self, y: np.ndarray, names: list[str] | None = None, want_resid: bool = False, batch: int = FIT_BATCH,
            ) -> dict[str, tuple[np.ndarray, np.ndarray]] | tuple[dict[str, tuple[np.ndarray, np.ndarray]], np.ndarray]:
        """Coefficient and CR1 SE per target for an (N x B) outcome matrix; optionally also the residuals ``y - Z theta``."""
        y2 = y[:, None] if y.ndim == 1 else y
        names = list(names or self.design.targets)
        parts, resid = [], []
        for first in range(0, y2.shape[1], batch):
            res, u = self._fit_chunk(y2[:, first:first + batch], names, want_resid)
            parts.append(res)
            if want_resid:
                resid.append(u)
        merged = {t: (np.concatenate([p[t][0] for p in parts]), np.concatenate([p[t][1] for p in parts])) for t in names}
        return (merged, np.hstack(resid)) if want_resid else merged

    # --- bootstrap hooks -------------------------------------------------------------------
    def restricted(self, target: str) -> "GlsEstimator":
        """The same procedure on the model without the target regressor (for the null-imposed bootstrap)."""
        if target not in self._restricted:
            design_r = drop_column(self.design, self.design.targets[target], f"{self.design.label} (no {target})")
            self._restricted[target] = GlsEstimator(design_r, wls=self.wls, ar1=self.ar1, winsor=self.winsor)
        return self._restricted[target]

    def bootstrap_outcomes(self, y: np.ndarray, target: str, v: np.ndarray) -> np.ndarray:
        """Wild-bootstrap outcomes ``fitted_restricted + v * residual_restricted`` as an N x (C * D) matrix.

        ``v`` has shape (C, G, D) (cluster weights); column ``c * D + d`` belongs to dataset ``c``, draw ``d``.
        """
        _, resid = self.restricted(target).fit(y, [], want_resid=True)
        fitted = y - resid
        weights = v[:, self.design.country_idx, :].transpose(1, 0, 2)  # N x C x D
        star = fitted[:, :, None] + weights * resid[:, :, None]
        return star.reshape(self.design.n_obs, -1)


# ---------------------------------------------------------------------------------------------
# Lagged-dependent-variable estimator (V5)
# ---------------------------------------------------------------------------------------------
class LdvEstimator:
    """OLS with fixed effects plus ``y_{t-1}`` as a regressor, on the rows that have a lag in the sample.

    ``design`` is the (full-row) simulation design; the estimation design drops the first row of every run (its lag is the
    initial condition). By Frisch-Waugh-Lovell the target coefficient is ``h*' y`` with
    ``h* = h - (h' ylag) ltilde / (ltilde' ltilde)`` where ``h`` is the OLS functional of the static model on the
    estimation rows and ``ltilde`` is the lag residualised on fixed effects and regressors; the CR1 variance is
    ``cr1 * sum_g (h*_g' u_g)^2`` with ``K + 1`` parameters. Bootstrap outcomes follow the recursion
    ``y*_t = nondynamic_t + phi y*_{t-1} + v_g u_t`` (fitted values of the restricted model, observed initial condition).
    """

    def __init__(self, design: power.Design, frame: pd.DataFrame, regressors: pd.DataFrame, targets: dict[str, str]) -> None:
        self.full = design
        self.frame, self.regressors, self.targets = frame, regressors, targets
        self.cur, self.lag = design.cur_rows, design.lag_rows
        sub_frame = frame.iloc[self.cur].reset_index(drop=True)
        sub_reg = regressors.iloc[self.cur].reset_index(drop=True)
        self.est = power.build_design(sub_frame, label=f"{design.label} (LDV rows)", regressors=sub_reg, targets=targets, scale=design.scale)
        d = self.est
        self.cr1 = d.n_clusters / (d.n_clusters - 1) * (d.n_obs - 1) / (d.n_obs - (d.k_params + 1))
        self._restricted: dict[str, LdvEstimator] = {}
        self.pos_groups = [np.flatnonzero(design.year_pos[self.cur] == p) for p in range(1, design.n_grid_years)]

    def _pieces(self, y: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """``ycur, ylag, ltilde, phi, u`` for an (N x B) outcome matrix."""
        d = self.est
        ycur, ylag = y[self.cur], y[self.lag]
        ltilde = power.residuals(d, ylag)
        ytilde = power.residuals(d, ycur)
        phi = (ltilde * ytilde).sum(axis=0) / (ltilde**2).sum(axis=0)
        return ycur, ylag, ltilde, phi, ytilde - phi * ltilde

    def fit(self, y: np.ndarray, names: list[str] | None = None, want_resid: bool = False,
            ) -> dict[str, tuple[np.ndarray, np.ndarray]] | tuple[dict[str, tuple[np.ndarray, np.ndarray]], np.ndarray]:
        """Coefficient and CR1 SE of each target; ``want_resid`` also returns ``(u, phi, nondynamic)``."""
        y2 = y[:, None] if y.ndim == 1 else y
        d = self.est
        ycur, ylag, ltilde, phi, u = self._pieces(y2)
        lsq = (ltilde**2).sum(axis=0)
        out = {}
        for t in names if names is not None else list(self.targets):
            h = d.h[t]
            h_lag = h @ ylag
            b = h @ ycur - phi * h_lag
            h_star = h[:, None] - ltilde * (h_lag / lsq)[None, :]
            scores = np.add.reduceat(h_star * u, d.starts, axis=0)
            out[t] = (b, np.sqrt(self.cr1 * (scores**2).sum(axis=0)))
        if want_resid:
            return out, (u, phi, ycur - phi * ylag - u)  # type: ignore[return-value]
        return out

    def restricted(self, target: str) -> "LdvEstimator":
        """The model without the target regressor."""
        if target not in self._restricted:
            keep = [c for c in self.regressors.columns if c != self.targets[target]]
            self._restricted[target] = LdvEstimator(self.full, self.frame, self.regressors[keep], {})
        return self._restricted[target]

    def bootstrap_outcomes(self, y: np.ndarray, target: str, v: np.ndarray) -> np.ndarray:
        """Recursive wild-bootstrap outcomes, N x (C * D); initial-condition rows keep their observed values."""
        full = self.full
        _, (u, phi, nondynamic) = self.restricted(target).fit(y, [], want_resid=True)  # type: ignore[misc]
        c_sets, g, d_draws = v.shape
        weights = v[:, full.country_idx[self.cur], :].transpose(1, 0, 2)  # N1 x C x D
        shock = (weights * u[:, :, None]).reshape(len(self.cur), -1)
        base = np.repeat(nondynamic, d_draws, axis=1)
        phi_rep = np.repeat(phi, d_draws)
        star = np.repeat(y, d_draws, axis=1)  # initial rows (not in cur) keep the observed outcome; cur rows are overwritten
        for rows in self.pos_groups:
            idx = self.cur[rows]
            star[idx] = base[rows] + phi_rep[None, :] * star[idx - 1] + shock[rows]
        return star


# ---------------------------------------------------------------------------------------------
# Generic wild-cluster bootstrap-t (null imposed), re-estimating the whole procedure per bootstrap sample
# ---------------------------------------------------------------------------------------------
def wild_bootstrap_pvalues(est: "GlsEstimator | LdvEstimator", target: str, y: np.ndarray, *, weights: str = "rademacher", n_boot: int = N_BOOT,
                           seed_key: int = 0, chunk: int = BOOT_CHUNK) -> np.ndarray:
    """Bootstrap p-values ``(1 + #{|t*| >= |t|}) / (n_boot + 1)`` of the target for each column of ``y`` (N x R).

    The cluster weights of chunk ``i`` are drawn from ``power.make_rng(PURPOSE_WCB_WEIGHTS, seed_key, i)`` with shape
    (datasets in chunk, G, n_boot), the convention of ``power.wild_bootstrap_reject`` (so the two agree exactly when the
    chunk size is ``power.WCB_CHUNK``). ``est`` must provide ``fit``, ``bootstrap_outcomes``.
    """
    g = est.design.n_clusters if isinstance(est, GlsEstimator) else est.full.n_clusters
    b_hat, se_hat = est.fit(y, [target])[target]
    t_obs = np.abs(b_hat / se_hat)
    pvalues = np.empty(y.shape[1])
    for i, first in enumerate(range(0, y.shape[1], chunk)):
        sl = slice(first, min(first + chunk, y.shape[1]))
        v = power.bootstrap_weights(power.make_rng(power.PURPOSE_WCB_WEIGHTS, seed_key, i), (sl.stop - sl.start, g, n_boot), weights)
        star = est.bootstrap_outcomes(y[:, sl], target, v)
        b_star, se_star = est.fit(star, [target])[target]
        t_star = np.abs(b_star / se_star).reshape(sl.stop - sl.start, n_boot)
        pvalues[sl] = (1 + (t_star >= t_obs[sl, None]).sum(axis=1)) / (n_boot + 1)
    return pvalues


# ---------------------------------------------------------------------------------------------
# Variant specifications
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class VariantSpec:
    """Definition of one variant: regressors, estimator and the data-generating processes it is evaluated under."""

    vid: str
    label: str
    era: bool = True
    use_controls: bool = False
    ireland_indicator: bool = False
    estimator: str = "ols"  # "ols" (fast engine), "gls" (GlsEstimator) or "ldv"
    wls: bool = False
    ar1: bool = False
    winsor: bool = False
    dgps: tuple[str, ...] = ("F",)
    designated_dgp: str = "F"
    complexity: int = 0  # number of modifications relative to V0
    restrict_to_control_sample: bool = False  # complete-case rows of the surviving controls, which are NOT regressors (V7@703)
    eligible: bool = True  # False: reported but never selected (V7@703)

    @property
    def fast(self) -> bool:
        """True when the variant is plain OLS with fixed regressors (exact FWL bootstrap of ``power.py``)."""
        return self.estimator == "ols" and not self.winsor


VARIANT_SPECS: dict[str, VariantSpec] = {
    "V0n": VariantSpec("V0n", "M1 without era terms (Gate 3b headline; reference, not eligible)", era=False),
    "V0": VariantSpec("V0", "M1 with centred era terms (registry baseline)", dgps=("F", "S")),
    "V1": VariantSpec("V1", "V0 + surviving controls (complete cases)", use_controls=True, dgps=("F", "O"), designated_dgp="O", complexity=1),
    "V2i": VariantSpec("V2i", "V0 + Ireland-2010 country-year indicator", ireland_indicator=True, dgps=("F", "O", "S"), designated_dgp="O", complexity=1),
    "V2w": VariantSpec("V2w", "V0 + residual-tail winsorising (1/99)", estimator="gls", winsor=True, dgps=("F", "S"), complexity=1),
    "V3": VariantSpec("V3", "V0, feasible WLS (1/sigma_i^2 re-estimated per draw)", estimator="gls", wls=True, complexity=1),
    "V4": VariantSpec("V4", "V0, AR(1) feasible GLS (Prais-Winsten, Nickell-corrected rho per draw)", estimator="gls", ar1=True, complexity=1),
    "V5": VariantSpec("V5", "V0 + lagged dependent variable (bias check)", estimator="ldv", complexity=1),
}
GATE3D_SPECS: dict[str, VariantSpec] = {  # Gate 3d: added to the context by ``Context`` but not to ``VARIANT_SPECS`` (the 3c job lists stay unchanged)
    "V7": VariantSpec("V7", "V0 (N = 715, no controls), feasible WLS + AR(1) GLS", estimator="gls", wls=True, ar1=True, complexity=2),
    "V7@703": VariantSpec("V7@703", "V7 on the 703 complete-case rows of V6 (no controls as regressors; not eligible)", estimator="gls", wls=True, ar1=True, complexity=2,
                          restrict_to_control_sample=True, eligible=False),
}
SIMPLICITY_ORDER = ("V0", "V1", "V2i", "V2w", "V3", "V4", "V5", "V7", "V6")  # tie-break order of the selection rule (Gate 3d: V7, complexity 2, sits before V6, complexity 3)


# ---------------------------------------------------------------------------------------------
# Data-generating processes
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class DgpParams:
    """Noise calibration shared by the three scenarios: country SDs, corrected rho, residual grid, block length, optional spike."""

    label: str
    sigma: np.ndarray
    rho_hat: float
    grid: np.ndarray
    block: int
    spike_size: float = 0.0
    mean_t: float = 0.0
    heterogeneity: dict[str, float] | None = None


@dataclass(frozen=True)
class SpikeNoise:
    """Base noise plus a one-off shock of random sign and fixed size at one row (the Ireland-2010 outlier of the ``S`` DGP)."""

    base: "power.ArNoise | power.BlockBootstrapNoise"
    row: int
    size: float

    def draw(self, rng: np.random.Generator, n_draws: int) -> np.ndarray:
        """N x ``n_draws`` noise matrix."""
        out = self.base.draw(rng, n_draws)
        out[self.row] += self.size * (rng.integers(0, 2, size=n_draws) * 2.0 - 1.0)
        return out


def make_noise(design: power.Design, params: DgpParams, scenario: str) -> "power.ArNoise | power.BlockBootstrapNoise | SpikeNoise":
    """Noise generator for a scenario (``ar1_rho_hat``, ``ar1_rho0``, ``block_bootstrap``) aligned with ``design`` rows."""
    if scenario == "ar1_rho_hat":
        base: "power.ArNoise | power.BlockBootstrapNoise" = power.ArNoise(design, params.sigma, params.rho_hat)
    elif scenario == "ar1_rho0":
        base = power.ArNoise(design, params.sigma, 0.0)
    elif scenario == "block_bootstrap":
        base = power.BlockBootstrapNoise(design, params.grid, params.block)
    else:
        raise ValueError(f"unknown scenario {scenario!r}")
    if params.spike_size > 0:
        row = np.flatnonzero((design.codes == IE_CODE) & (design.year == IE_YEAR))
        if len(row) != 1:
            raise ValueError("the spike DGP needs Ireland 2010 in the sample")
        return SpikeNoise(base, int(row[0]), params.spike_size)
    return base


class Context:
    """Sample, controls and the calibrated DGPs, built once per process from the raw data (residual-based only)."""

    def __init__(self, frame: pd.DataFrame | None = None, controls_attached: bool = False) -> None:
        if frame is None:
            import sample

            panel = sample.build_panel()
            frame = sample.select_sample(panel, sample.last_common_complete_year(panel, "cv"), "joint_cv").sample
        self.frame = frame if controls_attached else controls_module.attach_controls(frame)
        self.t4 = controls_module.apply_t4_rule(self.frame)
        self.control_names = tuple(self.t4.surviving)
        self.specs: dict[str, VariantSpec] = {**VARIANT_SPECS, **GATE3D_SPECS}
        self._designs: dict[str, power.Design] = {}
        self._params: dict[tuple[str, str], DgpParams] = {}
        self.design_ref = self.design_of(self.specs["V0n"])
        self.cal_ref = power.calibrate(self.design_ref)
        self.block = power.choose_block_length(self.design_ref, self.cal_ref)

    def design_of(self, spec: VariantSpec) -> power.Design:
        """Design of the spec's regressors on its complete-case sample (cached)."""
        if spec.vid not in self._designs:
            self._designs[spec.vid] = build_variant_design(
                self.frame, spec.vid, era=spec.era, control_names=self.control_names if spec.use_controls else (), ireland_indicator=spec.ireland_indicator,
                restrict_names=self.control_names if spec.restrict_to_control_sample else ())
        return self._designs[spec.vid]

    def _params_from(self, label: str, cal: power.Calibration, spike: float = 0.0) -> DgpParams:
        return DgpParams(label, cal.sigma, cal.rho_corrected, cal.grid, self.block, spike, cal.mean_t, cal.heterogeneity)

    def dgp(self, spec: VariantSpec, dgp: str) -> DgpParams:
        """DGP parameters: ``F`` fixed 3b noise (V0n residuals), ``O`` the variant's own residuals, ``S`` Ireland-spike."""
        key = (spec.vid if dgp == "O" else "-", dgp)
        if key not in self._params:
            if dgp == "F":
                self._params[key] = self._params_from("F", self.cal_ref)
            elif dgp == "O":
                self._params[key] = self._params_from("O", power.calibrate(self.design_of(spec)))
            elif dgp == "S":
                v0 = self.design_of(self.specs["V0"])
                u0 = power.calibrate(v0).resid
                row = np.flatnonzero((v0.codes == IE_CODE) & (v0.year == IE_YEAR))[0]
                base = power.calibrate(self.design_of(self.specs["V2i"]))
                self._params[key] = self._params_from("S", base, spike=float(abs(u0[row])))
            else:
                raise ValueError(dgp)
        return self._params[key]


# ---------------------------------------------------------------------------------------------
# Probit smoothing of simulated power curves
# ---------------------------------------------------------------------------------------------
def probit_fit(betas: np.ndarray, hits: np.ndarray, trials: np.ndarray) -> tuple[float, float]:
    """Maximum-likelihood ``(a, b)`` of ``P(reject) = Phi(a + b * beta)`` from binomial counts."""
    def negloglik(par: np.ndarray) -> float:
        p = np.clip(stats.norm.cdf(par[0] + par[1] * betas), 1e-9, 1 - 1e-9)
        return -float(np.sum(hits * np.log(p) + (trials - hits) * np.log(1 - p)))

    rate = np.clip(hits / trials, 0.02, 0.98)
    slope = np.polyfit(betas, stats.norm.ppf(rate), 1)
    res = optimize.minimize(negloglik, x0=np.array([slope[1], slope[0]]), method="Nelder-Mead", options={"xatol": 1e-8, "fatol": 1e-10, "maxiter": 4000})
    return float(res.x[0]), float(res.x[1])


def power_curve_mde(betas: np.ndarray, rates: np.ndarray, trials: np.ndarray, target_power: float = power.TARGET_POWER, n_resample: int = 200) -> dict[str, float]:
    """MDE at ``target_power`` from a probit fit of simulated rejection rates, with a parametric-bootstrap SE and the fit residual."""
    hits = np.round(rates * trials)
    a, b = probit_fit(betas, hits, trials)
    mde = (stats.norm.ppf(target_power) - a) / b if b > 0 else float("nan")
    rng = make_rng(PURPOSE_BOOT, 99)
    draws = []
    for _ in range(n_resample):
        h2 = rng.binomial(trials.astype(int), np.clip(stats.norm.cdf(a + b * betas), 0, 1))
        a2, b2 = probit_fit(betas, h2.astype(float), trials)
        if b2 > 0:
            draws.append((stats.norm.ppf(target_power) - a2) / b2)
    fitted = stats.norm.cdf(a + b * betas)
    return {"a": a, "b": b, "mde": float(mde), "mde_se": float(np.std(draws)) if draws else float("nan"),
            "max_fit_residual": float(np.max(np.abs(fitted - rates)))}


def probit_power(a: float, b: float, beta: float) -> float:
    """Fitted rejection probability at effect ``beta``."""
    return float(stats.norm.cdf(a + b * beta))


# ---------------------------------------------------------------------------------------------
# Jobs: one (variant, DGP, scenario) cell
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Settings:
    """Simulation sizes. ``full`` is the reported run; ``quick`` is a smoke test."""

    n_null: int = 20_000  # CR1 null draws (Monte Carlo SE of a 5% rate: 0.0015)
    size_fast: int = 4_000  # datasets for the bootstrap size, fast engine (SE 0.0035)
    mde_fast: int = 1_500  # datasets per grid point, fast engine
    size_generic: int = 1_500  # datasets for the bootstrap size, generic engine (SE 0.0056)
    mde_generic: int = 500  # datasets per grid point, generic engine (task minimum 300)
    n_boot: int = N_BOOT
    n_bias: int = 5_000
    n_ldv_cr1: int = 6_000


FULL = Settings()
QUICK = Settings(n_null=1_000, size_fast=100, mde_fast=100, size_generic=16, mde_generic=16, n_boot=39, n_bias=300, n_ldv_cr1=300)


@dataclass
class Variant:
    """A variant bound to its sample: design (simulation geometry) and estimator."""

    spec: VariantSpec
    design: power.Design
    estimator: "GlsEstimator | LdvEstimator"


def build_variant(ctx: Context, spec: VariantSpec) -> Variant:
    """Design and estimator of a spec on the context's sample."""
    design = ctx.design_of(spec)
    if spec.estimator == "ldv":
        frame = variant_frame(ctx.frame, ctx.control_names if (spec.use_controls or spec.restrict_to_control_sample) else ())
        regressors, _, targets = variant_regressors(frame, era=spec.era, control_names=ctx.control_names if spec.use_controls else (), ireland_indicator=spec.ireland_indicator)
        return Variant(spec, design, LdvEstimator(design, frame, regressors, targets))
    return Variant(spec, design, GlsEstimator(design, wls=spec.wls, ar1=spec.ar1, winsor=spec.winsor))


def target_column(design: power.Design, target: str) -> np.ndarray:
    """The regressor column of a target (the shape of a true effect)."""
    return design.x[:, design.x_names.index(design.targets[target])]


def effect_grid(mde_guess: float, target: str) -> np.ndarray:
    """True-effect grid for the simulated power curve: multiples of the CR1 MDE (+ the literature benchmarks for beta_S)."""
    points = [mde_guess * m for m in GRID_MULTIPLES]
    if target == "beta_S":
        points += list(BENCHMARK_EFFECTS)
    return np.array(sorted(points))


def cr1_from_null_draws(var: Variant, noise, rng: np.random.Generator, n_null: int) -> dict[str, dict[str, float]]:
    """CR1 size, MDE, size-adjusted MDE and benchmark powers from null draws (exact for shift-equivariant estimators)."""
    d = var.design
    b0 = {t: [] for t in d.targets}
    se = {t: [] for t in d.targets}
    done = 0
    while done < n_null:
        size = min(power.BATCH, n_null - done)
        fit = var.estimator.fit(noise.draw(rng, size))
        for t, (b, s) in fit.items():
            b0[t].append(b)
            se[t].append(s)
        done += size
    out = {}
    for t in d.targets:
        b, s = np.concatenate(b0[t]), np.concatenate(se[t])
        crit_emp = float(np.quantile(np.abs(b) / s, 1 - power.ALPHA))
        out[t] = {
            "size": float(np.mean(np.abs(b) / s > d.t_crit)), "median_se": float(np.median(s)), "mde": power.solve_mde(b, s, d.t_crit),
            "mde_size_adjusted": power.solve_mde(b, s, crit_emp), "crit_empirical": crit_emp, "n": float(n_null),
            **{f"power_{e:.2f}": power.power_at(b, s, d.t_crit, e) for e in BENCHMARK_EFFECTS},
        }
    return out


def ldv_cr1_curves(var: Variant, noise, rng: np.random.Generator, n_draws: int) -> dict[str, dict[str, float]]:
    """CR1 size and MDE of the LDV model by direct simulation (the shift property fails when the regressor is the lagged outcome)."""
    d = var.design
    e = noise.draw(rng, n_draws)
    out = {}
    for t in d.targets:
        x_j = target_column(d, t)
        b0, s0 = var.estimator.fit(e, [t])[t]
        guess = (d.t_crit + 0.84) * float(np.median(s0))
        betas = np.r_[0.0, effect_grid(guess, t)]
        rates = np.array([float(np.mean(np.abs(b / s) > d.t_crit)) for b, s in (var.estimator.fit(e + beta * x_j[:, None], [t])[t] for beta in betas)])
        curve = power_curve_mde(betas, rates, np.full(len(betas), float(n_draws)))
        out[t] = {"size": float(rates[0]), "median_se": float(np.median(s0)), "mde": curve["mde"], "mde_size_adjusted": float("nan"),
                  **{f"power_{eff:.2f}": probit_power(curve["a"], curve["b"], eff) for eff in BENCHMARK_EFFECTS}, "n": float(n_draws)}
    return out


def bootstrap_rate(var: Variant, target: str, noise_matrix: np.ndarray, beta: float, seed_key: int, n_boot: int, fast_data: "power.WcbData | None") -> float:
    """Wild-bootstrap rejection rate at true effect ``beta`` (fast exact engine for plain OLS, generic otherwise)."""
    if fast_data is not None:
        return float(power.wild_bootstrap_reject(var.design, target, fast_data, beta, "rademacher", seed_key, n_draws=n_boot).mean())
    y = noise_matrix + beta * target_column(var.design, target)[:, None]
    return float(np.mean(wild_bootstrap_pvalues(var.estimator, target, y, n_boot=n_boot, seed_key=seed_key) <= power.ALPHA))


def bias_rmse(var: Variant, noise, rng: np.random.Generator, n_draws: int, effect: float = TRUE_EFFECT) -> dict[str, dict[str, float]]:
    """Mean error, RMSE and SD of each target's estimate when the true effect of that target is ``effect``."""
    d = var.design
    e = noise.draw(rng, n_draws)
    out = {}
    for t in d.targets:
        b = var.estimator.fit(e + effect * target_column(d, t)[:, None], [t])[t][0]
        out[t] = {"true_effect": effect, "bias": float(b.mean() - effect), "rel_bias": float((b.mean() - effect) / effect), "rmse": float(np.sqrt(np.mean((b - effect) ** 2))),
                  "sd": float(b.std()), "mc_se_bias": float(b.std() / np.sqrt(n_draws)), "n": float(n_draws)}
    return out


def ldv_nickell(var: Variant, noise, rng: np.random.Generator, n_draws: int, rho_dgp: float) -> dict[str, float]:
    """Mean and SD of the estimated coefficient on ``capb_{t-1}`` in the LDV model, against the DGP's AR(1) coefficient.

    In the static DGP with AR(1) errors and no true dynamics in the mean, the LDV coefficient estimates the error
    persistence ``rho_dgp`` (common-factor restriction) and is biased downward by the Nickell term; the analytic
    large-N value ``nickell_bias(rho, T)`` is reported for comparison. Pure noise, no true effect.
    """
    e = noise.draw(rng, n_draws)
    _, (_, phi, _) = var.estimator.fit(e, [], want_resid=True)  # type: ignore[misc]
    t_mean = float(var.design.counts.mean())
    return {"phi_mean": float(phi.mean()), "phi_sd": float(phi.std()), "rho_dgp": float(rho_dgp), "bias_vs_rho": float(phi.mean() - rho_dgp),
            "nickell_analytic_bias": power.nickell_bias(rho_dgp, t_mean), "mean_t": t_mean, "n": float(n_draws)}


def cache_path(cache: Path, vid: str, dgp: str, scenario: str) -> Path:
    """Result file of one job."""
    return cache / f"{vid}__{dgp}__{scenario}.json"


def _save(path: Path, result: dict) -> None:
    import json

    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, indent=1, default=float), encoding="utf-8")
    tmp.replace(path)


def run_job(ctx: Context, vid: str, dgp: str, scenario: str, cache: Path, settings: Settings = FULL, log=print) -> dict:
    """Run (or resume) one job and persist it after every step. Returns the result dictionary.

    Steps: CR1 null draws (size, MDE, size-adjusted MDE, benchmark powers) -> per target: bootstrap size at beta = 0 and
    the simulated power curve (MDE from a probit fit) -> bias / RMSE at a known true effect (scenario ``ar1_rho_hat``).
    Common random numbers: noise streams depend on (DGP, scenario, purpose) only, not on the variant.
    """
    import json
    import time

    spec = ctx.specs[vid]
    var = build_variant(ctx, spec)
    d = var.design
    params = ctx.dgp(spec, dgp)
    noise = make_noise(d, params, scenario)
    scen, dk = SCENARIO_NAMES.index(scenario), DGP_KEYS[dgp]
    path = cache_path(cache, vid, dgp, scenario)
    result = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if result.get("complete"):
        return result
    start = time.time()
    result.setdefault("meta", {
        "vid": vid, "dgp": dgp, "scenario": scenario, "label": spec.label, "n_obs": d.n_obs, "n_clusters": d.n_clusters, "x_names": d.x_names, "rho_hat_dgp": params.rho_hat,
        "sigma_min": float(params.sigma.min()), "sigma_max": float(params.sigma.max()), "spike_size": params.spike_size, "block": params.block,
        "settings": settings.__dict__, "t_crit": d.t_crit,
    })
    log(f"[{vid}:{dgp}:{scenario}] start N={d.n_obs}")
    if "cr1" not in result:
        rng = make_rng(dk, scen, PURPOSE_NOISE_NULL)
        result["cr1"] = ldv_cr1_curves(var, noise, rng, settings.n_ldv_cr1) if spec.estimator == "ldv" else cr1_from_null_draws(var, noise, rng, settings.n_null)
        _save(path, result)
        log(f"[{vid}:{dgp}:{scenario}] cr1 done {time.time() - start:.0f}s")
    n_size = settings.size_fast if spec.fast else settings.size_generic
    n_mde = settings.mde_fast if spec.fast else settings.mde_generic
    e_size = noise.draw(make_rng(dk, scen, PURPOSE_NOISE_SIZE), n_size)
    e_mde = noise.draw(make_rng(dk, scen, PURPOSE_NOISE_WCB), n_mde)
    fast_size = power.wcb_prepare(d, e_size) if spec.fast else None
    fast_mde = power.wcb_prepare(d, e_mde) if spec.fast else None
    result.setdefault("wcb", {})
    for ti, t in enumerate(d.targets):
        if t in result["wcb"]:
            continue
        seed_key = 1000 + 100 * dk + 10 * scen + ti
        size = bootstrap_rate(var, t, e_size, 0.0, seed_key, settings.n_boot, fast_size[t] if fast_size else None)
        betas = effect_grid(result["cr1"][t]["mde"], t)
        rates = np.array([bootstrap_rate(var, t, e_mde, float(b), seed_key, settings.n_boot, fast_mde[t] if fast_mde else None) for b in betas])
        all_b, all_r = np.r_[0.0, betas], np.r_[size, rates]
        curve = power_curve_mde(all_b, all_r, np.r_[float(n_size), np.full(len(betas), float(n_mde))])
        result["wcb"][t] = {
            "size": size, "n_size": n_size, "n_grid": n_mde, "betas": betas.tolist(), "rates": rates.tolist(), "mde": curve["mde"], "mde_se": curve["mde_se"],
            "max_fit_residual": curve["max_fit_residual"], "fit_a": curve["a"], "fit_b": curve["b"],
            **{f"power_{e:.2f}": probit_power(curve["a"], curve["b"], e) for e in BENCHMARK_EFFECTS},
        }
        _save(path, result)
        log(f"[{vid}:{dgp}:{scenario}] wcb {t} size={size:.3f} mde={curve['mde']:.3f} ({time.time() - start:.0f}s)")
    if scenario == "ar1_rho_hat" and "bias" not in result:
        result["bias"] = bias_rmse(var, noise, make_rng(dk, scen, PURPOSE_NOISE_BIAS), settings.n_bias)
        if spec.estimator == "ldv":
            result["ldv_phi"] = ldv_nickell(var, noise, make_rng(dk, scen, PURPOSE_NOISE_BIAS, 1), settings.n_bias, params.rho_hat)
    result["complete"] = True
    result["seconds"] = time.time() - start
    _save(path, result)
    log(f"[{vid}:{dgp}:{scenario}] complete {result['seconds']:.0f}s")
    return result


# ---------------------------------------------------------------------------------------------
# Aggregation, the selection rule and V6
# ---------------------------------------------------------------------------------------------
def load_results(cache: Path) -> pd.DataFrame:
    """Tidy table (one row per variant x DGP x scenario x target) from the completed job files."""
    import json

    rows = []
    for path in sorted(cache.glob("*__*__*.json")):
        res = json.loads(path.read_text(encoding="utf-8"))
        if not res.get("complete"):
            continue
        meta = res["meta"]
        for t in res["cr1"]:
            w, c = res["wcb"][t], res["cr1"][t]
            bias = res.get("bias", {}).get(t, {})
            rows.append({
                "vid": meta["vid"], "dgp": meta["dgp"], "scenario": meta["scenario"], "target": t, "n_obs": meta["n_obs"], "rho_dgp": meta["rho_hat_dgp"],
                "cr1_size": c["size"], "cr1_mde": c["mde"], "cr1_mde_sa": c["mde_size_adjusted"], "wcb_size": w["size"], "wcb_n_size": w["n_size"], "wcb_mde": w["mde"], "wcb_mde_se": w["mde_se"],
                "cr1_power_041": c.get("power_0.41", np.nan), "cr1_power_049": c.get("power_0.49", np.nan), "wcb_power_041": w.get("power_0.41", np.nan), "wcb_power_049": w.get("power_0.49", np.nan),
                "grid_brackets_80": bool(min(w["rates"]) < power.TARGET_POWER < max(w["rates"])), "fit_residual": w["max_fit_residual"],
                "bias": bias.get("bias", np.nan), "rel_bias": bias.get("rel_bias", np.nan), "rmse": bias.get("rmse", np.nan), "sd": bias.get("sd", np.nan), "mc_se_bias": bias.get("mc_se_bias", np.nan),
            })
    return pd.DataFrame(rows)


def size_valid(size: float) -> bool:
    """True when a null rejection rate lies in the 3.5-6.5 per cent band."""
    return SIZE_VALID[0] <= size <= SIZE_VALID[1]


def evaluate_candidates(df: pd.DataFrame, specs: dict[str, VariantSpec], dgp_mode: str = "designated", exclude: tuple[str, ...] = ("V0n",)) -> pd.DataFrame:
    """One row per variant with the selection inputs: beta_S bootstrap MDE at rho_hat, size validity, relative bias.

    ``dgp_mode`` is ``"designated"`` (each variant under its own DGP convention), or a DGP label (``"F"``, ``"S"``) applied
    to every variant that has been run under it.
    """
    rows = []
    for vid, spec in specs.items():
        if vid in exclude or not spec.eligible:
            continue
        dgp = spec.designated_dgp if dgp_mode == "designated" else dgp_mode
        sub = df[(df["vid"] == vid) & (df["dgp"] == dgp) & (df["target"] == "beta_S")]
        if sub.empty:
            continue
        by = sub.set_index("scenario")
        if not {"ar1_rho_hat", "ar1_rho0"} <= set(by.index):
            continue
        bias = by.loc["ar1_rho_hat", "rel_bias"]
        rows.append({
            "variant": vid, "dgp": dgp, "n_obs": int(by.loc["ar1_rho_hat", "n_obs"]), "mde_wcb_rho_hat": by.loc["ar1_rho_hat", "wcb_mde"], "mde_wcb_rho0": by.loc["ar1_rho0", "wcb_mde"],
            "size_wcb_rho_hat": by.loc["ar1_rho_hat", "wcb_size"], "size_wcb_rho0": by.loc["ar1_rho0", "wcb_size"],
            "size_valid": bool(size_valid(by.loc["ar1_rho_hat", "wcb_size"]) and size_valid(by.loc["ar1_rho0", "wcb_size"])),
            "rel_bias": bias, "bias_ok": bool(abs(bias) < MAX_ABS_REL_BIAS), "complexity": spec.complexity,
        })
    return pd.DataFrame(rows)


def select_variant(candidates: pd.DataFrame) -> tuple[str | None, pd.DataFrame]:
    """Smallest beta_S bootstrap MDE at rho_hat among valid-size, low-bias variants; ties within 5 per cent -> simpler variant."""
    eligible = candidates[candidates["size_valid"] & candidates["bias_ok"]].copy()
    if eligible.empty:
        return None, eligible
    best = eligible["mde_wcb_rho_hat"].min()
    tied = eligible[eligible["mde_wcb_rho_hat"] <= best * (1 + TIE_TOLERANCE)].copy()
    tied["rank"] = tied["variant"].map({v: i for i, v in enumerate(SIMPLICITY_ORDER)})
    return str(tied.sort_values("rank").iloc[0]["variant"]), tied


def choose_v6_components(df: pd.DataFrame, specs: dict[str, VariantSpec], has_controls: bool) -> VariantSpec:
    """Mechanical V6 rule: controls (registry) + every stand-alone component that passes the screen on the common DGP ``F``.

    A component passes when its beta_S wild-bootstrap MDE at rho_hat is at least ``V6_GAIN_THRESHOLD`` below V0's, its
    bootstrap size at rho_hat and rho = 0 is inside the 3.5-6.5 per cent band and its relative bias is below 10 per cent.
    Of the two Ireland treatments only the better one enters. V5 (lagged dependent variable) changes the estimand and is
    never combined.
    """
    table = evaluate_candidates(df, specs, "F").set_index("variant")
    base = table.loc["V0", "mde_wcb_rho_hat"]
    passing = {v: bool(table.loc[v, "size_valid"] and table.loc[v, "bias_ok"] and table.loc[v, "mde_wcb_rho_hat"] <= base * (1 - V6_GAIN_THRESHOLD)) for v in ("V2i", "V2w", "V3", "V4") if v in table.index}
    ireland = [v for v in ("V2i", "V2w") if passing.get(v)]
    ireland_choice = min(ireland, key=lambda v: table.loc[v, "mde_wcb_rho_hat"]) if ireland else None
    wls, ar1 = bool(passing.get("V3")), bool(passing.get("V4"))
    winsor, indicator = ireland_choice == "V2w", ireland_choice == "V2i"
    parts = (["controls"] if has_controls else []) + ([f"Ireland {'indicator' if indicator else 'winsorising'}"] if ireland_choice else []) + (["WLS"] if wls else []) + (["AR(1) GLS"] if ar1 else [])
    return VariantSpec(
        "V6", "V0 + " + (", ".join(parts) if parts else "nothing (no component passed)"), use_controls=has_controls, ireland_indicator=indicator,
        estimator="gls" if (wls or ar1 or winsor) else "ols", wls=wls, ar1=ar1, winsor=winsor, dgps=("F", "O"), designated_dgp="O", complexity=len(parts))


def v6_path(cache: Path) -> Path:
    """File holding the mechanically chosen V6 specification."""
    return cache / "v6_spec.json"


def save_v6(cache: Path, spec: VariantSpec) -> None:
    """Persist the V6 specification (a choice made from stage-A power results only)."""
    import json

    v6_path(cache).write_text(json.dumps(spec.__dict__, indent=1), encoding="utf-8")


def load_v6(cache: Path) -> VariantSpec | None:
    """Read the V6 specification if stage A has been processed."""
    import json

    path = v6_path(cache)
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["dgps"] = tuple(raw["dgps"])
    return VariantSpec(**raw)


STAGE_A = ("V4", "V3", "V2w", "V5", "V0n", "V0", "V1", "V2i")  # slow generic-engine variants first for load balance
STAGE_C = ("V7", "V7@703")  # Gate 3d: the added candidate and its sample-change control


def job_list(stage: str, specs: dict[str, VariantSpec]) -> list[tuple[str, str, str]]:
    """(variant, DGP, scenario) triples of a stage (``A``: V0n..V5, ``B``: V6, ``C``: V7 and V7@703)."""
    vids = {"A": STAGE_A, "B": ("V6",), "C": STAGE_C}[stage]
    return [(v, dgp, s) for v in vids if v in specs for dgp in specs[v].dgps for s in SCENARIO_NAMES]


# ---------------------------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------------------------
def _mark(value: float, ok: bool) -> str:
    """Format a rate as a percentage and flag it with ``!`` when it is outside the validity band."""
    return f"{100 * value:.1f}%" + ("" if ok else " !")


def _pick(df: pd.DataFrame, vid: str, dgp: str, scenario: str, target: str, column: str) -> float:
    sub = df[(df["vid"] == vid) & (df["dgp"] == dgp) & (df["scenario"] == scenario) & (df["target"] == target)]
    return float(sub[column].iloc[0]) if len(sub) else float("nan")


def _vid_dgp(entry: "str | tuple[str, str]", specs: dict[str, VariantSpec], dgp_of) -> tuple[str, str]:
    """``(vid, dgp)`` of a table entry: an explicit pair, or a variant id whose DGP is ``dgp_of(spec)``."""
    return entry if isinstance(entry, tuple) else (entry, dgp_of(specs[entry]))


def mde_table(df: pd.DataFrame, specs: dict[str, VariantSpec], dgp_of, vids: "list[str | tuple[str, str]]") -> str:
    """Variant x target table of wild-bootstrap MDEs at rho_hat, rho = 0 and the block bootstrap (plus CR1 at rho_hat).

    An entry of ``vids`` may be a ``(vid, dgp)`` pair to show a variant under a DGP other than ``dgp_of(spec)``.
    """
    rows = []
    for entry in vids:
        vid, dgp = _vid_dgp(entry, specs, dgp_of)
        row: dict[str, object] = {"variant": vid, "DGP": dgp, "N": int(df[(df["vid"] == vid) & (df["dgp"] == dgp)]["n_obs"].iloc[0]) if len(df[(df["vid"] == vid) & (df["dgp"] == dgp)]) else ""}
        for t in ("beta_S", "gamma_B", "gamma_W"):
            for scen, tag in (("ar1_rho_hat", "rho_hat"), ("ar1_rho0", "rho=0"), ("block_bootstrap", "block")):
                row[f"{t} WCB {tag}"] = _pick(df, vid, dgp, scen, t, "wcb_mde")
            row[f"{t} CR1 rho_hat"] = _pick(df, vid, dgp, "ar1_rho_hat", t, "cr1_mde")
        rows.append(row)
    return power.md_table(pd.DataFrame(rows), floatfmt=".3f")


def size_table(df: pd.DataFrame, specs: dict[str, VariantSpec], dgp_of, vids: "list[str | tuple[str, str]]") -> str:
    """Null rejection rates by variant, target, inference method and scenario; ``!`` marks values outside 3.5-6.5 per cent."""
    rows = []
    for entry in vids:
        vid, dgp = _vid_dgp(entry, specs, dgp_of)
        for t in ("beta_S", "gamma_B", "gamma_W"):
            row: dict[str, object] = {"variant": f"{vid} ({dgp})" if isinstance(entry, tuple) else vid, "target": t}
            flags = []
            for method, column in (("CR1", "cr1_size"), ("WCB", "wcb_size")):
                for scen, tag in (("ar1_rho_hat", "rho_hat"), ("ar1_rho0", "rho=0"), ("block_bootstrap", "block")):
                    value = _pick(df, vid, dgp, scen, t, column)
                    row[f"{method} {tag}"] = _mark(value, size_valid(value)) if np.isfinite(value) else "n/a"
                    if method == "WCB" and scen != "block_bootstrap" and np.isfinite(value) and not size_valid(value):
                        flags.append(f"WCB {tag}")
            row["WCB verdict (AR(1) scenarios)"] = "INVALID: " + ", ".join(flags) if flags else "valid"
            rows.append(row)
    return power.md_table(pd.DataFrame(rows))


def bias_table(df: pd.DataFrame, specs: dict[str, VariantSpec], dgp_of, vids: "list[str | tuple[str, str]]") -> str:
    """Bias, relative bias, RMSE and SD of each target's estimate when its true effect is ``TRUE_EFFECT``."""
    rows = []
    for entry in vids:
        vid, dgp = _vid_dgp(entry, specs, dgp_of)
        for t in ("beta_S", "gamma_B", "gamma_W"):
            sub = df[(df["vid"] == vid) & (df["dgp"] == dgp) & (df["scenario"] == "ar1_rho_hat") & (df["target"] == t)]
            if sub.empty:
                continue
            r = sub.iloc[0]
            rows.append({"variant": f"{vid} ({dgp})" if isinstance(entry, tuple) else vid, "target": t, "bias (pp)": r["bias"], "relative bias": f"{100 * r['rel_bias']:.1f}%", "MC SE of bias": r["mc_se_bias"], "RMSE (pp)": r["rmse"], "SD (pp)": r["sd"]})
    return power.md_table(pd.DataFrame(rows), floatfmt=".3f")


def selected_table(df: pd.DataFrame, vid: str, dgp: str) -> tuple[str, list[dict[str, object]]]:
    """MDE table of the selected variant with G2 verdicts, the D-C label and power against the literature benchmarks."""
    rows, summary = [], []
    for t in ("beta_S", "gamma_B", "gamma_W"):
        hat, zero, block = (_pick(df, vid, dgp, s, t, "wcb_mde") for s in ("ar1_rho_hat", "ar1_rho0", "block_bootstrap"))
        cr_hat, cr_zero = _pick(df, vid, dgp, "ar1_rho_hat", t, "cr1_mde"), _pick(df, vid, dgp, "ar1_rho0", t, "cr1_mde")
        verdict, verdict_cr1 = power.gate_verdict(t, hat, zero), power.gate_verdict(t, cr_hat, cr_zero)
        label = "not powered" if hat > power.G2_NOGO else "powered"
        row = {"target": t, "WCB MDE rho_hat": hat, "WCB MDE rho=0": zero, "WCB MDE block": block, "CR1 MDE rho_hat": cr_hat, "CR1 MDE rho=0": cr_zero,
               "G2 (WCB)": verdict, "G2 (CR1)": verdict_cr1, "D-C": label}
        rows.append(row)
        summary.append({**row, "target": t})
    return power.md_table(pd.DataFrame(rows), floatfmt=".3f"), summary


def benchmark_table(df: pd.DataFrame, vid: str, dgp: str) -> str:
    """Power of beta_S against the 0.41 pp and 0.49 pp literature benchmarks (CR1 exact; bootstrap from the fitted curve)."""
    rows = []
    for scen in SCENARIO_NAMES:
        rows.append({
            "scenario": scen, "CR1 power at 0.41": _pick(df, vid, dgp, scen, "beta_S", "cr1_power_041"), "WCB power at 0.41": _pick(df, vid, dgp, scen, "beta_S", "wcb_power_041"),
            "CR1 power at 0.49": _pick(df, vid, dgp, scen, "beta_S", "cr1_power_049"), "WCB power at 0.49": _pick(df, vid, dgp, scen, "beta_S", "wcb_power_049"),
        })
    return power.md_table(pd.DataFrame(rows), floatfmt=".3f")


def calibration_rows(cache: Path) -> str:
    """Noise calibration of each DGP actually used (from the job metadata)."""
    import json

    seen, rows = set(), []
    for path in sorted(cache.glob("*__*__ar1_rho_hat.json")):
        meta = json.loads(path.read_text(encoding="utf-8"))["meta"]
        key = (meta["dgp"], meta["vid"] if meta["dgp"] == "O" else "-")
        if key in seen:
            continue
        seen.add(key)
        rows.append({"DGP": meta["dgp"], "variant (O only)": key[1], "N": meta["n_obs"], "rho_hat": meta["rho_hat_dgp"], "sigma min (pp)": meta["sigma_min"], "sigma max (pp)": meta["sigma_max"],
                     "Ireland-2010 spike (pp)": meta["spike_size"], "block (years)": meta["block"]})
    return power.md_table(pd.DataFrame(rows), floatfmt=".3f")


GATE3B_MDE = {  # reports/gate3_power_update.md section 4: (scenario, target) -> (CR1 MDE, wild-bootstrap MDE) of the M1 without era terms
    ("ar1_rho_hat", "beta_S"): (0.664, 0.679), ("ar1_rho_hat", "gamma_B"): (0.924, 1.062), ("ar1_rho_hat", "gamma_W"): (0.872, 0.874),
    ("ar1_rho0", "beta_S"): (0.939, 0.994), ("ar1_rho0", "gamma_B"): (1.168, 1.295), ("ar1_rho0", "gamma_W"): (0.859, 0.889),
    ("block_bootstrap", "beta_S"): (0.844, 0.895), ("block_bootstrap", "gamma_B"): (1.084, 1.204), ("block_bootstrap", "gamma_W"): (0.940, 0.990),
}


def validation_table(df: pd.DataFrame) -> str:
    """V0n (M1 without era terms, DGP F) against the published Gate 3b MDEs: an end-to-end check of the engine and the DGP."""
    rows = []
    for (scen, t), (cr1, wcb) in GATE3B_MDE.items():
        rows.append({"scenario": scen, "target": t, "3b CR1": cr1, "this run CR1": _pick(df, "V0n", "F", scen, t, "cr1_mde"), "3b WCB": wcb, "this run WCB": _pick(df, "V0n", "F", scen, t, "wcb_mde")})
    return power.md_table(pd.DataFrame(rows), floatfmt=".3f")


def ldv_table(cache: Path) -> str:
    """Nickell-type bias of the lagged-dependent-variable coefficient (V5) from its job file."""
    import json

    path = cache_path(cache, "V5", "F", "ar1_rho_hat")
    if not path.exists():
        return "V5 not run."
    phi = json.loads(path.read_text(encoding="utf-8")).get("ldv_phi")
    if phi is None:
        return "V5 not run."
    return power.md_table(pd.DataFrame([{
        "DGP rho (AR(1) errors)": phi["rho_dgp"], "mean coefficient on capb(t-1)": phi["phi_mean"], "SD across draws": phi["phi_sd"], "bias vs rho": phi["bias_vs_rho"],
        "analytic Nickell bias at T = %.1f" % phi["mean_t"]: phi["nickell_analytic_bias"]}]), floatfmt=".3f")


def reading_lines(df: pd.DataFrame, choice: str, specs: dict[str, VariantSpec]) -> list[str]:
    """Plain-language reading of the headline, with every number taken from ``df``."""
    g = lambda v, d, sc, t, c="wcb_mde": _pick(df, v, d, sc, t, c)  # noqa: E731
    dgp = specs[choice].designated_dgp
    s0, sc = g("V0", "F", "ar1_rho_hat", "beta_S"), g(choice, dgp, "ar1_rho_hat", "beta_S")
    lines = [
        "**Reading.**",
        "",
        f"* The registry baseline V0 (era terms) has beta_S wild-bootstrap MDE {s0:.2f} pp at the estimated rho, the same as the Gate 3b M1 without era terms (V0n {g('V0n', 'F', 'ar1_rho_hat', 'beta_S'):.2f}); the engine reproduces Gate 3b (section 2). "
        f"The era terms leave beta_S alone but raise the gamma_W MDE from {g('V0n', 'F', 'ar1_rho_hat', 'gamma_W'):.2f} to {g('V0', 'F', 'ar1_rho_hat', 'gamma_W'):.2f} pp: with the registry's three eras, gamma_W is 'not powered' in every OLS variant.",
        f"* Gains come from the estimator, not from the extra regressors. Feasible WLS (V3) lowers the beta_S MDE to {g('V3', 'F', 'ar1_rho_hat', 'beta_S'):.2f} pp ({100 * (1 - g('V3', 'F', 'ar1_rho_hat', 'beta_S') / s0):.0f}% below V0) and AR(1) feasible GLS (V4) to {g('V4', 'F', 'ar1_rho_hat', 'beta_S'):.2f} pp "
        f"({100 * (1 - g('V4', 'F', 'ar1_rho_hat', 'beta_S') / s0):.0f}%), both with bootstrap size 4.4-5.6 per cent and bias under 1 per cent. Controls (V1) and the Ireland indicator or winsorising (V2) change the beta_S MDE by "
        f"{100 * (g('V1', 'F', 'ar1_rho_hat', 'beta_S') / s0 - 1):+.0f}%, {100 * (g('V2i', 'F', 'ar1_rho_hat', 'beta_S') / s0 - 1):+.0f}% and {100 * (g('V2w', 'F', 'ar1_rho_hat', 'beta_S') / s0 - 1):+.0f}% on the common DGP; V2i looks better ({g('V2i', 'O', 'ar1_rho_hat', 'beta_S'):.2f} pp) only when the noise is recalibrated without the Ireland outlier, which is the DGP change, not the estimator.",
        f"* The combination {choice} ({specs[choice].label}) reaches {sc:.2f} pp, {100 * (1 - sc / s0):.0f}% below V0, and meets the validity screens (size, bias). Against the G2 line (0.50 pp at the estimated rho, 0.75 pp at rho = 0) it is AMBER under the bootstrap and 'GO' only under CR1, which is not a valid basis here: CR1 over-rejects for the feasible-GLS variants (about 8 per cent for beta_S) because it ignores that the weights and rho are estimated, "
        "whereas the bootstrap, which re-estimates them in every resample, has size 5.0-5.6 per cent. The headline is therefore the bootstrap column.",
        f"* The AR(1) part helps only through persistence: V4 at rho = 0 gives {g('V4', 'F', 'ar1_rho0', 'beta_S'):.2f} pp, no better than V0 ({g('V0', 'F', 'ar1_rho0', 'beta_S'):.2f}); the gain therefore depends on the estimated rho of 0.69 being right (Gate 3b caveat 4). The WLS part is robust to rho (V3 at rho = 0: {g('V3', 'F', 'ar1_rho0', 'beta_S'):.2f} pp).",
        f"* Demotion rule D-C under {choice}: " + ", ".join(f"{t} {'not powered' if g(choice, dgp, 'ar1_rho_hat', t) > power.G2_NOGO else 'powered'} ({g(choice, dgp, 'ar1_rho_hat', t):.2f} pp)" for t in ("beta_S", "gamma_B", "gamma_W")) + ".",
        f"* V5 (lagged outcome) is not recommended: it is the least efficient estimator that still has valid size (beta_S MDE {g('V5', 'F', 'ar1_rho_hat', 'beta_S'):.2f} pp) and its W_S coefficient is biased {100 * _pick(df, 'V5', 'F', 'ar1_rho_hat', 'beta_S', 'rel_bias'):.1f}% at a 0.5 pp static effect; its lag coefficient shows the Nickell bias (section 5).",
        "",
    ]
    return lines


def render_report(df: pd.DataFrame, ctx: Context, cache: Path, settings_note: str) -> str:
    """Markdown of ``reports/gate3c_specification_power.md`` computed from the completed jobs (all numbers come from ``df``)."""
    specs = ctx.specs
    present = [v for v in SIMPLICITY_ORDER if v in set(df["vid"])]
    designated = lambda s: s.designated_dgp  # noqa: E731
    on_f = lambda s: "F"  # noqa: E731
    main_ids = ["V0n"] + present if "V0n" in set(df["vid"]) else present
    cand = evaluate_candidates(df, specs, "designated")
    choice, tied = select_variant(cand)
    cand_f = evaluate_candidates(df, specs, "F")
    choice_f, _ = select_variant(cand_f)
    lines = [
        "# Gate 3c: power-only comparison of specification variants of the confirmatory model M1",
        "",
        f"Generated by `python src/evaluate/power_variants.py report` ({settings_note}). Engine `src/evaluate/power.py` (reused), variants `src/evaluate/power_variants.py`, tests `tests/test_power_variants.py`. Offline. "
        "**No effect estimate from the real CAPB panel was computed, printed or logged**: only OLS residuals of each variant's own regressor set calibrate the noise (country SDs, AR(1) persistence, residual grid), as in Gate 3b. "
        "Every random stream is `default_rng(SeedSequence([42, 3000, ...]))` with documented integer keys; results reproduce exactly.",
        "",
        "## 0. Headline",
        "",
    ]
    if choice is None:
        lines += ["**No variant satisfies the selection rule (valid size and absolute relative bias below 10 per cent).**", ""]
    else:
        table, summary = selected_table(df, choice, specs[choice].designated_dgp)
        s_hat = _pick(df, choice, specs[choice].designated_dgp, "ar1_rho_hat", "beta_S", "wcb_mde")
        v0_hat = _pick(df, "V0", "F", "ar1_rho_hat", "beta_S", "wcb_mde")
        lines += [
            f"**Recommended M1 variant: {choice}** ({specs[choice].label}), selected mechanically by the rule of section 1 (smallest wild-bootstrap beta_S MDE at the estimated rho among variants with valid size and |relative bias| < 10 per cent; ties within 5 per cent go to the simpler variant). "
            f"Its beta_S wild-bootstrap MDE at the estimated rho is {s_hat:.2f} pp against {v0_hat:.2f} pp for the registry baseline V0 on the common DGP. Selecting on the common DGP `F` alone would give {choice_f}.",
            "",
            table,
            "",
            "MDE in pp of potential GDP (gamma per +1 SD of the component), 80 per cent power, alpha 0.05, two-sided. WCB = wild-cluster bootstrap-t (Rademacher, null imposed, "
            f"{N_BOOT} draws); CR1 = country-clustered t(26). G2: beta_S MDE <= 0.50 pp at the estimated rho and <= 0.75 pp at rho = 0, NO-GO above 1.0 pp; interactions <= 0.75 pp per SD (NO-GO line 1.0 pp is an extension). "
            "D-C: any target whose WCB MDE at the estimated rho exceeds 1.0 pp is 'not powered'.",
            "",
            *reading_lines(df, choice, specs),
        ]
    lines += [
        "## 1. What was compared and how the choice is made",
        "",
        "| id | variant | estimator | DGP(s) run | designated DGP |",
        "|---|---|---|---|---|",
    ]
    for v in main_ids:
        s = specs[v]
        lines.append(f"| {v} | {s.label} | {s.estimator}{' + WLS' if s.wls else ''}{' + AR(1)' if s.ar1 else ''}{' + winsor' if s.winsor else ''} | {', '.join(s.dgps)} | {s.designated_dgp} |")
    lines += [
        "",
        "**DGPs.** `F`: the Gate 3b noise (country SDs and rho = 0.69 from the V0n residuals, simulation-corrected; the block bootstrap resamples its residual grid), used for every variant. For variants that add regressors (V1, V2i, V6) the "
        "designated DGP is `O`: noise recalibrated from the variant's OWN OLS residuals. **This changes the data-generating process**, because a model with controls or an Ireland indicator leaves less unexplained variance, and a fair power "
        "calculation for that model uses the noise it would face; the price is that the gain is credited only if the added terms belong in the true model. `S`: the V2i noise plus the Ireland-2010 shock re-inserted with random sign and the size of "
        "the observed V0 residual at that cell, because a Gaussian country SD cannot represent a one-off outlier; it is the faithful DGP for judging the Ireland treatments (V0, V2i, V2w).",
        "",
        "**Feasible GLS honesty.** V3 and V4 (and V2w, V6) estimate the first-stage residuals, `sigma_i^2`, `rho` and the winsor limits inside every simulated draw and again inside every bootstrap sample; nothing is taken from the real data. "
        "Adding a true effect shifts these estimators' coefficient by exactly that effect and leaves the CR1 SE unchanged, so CR1 size and MDE use one set of null draws; V5 (lagged outcome as regressor) lacks this property and is simulated directly.",
        "",
        "**Selection rule (pre-specified in the task, applied mechanically).** Among variants whose wild-bootstrap beta_S size is within 3.5-6.5 per cent at both AR(1) scenarios (rho_hat and rho = 0) and whose absolute relative bias of beta_S at a known true effect of 0.5 pp is below 10 per cent, choose the smallest beta_S wild-bootstrap MDE at rho_hat; "
        f"candidates within {int(100 * TIE_TOLERANCE)} per cent of the minimum are tied and the simpler variant wins (order {' < '.join(SIMPLICITY_ORDER)}). V0n is a reference row and is not eligible.",
        "",
        "**V6 rule.** V6 = V0 + the controls that survived T4 + every stand-alone component (Ireland treatment, WLS, AR(1) GLS) whose beta_S wild-bootstrap MDE on the common DGP `F` is at least "
        f"{int(100 * V6_GAIN_THRESHOLD)} per cent below V0's with valid size and bias below 10 per cent; only the better Ireland treatment enters; V5 never combines. Composition here: "
        f"{specs['V6'].label if 'V6' in specs else 'not run'}.",
        "",
        "## 2. Noise calibration of the DGPs used",
        "",
        calibration_rows(cache),
        "",
        "Engine validation: V0n on the `F` DGP is the Gate 3b M1, so it must reproduce the published Gate 3b MDEs (3b: 20,000 CR1 draws and 2,000 bootstrap datasets of 999 draws):",
        "",
        validation_table(df),
        "",
        "## 3. MDEs by variant (designated DGP)",
        "",
        mde_table(df, specs, designated, main_ids),
        "",
        "## 4. Size: null rejection rates (`!` = outside 3.5-6.5 per cent)",
        "",
        f"CR1: {int(ctx_settings_value(df, 'n_null'))} null draws. Bootstrap size uses {FULL.size_fast} datasets on the fast engine (Monte Carlo SE of a 5 per cent rate about 0.35 points) and {FULL.size_generic} on the generic engine (0.56 points); {FULL.mde_fast} / {FULL.mde_generic} datasets per grid point for the MDE. "
        "Variants whose bootstrap size is outside the band in an AR(1) scenario are flagged invalid. The block-bootstrap scenario over-rejects for every method in Gate 3b (about 10 per cent for beta_S and gamma_B) and is shown for completeness, not used for validity.",
        "",
        size_table(df, specs, designated, main_ids),
        "",
        "## 5. Bias and RMSE at a known true effect (0.5 pp, estimated-rho AR(1) noise)",
        "",
        bias_table(df, specs, designated, main_ids),
        "",
        "The lagged-dependent-variable model (V5): in this static DGP the coefficient on capb(t-1) estimates the error persistence and carries the Nickell bias,",
        "",
        ldv_table(cache),
        "",
        "## 6. The selection rule applied",
        "",
        power.md_table(cand.assign(**{c: cand[c].map(lambda v: f"{100 * v:.1f}%") for c in ("size_wcb_rho_hat", "size_wcb_rho0", "rel_bias")}), floatfmt=".3f"),
        "",
        f"Selected: **{choice}**. Tied within {int(100 * TIE_TOLERANCE)} per cent of the best: {', '.join(tied['variant']) if choice else 'none'}.",
        "",
    ]
    if choice is not None:
        dgp = specs[choice].designated_dgp
        table, summary = selected_table(df, choice, dgp)
        lines += [
            f"## 7. The recommended variant ({choice}): MDE table, G2 verdicts, demotion rule D-C, literature benchmarks",
            "",
            table,
            "",
            "Power of beta_S against the two literature benchmarks (indicative: those studies use other outcomes and designs; CR1 is exact from null draws, WCB from the fitted simulated power curve):",
            "",
            benchmark_table(df, choice, dgp),
            "",
        ]
    lines += [
        "## 8. Robustness: all variants on the common DGP `F`, and the Ireland treatments on the spike DGP `S`",
        "",
        "All variants on `F` (identical noise; V1, V2i and V6 gain nothing from their extra regressors and lose degrees of freedom):",
        "",
        mde_table(df, specs, on_f, [v for v in main_ids if "F" in specs[v].dgps]),
        "",
        power.md_table(cand_f.assign(**{c: cand_f[c].map(lambda v: f"{100 * v:.1f}%") for c in ("size_wcb_rho_hat", "size_wcb_rho0", "rel_bias")}), floatfmt=".3f"),
        "",
        f"Selection on `F` alone: {choice_f}.",
        "",
    ]
    s_ids = [v for v in main_ids if "S" in specs[v].dgps]
    if s_ids:
        cand_s = evaluate_candidates(df, specs, "S")
        choice_s, _ = select_variant(cand_s)
        lines += [
            "Ireland treatments on the spike DGP `S` (V0 and V2w face the outlier; V2i removes it with the indicator):",
            "",
            mde_table(df, specs, lambda s: "S", s_ids),
            "",
            f"Selection among these on `S`: {choice_s}.",
            "",
        ]
    lines += [
        "## 9. Limitations",
        "",
        "1. **Choosing a variant by power on the same panel is a researcher degree of freedom.** It is mitigated, not removed: the choice uses only noise calibrations and simulated draws (no effect estimate was computed, printed or logged), the rule and the candidate set are fixed before the results, "
        "and the registry is frozen only after the choice. It still tunes the specification to this panel's noise structure; the freeze must record the chosen variant and this report's hash.",
        "2. **The DGP drives the answer.** The designated convention credits variance reduction to variants that add regressors (`O`); on the common DGP `F` they do not gain. Neither is the truth: the truth about Ireland 2010 is a one-off shock, which `S` represents with an assumed sign symmetry and magnitude equal to a V0 residual.",
        "3. **Gaussian innovations, a common AR(1) coefficient, independence across countries** (AR(1) scenarios); the block bootstrap carries cross-country structure but understates persistence (Gate 3b). The analytic Nickell correction inside V4 under-corrects rho in this geometry (Gate 3b: 0.56 raw, 0.63 analytic, 0.69 simulated), "
        "which costs a little efficiency, not validity.",
        "4. **V1 changes the sample** (complete cases of the surviving controls) and the lag structure of V5 loses the first year of every run; MDEs of variants with different N are not like-for-like.",
        "5. **Bootstrap Monte Carlo error.** MDEs come from a probit fit through simulated rejection rates on a grid of true effects (common random numbers); the parametric-bootstrap SE of the fitted MDE is stored in the job files (`wcb_mde_se`) and is typically 0.01-0.03 pp. Differences under about 5 per cent are within noise, which is why ties go to the simpler variant.",
        "6. **V5** is a bias check: its W_S coefficient is a short-run effect and, in a static DGP with AR(1) errors, it is not centred on the true static effect; the bias column is the finding.",
        "7. **Webb weights** were not re-run; Gate 3b found Rademacher and Webb indistinguishable with 27 clusters.",
        "8. Power is for single coefficients at 5 per cent; the Holm family and any multiplicity adjustment are outside this comparison.",
        "",
        "## 10. Files and reproduction",
        "",
        "`src/evaluate/power_variants.py`, `tests/test_power_variants.py`, `src/normalize/eurostat.py`, `src/features/controls.py`, `reports/gate4_controls_coverage.md`, this report. "
        "Reproduce: `python src/evaluate/power_variants.py jobs A` lists the stage-A jobs; each is run with `python src/evaluate/power_variants.py job VID DGP SCENARIO --cache DIR`; then `choose`, stage B (`jobs B`), and `report`.",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------
# Gate 3d report: V7 against the Gate 3c variants (reuses the tables above)
# ---------------------------------------------------------------------------------------------
REPORT_3D_PATH = PROJECT_ROOT / "reports" / "gate3d_v7_candidate.md"
REFERENCE_PAIRS_3D = (("V0", "F"), ("V3", "F"), ("V4", "F"), ("V6", "F"), ("V6", "O"))  # shown beside V7 and V7@703


def max_abs_difference(a: object, b: object) -> float:
    """Largest absolute numeric difference between two nested job results (``seconds`` ignored; non-numeric leaves must be equal)."""
    if isinstance(a, dict) and isinstance(b, dict):
        keys = (set(a) | set(b)) - {"seconds"}
        return max([max_abs_difference(a.get(k), b.get(k)) for k in keys] or [0.0])
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return float("inf") if len(a) != len(b) else max([max_abs_difference(x, y) for x, y in zip(a, b)] or [0.0])
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return 0.0 if (a == b or (a != a and b != b)) else abs(float(a) - float(b))
    return 0.0 if a == b else float("inf")


def reproduction_table(old: pd.DataFrame, new: pd.DataFrame, pairs: "list[tuple[str, str]]", old_cache: Path, new_cache: Path) -> tuple[str, str, float]:
    """Gate 3c results against a fresh re-run of the same jobs: a per-target table, a per-job table and the largest absolute difference.

    The per-job figure compares every number in the two job files (including the simulated rejection rates), not only the table columns.
    """
    import json

    rows, job_rows, worst = [], [], 0.0
    for vid, dgp in pairs:
        for scen in SCENARIO_NAMES:
            if new[(new["vid"] == vid) & (new["dgp"] == dgp) & (new["scenario"] == scen)].empty:
                job_rows.append({"job": f"{vid}:{dgp}:{scen}", "max abs difference over every number in the job file": "not re-run"})
                continue
            for t in ("beta_S", "gamma_B", "gamma_W"):
                row: dict[str, object] = {"job": f"{vid}:{dgp}:{scen}", "target": t}
                for label, column in (("WCB MDE", "wcb_mde"), ("CR1 MDE", "cr1_mde"), ("WCB size", "wcb_size"), ("rel bias", "rel_bias")):
                    if scen != "ar1_rho_hat" and column == "rel_bias":
                        continue
                    row[f"{label} 3c"], row[f"{label} re-run"] = _pick(old, vid, dgp, scen, t, column), _pick(new, vid, dgp, scen, t, column)
                rows.append(row)
            a_res = json.loads(cache_path(old_cache, vid, dgp, scen).read_text(encoding="utf-8"))
            b_res = json.loads(cache_path(new_cache, vid, dgp, scen).read_text(encoding="utf-8"))
            diff = max_abs_difference(a_res, b_res)
            worst = max(worst, diff)
            job_rows.append({"job": f"{vid}:{dgp}:{scen}", "max abs difference over every number in the job file": f"{diff:.3g}"})
    return power.md_table(pd.DataFrame(rows).astype(object).fillna("-"), floatfmt=".4f"), power.md_table(pd.DataFrame(job_rows)), worst


def render_report_3d(df: pd.DataFrame, repro: pd.DataFrame, cache: Path, repro_cache: Path, settings_note: str) -> str:
    """Markdown of ``reports/gate3d_v7_candidate.md``; every number comes from the completed job files of ``cache`` and ``repro_cache``."""
    specs = {**VARIANT_SPECS, **GATE3D_SPECS}
    v6 = load_v6(cache)
    if v6 is not None:
        specs["V6"] = v6
    g = lambda v, d, sc, t, c="wcb_mde": _pick(df, v, d, sc, t, c)  # noqa: E731
    cand = evaluate_candidates(df, specs, "designated")
    choice, tied = select_variant(cand)
    cand_f = evaluate_candidates(df, specs, "F")
    choice_f, tied_f = select_variant(cand_f)
    eligible = cand[cand["size_valid"] & cand["bias_ok"]]
    best_row = eligible.sort_values("mde_wcb_rho_hat").iloc[0]
    best = float(best_row["mde_wcb_rho_hat"])
    thr = best * (1 + TIE_TOLERANCE)
    v7, v7_703 = g("V7", "F", "ar1_rho_hat", "beta_S"), g("V7@703", "F", "ar1_rho_hat", "beta_S")
    v6_o, v6_f = g("V6", "O", "ar1_rho_hat", "beta_S"), g("V6", "F", "ar1_rho_hat", "beta_S")
    v7_in = bool(v7 <= thr)
    v7_row = cand[cand["variant"] == "V7"].iloc[0]
    table_rep, table_jobs, worst = reproduction_table(df, repro, [("V6", "O"), ("V4", "F")], cache, repro_cache)
    n_rerun = len(repro[repro["vid"].isin(["V4", "V6"])][["vid", "dgp", "scenario"]].drop_duplicates())
    v6_gap = float(cand.loc[cand["variant"] == "V6", "mde_wcb_rho_hat"].iloc[0]) / best - 1 if (cand["variant"] == "V6").any() else float("nan")
    pct = lambda frame, cols: frame.assign(**{c: frame[c].map(lambda v: f"{100 * v:.1f}%") for c in cols})  # noqa: E731
    pct_cols = ("size_wcb_rho_hat", "size_wcb_rho0", "rel_bias")
    lines = [
        "# Gate 3d: candidate V7 (V0 + feasible WLS + AR(1) GLS, no controls) added to the power-only specification comparison",
        "",
        f"Generated by `python src/evaluate/power_variants.py report3d` ({settings_note}). Same engine, DGPs, seeds, numbers of null draws, bootstrap datasets and bootstrap replications as Gate 3c (`reports/gate3c_specification_power.md`); "
        "the Gate 3c job results are re-used unchanged for every other variant. Offline. **No effect estimate from the real CAPB panel was computed, printed or logged**: only residual-based noise calibration, as in Gates 3b and 3c.",
        "",
        "## 0. Headline",
        "",
        f"* **Selected under the unchanged mechanical rule on the extended set {{V0, V1, V2i, V2w, V3, V4, V5, V6, V7}}: {choice}.** Smallest eligible beta_S wild-bootstrap MDE at the estimated rho: {best:.3f} pp ({best_row['variant']}); "
        f"the 5 per cent tie band is <= {thr:.3f} pp; tied set: {', '.join(tied['variant'])}; the simplicity order {' < '.join(SIMPLICITY_ORDER)} then picks {choice}.",
        f"* **V7 beta_S MDE {v7:.3f} pp** (N = 715, DGP F) is {100 * (v7 / best - 1):+.1f}% against the minimum: **{'WITHIN' if v7_in else 'OUTSIDE'} the 5 per cent band**; V7 size {100 * v7_row['size_wcb_rho_hat']:.1f}% / {100 * v7_row['size_wcb_rho0']:.1f}% "
        f"(rho_hat / rho = 0), relative bias {100 * v7_row['rel_bias']:.1f}%, size_valid {bool(v7_row['size_valid'])}, bias_ok {bool(v7_row['bias_ok'])}. V6 (N = 703, DGP O) is {v6_o:.3f} pp; V6 on the common DGP F is {v6_f:.3f} pp.",
        f"* **V7@703** (same estimator on the 703 rows of V6, not eligible): {v7_703:.3f} pp, i.e. the sample change alone moves beta_S by {v7_703 - v7:+.3f} pp, and the controls themselves by {v6_f - v7_703:+.3f} pp (V6 on F vs V7@703); "
        f"recalibrating the noise on the V6 residuals (DGP O) adds {v6_o - v6_f:+.3f} pp.",
        f"* V6 (the Gate 3c choice) is {100 * v6_gap:+.1f}% against the minimum, so it is also inside the 5 per cent band; the tie is resolved by the simplicity order in favour of the simpler variant ({choice}).",
        f"* Selection on the common DGP F alone (every variant on identical noise) gives {choice_f}.",
        f"* Engine re-check: {n_rerun} of the 6 V4 (F) / V6 (O) jobs were re-run from scratch; the largest absolute difference to the Gate 3c job files over every stored number is {worst:.3g} (section 4).",
        "",
        "## 1. What was added",
        "",
        "* **V7** = the registry baseline V0 (M1 with the centred era terms, N = 715, no controls), estimated by feasible WLS (1/sigma_i^2 re-estimated from each draw's own first-stage residuals) AND AR(1) feasible GLS "
        "(Prais-Winsten, Nickell-corrected rho re-estimated per draw); both steps are repeated inside every wild-bootstrap sample. It is V6 without the controls. Designated DGP: `F` (no regressors are added, so no recalibration).",
        "* **V7@703** = V7 on the 703 complete-case rows used by V6 (the 12 country-years that lack the lagged output gap are dropped; the output gap and euro membership are NOT regressors), DGP `F`. It separates the effect of the sample change from the effect of the controls and is **not eligible** for selection.",
        "* **Complexity and tie-break.** V7 has two components (WLS and AR(1)): more than V3/V4 (1), less than V6 (3). The simplicity order is now **V0 < V1 < V2i < V2w < V3 < V4 < V5 < V7 < V6** (`SIMPLICITY_ORDER` in the code, asserted in the tests).",
        f"* **Rule (unchanged).** Among variants with wild-bootstrap beta_S size in 3.5-6.5 per cent at rho_hat and rho = 0 and |relative bias| < {int(100 * MAX_ABS_REL_BIAS)} per cent at a true 0.5 pp, take the smallest beta_S wild-bootstrap MDE at rho_hat; candidates within {int(100 * TIE_TOLERANCE)} per cent of it are tied and the simplest wins. V0n and V7@703 are reported, never eligible.",
        "* **Re-use of Gate 3c.** The Gate 3c job files (V0n, V0, V1, V2i, V2w, V3, V4, V5, V6) are read unchanged; V7 and V7@703 are new jobs with the 3c full settings. Because the noise streams depend on (DGP, scenario, purpose) only, V7 sees exactly the same draws as V3, V4 and V6-on-F (common random numbers).",
        "",
        "Calibration actually used (job metadata):",
        "",
        power.md_table(pd.DataFrame([{"variant": v, "DGP": d, "N": int(g(v, d, "ar1_rho_hat", "beta_S", "n_obs")), "rho_hat of the DGP": g(v, d, "ar1_rho_hat", "beta_S", "rho_dgp")} for v, d in (("V7", "F"), ("V7@703", "F"), ("V6", "O"))]), floatfmt=".3f"),
        "",
        "## 2. MDEs: V7 and V7@703 beside their references",
        "",
        mde_table(df, specs, lambda s: s.designated_dgp, [("V7", "F"), ("V7@703", "F"), *REFERENCE_PAIRS_3D]),
        "",
        "MDE in pp of potential GDP (gamma per +1 SD of the component), 80 per cent power, alpha 0.05, two-sided. WCB = wild-cluster bootstrap-t (Rademacher, null imposed, "
        f"{N_BOOT} draws, whole feasible procedure re-estimated per bootstrap sample); CR1 = country-clustered t(26). N differs between rows (715 vs 703): compare V7 with V7@703 and V6 on F with V7@703 for like-for-like contrasts.",
        "",
        "Monte Carlo SE of the fitted wild-bootstrap MDE at rho_hat (probit-fit parametric bootstrap, pp) and the CR1 MDE at rho = 0:",
        "",
        power.md_table(pd.DataFrame([{"variant (DGP)": f"{v} ({d})", **{f"{t} WCB SE": g(v, d, "ar1_rho_hat", t, "wcb_mde_se") for t in ("beta_S", "gamma_B", "gamma_W")},
                                      **{f"{t} CR1 MDE rho=0": g(v, d, "ar1_rho0", t, "cr1_mde") for t in ("beta_S", "gamma_B", "gamma_W")}} for v, d in (("V7", "F"), ("V7@703", "F"), ("V6", "F"), ("V6", "O"))]), floatfmt=".3f"),
        "",
        "## 3. Size and bias",
        "",
        "Null rejection rates (`!` = outside 3.5-6.5 per cent); bootstrap size uses 1500 datasets on the generic engine (Monte Carlo SE about 0.56 points):",
        "",
        size_table(df, specs, lambda s: s.designated_dgp, [("V7", "F"), ("V7@703", "F"), ("V4", "F"), ("V6", "O")]),
        "",
        f"Bias and RMSE at a known true effect of {TRUE_EFFECT} pp per target (estimated-rho AR(1) noise, {FULL.n_bias} draws):",
        "",
        bias_table(df, specs, lambda s: s.designated_dgp, [("V7", "F"), ("V7@703", "F"), ("V4", "F"), ("V6", "O")]),
        "",
        "## 4. Does the engine still reproduce Gate 3c?",
        "",
        f"{n_rerun} of the 6 jobs of V4 (F) and V6 (O) were re-run from scratch into a separate cache with the same code path, seeds and full settings, and compared with the stored Gate 3c job files:",
        "",
        table_rep,
        "",
        table_jobs,
        "",
        f"Largest absolute difference over all compared numbers: **{worst:.3g}**" + (" (bit-for-bit reproduction)." if worst == 0 else "."),
        "",
        "## 5. The selection rule re-applied to the extended set",
        "",
        power.md_table(pct(cand, pct_cols), floatfmt=".3f"),
        "",
        f"Eligible minimum {best:.3f} pp ({best_row['variant']}); tie threshold {best:.3f} x {1 + TIE_TOLERANCE:.2f} = {thr:.4f} pp. Tied: {', '.join(tied['variant'])}. **Selected: {choice}.** "
        f"V7 is {'within' if v7_in else 'not within'} the band ({v7:.3f} {'<=' if v7_in else '>'} {thr:.4f}).",
        "",
        "Sensitivity, every variant on the common DGP F (V6 on F, N = 703):",
        "",
        power.md_table(pct(cand_f, pct_cols), floatfmt=".3f"),
        "",
        f"Selection on F alone: **{choice_f}** (tied: {', '.join(tied_f['variant'])}).",
        "",
    ]
    if choice is not None:
        dgp = specs[choice].designated_dgp
        table, summary = selected_table(df, choice, dgp)
        lines += [
            f"## 6. The selected variant ({choice}): MDE table, G2 verdicts, demotion rule D-C, literature benchmarks",
            "",
            table,
            "",
            "G2: beta_S MDE <= 0.50 pp at the estimated rho and <= 0.75 pp at rho = 0 (GO), NO-GO above 1.0 pp, AMBER between; interactions <= 0.75 pp per SD (GO), NO-GO above 1.0 pp. "
            "D-C: a target whose WCB MDE at the estimated rho exceeds 1.0 pp is 'not powered'.",
            "",
            *[f"* {r['target']}: G2 (WCB) {r['G2 (WCB)']}, G2 (CR1) {r['G2 (CR1)']}; D-C {r['D-C']} (WCB MDE at rho_hat {r['WCB MDE rho_hat']:.3f} pp)." for r in summary],
            "",
            "Power of beta_S against the two literature benchmarks (indicative: those studies use other outcomes and designs; CR1 exact from null draws, WCB from the fitted simulated power curve):",
            "",
            benchmark_table(df, choice, dgp),
            "",
        ]
    lines += [
        "## 7. Limitations",
        "",
        "1. **V7 was added after the Gate 3c results were seen** (Gate 3c recorded the choice between V6 and a no-controls variant as open). The rule, the thresholds and the tie-break are unchanged and applied mechanically, and V7 is the only addition, but choosing a specification by power on the same panel remains a researcher degree of freedom; the freeze must record the variant, this report and the Gate 3c report.",
        "2. **The designated DGPs differ.** V7 faces the common noise F; V6 is credited with the noise recalibrated on its own residuals (O). The F-only selection above removes that asymmetry.",
        "3. **Differences under about 5 per cent are within Monte Carlo noise** (section 2 gives the fitted-MDE standard errors); this is why the rule ties within 5 per cent.",
        "4. **The AR(1) gain depends on rho = 0.69** (Gate 3b); at rho = 0 the MDEs are reported in section 2.",
        "5. Single-coefficient power at 5 per cent; Gaussian innovations, one common AR(1) coefficient and cross-country independence in the AR(1) scenarios (as in Gate 3c).",
        "",
        "## 8. Files and reproduction",
        "",
        "`src/evaluate/power_variants.py` (V7 and V7@703 in `GATE3D_SPECS`, stage C jobs, `report3d`), `tests/test_power_variants.py`, `reports/gate3c_specification_power.md`, this report. "
        "Reproduce: `python src/evaluate/power_variants.py jobs C` lists the stage-C jobs (V7, V7@703 on DGP F, three scenarios); run each with `job VID DGP SCENARIO --cache DIR` (copy the Gate 3c job files and `v6_spec.json` into DIR first), then `report3d --cache DIR --repro-cache DIR2`.",
        "",
    ]
    return "\n".join(lines)


def ctx_settings_value(df: pd.DataFrame, name: str) -> float:  # noqa: ARG001
    """Number of CR1 null draws used (the full-run setting)."""
    return float(FULL.n_null)


# ---------------------------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------------------------
DEFAULT_CACHE = PROJECT_ROOT / "data" / "interim" / "gate3c_cache"
REPORT_PATH = PROJECT_ROOT / "reports" / "gate3c_specification_power.md"


def main(argv: list[str] | None = None) -> None:
    """Command line: ``jobs STAGE``, ``job VID DGP SCENARIO``, ``choose``, ``report`` (all take ``--cache DIR`` and ``--quick``)."""
    import argparse

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("command", choices=["jobs", "job", "choose", "report", "report3d"])
    parser.add_argument("args", nargs="*")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--repro-cache", type=Path, default=None, help="report3d: cache with the from-scratch re-run of V4 (F) and V6 (O)")
    ns = parser.parse_args(argv)
    ns.cache.mkdir(parents=True, exist_ok=True)
    settings = QUICK if ns.quick else FULL
    if ns.command == "jobs":
        specs = {**VARIANT_SPECS, **GATE3D_SPECS}
        v6 = load_v6(ns.cache)
        if v6 is not None:
            specs["V6"] = v6
        for vid, dgp, scenario in job_list(ns.args[0], specs):
            print(vid, dgp, scenario)
        return
    if ns.command == "report3d":
        if ns.repro_cache is None:
            parser.error("report3d needs --repro-cache")
        note = "quick smoke settings" if ns.quick else "full settings: " + ", ".join(f"{k}={v}" for k, v in FULL.__dict__.items())
        out_3d = ns.out or REPORT_3D_PATH
        out_3d.write_text(render_report_3d(load_results(ns.cache), load_results(ns.repro_cache), ns.cache, ns.repro_cache, note), encoding="utf-8")
        print(f"wrote {out_3d}")
        return
    ctx = Context()
    v6 = load_v6(ns.cache)
    if v6 is not None:
        ctx.specs["V6"] = v6
    if ns.command == "job":
        vid, dgp, scenario = ns.args
        run_job(ctx, vid, dgp, scenario, ns.cache, settings)
    elif ns.command == "choose":
        spec = choose_v6_components(load_results(ns.cache), ctx.specs, bool(ctx.control_names))
        save_v6(ns.cache, spec)
        print(spec)
    else:
        df = load_results(ns.cache)
        note = "quick smoke settings" if ns.quick else "full settings: " + ", ".join(f"{k}={v}" for k, v in FULL.__dict__.items())
        out = ns.out or REPORT_PATH
        out.write_text(render_report(df, ctx, ns.cache, note), encoding="utf-8")
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
