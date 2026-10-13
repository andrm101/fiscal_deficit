"""S4: descriptive CAPB-revision / measurement-error appendix (GitHub issue 30; specification ``docs/s4_spec.md``, dated 2026-10-13).

Question: how far is the first-outturn CAPB (AMECO item ``UBLGBP``, pp of potential GDP) from the final value used in the confirmatory
analysis (Spring 2026), and how does that distance compare with the 0.5 pp smallest effect size of interest and with the size of the
headline beta_S? Trigger T3 passed, but a real-time panel covers 2015-2021 only (189 of 715 country-years; 51 elections), so there is no
election-effect replication; this module is the measurement-error appendix that replaces it.

Descriptive only. No election effect is estimated, no correction is applied to the pre-registered headline, and every statement is an
association. The first outturn of year y is the earliest archived vintage in which y is no longer a forecast (last two years of a Spring
vintage, last three of an Autumn or Winter vintage; AMECO has no forecast flag), computed by the frozen
``ameco_vintages.first_release_table`` (imported, not copied). The only election quantity used is the frozen exposure ``W_S`` (exposed =
``W_S > 0``), read through the tag-guarded ``m1.load_real_panel`` to stratify the revisions; no outcome is regressed on it.

Intervals: country-cluster (27 clusters) percentile bootstrap, B = 9999, seed 42, plus CR1 t(G - 1) intervals for the mean revision and the
exposure contrast. Every number of the markdown report comes from the results dictionary computed here.

Run: ``python src/evaluate/revisions.py`` (writes ``reports/results/s4_revisions.{md,json}`` and ``reports/figures/s4_revisions.png``).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import textwrap
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import scipy
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[2]
for _sub in ("normalize", "evaluate", "models/py", "features"):
    sys.path.insert(0, str(PROJECT_ROOT / "src" / _sub))
import ameco_vintages as av  # noqa: E402  (frozen: import only)
import figures as fg  # noqa: E402  (style helpers and the clustered mean interval)

RESULTS_DIR = PROJECT_ROOT / "reports" / "results"
FIGURES_DIR = PROJECT_ROOT / "reports" / "figures"
SPEC_PATH = PROJECT_ROOT / "docs" / "s4_spec.md"
HEADLINE_JSON = RESULTS_DIR / "m1_confirmatory.json"
OUT_STEM = "s4_revisions"

PRIMARY_WINDOW = (2014, 2021)  # confirmatory-sample years with a first outturn in the archive (Spring 2015 to Spring 2022)
EXTENDED_WINDOW = (2014, 2024)  # last year with a first outturn in the archive (Spring 2025); 2022-2024 are outside the confirmatory sample
LAST_CONFIRMATORY_YEAR = 2021
SESOI_PP = 0.5  # fallback only; the value used comes from m1_confirmatory.json (``sesoi_pp``)
N_BOOT = 9999
SEED = 42
LEVEL = 0.95
QUANTILE_LEVELS = (0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99)
HIST_BIN_PP = 0.25  # histogram bin width in pp
LABEL_ABS_REVISION_PP = 2.4  # points in the scatter with |revision| above this are labelled (the eight largest)
# Gate 5 reference values: ``table`` = the 3-decimal table of reports/gate5_realtime_feasibility.md section 6 ("First outturn" row);
# ``quoted`` = the rounded figures of the issue text and docs/decision_log.md (2026-10-10), with their number of decimals.
GATE5_REFERENCE = {
    "mean_abs_revision": {"table": 0.639, "quoted": 0.64, "quoted_decimals": 2},
    "sd_revision": {"table": 0.975, "quoted": 0.98, "quoted_decimals": 2},
    "share_sign_change_level": {"table": 0.097, "quoted": 0.097, "quoted_decimals": 3},
    "corr_first_final": {"table": 0.933, "quoted": 0.93, "quoted_decimals": 2},
}
BOOTSTRAPPED = (
    "mean_revision", "mean_abs_revision", "sd_revision", "median_revision", "median_abs_revision", "share_abs_gt_sesoi",
    "share_sign_change_level", "share_sign_change_delta", "corr_first_final", "slope_final_on_first", "intercept_final_on_first",
    "slope_first_on_final", "reliability", "corr_rev_first", "corr_rev_final",
)


# ---------------------------------------------------------------------------------------------
# Revision table
# ---------------------------------------------------------------------------------------------
def sign_change(first: Any, final: Any) -> np.ndarray:
    """True where the two values have opposite signs. Exact zeros and NaN never count as a sign change."""
    return (np.sign(np.asarray(first, float)) * np.sign(np.asarray(final, float))) < 0


def revision_table(long: pd.DataFrame, specs: list[av.VintageSpec], window: tuple[int, int] = PRIMARY_WINDOW) -> pd.DataFrame:
    """Country-years in ``window`` with a first outturn and a final value.

    Columns: ``eurostat_code, year, first_vintage, first_order, first, final, revision`` (final minus first, pp of potential GDP),
    ``d_first`` (CAPB(y) - CAPB(y-1) as read in the first-outturn vintage), ``d_final`` (the same change read in the final vintage; both NaN
    where year y-1 is missing in either vintage). The first-outturn rule is that of ``ameco_vintages.first_release_table``.
    """
    base = av.first_release_table(long, specs, window)
    base = base.dropna(subset=["first_outturn_value", "final_value"]).copy()
    order_of = {s.label: s.order for s in specs}
    wide = av.capb_wide(long)

    def prev_value(code: str, year: int, order: int) -> float:
        key = (code, year - 1)
        if key in wide.index and order in wide.columns:
            return float(wide.at[key, order])
        return float("nan")

    base["first_order"] = base["first_outturn_vintage"].map(order_of).astype(int)
    first_prev = [prev_value(c, y, o) for c, y, o in zip(base["eurostat_code"], base["year"], base["first_order"], strict=True)]
    final_prev = [prev_value(c, y, av.FINAL_ORDER) for c, y in zip(base["eurostat_code"], base["year"], strict=True)]
    out = pd.DataFrame(
        {
            "eurostat_code": base["eurostat_code"].to_numpy(),
            "year": base["year"].astype(int).to_numpy(),
            "first_vintage": base["first_outturn_vintage"].to_numpy(),
            "first_order": base["first_order"].to_numpy(),
            "first": base["first_outturn_value"].to_numpy(float),
            "final": base["final_value"].to_numpy(float),
        }
    )
    out["revision"] = out["final"] - out["first"]
    out["d_first"] = out["first"] - np.asarray(first_prev, float)
    out["d_final"] = out["final"] - np.asarray(final_prev, float)
    return out.sort_values(["eurostat_code", "year"]).reset_index(drop=True)


# ---------------------------------------------------------------------------------------------
# Core statistics
# ---------------------------------------------------------------------------------------------
def _cov(a: np.ndarray, b: np.ndarray) -> float:
    return float(((a - a.mean()) * (b - b.mean())).sum() / (len(a) - 1)) if len(a) > 1 else float("nan")


def _ratio(num: float, den: float) -> float:
    return float(num / den) if den and np.isfinite(den) and den > 0 else float("nan")


def core_stats(first: Any, final: Any, d_first: Any = None, d_final: Any = None, sesoi: float = SESOI_PP) -> dict[str, float]:
    """The statistics of the S4 specification on arrays of first outturn and final values (and their one-year changes).

    ``revision = final - first``. ``reliability = var(final) / var(first)``; ``slope_final_on_first`` and ``slope_first_on_final`` are OLS
    slopes; ``corr_rev_first`` and ``corr_rev_final`` are correlations of the revision with each value. The sign-of-change share uses
    only pairs where both one-year changes are finite. All variances use ``ddof = 1``.
    """
    x, y = np.asarray(first, float), np.asarray(final, float)
    n = int(x.size)
    nan = float("nan")
    rev = y - x
    out: dict[str, float] = {"n": n}
    out["mean_revision"] = float(rev.mean()) if n else nan
    out["mean_abs_revision"] = float(np.abs(rev).mean()) if n else nan
    out["sd_revision"] = float(rev.std(ddof=1)) if n > 1 else nan
    out["median_revision"] = float(np.median(rev)) if n else nan
    out["median_abs_revision"] = float(np.median(np.abs(rev))) if n else nan
    out["share_abs_gt_sesoi"] = float((np.abs(rev) > sesoi).mean()) if n else nan
    out["share_sign_change_level"] = float(sign_change(x, y).mean()) if n else nan
    if d_first is None or d_final is None:
        out["n_delta"], out["share_sign_change_delta"] = 0, nan
    else:
        df, dl = np.asarray(d_first, float), np.asarray(d_final, float)
        ok = np.isfinite(df) & np.isfinite(dl)
        out["n_delta"] = int(ok.sum())
        out["share_sign_change_delta"] = float(sign_change(df[ok], dl[ok]).mean()) if ok.any() else nan
    var_x, var_y = (float(x.var(ddof=1)), float(y.var(ddof=1))) if n > 1 else (nan, nan)
    cov_xy = _cov(x, y) if n > 1 else nan
    var_r = float(rev.var(ddof=1)) if n > 1 else nan
    out["sd_first"], out["sd_final"] = float(np.sqrt(var_x)) if n > 1 else nan, float(np.sqrt(var_y)) if n > 1 else nan
    out["corr_first_final"] = _ratio(cov_xy, np.sqrt(var_x * var_y)) if n > 1 else nan
    out["slope_final_on_first"] = _ratio(cov_xy, var_x) if n > 1 else nan
    out["intercept_final_on_first"] = float(y.mean() - out["slope_final_on_first"] * x.mean()) if n > 1 else nan
    out["slope_first_on_final"] = _ratio(cov_xy, var_y) if n > 1 else nan
    out["reliability"] = _ratio(var_y, var_x) if n > 1 else nan
    out["corr_rev_first"] = _ratio(_cov(rev, x), np.sqrt(var_r * var_x)) if n > 1 else nan
    out["corr_rev_final"] = _ratio(_cov(rev, y), np.sqrt(var_r * var_y)) if n > 1 else nan
    return out


def table_stats(table: pd.DataFrame, sesoi: float = SESOI_PP) -> dict[str, float]:
    """:func:`core_stats` of a revision table."""
    return core_stats(table["first"], table["final"], table["d_first"], table["d_final"], sesoi)


def revision_quantiles(table: pd.DataFrame, levels: Sequence[float] = QUANTILE_LEVELS) -> dict[str, dict[str, float]]:
    """Quantiles (linear interpolation) of the revision and of the absolute revision, keyed by the level as text."""
    rev = table["revision"].to_numpy(float)
    return {
        "revision": {f"{q:g}": float(np.quantile(rev, q)) for q in levels},
        "abs_revision": {f"{q:g}": float(np.quantile(np.abs(rev), q)) for q in levels},
    }


def group_summary(table: pd.DataFrame, by: str, sesoi: float = SESOI_PP) -> pd.DataFrame:
    """Revision size per group: n, mean, SD, mean absolute, median absolute, share above the SESOI, level sign-change share."""
    rows = []
    for key, grp in table.groupby(by, sort=True):
        rev = grp["revision"].to_numpy(float)
        rows.append(
            {
                by: key,
                "n": int(len(grp)),
                "mean_revision": float(rev.mean()),
                "sd_revision": float(rev.std(ddof=1)) if len(grp) > 1 else float("nan"),
                "mean_abs_revision": float(np.abs(rev).mean()),
                "median_abs_revision": float(np.median(np.abs(rev))),
                "share_abs_gt_sesoi": float((np.abs(rev) > sesoi).mean()),
                "share_sign_change_level": float(sign_change(grp["first"], grp["final"]).mean()),
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------------------------
# Uncertainty
# ---------------------------------------------------------------------------------------------
def cluster_draws(clusters: Any, stat_fn: Callable[[np.ndarray], dict[str, float]], n_boot: int = N_BOOT, seed: int = SEED) -> pd.DataFrame:
    """Country-cluster (pairs) bootstrap: resample clusters with replacement, evaluate ``stat_fn(row_index)`` on each draw.

    Returns a DataFrame with one row per draw. ``stat_fn`` receives the integer positions of the resampled rows.
    """
    _, inverse = np.unique(np.asarray(clusters), return_inverse=True)
    groups = [np.flatnonzero(inverse == g) for g in range(int(inverse.max()) + 1)]
    rng = np.random.default_rng(seed)
    records = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(groups), len(groups))
        records.append(stat_fn(np.concatenate([groups[g] for g in pick])))
    return pd.DataFrame.from_records(records)


def percentile_interval(draws: pd.DataFrame, level: float = LEVEL) -> dict[str, list[float | None]]:
    """Percentile interval per column of ``draws``; NaN draws are dropped (an all-NaN column gives ``[None, None]``)."""
    out: dict[str, list[float | None]] = {}
    for col in draws.columns:
        values = draws[col].to_numpy(float)
        values = values[np.isfinite(values)]
        if values.size == 0:
            out[col] = [None, None]
        else:
            lo, hi = np.percentile(values, [100 * (1 - level) / 2, 100 * (1 + level) / 2])
            out[col] = [float(lo), float(hi)]
    return out


def bootstrap_core(table: pd.DataFrame, sesoi: float = SESOI_PP, n_boot: int = N_BOOT, seed: int = SEED) -> dict[str, list[float | None]]:
    """Country-cluster bootstrap intervals of the :data:`BOOTSTRAPPED` statistics of a revision table."""
    arrays = {c: table[c].to_numpy(float) for c in ("first", "final", "d_first", "d_final")}

    def one(idx: np.ndarray) -> dict[str, float]:
        stat = core_stats(arrays["first"][idx], arrays["final"][idx], arrays["d_first"][idx], arrays["d_final"][idx], sesoi)
        return {k: stat[k] for k in BOOTSTRAPPED}

    return percentile_interval(cluster_draws(table["eurostat_code"].to_numpy(), one, n_boot, seed))


def cr1_difference(y: Any, d: Any, clusters: Any, level: float = LEVEL) -> dict[str, float]:
    """OLS of ``y`` on a constant and a 0/1 indicator ``d``; CR1 cluster-robust t(G - 1) interval for the indicator.

    ``CR1 = G / (G - 1) * (n - 1) / (n - 2)`` times the sandwich. Returns the difference (``d = 1`` minus ``d = 0`` mean),
    its standard error, interval, ``n`` and ``n_clusters``.
    """
    y, d = np.asarray(y, float), np.asarray(d, float)
    n = int(y.size)
    _, inverse = np.unique(np.asarray(clusters), return_inverse=True)
    g_count = int(inverse.max()) + 1
    nan = float("nan")
    if n < 3 or g_count < 2 or d.min() == d.max():
        return {"difference": nan, "se": nan, "ci_lo": nan, "ci_hi": nan, "n": n, "n_clusters": g_count}
    design = np.column_stack([np.ones(n), d])
    bread = np.linalg.inv(design.T @ design)
    beta = bread @ design.T @ y
    resid = y - design @ beta
    scores = np.zeros((g_count, 2))
    np.add.at(scores, inverse, design * resid[:, None])
    meat = scores.T @ scores
    scale = g_count / (g_count - 1) * (n - 1) / (n - 2)
    se = float(np.sqrt(scale * (bread @ meat @ bread)[1, 1]))
    half = float(stats.t.ppf(0.5 + level / 2, g_count - 1)) * se
    return {"difference": float(beta[1]), "se": se, "ci_lo": float(beta[1] - half), "ci_hi": float(beta[1] + half), "n": n, "n_clusters": g_count}


# ---------------------------------------------------------------------------------------------
# Exposure stratification, signal scales
# ---------------------------------------------------------------------------------------------
def exposure_contrast(table: pd.DataFrame, n_boot: int = N_BOOT, seed: int = SEED) -> dict[str, Any]:
    """Revisions by exposure year (``exposed`` column: ``W_S > 0``) with country-clustered intervals. Descriptive, unadjusted.

    Per stratum: n, countries, mean revision with a CR1 t(G - 1) interval, mean absolute revision. Contrast: exposed minus unexposed
    mean revision (and mean absolute revision) with a CR1 interval and a country-cluster bootstrap percentile interval.
    """
    flag = table["exposed"].to_numpy(bool)
    rev, absrev, codes = table["revision"].to_numpy(float), np.abs(table["revision"].to_numpy(float)), table["eurostat_code"].to_numpy()
    strata = {}
    for name, mask in (("exposed", flag), ("unexposed", ~flag)):
        sub = table[mask]
        strata[name] = {
            "n": int(mask.sum()),
            "n_countries": int(sub["eurostat_code"].nunique()),
            "mean_revision": fg.clustered_mean_ci(sub["revision"], sub["eurostat_code"]),
            "mean_abs_revision": fg.clustered_mean_ci(np.abs(sub["revision"]), sub["eurostat_code"]),
            "sd_revision": float(sub["revision"].std(ddof=1)) if len(sub) > 1 else float("nan"),
            "share_sign_change_level": float(sign_change(sub["first"], sub["final"]).mean()) if len(sub) else float("nan"),
        }

    def diff(idx: np.ndarray) -> dict[str, float]:
        f = flag[idx]
        if f.all() or not f.any():
            return {"difference_mean_revision": float("nan"), "difference_mean_abs_revision": float("nan")}
        return {
            "difference_mean_revision": float(rev[idx][f].mean() - rev[idx][~f].mean()),
            "difference_mean_abs_revision": float(absrev[idx][f].mean() - absrev[idx][~f].mean()),
        }

    draws = cluster_draws(codes, diff, n_boot, seed)
    bootstrap = percentile_interval(draws)
    return {
        "strata": strata,
        "difference_mean_revision": {"cr1": cr1_difference(rev, flag.astype(float), codes), "bootstrap_ci": bootstrap["difference_mean_revision"]},
        "difference_mean_abs_revision": {"cr1": cr1_difference(absrev, flag.astype(float), codes), "bootstrap_ci": bootstrap["difference_mean_abs_revision"]},
        "n_bootstrap_draws_valid": int(draws["difference_mean_revision"].notna().sum()),
    }


def twoway_demean(frame: pd.DataFrame, column: str, tol: float = 1e-10, max_iter: int = 2000) -> np.ndarray:
    """Residual of ``column`` after removing country and year means (alternating projections; exact for balanced panels)."""
    x = frame[column].to_numpy(float).copy()
    country, year = frame["eurostat_code"].to_numpy(), frame["year"].to_numpy()
    for _ in range(max_iter):
        previous = x.copy()
        x = x - pd.Series(x).groupby(country).transform("mean").to_numpy()
        x = x - pd.Series(x).groupby(year).transform("mean").to_numpy()
        if np.max(np.abs(x - previous)) < tol:
            break
    return x


def signal_scales(table: pd.DataFrame, panel: pd.DataFrame, headline: dict, stat: dict[str, float]) -> dict[str, float]:
    """Revision size against the scale of the signal: the headline beta_S and the dispersion of CAPB.

    ``panel`` is the confirmatory extract (columns ``eurostat_code, year, capb``); ``headline`` is the parsed ``m1_confirmatory.json``;
    ``stat`` the :func:`table_stats` of the revision table. All ratios are plain quotients (descriptive, no inference).
    """
    beta = headline["targets"]["beta_S"]
    beta_abs = abs(float(beta["estimate"]))
    capb = panel.dropna(subset=["capb"]).reset_index(drop=True)
    within = capb["capb"] - capb.groupby("eurostat_code")["capb"].transform("mean")
    within_sd = float(within.std(ddof=1))
    twoway_sd = float(np.std(twoway_demean(capb, "capb"), ddof=1))
    pooled_sd = float(capb["capb"].std(ddof=1))
    sample_sd = float(table["final"].std(ddof=1))
    sample_within = table["final"] - table.groupby("eurostat_code")["final"].transform("mean")
    sd_rev, abs_rev = stat["sd_revision"], stat["mean_abs_revision"]
    return {
        "beta_S": float(beta["estimate"]),
        "beta_S_ci_lo": float(beta["ci_lo"]),
        "beta_S_ci_hi": float(beta["ci_hi"]),
        "sd_final_revision_sample": sample_sd,
        "sd_within_final_revision_sample": float(sample_within.std(ddof=1)),
        "sd_capb_confirmatory": pooled_sd,
        "sd_capb_within_country_confirmatory": within_sd,
        "sd_capb_twoway_confirmatory": twoway_sd,
        "n_confirmatory": int(len(capb)),
        "sd_revision_over_abs_beta_S": _ratio(sd_rev, beta_abs),
        "mean_abs_revision_over_abs_beta_S": _ratio(abs_rev, beta_abs),
        "sd_revision_over_sd_final_revision_sample": _ratio(sd_rev, sample_sd),
        "sd_revision_over_sd_capb_confirmatory": _ratio(sd_rev, pooled_sd),
        "sd_revision_over_sd_within_confirmatory": _ratio(sd_rev, within_sd),
        "sd_revision_over_sd_twoway_confirmatory": _ratio(sd_rev, twoway_sd),
        "abs_beta_S_over_sd_revision": _ratio(beta_abs, sd_rev),
    }


def gate5_comparison(stat: dict[str, float]) -> list[dict[str, Any]]:
    """S4 statistics against the Gate 5 table (3 decimals) and the rounded figures quoted in the issue and decision log (no agreement is forced)."""
    rows = []
    for key, ref in GATE5_REFERENCE.items():
        s4 = stat[key]
        rows.append(
            {
                "statistic": key,
                "gate5_table": ref["table"],
                "gate5_quoted": ref["quoted"],
                "s4": s4,
                "agrees_with_table": bool(round(s4, 3) == ref["table"]),
                "agrees_with_quoted": bool(round(s4, ref["quoted_decimals"]) == ref["quoted"]),
            }
        )
    return rows


# ---------------------------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    """SHA-256 of a file (binary)."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_long(path: Path = av.INTERIM_CSV) -> pd.DataFrame:
    """The vintage long table written by ``ameco_vintages.py`` (26 archived vintages plus the pinned Spring 2026)."""
    long = pd.read_csv(path)
    long["printed_date"] = pd.to_datetime(long["printed_date"])
    orders = set(long["vintage_order"].unique())
    if orders != set(range(1, 27)) | {av.FINAL_ORDER}:
        raise ValueError(f"unexpected vintage orders in {path}: {sorted(orders)}")
    return long


