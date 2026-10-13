"""Publication-quality results figures for the thesis (post-freeze; descriptive display of frozen results).

Five figures, written to ``reports/figures`` at 300 dpi in the visual style of ``secondary_forest.png`` (``src/models/py/secondary.py``):

1. ``f1_headline_estimates.png``: beta_S, gamma_B, gamma_W with 95% bootstrap-t intervals, the +-SESOI band, Holm p-values
   (``reports/results/m1_confirmatory.json``).
2. ``f2_election_window_profile.png``: raw mean CAPB by year relative to each scheduled election, 95% CI clustered by country.
   Descriptive only; no inference is implied.
3. ``f3_exposure_vs_capb_partial.png``: Frisch-Waugh partial-association plot of CAPB on W_S (OLS-FE, descriptive) with the
   pre-registered V7 estimate quoted.
4. ``f4_inference_ladder.png``: beta_S across the inference specifications of ``reports/results/robustness.json``; the order is the
   order of the specification list (never ranked or selected) and the figure follows the file when rows are added.
5. ``f5_capb_country_year_heatmap.png``: country x year CAPB heatmap (diverging, centred at 0), scheduled-election years dotted.

Nothing here estimates a model for inference. The design matrix of figure 3 comes from ``power_variants.build_variant_design`` (the M1 /
V7 builder, imported and not copied); the sample is read only through ``m1.load_real_panel`` (tag-guarded, hash-checked). The
scheduled-election years are those of ``data/interim/election_calendar_eu27.csv`` (``class_primary == 'scheduled'``, the frozen ETAD
classification). Language is that of associations. The Agg backend is selected in :func:`main` only; the figure functions use
``matplotlib.figure.Figure`` and do not touch pyplot state.

Run: ``python src/evaluate/figures.py`` (optional ``--out-dir``).
"""
from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from matplotlib import colormaps
from matplotlib.colors import TwoSlopeNorm
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIGURES_DIR = PROJECT_ROOT / "reports" / "figures"
RESULTS_DIR = PROJECT_ROOT / "reports" / "results"
HEADLINE_JSON = RESULTS_DIR / "m1_confirmatory.json"
ROBUSTNESS_JSON = RESULTS_DIR / "robustness.json"
CALENDAR_CSV = PROJECT_ROOT / "data" / "interim" / "election_calendar_eu27.csv"
COUNTRIES_CSV = PROJECT_ROOT / "config" / "countries.csv"

DPI = 300  # minimum for publication figures (CLAUDE.md)
CI_LEVEL = 0.95
EVENT_WINDOW = 3  # years before and after a scheduled-election year shown in figure 2
N_BINS = 10  # quantile bins of the binned-mean overlay in figure 3
HEATMAP_CLIP_PCT = 99.0  # the heatmap colour scale is symmetric and clipped at this percentile of |CAPB|
HEADLINE_TARGETS = ("beta_S", "gamma_B", "gamma_W")
SCHEDULED_CLASS = "scheduled"
LADDER_SECTIONS = ("A",)  # section A of robustness.json holds the inference specifications; C and D are sample / specification checks
FIGURE_NAMES = {
    "f1": "f1_headline_estimates.png",
    "f2": "f2_election_window_profile.png",
    "f3": "f3_exposure_vs_capb_partial.png",
    "f4": "f4_inference_ladder.png",
    "f5": "f5_capb_country_year_heatmap.png",
}

# Style of secondary_forest.png (ink / muted grey / red accent) plus Okabe-Ito colours (colour-blind safe) for categories.
INK, MUTED, ACCENT = "#1f2933", "#7b8794", "#b3261e"
BLUE, VERMILLION, SKY, ORANGE = "#0072B2", "#D55E00", "#56B4E9", "#E69F00"
GRID = "#d5dae0"
SOURCE_LINE = "Source: European Commission, AMECO Spring 2026; Eurostat; ETAD; ParlGov; author's calculations."
SOURCE_WRAP = 120  # characters per line of the source note


# ---------------------------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------------------------
def _figure(width: float, height: float) -> Figure:
    """A figure that does not depend on the pyplot backend state."""
    return Figure(figsize=(width, height))


def _title(fig: Figure, title: str, subtitle: str | None = None, y: float = 0.995) -> None:
    """Left-aligned title (states what is shown) and an optional grey second line, as in ``secondary_forest.png``."""
    fig.text(0.01, y, title, ha="left", va="top", fontsize=10.5, fontweight="bold", color=INK)
    if subtitle:
        fig.text(0.01, y - 0.27 / fig.get_figheight(), textwrap.fill(subtitle, 118), ha="left", va="top", fontsize=8, color=MUTED, linespacing=1.3)


