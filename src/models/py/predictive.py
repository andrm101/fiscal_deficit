"""Predictive module (issue 31): rolling-origin forecasts of the next-year change in CAPB, non-causal.

Specification: ``docs/predictive_spec.md`` (dated 2026-10-13, written before any predictive result existed). This module implements it
exactly; every departure is listed under "Deviations" in ``reports/results/predictive.md`` (``DEVIATIONS`` below).

Information set. The origin T is the end of calendar year T. For country i the target is ``y = capb_{T+1} - capb_T`` (consecutive years).
Features are dated on or before T: ``capb_T``, ``dcapb_T`` (row T), ``debt_gdp_T``, ``outgap_T``, ``ig_diff_T``, ``olddep1_T``,
``olddep3_T``, ``medage_T`` (the ``*_lag`` columns of the forecast-year row T + 1, dated T), ``euro_T`` (row T) and four election
features built here from the calendar: elections held on or before 31 December T plus the statutory next date
``d_E + round(365.25 * L_E)`` (never the realised class or date of a later election). The frozen exposure columns are not predictors.

Everything that is fitted (country means, standardisation, hyperparameters, early-stopping iteration) uses the training window only and is
re-done at every origin. Seeds: ``power.make_rng(6000, purpose, ...)`` (key 6000 unused elsewhere). Nothing here is run on the real outcome
before the git tag ``preregistration-v1`` exists (``main`` calls :func:`m1.require_preregistration_tag`).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import warnings
from pathlib import Path
from typing import Any, Callable, Sequence

for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")  # small matrices: one BLAS/OpenMP thread per worker; parallelism is across jobs
import numpy as np
import pandas as pd
from scipy import stats

try:  # numpy may already be imported by the caller: limit the BLAS thread pool explicitly
    from threadpoolctl import threadpool_limits

    threadpool_limits(limits=1)
except ImportError:  # pragma: no cover
    pass

_SRC = Path(__file__).resolve().parents[2]
for _sub in ("models/py", "evaluate", "normalize", "features"):
    sys.path.insert(0, str(_SRC / _sub))
import m1  # noqa: E402
import power  # noqa: E402

PROJECT_ROOT = _SRC.parent
RESULTS_DIR = PROJECT_ROOT / "reports" / "results"
FIGURES_DIR = PROJECT_ROOT / "reports" / "figures"
JSON_PATH = RESULTS_DIR / "predictive.json"
MD_PATH = RESULTS_DIR / "predictive.md"
CACHE_DIR = PROJECT_ROOT / "data" / "interim" / "predictive_cache"
CALENDAR_CSV = PROJECT_ROOT / "data" / "interim" / "election_calendar_eu27.csv"
SPEC_PATH = PROJECT_ROOT / "docs" / "predictive_spec.md"
FREEZE_MANIFEST = PROJECT_ROOT / "docs" / "freeze_manifest.json"
ERRORS_FIG = FIGURES_DIR / "predictive_errors.png"
IMPORTANCE_FIG = FIGURES_DIR / "predictive_importance.png"
SOURCE_LINE = "Source: European Commission AMECO Spring 2026, Eurostat, ETAD v1.0.0 and ParlGov 2024; author's calculations"

# ---------------------------------------------------------------------------------------------
# Constants fixed by the specification
# ---------------------------------------------------------------------------------------------
SEED_KEY = 6000
PURPOSE_PERM, PURPOSE_BOOT, PURPOSE_AUX = 1, 2, 3
ORIGINS_P = tuple(range(2008, 2021))  # forecast years 2009-2021 (13 origins)
ORIGINS_H = (2021, 2022)  # forecast years 2022-2023
FIRST_TRAIN_YEAR = 1997
LAST_FORECAST_YEAR = 2023
B_BOOT = 9_999
N_INNER = 5
SESOI = 0.5  # pp, config/registry/confirmatory.toml
DEFAULT_TERM = 5.0  # CY, MT (calendar expected_term_years)
EXP_B = 300  # maximum boosting iterations

CONT_FISCAL = ["capb_T", "dcapb_T", "debt_gdp_T", "outgap_T", "ig_diff_T"]
CONT_DEMO = ["olddep1_T", "olddep3_T", "medage_T"]
RAW_FISCAL = ["euro_T"]
POLITICAL = ["Wk_next", "Wk_now", "Postk_next", "Postk_now"]
POLITICAL_ORACLE = ["Wk_next_o", "Wk_now_o", "Postk_next", "Postk_now"]
FROZEN_REALISED = ["fW_S", "fW_E", "fW_U"]
B2_COLUMNS = CONT_FISCAL + CONT_DEMO + RAW_FISCAL + POLITICAL

# set -> (columns entered as within/between pairs, columns entered raw)
SETS: dict[str, tuple[list[str], list[str]]] = {
    "B0": (["capb_T", "dcapb_T"], []),
    "B1": (CONT_FISCAL, RAW_FISCAL),
    "B2": (CONT_FISCAL + CONT_DEMO, RAW_FISCAL + POLITICAL),
    "B2p": (CONT_FISCAL, RAW_FISCAL + POLITICAL),
    "B2d": (CONT_FISCAL + CONT_DEMO, RAW_FISCAL),
    "B2o": (CONT_FISCAL + CONT_DEMO, RAW_FISCAL + POLITICAL_ORACLE),
    "B2f": (CONT_FISCAL + CONT_DEMO, RAW_FISCAL + POLITICAL + FROZEN_REALISED),
}
GAM_SMOOTH = {"B1": ["capb_T", "dcapb_T", "debt_gdp_T", "outgap_T", "ig_diff_T"], "B2": ["capb_T", "dcapb_T", "debt_gdp_T", "outgap_T", "ig_diff_T", "Wk_next", "olddep1_T"]}

ALPHAS = (0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0)
L1_RATIOS = (0.2, 0.5, 0.8)
HGB_GRID = tuple((d, leaf, l2) for d in (2, 3) for leaf in (20, 40) for l2 in (0.0, 1.0))
GAM_ALPHAS = (1.0, 10.0, 100.0, 1000.0)
LOGIT_C = (0.01, 0.1, 1.0, 10.0)

HOLM_FAMILY = (
    ("P1a-B1 vs P0", "P1a-B1", "P0"),
    ("P1b-B1 vs P0", "P1b-B1", "P0"),
    ("P1a-B2 vs P0", "P1a-B2", "P0"),
    ("P1b-B2 vs P0", "P1b-B2", "P0"),
    ("P1a: B2 vs B1", "P1a-B2", "P1a-B1"),
    ("P1b: B2 vs B1", "P1b-B2", "P1b-B1"),
)
ALE_FEATURES = ("capb_T_dm", "dcapb_T_dm", "debt_gdp_T_dm", "outgap_T_dm", "Wk_next", "olddep1_T_dm")
FORBIDDEN_WORDS = ("causes", "caused by", "impact of", "effect of", "driven by", "leads to", "due to the election")
DEVIATIONS: list[str] = []  # filled at run time by the stages (nothing is deviated from silently)


# ---------------------------------------------------------------------------------------------
# Election features known at the origin
# ---------------------------------------------------------------------------------------------
def _union_share(windows: Sequence[tuple[pd.Timestamp, pd.Timestamp]], year: int) -> float:
    """Share of calendar ``year`` inside the union of half-open day windows ``[start, end)``."""
    lo, hi = pd.Timestamp(year, 1, 1), pd.Timestamp(year + 1, 1, 1)
    n = (hi - lo).days
    mask = np.zeros(n, dtype=bool)
    for start, end in windows:
        a, b = max((start - lo).days, 0), min((end - lo).days, n)
        if b > a:
            mask[a:b] = True
    return float(mask.mean())


def load_calendar(path: Path = CALENDAR_CSV) -> pd.DataFrame:
    """The interim election calendar with parsed dates, restricted to ``in_calendar`` rows, sorted by country and date."""
    cal = pd.read_csv(path, parse_dates=["date_used", "sche_date"])
    cal = cal[cal["in_calendar"].astype(bool)]
    return cal.sort_values(["eurostat_code", "date_used"]).reset_index(drop=True)


def statutory_term(held: pd.DataFrame) -> float:
    """``L_E``: ETAD ``termlength`` of the latest election, else the last non-missing one among elections held, else 5.0 (CY, MT)."""
    terms = held["termlength"].dropna()
    return float(terms.iloc[-1]) if len(terms) else DEFAULT_TERM


def known_exposure(cal_country: pd.DataFrame, origin: int, oracle: bool = False) -> dict[str, float]:
    """``Wk_next, Wk_now, Postk_next, Postk_now`` of one country at origin ``origin`` (end of that year).

    Only elections dated on or before 31 December ``origin`` are read (``date_used`` and ``termlength``). The scheduled date of the next
    election is ``d_E + round(365.25 * L_E)`` days. With ``oracle=True`` the ETAD ``sche_date`` of the next recorded election is used when
    present (an ex-post record: a deliberately leaking diagnostic, never a forecast).
    """
    nan = {"Wk_next": np.nan, "Wk_now": np.nan, "Postk_next": np.nan, "Postk_now": np.nan}
    end = pd.Timestamp(origin, 12, 31)
    held = cal_country[cal_country["date_used"] <= end]
    if held.empty:
        return nan
    d_e = held["date_used"].iloc[-1]
    sched = d_e + pd.Timedelta(days=round(365.25 * statutory_term(held)))
    if oracle:
        later = cal_country[cal_country["date_used"] > d_e]
        if len(later) and pd.notna(later["sche_date"].iloc[0]):
            sched = later["sche_date"].iloc[0]
    year_off = pd.DateOffset(years=1)
    pre = [(d - year_off, d) for d in held["date_used"]] + [(sched - year_off, sched)]
    post = [(d, d + year_off) for d in held["date_used"]]
    return {"Wk_next": _union_share(pre, origin + 1), "Wk_now": _union_share(pre, origin), "Postk_next": _union_share(post, origin + 1), "Postk_now": _union_share(post, origin)}


def political_features(cal: pd.DataFrame, codes: Sequence[str], origins: Sequence[int], oracle: bool = False) -> pd.DataFrame:
    """Known-at-origin election features for every (country, origin)."""
    rows = []
    for code in codes:
        sub = cal[cal["eurostat_code"] == code]
        for t in origins:
            rows.append({"code": code, "origin": int(t), **known_exposure(sub, int(t), oracle=oracle)})
    return pd.DataFrame(rows)


def schedule_agreement(cal: pd.DataFrame, tol_days: int = 31) -> dict[str, float]:
    """Descriptive check on election dates only: ``date(previous) + termlength(previous)`` against ETAD ``sche_date`` (share within ``tol_days``)."""
    c = cal.sort_values(["eurostat_code", "date_used"]).copy()
    c["prev"] = c.groupby("eurostat_code")["date_used"].shift(1)
    c["prev_term"] = c.groupby("eurostat_code")["termlength"].shift(1)
    ok = c["prev"].notna() & c["prev_term"].notna() & c["sche_date"].notna()
    pred = c.loc[ok, "prev"] + pd.to_timedelta(c.loc[ok, "prev_term"] * 365.25, unit="D")
    diff = (c.loc[ok, "sche_date"] - pred).dt.days.abs()
    return {"n_pairs": int(ok.sum()), "share_within_tolerance": float((diff <= tol_days).mean()), "tolerance_days": tol_days}


# ---------------------------------------------------------------------------------------------
# Origin panel
# ---------------------------------------------------------------------------------------------
def build_origin_panel(gold: pd.DataFrame, cal: pd.DataFrame, origins: Sequence[int] | None = None) -> pd.DataFrame:
    """One row per (country, origin T): target ``y`` (forecast-year row T + 1) and the features dated on or before T.

    ``gold`` has the gold-panel columns ``eurostat_code, year, capb, sec_d_capb, debt_gdp_lag, outgap_lag, ig_diff_lag, euro_member,
    olddep1_lag, olddep3_lag, medage_lag, W_S, W_E, W_U``. The ``*_lag`` columns of row T + 1 are dated T; ``capb``, ``sec_d_capb`` and
    ``euro_member`` are read from row T. Row joins are explicit calendar joins on (country, year), never row shifts.
    """
    g = gold.rename(columns={"eurostat_code": "code"})
    cur = g[["code", "year", "capb", "sec_d_capb", "euro_member"]].rename(columns={"year": "origin", "capb": "capb_T", "sec_d_capb": "dcapb_T", "euro_member": "euro_T"})
    nxt = g[["code", "year", "sec_d_capb", "debt_gdp_lag", "outgap_lag", "ig_diff_lag", "olddep1_lag", "olddep3_lag", "medage_lag", "W_S", "W_E", "W_U"]].copy()
    nxt["origin"] = nxt["year"] - 1
    nxt = nxt.rename(columns={"year": "forecast_year", "sec_d_capb": "y", "debt_gdp_lag": "debt_gdp_T", "outgap_lag": "outgap_T", "ig_diff_lag": "ig_diff_T",
                              "olddep1_lag": "olddep1_T", "olddep3_lag": "olddep3_T", "medage_lag": "medage_T", "W_S": "fW_S", "W_E": "fW_E", "W_U": "fW_U"})
    op = cur.merge(nxt, on=["code", "origin"], how="inner", validate="one_to_one")
    if origins is not None:
        op = op[op["origin"].isin(list(origins))]
    op["euro_T"] = op["euro_T"].astype(float)
    codes = sorted(op["code"].unique())
    strict = political_features(cal, codes, sorted(op["origin"].unique()), oracle=False)
    oracle = political_features(cal, codes, sorted(op["origin"].unique()), oracle=True)[["code", "origin", "Wk_next", "Wk_now"]].rename(columns={"Wk_next": "Wk_next_o", "Wk_now": "Wk_now_o"})
    op = op.merge(strict, on=["code", "origin"], how="left", validate="one_to_one").merge(oracle, on=["code", "origin"], how="left", validate="one_to_one")
    op["complete"] = op["y"].notna() & op[B2_COLUMNS].notna().all(axis=1) & op["forecast_year"].between(FIRST_TRAIN_YEAR, LAST_FORECAST_YEAR)
    return op.sort_values(["code", "origin"]).reset_index(drop=True)


# ---------------------------------------------------------------------------------------------
# Feature transformation (training-window statistics only)
# ---------------------------------------------------------------------------------------------
class Transformer:
    """Country-demeaned (CD) or pooled (POOL) feature matrix, standardised with training-window mean and population SD."""

    def __init__(self, cont: Sequence[str], raw: Sequence[str], scheme: str = "CD") -> None:
        self.cont, self.raw, self.scheme = list(cont), list(raw), scheme

    def _matrix(self, df: pd.DataFrame, means: pd.DataFrame | None) -> tuple[np.ndarray, list[str]]:
        cols: list[np.ndarray] = []
        names: list[str] = []
        for c in self.cont:
            x = df[c].to_numpy(float)
            if self.scheme == "CD":
                m = df["code"].map(means[c]).to_numpy(float)
                cols += [x - m, m]
                names += [f"{c}_dm", f"{c}_bar"]
            else:
                cols.append(x)
                names.append(c)
        for c in self.raw:
            cols.append(df[c].to_numpy(float))
            names.append(c)
        return np.column_stack(cols), names

    def fit(self, train: pd.DataFrame) -> "Transformer":
        self.means = train.groupby("code")[self.cont].mean() if self.cont else None
        x, names = self._matrix(train, self.means)
        mu, sd = x.mean(axis=0), x.std(axis=0, ddof=0)
        self.keep = sd > 1e-12
        self.mu, self.sd = mu[self.keep], sd[self.keep]
        self.all_names = names
        self.names = [n for n, k in zip(names, self.keep, strict=True) if k]
        self.dropped = [n for n, k in zip(names, self.keep, strict=True) if not k]
        return self

    def transform(self, df: pd.DataFrame, means: pd.DataFrame | None = None) -> np.ndarray:
        x, _ = self._matrix(df, self.means if means is None else means)
        z = (x[:, self.keep] - self.mu) / self.sd
        if not np.isfinite(z).all():
            raise ValueError("non-finite feature after transformation (a country without a training mean?)")
        return z


# ---------------------------------------------------------------------------------------------
# Inner time-series validation and the models
# ---------------------------------------------------------------------------------------------
def inner_folds(train: pd.DataFrame, origin: int, n_inner: int = N_INNER) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    """Inner folds: validation years v = T - n + 1, ..., T; fit on forecast years <= v - 1, score on year v (training window only)."""
    out = []
    for v in range(origin - n_inner + 1, origin + 1):
        tr, va = train[train["forecast_year"] <= v - 1], train[train["forecast_year"] == v]
        if len(tr) and len(va):
            out.append((tr, va))
    return out


class Fitted:
    """A fitted forecaster: transformer plus estimator, with the chosen hyperparameters."""

    def __init__(self, tf: Transformer, est: Any, info: dict[str, Any], predict_fn: Callable[[Any, np.ndarray], np.ndarray] | None = None) -> None:
        self.tf, self.est, self.info, self._predict = tf, est, info, predict_fn

    def matrix(self, df: pd.DataFrame, means: pd.DataFrame | None = None) -> np.ndarray:
        return self.tf.transform(df, means)

    def predict_matrix(self, x: np.ndarray) -> np.ndarray:
        return np.asarray(self._predict(self.est, x) if self._predict else self.est.predict(x), float)

    def predict(self, df: pd.DataFrame, means: pd.DataFrame | None = None) -> np.ndarray:
        return self.predict_matrix(self.matrix(df, means))


def _linear_configs(alphas: Sequence[float] = ALPHAS, l1: Sequence[float] = L1_RATIOS) -> list[tuple[str, float, float]]:
    return [("ridge", a, 0.0) for a in alphas] + [("enet", a, r) for a in alphas for r in l1]


def _build_linear(cfg: tuple[str, float, float]) -> Any:
    from sklearn.linear_model import ElasticNet, Ridge

    kind, alpha, ratio = cfg
    if kind == "ridge":
        return Ridge(alpha=alpha)
    return ElasticNet(alpha=alpha, l1_ratio=ratio, max_iter=100_000, tol=1e-8)


def _pick(scores: np.ndarray, order_keys: Sequence[tuple]) -> int:
    """Index of the smallest score; ties (within 1e-12) go to the smallest order key (the more regularised configuration)."""
    best = float(np.min(scores))
    tied = [i for i, s in enumerate(scores) if s <= best + 1e-12]
    return min(tied, key=lambda i: order_keys[i])


def fit_linear(train: pd.DataFrame, origin: int, set_name: str, scheme: str = "CD", alphas: Sequence[float] = ALPHAS, l1: Sequence[float] = L1_RATIOS) -> Fitted:
    """P1a: ridge / elastic net, configuration chosen by the inner time-series validation inside ``train``."""
    cont, raw = SETS[set_name]
    configs = _linear_configs(alphas, l1)
    prepped = []
    for tr, va in inner_folds(train, origin):
        tf = Transformer(cont, raw, scheme).fit(tr)
        prepped.append((tf.transform(tr), tr["y"].to_numpy(float), tf.transform(va), va["y"].to_numpy(float)))
    scores = np.zeros(len(configs))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for i, cfg in enumerate(configs):
            fold = []
            for xtr, ytr, xva, yva in prepped:
                est = _build_linear(cfg).fit(xtr, ytr)
                fold.append(float(np.mean((yva - est.predict(xva)) ** 2)))
            scores[i] = float(np.mean(fold))
        keys = [(-a, r, 0 if k == "ridge" else 1) for k, a, r in configs]
        best = _pick(scores, keys)
        tf = Transformer(cont, raw, scheme).fit(train)
        est = _build_linear(configs[best]).fit(tf.transform(train), train["y"].to_numpy(float))
    kind, alpha, ratio = configs[best]
    return Fitted(tf, est, {"model": "P1a", "kind": kind, "alpha": alpha, "l1_ratio": ratio, "inner_mse": float(scores[best]), "n_train": int(len(train)), "dropped": tf.dropped,
                            "n_nonzero": int(np.sum(np.abs(est.coef_) > 1e-12))})


def _build_hgb(depth: int, leaf: int, l2: float, max_iter: int) -> Any:
    from sklearn.ensemble import HistGradientBoostingRegressor

    return HistGradientBoostingRegressor(loss="squared_error", learning_rate=0.05, max_iter=max_iter, early_stopping=False, max_bins=255, max_leaf_nodes=None,
                                         max_depth=depth, min_samples_leaf=leaf, l2_regularization=l2, random_state=42)


def fit_hgb(train: pd.DataFrame, origin: int, set_name: str, scheme: str = "CD", grid: Sequence[tuple[int, int, float]] = HGB_GRID, max_iter: int = EXP_B) -> Fitted:
    """P1b: histogram gradient boosting; (configuration, iteration count) = argmin of the mean inner validation MSE (time-ordered folds)."""
    cont, raw = SETS[set_name]
    prepped = []
    for tr, va in inner_folds(train, origin):
        tf = Transformer(cont, raw, scheme).fit(tr)
        prepped.append((tf.transform(tr), tr["y"].to_numpy(float), tf.transform(va), va["y"].to_numpy(float)))
    scores = np.zeros((len(grid), max_iter))
    for i, (d, leaf, l2) in enumerate(grid):
        per_fold = []
        for xtr, ytr, xva, yva in prepped:
            est = _build_hgb(d, leaf, l2, max_iter).fit(xtr, ytr)
            staged = np.array([p for p in est.staged_predict(xva)])  # (iterations, n_val)
            per_fold.append(np.mean((yva[None, :] - staged) ** 2, axis=1))
        scores[i] = np.mean(per_fold, axis=0)
    flat = scores.ravel()
    best_val = float(flat.min())
    cand = [(m, d, -leaf, l2, i) for i, (d, leaf, l2) in enumerate(grid) for m in range(max_iter) if scores[i, m] <= best_val + 1e-12]
    m_star, _, _, _, gi = min(cand)  # smallest iteration, then smaller depth, larger leaf, smaller l2
    d, leaf, l2 = grid[gi]
    tf = Transformer(cont, raw, scheme).fit(train)
    est = _build_hgb(d, leaf, l2, m_star + 1).fit(tf.transform(train), train["y"].to_numpy(float))
    return Fitted(tf, est, {"model": "P1b", "max_depth": d, "min_samples_leaf": leaf, "l2_regularization": l2, "n_iter": m_star + 1, "inner_mse": best_val,
                            "n_train": int(len(train)), "dropped": tf.dropped})


def _gam_design(tf: Transformer, x: np.ndarray, smooth_names: Sequence[str]) -> tuple[np.ndarray, np.ndarray, list[int]]:
    idx = [tf.names.index(n) for n in smooth_names if n in tf.names]
    lin = [j for j in range(x.shape[1]) if j not in idx]
    return np.column_stack([np.ones(len(x)), x[:, lin]]), x[:, idx], idx


def fit_gam(train: pd.DataFrame, origin: int, set_name: str, scheme: str = "CD", alphas: Sequence[float] = GAM_ALPHAS) -> Fitted:
    """P1c: Gaussian GAM (statsmodels GLMGam, cubic B-splines with 4 df) on the within-country parts of pre-listed variables."""
    from statsmodels.gam.api import BSplines, GLMGam

    cont, raw = SETS[set_name]
    smooth_vars = [f"{c}_dm" if c in cont else c for c in GAM_SMOOTH[set_name]]

    def fit_one(tr: pd.DataFrame, alpha: float) -> tuple[Transformer, Any, np.ndarray, np.ndarray, list[int], BSplines]:
        tf = Transformer(cont, raw, scheme).fit(tr)
        x = tf.transform(tr)
        lin, sm, idx = _gam_design(tf, x, smooth_vars)
        lo, hi = sm.min(axis=0), sm.max(axis=0)
        bs = BSplines(sm, df=[4] * sm.shape[1], degree=[3] * sm.shape[1], include_intercept=False)
        res = GLMGam(tr["y"].to_numpy(float), exog=lin, smoother=bs, alpha=[alpha] * sm.shape[1]).fit()
        return tf, res, lo, hi, idx, bs

    def pred(model: tuple, df: pd.DataFrame) -> np.ndarray:
        tf, res, lo, hi, idx, bs = model
        x = tf.transform(df)
        lin, sm, _ = _gam_design(tf, x, smooth_vars)
        sm = np.clip(sm, lo, hi)
        return np.asarray(res.predict(exog=lin, exog_smooth=sm), float)

    scores = np.zeros(len(alphas))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for i, a in enumerate(alphas):
            fold = []
            for tr, va in inner_folds(train, origin):
                fold.append(float(np.mean((va["y"].to_numpy(float) - pred(fit_one(tr, a), va)) ** 2)))
            scores[i] = float(np.mean(fold))
        best = _pick(scores, [(-a,) for a in alphas])
        model = fit_one(train, alphas[best])
    fitted = Fitted(model[0], model, {"model": "P1c", "alpha": alphas[best], "inner_mse": float(scores[best]), "n_train": int(len(train))}, predict_fn=None)
    fitted.predict = lambda df, means=None, _m=model: pred(_m, df)  # type: ignore[method-assign]
    return fitted


def make_fitter(model: str, set_name: str, scheme: str = "CD") -> Callable[[pd.DataFrame, int], Fitted]:
    if model == "P1a":
        return lambda train, origin: fit_linear(train, origin, set_name, scheme)
    if model == "P1b":
        return lambda train, origin: fit_hgb(train, origin, set_name, scheme)
    if model == "P1c":
        return lambda train, origin: fit_gam(train, origin, set_name, scheme)
    raise ValueError(f"unknown model {model}")


def training_window(op: pd.DataFrame, origin: int, exclude: str | None = None) -> pd.DataFrame:
    """Complete rows with forecast year <= origin (targets realised by the end of ``origin``), optionally without one country."""
    tr = op[op["complete"] & (op["forecast_year"] <= origin)]
    return tr[tr["code"] != exclude] if exclude else tr


def test_rows(op: pd.DataFrame, origin: int, only: str | None = None) -> pd.DataFrame:
    te = op[op["complete"] & (op["origin"] == origin)]
    return te[te["code"] == only] if only else te


# ---------------------------------------------------------------------------------------------
# Jobs (one origin x model x set x scheme x optional held-out country), cached on disk
# ---------------------------------------------------------------------------------------------
def permutation_and_ale(fitted: Fitted, test: pd.DataFrame, train: pd.DataFrame, origin: int, model_id: int, reps: int = 200, do_ale: bool = False) -> dict[str, Any]:
    """Out-of-sample grouped and single-column permutation importance at one origin (and ALE curves when ``do_ale``)."""
    names = fitted.tf.names
    x = fitted.matrix(test)
    y = test["y"].to_numpy(float)
    codes = test["code"].to_numpy()
    base_e2 = (y - fitted.predict_matrix(x)) ** 2
    pol = [i for i, n in enumerate(names) if n in POLITICAL]
    demo = [i for i, n in enumerate(names) if any(n == f"{c}_{s}" for c in CONT_DEMO for s in ("dm", "bar"))]
    fiscal = [i for i in range(len(names)) if i not in pol and i not in demo]
    items: dict[str, list[int]] = {"group:fiscal_macro": fiscal, "group:political": pol, "group:demographic": demo}
    items.update({f"col:{n}": [i] for i, n in enumerate(names)})
    inc = {k: np.zeros(len(y)) for k in items}
    for r in range(reps):
        rng = power.make_rng(SEED_KEY, PURPOSE_PERM, origin, r, model_id)
        for k, cols in items.items():
            if not cols:
                continue
            perm = rng.permutation(len(y))
            xp = x.copy()
            xp[:, cols] = x[perm][:, cols]
            inc[k] += (y - fitted.predict_matrix(xp)) ** 2 - base_e2
    out = {"codes": [str(c) for c in codes], "base_e2": base_e2.tolist(), "inc": {k: (v / reps).tolist() for k, v in inc.items() if items[k]}, "names": names}
    if do_ale:
        xt = fitted.matrix(train)
        ale = {}
        for feat in ALE_FEATURES:
            if feat in names:
                j = names.index(feat)
                edges, curve = ale_first_order(fitted.predict_matrix, xt, j)
                ale[feat] = {"edges": (edges * fitted.tf.sd[j] + fitted.tf.mu[j]).tolist(), "ale": curve.tolist()}
        out["ale"] = ale
    return out


def ale_first_order(predict: Callable[[np.ndarray], np.ndarray], x: np.ndarray, j: int, n_bins: int = 10) -> tuple[np.ndarray, np.ndarray]:
    """First-order accumulated local effects of column ``j`` (equal-count bins, centred); returns bin edges and the ALE at the edges."""
    col = x[:, j]
    edges = np.unique(np.quantile(col, np.linspace(0.0, 1.0, n_bins + 1)))
    k = len(edges) - 1
    if k < 1:
        return edges, np.zeros_like(edges)
    idx = np.clip(np.searchsorted(edges, col, side="right") - 1, 0, k - 1)
    eff, cnt = np.zeros(k), np.zeros(k)
    for b in range(k):
        m = idx == b
        if m.any():
            hi, lo = x[m].copy(), x[m].copy()
            hi[:, j], lo[:, j] = edges[b + 1], edges[b]
            eff[b] = float(np.mean(predict(hi) - predict(lo)))
            cnt[b] = m.sum()
    ale = np.concatenate([[0.0], np.cumsum(eff)])
    mid = (ale[:-1] + ale[1:]) / 2
    return edges, ale - float(np.sum(mid * cnt) / cnt.sum())


def job_name(job: dict[str, Any]) -> str:
    return "__".join(str(job.get(k)) for k in ("kind", "model", "set", "scheme", "loco", "origin"))


def run_job(job: dict[str, Any], op: pd.DataFrame, cache: Path | None = CACHE_DIR) -> dict[str, Any]:
    """Fit one forecaster at one origin and forecast the test rows. Cached as JSON; a cached result is returned unchanged."""
    path = None if cache is None else cache / f"{job_name(job)}.json"
    if path is not None and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    origin, loco = int(job["origin"]), job.get("loco")
    train = training_window(op, origin, exclude=loco)
    test = test_rows(op, origin, only=loco)
    t0 = time.time()
    result: dict[str, Any] = {k: job.get(k) for k in ("kind", "model", "set", "scheme", "loco", "origin")}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if job["kind"] == "event":
                result.update(_event_job(job, train, test, origin))
            else:
                fitted = make_fitter(job["model"], job["set"], job.get("scheme", "CD"))(train, origin)
                means = None
                if loco:  # the held-out country's own feature history (training-window rule) supplies its country means
                    hist = training_window(op, origin)
                    hist = hist[hist["code"] == loco]
                    cont = SETS[job["set"]][0]
                    means = hist.groupby("code")[cont].mean()
                yhat = fitted.predict(test, means)
                result["preds"] = {"code": test["code"].tolist(), "forecast_year": test["forecast_year"].tolist(), "y": test["y"].tolist(), "yhat": yhat.tolist()}
                result["hyper"] = fitted.info
                if job.get("extras") and job["model"] in ("P1a", "P1b"):
                    result["importance"] = permutation_and_ale(fitted, test, train, origin, 1 if job["model"] == "P1a" else 2, do_ale=bool(job.get("ale")))
        result["status"] = "ok"
    except Exception as error:  # a failed fit is reported as failed, never re-specified
        result["status"] = "failed"
        result["error"] = f"{type(error).__name__}: {error}"
    result["seconds"] = round(time.time() - t0, 2)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(result), encoding="utf-8")
        os.replace(tmp, path)
    return result


# ---------------------------------------------------------------------------------------------
# Binary deterioration event (optional, secondary)
# ---------------------------------------------------------------------------------------------
def _event_job(job: dict[str, Any], train: pd.DataFrame, test: pd.DataFrame, origin: int) -> dict[str, Any]:
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression

    cont, raw = SETS[job["set"]]
    lab = lambda d: (d["y"].to_numpy(float) < -SESOI).astype(int)  # noqa: E731
    rate = float(lab(train).mean())
    folds = []
    for tr, va in inner_folds(train, origin):
        tf = Transformer(cont, raw, "CD").fit(tr)
        folds.append((tf.transform(tr), lab(tr), tf.transform(va), lab(va)))

    def ll(y: np.ndarray, p: np.ndarray) -> float:
        p = np.clip(p, 1e-6, 1 - 1e-6)
        return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))

    tf = Transformer(cont, raw, "CD").fit(train)
    xtr, ytr, xte = tf.transform(train), lab(train), tf.transform(test)
    if job["model"] == "P1a":
        scores = []
        for c in LOGIT_C:
            fold = []
            for a, b, c2, d in folds:
                if len(set(b)) < 2:
                    fold.append(ll(d, np.full(len(d), b.mean())))
                else:
                    fold.append(ll(d, LogisticRegression(C=c, max_iter=5000).fit(a, b).predict_proba(c2)[:, 1]))
            scores.append(float(np.mean(fold)))
        best = _pick(np.array(scores), [(c,) for c in LOGIT_C])
        p = LogisticRegression(C=LOGIT_C[best], max_iter=5000).fit(xtr, ytr).predict_proba(xte)[:, 1] if len(set(ytr)) > 1 else np.full(len(test), rate)
        hyper = {"C": LOGIT_C[best]}
    else:
        sc = np.zeros((len(HGB_GRID), EXP_B))
        for i, (d, leaf, l2) in enumerate(HGB_GRID):
            per = []
            for a, b, c2, dd in folds:
                if len(set(b)) < 2:
                    per.append(np.full(EXP_B, ll(dd, np.full(len(dd), b.mean()))))
                    continue
                clf = HistGradientBoostingClassifier(learning_rate=0.05, max_iter=EXP_B, early_stopping=False, max_depth=d, min_samples_leaf=leaf, l2_regularization=l2, random_state=42).fit(a, b)
                per.append(np.array([ll(dd, q[:, 1]) for q in clf.staged_predict_proba(c2)]))
            sc[i] = np.mean(per, axis=0)
        best_val = float(sc.min())
        cand = [(m, d, -leaf, l2, i) for i, (d, leaf, l2) in enumerate(HGB_GRID) for m in range(EXP_B) if sc[i, m] <= best_val + 1e-12]
        m_star, _, _, _, gi = min(cand)
        d, leaf, l2 = HGB_GRID[gi]
        if len(set(ytr)) > 1:
            clf = HistGradientBoostingClassifier(learning_rate=0.05, max_iter=m_star + 1, early_stopping=False, max_depth=d, min_samples_leaf=leaf, l2_regularization=l2, random_state=42).fit(xtr, ytr)
            p = clf.predict_proba(xte)[:, 1]
        else:
            p = np.full(len(test), rate)
        hyper = {"max_depth": d, "min_samples_leaf": leaf, "l2_regularization": l2, "n_iter": m_star + 1}
    return {"preds": {"code": test["code"].tolist(), "forecast_year": test["forecast_year"].tolist(), "y": lab(test).tolist(), "p": np.asarray(p).tolist(), "rate": rate}, "hyper": hyper}


def event_metrics(rows: pd.DataFrame) -> dict[str, Any]:
    """Brier, log-loss, AUC, Brier skill against the training-window rate, calibration slope of the logit (rows: y, p, rate)."""
    from sklearn.metrics import roc_auc_score

    y, p, r = rows["y"].to_numpy(float), np.clip(rows["p"].to_numpy(float), 1e-6, 1 - 1e-6), np.clip(rows["rate"].to_numpy(float), 1e-6, 1 - 1e-6)
    brier, brier0 = float(np.mean((y - p) ** 2)), float(np.mean((y - r) ** 2))
    out: dict[str, Any] = {"n": int(len(y)), "prevalence": float(y.mean()), "brier": brier, "brier_benchmark": brier0, "brier_skill": 1 - brier / brier0,
                           "log_loss": float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))), "log_loss_benchmark": float(-np.mean(y * np.log(r) + (1 - y) * np.log(1 - r)))}
    out["auc"] = float(roc_auc_score(y, p)) if 0 < y.sum() < len(y) else None
    try:
        import statsmodels.api as sm

        lg = np.log(p / (1 - p))
        res = sm.Logit(y, sm.add_constant(lg)).fit(disp=0)
        out["calibration_slope"], out["calibration_intercept"] = float(res.params[1]), float(res.params[0])
    except Exception:  # pragma: no cover
        out["calibration_slope"] = out["calibration_intercept"] = None
    return out


# ---------------------------------------------------------------------------------------------
# Metrics and tests
# ---------------------------------------------------------------------------------------------
def rmse(e: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.asarray(e, float) ** 2)))


def mae(e: np.ndarray) -> float:
    return float(np.mean(np.abs(np.asarray(e, float))))


def dm_hln(d: Sequence[float]) -> dict[str, float]:
    """Diebold-Mariano test (h = 1) with the Harvey-Leybourne-Newbold correction on a loss-differential series (positive favours the model).

    ``DM = mean(d) / sqrt(gamma_0 / n)`` with ``gamma_0`` the ddof-0 variance; the HLN factor ``sqrt((n + 1 - 2h + h(h-1)/n) / n)`` equals
    ``sqrt((n-1)/n)`` for h = 1, which makes the statistic the paired t statistic. Two-sided p-value from Student t with n - 1 df.
    """
    d = np.asarray(d, float)
    n = len(d)
    h = 1
    gamma0 = float(np.mean((d - d.mean()) ** 2))
    if gamma0 <= 0:
        return {"n": n, "mean": float(d.mean()), "dm": float("nan"), "hln": float("nan"), "p": float("nan"), "lag1": float("nan")}
    dm = float(d.mean() / np.sqrt(gamma0 / n))
    hln = dm * float(np.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n))
    p = float(2 * stats.t.sf(abs(hln), n - 1))
    lag1 = float(np.corrcoef(d[:-1], d[1:])[0, 1]) if n > 2 else float("nan")
    return {"n": n, "mean": float(d.mean()), "sd": float(d.std(ddof=1)), "dm": dm, "hln": hln, "p": p, "lag1": lag1, "df": n - 1}


def calibration_fit(y: np.ndarray, yhat: np.ndarray) -> tuple[float, float]:
    """OLS ``y = a + b * yhat``: returns (slope b, intercept a); nan if the forecast is constant."""
    y, x = np.asarray(y, float), np.asarray(yhat, float)
    if np.ptp(x) < 1e-12:
        return float("nan"), float("nan")
    b = float(np.cov(x, y, ddof=0)[0, 1] / np.var(x))
    return b, float(y.mean() - b * x.mean())


def boot_indices(n_clusters: int, b: int = B_BOOT, key: int = 0) -> np.ndarray:
    return power.make_rng(SEED_KEY, PURPOSE_BOOT, key).integers(0, n_clusters, size=(b, n_clusters))


def pct_interval(x: np.ndarray, level: float = 0.95) -> list[float]:
    a = (1 - level) / 2
    return [float(np.quantile(x, a)), float(np.quantile(x, 1 - a))]


def calibration_boot(per_country: np.ndarray, idx: np.ndarray) -> dict[str, Any]:
    """Cluster-bootstrap interval of the calibration line. ``per_country`` columns: n, Sx, Sy, Sxx, Sxy (one row per country)."""
    n, sx, sy, sxx, sxy = (per_country[:, i] for i in range(5))
    tot = [per_country[:, i].sum() for i in range(5)]
    point_b = (tot[0] * tot[4] - tot[1] * tot[2]) / (tot[0] * tot[3] - tot[1] ** 2)
    point_a = (tot[2] - point_b * tot[1]) / tot[0]
    N, SX, SY, SXX, SXY = (per_country[idx, i].sum(axis=1) for i in range(5))
    b = (N * SXY - SX * SY) / (N * SXX - SX**2)
    a = (SY - b * SX) / N
    return {"slope": float(point_b), "slope_ci": pct_interval(b), "intercept": float(point_a), "intercept_ci": pct_interval(a)}


def holm_adjust(p: Sequence[float]) -> list[float]:
    return m1.holm(list(p))


# ---------------------------------------------------------------------------------------------
# Forecast table helpers
# ---------------------------------------------------------------------------------------------
def collect_forecasts(op: pd.DataFrame, results: Sequence[dict[str, Any]], label: Callable[[dict[str, Any]], str]) -> pd.DataFrame:
    rows = []
    for r in results:
        if r.get("status") != "ok" or "preds" not in r or "yhat" not in r["preds"]:
            continue
        p = r["preds"]
        rows.append(pd.DataFrame({"model": label(r), "code": p["code"], "fy": p["forecast_year"], "y": p["y"], "yhat": p["yhat"], "origin": r["origin"]}))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["model", "code", "fy", "y", "yhat", "origin"])


def add_benchmarks(op: pd.DataFrame, origins: Sequence[int]) -> pd.DataFrame:
    """P0 (forecast 0) and P0b (last change repeated) on the evaluation rows of the given origins."""
    te = op[op["complete"] & op["origin"].isin(list(origins))]
    base = pd.DataFrame({"code": te["code"], "fy": te["forecast_year"], "y": te["y"], "origin": te["origin"]})
    p0 = base.assign(model="P0", yhat=0.0)
    p0b = base.assign(model="P0b", yhat=te["dcapb_T"].to_numpy(float))
    return pd.concat([p0, p0b], ignore_index=True)


def error_cube(f: pd.DataFrame, model: str, codes: Sequence[str], years: Sequence[int]) -> np.ndarray:
    """errors ``y - yhat`` as a (country, year) array for one model (nan where absent)."""
    s = f[f["model"] == model]
    cube = pd.DataFrame(np.nan, index=list(codes), columns=list(years))
    for c, fy, e in zip(s["code"], s["fy"], s["y"] - s["yhat"], strict=True):
        cube.loc[c, fy] = e
    return cube.to_numpy(float)


def loss_differential(e_bench: np.ndarray, e_model: np.ndarray, loss: str = "sq") -> np.ndarray:
    """Year-by-year cross-country mean of ``loss(benchmark) - loss(model)`` (positive favours the model)."""
    fn = np.square if loss == "sq" else np.abs
    return np.nanmean(fn(e_bench) - fn(e_model), axis=0)


def accuracy_row(cube: np.ndarray) -> dict[str, float]:
    return {"rmse": rmse(cube[np.isfinite(cube)]), "mae": mae(cube[np.isfinite(cube)]), "n": int(np.isfinite(cube).sum())}


def boot_accuracy(cubes: dict[str, np.ndarray], idx: np.ndarray, bench: str = "P0") -> dict[str, dict[str, Any]]:
    """Cluster-bootstrap 95% intervals of RMSE, MAE, the RMSE ratio to ``bench`` and the MSE skill score, for every model in ``cubes``."""
    out: dict[str, dict[str, Any]] = {}
    sq = {m: np.nansum(c**2, axis=1) for m, c in cubes.items()}
    ab = {m: np.nansum(np.abs(c), axis=1) for m, c in cubes.items()}
    n = {m: np.isfinite(c).sum(axis=1).astype(float) for m, c in cubes.items()}
    mse = {m: sq[m][idx].sum(axis=1) / n[m][idx].sum(axis=1) for m in cubes}
    for m in cubes:
        mae_b = ab[m][idx].sum(axis=1) / n[m][idx].sum(axis=1)
        ratio = np.sqrt(mse[m] / mse[bench])
        out[m] = {"rmse_ci": pct_interval(np.sqrt(mse[m])), "mae_ci": pct_interval(mae_b), "ratio_ci": pct_interval(ratio), "skill_ci": pct_interval(1 - mse[m] / mse[bench])}
    return out


def cluster_mse_difference(c_bench: np.ndarray, c_model: np.ndarray, idx: np.ndarray) -> dict[str, Any]:
    """Cluster-bootstrap interval of ``MSE(bench) - MSE(model)`` and of the relative reduction ``1 - MSE(model)/MSE(bench)``."""
    sb, sm = np.nansum(c_bench**2, axis=1), np.nansum(c_model**2, axis=1)
    nb = np.isfinite(c_bench).sum(axis=1).astype(float)
    mb, mm = sb[idx].sum(axis=1) / nb[idx].sum(axis=1), sm[idx].sum(axis=1) / nb[idx].sum(axis=1)
    pb, pm = sb.sum() / nb.sum(), sm.sum() / nb.sum()
    return {"mse_diff": float(pb - pm), "mse_diff_ci": pct_interval(mb - mm), "rel_reduction": float(1 - pm / pb), "rel_reduction_ci": pct_interval(1 - mm / mb)}


def family_tests(cubes: dict[str, np.ndarray], idx: np.ndarray, drop_years: Sequence[int] = (), years: Sequence[int] = ()) -> list[dict[str, Any]]:
    """The six pre-listed two-sided DM-HLN comparisons (squared loss), raw and Holm-adjusted p, with companion bootstrap intervals."""
    keep = [i for i, y in enumerate(years) if y not in set(drop_years)] if years else slice(None)
    rows = []
    for name, model, bench in HOLM_FAMILY:
        if model not in cubes or bench not in cubes:
            rows.append({"comparison": name, "status": "failed", "p": float("nan")})
            continue
        d = loss_differential(cubes[bench][:, keep], cubes[model][:, keep])
        res = dm_hln(d)
        res.update(cluster_mse_difference(cubes[bench][:, keep], cubes[model][:, keep], idx) if not drop_years else {})
        rows.append({"comparison": name, "model": model, "bench": bench, "status": "ok", **res})
    ok = [r for r in rows if r["status"] == "ok"]
    adj = holm_adjust([1.0 if not np.isfinite(r["p"]) else r["p"] for r in ok]) if ok else []  # a degenerate (zero-variance) differential counts as p = 1
    for r, a in zip(ok, adj, strict=True):
        r["p_holm"] = a
        r["reading"] = reading(r, "persistence" if r["bench"] == "P0" else "baseline")
    return rows


def reading(row: dict[str, Any], kind: str) -> str:
    sig = row["p_holm"] <= 0.05
    if kind == "persistence":
        return "better than persistence" if sig and row["mean"] > 0 else ("worse than persistence" if sig and row["mean"] < 0 else "not distinguishable from persistence")
    return "block improves (adjusted p <= 0.05)" if sig and row["mean"] > 0 else ("block worsens (adjusted p <= 0.05)" if sig and row["mean"] < 0 else "no evidence of improvement")


# ---------------------------------------------------------------------------------------------
# Guards, loading and orchestration
# ---------------------------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_lf(path: Path) -> str:
    """SHA-256 of the content with CRLF/CR normalised to LF (the rule of ``scripts/freeze.py`` for the freeze manifest)."""
    raw = path.read_bytes()
    lf, cr, crlf = bytes([10]), bytes([13]), bytes([13, 10])
    return hashlib.sha256(raw.replace(crlf, lf).replace(cr, lf)).hexdigest()


def frozen_unchanged(manifest: Path = FREEZE_MANIFEST, root: Path = PROJECT_ROOT) -> dict[str, bool]:
    files = json.loads(manifest.read_text(encoding="utf-8"))["files"]
    out = {}
    for rel, meta in files.items():
        path = root / rel
        out[rel] = path.exists() and (sha256_lf(path) == meta["sha256"] or sha256_file(path) == meta["sha256"])
    return out


def load_real() -> tuple[pd.DataFrame, dict[str, Any]]:
    """Origin panel of the real data. Refuses without the tag; checks that the 1995-2021 part reproduces the confirmatory extract."""
    m1.require_preregistration_tag()
    import panel as panel_module  # noqa: PLC0415

    extract, digest = m1.load_real_panel()
    inputs = panel_module.load_inputs()
    built = panel_module.assemble_gold_panel(inputs, start=1995, end=2023)
    gold = built.panel
    key = ["eurostat_code", "year"]
    ref = extract.sort_values(key).set_index(key)
    cmp = gold.set_index(key).loc[ref.index]
    for col in ("capb", "olddep1_lag", "outgap_lag", "debt_gdp_lag", "ig_diff_lag"):
        a, b = cmp[col].to_numpy(float), ref[col].to_numpy(float)
        if not np.allclose(a, b, equal_nan=True, atol=1e-9):
            raise ValueError(f"the 2023 build differs from the confirmatory extract in {col}")
    cal = load_calendar()
    op = build_origin_panel(gold, cal)
    used = op[op["complete"] & (op["forecast_year"] <= 2021)]
    in_ext = used.merge(ref.reset_index()[key].rename(columns={"eurostat_code": "code", "year": "forecast_year"}), on=["code", "forecast_year"], how="left", indicator=True)
    if not (in_ext["_merge"] == "both").all():
        raise ValueError("a used row with forecast year <= 2021 is not in the confirmatory extract")
    meta = {"extract_sha256": digest, "gold_rows_2023_build": int(len(gold)), "last_observed_ameco_year": int(built.last_observed_year), "schedule_agreement": schedule_agreement(cal),
            "code_sha256": sha256_file(Path(__file__)), "spec_sha256": sha256_file(SPEC_PATH)}
    return op, meta


def jobs_for(stage: str, op: pd.DataFrame) -> list[dict[str, Any]]:
    codes = sorted(op["code"].unique())
    jobs: list[dict[str, Any]] = []
    if stage in ("P", "H"):
        origins = ORIGINS_P if stage == "P" else ORIGINS_H
        for o in origins:
            for model in ("P1a", "P1b"):
                for s in ("B0", "B1", "B2", "B2p", "B2d"):
                    extras = s == "B2" and stage == "P"
                    jobs.append({"kind": "main", "model": model, "set": s, "scheme": "CD", "loco": None, "origin": o, "extras": extras, "ale": extras and o == ORIGINS_P[-1]})
                for s in ("B1", "B2"):
                    jobs.append({"kind": "main", "model": model, "set": s, "scheme": "POOL", "loco": None, "origin": o})
            for s in ("B1", "B2"):
                jobs.append({"kind": "main", "model": "P1c", "set": s, "scheme": "CD", "loco": None, "origin": o})
    elif stage == "oracle":
        for o in ORIGINS_P + ORIGINS_H:
            for model in ("P1a", "P1b"):
                for s in ("B2o", "B2f"):
                    jobs.append({"kind": "main", "model": model, "set": s, "scheme": "CD", "loco": None, "origin": o})
    elif stage == "loco":
        for c in codes:
            for o in ORIGINS_P:
                for model in ("P1a", "P1b"):
                    for s in ("B1", "B2"):
                        jobs.append({"kind": "main", "model": model, "set": s, "scheme": "CD", "loco": c, "origin": o})
    elif stage == "event":
        for o in ORIGINS_P + ORIGINS_H:
            for model in ("P1a", "P1b"):
                for s in ("B1", "B2"):
                    jobs.append({"kind": "event", "model": model, "set": s, "scheme": "CD", "loco": None, "origin": o})
    else:
        raise ValueError(stage)
    return jobs


def run_stage(stage: str, op: pd.DataFrame, n_jobs: int = 20) -> list[dict[str, Any]]:
    from joblib import Parallel, delayed

    jobs = jobs_for(stage, op)
    todo = [j for j in jobs if not (CACHE_DIR / f"{job_name(j)}.json").exists()]
    print(f"[{stage}] {len(jobs)} jobs, {len(todo)} to run", flush=True)
    t0 = time.time()
    if todo:
        Parallel(n_jobs=n_jobs, verbose=0, batch_size=1)(delayed(run_job)(j, op) for j in todo)
    print(f"[{stage}] done in {time.time() - t0:.0f}s", flush=True)
    return [run_job(j, op) for j in jobs]


def model_label(r: dict[str, Any]) -> str:
    base = f"{r['model']}-{r['set']}"
    if r.get("scheme") == "POOL":
        base += "-POOL"
    if r.get("loco"):
        base += " (LOCO)"
    return base


if __name__ == "__main__":  # the report assembly lives in predictive_report.py (same package, imports this module)
    import predictive_report

    sys.exit(predictive_report.main())