def attach_exposure(table: pd.DataFrame, panel: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    """Add ``W_S`` and ``exposed`` (``W_S > 0``) from the confirmatory extract; check that the panel CAPB equals the final value.

    Rows without a panel match keep ``exposed`` NaN (object column); the check dictionary reports the matched count and the largest
    absolute difference between the panel CAPB and the final vintage value.
    """
    merged = table.merge(panel[["eurostat_code", "year", "capb", "W_S"]], on=["eurostat_code", "year"], how="left")
    matched = merged["capb"].notna()
    check = {
        "n_rows": int(len(merged)),
        "n_matched_to_panel": int(matched.sum()),
        "max_abs_panel_minus_final": float((merged.loc[matched, "capb"] - merged.loc[matched, "final"]).abs().max()) if matched.any() else float("nan"),
    }
    merged["exposed"] = (merged["W_S"] > 0).where(merged["W_S"].notna())
    return merged.drop(columns=["capb"]), check


# ---------------------------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------------------------
def top_revisions(table: pd.DataFrame, n: int = 8) -> list[dict[str, Any]]:
    """The ``n`` largest absolute revisions."""
    top = table.reindex(table["revision"].abs().sort_values(ascending=False).index).head(n)
    return [
        {"eurostat_code": r.eurostat_code, "year": int(r.year), "first": float(r.first), "final": float(r.final), "revision": float(r.revision)}
        for r in top.itertuples(index=False)
    ]


def sample_block(table: pd.DataFrame, sesoi: float, n_boot: int, seed: int) -> dict[str, Any]:
    """Statistics, bootstrap intervals, CR1 interval of the mean revision and quantiles of one revision sample."""
    return {
        "n": int(len(table)),
        "n_countries": int(table["eurostat_code"].nunique()),
        "years": [int(table["year"].min()), int(table["year"].max())],
        "first_vintage_counts": {k: int(v) for k, v in table["first_vintage"].value_counts().sort_index().items()},
        "stats": table_stats(table, sesoi),
        "bootstrap_ci": bootstrap_core(table, sesoi, n_boot, seed),
        "mean_revision_cr1": fg.clustered_mean_ci(table["revision"], table["eurostat_code"]),
        "quantiles": revision_quantiles(table),
        "top_revisions": top_revisions(table),
    }


def compute(long: pd.DataFrame, panel: pd.DataFrame, headline: dict, n_boot: int = N_BOOT, seed: int = SEED) -> dict[str, Any]:
    """The full S4 results dictionary (primary 2014-2021 sample, 2014-2024 extension, strata, signal scales, Gate 5 comparison)."""
    specs = av.vintage_specs()
    sesoi = fg.sesoi_of(headline)
    raw = revision_table(long, specs, EXTENDED_WINDOW)
    extended, _ = attach_exposure(raw, panel)
    primary, primary_check = attach_exposure(raw[raw["year"].between(*PRIMARY_WINDOW)].reset_index(drop=True), panel)
    block = sample_block(primary, sesoi, n_boot, seed)
    by_year = group_summary(extended, "year", sesoi)
    exposed_count = primary.groupby("year")["exposed"].apply(lambda s: int(s.astype(bool).sum()))
    by_year["n_exposed"] = by_year["year"].map(exposed_count)
    by_year["in_confirmatory_sample"] = by_year["year"] <= LAST_CONFIRMATORY_YEAR
    return {
        "meta": {
            "spec": "docs/s4_spec.md",
            "spec_sha256": sha256_file(SPEC_PATH),
            "sesoi_pp": sesoi,
            "n_boot": n_boot,
            "seed": seed,
            "level": LEVEL,
            "primary_window": list(PRIMARY_WINDOW),
            "extended_window": list(EXTENDED_WINDOW),
            "interim_csv_sha256": sha256_file(av.INTERIM_CSV) if Path(av.INTERIM_CSV).exists() else None,
            "forecast_years_by_season": av.FORECAST_YEARS_BY_SEASON,
            "final_vintage": av.FINAL_LABEL,
            "versions": {"numpy": np.__version__, "pandas": pd.__version__, "scipy": scipy.__version__},
        },
        "checks": primary_check,
        "primary": block,
        "extended": sample_block(extended, sesoi, n_boot, seed),
        "by_year": by_year.to_dict(orient="records"),
        "by_country": group_summary(primary, "eurostat_code", sesoi).sort_values("mean_abs_revision", ascending=False).to_dict(orient="records"),
        "exposure": exposure_contrast(primary, n_boot, seed),
        "signal": signal_scales(primary, panel, headline, block["stats"]),
        "gate5": gate5_comparison(block["stats"]),
    }


# ---------------------------------------------------------------------------------------------
# Figure
# ---------------------------------------------------------------------------------------------
def figure_revisions(table: pd.DataFrame, results: dict[str, Any], path: Path) -> Path:
    """Panel A: final against first outturn with the 45-degree line and the +-SESOI band. Panel B: histogram of the revisions."""
    sesoi = results["meta"]["sesoi_pp"]
    stat = results["primary"]["stats"]
    fig = fg._figure(8.6, 4.9)
    ax_a = fig.add_axes([0.075, 0.19, 0.40, 0.58])
    ax_b = fig.add_axes([0.585, 0.19, 0.395, 0.58])

    lo = float(min(table["first"].min(), table["final"].min())) - 0.5
    hi = float(max(table["first"].max(), table["final"].max())) + 0.5
    grid = np.array([lo, hi])
    ax_a.fill_between(grid, grid - sesoi, grid + sesoi, color=fg.SKY, alpha=0.22, lw=0, zorder=0)
    ax_a.plot(grid, grid, color=fg.MUTED, lw=1.0, ls="--", zorder=1)
    exposed = table["exposed"].astype(bool).to_numpy() if "exposed" in table and table["exposed"].notna().all() else np.zeros(len(table), bool)
    ax_a.scatter(table.loc[~exposed, "first"], table.loc[~exposed, "final"], s=16, color=fg.BLUE, alpha=0.65, lw=0, zorder=3, label="Not an exposure year (W_S = 0)")
    if exposed.any():
        ax_a.scatter(table.loc[exposed, "first"], table.loc[exposed, "final"], s=18, color=fg.VERMILLION, alpha=0.75, lw=0, marker="D", zorder=4, label="Exposure year (W_S > 0)")
    placed: list[tuple[float, float]] = []
    for rec in table[table["revision"].abs() > LABEL_ABS_REVISION_PP].sort_values("first").itertuples(index=False):
        crowded = any(abs(rec.first - px) < 1.2 and abs(rec.final - py) < 0.8 for px, py in placed)
        above = (rec.revision > 0) != crowded
        left = rec.first < 0
        ax_a.annotate(f"{rec.eurostat_code} {rec.year}", (rec.first, rec.final), xytext=(-4 if left else 4, 3 if above else -9), textcoords="offset points",
                      ha="right" if left else "left", fontsize=6.5, color=fg.INK)
        placed.append((rec.first, rec.final))
    ax_a.set_xlim(lo, hi)
    ax_a.set_ylim(lo, hi)
    ax_a.set_aspect("equal", adjustable="box")
    ax_a.set_xlabel("First-outturn CAPB (vintage Spring y+1), pp of potential GDP", fontsize=8, color=fg.INK)
    ax_a.set_ylabel("Final CAPB (AMECO Spring 2026), pp of potential GDP", fontsize=8, color=fg.INK)
    ax_a.set_title("A. Final against first outturn", loc="left", fontsize=9, color=fg.INK)
    ax_a.grid(True, color=fg.GRID, lw=0.5, zorder=0)
    ax_a.set_axisbelow(True)
    fg._clean_axes(ax_a)
    handles = [
        fg.Line2D([], [], color=fg.MUTED, ls="--", lw=1.0, label="45-degree line (no revision)"),
        fg.Patch(facecolor=fg.SKY, alpha=0.4, label=f"±{sesoi:g} pp band (SESOI)"),
        fg.Line2D([], [], color=fg.BLUE, marker="o", ms=4.5, lw=0, label="Not an exposure year (W_S = 0)"),
    ]
    if exposed.any():
        handles.append(fg.Line2D([], [], color=fg.VERMILLION, marker="D", ms=4.5, lw=0, label="Exposure year (W_S > 0)"))
    ax_a.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=2, fontsize=7, frameon=False, handlelength=1.5, columnspacing=1.2)

    rev = table["revision"].to_numpy(float)
    edge_lo = np.floor(rev.min() / HIST_BIN_PP) * HIST_BIN_PP
    edge_hi = np.ceil(rev.max() / HIST_BIN_PP) * HIST_BIN_PP + HIST_BIN_PP
    bins = np.arange(edge_lo, edge_hi + 1e-9, HIST_BIN_PP)
    ax_b.axvspan(-sesoi, sesoi, color=fg.SKY, alpha=0.22, lw=0, zorder=0)
    ax_b.hist(rev, bins=bins, color=fg.BLUE, alpha=0.8, edgecolor="white", lw=0.4, zorder=2)
    ax_b.axvline(0.0, color=fg.MUTED, lw=1.0, ls="--", zorder=3)
    ax_b.axvline(-sesoi, color=fg.ACCENT, lw=1.0, ls=":", zorder=3)
    ax_b.axvline(sesoi, color=fg.ACCENT, lw=1.0, ls=":", zorder=3)
    ax_b.axvline(stat["mean_revision"], color=fg.ORANGE, lw=1.4, zorder=3)
    ax_b.set_xlabel("Revision = final minus first outturn, pp of potential GDP", fontsize=8, color=fg.INK)
    ax_b.set_ylabel(f"Country-years per {HIST_BIN_PP:g} pp bin (count)", fontsize=8, color=fg.INK)
    ax_b.set_title("B. Distribution of the revisions", loc="left", fontsize=9, color=fg.INK)
    ax_b.yaxis.grid(True, color=fg.GRID, lw=0.5, zorder=0)
    ax_b.set_axisbelow(True)
    fg._clean_axes(ax_b)
    note = (
        f"N = {int(stat['n'])} country-years\n"
        f"mean = {stat['mean_revision']:+.2f} pp, SD = {stat['sd_revision']:.2f} pp\n"
        f"mean |rev| = {stat['mean_abs_revision']:.2f} pp\n"
        f"|rev| > {sesoi:g} pp: {100 * stat['share_abs_gt_sesoi']:.0f}%"
    )
    ax_b.text(0.98, 0.97, note, transform=ax_b.transAxes, ha="right", va="top", fontsize=7.5, color=fg.INK, linespacing=1.35)
    handles_b = [
        fg.Patch(facecolor=fg.SKY, alpha=0.4, label=f"±{sesoi:g} pp band (SESOI)"),
        fg.Line2D([], [], color=fg.ACCENT, ls=":", lw=1.0, label=f"±{sesoi:g} pp limits"),
        fg.Line2D([], [], color=fg.ORANGE, lw=1.4, label="Mean revision"),
    ]
    ax_b.legend(handles=handles_b, loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=3, fontsize=7, frameon=False, handlelength=1.5, columnspacing=1.2)

    years = results["primary"]["years"]
    fg._title(
        fig,
        "CAPB revisions between first outturn and the final value: descriptive measurement-error appendix (S4)",
        f"{int(stat['n'])} country-years, {results['primary']['n_countries']} countries, {years[0]}-{years[1]}. First outturn: earliest archived AMECO vintage in which the year is not "
        "a forecast (Spring y+1). Final: Spring 2026, the vintage of the confirmatory analysis. Raw and unadjusted; no election effect is estimated.",
    )
    source = (
        "Source: European Commission, AMECO vintages Spring 2015 to Spring 2025 and Spring 2026 (item UBLGBP, CAPB, surplus positive); exposure year: frozen W_S "
        "(ETAD scheduled elections); author's calculations. CAPB is a model-based estimate; revisions mix new data and re-estimation of potential output."
    )
    fig.text(0.01, 0.0, textwrap.fill(source, fg.SOURCE_WRAP), ha="left", va="top", fontsize=7, color=fg.MUTED, linespacing=1.3)
    return fg._save(fig, path)