def _source(fig: Figure, extra: str = "", y: float = -0.01) -> None:
    """Source / attribution line (and an optional note) under the figure."""
    fig.text(0.01, y, textwrap.fill((SOURCE_LINE + " " + extra).strip(), SOURCE_WRAP), ha="left", va="top", fontsize=7, color=MUTED, linespacing=1.3)


def _clean_axes(ax: Any, *, left: bool = True) -> None:
    for side in ("top", "right") + (() if left else ("left",)):
        ax.spines[side].set_visible(False)
    ax.tick_params(labelsize=8, colors=INK)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(INK)


def _save(fig: Figure, path: Path) -> Path:
    """Write the figure at ``DPI`` (tight bounding box, so nothing is clipped) and return the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, bbox_inches="tight", pad_inches=0.12, facecolor="white")
    return path


def _num(value: Any) -> float | None:
    return None if value is None else float(value)


# ---------------------------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------------------------
def load_json(path: Path) -> dict:
    """Parse a results file (UTF-8)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sesoi_of(document: dict) -> float:
    """Smallest effect size of interest in pp: ``sesoi_pp`` of ``m1_confirmatory.json`` or ``meta.sesoi_pp`` of ``robustness.json``."""
    if "sesoi_pp" in document:
        return float(document["sesoi_pp"])
    meta = document.get("meta", {})
    if "sesoi_pp" in meta:
        return float(meta["sesoi_pp"])
    raise KeyError("no sesoi_pp in the results document")


def headline_rows(headline: dict) -> list[dict]:
    """One dict per headline target (``HEADLINE_TARGETS`` order) from ``m1_confirmatory.json``.

    Keys: name, estimate, ci_lo, ci_hi, p_holm (None for the descriptive gamma_W), reading, role.
    """
    rows = []
    for name in HEADLINE_TARGETS:
        if name not in headline["targets"]:
            raise KeyError(f"target {name!r} missing from the headline results")
        t = headline["targets"][name]
        rows.append({"name": name, "estimate": float(t["estimate"]), "ci_lo": float(t["ci_lo"]), "ci_hi": float(t["ci_hi"]),
                     "p_holm": _num(t.get("p_holm")), "reading": t.get("reading"), "role": t.get("role", "")})
    return rows


def _spec_label(row: dict) -> str:
    label, inference = str(row.get("label", row.get("id", ""))), str(row.get("inference", ""))
    named_in_label = inference.split(" (")[0].split(",")[0].strip().lower() in label.lower()  # e.g. "Driscoll-Kraay" appears in both
    return f"{label}, {inference}" if inference and not named_in_label else label


def ladder_rows(robustness: dict, sections: Sequence[str] = LADDER_SECTIONS) -> tuple[list[dict], int]:
    """Rows of the inference ladder, in file order: the V7 headline first, then every ``rows`` entry of the named ``sections`` (default A).

    A row needs a ``beta_S`` target with an estimate and an interval; rows without one (a failed specification) are skipped and counted.
    ``excludes_zero`` is recomputed from the 95% interval (the definition of ``summary.definitions``). Returns ``(rows, n_skipped)``.
    """
    head = robustness["headline"]["targets"]["beta_S"]
    rows: list[dict] = [{"id": "headline", "group": "", "label": "V7 headline (pre-registered)", "kind": "headline", "estimate": float(head["estimate"]),
                         "ci_lo": float(head["ci_lo"]), "ci_hi": float(head["ci_hi"])}]
    skipped = 0
    for key in sections:
        section = robustness.get("sections", {}).get(key)
        if not isinstance(section, dict) or not isinstance(section.get("rows"), list):
            continue
        for row in section["rows"]:
            t = (row.get("targets") or {}).get("beta_S")
            if row.get("status", "ok") != "ok" or not t or t.get("estimate") is None or t.get("ci_lo") is None or t.get("ci_hi") is None:
                skipped += 1
                continue
            rows.append({"id": row.get("id", ""), "group": str(row.get("group", "")), "label": _spec_label(row), "kind": "spec",
                         "estimate": float(t["estimate"]), "ci_lo": float(t["ci_lo"]), "ci_hi": float(t["ci_hi"])})
    for row in rows:
        row["excludes_zero"] = bool(row["ci_lo"] > 0 or row["ci_hi"] < 0)
    return rows, skipped


