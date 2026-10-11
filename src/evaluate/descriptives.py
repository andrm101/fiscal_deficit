"""Tier-1 descriptives for the Fiscal_Deficit capstone: UNCONDITIONAL on elections.

Freeze rule
-----------
The pre-registration freeze (tag ``preregistration-v1``) has not happened. Until it does, no statistic, table or
figure may relate the outcome (CAPB or any ``sec_`` fiscal outcome) to any election variable (``W_S``, ``W_E``,
``W_D``, ``W_U``, ``Post``, the election dates, the scheduled/early/delayed/unclassified classes). Every routine in
this module therefore takes its inputs through :func:`select_columns`, which calls
:func:`assert_no_exposure_with_outcome` and raises :class:`FreezeRuleViolation` if the requested columns mix an
outcome column with an exposure column. The election calendar is described on its own (counts, shares, distribution
of exposure values): that part reads only outcome-free columns. The two exposure-completeness flags
(``exposure_complete_cv``, ``exposure_complete_etad``) record right-censoring of the election data, not exposure
values, and are allowed next to outcome columns (coverage heatmap).

Conventions
-----------
* SDs of variance decompositions use the population form (RSS / N) as in Appendix D; pooled SDs use N - 1.
* Randomness: only :func:`corrected_rho_indirect` (simulation, ``numpy.random.default_rng(SEED)`` with ``SEED = 42``).
* Figures: PNG at 300 dpi in ``reports/figures``, title, axis labels with units, legend, source line, Okabe-Ito
  colour-blind-safe palette.
* Run ``python src/evaluate/descriptives.py`` after ``python src/features/panel.py``; it writes
  ``reports/tier1_descriptives.md`` and the figures only.
"""
from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402
from scipy import optimize, stats  # noqa: E402

_SRC = Path(__file__).resolve().parents[1]
for _sub in ("normalize", "evaluate", "features"):
    sys.path.insert(0, str(_SRC / _sub))
import countries  # noqa: E402
import sample  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLD_PARQUET = PROJECT_ROOT / "data" / "processed" / "gold" / "panel_country_year.parquet"
CALENDAR_CSV = PROJECT_ROOT / "data" / "interim" / "election_calendar_eu27.csv"
EXPOSURE_CSV = PROJECT_ROOT / "data" / "interim" / "exposure_eu27.csv"
FIG_DIR = PROJECT_ROOT / "reports" / "figures"
REPORT_PATH = PROJECT_ROOT / "reports" / "tier1_descriptives.md"

SEED = 42  # persistence simulation only
DPI = 300  # minimum for publication figures (CLAUDE.md)
N_SIM = 1_000  # simulated panels for the indirect-inference correction (same order as Gate 3b)
TOP_RESIDUALS = 10  # number of largest absolute two-way residual cells listed
WINDOW = (1995, 2021)  # gold panel years
ELECTION_RELEVANT = (pd.Timestamp("1994-01-01"), pd.Timestamp("2022-12-31"))  # elections that can touch exposure in 1995-2021
IRELAND_OUTLIER = ("IE", 2010)
GATE3_PERSISTENCE = {"raw pooled": 0.594, "country-standardised": 0.562, "Nickell analytic": 0.627, "simulation-corrected": 0.694}
GATE3A_TWO_WAY_SD_PP = 1.246  # reports/gate3_calendar_and_sample.md section 7
VIF_FLAG = 5.0  # CLAUDE.md: VIF > 5 requires discussion
CRISES = [(2008, 2009, "2008-09 financial crisis"), (2010, 2012, "2010-12 euro-area debt crisis"), (2020, 2021, "2020-21 pandemic")]

# Okabe-Ito colour-blind-safe palette
BLACK, ORANGE, SKY, GREEN, YELLOW, BLUE, VERMILLION, PURPLE = "#000000", "#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7"
SRC_AMECO = "Source: European Commission, AMECO Spring 2026 (UBLGBP); Eurostat demo_pjanind; author's calculations."
SRC_SECONDARY = "Source: Eurostat gov_10a_main (% of GDP); European Commission, AMECO Spring 2026 (UBLGBP, UBLGIE, UBLGCP); author's calculations."
SRC_CALENDAR = "Source: ETAD v1.0.0 and ParlGov 2024 (stable) election dates, author's classification (src/normalize/elections.py)."

# ---------------------------------------------------------------------------------------------
# Freeze-rule guard
# ---------------------------------------------------------------------------------------------
EXPOSURE_NAMES = {
    "w_s", "w_e", "w_d", "w_u", "post", "w_s_gf", "w_e_gf", "w_d_gf", "w_u_gf", "post_gf", "w_s_plus_u", "touches_unclassified_or_delayed",
    "date_used", "class_primary", "class_gap", "class_gapfill", "class_rule", "n_elections_held", "sche_date", "dif_days", "timing1", "timing2",
    "etad_date", "parlgov_date", "scheduled", "early", "delayed", "unclassified",
}
EXPOSURE_PREFIXES = ("w_", "post", "election", "exposure", "n_elections")
COMPLETENESS_FLAGS = {"exposure_complete_cv", "exposure_complete_etad"}  # right-censoring status, not exposure values
OUTCOME_PREFIXES = ("capb", "sec_", "delta_capb", "primary_balance", "cyclical")


class FreezeRuleViolation(ValueError):
    """Raised when a statistic would combine an outcome column with an election-exposure column before the freeze."""


def is_exposure_column(name: str) -> bool:
    """True for election-exposure or election-calendar columns (completeness flags excluded)."""
    low = str(name).lower()
    if low in COMPLETENESS_FLAGS:
        return False
    return low in EXPOSURE_NAMES or low.startswith(EXPOSURE_PREFIXES)


def is_outcome_column(name: str) -> bool:
    """True for CAPB and every secondary fiscal outcome (including derived ``capb_*`` columns)."""
    return str(name).lower().startswith(OUTCOME_PREFIXES)


def assert_no_exposure_with_outcome(columns: Iterable[str]) -> None:
    """Raise :class:`FreezeRuleViolation` if ``columns`` contain an outcome column and an exposure column."""
    names = [str(c) for c in columns]
    outcomes = sorted(c for c in names if is_outcome_column(c))
    exposures = sorted(c for c in names if is_exposure_column(c))
    if outcomes and exposures:
        raise FreezeRuleViolation(
            f"freeze rule: outcome column(s) {outcomes} may not be combined with exposure column(s) {exposures} before preregistration-v1"
        )