# ---------------------------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------------------------
def _n(x: float | None, d: int = 3) -> str:
    return "-" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{d}f}"


def _pct(x: float | None, d: int = 1) -> str:
    return "-" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{100 * x:.{d}f}%"


def _ci(interval: Sequence[float | None] | None, d: int = 3, pct: bool = False) -> str:
    if interval is None or interval[0] is None or interval[1] is None:
        return "-"
    f = _pct if pct else _n
    return f"[{f(interval[0], d)}, {f(interval[1], d)}]"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return lines


def _stat_rows(block: dict[str, Any]) -> list[list[str]]:
    s, ci = block["stats"], block["bootstrap_ci"]
    spec = [
        ("Mean revision (final - first), pp", "mean_revision", 3, False),
        ("Mean absolute revision, pp", "mean_abs_revision", 3, False),
        ("SD of the revision, pp", "sd_revision", 3, False),
        ("Median revision, pp", "median_revision", 3, False),
        ("Median absolute revision, pp", "median_abs_revision", 3, False),
        ("Share with |revision| above the SESOI", "share_abs_gt_sesoi", 1, True),
        ("Share with a sign change of the CAPB level", "share_sign_change_level", 1, True),
        ("Share with a sign change of the one-year change in CAPB", "share_sign_change_delta", 1, True),
        ("Correlation, first outturn and final", "corr_first_final", 3, False),
        ("Slope of final on first", "slope_final_on_first", 3, False),
        ("Intercept of final on first, pp", "intercept_final_on_first", 3, False),
        ("Slope of first on final", "slope_first_on_final", 3, False),
        ("Reliability ratio var(final) / var(first)", "reliability", 3, False),
        ("Correlation of the revision with the first outturn", "corr_rev_first", 3, False),
        ("Correlation of the revision with the final", "corr_rev_final", 3, False),
    ]
    rows = []
    for label, key, d, pct in spec:
        rows.append([label, _pct(s[key], d) if pct else _n(s[key], d), _ci(ci[key], d, pct)])
    return rows