# ---------------------------------------------------------------------------------------------
# F1: headline estimates
# ---------------------------------------------------------------------------------------------
ROW_LABELS = {
    "beta_S": "beta_S\nfull year of pre-election exposure\nto a scheduled election (W_S = 1)",
    "gamma_B": "gamma_B\nx between-country ageing component\n(per +1 SD)",
    "gamma_W": "gamma_W\nx within-country ageing component\n(per +1 SD)",
}


def _headline_note(row: dict, sesoi: float) -> str:
    lines = [f"{row['estimate']:+.3f}  [{row['ci_lo']:+.3f}, {row['ci_hi']:+.3f}]"]
    if row["p_holm"] is None:
        lines.append("descriptive, not tested")
    else:
        lines.append(f"Holm p = {row['p_holm']:.4f}")
        if row["reading"]:
            lines.append(str(row["reading"]).replace("+-sesoi", f"±{sesoi:g} pp"))
    return "\n".join(lines)


def figure_headline_estimates(headline: dict, path: Path) -> Path:
    """Figure 1: point estimates with 95% bootstrap-t intervals for beta_S, gamma_B, gamma_W; +-SESOI band, zero line, Holm p."""
    rows, sesoi = headline_rows(headline), sesoi_of(headline)
    fig = _figure(7.4, 3.9)
    ax = fig.add_axes([0.30, 0.25, 0.68, 0.58])
    n = len(rows)
    ax.axvspan(-sesoi, sesoi, color=SKY, alpha=0.22, lw=0, zorder=0)
    ax.axvline(0.0, color=MUTED, lw=1.0, ls="--", zorder=1)
    x_text = max(r["ci_hi"] for r in rows) + 0.18
    for i, row in enumerate(rows):
        y = n - 1 - i
        confirmatory = row["p_holm"] is not None
        colour = BLUE if confirmatory else MUTED
        ax.plot([row["ci_lo"], row["ci_hi"]], [y, y], color=colour, lw=1.8, solid_capstyle="butt", zorder=2)
        ax.plot([row["estimate"]], [y], "o", ms=7, mfc=colour if confirmatory else "white", mec=colour, mew=1.5, zorder=3)
        ax.text(x_text, y, _headline_note(row, sesoi), ha="left", va="center", fontsize=8, color=INK, linespacing=1.35)
    ax.set_yticks(range(n))
    ax.set_yticklabels([ROW_LABELS[r["name"]] for r in reversed(rows)], fontsize=8.5, color=INK, linespacing=1.3)
    ax.set_ylim(-0.6, n - 0.4)
    lo = min(min(r["ci_lo"] for r in rows), -sesoi) - 0.1
    ax.set_xlim(lo, x_text + 1.25 * (max(r["ci_hi"] for r in rows) - lo) * 0.3 + 0.45)
    ax.set_xticks([t for t in np.arange(np.ceil(lo * 2) / 2, x_text + 0.01, 0.5)])
    ax.xaxis.grid(True, color=GRID, lw=0.5, zorder=0)
    ax.set_axisbelow(True)
    ax.set_xlabel("Association with CAPB, pp of potential GDP\n(beta_S per unit of exposure; gamma per +1 SD of the ageing component)", fontsize=8, color=INK)
    _clean_axes(ax, left=False)
    ax.tick_params(axis="y", length=0)
    handles = [Line2D([], [], color=BLUE, marker="o", ms=6, lw=1.6, label="Confirmatory (Holm family: beta_S, gamma_B)"),
               Line2D([], [], color=MUTED, marker="o", ms=6, mfc="white", lw=1.6, label="Descriptive"),
               Patch(facecolor=SKY, alpha=0.4, label=f"±SESOI band (±{sesoi:g} pp)")]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.42, -0.3), ncol=3, fontsize=7.5, frameon=False, handlelength=1.6, columnspacing=1.2)
    _title(fig, "Headline estimates: associations of scheduled-election exposure with CAPB (V7)",
           f"Point estimate and 95% unrestricted bootstrap-t interval (n = {headline['n_obs']}, {headline['n_countries']} countries). "
           "Holm adjustment over beta_S and gamma_B only; gamma_W is reported without a test.")
    _source(fig, "Associations; scheduled elections are predetermined, not exogenous.", y=0.0)
    return _save(fig, path)


