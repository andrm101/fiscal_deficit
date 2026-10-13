"""Pre-specified robustness and diagnostics suite for the M1 confirmatory result (``docs/robustness_spec.md``, sections A-E).

NEW CODE ONLY. Nothing in the frozen files is edited; the pieces of the headline (``m1.load_real_panel``, the design, ``GlsEstimator``,
``wild_bootstrap_pvalues``, the bootstrap-t intervals, ``holm``, ``classify_interval``) are reused. The real panel is read only through
the guarded loader ``m1.load_real_panel`` (git tag ``preregistration-v1`` required; the tag lookup is read-only).

Rules fixed in ``docs/robustness_spec.md`` and kept here
* every specification is reported (estimate, 95% interval, p-value where defined, inference method, N, the pre-registered three-way
  reading with SESOI 0.5 pp, and the sign relative to the headline); nothing is dropped, ranked or chosen; failures are reported as such;
* diagnostics are reported and never used to choose a specification;
* results are associations (scheduled elections are predetermined, not exogenous).

Sections
* A  inference sensitivities: OLS-FE baseline (CR1, wild-cluster bootstrap-t), Driscoll-Kraay (m = 2, 4), two-way clustering,
     CCE-lite / CCE-full (CR1, wild bootstrap), V7 + CCE, residual cross-section dependence (Pesaran CD) before / after CCE
* B  diagnostics: modified Wald, Wooldridge, CIPS, VIF, Hausman/Mundlak, binned linearity and common support, lead placebo
* C  sample variants of V7
* D  definition variants of V7
* E  outputs (markdown, json, forest plot)

Estimator conventions (documented choices where the specification leaves a free parameter)
* Driscoll-Kraay (Driscoll & Kraay 1998) on the OLS two-way fixed-effects design, Bartlett kernel ``w_j = 1 - j / (m + 1)``,
  ``Omega = Gamma_0 + sum_{j=1}^m w_j (Gamma_j + Gamma_j')`` with ``Gamma_j = sum_t S_t S_{t-j}'`` and ``S_t`` the sum over the countries
  present in year ``t`` of ``x~_it u_it`` (``x~`` = regressors after partialling out country and year effects). The reported variance
  is ``c_DK (X~'X~)^-1 Omega (X~'X~)^-1`` with the small-sample factor ``c_DK = T / (T - 1) * (N - 1) / (N - K)`` (the CR1 form with the
  time periods as clusters, K = ``Design.k_params``), critical values t(T - 1). The unscaled sandwich (``c_DK = 1``) equals
  ``linearmodels.PanelOLS(..., cov_type='kernel')`` up to linearmodels' own factor ``n / (n - extra_df)``; the cross-check removes it.
* Two-way clustering (Cameron, Gelbach & Miller 2011): ``V = c_G V_G + c_T V_T - c_GT V_GT`` with ``c_G = G / (G - 1) (N - 1) / (N - K)``,
  ``c_T = T / (T - 1) (N - 1) / (N - K)`` and ``c_GT = N / (N - K)``; if ``V`` is not positive semi-definite its negative eigenvalues are set to zero.
  Critical values t(min(G, T) - 1).
* CCE (Pesaran 2006, pooled version, country-specific coefficients on the cross-sectional averages (CSAs)): CSAs are year means over the
  countries present that year; year effects are kept. For every CSA variable the sum over countries of ``d_i * csa_t`` equals ``csa_t``,
  an exact linear combination of the year dummies, so one country's column per CSA variable is dropped (the last country in code
  order); any further exactly collinear columns found by a sequential QR are dropped and listed.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import warnings
from pathlib import Path
from typing import Any

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")  # the batched small solves of the GLS engine are 100-1000x slower with many BLAS threads
import numpy as np
import pandas as pd
from scipy import stats

try:  # numpy may already have been imported by the caller: limit the BLAS thread pool explicitly
    from threadpoolctl import threadpool_limits

    threadpool_limits(limits=1)
except ImportError:  # pragma: no cover
    pass

_SRC = Path(__file__).resolve().parents[2]
for _sub in ("models/py", "evaluate", "normalize", "features"):
    sys.path.insert(0, str(_SRC / _sub))
import m1  # noqa: E402
import power  # noqa: E402
import power_variants as pv  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RESULTS_DIR = PROJECT_ROOT / "reports" / "results"
FIGURES_DIR = PROJECT_ROOT / "reports" / "figures"
JSON_PATH = RESULTS_DIR / "robustness.json"
MD_PATH = RESULTS_DIR / "robustness.md"
FOREST_PATH = FIGURES_DIR / "robustness_forest.png"
HEADLINE_JSON = RESULTS_DIR / "m1_confirmatory.json"
FREEZE_MANIFEST = PROJECT_ROOT / "docs" / "freeze_manifest.json"
CALENDAR_CSV = PROJECT_ROOT / "data" / "interim" / "election_calendar_eu27.csv"

B_MAIN = 9_999
B_LOCO = 999
SEED_KEY = m1.SEED_KEY
TARGETS = ("beta_S", "gamma_B", "gamma_W")
TESTED = ("beta_S", "gamma_B")
GROUPS = ("A", "C", "D")
SOURCE_LINE = "Source: European Commission, AMECO Spring 2026 (UBLGBP); ETAD; ParlGov; Eurostat; author's calculations"
CCE_PARAM_BUDGET = 1.5e7  # k^2 * batch cap for the generalised-least-squares normal equations (memory)


# ---------------------------------------------------------------------------------------------
# Headline, panel, readings
# ---------------------------------------------------------------------------------------------
def load_headline(path: Path = HEADLINE_JSON) -> dict[str, Any]:
    """The pre-registered V7 result (``reports/results/m1_confirmatory.json``) as a dictionary."""
    return json.loads(path.read_text(encoding="utf-8"))


def load_panel() -> tuple[pd.DataFrame, str]:
    """Confirmatory extract (715 rows) of the gold panel through the guarded loader (tag ``preregistration-v1`` must exist)."""
    return m1.load_real_panel()


def sorted_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Rows sorted by country and year, index reset (the order of every design)."""
    return frame.sort_values(["eurostat_code", "year"]).reset_index(drop=True)


def target_entry(name: str, estimate: float, lo: float, hi: float, p: float | None, se: float | None, headline: dict[str, Any], sesoi: float) -> dict[str, Any]:
    """One target of one specification: estimate, interval, p, reading (tested targets only) and sign relative to the headline."""
    entry: dict[str, Any] = {"estimate": float(estimate), "se": None if se is None else float(se), "ci_lo": float(lo), "ci_hi": float(hi),
                             "p": None if p is None else float(p)}
    head = headline["targets"][name]["estimate"]
    entry["same_sign_as_headline"] = bool(np.sign(estimate) == np.sign(head))
    if name in TESTED:
        excludes, equivalent = m1.interval_flags(float(lo), float(hi), sesoi)
        entry.update(excludes_zero=excludes, equivalent_within_sesoi=equivalent, reading=m1.classify_interval(float(lo), float(hi), sesoi))
    else:
        entry.update(excludes_zero=None, equivalent_within_sesoi=None, reading=None)
    return entry