def render_markdown(results: dict[str, Any]) -> str:
    """Markdown report of the S4 appendix; every number is taken from ``results``."""
    meta, prim, ext = results["meta"], results["primary"], results["extended"]
    s, ci = prim["stats"], prim["bootstrap_ci"]
    sesoi = meta["sesoi_pp"]
    sig, exp, chk = results["signal"], results["exposure"], results["checks"]
    es = ext["stats"]
    L: list[str] = []
    add = L.append
    add("# S4: CAPB revisions and measurement error (descriptive appendix)")
    add("")
    add(
        f"Specification: `{meta['spec']}` (dated 2026-10-13, SHA-256 `{meta['spec_sha256'][:16]}...`). Code: `src/evaluate/revisions.py`; figure: `reports/figures/s4_revisions.png`. "
        f"Units: percentage points (pp) of potential GDP (AMECO `UBLGBP`, surplus positive). Descriptive only: no election effect is estimated, the pre-registered headline is unchanged "
        f"(beta_S = {_n(sig['beta_S'])} pp, 95% interval {_ci([sig['beta_S_ci_lo'], sig['beta_S_ci_hi']])}), and all statements are associations."
    )
    add("")
    add(
        "Why this appendix exists: trigger T3 passed (the vintage archive carries CAPB for all 27 countries), but a real-time panel covers 2015-2021 only (189 of 715 confirmatory country-years; 51 elections), "
        "so an election-effect replication on first-release data is not feasible (Gate 5, `reports/gate5_realtime_feasibility.md`). What the archive supports is a description of how far the first-outturn "
        "CAPB lies from the final value used in the confirmatory analysis."
    )
    add("")
    add("## 0. Summary")
    add("")
    y0, y1 = prim["years"]
    add(f"- Sample: {prim['n']} country-years ({prim['n_countries']} countries, {y0}-{y1}); first-outturn vintages: {'; '.join(f'{k} ({v})' for k, v in prim['first_vintage_counts'].items())}.")
    add(f"- Revision (final - first outturn): mean {_n(s['mean_revision'], 2)} pp {_ci(ci['mean_revision'], 2)}; mean absolute {_n(s['mean_abs_revision'], 2)} pp {_ci(ci['mean_abs_revision'], 2)}; SD {_n(s['sd_revision'], 2)} pp {_ci(ci['sd_revision'], 2)}; median absolute {_n(s['median_abs_revision'], 2)} pp {_ci(ci['median_abs_revision'], 2)}.")
    add(f"- Level sign change in {_pct(s['share_sign_change_level'])} {_ci(ci['share_sign_change_level'], 1, True)} of country-years; correlation of first outturn and final {_n(s['corr_first_final'], 2)} {_ci(ci['corr_first_final'], 2)}.")
    add(f"- |Revision| above the {sesoi:g} pp SESOI in {_pct(s['share_abs_gt_sesoi'])} {_ci(ci['share_abs_gt_sesoi'], 1, True)} of country-years; mean absolute revision {_n(s['mean_abs_revision'], 2)} pp and median absolute revision {_n(s['median_abs_revision'], 2)} pp against {sesoi:g} pp (pre-specified reading in section 3).")
    add(f"- The SD of the revision is {_n(sig['sd_revision_over_abs_beta_S'], 1)} times |beta_S| and the mean absolute revision {_n(sig['mean_abs_revision_over_abs_beta_S'], 1)} times |beta_S|; the revision SD is {_n(sig['sd_revision_over_sd_within_confirmatory'], 2)} of the within-country SD of CAPB in the confirmatory sample.")
    add("")
    # ---- 1 definitions
    add("## 1. Definitions and sample")
    add("")
    add(
        "- **First outturn.** The value of CAPB for year y in the earliest archived vintage in which y is no longer a forecast. AMECO has no forecast flag, so the rule is structural: the last "
        f"{av.FORECAST_YEARS_BY_SEASON['spring']} year columns of a Spring vintage and the last {av.FORECAST_YEARS_BY_SEASON['autumn']} of an Autumn vintage are forecasts; Winter is treated like Autumn "
        f"({av.FORECAST_YEARS_BY_SEASON['winter']} forecast years; an assumption, since the previous year's outturn reaches AMECO only from Spring). The rule is applied by the frozen `ameco_vintages.first_release_table`."
    )
    add(f"- **Final.** {meta['final_vintage']} (the pinned vintage of the confirmatory analysis). Check: {chk['n_matched_to_panel']} of {chk['n_rows']} sample rows match the gold-panel CAPB; largest absolute difference between the panel CAPB and the final value {_n(chk['max_abs_panel_minus_final'], 6)} pp.")
    add("- **Revision** = final - first outturn (positive: the first outturn understated the surplus relative to the final).")
    add(f"- **Primary sample**: country-years {y0}-{y1} with both values ({prim['n']}). Extension: {ext['years'][0]}-{ext['years'][1]} ({ext['n']}); 2022-2024 lie outside the confirmatory sample. The 2014 first outturn is Spring 2015 (Autumn 2014 holds 2014 as a forecast).")
    add("")
    add("First-outturn vintages (primary sample): " + "; ".join(f"{k}: {v}" for k, v in prim["first_vintage_counts"].items()) + ".")
    add("")
    # ---- 2 distribution
    add("## 2. Revision statistics")
    add("")
    add(f"Primary sample, N = {prim['n']}. Intervals are 95% country-cluster percentile bootstrap intervals ({meta['n_boot']} draws, seed {meta['seed']}, {prim['n_countries']} clusters; approximate with so few clusters).")
    add("")
    L += _table(["Statistic", "Estimate", "95% interval"], _stat_rows(prim))
    add("")
    add(f"Mean revision with a CR1 t({prim['mean_revision_cr1']['n_clusters'] - 1}) interval: {_n(prim['mean_revision_cr1']['mean'])} pp {_ci([prim['mean_revision_cr1']['ci_lo'], prim['mean_revision_cr1']['ci_hi']])}.")
    add(f"The sign-of-change share uses the {int(s['n_delta'])} country-years with the one-year change defined in both vintages. Exact zeros never count as sign changes.")
    add("")
    q = prim["quantiles"]
    add("Quantiles (pp):")
    add("")
    levels = list(q["revision"])
    L += _table(["Quantity"] + [f"{100 * float(l):g}%" for l in levels], [["Revision"] + [_n(q["revision"][l], 2) for l in levels], ["Absolute revision"] + [_n(q["abs_revision"][l], 2) for l in levels]])
    add("")
    add("Largest absolute revisions (pp):")
    add("")
    L += _table(["Country", "Year", "First outturn", "Final", "Revision"], [[r["eurostat_code"], str(r["year"]), _n(r["first"], 2), _n(r["final"], 2), _n(r["revision"], 2)] for r in prim["top_revisions"]])
    add("")
    # ---- 3 SESOI
    add(f"## 3. Revisions against the {sesoi:g} pp smallest effect size of interest")
    add("")
    mean_above = ci["mean_abs_revision"][0] is not None and ci["mean_abs_revision"][0] > sesoi
    med_above = ci["median_abs_revision"][0] is not None and ci["median_abs_revision"][0] > sesoi
    add(
        f"The mean absolute revision is {_n(s['mean_abs_revision'], 2)} pp {_ci(ci['mean_abs_revision'], 2)}, the median absolute revision {_n(s['median_abs_revision'], 2)} pp {_ci(ci['median_abs_revision'], 2)}, "
        f"and {_pct(s['share_abs_gt_sesoi'])} {_ci(ci['share_abs_gt_sesoi'], 1, True)} of country-years have |revision| above {sesoi:g} pp."
    )
    add("")
    if mean_above and med_above:
        add(f"Reading (pre-specified rule, spec section 2 item 7): both the mean and the median absolute revision have intervals entirely above {sesoi:g} pp, so the typical first-outturn revision exceeds the SESOI.")
    elif mean_above:
        add(
            f"Reading (pre-specified rule, spec section 2 item 7): the mean absolute revision exceeds the SESOI (interval entirely above {sesoi:g} pp), so on average the first outturn lies further from the final than the effect size the study aims to bound. "
            f"The median absolute revision ({_n(s['median_abs_revision'], 2)} pp {_ci(ci['median_abs_revision'], 2)}) does not have an interval entirely above {sesoi:g} pp: the distribution is right-skewed, "
            f"so the claim 'the typical revision exceeds the SESOI' holds for the mean and not unambiguously for the median. Both are reported; neither is preferred."
        )
    elif med_above:
        add(f"Reading (pre-specified rule): the median absolute revision exceeds the SESOI; the mean absolute revision interval ({_ci(ci['mean_abs_revision'], 2)}) does not lie entirely above {sesoi:g} pp.")
    else:
        def where(est: float, interval: Sequence[float | None]) -> str:
            side = "above" if est > sesoi else "below"
            inside = interval[0] is not None and interval[0] <= sesoi <= interval[1]
            return f"point estimate {_n(est, 2)} pp ({side} {sesoi:g} pp), interval {_ci(interval, 2)} {'contains' if inside else 'excludes'} {sesoi:g} pp"

        add(
            f"Reading (pre-specified rule, spec section 2 item 7): neither the mean nor the median absolute revision has an interval entirely above {sesoi:g} pp, so this sample does not support the statement that the typical revision exceeds the SESOI. "
            f"Mean absolute revision: {where(s['mean_abs_revision'], ci['mean_abs_revision'])}. Median absolute revision: {where(s['median_abs_revision'], ci['median_abs_revision'])}. "
            f"The mean is pulled up by a right tail (the largest revisions are listed above) while {_pct(1 - s['share_abs_gt_sesoi'], 0)} of country-years lie within {sesoi:g} pp of the final. "
            f"What can be said: revisions of the size of the SESOI are common ({_pct(s['share_abs_gt_sesoi'], 0)} of country-years exceed it) and the revision SD ({_n(s['sd_revision'], 2)} pp) is a multiple of it."
        )
    add("")
    # ---- 4 noise to signal
    add("## 4. Noise-to-signal comparison")
    add("")
    add(
        f"Headline beta_S = {_n(sig['beta_S'])} pp (95% bootstrap-t interval {_ci([sig['beta_S_ci_lo'], sig['beta_S_ci_hi']])}; pre-registered V7, unchanged). Plain quotients; no inference."
    )
    add("")
    L += _table(
        ["Quantity", "Value"],
        [
            ["SD of the revision / |beta_S|", _n(sig["sd_revision_over_abs_beta_S"], 2)],
            ["Mean absolute revision / |beta_S|", _n(sig["mean_abs_revision_over_abs_beta_S"], 2)],
            [f"SD of final CAPB, revision sample (pp)", _n(sig["sd_final_revision_sample"], 2)],
            ["SD of the revision / SD of final CAPB, revision sample", _n(sig["sd_revision_over_sd_final_revision_sample"], 2)],
            [f"SD of CAPB, confirmatory sample (N = {sig['n_confirmatory']}) (pp)", _n(sig["sd_capb_confirmatory"], 2)],
            ["SD of the revision / SD of CAPB, confirmatory sample", _n(sig["sd_revision_over_sd_capb_confirmatory"], 2)],
            ["Within-country SD of CAPB, confirmatory sample (pp)", _n(sig["sd_capb_within_country_confirmatory"], 2)],
            ["SD of the revision / within-country SD", _n(sig["sd_revision_over_sd_within_confirmatory"], 2)],
            ["Two-way (country and year) demeaned SD of CAPB, confirmatory sample (pp)", _n(sig["sd_capb_twoway_confirmatory"], 2)],
            ["SD of the revision / two-way demeaned SD", _n(sig["sd_revision_over_sd_twoway_confirmatory"], 2)],
        ],
    )
    add("")
    add(
        f"Reading: the revision SD ({_n(s['sd_revision'], 2)} pp) is {_n(sig['sd_revision_over_abs_beta_S'], 1)} times the size of the estimated beta_S. The variation a fixed-effects design uses (within-country, or net of country and year effects) has an SD of "
        f"{_n(sig['sd_capb_within_country_confirmatory'], 2)} and {_n(sig['sd_capb_twoway_confirmatory'], 2)} pp, so the revision SD is {_n(sig['sd_revision_over_sd_within_confirmatory'], 2)} and {_n(sig['sd_revision_over_sd_twoway_confirmatory'], 2)} times those scales. "
        "This describes how noisy a first-outturn CAPB would have been as a measure of the final value; it does not say that the final value is free of error, and it does not by itself bias or invalidate the pre-registered estimate."
    )
    add("")
    # ---- 5 reliability
    add("## 5. Reliability and attenuation (illustration, no correction applied)")
    add("")
    rel, rci = s["reliability"], ci["reliability"]
    cr, cf = s["corr_rev_first"], s["corr_rev_final"]
    closer = "final" if abs(cf) < abs(cr) else "first outturn"
    add(f"Reliability ratio var(final) / var(first outturn) = {_n(rel)} {_ci(rci)}; SD of the first outturn {_n(s['sd_first'], 2)} pp, of the final {_n(s['sd_final'], 2)} pp. Slope of final on first {_n(s['slope_final_on_first'])} {_ci(ci['slope_final_on_first'])}; slope of first on final {_n(s['slope_first_on_final'])} {_ci(ci['slope_first_on_final'])}.")
    add("")
    add(
        "Classical-measurement-error reasoning, in words. Suppose the first outturn equalled the final value plus noise that is independent of the final value. Then var(first) = var(final) + var(noise), so the reliability ratio would be below one, "
        "and it would equal the factor by which an OLS slope on the first outturn *used as a regressor* shrinks towards zero (a true slope of 1 would be estimated near the reliability). "
        "Under that model the revision would also be uncorrelated with the final value. The opposite polar case treats the revision as news that is independent of the first outturn (final = first + news); "
        "then var(final) is at least var(first), the reliability is at least one, and there is no attenuation. "
        "In this sample, "
        + (
            f"the reliability is below one ({_n(rel, 2)}), the direction the noise model predicts"
            if rel < 1
            else f"the reliability is at or above one ({_n(rel, 2)}), the direction of the news model and not of added noise"
        )
        + f"; the revision is correlated {_n(cr, 2)} {_ci(ci['corr_rev_first'], 2)} with the first outturn and {_n(cf, 2)} {_ci(ci['corr_rev_final'], 2)} with the final, the correlation with the {closer} being closer to zero. "
        f"The gap between the reliability and the slope of final on first ({_n(rel - s['slope_final_on_first'], 3)}) equals cov(revision, final) / var(first) and is zero in the pure classical-noise case. "
        "The real process is probably a mixture (new outturn data are news; re-estimation of potential output and benchmark changes behave more like systematic shifts), and the sample cannot separate the two."
    )
    add("")
    add(
        "What this means for the headline. In the pre-registered model CAPB is the *outcome* and the exposure `W_S` is calendar-based. Classical noise in an outcome does not bias the coefficient on an error-free regressor; it widens the interval. "
        "The attenuation reasoning therefore applies to analyses that use CAPB (or its lags) as a regressor and to any real-time re-analysis. Non-classical error, i.e. revisions associated with election exposure, is the case that could matter for the headline; section 7 describes it. "
        "No correction is applied: the headline stays as pre-registered."
    )
    add("")
    # ---- 6 by year / country
    add("## 6. Revision size by year and by country")
    add("")
    add("By year (27 country-years each; `n_exposed` = country-years with `W_S > 0`, available for the confirmatory sample only). Rows marked * lie outside the confirmatory sample (2022-2024) and are not part of the primary sample.")
    add("")
    rows = []
    for r in results["by_year"]:
        n_exp = "-" if r["n_exposed"] is None or (isinstance(r["n_exposed"], float) and not np.isfinite(r["n_exposed"])) else str(int(r["n_exposed"]))
        rows.append([f"{r['year']}" + ("" if r["in_confirmatory_sample"] else "*"), str(r["n"]), n_exp, _n(r["mean_revision"], 2), _n(r["sd_revision"], 2), _n(r["mean_abs_revision"], 2), _pct(r["share_abs_gt_sesoi"], 0), _pct(r["share_sign_change_level"], 0)])
    L += _table(["Year", "n", "n_exposed", "Mean revision", "SD", "Mean abs", f"|rev| > {sesoi:g}", "Sign change"], rows)
    add("")
    add("By country (primary sample, 8 years each, sorted by mean absolute revision; country-level statistics from 8 observations are unstable):")
    add("")
    rows = [[r["eurostat_code"], str(r["n"]), _n(r["mean_revision"], 2), _n(r["sd_revision"], 2), _n(r["mean_abs_revision"], 2), _n(r["median_abs_revision"], 2), _pct(r["share_abs_gt_sesoi"], 0), _pct(r["share_sign_change_level"], 0)] for r in results["by_country"]]
    L += _table(["Country", "n", "Mean revision", "SD", "Mean abs", "Median abs", f"|rev| > {sesoi:g}", "Sign change"], rows)
    add("")
    # ---- 7 exposure
    add("## 7. Revisions and election-exposure years (descriptive, unadjusted)")
    add("")
    ex_s, un_s = exp["strata"]["exposed"], exp["strata"]["unexposed"]
    d1, d2 = exp["difference_mean_revision"], exp["difference_mean_abs_revision"]
    rows = []
    for name, st in (("Exposure year (`W_S > 0`)", ex_s), ("Not an exposure year (`W_S = 0`)", un_s)):
        m, a = st["mean_revision"], st["mean_abs_revision"]
        rows.append([name, str(st["n"]), str(st["n_countries"]), f"{_n(m['mean'])} {_ci([m['ci_lo'], m['ci_hi']])}", f"{_n(a['mean'])} {_ci([a['ci_lo'], a['ci_hi']])}", _n(st["sd_revision"], 2), _pct(st["share_sign_change_level"])])
    L += _table(["Stratum", "n", "Countries", "Mean revision, pp [95% CI, country-clustered t]", "Mean abs revision, pp [95% CI]", "SD", "Sign change"], rows)
    add("")
    add(
        f"Difference in the mean revision (exposure year minus other years): {_n(d1['cr1']['difference'])} pp, CR1 t({d1['cr1']['n_clusters'] - 1}) interval {_ci([d1['cr1']['ci_lo'], d1['cr1']['ci_hi']])}, country-cluster bootstrap interval {_ci(d1['bootstrap_ci'])}. "
        f"Difference in the mean absolute revision: {_n(d2['cr1']['difference'])} pp, CR1 interval {_ci([d2['cr1']['ci_lo'], d2['cr1']['ci_hi']])}, bootstrap interval {_ci(d2['bootstrap_ci'])}."
    )
    add("")
    add(
        "Descriptive and unadjusted: no controls, no country or year effects, no test of the election effect is reported or implied. An exposure-year difference in revisions could indicate that first-outturn CAPB is biased around elections (a real-time bias), "
        "but it could equally reflect which countries and years are exposed (the exposure-year count by year is in section 6), so it is not a replication of the election effect and it does not enter the confirmatory family."
    )
    add("")
    # ---- 8 gate 5
    add("## 8. Comparison with Gate 5")
    add("")
    labels = {"mean_abs_revision": "Mean absolute revision, pp", "sd_revision": "SD of the revision, pp", "share_sign_change_level": "Level sign-change share", "corr_first_final": "Correlation first/final"}
    rows = []
    for g in results["gate5"]:
        quoted_d = 3 if g["statistic"] == "share_sign_change_level" else 2
        rows.append([labels[g["statistic"]], _n(g["gate5_table"], 3), _n(g["gate5_quoted"], quoted_d), _n(g["s4"], 5), "yes" if g["agrees_with_table"] else "NO", "yes" if g["agrees_with_quoted"] else "NO"])
    L += _table(["Statistic", "Gate 5 table (3 d)", "Quoted in issue / decision log", "S4 (unrounded)", "Agrees with table at 3 d", "Agrees with quoted figure"], rows)
    add("")
    gates = results["gate5"]
    if all(g["agrees_with_table"] for g in gates):
        add(
            "All four statistics reproduce the Gate 5 table at its three-decimal rounding. Same definition (first outturn = earliest archived vintage with the year non-forecast under the Spring 2 / Autumn 3 rule, the frozen `first_release_table`), "
            "same window (2014-2021), same final (pinned Spring 2026) and the same country-years: S4 restates the Gate 5 computation and adds intervals; it is not a new estimate."
        )
    else:
        bad = [g["statistic"] for g in gates if not g["agrees_with_table"]]
        add(f"The following statistics differ from the Gate 5 table at three decimals: {', '.join(bad)}. Both use the frozen `first_release_table`, so the difference points to a sample or definition difference that has to be traced before the appendix is used.")
    for g in (g for g in gates if g["agrees_with_table"] and not g["agrees_with_quoted"]):
        add("")
        add(
            f"The rounded figure quoted in the issue and the decision log for the {labels[g['statistic']].split(',')[0].lower()} ({_n(g['gate5_quoted'], 2)}) differs from the S4 value rounded to two decimals ({_n(round(g['s4'], 2), 2)}): "
            f"the unrounded S4 value is {_n(g['s4'], 5)}, which Gate 5 printed as {_n(g['gate5_table'], 3)}; rounding that three-decimal figure a second time gives {_n(g['gate5_quoted'], 2)}. "
            "This is a double-rounding difference of one unit in the second decimal, not a difference of sample or definition."
        )
    add("")
    # ---- 9 extension
    add(f"## 9. Sensitivity: extended window {ext['years'][0]}-{ext['years'][1]}")
    add("")
    add(f"N = {ext['n']} ({ext['n_countries']} countries); 2022-2024 are outside the confirmatory sample, and their final values are only 1 to 3 years after the first outturn, so late revisions are not yet in.")
    add("")
    eci = ext["bootstrap_ci"]
    L += _table(
        ["Statistic", "Primary", "Extended", "Extended 95% interval"],
        [
            ["N", str(int(s["n"])), str(int(es["n"])), ""],
            ["Mean revision, pp", _n(s["mean_revision"]), _n(es["mean_revision"]), _ci(eci["mean_revision"])],
            ["Mean absolute revision, pp", _n(s["mean_abs_revision"]), _n(es["mean_abs_revision"]), _ci(eci["mean_abs_revision"])],
            ["SD of the revision, pp", _n(s["sd_revision"]), _n(es["sd_revision"]), _ci(eci["sd_revision"])],
            ["Median absolute revision, pp", _n(s["median_abs_revision"]), _n(es["median_abs_revision"]), _ci(eci["median_abs_revision"])],
            [f"Share |revision| > {sesoi:g} pp", _pct(s["share_abs_gt_sesoi"]), _pct(es["share_abs_gt_sesoi"]), _ci(eci["share_abs_gt_sesoi"], 1, True)],
            ["Level sign-change share", _pct(s["share_sign_change_level"]), _pct(es["share_sign_change_level"]), _ci(eci["share_sign_change_level"], 1, True)],
            ["Correlation first/final", _n(s["corr_first_final"]), _n(es["corr_first_final"]), _ci(eci["corr_first_final"])],
            ["Reliability var(final)/var(first)", _n(s["reliability"]), _n(es["reliability"]), _ci(eci["reliability"])],
        ],
    )
    add("")
    # ---- 10 limitations
    add("## 10. Limitations")
    add("")
    for item in (
        "CAPB is a model-based estimate (potential output, budget semi-elasticities). A revision mixes new outturn data with re-estimation of the model; the decomposition is not identified here.",
        "AMECO methodology changes between vintages (ESA 95 to ESA 2010 in Autumn 2015, a level shift at Spring 2020, COVID treatment; Gate 5 section 4), so a revision is not pure data noise and the vintage series is not homogeneous.",
        "The archived chapter 17 files are not guaranteed to be the originally released versions (Gate 5 section 8), so 'first outturn' means first outturn in the archive.",
        "The real-time panel covers 2015-2021 for elections (189 of 715 country-years; 51 elections), so it cannot support a replication of the election effect, and this appendix does not attempt one.",
        "The forecast / outturn cut-off is structural (no AMECO flag); country-specific exceptions were not checked. If Winter were treated as two forecast years the first outturn of some years could be a Winter vintage (Gate 5 section 8).",
        "Eight years per country and 27 countries: country-level statistics are unstable and the percentile bootstrap with 27 clusters is approximate. The intervals describe the sampling variation of the country panel, not the model uncertainty of AMECO.",
        "The reliability ratio, the sign-change shares and the exposure comparison are descriptive features of this panel, not estimates of a structural measurement-error parameter or of a real-time bias.",
    ):
        add(f"- {item}")
    add("")
    # ---- 11 provenance
    add("## 11. Provenance")
    add("")
    v = meta["versions"]
    add(f"- seed {meta['seed']}, {meta['n_boot']} country-cluster bootstrap draws, level {meta['level']:g}; numpy {v['numpy']}, pandas {v['pandas']}, scipy {v['scipy']}.")
    add(f"- vintage long table `data/interim/ameco_vintage_capb.csv` SHA-256 `{meta['interim_csv_sha256']}`.")
    add("- confirmatory panel read through `m1.load_real_panel` (tag `preregistration-v1`, hash-checked); used for `W_S` and for the SD of CAPB only.")
    add("- reproduce: `python src/evaluate/revisions.py`; tests: `python -m pytest tests/test_revisions.py -q -p no:cacheprovider`.")
    add("")
    return "\n".join(L)