# ---------------------------------------------------------------------------------------------
# F2: election-window profile
# ---------------------------------------------------------------------------------------------
def clustered_mean_ci(values: Any, clusters: Any, level: float = CI_LEVEL) -> dict:
    """Mean of ``values`` with a cluster-robust (CR1) t interval, t(G - 1).

    ``var(mean) = G / (G - 1) * sum_g (sum_{i in g} (x_i - mean))^2 / n^2``. NaN values are dropped; with fewer than two clusters the
    interval is NaN. Returns ``{"mean", "ci_lo", "ci_hi", "n", "n_clusters"}``.
    """
    x = np.asarray(values, float)
    g = np.asarray(clusters)
    keep = ~np.isnan(x)
    x, g = x[keep], g[keep]
    n = int(x.size)
    if n == 0:
        return {"mean": np.nan, "ci_lo": np.nan, "ci_hi": np.nan, "n": 0, "n_clusters": 0}
    mean = float(x.mean())
    _, inverse = np.unique(g, return_inverse=True)
    n_clusters = int(inverse.max()) + 1
    if n_clusters < 2:
        return {"mean": mean, "ci_lo": np.nan, "ci_hi": np.nan, "n": n, "n_clusters": n_clusters}
    sums = np.bincount(inverse, weights=x - mean)
    se = float(np.sqrt(n_clusters / (n_clusters - 1) * np.sum(sums**2)) / n)
    half = float(stats.t.ppf(0.5 + level / 2, n_clusters - 1)) * se
    return {"mean": mean, "ci_lo": mean - half, "ci_hi": mean + half, "n": n, "n_clusters": n_clusters}


def load_scheduled_events(path: Path = CALENDAR_CSV) -> pd.DataFrame:
    """Scheduled elections of the frozen calendar: columns ``eurostat_code``, ``year`` (one row per election, ``class_primary == 'scheduled'``)."""
    calendar = pd.read_csv(path)
    keep = (calendar["class_primary"] == SCHEDULED_CLASS) & calendar["in_calendar"].astype(bool)
    return calendar.loc[keep, ["eurostat_code", "year"]].drop_duplicates().reset_index(drop=True)


def event_window_values(panel: pd.DataFrame, events: pd.DataFrame, window: int = EVENT_WINDOW) -> pd.DataFrame:
    """Event-level values: one row per (event, k) with the country-demeaned CAPB ``deviation`` and the year-on-year ``change``.

    ``k`` = calendar year minus the scheduled-election year, ``-window..window``. The country mean is taken over the rows of ``panel``
    (rows with CAPB observed); ``change`` needs the previous calendar year. Inputs are not modified.
    """
    p = panel.loc[panel["capb"].notna(), ["eurostat_code", "year", "capb"]].sort_values(["eurostat_code", "year"]).reset_index(drop=True)
    by = p.groupby("eurostat_code")
    p["deviation"] = p["capb"] - by["capb"].transform("mean")
    p["change"] = (p["capb"] - by["capb"].shift(1)).where(by["year"].diff() == 1)
    ev = events[["eurostat_code", "year"]].drop_duplicates().rename(columns={"year": "event_year"})
    grid = ev.merge(pd.DataFrame({"k": np.arange(-window, window + 1)}), how="cross")
    grid["year"] = grid["event_year"] + grid["k"]
    return grid.merge(p[["eurostat_code", "year", "deviation", "change"]], on=["eurostat_code", "year"], how="inner")


def event_window_summary(panel: pd.DataFrame, events: pd.DataFrame, window: int = EVENT_WINDOW, level: float = CI_LEVEL) -> pd.DataFrame:
    """Mean and country-clustered CI by ``k`` for both measures: columns measure, k, mean, ci_lo, ci_hi, n, n_clusters."""
    values = event_window_values(panel, events, window)
    records = []
    for measure in ("deviation", "change"):
        for k in range(-window, window + 1):
            sub = values[values["k"] == k]
            records.append({"measure": measure, "k": k, **clustered_mean_ci(sub[measure].to_numpy(), sub["eurostat_code"].to_numpy(), level)})
    return pd.DataFrame(records)