def make_row(spec_id: str, group: str, label: str, estimator: str, inference: str, n_obs: int, n_clusters: int, targets: dict[str, dict[str, Any]],
             note: str = "", extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """A reported specification."""
    return {"id": spec_id, "group": group, "label": label, "estimator": estimator, "inference": inference, "n_obs": int(n_obs), "n_clusters": int(n_clusters),
            "status": "ok", "note": note, "targets": targets, "extra": extra or {}}


def failed_row(spec_id: str, group: str, label: str, estimator: str, inference: str, error: BaseException) -> dict[str, Any]:
    """A specification that could not be estimated: reported as such, never dropped."""
    return {"id": spec_id, "group": group, "label": label, "estimator": estimator, "inference": inference, "n_obs": None, "n_clusters": None,
            "status": "failed", "note": "", "error": f"{type(error).__name__}: {error}", "targets": {}, "extra": {}}


# ---------------------------------------------------------------------------------------------
# Estimators and bootstrap inference
# ---------------------------------------------------------------------------------------------
class BatchedGls(pv.GlsEstimator):
    """``GlsEstimator`` whose default column batch is capped so that wide designs (CCE-full, k > 300) stay inside memory.

    Pure memory management: the arithmetic is the frozen engine's; results do not depend on the batch size.
    """

    def __init__(self, design: power.Design, **kwargs: Any) -> None:
        super().__init__(design, **kwargs)
        self.default_batch = int(max(10, min(pv.FIT_BATCH, CCE_PARAM_BUDGET / float(self.k) ** 2)))

    def fit(self, y: np.ndarray, names: list[str] | None = None, want_resid: bool = False, batch: int | None = None):  # type: ignore[override]
        return super().fit(y, names, want_resid, self.default_batch if batch is None else batch)

    def restricted(self, target: str) -> "BatchedGls":  # type: ignore[override]
        if target not in self._restricted:
            design_r = pv.drop_column(self.design, self.design.targets[target], f"{self.design.label} (no {target})")
            self._restricted[target] = BatchedGls(design_r, wls=self.wls, ar1=self.ar1, winsor=self.winsor)
        return self._restricted[target]


def m1_design(frame: pd.DataFrame, label: str = "M1", **kwargs: Any) -> power.Design:
    """Headline design (``build_variant_design(frame, 'M1', era=True, control_names=())``) on ``frame``; keyword arguments are passed through."""
    kwargs.setdefault("era", True)
    kwargs.setdefault("control_names", ())
    return pv.build_variant_design(frame, label, **kwargs)


def v7_estimator(design: power.Design, winsor: bool = False) -> BatchedGls:
    """V7: feasible WLS plus AR(1) feasible GLS (Prais-Winsten, Nickell-corrected rho)."""
    return BatchedGls(design, wls=True, ar1=True, winsor=winsor)


def ols_estimator(design: power.Design) -> BatchedGls:
    """Plain two-way fixed-effects OLS in the same engine (CR1 identical to ``power.estimate``)."""
    return BatchedGls(design)


def bootstrap_block(est: pv.GlsEstimator, n_boot: int, targets: tuple[str, ...] = TARGETS, seed_key: int = SEED_KEY, tested: tuple[str, ...] = TESTED) -> dict[str, Any]:
    """Estimates, CR1 results and the null-imposed / unrestricted wild-cluster bootstrap-t of the headline procedure for any estimator.

    Mirrors ``m1.run_m1`` step for step: p-values (tested targets) from ``pv.wild_bootstrap_pvalues`` and bootstrap-t percentile intervals
    from ``m1.unrestricted_bootstrap_t`` with the same Rademacher weights (``seed_key`` 42) and B.
    """
    design = est.design
    y = design.y
    fit = est.fit(y, list(targets))
    out: dict[str, Any] = {"n_boot": n_boot, "targets": {}}
    p_boot = {t: float(pv.wild_bootstrap_pvalues(est, t, y[:, None], weights="rademacher", n_boot=n_boot, seed_key=seed_key)[0]) for t in targets if t in tested}
    t_star = m1.unrestricted_bootstrap_t(est, y, targets, n_boot, seed_key)
    tail = (1.0 - m1.CI_LEVEL) / 2.0
    for t in targets:
        b, se = float(fit[t][0][0]), float(fit[t][1][0])
        q_lo, q_hi = np.quantile(t_star[t], [tail, 1.0 - tail])
        out["targets"][t] = {
            "estimate": b, "cr1_se": se, "cr1_p": float(2 * stats.t.sf(abs(b / se), design.n_clusters - 1)),
            "cr1_lo": b - design.t_crit * se, "cr1_hi": b + design.t_crit * se,
            "boot_lo": b - float(q_hi) * se, "boot_hi": b - float(q_lo) * se, "p_boot": p_boot.get(t),
        }
    return out


def rows_from_block(block: dict[str, Any], headline: dict[str, Any], sesoi: float, *, spec_id: str, group: str, label: str, estimator: str,
                    design: power.Design, note: str = "", extra: dict[str, Any] | None = None, cr1: bool = True, boot: bool = True) -> list[dict[str, Any]]:
    """The CR1 t(G-1) row and the wild-cluster bootstrap-t row of one fitted estimator."""
    rows = []
    n, g = design.n_obs, design.n_clusters
    extra = dict(extra or {})
    extra["cr1_transparency"] = {t: {k: v[k] for k in ("cr1_se", "cr1_p", "cr1_lo", "cr1_hi")} for t, v in block["targets"].items()}
    if cr1:
        tg = {t: target_entry(t, v["estimate"], v["cr1_lo"], v["cr1_hi"], v["cr1_p"] if t in TESTED else None, v["cr1_se"], headline, sesoi) for t, v in block["targets"].items()}
        rows.append(make_row(f"{spec_id}|cr1", group, label, estimator, f"CR1 t({g - 1})", n, g, tg, note, extra))
    if boot:
        tg = {t: target_entry(t, v["estimate"], v["boot_lo"], v["boot_hi"], v["p_boot"], v["cr1_se"], headline, sesoi) for t, v in block["targets"].items()}
        rows.append(make_row(f"{spec_id}|wcb", group, label, estimator, f"wild-cluster bootstrap-t, B={block['n_boot']}", n, g, tg, note, extra))
    return rows


# ---------------------------------------------------------------------------------------------
# OLS algebra: Driscoll-Kraay and two-way clustering
# ---------------------------------------------------------------------------------------------
class FeOls:
    """Two-way fixed-effects OLS pieces of a :class:`power.Design`: partialled-out regressors ``xt``, ``(xt'xt)^-1``, coefficients, residuals."""

    def __init__(self, design: power.Design, y: np.ndarray | None = None) -> None:
        self.design = design
        self.y = design.y if y is None else y
        self.xt = design.x - design.q_fe @ (design.q_fe.T @ design.x)
        self.xtx_inv = np.linalg.inv(self.xt.T @ self.xt)
        self.beta = self.xtx_inv @ (self.xt.T @ self.y)
        self.resid = power.residuals(design, self.y)
        self.scores = self.xt * self.resid[:, None]
        self.n, self.k = design.n_obs, design.k_params

    def index(self, target: str) -> int:
        """Position of a target's regressor among the regressors."""
        return self.design.x_names.index(self.design.targets[target])

    def cr1(self) -> np.ndarray:
        """Country-clustered CR1 covariance (same as ``power.estimate``)."""
        d = self.design
        s = np.add.reduceat(self.scores, d.starts, axis=0)
        return d.cr1 * self.xtx_inv @ (s.T @ s) @ self.xtx_inv

    def driscoll_kraay(self, bandwidth: int, small_sample: bool = True) -> np.ndarray:
        """Driscoll-Kraay covariance, Bartlett kernel ``w_j = 1 - j / (bandwidth + 1)``; ``small_sample=False`` returns the bare sandwich."""
        d = self.design
        years = np.unique(d.year)
        if not np.all(np.diff(years) == 1):
            raise ValueError("Driscoll-Kraay needs consecutive years")
        idx = np.searchsorted(years, d.year)
        s_t = np.zeros((len(years), self.scores.shape[1]))
        np.add.at(s_t, idx, self.scores)
        omega = s_t.T @ s_t
        for j in range(1, bandwidth + 1):
            gamma = s_t[j:].T @ s_t[:-j]
            omega = omega + (1.0 - j / (bandwidth + 1.0)) * (gamma + gamma.T)
        factor = len(years) / (len(years) - 1.0) * (self.n - 1.0) / (self.n - self.k) if small_sample else 1.0
        return factor * self.xtx_inv @ omega @ self.xtx_inv

    def two_way(self, small_sample: bool = True, psd_fix: bool = True) -> tuple[np.ndarray, dict[str, Any]]:
        """Cameron-Gelbach-Miller two-way (country, year) covariance with the eigenvalue fix; returns the matrix and a diagnostics dict."""
        d = self.design
        n, k = float(self.n), float(self.k)
        g, years = d.n_clusters, np.unique(d.year)
        t_n = len(years)
        s_g = np.add.reduceat(self.scores, d.starts, axis=0)
        s_t = np.zeros((t_n, self.scores.shape[1]))
        np.add.at(s_t, np.searchsorted(years, d.year), self.scores)
        base = (n - 1.0) / (n - k) if small_sample else 1.0
        c_gt = n / (n - k) if small_sample else 1.0
        c_g = g / (g - 1.0) * base if small_sample else 1.0
        c_t = t_n / (t_n - 1.0) * base if small_sample else 1.0
        v_raw = c_g * (s_g.T @ s_g) + c_t * (s_t.T @ s_t) - c_gt * (self.scores.T @ self.scores)
        cov = self.xtx_inv @ ((v_raw + v_raw.T) / 2.0) @ self.xtx_inv
        cov = (cov + cov.T) / 2.0
        eigval, eigvec = np.linalg.eigh(cov)
        fixed = bool(eigval.min() < 0)
        if fixed and psd_fix:
            cov = (eigvec * np.clip(eigval, 0.0, None)) @ eigvec.T
        return cov, {"psd_fix_applied": fixed, "min_eigenvalue_of_V": float(eigval.min()), "n_negative_eigenvalues": int((eigval < 0).sum())}


def cov_rows(design: power.Design, cov: np.ndarray, ols: FeOls, headline: dict[str, Any], sesoi: float, *, spec_id: str, group: str, label: str,
             inference: str, crit_df: int, note: str = "", extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Row for a covariance-matrix based inference (estimate +- t(crit_df) * se, two-sided t p-value for tested targets)."""
    crit = float(stats.t.ppf(0.975, crit_df))
    tg = {}
    for t in TARGETS:
        i = ols.index(t)
        b, se = float(ols.beta[i]), float(np.sqrt(cov[i, i]))
        p = float(2 * stats.t.sf(abs(b / se), crit_df)) if t in TESTED else None
        tg[t] = target_entry(t, b, b - crit * se, b + crit * se, p, se, headline, sesoi)
    return make_row(spec_id, group, label, "OLS two-way fixed effects (V0)", inference, design.n_obs, design.n_clusters, tg, note, extra)


def dk_crosscheck(design: power.Design, bandwidths: tuple[int, ...] = (2, 4)) -> dict[str, Any]:
    """Compare the numpy Driscoll-Kraay standard errors with ``linearmodels.PanelOLS(entity_effects, time_effects).fit(cov_type='kernel')``.

    linearmodels multiplies the bare sandwich by ``n / (n - df_model)`` (``df_model`` = regressors plus absorbed effects); the comparison applies
    that factor to the numpy sandwich (``small_sample=False``). Returns the largest relative differences (standard errors and coefficients).
    """
    from linearmodels.panel import PanelOLS  # noqa: PLC0415

    fe = FeOls(design)
    idx = pd.MultiIndex.from_arrays([design.codes, design.year], names=["entity", "time"])
    exog = pd.DataFrame(design.x, columns=design.x_names, index=idx)
    y = pd.Series(design.y, index=idx)
    out: dict[str, Any] = {"max_rel_diff_coefficients": None, "bandwidths": {}}
    for m in bandwidths:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = PanelOLS(y, exog, entity_effects=True, time_effects=True).fit(cov_type="kernel", kernel="bartlett", bandwidth=m)
        mine = np.sqrt(np.diag(fe.driscoll_kraay(m, small_sample=False)) * design.n_obs / (design.n_obs - res.df_model))
        lm = res.std_errors.to_numpy()
        out["bandwidths"][str(m)] = {"max_rel_diff_se": float(np.max(np.abs(mine / lm - 1.0))), "linearmodels_df_model": int(res.df_model)}
        out["max_rel_diff_coefficients"] = float(np.max(np.abs(res.params.to_numpy() - fe.beta) / np.maximum(np.abs(fe.beta), 1e-12)))
    return out


# ---------------------------------------------------------------------------------------------
# Common correlated effects
# ---------------------------------------------------------------------------------------------
def csa_columns(frame: pd.DataFrame, regressors: pd.DataFrame, names: list[str]) -> pd.DataFrame:
    """Year means (over the countries present that year) of ``capb`` and of the named regressors, as full-length columns aligned with ``frame``."""
    source = pd.DataFrame({"capb": frame["capb"].to_numpy(float), **{c: regressors[c].to_numpy(float) for c in names if c != "capb"}})
    year = frame["year"].to_numpy()
    return source.groupby(year).transform("mean")


def build_cce_regressors(frame: pd.DataFrame, kind: str) -> tuple[pd.DataFrame, dict[str, float], dict[str, str], dict[str, Any]]:
    """M1 regressors plus the CCE columns ``d_i * csa_t`` (country-specific coefficients) for ``kind`` in {'lite', 'full'}.

    Returns the extended regressor frame, scale, targets and a report (added parameters, dropped columns, rank checks).
    """
    frame = sorted_frame(frame)
    base, scale, targets = pv.variant_regressors(frame, era=True, control_names=())
    if kind == "lite":
        sources = ["capb", "W_S"]
    elif kind == "full":
        sources = ["capb", *base.columns]
    else:
        raise ValueError(kind)
    csa = csa_columns(frame, base, sources)
    codes = frame["eurostat_code"].to_numpy()
    countries = list(dict.fromkeys(codes))
    cols: dict[str, np.ndarray] = {}
    dropped: list[str] = []
    for s in sources:
        for pos, c in enumerate(countries):
            name = f"CSA[{s}]x{c}"
            if pos == len(countries) - 1:
                dropped.append(f"{name} (sum over countries of d_i*csa_t = csa_t, exact combination of the year dummies)")
                continue
            cols[name] = (codes == c).astype(float) * csa[s].to_numpy(float)
    extended = pd.concat([base, pd.DataFrame(cols)], axis=1)
    # further exact dependencies against fixed effects and the base regressors, in the order [country dummies, year dummies, base, csa]
    n = len(frame)
    years = np.unique(frame["year"].to_numpy())
    g = len(countries)
    fe = np.zeros((n, g + len(years) - 1))
    fe[np.arange(n), pd.factorize(codes)[0]] = 1.0
    ycol = np.searchsorted(years, frame["year"].to_numpy())
    keep = ycol > 0
    fe[np.arange(n)[keep], g + ycol[keep] - 1] = 1.0
    mat = np.hstack([fe, extended.to_numpy(float)])
    r = np.linalg.qr(mat, mode="r")
    norms = np.linalg.norm(mat, axis=0)
    dependent = np.flatnonzero(np.abs(np.diag(r)) <= 1e-9 * np.maximum(norms, 1.0))
    extra_dropped = []
    for j in dependent:
        pos = j - fe.shape[1]
        if pos < 0:
            raise ValueError("fixed effects are rank deficient")
        extra_dropped.append(extended.columns[pos])
    if extra_dropped:
        if any(c in base.columns for c in extra_dropped):
            raise ValueError(f"a base M1 regressor is collinear in the CCE design: {extra_dropped}")
        extended = extended.drop(columns=extra_dropped)
        dropped.extend(f"{c} (exactly collinear in sequential QR)" for c in extra_dropped)
    n_added = extended.shape[1] - base.shape[1]
    n_params = fe.shape[1] + extended.shape[1]
    report = {"kind": kind, "csa_variables": sources, "n_csa_variables": len(sources), "added_parameters": n_added, "n_obs": n,
              "n_parameters_total": n_params, "residual_df": n - n_params, "dropped_columns": dropped,
              "df_exhausted": bool(n - n_params <= 0), "added_to_n_ratio": n_added / n}
    return extended, scale, targets, report


def cce_design(frame: pd.DataFrame, kind: str) -> tuple[power.Design, dict[str, Any]]:
    """:class:`power.Design` of the CCE-augmented M1 model and its report."""
    frame = sorted_frame(frame)
    regressors, scale, targets, report = build_cce_regressors(frame, kind)
    return power.build_design(frame, label=f"M1 + CCE-{kind}", regressors=regressors, targets=targets, scale=scale), report


# ---------------------------------------------------------------------------------------------
# Residual cross-section dependence (Pesaran 2015 CD)
# ---------------------------------------------------------------------------------------------
def _pesaran_cd_loop(grid: np.ndarray, min_overlap: int = power.MIN_CD_OVERLAP) -> dict[str, float]:
    """Reference (pair-by-pair) implementation of :func:`pesaran_cd`, used by the tests to check the vectorised version."""
    g = grid.shape[1]
    rho, weight = [], []
    for i in range(g):
        for j in range(i + 1, g):
            ok = ~np.isnan(grid[:, i]) & ~np.isnan(grid[:, j])
            if ok.sum() >= min_overlap:
                a, b = grid[ok, i], grid[ok, j]
                if a.std() > 0 and b.std() > 0:
                    rho.append(float(np.corrcoef(a, b)[0, 1]))
                    weight.append(math.sqrt(ok.sum()))
    rho_a, w_a = np.array(rho), np.array(weight)
    return {"cd": float((w_a * rho_a).sum() / math.sqrt(len(rho_a))), "mean_corr": float(rho_a.mean()), "mean_abs_corr": float(np.abs(rho_a).mean()), "n_pairs": float(len(rho_a))}


def _pairwise_correlations(grid: np.ndarray, min_overlap: int) -> tuple[np.ndarray, np.ndarray]:
    """Upper-triangle pairwise correlations over common years and the common-year counts (vectorised, NaN-aware)."""
    present = ~np.isnan(grid)
    x = np.where(present, grid, 0.0)
    m = present.astype(float)
    n_ij = m.T @ m
    s1 = x.T @ m  # s1[i, j] = sum over common years of x_i
    s2 = (x**2).T @ m
    cross = x.T @ x
    with np.errstate(invalid="ignore", divide="ignore"):
        mean_i, mean_j = s1 / n_ij, s1.T / n_ij
        var_i, var_j = s2 / n_ij - mean_i**2, s2.T / n_ij - mean_j**2
        corr = (cross / n_ij - mean_i * mean_j) / np.sqrt(var_i * var_j)
    iu = np.triu_indices(grid.shape[1], k=1)
    r, n = corr[iu], n_ij[iu]
    ok = (n >= min_overlap) & np.isfinite(r)
    return r[ok], n[ok]


def pesaran_cd(grid: np.ndarray, min_overlap: int = power.MIN_CD_OVERLAP) -> dict[str, float]:
    """Pesaran (2015) CD test of cross-sectional independence on a (years x units) residual grid with NaN for missing cells.

    ``CD = sum_{i<j} sqrt(T_ij) rho_ij / sqrt(P)`` with ``rho_ij`` the correlation over the ``T_ij`` common years and ``P`` the number of
    unit pairs with ``T_ij >= min_overlap`` (``P = N (N - 1) / 2`` gives the textbook ``sqrt(2 / (N (N - 1))) sum sqrt(T_ij) rho_ij``). Under
    independence ``CD ~ N(0, 1)`` asymptotically. Also returns the mean and the mean absolute pairwise correlation.

    Caveat for residuals of a model with year effects: removing the year means makes the average pairwise correlation equal to about
    ``-1 / (N - 1)`` even under independence, so the statistic is shifted negative; :func:`cd_null` simulates the matching null.
    """
    rho, n_ij = _pairwise_correlations(grid, min_overlap)
    cd = float((np.sqrt(n_ij) * rho).sum() / math.sqrt(len(rho)))
    return {"cd": cd, "p_value": float(2 * stats.norm.sf(abs(cd))), "mean_corr": float(rho.mean()), "mean_abs_corr": float(np.abs(rho).mean()),
            "n_pairs": float(len(rho)), "share_positive": float((rho > 0).mean())}


def cd_null(design: power.Design, rho: float = 0.0, sigma: np.ndarray | None = None, n_sim: int = 500, seed: int = 0) -> dict[str, float]:
    """Null distribution of CD and of the mean absolute correlation for INDEPENDENT errors projected on the residual space of ``design``.

    ``u = (I - Q_z Q_z') e`` with ``e`` independent across countries: iid ``N(0, 1)`` when ``rho = 0``, otherwise stationary AR(1)
    with persistence ``rho`` and country SDs ``sigma`` (``power.ArNoise``). The projection removes year means (and the CCE columns), which
    makes the average pairwise correlation about ``-1 / (N - 1)`` and pins the sum of the pairwise correlations, so the null of CD is
    centred far from zero with a small spread: read the observed values against this null, not against N(0, 1).
    """
    rng = np.random.default_rng(np.random.SeedSequence([42, 8100, seed]))
    if rho == 0.0 and sigma is None:
        noise = rng.standard_normal((design.n_obs, n_sim))
    else:
        noise = power.ArNoise(design, np.ones(design.n_clusters) if sigma is None else sigma, rho).draw(rng, n_sim)
    resid = power.residuals(design, noise)
    cds, absr = np.empty(n_sim), np.empty(n_sim)
    for s in range(n_sim):
        out = pesaran_cd(power.residual_grid(design, resid[:, s]))
        cds[s], absr[s] = out["cd"], out["mean_abs_corr"]
    return {"cd_mean": float(cds.mean()), "cd_sd": float(cds.std(ddof=1)), "mean_abs_corr": float(absr.mean()), "mean_abs_corr_sd": float(absr.std(ddof=1)), "rho": float(rho), "n_sim": n_sim}


def residual_dependence(design: power.Design, resid: np.ndarray, nulls: dict[str, dict[str, float]] | None = None) -> dict[str, Any]:
    """Pesaran CD of a residual vector aligned with ``design`` (rows sorted by country, year), optionally with the simulated nulls beside it."""
    out: dict[str, Any] = pesaran_cd(power.residual_grid(design, resid))
    for name, null in (nulls or {}).items():
        out[f"null_{name}"] = null
        out[f"excess_mean_abs_corr_vs_{name}"] = out["mean_abs_corr"] - null["mean_abs_corr"]
    return out


def dependence_nulls(design: power.Design, rho: float, sigma: np.ndarray, n_sim: int = 500) -> dict[str, dict[str, float]]:
    """Both nulls (iid errors; AR(1) errors with the estimated persistence and country SDs) for a design."""
    return {"iid": cd_null(design, n_sim=n_sim), "ar1": cd_null(design, rho=rho, sigma=sigma, n_sim=n_sim, seed=1)}


def v7_residuals(est: pv.GlsEstimator) -> tuple[np.ndarray, np.ndarray]:
    """V7 residuals: raw ``y - Z theta`` and the Prais-Winsten-transformed, weighted residuals ``sqrt(w_i) (P u)`` that the GLS treats as iid."""
    y = est.design.y[:, None]
    _, resid = est.fit(y, [], want_resid=True)
    _, _, rho, w = est.first_stage(y)
    transformed = est._transform(resid, rho) * np.sqrt(w.T[est.design.country_idx])
    return resid[:, 0], transformed[:, 0]


# ---------------------------------------------------------------------------------------------
# Section A
# ---------------------------------------------------------------------------------------------
def _log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def run_section_a(frame: pd.DataFrame, headline: dict[str, Any], sesoi: float, n_boot: int = B_MAIN) -> dict[str, Any]:
    """Section A: OLS-FE baseline, Driscoll-Kraay, two-way clustering, CCE, V7 + CCE, and the residual dependence diagnostics."""
    rows: list[dict[str, Any]] = []
    frame = sorted_frame(frame)
    design = m1_design(frame, "OLS-FE (V0)")
    ols_est = ols_estimator(design)
    y = design.y
    fe = FeOls(design)
    check = [float(fe.beta[fe.index(t)] - ols_est.fit(y, [t])[t][0][0]) for t in TARGETS]
    if max(abs(c) for c in check) > 1e-9:
        raise AssertionError(f"FeOls differs from the engine: {check}")

    def guarded(spec_id: str, label: str, estimator: str, inference: str, fn) -> None:
        t0 = time.time()
        try:
            rows.extend(fn())
            _log(f"A {spec_id} done in {time.time() - t0:.1f}s")
        except Exception as error:  # noqa: BLE001  (a failure is a result: reported, never hidden)
            rows.append(failed_row(spec_id, "A", label, estimator, inference, error))
            _log(f"A {spec_id} FAILED: {type(error).__name__}: {error}")

    # A1 OLS baseline
    def a1() -> list[dict[str, Any]]:
        block = bootstrap_block(ols_est, n_boot)
        return rows_from_block(block, headline, sesoi, spec_id="A1-ols", group="A", label="OLS two-way FE baseline (V0)", estimator="OLS two-way fixed effects (V0)", design=design)

    guarded("A1-ols", "OLS two-way FE baseline (V0)", "OLS", "CR1 / wild bootstrap", a1)

    # A2 Driscoll-Kraay
    dk_info: dict[str, Any] = {}
    for m in (2, 4):
        def a2(m=m) -> list[dict[str, Any]]:
            cov = fe.driscoll_kraay(m)
            dk_info[m] = {"bandwidth": m, "T": int(len(np.unique(design.year))), "small_sample_factor": float(len(np.unique(design.year)) / (len(np.unique(design.year)) - 1.0) * (fe.n - 1.0) / (fe.n - fe.k))}
            return [cov_rows(design, cov, fe, headline, sesoi, spec_id=f"A2-dk{m}", group="A", label=f"Driscoll-Kraay, Bartlett kernel, m = {m}",
                             inference=f"Driscoll-Kraay (m={m}), t({len(np.unique(design.year)) - 1})", crit_df=len(np.unique(design.year)) - 1, extra=dk_info[m])]

        guarded(f"A2-dk{m}", f"Driscoll-Kraay m={m}", "OLS", "DK", a2)

    # A3 two-way clustering
    def a3() -> list[dict[str, Any]]:
        cov, info = fe.two_way()
        return [cov_rows(design, cov, fe, headline, sesoi, spec_id="A3-twoway", group="A", label="Two-way clustering (country, year), Cameron-Gelbach-Miller 2011",
                         inference=f"two-way cluster, t({min(design.n_clusters, len(np.unique(design.year))) - 1})", crit_df=min(design.n_clusters, len(np.unique(design.year))) - 1, extra=info)]

    guarded("A3-twoway", "Two-way clustering", "OLS", "two-way", a3)

    # A4 / A5 CCE
    cce_reports: dict[str, Any] = {}
    cd_rows: list[dict[str, Any]] = []
    v7_head = v7_estimator(design)
    _, u1, rho_arr, _ = v7_head.first_stage(y[:, None])
    rho_hat = float(rho_arr[0])
    sigma_i = np.sqrt(np.add.reduceat(u1[:, 0] ** 2, design.starts) / design.counts)
    for kind in ("lite", "full"):
        try:
            cdes, rep = cce_design(frame, kind)
            cce_reports[kind] = rep
            _log(f"A CCE-{kind}: +{rep['added_parameters']} parameters, residual df {rep['residual_df']}")
        except Exception as error:  # noqa: BLE001
            for sid, est_name in ((f"A4-cce{kind}", "OLS + CCE"), (f"A5-v7cce{kind}", "V7 + CCE")):
                rows.append(failed_row(sid, "A", f"{est_name}-{kind}", est_name, "-", error))
            cce_reports[kind] = {"kind": kind, "error": f"{type(error).__name__}: {error}"}
            continue

        def a4(cdes=cdes, rep=rep, kind=kind) -> list[dict[str, Any]]:
            est = ols_estimator(cdes)
            block = bootstrap_block(est, n_boot)
            ex = {k: rep[k] for k in ("added_parameters", "n_parameters_total", "residual_df", "df_exhausted", "dropped_columns")}
            r = rows_from_block(block, headline, sesoi, spec_id=f"A4-cce{kind}", group="A", label=f"OLS two-way FE + CCE-{kind}", estimator=f"OLS + CCE-{kind}", design=cdes, extra=ex,
                                note=f"{rep['added_parameters']} added parameters, residual df {rep['residual_df']}")
            null = dependence_nulls(cdes, rho_hat, sigma_i)
            cd_rows.append({"model": f"OLS-FE + CCE-{kind}", **residual_dependence(cdes, power.residuals(cdes, cdes.y), null)})
            return r

        guarded(f"A4-cce{kind}", f"OLS + CCE-{kind}", "OLS + CCE", "CR1/WCB", a4)

        def a5(cdes=cdes, rep=rep, kind=kind) -> list[dict[str, Any]]:
            est = v7_estimator(cdes)
            block = bootstrap_block(est, n_boot)
            ex = {k: rep[k] for k in ("added_parameters", "n_parameters_total", "residual_df", "df_exhausted", "dropped_columns")}
            r = rows_from_block(block, headline, sesoi, spec_id=f"A5-v7cce{kind}", group="A", label=f"V7 + CCE-{kind}", estimator=f"V7 + CCE-{kind}", design=cdes, extra=ex, cr1=False,
                                note=f"{rep['added_parameters']} added parameters, residual df {rep['residual_df']}")
            raw, pw = v7_residuals(est)
            null = dependence_nulls(cdes, rho_hat, sigma_i)
            cd_rows.append({"model": f"V7 + CCE-{kind} (raw residuals)", **residual_dependence(cdes, raw, null)})
            cd_rows.append({"model": f"V7 + CCE-{kind} (Prais-Winsten weighted residuals)", **residual_dependence(cdes, pw, null)})
            return r

        guarded(f"A5-v7cce{kind}", f"V7 + CCE-{kind}", "V7 + CCE", "CR1/WCB", a5)

    # A6 dependence before CCE
    null0 = dependence_nulls(design, rho_hat, sigma_i)
    before = [{"model": "OLS-FE (V0)", **residual_dependence(design, fe.resid, null0)}]
    raw, pw = v7_residuals(v7_head)
    before += [{"model": "V7 (raw residuals)", **residual_dependence(design, raw, null0)}, {"model": "V7 (Prais-Winsten weighted residuals)", **residual_dependence(design, pw, null0)}]
    return {"rows": rows, "rho_hat": rho_hat, "cce": cce_reports, "dependence": before + cd_rows, "driscoll_kraay": dk_info, "dk_crosscheck_real": dk_crosscheck(design)}


# ---------------------------------------------------------------------------------------------
# Section B: diagnostics implemented here because no installed package provides them
# ---------------------------------------------------------------------------------------------
def modified_wald(resid: np.ndarray, starts: np.ndarray, counts: np.ndarray) -> dict[str, float]:
    """Greene's modified Wald test for groupwise heteroskedasticity in the residuals of a fixed-effects model.

    ``W = sum_i (s_i^2 - s^2)^2 / V_i`` with ``s_i^2 = mean_t e_it^2``, ``s^2 = e'e / n`` (pooled variance under H0) and
    ``V_i = sum_t (e_it^2 - s_i^2)^2 / (T_i (T_i - 1))``. Under H0 (equal variances; power also depends on normality)
    ``W ~ chi2(N)`` asymptotically in T.
    """
    e2 = resid**2
    s_i = np.add.reduceat(e2, starts) / counts
    s2 = float(e2.mean())
    dev = (e2 - np.repeat(s_i, counts)) ** 2
    v_i = np.add.reduceat(dev, starts) / (counts * (counts - 1.0))
    w = float(((s_i - s2) ** 2 / v_i).sum())
    g = len(starts)
    return {"statistic": w, "df": g, "p_value": float(stats.chi2.sf(w, g)), "sigma_i_min": float(np.sqrt(s_i.min())), "sigma_i_max": float(np.sqrt(s_i.max()))}


def modified_wald_mc(resid: np.ndarray, design: power.Design, n_sim: int = 2_000, seed: int = 0) -> dict[str, float]:
    """Modified Wald statistic with a Monte Carlo p-value under iid normal homoskedastic errors pushed through the design's residual maker.

    The statistic is known to over-reject when ``T`` is small (the variance of the squared residuals is estimated from ``T`` points per unit): with
    ``T = 27`` the asymptotic chi-square p-value is not size-correct. The simulated null uses the same layout (unit counts, fixed effects and
    regressors), so the p-value is calibrated for iid normal errors; it does not address non-normality or serial correlation.
    """
    obs = modified_wald(resid, design.starts, design.counts)
    rng = np.random.default_rng(np.random.SeedSequence([42, 8200, seed]))
    sims = np.empty(n_sim)
    noise = power.residuals(design, rng.standard_normal((design.n_obs, n_sim)))
    for k in range(n_sim):
        sims[k] = modified_wald(noise[:, k], design.starts, design.counts)["statistic"]
    obs["p_value_mc"] = float((1 + (sims >= obs["statistic"]).sum()) / (n_sim + 1))
    obs["null_median_statistic"] = float(np.median(sims))
    obs["null_q95_statistic"] = float(np.quantile(sims, 0.95))
    obs["n_sim"] = n_sim
    return obs


def wooldridge_serial(design: power.Design, y: np.ndarray | None = None) -> dict[str, float]:
    """Wooldridge (2002) / Drukker (2003) serial-correlation test for the fixed-effects model.

    First-difference the model (consecutive years only; year effects become year dummies), take the residuals ``e`` of the
    differenced regression, regress ``e_t`` on ``e_{t-1}`` without a constant, and test ``H0: coefficient = -1/2`` (which holds when
    the levels errors are serially uncorrelated) with a country-clustered standard error, ``F(1, G - 1)``.
    """
    y = design.y if y is None else y
    cur, lag = design.cur_rows, design.lag_rows
    dy = y[cur] - y[lag]
    dx = design.x[cur] - design.x[lag]
    years = np.unique(design.year[cur])
    dummies = (design.year[cur][:, None] == years[None, :]).astype(float)
    z = np.hstack([dx, dummies])
    coef, *_ = np.linalg.lstsq(z, dy, rcond=None)
    e_diff = dy - z @ coef
    e_full = np.full(design.n_obs, np.nan)
    e_full[cur] = e_diff
    rows = cur[~np.isnan(e_full[cur - 1])]
    e_t, e_l = e_full[rows], e_full[rows - 1]
    b = float((e_l * e_t).sum() / (e_l**2).sum())
    v = e_t - b * e_l
    cluster = design.country_idx[rows]
    g_n = design.n_clusters
    score = np.bincount(cluster, weights=e_l * v, minlength=g_n)
    var_b = g_n / (g_n - 1.0) * float((score**2).sum()) / float((e_l**2).sum()) ** 2
    f = (b + 0.5) ** 2 / var_b
    return {"coefficient": b, "se": math.sqrt(var_b), "f_statistic": float(f), "df1": 1, "df2": g_n - 1, "p_value": float(stats.f.sf(f, 1, g_n - 1)), "n_pairs": int(len(rows))}


def cadf_tstat(y: np.ndarray, ybar: np.ndarray, lags: int, trend: bool) -> float:
    """t statistic of ``y_{t-1}`` in the cross-sectionally augmented Dickey-Fuller regression of one unit (Pesaran 2007).

    ``dy_t = a + [c t] + b y_{t-1} + c1 ybar_{t-1} + d0 dybar_t + sum_{l=1}^p (d_l dybar_{t-l} + f_l dy_{t-l}) + e_t`` over the unit's
    contiguous years; ``y`` and ``ybar`` are aligned series (``ybar`` = cross-sectional mean over the units present that year).
    """
    dy, dybar = np.diff(y), np.diff(ybar)
    t_idx = np.arange(lags + 1, len(y))  # positions t with all lags available (dy[t - 1] is the change into t)
    cols = [np.ones(len(t_idx))]
    if trend:
        cols.append(t_idx.astype(float))
    cols += [y[t_idx - 1], ybar[t_idx - 1], dybar[t_idx - 1]]
    for ell in range(1, lags + 1):
        cols += [dybar[t_idx - 1 - ell], dy[t_idx - 1 - ell]]
    x = np.column_stack(cols)
    target = dy[t_idx - 1]
    xtx_inv = np.linalg.inv(x.T @ x)
    coef = xtx_inv @ (x.T @ target)
    resid = target - x @ coef
    sigma2 = float(resid @ resid) / (len(target) - x.shape[1])
    pos = 2 if trend else 1
    return float(coef[pos] / math.sqrt(sigma2 * xtx_inv[pos, pos]))


def cips_statistic(values: np.ndarray, lags: int = 1, trend: bool = False) -> dict[str, Any]:
    """CIPS (Pesaran 2007) on a (years x units) grid with NaN outside each unit's contiguous span: the mean of the unit CADF t statistics."""
    ybar = np.nanmean(values, axis=1)
    stats_i = []
    for i in range(values.shape[1]):
        ok = np.flatnonzero(~np.isnan(values[:, i]))
        if len(ok) == 0:
            continue
        if not np.all(np.diff(ok) == 1):
            raise ValueError("each unit must be observed over a contiguous span of years")
        stats_i.append(cadf_tstat(values[ok, i], ybar[ok], lags, trend))
    return {"cips": float(np.mean(stats_i)), "unit_statistics": [float(s) for s in stats_i], "n_units": len(stats_i)}


def cips_simulated_critical(values: np.ndarray, lags: int, trend: bool, n_sim: int = 1_000, seed: int = 0) -> dict[str, Any]:
    """Finite-sample null distribution of CIPS for the SAME unbalanced layout as ``values``: independent random walks plus one common factor.

    Pesaran's (2007) tabulated critical values exist for balanced panels only; this panel is unbalanced, so the critical values are
    simulated: ``y_it = y_{i,t-1} + gamma_i f_t + e_it`` with ``f_t, e_it ~ N(0, 1)`` and ``gamma_i ~ U(0, 2)``, same cells, same lag rule.
    Left-tail test: reject the unit root when CIPS is below the critical value.
    """
    rng = np.random.default_rng(np.random.SeedSequence([42, 8000, seed]))
    present = ~np.isnan(values)
    t_n, n_u = values.shape
    sims = np.empty(n_sim)
    for s in range(n_sim):
        f = rng.standard_normal(t_n)
        gamma = rng.uniform(0.0, 2.0, size=n_u)
        steps = gamma[None, :] * f[:, None] + rng.standard_normal((t_n, n_u))
        walk = np.cumsum(steps, axis=0)
        grid = np.where(present, walk, np.nan)
        sims[s] = cips_statistic(grid, lags, trend)["cips"]
    return {"crit_1": float(np.quantile(sims, 0.01)), "crit_5": float(np.quantile(sims, 0.05)), "crit_10": float(np.quantile(sims, 0.10)), "n_sim": n_sim,
            "sim_mean": float(sims.mean()), "sims": sims}


def cips_test(values: np.ndarray, lags: int = 1, trend: bool = False, n_sim: int = 1_000, seed: int = 0) -> dict[str, Any]:
    """CIPS statistic, simulated critical values and the simulated left-tail p-value."""
    obs = cips_statistic(values, lags, trend)
    crit = cips_simulated_critical(values, lags, trend, n_sim, seed)
    sims = crit.pop("sims")
    p = float((1 + (sims <= obs["cips"]).sum()) / (len(sims) + 1))
    return {"cips": obs["cips"], "n_units": obs["n_units"], "lags": lags, "trend": trend, "p_value_left_tail": p, **crit,
            "reject_5pct": bool(obs["cips"] < crit["crit_5"]), "unit_statistics_min": min(obs["unit_statistics"]), "unit_statistics_max": max(obs["unit_statistics"])}


def wide_grid(frame: pd.DataFrame, column: str) -> np.ndarray:
    """(years x countries) grid of a column, NaN where the country-year is not in the sample."""
    frame = sorted_frame(frame)
    years = np.sort(frame["year"].unique())
    codes = list(dict.fromkeys(frame["eurostat_code"]))
    grid = np.full((len(years), len(codes)), np.nan)
    grid[np.searchsorted(years, frame["year"].to_numpy()), pd.factorize(frame["eurostat_code"])[0]] = frame[column].to_numpy(float)
    return grid


def vif_table(design: power.Design) -> dict[str, Any]:
    """Variance inflation factors of the M1 regressors: after partialling out the fixed effects (the relevant ones) and on the raw columns."""
    fe = FeOls(design)
    within = np.diag(fe.xtx_inv) * (fe.xt**2).sum(axis=0)
    raw = design.x - design.x.mean(axis=0)
    raw_vif = np.diag(np.linalg.inv(raw.T @ raw)) * (raw**2).sum(axis=0)
    return {"names": list(design.x_names), "vif_within": [float(v) for v in within], "vif_raw": [float(v) for v in raw_vif], "flag_threshold": 5.0,
            "flagged_within": [n for n, v in zip(design.x_names, within) if v > 5.0], "flagged_raw": [n for n, v in zip(design.x_names, raw_vif) if v > 5.0]}


def _sequential_independent(mat: np.ndarray) -> np.ndarray:
    """Indices of the columns that are not exact combinations of earlier ones (sequential QR)."""
    r = np.linalg.qr(mat, mode="r")
    norms = np.linalg.norm(mat, axis=0)
    return np.flatnonzero(np.abs(np.diag(r)) > 1e-9 * np.maximum(norms, 1.0))


def mundlak_hausman(design: power.Design) -> dict[str, Any]:
    """Regression-based (Mundlak / Wooldridge) Hausman test with country-clustered inference.

    Pooled OLS of ``y`` on the M1 regressors, their country means, year dummies and a constant; ``H0``: the coefficients on the country means
    are jointly zero (random-effects orthogonality). Wald statistic with CR1 covariance (clusters = countries), referred to ``F(q, G - 1)``.
    Country means that are exact combinations of other columns are dropped and listed.
    """
    d = design
    n = d.n_obs
    means = np.column_stack([np.bincount(d.country_idx, weights=d.x[:, j]) / d.counts for j in range(d.x.shape[1])])[d.country_idx]
    years = np.unique(d.year)
    ydum = (d.year[:, None] == years[None, 1:]).astype(float)
    base = np.hstack([np.ones((n, 1)), d.x, ydum])
    keep = _sequential_independent(np.hstack([base, means]))
    n_base = base.shape[1]
    mean_keep = [int(j - n_base) for j in keep if j >= n_base]
    dropped = [d.x_names[j] for j in range(means.shape[1]) if j not in mean_keep]
    z = np.hstack([base, means[:, mean_keep]])
    ztz_inv = np.linalg.inv(z.T @ z)
    beta = ztz_inv @ (z.T @ d.y)
    u = d.y - z @ beta
    s = np.add.reduceat(z * u[:, None], d.starts, axis=0)
    g_n, k = d.n_clusters, z.shape[1]
    cov = g_n / (g_n - 1.0) * (n - 1.0) / (n - k) * ztz_inv @ (s.T @ s) @ ztz_inv
    q = len(mean_keep)
    sl = slice(n_base, n_base + q)
    wald = float(beta[sl] @ np.linalg.solve(cov[sl, sl], beta[sl]))
    f = wald / q
    return {"wald": wald, "q": q, "f_statistic": f, "df2": g_n - 1, "p_value_f": float(stats.f.sf(f, q, g_n - 1)), "p_value_chi2": float(stats.chi2.sf(wald, q)),
            "dropped_country_means": dropped, "country_means_tested": [d.x_names[j] for j in mean_keep], "note": "G = 27 clusters, q country-mean coefficients: F(q, G-1) reference"}


def classical_hausman(design: power.Design) -> dict[str, Any]:
    """Classical Hausman test (FE vs RE) with ``linearmodels``: coefficients on the M1 regressors and the year dummies; ``H = d'(V_FE - V_RE)^+ d``.

    Assumes homoskedastic, serially uncorrelated errors under H0 (reported beside the robust Mundlak form); ``V_FE - V_RE`` may fail to be
    positive semi-definite in finite samples, the pseudo-inverse and its rank are reported.
    """
    from linearmodels.panel import PanelOLS, RandomEffects  # noqa: PLC0415

    d = design
    years = np.unique(d.year)
    ydum = pd.DataFrame((d.year[:, None] == years[None, 1:]).astype(float), columns=[f"y{int(v)}" for v in years[1:]])
    exog = pd.concat([pd.DataFrame(d.x, columns=d.x_names), ydum], axis=1)
    idx = pd.MultiIndex.from_arrays([d.codes, d.year], names=["entity", "time"])
    exog.index, y = idx, pd.Series(d.y, index=idx)
    fe = PanelOLS(y, exog, entity_effects=True).fit(cov_type="unadjusted")
    re = RandomEffects(y, exog.assign(const=1.0)).fit(cov_type="unadjusted")
    names = list(exog.columns)
    diff = fe.params[names].to_numpy() - re.params[names].to_numpy()
    vdiff = fe.cov.loc[names, names].to_numpy() - re.cov.loc[names, names].to_numpy()
    sym = (vdiff + vdiff.T) / 2.0
    eigval, eigvec = np.linalg.eigh(sym)
    tol = 1e-10 * max(float(eigval.max()), 1e-12)
    pos = eigval > tol
    h = float(((eigvec[:, pos].T @ diff) ** 2 / eigval[pos]).sum())
    rank = int(pos.sum())
    return {"statistic": h, "df": rank, "p_value": float(stats.chi2.sf(h, rank)), "min_eigenvalue_of_V_FE_minus_V_RE": float(eigval.min()),
            "n_negative_eigenvalues": int((eigval < -tol).sum()), "note": "computed on the positive eigen-directions of V_FE - V_RE",
            "re_effects_variance": float(re.variance_decomposition["Effects"]), "re_theta_max": float(np.max(np.asarray(re.theta)))}


# ---------------------------------------------------------------------------------------------
# Section E: results file (json + markdown), summary counts
# ---------------------------------------------------------------------------------------------
def robustness_code_hash() -> str:
    """LF-normalised SHA-256 of this module."""
    return m1.file_sha256(Path(__file__).resolve())


def meta_block(extract_hash: str, headline: dict[str, Any]) -> dict[str, Any]:
    """Provenance of the suite."""
    import scipy  # noqa: PLC0415

    return {"spec": "docs/robustness_spec.md", "source": headline["source"], "n_obs": headline["n_obs"], "sesoi_pp": headline["sesoi_pp"], "b_main": B_MAIN, "b_loco": B_LOCO,
            "seed": power.SEED, "seed_key": SEED_KEY, "versions": {"numpy": np.__version__, "pandas": pd.__version__, "scipy": scipy.__version__},
            "extract_hash": extract_hash, "robustness_py_sha256": robustness_code_hash(), "headline_registry_hash": headline["registry_hash"], "headline_code_hash": headline["code_hash"]}


def load_results() -> dict[str, Any]:
    """Existing results file or an empty skeleton."""
    if JSON_PATH.exists():
        return json.loads(JSON_PATH.read_text(encoding="utf-8"))
    return {"meta": {}, "headline": {}, "sections": {}, "summary": {}}


def all_rows(results: dict[str, Any]) -> list[dict[str, Any]]:
    """Every specification row of sections A, C and D."""
    rows = []
    for key in ("A", "C", "D"):
        rows.extend(results.get("sections", {}).get(key, {}).get("rows", []))
    return rows


def summarise(results: dict[str, Any]) -> dict[str, Any]:
    """Counts over all reported specifications (no ranking, no selection); failed specifications are listed separately."""
    rows = all_rows(results)
    out: dict[str, Any] = {"definitions": {
        "keeps_sign": "estimate has the same sign as the headline estimate", "excludes_zero": "95% interval of the row excludes zero",
        "within_sesoi": "95% interval lies inside +-SESOI (0.5 pp)", "note": "specifications are not independent (shared data, nested designs, one estimate with several inference methods)"}}
    labels = {"all": lambda r: True, "A": lambda r: r["group"] == "A", "C": lambda r: r["group"] == "C", "C-LOCO": lambda r: r["group"] == "C-LOCO", "D": lambda r: r["group"] == "D",
              "all_excluding_LOCO": lambda r: r["group"] != "C-LOCO"}
    for name, pick in labels.items():
        sel = [r for r in rows if pick(r)]
        ok = [r for r in sel if r["status"] == "ok"]
        entry: dict[str, Any] = {"n_specifications": len(sel), "n_failed": len(sel) - len(ok), "failed_ids": [r["id"] for r in sel if r["status"] != "ok"]}
        for t in TESTED:
            tg = [r["targets"][t] for r in ok if t in r["targets"]]
            entry[t] = {"n": len(tg), "keeps_sign": int(sum(x["same_sign_as_headline"] for x in tg)), "excludes_zero": int(sum(x["excludes_zero"] for x in tg)),
                        "within_sesoi": int(sum(x["equivalent_within_sesoi"] for x in tg))}
        out[name] = entry
    return out


def write_results(results: dict[str, Any]) -> None:
    """Write json and markdown (recomputing the summary); called after every section so nothing is lost."""
    results["summary"] = summarise(results)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(results, indent=1, allow_nan=False, default=_json_default) + "\n", encoding="utf-8", newline="\n")
    MD_PATH.write_text(render_markdown(results), encoding="utf-8", newline="\n")


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f"not serialisable: {type(obj)}")


def _f(v: float | None, d: int = 3) -> str:
    return "-" if v is None else f"{v:.{d}f}"


def _cell(t: dict[str, Any] | None) -> str:
    """'est [lo, hi]; p; reading; sign' of one target of one row."""
    if t is None:
        return "-"
    p = "" if t["p"] is None else f"; p={_f(t['p'], 4)}"
    reading = "" if t["reading"] is None else f"; {t['reading'].replace('equivalent within +-sesoi', 'equiv. +-0.5').replace('excludes zero', 'excl. 0')}"
    sign = "" if t["same_sign_as_headline"] else "; SIGN DIFFERS"
    return f"{_f(t['estimate'])} [{_f(t['ci_lo'])}, {_f(t['ci_hi'])}]{p}{reading}{sign}"


def spec_table(rows: list[dict[str, Any]], with_gamma_w: bool = True) -> list[str]:
    """Markdown table of specification rows."""
    head = "| id | specification | inference | N | beta_S: est [95% interval]; p; reading | gamma_B: est [95% interval]; p; reading |" + (" gamma_W: est [95% interval] |" if with_gamma_w else "")
    lines = [head, "|---|---|---|---|---|---|" + ("---|" if with_gamma_w else "")]
    for r in rows:
        if r["status"] != "ok":
            lines.append(f"| {r['id']} | {r['label']} | {r['inference']} | - | FAILED: {r.get('error', '')} | |" + (" |" if with_gamma_w else ""))
            continue
        g_w = r["targets"].get("gamma_W")
        gw = f" {_f(g_w['estimate'])} [{_f(g_w['ci_lo'])}, {_f(g_w['ci_hi'])}] |" if (with_gamma_w and g_w) else (" - |" if with_gamma_w else "")
        lines.append(f"| {r['id']} | {r['label']} | {r['inference']} | {r['n_obs']} | {_cell(r['targets'].get('beta_S'))} | {_cell(r['targets'].get('gamma_B'))} |{gw}")
    notes = [f"* {r['id']}: {r['note']}" for r in rows if r.get("note")]
    return lines + (["", "Notes:", *notes] if notes else [])


def render_section_a(sec: dict[str, Any]) -> list[str]:
    """Markdown of section A."""
    lines = ["## A. Inference sensitivities (cross-country dependence)", "",
             "All rows use the M1 regressors as in the headline (centred era terms, no controls, N = 715). Rows with the same estimator differ only in the inference method. "
             "Intervals of the bootstrap rows are bootstrap-t percentile intervals as in the headline; CR1, Driscoll-Kraay and two-way rows use estimate +- t(26) x SE. As in the headline, the bootstrap p-value (null imposed) and the bootstrap-t interval (unrestricted) are different constructions, so near the margin an interval can exclude zero while p is above 0.05 (and the reverse).", ""]
    lines += spec_table(sec["rows"]) + [""]
    dk = sec.get("driscoll_kraay", {})
    chk = sec.get("dk_crosscheck_real", {})
    lines += ["### Driscoll-Kraay implementation and cross-check", "",
              "Bartlett kernel; bandwidth m = floor(4 (T/100)^(2/9)) = 2 and a second run with m = 4. Small-sample factor c = T/(T-1) x (N-1)/(N-K) with T = 27 years, N = 715, K = 35 "
              "(the project's CR1 parameter count: year dummies plus regressors), critical values t(26). "
              + (f"Factors: m=2: {_f(dk.get('2', dk.get(2, {})).get('small_sample_factor'), 4)}; m=4: {_f(dk.get('4', dk.get(4, {})).get('small_sample_factor'), 4)}. " if dk else "")
              + "Cross-check against `linearmodels.PanelOLS(entity_effects=True, time_effects=True).fit(cov_type='kernel', kernel='bartlett', bandwidth=m)` on the real regressors "
              "(linearmodels' own factor n/(n - df_model) applied to the numpy sandwich): "
              + (", ".join(f"m={m}: max relative difference in standard errors {v['max_rel_diff_se']:.1e}" for m, v in chk.get("bandwidths", {}).items()) + f"; coefficients {chk.get('max_rel_diff_coefficients', float('nan')):.1e}." if chk else "not run."), ""]
    tw = [r for r in sec["rows"] if r["id"] == "A3-twoway" and r["status"] == "ok"]
    if tw:
        ex = tw[0]["extra"]
        lines += ["### Two-way clustering", "", f"Cameron-Gelbach-Miller (2011) V = V_country + V_year - V_(country x year), with c_G = G/(G-1) (N-1)/(N-K), c_T = T/(T-1) (N-1)/(N-K), c_GT = N/(N-K). "
                  f"Variance matrix not positive semi-definite: {ex.get('psd_fix_applied')} (smallest eigenvalue {ex.get('min_eigenvalue_of_V'):.3e}, {ex.get('n_negative_eigenvalues')} negative); "
                  "when it was not, the negative eigenvalues were set to zero before the standard errors were read.", ""]
    lines += ["### CCE designs (Pesaran 2006, country-specific coefficients on cross-sectional averages, year effects kept)", "",
              "| version | CSA variables | added parameters | total parameters | residual df (N - parameters) | df exhausted | dropped exactly collinear columns |", "|---|---|---|---|---|---|---|"]
    for kind, rep in sec["cce"].items():
        if "error" in rep:
            lines.append(f"| CCE-{kind} | - | FAILED: {rep['error']} | | | | |")
        else:
            lines.append(f"| CCE-{kind} | {len(rep['csa_variables'])} ({', '.join(rep['csa_variables'])}) | {rep['added_parameters']} | {rep['n_parameters_total']} | {rep['residual_df']} | {rep['df_exhausted']} | {len(rep['dropped_columns'])} (one country column per CSA variable: the sum over countries of d_i x csa_t equals csa_t, a combination of the year dummies) |")
    lines += ["", f"Note: the CR1 factor uses the project convention k = year dummies + regressors; with {sec['cce'].get('full', {}).get('added_parameters', '?')} added columns the CCE-full CR1 factor is large. ", ""]
    lines += ["### Residual cross-section dependence (Pesaran 2015 CD; mean absolute pairwise correlation)", "",
              "CD is computed on pairwise correlations of the residuals over common years (351 pairs). Residuals of models with year effects have an average pairwise correlation of about -1/(N-1) = -0.038 by construction, "
              "which shifts CD to about -3.7 even under independence and pins the sum of the correlations, so the N(0,1) p-value is not informative here. "
              "Simulated benchmarks for independent errors pushed through the same projection are shown (iid errors; AR(1) errors with the estimated persistence "
              f"rho = {_f(sec.get('rho_hat'), 3)} and country SDs). The mean absolute correlation is the more informative summary.", "",
              "| residuals | CD | mean pairwise corr | mean abs corr | CD null mean (iid / AR(1)) | mean abs corr null (iid / AR(1), sd) | excess mean abs corr vs AR(1) null |", "|---|---|---|---|---|---|---|"]
    for d in sec["dependence"]:
        n_i, n_a = d["null_iid"], d["null_ar1"]
        lines.append(f"| {d['model']} | {_f(d['cd'], 2)} | {_f(d['mean_corr'], 3)} | {_f(d['mean_abs_corr'], 3)} | {_f(n_i['cd_mean'], 2)} / {_f(n_a['cd_mean'], 2)} | "
                     f"{_f(n_i['mean_abs_corr'], 3)} / {_f(n_a['mean_abs_corr'], 3)} ({_f(n_a['mean_abs_corr_sd'], 3)}) | {_f(d['excess_mean_abs_corr_vs_ar1'], 3)} |")
    return lines + [""]


def render_markdown(results: dict[str, Any]) -> str:
    """Whole report from the results dictionary (sections that have not been run yet are listed as pending)."""
    meta, head = results.get("meta", {}), results.get("headline", {})
    lines = ["# Robustness and diagnostics (docs/robustness_spec.md)", "",
             "Associations only. Scheduled elections are predetermined, not exogenous. The headline remains the pre-registered V7 result; nothing below replaces it, selects among specifications or ranks them. "
             "Every specification is shown. Estimates are in pp of potential GDP (interactions per +1 SD of the component). Reading: SESOI "
             f"{meta.get('sesoi_pp', 0.5)} pp; label precedence excludes zero, then equivalent within +-SESOI, then inconclusive (as in `reports/results/m1_confirmatory.md`). "
             "'SIGN DIFFERS' marks an estimate whose sign differs from the headline estimate.", ""]
    if head:
        bs, gb = head["targets"]["beta_S"], head["targets"]["gamma_B"]
        lines += ["## Headline (pre-registered V7, bootstrap-t B = 9,999, N = 715)", "", "| target | estimate | 95% interval | p (wild bootstrap) | reading |", "|---|---|---|---|---|",
                  f"| beta_S | {_f(bs['estimate'])} | [{_f(bs['ci_lo'])}, {_f(bs['ci_hi'])}] | {_f(bs['p_bootstrap'], 4)} | {bs['reading']} |",
                  f"| gamma_B | {_f(gb['estimate'])} | [{_f(gb['ci_lo'])}, {_f(gb['ci_hi'])}] | {_f(gb['p_bootstrap'], 4)} | {gb['reading']} |", ""]
    secs = results.get("sections", {})
    for key, fn in RENDERERS.items():
        if key in secs:
            lines += fn(secs[key])
        else:
            lines += [f"## Section {key}: not yet run", ""]
    if results.get("summary") and secs:
        lines += render_summary(results["summary"])
    lines += ["## E. Outputs and tests", "",
              "* Files: `reports/results/robustness.md` (this file), `reports/results/robustness.json` (every specification with all numbers, the dependence diagnostics and the summary counts), `reports/figures/robustness_forest.png` (beta_S and gamma_B, point estimates and 95% intervals, 300 dpi).",
              "* Tests (`tests/test_robustness.py`) use synthetic panels with a known answer: the numpy Driscoll-Kraay standard errors equal `linearmodels` (bandwidths 0, 2, 4; balanced and unbalanced); two-way clustering equals statsmodels' `cov_cluster_2groups` without small-sample factors; "
              "CCE removes the bias of a heterogeneous common factor that year effects cannot; Pesaran CD is N(0,1)-like under independence and large under a common factor; the modified Wald, Wooldridge, CIPS, Mundlak-Hausman and binned tests reject where they should and not where they should not; the 12-month exposure rebuild reproduces the frozen exposure columns to 1e-12; "
              "and the frozen files match `docs/freeze_manifest.json` byte for byte (LF-normalised SHA-256).", ""]
    lines += ["## What this does not show", "",
              "* The results are associations. Scheduled elections are predetermined, not exogenous, and the ageing interactions (especially gamma_B, a cross-country contrast) have no causal reading.",
              "* The specifications are not independent: they share one panel, many are nested, and several rows are the same estimate under different inference. Counts of specifications that keep a sign or exclude zero are descriptive, not a vote and not a probability.",
              "* No specification is preferred. The headline remains the pre-registered V7 result; sensitivities are reported whatever they show.",
              "* The CAPB is a model estimate with a typical first-outturn revision of 0.64 pp, as large as the SESOI; none of these checks addresses measurement error.",
              "* Diagnostics (section B) describe the data and were not used to choose any specification.", ""]
    if meta:
        lines += ["## Provenance", "", f"* seed {meta.get('seed')}, bootstrap seed key {meta.get('seed_key')}; B = {meta.get('b_main')} (main), {meta.get('b_loco')} (each leave-one-country-out fit); Rademacher weights, whole feasible procedure re-estimated in every bootstrap sample",
                  f"* versions: numpy {meta.get('versions', {}).get('numpy')}, pandas {meta.get('versions', {}).get('pandas')}, scipy {meta.get('versions', {}).get('scipy')}",
                  f"* gold extract hash: `{meta.get('extract_hash')}`", f"* robustness.py SHA-256 (LF-normalised): `{meta.get('robustness_py_sha256')}`",
                  f"* headline registry hash `{meta.get('headline_registry_hash')}`; headline code hash `{meta.get('headline_code_hash')}`", ""]
    return "\n".join(lines)


def render_summary(summary: dict[str, Any]) -> list[str]:
    """Markdown of the summary counts."""
    lines = ["## Summary counts (descriptive; specifications are not independent)", "",
             "| group | specifications | failed | beta_S keeps sign | beta_S interval excludes 0 | beta_S interval inside +-0.5 | gamma_B keeps sign | gamma_B interval excludes 0 | gamma_B interval inside +-0.5 |", "|---|---|---|---|---|---|---|---|---|"]
    names = {"all": "all specifications", "all_excluding_LOCO": "all excluding the 27 leave-one-out fits", "A": "A inference", "C": "C sample variants (excl. leave-one-out)", "C-LOCO": "C leave-one-country-out fits", "D": "D definitions"}
    for key, label in names.items():
        e = summary.get(key)
        if not e:
            continue
        b, g = e["beta_S"], e["gamma_B"]
        n_b, n_g = b["n"], g["n"]
        lines.append(f"| {label} | {e['n_specifications']} | {e['n_failed']} | {b['keeps_sign']}/{n_b} | {b['excludes_zero']}/{n_b} | {b['within_sesoi']}/{n_b} | {g['keeps_sign']}/{n_g} | {g['excludes_zero']}/{n_g} | {g['within_sesoi']}/{n_g} |")
    return lines + [""]


RENDERERS: dict[str, Any] = {"A": render_section_a}

# ---------------------------------------------------------------------------------------------
# Exposure rebuild from the election calendar (new code; the frozen module is only used by the tests, as the reference)
# ---------------------------------------------------------------------------------------------
LETTER_OF = {"scheduled": "S", "early": "E", "delayed": "D"}  # every other class (unclassified, unavailable) goes to U, as in the frozen construction


def load_calendar(path: Path = CALENDAR_CSV) -> pd.DataFrame:
    """Election calendar of the 27 members (1990-2023) with parsed dates; only rows with ``in_calendar`` are used by the rebuild."""
    cal = pd.read_csv(path, parse_dates=["date_used"])
    cal["in_calendar"] = cal["in_calendar"].astype(bool)
    return cal


def _union_share(windows: list[tuple[pd.Timestamp, pd.Timestamp]], years: range) -> dict[int, float]:
    """Share of each calendar year covered by the union of the half-open day windows ``[start, end)``."""
    first, last = pd.Timestamp(years[0], 1, 1), pd.Timestamp(years[-1] + 1, 1, 1)
    mask = np.zeros((last - first).days, dtype=bool)
    for start, end in windows:
        lo, hi = max((start - first).days, 0), min((end - first).days, len(mask))
        if hi > lo:
            mask[lo:hi] = True
    out = {}
    for year in years:
        lo, hi = (pd.Timestamp(year, 1, 1) - first).days, (pd.Timestamp(year + 1, 1, 1) - first).days
        out[year] = float(mask[lo:hi].mean())
    return out


def rebuild_exposure(calendar: pd.DataFrame, *, pre_months: int = 12, lead_offset_months: int = 0, post_months: int = 12, class_col: str = "class_primary",
                     years: range = range(1990, 2024)) -> pd.DataFrame:
    """Country-year exposure ``W_S, W_E, W_D, W_U, Post`` with the share-of-year union construction of the frozen exposure module.

    The pre-window of an election on day ``d`` is ``[d - (pre_months + lead_offset) months, d - lead_offset months)``; ``lead_offset = 0`` is the
    window itself (12 months = the pre-registered window), ``lead_offset = 12`` with ``pre_months = 12`` is the placebo window of months 13-24.
    ``W_X`` is the share of calendar year ``t`` inside the UNION of the pre-windows of the elections of class ``X`` (0 to 1); ``Post`` is the share
    inside the union of the ``post_months`` after any election. Classes come from ``class_col``; anything other than scheduled / early / delayed is
    unclassified (``W_U``). Only calendar rows with ``in_calendar`` are used.
    """
    used = calendar[calendar["in_calendar"]]
    records = []
    for code in dict.fromkeys(calendar["eurostat_code"]):
        sub = used[used["eurostat_code"] == code]
        shares = {}
        for letter in "SEDU":
            days = [d for d, c in zip(sub["date_used"], sub[class_col], strict=True) if LETTER_OF.get(c, "U") == letter]
            shares[letter] = _union_share([(d - pd.DateOffset(months=pre_months + lead_offset_months), d - pd.DateOffset(months=lead_offset_months)) for d in days], years)
        post = _union_share([(d, d + pd.DateOffset(months=post_months)) for d in sub["date_used"]], years)
        for year in years:
            records.append({"eurostat_code": code, "year": year, "W_S": shares["S"][year], "W_E": shares["E"][year], "W_D": shares["D"][year], "W_U": shares["U"][year], "Post": post[year]})
    return pd.DataFrame(records)


def election_year_dummies(calendar: pd.DataFrame, class_col: str = "class_primary", years: range = range(1990, 2024)) -> pd.DataFrame:
    """Calendar-year election dummies by class: 1 in a year with at least one election of the class (``W_S`` <- scheduled, ``W_E``, ``W_D``, ``W_U``)."""
    used = calendar[calendar["in_calendar"]].copy()
    used["letter"] = used[class_col].map(lambda c: LETTER_OF.get(c, "U"))
    used["yr"] = used["date_used"].dt.year
    rows = []
    for code in dict.fromkeys(calendar["eurostat_code"]):
        sub = used[used["eurostat_code"] == code]
        for year in years:
            hit = set(sub.loc[sub["yr"] == year, "letter"])
            rows.append({"eurostat_code": code, "year": year, **{f"W_{k}": float(k in hit) for k in "SEDU"}})
    return pd.DataFrame(rows)


def with_columns(frame: pd.DataFrame, new: pd.DataFrame, columns: list[str] | None = None, rename: dict[str, str] | None = None) -> pd.DataFrame:
    """Copy of ``frame`` whose columns are replaced (or added) from ``new`` by (country, year); raises if any cell is missing."""
    columns = columns or [c for c in new.columns if c not in ("eurostat_code", "year")]
    rename = rename or {}
    merged = frame[["eurostat_code", "year"]].merge(new[["eurostat_code", "year", *columns]], on=["eurostat_code", "year"], how="left", validate="one_to_one")
    if merged[columns].isna().any().any():
        raise ValueError("the replacement columns do not cover every country-year of the sample")
    out = frame.copy()
    for c in columns:
        out[rename.get(c, c)] = merged[c].to_numpy()
    return out


# ---------------------------------------------------------------------------------------------
# Section B runner
# ---------------------------------------------------------------------------------------------
def binned_diagnostic(frame: pd.DataFrame, which: str, bins: int = 3) -> dict[str, Any]:
    """Binned-kernel style linearity and common-support check (Hainmueller, Mummolo & Xu 2019) for one interaction of M1.

    ``which`` is 'between' or 'within'. The component (``abar_i / sd`` or ``(z - abar_i) / sd``, as in M1) is cut into three equal-count bins. The
    binning model replaces ``W_S`` and the interaction by ``W_S x bin_j`` (the bin-specific association at the average era composition, the other
    interaction at zero); for the within component the bin dummies G_2, G_3 enter as main effects (time-varying), for the between component
    they are absorbed by the country effects. The linear-model prediction in a bin is ``beta_S + gamma * (exposure-weighted bin mean of the
    component)``. Linearity is tested by adding ``W_S x G_2, W_S x G_3`` to the linear M1 and testing the two terms jointly (``F(2, G - 1)``, CR1).
    Estimator: OLS two-way fixed effects with CR1 (the bin estimates are a diagnostic, not a headline).
    """
    frame = sorted_frame(frame)
    reg, scale, targets = pv.variant_regressors(frame, era=True, control_names=())
    a = frame["olddep1_lag"].to_numpy(float)
    z = (a - a.mean()) / a.std(ddof=0)
    abar = pd.Series(z).groupby(frame["eurostat_code"].to_numpy()).transform("mean").to_numpy()
    comp = abar / scale["sd_between_z"] if which == "between" else (z - abar) / scale["sd_within_z"]
    bin_id = pd.qcut(pd.Series(comp), bins, labels=False, duplicates="drop").to_numpy()
    n_bins = int(bin_id.max()) + 1
    w_s = frame["W_S"].to_numpy(float)
    inter = "WS_x_between" if which == "between" else "WS_x_within"
    codes = frame["eurostat_code"].to_numpy()

    def design_of(columns: pd.DataFrame) -> power.Design:
        return power.build_design(frame, label=f"binned {which}", regressors=columns, targets={}, scale={})

    dummies = {f"G{j + 1}": (bin_id == j).astype(float) for j in range(n_bins)}
    ws_bin = {f"WS_G{j + 1}": w_s * dummies[f"G{j + 1}"] for j in range(n_bins)}
    main = {f"G{j + 1}": dummies[f"G{j + 1}"] for j in range(1, n_bins)} if which == "within" else {}
    binned = pd.concat([reg.drop(columns=["W_S", inter]), pd.DataFrame({**ws_bin, **main})], axis=1)
    fe_b = FeOls(design_of(binned))
    cov_b = fe_b.cr1()
    t_crit = fe_b.design.t_crit
    linear = FeOls(power.build_design(frame, label="linear", regressors=reg, targets=power.TARGETS_M1, scale=scale))
    b_s, gamma = float(linear.beta[linear.index("beta_S")]), float(linear.beta[list(linear.design.x_names).index(inter)])
    # linearity: add the bin terms of bins 2..n to the linear model
    extra_cols = {f"WS_G{j + 1}": ws_bin[f"WS_G{j + 1}"] for j in range(1, n_bins)} | main
    ext = FeOls(design_of(pd.concat([reg, pd.DataFrame(extra_cols)], axis=1)))
    names = list(ext.design.x_names)
    idx = [names.index(f"WS_G{j + 1}") for j in range(1, n_bins)]
    cov_e = ext.cr1()
    b_t = ext.beta[idx]
    wald = float(b_t @ np.linalg.solve(cov_e[np.ix_(idx, idx)], b_t))
    q = len(idx)
    f_stat = wald / q
    g_n = ext.design.n_clusters
    out_bins = []
    for j in range(n_bins):
        pos = list(fe_b.design.x_names).index(f"WS_G{j + 1}")
        est, se = float(fe_b.beta[pos]), float(np.sqrt(cov_b[pos, pos]))
        sel = bin_id == j
        treated = sel & (w_s > 0)
        weighted_mean = float((w_s[sel] * comp[sel]).sum() / w_s[sel].sum()) if w_s[sel].sum() > 0 else float("nan")
        out_bins.append({"bin": j + 1, "component_min": float(comp[sel].min()), "component_max": float(comp[sel].max()), "n_obs": int(sel.sum()), "n_countries": int(len(set(codes[sel]))),
                         "n_obs_exposed": int(treated.sum()), "n_countries_exposed": int(len(set(codes[treated]))), "mean_exposure": float(w_s[sel].mean()),
                         "binned_estimate": est, "binned_ci_lo": est - t_crit * se, "binned_ci_hi": est + t_crit * se,
                         "exposure_weighted_component_mean": weighted_mean, "linear_prediction": b_s + gamma * weighted_mean,
                         "thin_support": bool(len(set(codes[treated])) < 5)})
    return {"moderator": which, "bins": out_bins, "linear_beta_S": b_s, "linear_gamma": gamma, "linearity_wald": wald, "linearity_q": q, "linearity_f": f_stat, "linearity_df2": g_n - 1,
            "linearity_p": float(stats.f.sf(f_stat, q, g_n - 1)), "estimator": "OLS two-way FE, CR1 (country clusters), t(26) intervals"}


def lead_placebo(frame: pd.DataFrame, calendar: pd.DataFrame, n_boot: int, max_year: int | None = None) -> dict[str, Any]:
    """V7 on M1 plus ``W_S_lead`` (share of year t inside months 13-24 before a scheduled election): coefficient with bootstrap-t inference."""
    frame = sorted_frame(frame)
    if max_year is not None:
        frame = frame[frame["year"] <= max_year].reset_index(drop=True)
    lead = rebuild_exposure(calendar, pre_months=12, lead_offset_months=12, years=range(1990, 2024))[["eurostat_code", "year", "W_S"]].rename(columns={"W_S": "W_S_lead"})
    merged = with_columns(frame, lead, ["W_S_lead"])
    reg, scale, targets = pv.variant_regressors(merged, era=True, control_names=())
    reg = reg.assign(W_S_lead=merged["W_S_lead"].to_numpy(float))
    design = power.build_design(merged, label="M1 + lead placebo", regressors=reg, targets={**targets, "lead": "W_S_lead"}, scale=scale)
    est = v7_estimator(design)
    names = ("beta_S", "gamma_B", "gamma_W", "lead")
    block = bootstrap_block(est, n_boot, targets=names, tested=("beta_S", "gamma_B", "lead"))
    lead_t = block["targets"]["lead"]
    return {"n_obs": design.n_obs, "max_year": max_year, "estimator": "V7", "inference": f"wild-cluster bootstrap-t, B={n_boot}",
            "lead": {"estimate": lead_t["estimate"], "ci_lo": lead_t["boot_lo"], "ci_hi": lead_t["boot_hi"], "p": lead_t["p_boot"], "cr1_se": lead_t["cr1_se"]},
            "beta_S": {"estimate": block["targets"]["beta_S"]["estimate"], "ci_lo": block["targets"]["beta_S"]["boot_lo"], "ci_hi": block["targets"]["beta_S"]["boot_hi"], "p": block["targets"]["beta_S"]["p_boot"]},
            "gamma_B": {"estimate": block["targets"]["gamma_B"]["estimate"], "ci_lo": block["targets"]["gamma_B"]["boot_lo"], "ci_hi": block["targets"]["gamma_B"]["boot_hi"], "p": block["targets"]["gamma_B"]["p_boot"]},
            "mean_W_S_lead": float(merged["W_S_lead"].mean()), "share_lead_exposed": float((merged["W_S_lead"] > 0).mean())}


def run_section_b(frame: pd.DataFrame, headline: dict[str, Any], sesoi: float, n_boot: int = B_MAIN, n_sim_cips: int = 2_000) -> dict[str, Any]:
    """Section B: the pre-registered diagnostics. Reported only; never used to choose a specification."""
    frame = sorted_frame(frame)
    design = m1_design(frame, "OLS-FE (V0)")
    fe = FeOls(design)
    out: dict[str, Any] = {}

    def guarded(key: str, fn) -> None:
        t0 = time.time()
        try:
            out[key] = fn()
            _log(f"B {key} done in {time.time() - t0:.1f}s")
        except Exception as error:  # noqa: BLE001
            out[key] = {"error": f"{type(error).__name__}: {error}"}
            _log(f"B {key} FAILED: {type(error).__name__}: {error}")

    guarded("modified_wald", lambda: {"ols_fe_residuals": modified_wald_mc(fe.resid, design), "v7_residuals": modified_wald_mc(v7_residuals(v7_estimator(design))[0], design)})
    guarded("wooldridge", lambda: wooldridge_serial(design))
    for var, col in (("capb", "capb"), ("moderator_lag", "olddep1_lag")):
        for trend in (False, True):
            key = f"cips_{var}_{'trend' if trend else 'constant'}"
            guarded(key, lambda col=col, trend=trend: cips_test(wide_grid(frame, col), lags=1, trend=trend, n_sim=n_sim_cips, seed=int(trend) + (2 if col != "capb" else 0)))
    guarded("vif", lambda: vif_table(design))
    guarded("hausman_mundlak", lambda: mundlak_hausman(design))
    guarded("hausman_classical", lambda: classical_hausman(design))
    guarded("binned_between", lambda: binned_diagnostic(frame, "between"))
    guarded("binned_within", lambda: binned_diagnostic(frame, "within"))
    calendar = load_calendar()
    guarded("lead_placebo", lambda: lead_placebo(frame, calendar, n_boot))
    guarded("lead_placebo_to_2020", lambda: lead_placebo(frame, calendar, n_boot, max_year=2020))
    return out


def render_section_b(sec: dict[str, Any]) -> list[str]:
    """Markdown of section B."""
    def err(d: dict[str, Any]) -> str | None:
        return d.get("error") if isinstance(d, dict) else None

    lines = ["## B. Pre-registered diagnostics (reported, never used to choose a specification)", ""]
    mw = sec.get("modified_wald", {})
    lines += ["### Groupwise heteroskedasticity (modified Wald, Greene) and serial correlation (Wooldridge)", "",
              "The modified Wald statistic over-rejects when T is small (in a 400-draw check with iid normal errors the 5% test rejected 32% of the time at T = 40, 7.5% at T = 200), so a Monte Carlo p-value under iid normal errors with this panel's layout is shown beside the chi-square p-value.", "",
              "| test | statistic | df | p (chi-square) | detail |", "|---|---|---|---|---|"]
    if err(mw):
        lines.append(f"| modified Wald | FAILED: {err(mw)} | | | |")
    else:
        for key, label in (("ols_fe_residuals", "modified Wald (OLS-FE residuals)"), ("v7_residuals", "modified Wald (V7 residuals)")):
            r = mw[key]
            lines.append(f"| {label} | {_f(r['statistic'], 1)} | {r['df']} | {r['p_value']:.2e} | Monte Carlo p = {_f(r['p_value_mc'], 4)} (null median {_f(r['null_median_statistic'], 1)}, 95th percentile {_f(r['null_q95_statistic'], 1)}); country residual SD from {_f(r['sigma_i_min'], 2)} to {_f(r['sigma_i_max'], 2)} |")
    wo = sec.get("wooldridge", {})
    if err(wo):
        lines.append(f"| Wooldridge | FAILED: {err(wo)} | | | |")
    else:
        lines.append(f"| Wooldridge (H0: coefficient = -0.5) | F = {_f(wo['f_statistic'], 1)} | (1, {wo['df2']}) | {wo['p_value']:.2e} | coefficient {_f(wo['coefficient'], 3)} (se {_f(wo['se'], 3)}), {wo['n_pairs']} residual pairs |")
    lines += ["", "### Panel unit-root tests (CIPS, Pesaran 2007; lag order fixed at 1; critical values simulated for this unbalanced layout)", "",
              "| series | deterministic terms | CIPS | simulated 1% / 5% / 10% critical values | p (left tail) | unit root rejected at 5% |", "|---|---|---|---|---|---|"]
    for var, label in (("capb", "capb"), ("moderator_lag", "lagged OLDDEP1")):
        for tr in ("constant", "trend"):
            r = sec.get(f"cips_{var}_{tr}", {})
            if err(r) or not r:
                lines.append(f"| {label} | {tr} | FAILED: {err(r)} | | | |")
            else:
                lines.append(f"| {label} | {tr} | {_f(r['cips'], 3)} | {_f(r['crit_1'], 2)} / {_f(r['crit_5'], 2)} / {_f(r['crit_10'], 2)} | {_f(r['p_value_left_tail'], 4)} | {r['reject_5pct']} |")
    vif = sec.get("vif", {})
    lines += ["", "### Variance inflation factors of the M1 regressors (flag above 5)", ""]
    if err(vif):
        lines.append(f"FAILED: {err(vif)}")
    else:
        lines += ["| regressor | VIF after partialling out country and year effects | VIF on the raw columns |", "|---|---|---|"]
        for n, w, r in zip(vif["names"], vif["vif_within"], vif["vif_raw"]):
            lines.append(f"| {n} | {_f(w, 2)}{' (flag)' if w > 5 else ''} | {_f(r, 2)}{' (flag)' if r > 5 else ''} |")
    hm, hc = sec.get("hausman_mundlak", {}), sec.get("hausman_classical", {})
    lines += ["", "### Hausman FE vs RE", ""]
    if err(hm):
        lines.append(f"Mundlak (robust) form: FAILED: {err(hm)}")
    else:
        lines.append(f"* Mundlak/Wooldridge regression form with country-clustered covariance: Wald = {_f(hm['wald'], 2)} on {hm['q']} country-mean coefficients, F({hm['q']}, {hm['df2']}) p = {hm['p_value_f']:.1e} (chi-square p = {hm['p_value_chi2']:.1e}); dropped exactly collinear country means: {hm['dropped_country_means'] or 'none'}.")
    if err(hc):
        lines.append(f"* Classical Hausman: FAILED: {err(hc)}")
    else:
        lines.append(f"* Classical Hausman (linearmodels FE vs RE, homoskedastic covariances; coefficients on the M1 regressors and the year dummies): H = {_f(hc['statistic'], 2)}, df = {hc['df']}, p = {_f(hc['p_value'], 4)}; negative eigenvalues of V_FE - V_RE: {hc['n_negative_eigenvalues']}."
                     + (" The estimated random-effects variance is zero (theta = 0), so the RE estimator is pooled OLS and V_FE - V_RE is far from positive semi-definite: this classical statistic is not interpretable here; the Mundlak form above is the Hausman result." if hc.get("re_effects_variance", 1) == 0 else ""))
    for which in ("between", "within"):
        b = sec.get(f"binned_{which}", {})
        lines += ["", f"### Binned linearity and common support: {which} component of ageing (three equal-count bins; OLS-FE, CR1)", ""]
        if err(b) or not b:
            lines.append(f"FAILED: {err(b)}")
            continue
        lines += ["| bin | component range (SD units) | obs | countries | exposed obs (W_S > 0) | exposed countries | binned effect of W_S [95% CI] | linear-model prediction | thin support (< 5 exposed countries) |", "|---|---|---|---|---|---|---|---|---|"]
        for r in b["bins"]:
            lines.append(f"| {r['bin']} | {_f(r['component_min'], 2)} to {_f(r['component_max'], 2)} | {r['n_obs']} | {r['n_countries']} | {r['n_obs_exposed']} | {r['n_countries_exposed']} | "
                         f"{_f(r['binned_estimate'])} [{_f(r['binned_ci_lo'])}, {_f(r['binned_ci_hi'])}] | {_f(r['linear_prediction'])} | {r['thin_support']} |")
        lines.append(f"\nLinearity (adding W_S x bin 2 and W_S x bin 3 to the linear model): F(2, {b['linearity_df2']}) = {_f(b['linearity_f'], 2)}, p = {_f(b['linearity_p'], 4)}. Linear OLS-FE coefficients: beta_S {_f(b['linear_beta_S'])}, interaction {_f(b['linear_gamma'])}.")
    lines += ["", "### Lead placebo (V7; W_S_lead = share of year t inside months 13-24 before a scheduled election; the pre-window itself is months 1-12)", "",
              "| sample | N | W_S_lead: estimate [95% bootstrap-t interval]; p | beta_S in the augmented model | gamma_B in the augmented model |", "|---|---|---|---|---|"]
    for key, label in (("lead_placebo", "as specified: 1995-2021"), ("lead_placebo_to_2020", "to 2020 (the lead window of 2021 reaches into 2023, where the election calendar is incomplete)")):
        r = sec.get(key, {})
        if err(r) or not r:
            lines.append(f"| {label} | - | FAILED: {err(r)} | | |")
            continue
        ld, bs, gb = r["lead"], r["beta_S"], r["gamma_B"]
        lines.append(f"| {label} | {r['n_obs']} | {_f(ld['estimate'])} [{_f(ld['ci_lo'])}, {_f(ld['ci_hi'])}]; p = {_f(ld['p'], 4)} | {_f(bs['estimate'])} [{_f(bs['ci_lo'])}, {_f(bs['ci_hi'])}] | {_f(gb['estimate'])} [{_f(gb['ci_lo'])}, {_f(gb['ci_hi'])}] |")
    return lines + [""]


RENDERERS["B"] = render_section_b

# ---------------------------------------------------------------------------------------------
# Sections C and D: V7 on sample and definition variants
# ---------------------------------------------------------------------------------------------
def v7_variant_row(frame: pd.DataFrame, headline: dict[str, Any], sesoi: float, n_boot: int, *, spec_id: str, group: str, label: str,
                   design_kwargs: dict[str, Any] | None = None, winsor: bool = False, note: str = "", extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """One V7 specification: the headline procedure (wild-cluster bootstrap-t, B as given) on a variant of the sample or of the definitions."""
    design = m1_design(frame, label, **(design_kwargs or {}))
    est = v7_estimator(design, winsor=winsor)
    block = bootstrap_block(est, n_boot)
    row = rows_from_block(block, headline, sesoi, spec_id=spec_id, group=group, label=label, estimator="V7" + (" + winsorised residual tails" if winsor else ""), design=design,
                          note=note, extra={**(extra or {}), "n_countries": design.n_clusters, "x_names": list(design.x_names)}, cr1=False, boot=True)[0]
    row["id"] = spec_id
    return row


def extension_2022_frame(extract: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """The 2022 extension (N = 737) built with the frozen panel assembler (``assemble_gold_panel(..., end=2022)``) and the ETAD-trusted exposure flag.

    A country-year of 2022 is added when CAPB, the lagged OLDDEP1 and ``exposure_complete_etad`` are all present (22 countries: AT, CY, EL, MT and
    PL are incomplete); the 1995-2021 part must reproduce the confirmatory extract exactly, otherwise this raises.
    """
    import panel as panel_module  # noqa: PLC0415

    inputs = panel_module.load_inputs()
    built = panel_module.assemble_gold_panel(inputs, start=1995, end=2022)
    panel22 = built.panel
    ok = panel22["capb"].notna() & panel22["olddep1_lag"].notna() & panel22["exposure_complete_etad"]
    joint = panel22[ok]
    counts = joint.groupby("eurostat_code").size()
    joint = joint[joint["eurostat_code"].isin(counts[counts >= 20].index)]
    old = joint[joint["year"] <= 2021]
    key = ["eurostat_code", "year"]
    ref = extract.sort_values(key).reset_index(drop=True)
    old = old.sort_values(key).reset_index(drop=True)
    if len(old) != len(ref) or not (old[key].to_numpy() == ref[key].to_numpy()).all():
        raise ValueError("the 1995-2021 part of the 2022 build does not have the confirmatory keys")
    for col in ("capb", "W_S", "W_E", "W_D", "W_U", "Post", "olddep1_lag"):
        if np.max(np.abs(old[col].to_numpy(float) - ref[col].to_numpy(float))) > 1e-9:
            raise ValueError(f"the 1995-2021 part of the 2022 build differs from the confirmatory extract in {col}")
    new = joint[joint["year"] == 2022]
    info = {"n_obs": int(len(joint)), "added_2022": int(len(new)), "countries_added": sorted(new["eurostat_code"]), "countries_without_2022": sorted(set(ref["eurostat_code"]) - set(new["eurostat_code"])),
            "capb_last_observed_year": int(built.last_observed_year)}
    return joint.sort_values(key).reset_index(drop=True), info


def run_section_c(frame: pd.DataFrame, headline: dict[str, Any], sesoi: float, n_boot: int = B_MAIN) -> dict[str, Any]:
    """Section C: sample variants of V7 (B = 9,999) and the leave-one-country-out fits (B = 999)."""
    frame = sorted_frame(frame)
    rows: list[dict[str, Any]] = []
    notes: dict[str, Any] = {}

    def run(spec_id: str, label: str, group: str = "C", **kwargs: Any) -> None:
        t0 = time.time()
        try:
            rows.append(v7_variant_row(kwargs.pop("frame", frame), headline, sesoi, kwargs.pop("n_boot", n_boot), spec_id=spec_id, group=group, label=label, **kwargs))
            _log(f"C {spec_id} done in {time.time() - t0:.1f}s (N={rows[-1]['n_obs']})")
        except Exception as error:  # noqa: BLE001  (a failure is a result: reported, never hidden)
            rows.append(failed_row(spec_id, group, label, "V7", "wild-cluster bootstrap-t", error))
            _log(f"C {spec_id} FAILED: {type(error).__name__}: {error}")

    counts = frame.groupby("eurostat_code")["year"].transform("size")
    balanced = frame[counts == 27].reset_index(drop=True)
    run("C1-balanced22", "Balanced-22 (countries observed in all 27 years)", frame=balanced, note=f"{balanced['eurostat_code'].nunique()} countries")
    kept = frame[~frame["touches_unclassified_or_delayed"].astype(bool)].reset_index(drop=True)
    run("C2-drop-unclassified-delayed", "Drop country-years touching unclassified or delayed elections", frame=kept,
        note=f"{len(frame) - len(kept)} country-years dropped; W_U and W_D are then identically zero and drop out of the model")
    gf = frame.copy()
    for c in ("W_S", "W_E", "W_D", "W_U", "Post"):
        gf[c] = gf[f"{c}_gf"]
    run("C3-gapfilled", "Gap-filled election classes (*_gf exposure columns)", frame=gf)
    run("C5-ireland-winsor", "Ireland 2010 handled by residual-tail winsorising (V2w rule, 1st/99th percentile)", winsor=True,
        note="winsorising is applied to the first-stage residuals in every bootstrap sample, as in the project's V2w")
    run("C6a-drop-2008-2012", "Drop 2008-2012", frame=frame[~frame["year"].between(2008, 2012)].reset_index(drop=True))
    run("C6b-drop-2020-2021", "Drop 2020-2021", frame=frame[~frame["year"].between(2020, 2021)].reset_index(drop=True))
    run("C6c-drop-both", "Drop 2008-2012 and 2020-2021", frame=frame[~(frame["year"].between(2008, 2012) | frame["year"].between(2020, 2021))].reset_index(drop=True))
    controls = frame[frame["outgap_lag"].notna() & frame["euro_member"].notna()].reset_index(drop=True)
    run("C8-controls", "Robustness-controls model (adds lagged output gap and euro membership)", frame=controls, design_kwargs={"control_names": ("outgap_lag", "euro_member")},
        note=f"complete cases of the two controls: N = {len(controls)} (specification: 703)")
    try:
        ext, info = extension_2022_frame(frame)
        notes["extension_2022"] = {"built": True, **info}
        run("C7-extension-2022", "2022 extension (ETAD-trusted exposure for 22 countries)", frame=ext, note=f"+{info['added_2022']} country-years in 2022; no 2022 for {', '.join(info['countries_without_2022'])}")
    except Exception as error:  # noqa: BLE001
        notes["extension_2022"] = {"built": False, "reason": f"{type(error).__name__}: {error}"}
        rows.append(failed_row("C7-extension-2022", "C", "2022 extension", "V7", "wild-cluster bootstrap-t", error))
        _log(f"C C7 not built: {error}")

    # leave-one-country-out
    loco_rows = []
    for code in dict.fromkeys(frame["eurostat_code"]):
        t0 = time.time()
        sub = frame[frame["eurostat_code"] != code].reset_index(drop=True)
        try:
            loco_rows.append(v7_variant_row(sub, headline, sesoi, B_LOCO, spec_id=f"C4-loco-{code}", group="C-LOCO", label=f"Leave out {code}", note=f"B = {B_LOCO}"))
        except Exception as error:  # noqa: BLE001
            loco_rows.append(failed_row(f"C4-loco-{code}", "C-LOCO", f"Leave out {code}", "V7", f"wild-cluster bootstrap-t, B={B_LOCO}", error))
            _log(f"C loco {code} FAILED: {type(error).__name__}: {error}")
        _log(f"C loco {code} done in {time.time() - t0:.1f}s")
    rows.extend(loco_rows)
    ok = [r for r in loco_rows if r["status"] == "ok"]
    notes["loco"] = loco_summary(ok, headline)
    return {"rows": rows, "notes": notes}


def loco_summary(ok_rows: list[dict[str, Any]], headline: dict[str, Any]) -> dict[str, Any]:
    """Range of the leave-one-out estimates and the country whose removal moves the estimate most (absolute shift from the headline)."""
    out: dict[str, Any] = {"n_fits": len(ok_rows)}
    for t in TESTED:
        head = headline["targets"][t]["estimate"]
        est = {r["id"].removeprefix("C4-loco-"): r["targets"][t]["estimate"] for r in ok_rows}
        far = max(est, key=lambda c: abs(est[c] - head))
        out[t] = {"headline": head, "min": min(est.values()), "max": max(est.values()), "argmin": min(est, key=est.get), "argmax": max(est, key=est.get),
                  "most_influential": far, "most_influential_estimate": est[far], "most_influential_shift": est[far] - head,
                  "n_interval_excludes_zero": int(sum(r["targets"][t]["excludes_zero"] for r in ok_rows)), "n_same_sign": int(sum(r["targets"][t]["same_sign_as_headline"] for r in ok_rows)),
                  "bootstrap_p_range": [min(r["targets"][t]["p"] for r in ok_rows), max(r["targets"][t]["p"] for r in ok_rows)]}
    return out


def run_section_d(frame: pd.DataFrame, headline: dict[str, Any], sesoi: float, n_boot: int = B_MAIN) -> dict[str, Any]:
    """Section D: definition variants of V7 (windows of 6 and 18 months, calendar-year dummy, alternative ageing moderators)."""
    frame = sorted_frame(frame)
    rows: list[dict[str, Any]] = []
    calendar = load_calendar()

    def run(spec_id: str, label: str, builder, **kwargs: Any) -> None:
        t0 = time.time()
        try:
            rows.append(v7_variant_row(builder(), headline, sesoi, n_boot, spec_id=spec_id, group="D", label=label, **kwargs))
            _log(f"D {spec_id} done in {time.time() - t0:.1f}s (N={rows[-1]['n_obs']})")
        except Exception as error:  # noqa: BLE001
            rows.append(failed_row(spec_id, "D", label, "V7", "wild-cluster bootstrap-t", error))
            _log(f"D {spec_id} FAILED: {type(error).__name__}: {error}")

    for months, sid in ((6, "D1-window-6m"), (18, "D2-window-18m")):
        def build(months=months) -> pd.DataFrame:
            expo = rebuild_exposure(calendar, pre_months=months)
            return with_columns(frame, expo, ["W_S", "W_E", "W_D", "W_U", "Post"])

        extra_note = (("exposure for 2021 needs elections through 2022-06" if months == 6 else "exposure for 2021 needs elections through 2023-06 (ParlGov coverage ends 2023-06; ETAD 2023 is partial)")
                      + f"; beta_S is per full year inside a {months}-month window, so a unit of exposure covers a different span of calendar time than in the headline (12 months): compare sign and interval, not magnitude")
        run(sid, f"Pre-election window of {months} months (all classes rebuilt; Post stays 12 months)", build, note=extra_note)

    def build_dummy() -> pd.DataFrame:
        return with_columns(frame, election_year_dummies(calendar), ["W_S", "W_E", "W_D", "W_U"])

    run("D3-calendar-year-dummy", "Calendar-year election dummies in place of the fractional pre-window exposure (W_S, W_E, W_D, W_U; Post kept)", build_dummy,
        note="scale differs from the headline: 1 = an election of the class occurs in year t, versus the share of the year inside the 12-month window")
    for col, sid, label in (("olddep3_lag", "D4-olddep3", "Moderator: OLDDEP3 lag (re-standardised, same Mundlak split)"), ("medage_lag", "D5-medage", "Moderator: median age lag (re-standardised, same Mundlak split)")):
        def build_mod(col=col) -> pd.DataFrame:
            sub = frame[frame[col].notna()].copy().reset_index(drop=True)
            sub["olddep1_lag"] = sub[col]
            return sub

        run(sid, label, build_mod, note=f"rows with {col} observed: {int(frame[col].notna().sum())} of {len(frame)}")
    return {"rows": rows}


def render_section_c(sec: dict[str, Any]) -> list[str]:
    """Markdown of section C."""
    rows = sec["rows"]
    main = [r for r in rows if r["group"] == "C"]
    loco = [r for r in rows if r["group"] == "C-LOCO"]
    lines = ["## C. Sample variants (V7, wild-cluster bootstrap-t B = 9,999; leave-one-out B = 999)", "",
             "The estimator is the pre-registered V7 in every row; the sample is changed as stated. Estimates and intervals follow the headline procedure (bootstrap-t percentile interval; p from the null-imposed bootstrap). "
             "CR1 numbers for each row are stored in the json (`extra.cr1_transparency`).", ""]
    lines += spec_table(main) + [""]
    ext = sec.get("notes", {}).get("extension_2022", {})
    if ext.get("built"):
        lines += [f"2022 extension: built with the frozen panel assembler (`assemble_gold_panel(..., end=2022)`); the 1995-2021 part reproduces the confirmatory extract exactly. N = {ext['n_obs']} (+{ext['added_2022']}); "
                  f"no 2022 for {', '.join(ext['countries_without_2022'])} (exposure not complete on the ETAD basis). Exposure for 2022 is complete only on trust in ETAD.", ""]
    elif ext:
        lines += [f"2022 extension: NOT BUILT. Reason: {ext.get('reason')}", ""]
    lines += ["### Leave-one-country-out (27 fits, B = 999)", ""]
    ls = sec.get("notes", {}).get("loco", {})
    for t in TESTED:
        e = ls.get(t)
        if e:
            lines.append(f"* {t}: headline {_f(e['headline'])}; leave-one-out estimates range from {_f(e['min'])} (without {e['argmin']}) to {_f(e['max'])} (without {e['argmax']}); "
                         f"largest shift from the headline when {e['most_influential']} is removed ({_f(e['most_influential_estimate'])}, shift {_f(e['most_influential_shift'])}); "
                         f"{e['n_same_sign']}/{ls['n_fits']} keep the sign; interval excludes zero in {e['n_interval_excludes_zero']}/{ls['n_fits']}; bootstrap p between {_f(e['bootstrap_p_range'][0], 4)} and {_f(e['bootstrap_p_range'][1], 4)}.")
    lines += ["", "| left out | beta_S: est [95% interval]; p; reading | gamma_B: est [95% interval]; p; reading |", "|---|---|---|"]
    for r in loco:
        if r["status"] != "ok":
            lines.append(f"| {r['label']} | FAILED: {r.get('error')} | |")
        else:
            lines.append(f"| {r['label'].removeprefix('Leave out ')} | {_cell(r['targets']['beta_S'])} | {_cell(r['targets']['gamma_B'])} |")
    return lines + [""]


def render_section_d(sec: dict[str, Any]) -> list[str]:
    """Markdown of section D."""
    lines = ["## D. Definition variants (V7, wild-cluster bootstrap-t B = 9,999)", "",
             "Windows are rebuilt from `data/interim/election_calendar_eu27.csv` by the share-of-year union construction (new code; the 12-month rebuild reproduces the frozen exposure columns to 1e-12, checked in the tests). "
             "The post-election window stays 12 months in the 6- and 18-month variants.", ""]
    lines += spec_table(sec["rows"]) + [""]
    return lines


RENDERERS["C"] = render_section_c
RENDERERS["D"] = render_section_d

# ---------------------------------------------------------------------------------------------
# Forest plot
# ---------------------------------------------------------------------------------------------
GROUP_TITLES = {"A": "A. Inference (same M1 regressors)", "C": "C. Sample variants (V7)", "C-LOCO": "C. Leave one country out (V7, B = 999)", "D": "D. Definitions (V7)"}
GROUP_COLOURS = {"A": "#1f77b4", "C": "#d95f02", "C-LOCO": "#7f7f7f", "D": "#7570b3"}  # colour-blind-safe qualitative set; headline in black


def _short_label(row: dict[str, Any]) -> str:
    """Compact label for the forest plot: the label, plus the inference method for group A."""
    label = row["label"]
    for old, new in (("Pre-election window of ", "Window "), (" (all classes rebuilt; Post stays 12 months)", ""), ("Calendar-year election dummies in place of the fractional pre-window exposure (W_S, W_E, W_D, W_U; Post kept)", "Calendar-year election dummy"),
                     ("Drop country-years touching unclassified or delayed elections", "Drop unclassified/delayed country-years"), (" (countries observed in all 27 years)", ""),
                     (" (ETAD-trusted exposure for 22 countries)", ""), ("Robustness-controls model (adds lagged output gap and euro membership)", "Controls: output gap, euro membership"),
                     ("Ireland 2010 handled by residual-tail winsorising (V2w rule, 1st/99th percentile)", "Ireland 2010 winsorised (V2w)"), ("Gap-filled election classes (*_gf exposure columns)", "Gap-filled election classes"),
                     ("Moderator: ", "Moderator "), (" (re-standardised, same Mundlak split)", ""), ("Two-way clustering (country, year), Cameron-Gelbach-Miller 2011", "Two-way clustering"),
                     ("Driscoll-Kraay, Bartlett kernel, ", "Driscoll-Kraay ")):
        label = label.replace(old, new)
    if row["group"] == "A":
        inf = row["inference"]
        short = "CR1" if inf.startswith("CR1") else "wild bootstrap" if inf.startswith("wild") else ""
        if short:
            label = f"{label} [{short}]"
    return label[:58]


def forest_plot(results: dict[str, Any], path: Path = FOREST_PATH) -> Path:
    """Forest plot of beta_S and gamma_B with 95% intervals for every specification, grouped A / C / D, with the zero line and the +-SESOI band."""
    import matplotlib  # noqa: PLC0415

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: PLC0415

    sesoi = float(results["meta"].get("sesoi_pp", 0.5))
    head = results["headline"]["targets"]
    rows = [r for r in all_rows(results) if r["status"] == "ok"]
    order = ["A", "C", "C-LOCO", "D"]
    layout: list[tuple[str, dict[str, Any] | None]] = [("H", None)]
    for g in order:
        members = [r for r in rows if r["group"] == g]
        if members:
            layout.append((g, None))
            layout.extend((g, r) for r in members)
    n = len(layout)
    fig, axes = plt.subplots(1, 2, figsize=(13, max(8.0, 0.215 * n + 2.4)), sharey=True)
    for ax, target, title in ((axes[0], "beta_S", "beta_S: a full year of pre-election exposure to a scheduled election"), (axes[1], "gamma_B", "gamma_B: per +1 SD of between-country ageing")):
        ax.axvspan(-sesoi, sesoi, color="#e8e8e8", zorder=0, label=f"±{sesoi} pp (smallest effect size of interest)")
        ax.axvline(0.0, color="black", lw=0.8, zorder=1)
        ys, labels = [], []
        for i, (g, r) in enumerate(layout):
            y = n - i
            if g == "H":
                est, lo, hi = head[target]["estimate"], head[target]["ci_lo"], head[target]["ci_hi"]
                ax.errorbar(est, y, xerr=[[est - lo], [hi - est]], fmt="D", color="black", ms=5, lw=1.6, capsize=2, zorder=3)
                labels.append("Headline: V7, pre-registered")
                ys.append(y)
            elif r is None:
                ax.axhline(y + 0.5, color="#bbbbbb", lw=0.5)
                ys.append(y)
                labels.append(GROUP_TITLES[g])
            else:
                t = r["targets"][target]
                est, lo, hi = t["estimate"], t["ci_lo"], t["ci_hi"]
                ax.errorbar(est, y, xerr=[[est - lo], [hi - est]], fmt="o", color=GROUP_COLOURS[g], ms=3.6, lw=1.1, capsize=1.5, zorder=2)
                ys.append(y)
                labels.append(_short_label(r))
        ax.set_yticks(ys)
        ax.set_yticklabels(labels, fontsize=7)
        for tick, (g, r) in zip(ax.get_yticklabels(), layout):
            if r is None and g != "H":
                tick.set_fontweight("bold")
        ax.set_ylim(0.3, n + 0.9)
        ax.set_xlabel("Estimate and 95% interval (pp of potential GDP" + ("; interaction per +1 SD)" if target == "gamma_B" else " per unit of exposure)"), fontsize=8)
        ax.set_title(title, fontsize=9)
        ax.tick_params(axis="x", labelsize=8)
        ax.grid(axis="x", color="#dddddd", lw=0.4)
    axes[0].legend(loc="upper right", fontsize=7, frameon=False)
    fig.suptitle("Robustness of the association between scheduled elections and the cyclically adjusted primary balance, EU-27, 1995-2021", fontsize=10, y=0.995)
    fig.text(0.01, 0.003, SOURCE_LINE + ". Associations only; specifications are not independent; no specification is preferred.", fontsize=7, ha="left", va="bottom")
    fig.tight_layout(rect=(0, 0.015, 1, 0.985))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=300)
    plt.close(fig)
    return path


# ==== MAIN ====
def runners() -> dict[str, Any]:
    """Section name -> function(frame, headline, sesoi, n_boot) returning the section payload."""
    table: dict[str, Any] = {"A": run_section_a}
    for name in ("B", "C", "D"):
        fn = globals().get(f"run_section_{name.lower()}")
        if fn is not None:
            table[name] = fn
    return table


def run_sections(sections: list[str], n_boot: int = B_MAIN) -> dict[str, Any]:
    """Run the named sections on the real panel and write json + markdown after each one."""
    frame, digest = load_panel()
    headline = load_headline()
    sesoi = float(headline["sesoi_pp"])
    results = load_results()
    results["meta"] = meta_block(digest, headline)
    results["headline"] = headline
    table = runners()
    for name in sections:
        if name not in table:
            raise SystemExit(f"section {name} is not implemented")
        t0 = time.time()
        _log(f"section {name}: start")
        results["sections"][name] = table[name](frame, headline, sesoi, n_boot)
        results["meta"] = meta_block(digest, headline)
        write_results(results)
        _log(f"section {name}: done in {time.time() - t0:.0f}s, files written")
    return results


def main(argv: list[str] | None = None) -> int:
    """``.venv/Scripts/python.exe src/models/py/robustness.py --sections A B C D E``: run the suite on the real panel (needs the tag)."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sections", nargs="+", default=["A", "B", "C", "D"], help="sections to run, in order (A B C D); E (plot) is run by --plot")
    parser.add_argument("--n-boot", type=int, default=B_MAIN)
    parser.add_argument("--plot", action="store_true", help="redraw the forest plot from the json")
    args = parser.parse_args(argv)
    if args.sections:
        run_sections([s for s in args.sections if s != "E"], args.n_boot)
    if args.plot or "E" in args.sections:
        draw = globals().get("forest_plot")
        if draw is None:
            raise SystemExit("forest plot not implemented")
        draw(load_results())
    return 0


if __name__ == "__main__":
    sys.exit(main())