# ---------------------------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------------------------
def _clean(value: Any) -> Any:
    """JSON-safe copy: numpy scalars to Python, NaN and inf to None."""
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def main(argv: Sequence[str] | None = None) -> dict[str, Any]:
    """Compute S4 on the real data and write the markdown, JSON and figure."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument("--figures-dir", type=Path, default=FIGURES_DIR)
    parser.add_argument("--n-boot", type=int, default=N_BOOT)
    args = parser.parse_args(argv)
    import matplotlib

    matplotlib.use("Agg")
    import m1  # noqa: PLC0415  (tag-guarded loader; heavy import kept out of module import)

    panel, extract_hash = m1.load_real_panel()
    long = load_long()
    headline = fg.load_json(HEADLINE_JSON)
    results = compute(long, panel, headline, n_boot=args.n_boot)
    results["meta"]["gold_extract_hash"] = extract_hash
    table = attach_exposure(revision_table(long, av.vintage_specs(), PRIMARY_WINDOW), panel)[0]
    args.results_dir.mkdir(parents=True, exist_ok=True)
    (args.results_dir / f"{OUT_STEM}.json").write_text(json.dumps(_clean(results), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (args.results_dir / f"{OUT_STEM}.md").write_text(render_markdown(results), encoding="utf-8")
    figure_revisions(table, results, args.figures_dir / f"{OUT_STEM}.png")
    return results


if __name__ == "__main__":
    main()