def figure_election_window_profile(panel: pd.DataFrame, events: pd.DataFrame, path: Path, window: int = EVENT_WINDOW) -> Path:
    """Figure 2: raw mean CAPB (deviation from the country mean; year-on-year change) by year relative to a scheduled election.

    Descriptive only: the interval is a country-clustered 95% t interval of the event means; no model, no adjustment, no test.
    """
    summary = event_window_summary(panel, events, window)
    fig = _figure(7.4, 6.2)
    axes = fig.subplots(2, 1)
    fig.subplots_adjust(left=0.1, right=0.98, top=0.83, bottom=0.16, hspace=0.62)
    panels = (("deviation", "A. CAPB minus the country mean", "pp of potential GDP"), ("change", "B. Year-on-year change in CAPB", "pp of potential GDP"))
    for ax, (measure, heading, unit) in zip(axes, panels, strict=True):
        s = summary[summary["measure"] == measure]
        ax.axhline(0.0, color=MUTED, lw=1.0, ls="--", zorder=1)
        ax.axvline(0.0, color=ORANGE, lw=1.0, ls=":", zorder=1)
        ax.errorbar(s["k"], s["mean"], yerr=[s["mean"] - s["ci_lo"], s["ci_hi"] - s["mean"]], fmt="o-", color=BLUE, ecolor=BLUE, elinewidth=1.4, capsize=3, ms=5.5, lw=1.0, zorder=3)
        ax.set_xticks(s["k"])
        ax.set_xticklabels([f"{int(k):+d}\nn = {int(n)}" if k != 0 else f"0\nn = {int(n)}" for k, n in zip(s["k"], s["n"], strict=True)], fontsize=7.5)
        ax.set_ylabel(unit, fontsize=8, color=INK)
        ax.set_title(heading, loc="left", fontsize=9, color=INK)
        ax.yaxis.grid(True, color=GRID, lw=0.5, zorder=0)
        ax.set_axisbelow(True)
        _clean_axes(ax)
    axes[1].set_xlabel("Years relative to the scheduled-election year (k = calendar year - election year)\nn = number of election events with CAPB observed at that k", fontsize=7.5, color=INK)
    n_events = int(summary["n"].max()) if len(summary) else 0
    _title(fig, "CAPB around scheduled elections: raw means, descriptive only",
           f"Mean over scheduled-election events (up to {n_events} per k) with 95% intervals clustered by country (t, G - 1 d.f.). Raw and unadjusted: no controls, no year effects, "
           "no test. Dotted line: election year; events of one country within 6 years have overlapping windows.")
    _source(fig, "Scheduled elections: ETAD classification. CAPB: confirmatory sample, 1995-2021.", y=0.0)
    return _save(fig, path)


# ---------------------------------------------------------------------------------------------
# F3: Frisch-Waugh partial-association plot
# ---------------------------------------------------------------------------------------------
def fwl_residuals(design: Any, name: str = "W_S") -> tuple[np.ndarray, np.ndarray]:
    """Frisch-Waugh residuals ``(x_res, y_res)`` of regressor ``name`` and CAPB from an ``power.Design``.

    Both are residualised on the two-way fixed-effect basis ``design.q_fe`` (country and year) and on every other regressor of the M1
    design, so that the OLS slope of ``y_res`` on ``x_res`` equals the OLS-FE coefficient of ``name`` in the full model. The design is read, not modified.
    """
    x = np.asarray(design.x, float)
    y = np.asarray(design.y, float)
    q = np.asarray(design.q_fe, float)
    j = list(design.x_names).index(name)
    x_t = x - q @ (q.T @ x)
    y_t = y - q @ (q.T @ y)
    others = np.delete(x_t, j, axis=1)

    def resid(v: np.ndarray) -> np.ndarray:
        if others.shape[1] == 0:
            return v.copy()
        coef, *_ = np.linalg.lstsq(others, v, rcond=None)
        return v - others @ coef

    return resid(x_t[:, j]), resid(y_t)