def select_columns(frame: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    """Guarded column selection: every descriptive routine reads its inputs through this function."""
    cols = list(columns)
    assert_no_exposure_with_outcome(cols)
    return frame[cols]


# ---------------------------------------------------------------------------------------------
# Loading and generic helpers
# ---------------------------------------------------------------------------------------------
def load_panel(path: Path = GOLD_PARQUET) -> pd.DataFrame:
    """Gold panel from Parquet; if the file is missing the panel is assembled in memory (nothing is written)."""
    if path.exists():
        try:
            return pd.read_parquet(path)
        except OSError:  # pyarrow occasionally rejects size statistics when reading with threads; retry single-threaded
            import pyarrow.parquet as pq

            return pq.read_table(path, use_threads=False).to_pandas()
    import panel as panel_module  # noqa: E402  (lazy: only needed when the gold file is missing)

    return panel_module.build_gold_panel().panel


def md_table(frame: pd.DataFrame, floatfmt: str = ".2f") -> str:
    """GitHub pipe table; floats use ``floatfmt``, missing cells are empty."""
    cols = [str(c) for c in frame.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for row in frame.itertuples(index=False, name=None):
        cells = []
        for v in row:
            if isinstance(v, (float, np.floating)):
                cells.append("" if np.isnan(v) else format(v, floatfmt))
            elif v is None or (not isinstance(v, str) and pd.isna(v)):
                cells.append("")
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def design_matrix(frame: pd.DataFrame) -> np.ndarray:
    """Country dummies plus year dummies (first year dropped): the two-way fixed-effects design."""
    c = pd.get_dummies(frame["eurostat_code"], dtype=float).to_numpy()
    y = pd.get_dummies(frame["year"], dtype=float).to_numpy()[:, 1:]
    return np.column_stack([c, y])


def two_way_demean(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Residuals of each column on country and year effects, fitted on the rows of ``frame`` (unbalanced panels allowed)."""
    q, _ = np.linalg.qr(design_matrix(frame))
    values = frame[columns].to_numpy(dtype=float)
    resid = values - q @ (q.T @ values)
    return pd.DataFrame(resid, index=frame.index, columns=columns)


def ageing_groups() -> dict[str, str]:
    """EU-15 members of 1995 (without the UK) versus accession members of 2004 or later; from ``config/countries.csv``."""
    table = countries.load_countries()
    return {c: ("EU-15 (accession 1995 or earlier)" if int(y) <= 1995 else "Accession 2004 or later") for c, y in zip(table["eurostat_code"], table["eu_accession_year"], strict=True)}


# ---------------------------------------------------------------------------------------------
# (a) Coverage and missingness
# ---------------------------------------------------------------------------------------------
COVERAGE_LABELS = ["all three available", "capb missing", "olddep1_lag missing", "capb and olddep1_lag missing", "exposure incomplete"]


def coverage_matrix(panel: pd.DataFrame) -> pd.DataFrame:
    """Country x year codes of joint availability of ``capb``, ``olddep1_lag`` and ``exposure_complete_cv`` (see ``COVERAGE_LABELS``)."""
    data = select_columns(panel, ["eurostat_code", "year", "capb", "olddep1_lag", "exposure_complete_cv"])
    code = np.zeros(len(data), dtype=int)
    no_capb, no_mod = data["capb"].isna().to_numpy(), data["olddep1_lag"].isna().to_numpy()
    code[no_capb & ~no_mod], code[~no_capb & no_mod], code[no_capb & no_mod] = 1, 2, 3
    code[(~data["exposure_complete_cv"].astype(bool)).to_numpy()] = 4
    return data.assign(code=code).pivot(index="eurostat_code", columns="year", values="code")


def missing_cells_table(panel: pd.DataFrame) -> pd.DataFrame:
    """Country-years without joint availability, grouped by country and cause, with years as runs."""
    data = select_columns(panel, ["eurostat_code", "year", "capb", "olddep1_lag", "exposure_complete_cv"])
    rows = []
    for row in data.itertuples(index=False):
        causes = []
        if pd.isna(row.capb):
            causes.append("capb absent from AMECO UBLGBP (series starts later)")
        if pd.isna(row.olddep1_lag):
            causes.append("OLDDEP1 at t-1 empty in Eurostat (flag e)")
        if not row.exposure_complete_cv:
            causes.append("election data right-censored")
        if causes:
            rows.append({"eurostat_code": row.eurostat_code, "year": int(row.year), "cause": "; ".join(causes)})
    if not rows:
        return pd.DataFrame(columns=["eurostat_code", "years", "n", "cause"])
    table = pd.DataFrame(rows)
    out = []
    for (code, cause), sub in table.groupby(["eurostat_code", "cause"]):
        years = sorted(sub["year"])
        runs, start, prev = [], years[0], years[0]
        for y in years[1:]:
            if y != prev + 1:
                runs.append((start, prev))
                start = y
            prev = y
        runs.append((start, prev))
        out.append({"eurostat_code": code, "years": ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in runs), "n": len(years), "cause": cause})
    return pd.DataFrame(out)


# ---------------------------------------------------------------------------------------------
# (b) CAPB distribution and persistence
# ---------------------------------------------------------------------------------------------
def capb_summary(extract: pd.DataFrame) -> dict[str, float]:
    """Pooled mean and SD, within-country SD, between-country SD and two-way SD of CAPB (pp of potential GDP)."""
    data = select_columns(extract, ["eurostat_code", "year", "capb"])
    g1 = sample.g1_statistics(data, "capb")
    country_mean = data.groupby("eurostat_code")["capb"].transform("mean")
    within = float(np.sqrt(((data["capb"] - country_mean) ** 2).mean()))
    return {
        "n_obs": int(g1["n_obs"]), "n_countries": int(g1["n_countries"]), "mean": float(data["capb"].mean()), "median": float(data["capb"].median()),
        "sd_pooled_ddof1": float(data["capb"].std(ddof=1)), "sd_pooled_pop": float(g1["total_sd"]), "sd_within_country": within,
        "sd_between_country": float(g1["sd_country_means_pp"]), "sd_two_way": float(g1["sd_two_way_demeaned_pp"]),
        "sd_two_way_df_corrected": float(g1["sd_two_way_demeaned_df_corrected_pp"]),
        "share_between": float(g1["share_between_country"]), "share_common_year": float(g1["share_common_year_after_country"]),
        "share_two_way_residual": float(g1["share_two_way_residual"]),
        "min": float(data["capb"].min()), "max": float(data["capb"].max()), "n_negative": int((data["capb"] < 0).sum()),
        "skewness": float(stats.skew(data["capb"])), "excess_kurtosis": float(stats.kurtosis(data["capb"])),
    }


def residual_cells(extract: pd.DataFrame, k: int = TOP_RESIDUALS) -> pd.DataFrame:
    """The ``k`` largest absolute residuals of CAPB on country and year effects ONLY (no election variable)."""
    data = select_columns(extract, ["eurostat_code", "year", "capb"]).reset_index(drop=True)
    resid = two_way_demean(data, ["capb"])["capb"]
    out = data.assign(capb_two_way_residual=resid, abs_residual=resid.abs()).sort_values("abs_residual", ascending=False).head(k)
    return out.drop(columns="abs_residual").reset_index(drop=True)


def _pairs(codes: np.ndarray, years: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Positions of consecutive-year pairs ``(t, t-1)`` within a country (rows sorted by country, year)."""
    ok = (codes[1:] == codes[:-1]) & (years[1:] - years[:-1] == 1)
    idx = np.arange(1, len(codes))[ok]
    return idx, idx - 1


def pooled_ar1(resid: np.ndarray, codes: np.ndarray, years: np.ndarray, standardise: bool) -> np.ndarray:
    """Pooled AR(1) coefficient ``sum e_t e_{t-1} / sum e_{t-1}^2`` over consecutive-year pairs; columns are independent series.

    ``standardise`` divides each country's residuals by their own SD first (as in Gate 3b).
    """
    e = np.atleast_2d(resid.T).T if resid.ndim == 1 else resid
    cur, prev = _pairs(codes, years)
    if standardise:
        starts = np.flatnonzero(np.r_[True, codes[1:] != codes[:-1]])
        counts = np.diff(np.r_[starts, len(codes)])
        sd = np.sqrt(np.add.reduceat(e**2, starts, axis=0) / counts[:, None])
        e = e / np.repeat(sd, counts, axis=0)
    return (e[cur] * e[prev]).sum(axis=0) / (e[prev] ** 2).sum(axis=0)


def _simulate_ar1(counts: np.ndarray, rho: float, shocks: np.ndarray) -> np.ndarray:
    """Stationary unit-variance AR(1) noise on contiguous country blocks of the given lengths, from standard-normal ``shocks``."""
    out = np.empty_like(shocks)
    scale = np.sqrt(1.0 - rho**2)
    pos = 0
    for length in counts:
        out[pos] = shocks[pos]
        for step in range(1, length):
            out[pos + step] = rho * out[pos + step - 1] + scale * shocks[pos + step]
        pos += length
    return out


def corrected_rho_indirect(extract: pd.DataFrame, observed: float, n_sim: int = N_SIM, seed: int = SEED) -> float:
    """Indirect-inference correction of the country-standardised pooled AR(1) of the two-way residual.

    Finds ``rho`` such that the same estimator applied to simulated AR(1) noise on the real sample geometry (country
    blocks, year effects projected out) averages ``observed``. Common random numbers (one shock matrix drawn from
    ``default_rng(seed)``) keep the objective smooth; the root is bracketed on [0, 0.95] with Brent's method.
    """
    data = select_columns(extract, ["eurostat_code", "year", "capb"]).sort_values(["eurostat_code", "year"]).reset_index(drop=True)
    codes, years = data["eurostat_code"].to_numpy(), data["year"].to_numpy()
    counts = data.groupby("eurostat_code", sort=True).size().to_numpy()
    if not (np.diff(years)[codes[1:] == codes[:-1]] == 1).all():
        raise ValueError("country blocks must be contiguous in years")
    q, _ = np.linalg.qr(design_matrix(data))
    shocks = np.random.default_rng(seed).standard_normal((len(data), n_sim))

    def gap(rho: float) -> float:
        noise = _simulate_ar1(counts, rho, shocks)
        resid = noise - q @ (q.T @ noise)
        return float(pooled_ar1(resid, codes, years, True).mean() - observed)

    return float(optimize.brentq(gap, 0.0, 0.95, xtol=1e-4))


def persistence_table(extract: pd.DataFrame) -> dict[str, float]:
    """AR(1) persistence of the two-way (country + year) residual of CAPB: raw, standardised, analytic and simulation corrections."""
    data = select_columns(extract, ["eurostat_code", "year", "capb"]).sort_values(["eurostat_code", "year"]).reset_index(drop=True)
    resid = two_way_demean(data, ["capb"])["capb"].to_numpy()
    codes, years = data["eurostat_code"].to_numpy(), data["year"].to_numpy()
    raw = float(pooled_ar1(resid, codes, years, False)[0])
    standardised = float(pooled_ar1(resid, codes, years, True)[0])
    t_obs = float(data.groupby("eurostat_code").size().mean())
    import power  # noqa: E402  (nickell_corrected_rho only; lazy so that importing this module stays light)

    return {
        "raw_pooled": raw, "country_standardised": standardised, "mean_obs_per_country": t_obs,
        "nickell_analytic": float(power.nickell_corrected_rho(standardised, t_obs)),
        "simulation_corrected": corrected_rho_indirect(data, standardised),
        "n_pairs": int(len(_pairs(codes, years)[0])),
    }


def capb_by_year(extract: pd.DataFrame) -> pd.DataFrame:
    """Cross-country median and interquartile range of CAPB by year (pp of potential GDP)."""
    data = select_columns(extract, ["year", "capb"])
    grouped = data.groupby("year")["capb"]
    return pd.DataFrame({"n": grouped.size(), "q25": grouped.quantile(0.25), "median": grouped.median(), "q75": grouped.quantile(0.75)}).reset_index()


# ---------------------------------------------------------------------------------------------
# (d) Ageing
# ---------------------------------------------------------------------------------------------
def ageing_summary(extract: pd.DataFrame) -> dict[str, float | str]:
    """Variance shares and two-way SD of ``olddep1_lag`` (Appendix D / Gate 3a definitions) on the confirmatory extract."""
    data = select_columns(extract, ["eurostat_code", "year", "olddep1_lag"])
    return sample.g1_statistics(data, "olddep1_lag")


def ageing_dispersion(extract: pd.DataFrame, years: tuple[int, int] = (1995, 2021)) -> pd.DataFrame:
    """Cross-country dispersion of ``olddep1_lag`` in two years, for all available countries and for the balanced subset."""
    data = select_columns(extract, ["eurostat_code", "year", "olddep1_lag"])
    balanced = set(sample.balanced_subset(data)["eurostat_code"])
    rows = []
    for label, subset in (("all countries available in the year", data), (f"balanced subset ({len(balanced)} countries)", data[data["eurostat_code"].isin(balanced)])):
        for year in years:
            x = subset.loc[subset["year"] == year, "olddep1_lag"]
            rows.append({"countries": label, "year": year, "n": len(x), "mean": x.mean(), "SD": x.std(ddof=1), "min": x.min(), "p25": x.quantile(0.25), "median": x.median(), "p75": x.quantile(0.75), "max": x.max(), "range": x.max() - x.min()})
    return pd.DataFrame(rows)


def ageing_group_table(extract: pd.DataFrame, years: tuple[int, int] = (1995, 2021)) -> pd.DataFrame:
    """Median ``olddep1_lag`` by group and year."""
    data = select_columns(extract, ["eurostat_code", "year", "olddep1_lag"])
    groups = ageing_groups()
    data = data.assign(group=data["eurostat_code"].map(groups))
    rows = []
    for group, sub in data.groupby("group"):
        row = {"group": group, "countries": sub["eurostat_code"].nunique()}
        for year in years:
            x = sub.loc[sub["year"] == year, "olddep1_lag"]
            row[f"median {year}"], row[f"n {year}"] = x.median(), len(x)
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------------------------
# (e) Election calendar on its own (outcome-free)
# ---------------------------------------------------------------------------------------------
CLASS_ORDER = ["scheduled", "early", "delayed", "unclassified"]
EXPOSURE_VARIABLES = ["W_S", "W_E", "W_D", "W_U", "Post"]


def load_calendar(path: Path = CALENDAR_CSV) -> pd.DataFrame:
    """Election calendar (calendar rows with ``in_calendar``) with a parsed ``date_used``."""
    cal = pd.read_csv(path)
    cal = cal[cal["in_calendar"].astype(bool)].copy()
    cal["date_used"] = pd.to_datetime(cal["date_used"])
    return cal


def calendar_by_year(cal: pd.DataFrame) -> pd.DataFrame:
    """Elections per calendar year of the election date, by ETAD-based class."""
    data = select_columns(cal, ["date_used", "class_primary"])
    table = data.assign(year=data["date_used"].dt.year).groupby(["year", "class_primary"]).size().unstack(fill_value=0)
    table = table.reindex(columns=CLASS_ORDER, fill_value=0)
    table["total"] = table.sum(axis=1)
    return table.reset_index()


def calendar_by_country(cal: pd.DataFrame, relevant: tuple[pd.Timestamp, pd.Timestamp] = ELECTION_RELEVANT) -> pd.DataFrame:
    """Elections per country by class among elections that can touch exposure in 1995-2021 (dated 1994-01-01 to 2022-12-31)."""
    data = select_columns(cal, ["eurostat_code", "date_used", "class_primary"])
    data = data[data["date_used"].between(*relevant)]
    table = data.groupby(["eurostat_code", "class_primary"]).size().unstack(fill_value=0).reindex(columns=CLASS_ORDER, fill_value=0)
    table["total"] = table.sum(axis=1)
    return table.reset_index().sort_values(["scheduled", "eurostat_code"]).reset_index(drop=True)


def unclassified_elections(cal: pd.DataFrame) -> pd.DataFrame:
    """Unclassified elections dated 1994 or later (the ones that can touch the 1995-2021 panel), with the rule that left them unclassified."""
    data = select_columns(cal, ["eurostat_code", "date_used", "class_primary", "class_rule", "class_gap"])
    data = data[(data["class_primary"] == "unclassified") & (data["date_used"] >= pd.Timestamp("1994-01-01"))]
    data = data.assign(touches_1995_2021=data["date_used"] <= ELECTION_RELEVANT[1])
    return data.sort_values(["eurostat_code", "date_used"]).reset_index(drop=True)


def exposure_distribution(exposure: pd.DataFrame, keys: pd.DataFrame | None = None) -> pd.DataFrame:
    """Distribution of each exposure variable over 1995-2021 country-years (optionally restricted to the ``keys`` of the extract)."""
    data = select_columns(exposure, ["eurostat_code", "year"] + EXPOSURE_VARIABLES)
    data = data[data["year"].between(*WINDOW)]
    if keys is not None:
        data = data.merge(keys[["eurostat_code", "year"]], on=["eurostat_code", "year"], how="inner")
    rows = []
    for var in EXPOSURE_VARIABLES:
        x = data[var]
        pos = x[x > 0]
        rows.append({"variable": var, "n country-years": len(x), "share > 0 (%)": 100 * (x > 0).mean(), "mean": x.mean(), "SD": x.std(ddof=1), "median": x.median(), "p90": x.quantile(0.9), "max": x.max(), "mean if > 0": pos.mean() if len(pos) else np.nan, "share = 1 (%)": 100 * (x >= 1.0 - 1e-9).mean()})
    return pd.DataFrame(rows)


def any_positive_share(exposure: pd.DataFrame, keys: pd.DataFrame | None = None) -> dict[str, float]:
    """Share of country-years with positive exposure of any pre-election class, and with a positive ``Post``."""
    data = select_columns(exposure, ["eurostat_code", "year"] + EXPOSURE_VARIABLES)
    data = data[data["year"].between(*WINDOW)]
    if keys is not None:
        data = data.merge(keys[["eurostat_code", "year"]], on=["eurostat_code", "year"], how="inner")
    pre = (data[["W_S", "W_E", "W_D", "W_U"]] > 0).any(axis=1)
    return {"n": len(data), "any_pre_window_%": 100 * float(pre.mean()), "post_%": 100 * float((data["Post"] > 0).mean()), "any_pre_or_post_%": 100 * float((pre | (data["Post"] > 0)).mean())}


# ---------------------------------------------------------------------------------------------
# (f) Secondary aggregates and the fiscal-balance decomposition
# ---------------------------------------------------------------------------------------------
SECONDARY_SERIES = {
    "sec_revenue": "Revenue (TR)", "sec_total_expenditure": "Total expenditure (TE)", "sec_interest_d41pay": "Interest paid (D41PAY)",
    "sec_social_benefits_d62": "Social benefits other than in kind (D62PAY)", "sec_social_transfers_kind_d632": "Social transfers in kind (D632PAY)",
}


def secondary_medians(panel: pd.DataFrame) -> pd.DataFrame:
    """Cross-country median by year of the secondary aggregates (% of GDP) over the 729-row window panel."""
    data = select_columns(panel, ["eurostat_code", "year"] + list(SECONDARY_SERIES))
    out = data.groupby("year")[list(SECONDARY_SERIES)].median()
    out["n_countries"] = data.groupby("year")["sec_revenue"].count()
    return out.reset_index()


def illustrative_countries(panel: pd.DataFrame) -> pd.DataFrame:
    """Rule fixed in advance: rank countries by the mean absolute cyclical component (UBLGCP, pp of potential GDP) over 1995-2021;
    pick the largest, the smallest and the (lower) median country. Ties break by country code. Nothing election-related is used.
    """
    data = select_columns(panel, ["eurostat_code", "year", "sec_cyclical_component"])
    table = data.dropna(subset=["sec_cyclical_component"]).assign(abs_cyc=lambda d: d["sec_cyclical_component"].abs()).groupby("eurostat_code")["abs_cyc"].agg(["mean", "size"])
    table = table.rename(columns={"mean": "mean_abs_cyclical_pp", "size": "n_years"}).reset_index().sort_values(["mean_abs_cyclical_pp", "eurostat_code"]).reset_index(drop=True)
    picks = {"smallest": 0, "median": (len(table) - 1) // 2, "largest": len(table) - 1}
    table["pick"] = ""
    for label, pos in picks.items():
        table.loc[pos, "pick"] = label
    return table


# ---------------------------------------------------------------------------------------------
# (g) Within correlations and VIF
# ---------------------------------------------------------------------------------------------
CORR_VARIABLES = ["capb", "outgap_lag", "debt_gdp_lag", "ig_diff_lag", "olddep1_lag"]
VIF_SETS = {
    "continuous regressors (olddep1_lag, outgap_lag, debt_gdp_lag, ig_diff_lag)": ["olddep1_lag", "outgap_lag", "debt_gdp_lag", "ig_diff_lag"],
    "registered robustness model (olddep1_lag, outgap_lag, euro_member)": ["olddep1_lag", "outgap_lag", "euro_member"],
}


def within_correlations(extract: pd.DataFrame, variables: list[str] = CORR_VARIABLES) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Two-way-demeaned (within) Pearson correlations by pair, each on its own pairwise-complete rows.

    Returns ``(matrix of r, long table with n and a naive 95% Fisher-z interval)``. The interval ignores clustering and
    the loss of degrees of freedom from the fixed effects, so it is optimistic; it is a description, not a test.
    """
    data = select_columns(extract, ["eurostat_code", "year"] + variables)
    matrix = pd.DataFrame(np.eye(len(variables)), index=variables, columns=variables)
    rows = []
    for i, a in enumerate(variables):
        for b in variables[i + 1:]:
            pair = data.dropna(subset=[a, b]).reset_index(drop=True)
            resid = two_way_demean(pair, [a, b])
            r = float(np.corrcoef(resid[a], resid[b])[0, 1])
            n = len(pair)
            z, se = np.arctanh(r), 1.0 / np.sqrt(n - 3)
            rows.append({"variable A": a, "variable B": b, "n": n, "r (within)": r, "95% CI low": float(np.tanh(z - 1.96 * se)), "95% CI high": float(np.tanh(z + 1.96 * se))})
            matrix.loc[a, b] = matrix.loc[b, a] = r
    return matrix, pd.DataFrame(rows)


def within_vif(extract: pd.DataFrame, regressors: list[str]) -> pd.DataFrame:
    """VIF of two-way-demeaned regressors (diagonal of the inverse correlation matrix) on the complete cases; exposure terms excluded."""
    data = select_columns(extract, ["eurostat_code", "year"] + regressors).dropna().reset_index(drop=True)
    resid = two_way_demean(data, regressors)
    vif = np.diag(np.linalg.inv(np.corrcoef(resid.to_numpy().T)))
    return pd.DataFrame({"regressor": regressors, "VIF (within)": vif, "flag": ["VIF > 5" if v > VIF_FLAG else "" for v in vif], "n": len(data)})


# ---------------------------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------------------------
def _finish(fig: plt.Figure, name: str, source: str, source_y: float = -0.005) -> Path:
    """Add the source line, save at ``DPI`` and close."""
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.text(0.01, source_y, source, ha="left", va="top", fontsize=7, color="#333333")
    path = FIG_DIR / name
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    return path


def _crisis_bands(ax: plt.Axes, label: bool = True) -> None:
    shades = ["#EEEEEE", "#DDDDDD", "#CCCCCC"]
    for (a, b, text), shade in zip(CRISES, shades, strict=True):
        ax.axvspan(a - 0.5, b + 0.5, color=shade, alpha=0.7, label=text if label else None, zorder=0)


def fig_coverage(matrix: pd.DataFrame) -> Path:
    """Country x year heatmap of joint availability."""
    colours = ["#FFFFFF", VERMILLION, SKY, PURPLE, YELLOW]
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.imshow(matrix.to_numpy(), cmap=ListedColormap(colours), vmin=-0.5, vmax=4.5, aspect="auto")
    ax.set_xticks(range(0, matrix.shape[1], 2), [str(y) for y in matrix.columns[::2]], rotation=90, fontsize=8)
    ax.set_yticks(range(matrix.shape[0]), list(matrix.index), fontsize=8)
    ax.set_xticks(np.arange(-0.5, matrix.shape[1]), minor=True)
    ax.set_yticks(np.arange(-0.5, matrix.shape[0]), minor=True)
    ax.grid(which="minor", color="#BBBBBB", linewidth=0.4)
    ax.tick_params(which="minor", length=0)
    ax.set_xlabel("Year t")
    ax.set_ylabel("Country (Eurostat code)")
    ax.set_title("Joint availability of capb, olddep1_lag and complete election data, 1995-2021")
    handles = [plt.Rectangle((0, 0), 1, 1, facecolor=c, edgecolor="#888888") for c in colours]
    fig.subplots_adjust(bottom=0.2)
    ax.legend(handles, COVERAGE_LABELS, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=3, fontsize=8, frameon=False)
    return _finish(fig, "t1_coverage_heatmap.png", SRC_AMECO)


def fig_capb_distribution(extract: pd.DataFrame) -> Path:
    """Histogram of pooled CAPB and per-country boxplots; Ireland 2010 marked."""
    data = select_columns(extract, ["eurostat_code", "year", "capb"])
    ie = data[(data["eurostat_code"] == IRELAND_OUTLIER[0]) & (data["year"] == IRELAND_OUTLIER[1])].iloc[0]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5), gridspec_kw={"width_ratios": [1, 1.8]})
    ax1.hist(data["capb"], bins=40, color=BLUE, edgecolor="white", label="country-years (N = %d)" % len(data))
    ax1.axvline(data["capb"].median(), color=BLACK, linestyle="--", linewidth=1, label=f"median {data['capb'].median():.2f} pp")
    ax1.annotate(f"IE {IRELAND_OUTLIER[1]}: {ie['capb']:.1f} pp", xy=(ie["capb"], 1), xytext=(ie["capb"] + 2.5, 22), arrowprops={"arrowstyle": "->", "color": VERMILLION}, color=VERMILLION, fontsize=9)
    ax1.set_xlabel("CAPB (UBLGBP), percentage points of potential GDP")
    ax1.set_ylabel("Number of country-years")
    ax1.set_title("Pooled distribution")
    ax1.legend(fontsize=8)
    order = data.groupby("eurostat_code")["capb"].median().sort_values().index
    ax2.boxplot([data.loc[data["eurostat_code"] == c, "capb"] for c in order], tick_labels=list(order), showfliers=True, flierprops={"marker": "o", "markersize": 3, "markerfacecolor": "none", "markeredgecolor": "#555555"}, boxprops={"color": BLUE}, medianprops={"color": BLACK}, whiskerprops={"color": BLUE}, capprops={"color": BLUE})
    pos = list(order).index(IRELAND_OUTLIER[0]) + 1
    ax2.scatter([pos], [ie["capb"]], color=VERMILLION, s=40, zorder=5, label=f"IE {IRELAND_OUTLIER[1]} ({ie['capb']:.1f} pp)")
    ax2.axhline(0, color="#888888", linewidth=0.8)
    ax2.set_xlabel("Country (ordered by median CAPB)")
    ax2.set_ylabel("CAPB, pp of potential GDP")
    ax2.set_title("By country, 1995-2021")
    ax2.tick_params(axis="x", labelsize=8)
    ax2.legend(fontsize=8, loc="lower right")
    fig.suptitle("Cyclically adjusted primary balance: distribution (confirmatory sample)")
    return _finish(fig, "t1_capb_distribution.png", SRC_AMECO)


def fig_capb_over_time(by_year: pd.DataFrame) -> Path:
    """Cross-country median and interquartile range by year, with crisis bands."""
    fig, ax = plt.subplots(figsize=(10, 5.2))
    _crisis_bands(ax)
    ax.fill_between(by_year["year"], by_year["q25"], by_year["q75"], color=SKY, alpha=0.55, label="interquartile range across countries")
    ax.plot(by_year["year"], by_year["median"], color=BLUE, linewidth=2, marker="o", markersize=3, label="cross-country median")
    ax.axhline(0, color="#888888", linewidth=0.8)
    ax.set_xlabel("Year")
    ax.set_ylabel("CAPB, pp of potential GDP")
    ax.set_title("CAPB over time: cross-country median and interquartile range")
    ax.set_xlim(by_year["year"].min() - 0.5, by_year["year"].max() + 0.5)
    ax.legend(fontsize=8, loc="lower right")
    return _finish(fig, "t1_capb_over_time.png", SRC_AMECO + " 22-27 countries per year.")


def fig_ageing(extract: pd.DataFrame) -> Path:
    """OLDDEP1 (lagged) trajectories by country in two panels (EU-15 versus accession members)."""
    data = select_columns(extract, ["eurostat_code", "year", "olddep1_lag"])
    groups = ageing_groups()
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), sharey=True)
    for ax, (group, colour) in zip(axes, [("EU-15 (accession 1995 or earlier)", BLUE), ("Accession 2004 or later", ORANGE)], strict=True):
        members = [c for c in sorted(data["eurostat_code"].unique()) if groups[c] == group]
        for c in members:
            sub = data[data["eurostat_code"] == c]
            ax.plot(sub["year"], sub["olddep1_lag"], color=colour, alpha=0.55, linewidth=1.2)
            ax.text(sub["year"].max() + 0.2, sub["olddep1_lag"].iloc[-1], c, fontsize=7, va="center", color=colour)
        med = data[data["eurostat_code"].isin(members)].groupby("year")["olddep1_lag"].median()
        ax.plot(med.index, med.values, color=BLACK, linewidth=2.2, label="group median")
        ax.plot([], [], color=colour, linewidth=1.2, label=f"countries (n = {len(members)})")
        ax.set_title(group)
        ax.set_xlabel("Year t")
        ax.set_xlim(1995, 2023)
        ax.legend(fontsize=8, loc="upper left")
    axes[0].set_ylabel("OLDDEP1 at t-1, persons 65+ per 100 aged 15-64")
    fig.suptitle("Old-age dependency ratio (lagged one year): country trajectories")
    return _finish(fig, "t1_olddep1_trajectories.png", "Source: Eurostat demo_pjanind (OLDDEP1); author's calculations. Confirmatory sample, 22-27 countries per year.")


def fig_calendar(by_year: pd.DataFrame, by_country: pd.DataFrame) -> Path:
    """Elections per year by class and per country by class (stacked bars)."""
    palette = {"scheduled": BLUE, "early": ORANGE, "delayed": GREEN, "unclassified": "#999999"}
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 9))
    years = by_year[by_year["year"] >= 1994]
    bottom = np.zeros(len(years))
    for cls in CLASS_ORDER:
        ax1.bar(years["year"], years[cls], bottom=bottom, color=palette[cls], label=cls)
        bottom += years[cls].to_numpy()
    ax1.set_xlabel("Year of election")
    ax1.set_ylabel("Number of national lower-house elections (EU-27)")
    ax1.set_title("Election calendar: elections per year by class, 1994-2023")
    ax1.set_ylim(0, years["total"].max() + 2.5)
    ax1.legend(fontsize=8, ncol=4, loc="upper left")
    table = by_country.sort_values("total", ascending=False)
    bottom = np.zeros(len(table))
    for cls in CLASS_ORDER:
        ax2.bar(table["eurostat_code"], table[cls], bottom=bottom, color=palette[cls], label=cls)
        bottom += table[cls].to_numpy()
    ax2.set_xlabel("Country (Eurostat code)")
    ax2.set_ylabel("Number of elections, 1994-2022")
    ax2.set_title("Election calendar: elections per country by class (elections dated 1994-2022)")
    ax2.set_ylim(0, table["total"].max() + 2.5)
    ax2.legend(fontsize=8, ncol=4, loc="upper right")
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    return _finish(fig, "t1_election_calendar_counts.png", SRC_CALENDAR)


def fig_exposure_distribution(exposure: pd.DataFrame) -> Path:
    """Share of country-years with positive exposure and the distribution of positive values."""
    data = select_columns(exposure, ["eurostat_code", "year"] + EXPOSURE_VARIABLES)
    data = data[data["year"].between(*WINDOW)]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.8))
    shares = [100 * (data[v] > 0).mean() for v in EXPOSURE_VARIABLES]
    ax1.bar(EXPOSURE_VARIABLES, shares, color=[BLUE, ORANGE, GREEN, "#999999", PURPLE])
    for i, s in enumerate(shares):
        ax1.text(i, s + 0.8, f"{s:.1f}%", ha="center", fontsize=8)
    ax1.set_xlabel("Exposure variable")
    ax1.set_ylabel("Share of country-years with value > 0 (%)")
    ax1.set_title(f"Positive exposure (N = {len(data)} country-years, 1995-2021)")
    for var, colour in (("W_S", BLUE), ("W_E", ORANGE), ("Post", PURPLE)):
        x = data.loc[data[var] > 0, var]
        ax2.hist(x, bins=20, range=(0, 1), histtype="step", linewidth=1.8, color=colour, label=f"{var} (n > 0 = {len(x)})")
    ax2.set_xlabel("Exposure value (share of calendar year, 0-1)")
    ax2.set_ylabel("Number of country-years with value > 0")
    ax2.set_title("Distribution of positive exposure values")
    ax2.legend(fontsize=8)
    return _finish(fig, "t1_exposure_distribution.png", SRC_CALENDAR)


def fig_secondary(medians: pd.DataFrame) -> Path:
    """Cross-country medians of the secondary aggregates (% of GDP)."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.2))
    for ax, cols, colours in ((ax1, ["sec_revenue", "sec_total_expenditure"], [BLUE, VERMILLION]), (ax2, ["sec_interest_d41pay", "sec_social_benefits_d62", "sec_social_transfers_kind_d632"], [GREEN, ORANGE, PURPLE])):
        _crisis_bands(ax, label=ax is ax1)
        for col, colour in zip(cols, colours, strict=True):
            ax.plot(medians["year"], medians[col], color=colour, linewidth=2, label=SECONDARY_SERIES[col])
        ax.set_xlabel("Year")
        ax.set_ylabel("Cross-country median, % of GDP")
        ax.legend(fontsize=8, loc="best")
    ax1.set_title("Revenue and total expenditure")
    ax2.set_title("Interest and social benefits")
    fig.suptitle("General government aggregates, cross-country median, 1995-2021")
    return _finish(fig, "t1_secondary_aggregates.png", SRC_SECONDARY + " Medians over the countries with data in each year.")


def fig_decomposition(panel: pd.DataFrame, picks: pd.DataFrame) -> Path:
    """CAPB, headline primary balance and cyclical component for the three rule-selected countries."""
    data = select_columns(panel, ["eurostat_code", "year", "capb", "sec_primary_balance_edp", "sec_cyclical_component"])
    chosen = picks[picks["pick"] != ""].set_index("pick").loc[["largest", "median", "smallest"]]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), sharey=True)
    for ax, (label, row) in zip(axes, chosen.iterrows(), strict=True):
        sub = data[data["eurostat_code"] == row["eurostat_code"]]
        _crisis_bands(ax, label=False)
        ax.plot(sub["year"], sub["capb"], color=BLUE, linewidth=2, label="CAPB (UBLGBP, % of potential GDP)")
        ax.plot(sub["year"], sub["sec_primary_balance_edp"], color=ORANGE, linewidth=1.6, label="headline primary balance (UBLGIE, % of GDP)")
        ax.plot(sub["year"], sub["sec_cyclical_component"], color=GREEN, linewidth=1.6, linestyle="--", label="cyclical component (UBLGCP, % of potential GDP)")
        ax.axhline(0, color="#888888", linewidth=0.8)
        ax.set_title(f"{row['eurostat_code']} ({label} mean |cyclical component| = {row['mean_abs_cyclical_pp']:.2f} pp)", fontsize=9)
        ax.set_xlabel("Year")
    axes[0].set_ylabel("Percentage points")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, fontsize=8, frameon=False, bbox_to_anchor=(0.5, -0.06))
    fig.suptitle("Fiscal balance decomposition for three countries chosen by the size of the cyclical component")
    return _finish(fig, "t1_decomposition_illustrative.png", SRC_SECONDARY + " Denominators differ (potential vs actual GDP), so the series are not additive.", source_y=-0.1)


def fig_within_corr(matrix: pd.DataFrame) -> Path:
    """Heatmap of within correlations."""
    fig, ax = plt.subplots(figsize=(6.6, 5.6))
    im = ax.imshow(matrix.to_numpy(), cmap="PuOr", vmin=-1, vmax=1)
    labels = list(matrix.columns)
    ax.set_xticks(range(len(labels)), labels, rotation=35, ha="right", fontsize=8)
    ax.set_yticks(range(len(labels)), labels, fontsize=8)
    for i in range(len(labels)):
        for j in range(len(labels)):
            ax.text(j, i, f"{matrix.iloc[i, j]:.2f}", ha="center", va="center", fontsize=8, color="black")
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Pearson r of two-way-demeaned variables")
    ax.set_xlabel("Variable (lags at t-1 as named; capb at t)")
    ax.set_ylabel("Variable")
    ax.set_title("Within correlations (country and year effects removed)")
    return _finish(fig, "t1_within_correlations.png", SRC_AMECO + " Eurostat gov_10dd_edpt1, gov_10a_main, nama_10_gdp for debt and interest-growth.")


# ---------------------------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------------------------
def build_report(panel: pd.DataFrame, calendar: pd.DataFrame, exposure: pd.DataFrame) -> str:
    """Compute every Tier-1 descriptive, write the figures and return the markdown report."""
    extract = panel[panel["in_confirmatory"]].reset_index(drop=True)
    keys = extract[["eurostat_code", "year"]]
    figs: dict[str, Path] = {}

    cov = coverage_matrix(panel)
    figs["coverage"] = fig_coverage(cov)
    missing = missing_cells_table(panel)

    joint_ok = cov.eq(0)
    first_ok = joint_ok.idxmax(axis=1)
    is_leading = all((joint_ok.loc[c, [y for y in joint_ok.columns if y >= first_ok[c]]]).all() for c in joint_ok.index)
    leading_text = "Every missing cell lies before the first fully available year of its country (series starting later in AMECO for CY, CZ, SI, SK and HR; empty Eurostat cells for HR)." if is_leading else "Some missing cells lie inside a country's series."

    summary = capb_summary(extract)
    all_resid = residual_cells(extract, k=len(extract))
    resid = all_resid.head(TOP_RESIDUALS).reset_index(drop=True)
    persist = persistence_table(extract)
    figs["dist"] = fig_capb_distribution(extract)
    by_year = capb_by_year(extract)
    figs["time"] = fig_capb_over_time(by_year)

    age = ageing_summary(extract)
    disp = ageing_dispersion(extract)
    age_groups = ageing_group_table(extract)
    figs["ageing"] = fig_ageing(extract)

    cal_year, cal_country = calendar_by_year(calendar), calendar_by_country(calendar)
    uncl = unclassified_elections(calendar)
    expo_all, expo_ext = exposure_distribution(exposure), exposure_distribution(exposure, keys)
    exposure_window = select_columns(exposure, ["eurostat_code", "year"] + EXPOSURE_VARIABLES)
    exposure_window = exposure_window[exposure_window["year"].between(*WINDOW)]
    pos_all, pos_ext = any_positive_share(exposure), any_positive_share(exposure, keys)
    figs["calendar"] = fig_calendar(cal_year, cal_country)
    figs["exposure"] = fig_exposure_distribution(exposure)

    med = secondary_medians(panel)
    picks = illustrative_countries(panel)
    figs["secondary"] = fig_secondary(med)
    figs["decomp"] = fig_decomposition(panel, picks)

    corr, pairs = within_correlations(extract)
    figs["corr"] = fig_within_corr(corr)
    vif_tables = {label: within_vif(extract, cols) for label, cols in VIF_SETS.items()}

    rel = lambda key: f"figures/{figs[key].name}"  # noqa: E731
    n_obs, n_c = summary["n_obs"], summary["n_countries"]
    ie = all_resid[(all_resid["eurostat_code"] == IRELAND_OUTLIER[0]) & (all_resid["year"] == IRELAND_OUTLIER[1])]
    ie_rank = int(ie.index[0]) + 1
    rho_rows = pd.DataFrame(
        [
            {"estimator": "pooled AR(1), raw two-way residual", "this report (country + year effects)": persist["raw_pooled"], "Gate 3b (full M1 residual)": GATE3_PERSISTENCE["raw pooled"]},
            {"estimator": "pooled AR(1), country-standardised", "this report (country + year effects)": persist["country_standardised"], "Gate 3b (full M1 residual)": GATE3_PERSISTENCE["country-standardised"]},
            {"estimator": f"Nickell analytic correction (T = {persist['mean_obs_per_country']:.1f})", "this report (country + year effects)": persist["nickell_analytic"], "Gate 3b (full M1 residual)": GATE3_PERSISTENCE["Nickell analytic"]},
            {"estimator": f"simulation (indirect-inference) correction, {N_SIM} panels, seed {SEED}", "this report (country + year effects)": persist["simulation_corrected"], "Gate 3b (full M1 residual)": GATE3_PERSISTENCE["simulation-corrected"]},
        ]
    )
    shares = pd.DataFrame(
        [
            {"statistic": "mean (pp)", "capb": summary["mean"], "olddep1_lag": age["mean"]},
            {"statistic": "pooled SD, N - 1 (pp)", "capb": summary["sd_pooled_ddof1"], "olddep1_lag": float("nan")},
            {"statistic": "pooled SD, population form (pp)", "capb": summary["sd_pooled_pop"], "olddep1_lag": age["total_sd"]},
            {"statistic": "between-country SD (country means, pp)", "capb": summary["sd_between_country"], "olddep1_lag": age["sd_country_means_pp"]},
            {"statistic": "within-country SD (deviation from country mean, pp)", "capb": summary["sd_within_country"], "olddep1_lag": float(np.sqrt(((extract["olddep1_lag"] - extract.groupby("eurostat_code")["olddep1_lag"].transform("mean")) ** 2).mean()))},
            {"statistic": "two-way SD (country + year effects removed, RSS/N, pp)", "capb": summary["sd_two_way"], "olddep1_lag": age["sd_two_way_demeaned_pp"]},
            {"statistic": "two-way SD, df-corrected (pp)", "capb": summary["sd_two_way_df_corrected"], "olddep1_lag": age["sd_two_way_demeaned_df_corrected_pp"]},
            {"statistic": "variance share: between countries", "capb": summary["share_between"], "olddep1_lag": age["share_between_country"]},
            {"statistic": "variance share: common year effects (after country)", "capb": summary["share_common_year"], "olddep1_lag": age["share_common_year_after_country"]},
            {"statistic": "variance share: two-way residual", "capb": summary["share_two_way_residual"], "olddep1_lag": age["share_two_way_residual"]},
        ]
    )
    ordered = extract.sort_values(["eurostat_code", "year"]).groupby("eurostat_code")["olddep1_lag"]
    n_rising = int((ordered.last() > ordered.first()).sum())
    d1995 = disp[(disp["year"] == 1995)].set_index("countries")
    d2021 = disp[(disp["year"] == 2021)].set_index("countries")
    bal = [i for i in d1995.index if i.startswith("balanced")][0]
    allc = "all countries available in the year"
    sd_ratio_all = d2021.loc[allc, "SD"] / d1995.loc[allc, "SD"]
    sd_ratio_bal = d2021.loc[bal, "SD"] / d1995.loc[bal, "SD"]
    n_scheduled_min = cal_country[cal_country["scheduled"] == cal_country["scheduled"].min()]
    pick_text = ", ".join(f"{r.eurostat_code} ({r.pick}, {r.mean_abs_cyclical_pp:.2f} pp)" for r in picks[picks["pick"] != ""].itertuples())
    cal_total = int(cal_year["total"].sum())
    cal_cls = {c: int(cal_year[c].sum()) for c in CLASS_ORDER}
    cal_from94 = calendar[calendar["date_used"] >= pd.Timestamp("1994-01-01")]
    cal94 = {c: int((cal_from94["class_primary"] == c).sum()) for c in CLASS_ORDER}
    lines = [
        "# Tier-1 descriptives (unconditional on elections)",
        "",
        "Generated by `python src/evaluate/descriptives.py` (module `src/evaluate/descriptives.py`, tests `tests/test_descriptives.py`) from the gold panel `data/processed/gold/panel_country_year.parquet` (`reports/gold_panel_audit.md`). Offline, deterministic; the only random draw is the persistence simulation (`numpy.random.default_rng(42)`).",
        "",
        "**Freeze rule.** The pre-registration freeze (tag `preregistration-v1`) has not happened. No statistic, table or figure below relates CAPB or any secondary fiscal outcome to an election variable (`W_S`, `W_E`, `W_D`, `W_U`, `Post`, election dates, scheduled/early/delayed/unclassified classes). The guard `assert_no_exposure_with_outcome` raises if a routine requests both kinds of column, and every routine reads its inputs through it. Section 5 describes the election calendar on its own. The 715-row sample is defined by data availability and exposure completeness, not by outcome values.",
        "",
        "Units: CAPB and the cyclical component are percentage points (pp) of potential GDP, surplus positive; headline primary balance and the aggregates in section 6 are % of GDP; OLDDEP1 is persons aged 65+ per 100 aged 15-64, taken at t-1.",
        "",
        "## 1. Coverage and missingness",
        "",
        f"![coverage]({rel('coverage')})",
        "",
        f"Joint availability of `capb`, `olddep1_lag` and the cross-validated exposure-completeness flag over 1995-2021 for 27 countries ({len(panel)} cells): {int((cov == 0).to_numpy().sum())} cells have all three; {int((cov != 0).to_numpy().sum())} do not. {int((cov == 4).to_numpy().sum())} cells are lost to incomplete exposure. Missing cells, by cause:",
        "",
        md_table(missing),
        "",
        f"{leading_text} The panel is therefore unbalanced: {int((extract.groupby('eurostat_code').size() == extract['year'].nunique()).sum())} countries have the full {extract['year'].nunique()}-year run; N = {n_obs} country-years.",
        "",
        "## 2. CAPB distribution",
        "",
        f"![capb distribution]({rel('dist')})",
        "",
        f"Confirmatory sample: N = {n_obs}, {n_c} countries, 1995-2021. CAPB has mean {summary['mean']:.2f} pp, median {summary['median']:.2f} pp, minimum {summary['min']:.2f} pp, maximum {summary['max']:.2f} pp; {summary['n_negative']} of {n_obs} values are negative (skewness {summary['skewness']:.2f}, excess kurtosis {summary['excess_kurtosis']:.2f}). Variance decomposition of CAPB and, for reference, of the lagged moderator:",
        "",
        md_table(shares, ".3f"),
        "",
        f"The two-way SD of CAPB ({summary['sd_two_way']:.2f} pp; {summary['sd_two_way_df_corrected']:.2f} pp with the degrees-of-freedom correction) is the scale left after removing country and year effects; between-country differences account for {100 * summary['share_between']:.1f}% and common year effects for {100 * summary['share_common_year']:.1f}% of the variance about the grand mean.",
        "",
        f"**Largest absolute residual cells** (CAPB regressed on country and year effects only; no election variable). Ireland {IRELAND_OUTLIER[1]} (CAPB {ie['capb'].iloc[0]:.1f} pp, residual {ie['capb_two_way_residual'].iloc[0]:.1f} pp) ranks {ie_rank} of {len(all_resid)}.",
        "",
        md_table(resid.assign(rank=range(1, len(resid) + 1))[["rank", "eurostat_code", "year", "capb", "capb_two_way_residual"]].rename(columns={"capb": "capb (pp)", "capb_two_way_residual": "two-way residual (pp)"})),
        "",
        "### Persistence of the two-way residual",
        "",
        f"AR(1) coefficient of the country-and-year-effects residual of CAPB over {persist['n_pairs']} consecutive-year pairs. The earlier figures come from the full M1 residual (with the election and ageing terms) in `reports/gate3_power_update.md`; the comparison is therefore between two different residuals, and I did not re-derive any effect estimate.",
        "",
        md_table(rho_rows, ".3f"),
        "",
        f"Reading: the raw two-way-residual AR(1) is {persist['raw_pooled']:.2f} (country-standardised {persist['country_standardised']:.2f}), against 0.59 and 0.56 for the M1 residual; the simulation-corrected value is {persist['simulation_corrected']:.2f} against 0.69. The range of 0.56-0.59 raw and the corrected value of 0.69 are {'reproduced within 0.03' if abs(persist['simulation_corrected'] - 0.694) < 0.03 and abs(persist['country_standardised'] - 0.562) < 0.03 else 'not reproduced within 0.03'} by the residual that omits all election and ageing terms.",
        "",
        "## 3. CAPB over time",
        "",
        f"![capb over time]({rel('time')})",
        "",
        md_table(by_year.assign(n=by_year["n"].astype(int)).rename(columns={"q25": "25th pct (pp)", "median": "median (pp)", "q75": "75th pct (pp)"}), ".2f"),
        "",
        f"The cross-country median ranges from {by_year['median'].min():.2f} pp ({int(by_year.loc[by_year['median'].idxmin(), 'year'])}) to {by_year['median'].max():.2f} pp ({int(by_year.loc[by_year['median'].idxmax(), 'year'])}). Shaded bands mark 2008-09, 2010-12 and 2020-21; they are annotations of calendar periods and not variables in any model. The number of countries per year rises from {int(by_year['n'].iloc[0])} in 1995 to {int(by_year['n'].iloc[-1])}.",
        "",
        "## 4. Ageing (OLDDEP1 at t-1)",
        "",
        f"![olddep1 trajectories]({rel('ageing')})",
        "",
        f"Two-way SD of `olddep1_lag` on the confirmatory sample: **{age['sd_two_way_demeaned_pp']:.3f} pp** ({age['sd_two_way_demeaned_z']:.3f} z; df-corrected {age['sd_two_way_demeaned_df_corrected_pp']:.3f} pp); Gate 3a reported {GATE3A_TWO_WAY_SD_PP:.3f} pp, so the audited figure is {'confirmed' if abs(age['sd_two_way_demeaned_pp'] - GATE3A_TWO_WAY_SD_PP) < 0.005 else 'NOT confirmed'} (difference {age['sd_two_way_demeaned_pp'] - GATE3A_TWO_WAY_SD_PP:+.4f} pp). Variance shares: between countries {age['share_between_country']:.3f}, common year effects {age['share_common_year_after_country']:.3f}, two-way residual {age['share_two_way_residual']:.3f} (see the table in section 2). {n_rising} of {n_c} countries have a higher `olddep1_lag` in their last sample year than in their first; the common year effects account for {100 * age['share_common_year_after_country']:.1f}% of the variance and the two-way residual for {100 * age['share_two_way_residual']:.1f}%.",
        "",
        "Cross-country dispersion of `olddep1_lag`, first and last sample year:",
        "",
        md_table(disp, ".2f"),
        "",
        f"The cross-country SD changes by a factor {sd_ratio_all:.2f} between 1995 and 2021 across all available countries (22 in 1995, 27 in 2021) and {sd_ratio_bal:.2f} in the balanced subset. Group medians:",
        "",
        md_table(age_groups, ".2f"),
        "",
        "## 5. The election calendar on its own (outcome-free)",
        "",
        f"![calendar counts]({rel('calendar')})",
        "",
        f"The calendar holds {cal_total} national lower-house elections 1990-2023 ({', '.join(f'{c} {n}' for c, n in cal_cls.items())}); dated 1994 or later: {', '.join(f'{c} {n}' for c, n in cal94.items())}. Elections per year by class (election date year):",
        "",
        md_table(cal_year[cal_year["year"] >= 1994].astype(int)),
        "",
        "Elections per country by class among those that can touch exposure in 1995-2021 (dated 1994-01-01 to 2022-12-31), sorted by the number of scheduled elections:",
        "",
        md_table(cal_country),
        "",
        f"Fewest scheduled elections: {', '.join(n_scheduled_min['eurostat_code'])} ({int(n_scheduled_min['scheduled'].iloc[0])} each). Cyprus and Malta are absent from ETAD, so their elections are all unclassified.",
        "",
        f"### Unclassified elections dated 1994 or later: {len(uncl)}",
        "",
        f"Of these, {int(uncl['touches_1995_2021'].sum())} fall on or before 2022-12-31 and can enter the 1995-2021 exposure; the remaining {int((~uncl['touches_1995_2021']).sum())} are 2023 elections.",
        "",
        md_table(uncl.assign(date_used=uncl["date_used"].dt.strftime("%Y-%m-%d")).drop(columns="touches_1995_2021").rename(columns={"class_rule": "rule", "class_gap": "gap-based class"})),
        "",
        f"![exposure distribution]({rel('exposure')})",
        "",
        "Distribution of the exposure variables (share of the calendar year inside the window; 0-1) over the 729 country-years of 1995-2021, and over the 715-row confirmatory sample:",
        "",
        md_table(expo_all.assign(sample="window 729"), ".3f"),
        "",
        md_table(expo_ext.assign(sample="confirmatory 715"), ".3f"),
        "",
        f"Share of country-years with a positive pre-election exposure of any class: {pos_all['any_pre_window_%']:.1f}% of {pos_all['n']} (window) and {pos_ext['any_pre_window_%']:.1f}% of {pos_ext['n']} (confirmatory); with a positive `Post`: {pos_all['post_%']:.1f}% and {pos_ext['post_%']:.1f}%; positive pre-election or post exposure: {pos_all['any_pre_or_post_%']:.1f}% and {pos_ext['any_pre_or_post_%']:.1f}%. `W_D` is positive in {int((exposure_window['W_D'] > 0).sum())} country-years of the window (the single delayed election is HR 2000-01-03).",
        "",
        "## 6. Secondary fiscal aggregates",
        "",
        f"![secondary aggregates]({rel('secondary')})",
        "",
        md_table(med.rename(columns={k: v for k, v in SECONDARY_SERIES.items()}).assign(n_countries=med["n_countries"].astype(int)), ".2f"),
        "",
        "Cross-country medians, % of GDP, over the countries with data in each year (Eurostat `gov_10a_main`).",
        "",
        "### Decomposition for three illustrative countries",
        "",
        f"Rule fixed in advance: rank countries by the mean absolute cyclical component (AMECO UBLGCP, pp of potential GDP) over 1995-2021 and take the largest, the smallest and the (lower) median. Selected: {pick_text}. The rule uses no election variable.",
        "",
        f"![decomposition]({rel('decomp')})",
        "",
        md_table(picks.rename(columns={"mean_abs_cyclical_pp": "mean abs cyclical component (pp)", "n_years": "years"}), ".2f"),
        "",
        "CAPB is expressed in % of potential GDP and the headline primary balance (UBLGIE, EDP basis) in % of GDP, so the three series are not additive; the figure shows their co-movement only.",
        "",
        "## 7. Within correlations and multicollinearity (no exposure variable)",
        "",
        f"![within correlations]({rel('corr')})",
        "",
        "Pearson correlations of two-way-demeaned (country and year effects removed) variables, each pair on its own pairwise-complete rows of the confirmatory sample. Intervals are naive Fisher-z intervals that ignore clustering and the fixed-effects degrees of freedom; they are descriptive.",
        "",
        md_table(pairs, ".3f"),
        "",
        "VIF of the two-way-demeaned regressors (the diagonal of the inverse correlation matrix), exposure terms excluded; VIF above 5 would be flagged for discussion. This is a partial check: the VIF of the full M1 design including the exposure terms and interactions is deferred until after the freeze.",
        "",
    ]
    for label, table in vif_tables.items():
        lines += [f"{label}:", "", md_table(table, ".2f"), ""]
    lines += [
        "## 8. What these descriptives do not show",
        "",
        "* They do not relate CAPB, or any secondary outcome, to any election variable: no election-window plot, event study, outcome-on-election regression or group mean of CAPB by exposure appears here. Every election-related statement about fiscal outcomes is deferred until after the freeze (`preregistration-v1`).",
        "* Section 5 describes the calendar by itself; it says nothing about fiscal behaviour around elections.",
        "* The crisis bands are calendar annotations. Co-movement of the cross-country median with them is not evidence about any mechanism.",
        "* The within correlations are associations between variables with country and year effects removed; they are not causal and ignore clustering. The VIF check is partial.",
        "* The persistence comparison uses a different residual than Gate 3b (no election or ageing terms), so equality of the numbers is not expected.",
        "* The sample is unbalanced (14 country-years at the start of five countries' series are absent), and CAPB is a model-based Commission estimate that is revised between vintages.",
        "",
    ]
    return "\n".join(line for line in lines if line is not None)


def main() -> int:
    """Write the figures and ``reports/tier1_descriptives.md``."""
    panel = load_panel()
    calendar = load_calendar()
    exposure = pd.read_csv(EXPOSURE_CSV)
    REPORT_PATH.write_text(build_report(panel, calendar, exposure), encoding="utf-8")
    print(f"wrote {REPORT_PATH.relative_to(PROJECT_ROOT)} and figures in {FIG_DIR.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