def ols_slope(x: np.ndarray, y: np.ndarray) -> float:
    """Slope through the origin of residualised data: ``x'y / x'x`` (both are already centred by the fixed effects)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    return float(x @ y / (x @ x))


def binned_means(x: np.ndarray, y: np.ndarray, n_bins: int = N_BINS) -> pd.DataFrame:
    """Means of ``x`` and ``y`` within quantile bins of ``x`` (bins that cannot be formed because of ties are merged)."""
    frame = pd.DataFrame({"x": np.asarray(x, float), "y": np.asarray(y, float)})
    frame["bin"] = pd.qcut(frame["x"], n_bins, labels=False, duplicates="drop")
    out = frame.groupby("bin", observed=True).agg(x=("x", "mean"), y=("y", "mean"), n=("x", "size")).reset_index(drop=True)
    return out


def partial_association_inputs(design: Any, name: str = "W_S") -> dict:
    """Residuals, OLS-FE slope and binned means for figure 3 (pure function of the design)."""
    x_res, y_res = fwl_residuals(design, name)
    return {"x": x_res, "y": y_res, "slope": ols_slope(x_res, y_res), "bins": binned_means(x_res, y_res)}


def figure_partial_association(design: Any, headline: dict, path: Path) -> Path:
    """Figure 3: residualised CAPB against residualised W_S (OLS-FE, descriptive) with the OLS slope and a binned-mean overlay.

    The pre-registered V7 estimate of beta_S (``headline``) is quoted in the annotation; it differs from the OLS-FE slope because V7 is a
    weighted, AR(1)-corrected estimator.
    """
    inputs = partial_association_inputs(design)
    x, y, slope, bins = inputs["x"], inputs["y"], inputs["slope"], inputs["bins"]
    b = headline["targets"]["beta_S"]
    fig = _figure(7.0, 5.3)
    ax = fig.add_axes([0.11, 0.2, 0.86, 0.63])
    ax.axhline(0.0, color=MUTED, lw=0.8, zorder=0)
    ax.axvline(0.0, color=MUTED, lw=0.8, zorder=0)
    ax.scatter(x, y, s=11, color=MUTED, alpha=0.4, lw=0, zorder=1, label=f"Country-years (n = {len(x)})")
    grid = np.array([x.min(), x.max()])
    ax.plot(grid, slope * grid, color=VERMILLION, lw=2.0, zorder=3, label=f"OLS-FE slope = {slope:+.3f}")
    ax.plot(bins["x"], bins["y"], "o", ms=7, mfc="white", mec=BLUE, mew=1.8, zorder=4, label=f"Binned means ({len(bins)} quantile bins of residualised W_S)")
    lo, hi = np.quantile(y, [0.005, 0.995])
    pad = 0.1 * (hi - lo)
    ax.set_ylim(lo - pad, hi + pad)
    n_out = int(np.sum((y < lo - pad) | (y > hi + pad)))
    ax.set_xlabel("Residualised W_S (share of the year inside the 12-month pre-election window),\nnet of country and year effects and the other M1 terms", fontsize=7.5, color=INK)
    ax.set_ylabel("Residualised CAPB, pp of potential GDP", fontsize=8.5, color=INK)
    ax.yaxis.grid(True, color=GRID, lw=0.5, zorder=0)
    ax.set_axisbelow(True)
    _clean_axes(ax)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=3, fontsize=7.5, frameon=False, handletextpad=0.4, columnspacing=1.0)
    note = (f"Pre-registered V7 estimate: beta_S = {b['estimate']:+.3f} pp of potential GDP per unit of W_S, 95% bootstrap-t interval "
            f"[{b['ci_lo']:+.3f}, {b['ci_hi']:+.3f}], Holm p = {b['p_holm']:.3f}.")
    fig.text(0.01, 0.0, textwrap.fill(note, 112), ha="left", va="top", fontsize=8, color=INK, linespacing=1.3)
    _title(fig, "Partial association of CAPB with pre-election exposure (OLS-FE, descriptive)",
           "Frisch-Waugh plot: both axes are residuals after country and year fixed effects and the other M1 regressors, so the OLS slope is the "
           "fixed-effects coefficient of W_S. The V7 estimator weights and AR(1)-corrects, hence the small difference.")
    _source(fig, (f"{n_out} points outside the vertical range are not drawn (slope and means use all). " if n_out else "") + "Associations only.", y=-0.07)
    return _save(fig, path)


# ---------------------------------------------------------------------------------------------
# F4: inference ladder
# ---------------------------------------------------------------------------------------------
def figure_inference_ladder(robustness: dict, path: Path, sections: Sequence[str] = LADDER_SECTIONS) -> Path:
    """Figure 4: beta_S with its 95% interval under every inference specification of ``robustness.json`` (file order, not ranked).

    Intervals that exclude zero are vermillion and filled, the others blue and hollow (redundant coding). The title counts the specifications
    excluding zero (the V7 headline, shown first as a reference, is not counted).
    """
    rows, skipped = ladder_rows(robustness, sections)
    sesoi = sesoi_of(robustness)
    specs = [r for r in rows if r["kind"] == "spec"]
    n_excl = sum(r["excludes_zero"] for r in specs)
    layout: list[tuple[str, dict | None]] = [("row", rows[0]), ("gap", None)]
    groups = list(dict.fromkeys(r["group"] for r in specs))
    previous = None
    for r in specs:
        if len(groups) > 1 and r["group"] != previous:
            layout.append(("group", {"label": f"Group {r['group']}"}))
            previous = r["group"]
        layout.append(("row", r))
    top_in, bottom_in = 0.95, 1.4  # title block above, axis label / legend / source below
    height = 0.42 * len(layout) + top_in + bottom_in
    fig = _figure(7.4, height)
    ax = fig.add_axes([0.40, bottom_in / height, 0.58, 1 - (top_in + bottom_in) / height])
    axes_height_in = height - top_in - bottom_in
    total = len(layout)
    ax.axvspan(-sesoi, sesoi, color=SKY, alpha=0.22, lw=0, zorder=0)
    ax.axvline(0.0, color=MUTED, lw=1.0, ls="--", zorder=1)
    labels = {}
    for i, (kind, r) in enumerate(layout):
        y = total - 1 - i
        if kind == "gap":
            continue
        if kind == "group":
            labels[y] = (r["label"], True)
            continue
        labels[y] = ("\n".join(textwrap.wrap(r["label"], 46)), r["kind"] == "headline")
        colour = VERMILLION if r["excludes_zero"] else BLUE
        ax.plot([r["ci_lo"], r["ci_hi"]], [y, y], color=colour, lw=1.7, solid_capstyle="butt", zorder=2)
        ax.plot([r["estimate"]], [y], "D" if r["kind"] == "headline" else "o", ms=6.5, mfc=colour if r["excludes_zero"] else "white", mec=colour, mew=1.5, zorder=3)
    ax.set_yticks(list(labels))
    ax.set_yticklabels([labels[y][0] for y in labels], fontsize=7.5, color=INK, linespacing=1.2)
    for tick, y in zip(ax.get_yticklabels(), labels, strict=True):
        if labels[y][1]:
            tick.set_fontweight("bold")
    ax.set_ylim(-0.7, total - 0.3)
    ax.xaxis.grid(True, color=GRID, lw=0.5, zorder=0)
    ax.set_axisbelow(True)
    ax.set_xlabel("beta_S, pp of potential GDP\n(association with a full year of pre-election exposure to a scheduled election)", fontsize=8, color=INK)
    _clean_axes(ax, left=False)
    ax.tick_params(axis="y", length=0)
    handles = [Line2D([], [], color=VERMILLION, marker="o", ms=6, lw=1.6, label="95% interval excludes zero"),
               Line2D([], [], color=BLUE, marker="o", ms=6, mfc="white", lw=1.6, label="95% interval includes zero"),
               Line2D([], [], color=INK, marker="D", ms=5, lw=0, mfc="white", label="V7 headline (reference)"),
               Patch(facecolor=SKY, alpha=0.4, label=f"±SESOI band (±{sesoi:g} pp)")]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.35, -0.5 / axes_height_in), ncol=2, fontsize=7.5, frameon=False)
    extra = f"{skipped} failed specification(s) not shown. " if skipped else ""
    _title(fig, f"beta_S under {len(specs)} inference specifications: {n_excl} of {len(specs)} 95% intervals exclude zero",
           "Specifications are listed in the order of the specification list and are neither ranked nor selected; they share data and are not independent. "
           "Exclusion of zero is judged on the 95% interval; a null-imposed bootstrap p-value can differ near the boundary.")
    _source(fig, extra + "Associations only.", y=0.0)
    return _save(fig, path)


# ---------------------------------------------------------------------------------------------
# F5: country x year heatmap
# ---------------------------------------------------------------------------------------------
def load_iso2_map(path: Path = COUNTRIES_CSV) -> dict[str, str]:
    """Eurostat code -> ISO 3166-1 alpha-2 code (Greece: EL -> GR); an empty map if the crosswalk is missing."""
    if not Path(path).exists():
        return {}
    frame = pd.read_csv(path, usecols=["eurostat_code", "iso2"])
    return dict(zip(frame["eurostat_code"], frame["iso2"], strict=True))


def heatmap_matrix(panel: pd.DataFrame, iso2: dict[str, str] | None = None) -> pd.DataFrame:
    """CAPB matrix: rows = countries sorted alphabetically by ISO-2 code (never by outcome), columns = years (NaN where missing)."""
    mapping = iso2 or {}
    wide = panel.pivot(index="eurostat_code", columns="year", values="capb")
    wide.index = [mapping.get(code, code) for code in wide.index]
    return wide.sort_index().sort_index(axis=1)


def figure_capb_heatmap(panel: pd.DataFrame, events: pd.DataFrame, path: Path, iso2: dict[str, str] | None = None) -> Path:
    """Figure 5: CAPB by country (rows, alphabetical by ISO code) and year; diverging scale centred at 0; scheduled-election years dotted."""
    mapping = load_iso2_map() if iso2 is None else iso2
    matrix = heatmap_matrix(panel, mapping)
    values = matrix.to_numpy(float)
    limit = float(np.nanpercentile(np.abs(values), HEATMAP_CLIP_PCT))
    cmap = colormaps["RdBu"].copy()
    cmap.set_bad("#d9d9d9")
    fig = _figure(7.4, 7.6)
    ax = fig.add_axes([0.07, 0.17, 0.80, 0.70])
    image = ax.imshow(np.ma.masked_invalid(values), cmap=cmap, norm=TwoSlopeNorm(vmin=-limit, vcenter=0.0, vmax=limit), aspect="auto", interpolation="nearest")
    years = list(matrix.columns)
    ax.set_xticks(range(0, len(years), 2))
    ax.set_xticklabels([str(years[i]) for i in range(0, len(years), 2)], rotation=90, fontsize=7.5)
    ax.set_yticks(range(matrix.shape[0]))
    ax.set_yticklabels(list(matrix.index), fontsize=7.5)
    ax.set_xticks(np.arange(-0.5, len(years)), minor=True)
    ax.set_yticks(np.arange(-0.5, matrix.shape[0]), minor=True)
    ax.grid(which="minor", color="white", linewidth=0.5)
    ax.tick_params(which="minor", length=0)
    ax.tick_params(which="major", length=2)
    for side in ax.spines.values():
        side.set_visible(False)
    row_of = {code: i for i, code in enumerate(matrix.index)}
    col_of = {year: j for j, year in enumerate(years)}
    ev = events[["eurostat_code", "year"]].drop_duplicates()
    cells = [(col_of[y], row_of[mapping.get(c, c)]) for c, y in zip(ev["eurostat_code"], ev["year"], strict=True) if y in col_of and mapping.get(c, c) in row_of]
    if cells:
        ax.scatter([c[0] for c in cells], [c[1] for c in cells], s=9, color="black", edgecolors="white", linewidths=0.6, zorder=3)
    ax.set_xlabel("Year", fontsize=8.5, color=INK)
    ax.set_ylabel("Country (ISO 3166-1 alpha-2, alphabetical)", fontsize=8.5, color=INK)
    cax = fig.add_axes([0.89, 0.17, 0.02, 0.70])
    bar = fig.colorbar(image, cax=cax, extend="both")
    bar.set_label("CAPB, pp of potential GDP (positive = surplus)", fontsize=8, color=INK)
    bar.ax.tick_params(labelsize=7.5)
    handles = [Line2D([], [], marker="o", ls="", mfc="black", mec="white", ms=5, label="Scheduled-election year"), Patch(facecolor="#d9d9d9", label="CAPB not in the sample")]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2, fontsize=7.5, frameon=False)
    _title(fig, "Cyclically adjusted primary balance by country and year, with scheduled-election years",
           f"Colour scale symmetric around 0 and clipped at the {HEATMAP_CLIP_PCT:g}th percentile of |CAPB| (±{limit:.1f} pp); more extreme cells take the end colour. Descriptive.")
    _source(fig, "CAPB: AMECO UBLGBP (confirmatory sample).", y=0.035)
    return _save(fig, path)


# ---------------------------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    """Build all five figures from the frozen results and the (tag-guarded) real panel."""
    import matplotlib

    matplotlib.use("Agg")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, default=FIGURES_DIR, help="output folder (default reports/figures)")
    args = parser.parse_args(argv)
    src = Path(__file__).resolve().parents[1]
    for sub in ("models/py", "evaluate", "normalize", "features"):
        sys.path.insert(0, str(src / sub))
    import m1  # noqa: E402  (tag guard, hash-checked loader)
    import power_variants as pv  # noqa: E402  (the M1 / V7 design builder)

    headline, robustness = load_json(HEADLINE_JSON), load_json(ROBUSTNESS_JSON)
    out = Path(args.out_dir)
    try:
        extract, _ = m1.load_real_panel()
    except m1.PreregistrationTagMissing as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 1
    events = load_scheduled_events()
    design = pv.build_variant_design(extract, "M1", era=True, control_names=())
    paths = [
        figure_headline_estimates(headline, out / FIGURE_NAMES["f1"]),
        figure_election_window_profile(extract, events, out / FIGURE_NAMES["f2"]),
        figure_partial_association(design, headline, out / FIGURE_NAMES["f3"]),
        figure_inference_ladder(robustness, out / FIGURE_NAMES["f4"]),
        figure_capb_heatmap(extract, events, out / FIGURE_NAMES["f5"]),
    ]
    for path in paths:
        try:
            print(f"written {path.relative_to(PROJECT_ROOT).as_posix()}")
        except ValueError:
            print(f"written {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
