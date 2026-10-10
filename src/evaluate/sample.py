"""Gate 3a: joint-coverage sample selection and the G1 moderator-variation statistics.

Rule (decision log #2; acquisition manifest section 6, step 3): the start year ``t0`` is the earliest year
such that from ``t0`` to the end year (i) at least ``MIN_COUNTRIES_PER_YEAR`` retained countries are jointly
observed in every year and (ii) every retained country has at least ``MIN_OBS_PER_COUNTRY`` observations.
A country-year is *jointly observed* when it has a CAPB value (AMECO ``UBLGBP``, surplus positive, % of potential
GDP), the lagged moderator ``A_{t-1}`` (Eurostat ``OLDDEP1``, per cent, age 65+ over 15-64), and complete
election exposure (see ``elections.py``). The end year follows the exposure-completeness rule. Negative CAPB
values are legitimate and are never filtered. Eurostat observation flags (b, e, p) are carried as columns.

This module reads CAPB and OLDDEP1; the election modules never do. No randomness is involved (no seeds).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

_NORMALIZE = Path(__file__).resolve().parents[1] / "normalize"
sys.path.insert(0, str(_NORMALIZE))
import ameco  # noqa: E402
import countries  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CAPB_CSV = ameco.AMECO_DIR / "sdmx" / "AMECO_CHAPTER17-01_UBLGBP.csv"
OLDDEP_CSV = PROJECT_ROOT / "data" / "raw" / "elections_ageing" / "eurostat_demo_pjanind" / "demo_pjanind_EU27_OLDDEP_1994_2025.csv"
EXPOSURE_CSV = PROJECT_ROOT / "data" / "interim" / "exposure_eu27.csv"
CALENDAR_CSV = PROJECT_ROOT / "data" / "interim" / "election_calendar_eu27.csv"

MIN_COUNTRIES_PER_YEAR = 22  # decision log #2 / manifest section 6 step 3
MIN_OBS_PER_COUNTRY = 20  # same
MODERATOR_INDICATOR = "OLDDEP1"
LAG_YEARS = 1  # moderator enters lagged one year (proposal 9.2)

# G1 gate (reports/appendix_D_feasibility_gates.md, gate table): two-way-demeaned SD of the moderator.
G1_GREEN_PP = 1.0
G1_GREEN_Z = 0.20
G1_GREEN_RESIDUAL_SHARE = 0.05
G1_AMBER_PP = 0.7


# ---------------------------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------------------------
def read_capb(path: Path = CAPB_CSV) -> pd.DataFrame:
    """CAPB (``UBLGBP``) by Eurostat country code and year for the EU-27, observed years only.

    Forecast years are dropped using the AMECO rule (last two years of a Spring vintage; ``ameco.last_observed_year``).
    Negative values are kept.
    """
    frame = ameco.read_sdmx_csv(path)
    last_observed = ameco.last_observed_year(int(frame["TIME_PERIOD"].max()), "spring")
    to_eurostat = countries.ameco_to_eurostat()
    frame = frame[frame["REF_AREA"].isin(to_eurostat) & (frame["TIME_PERIOD"] <= last_observed)].copy()
    frame["eurostat_code"] = frame["REF_AREA"].map(to_eurostat)
    frame = frame.rename(columns={"TIME_PERIOD": "year", "OBS_VALUE": "capb", "OBS_STATUS": "capb_obs_status"})
    return frame[["eurostat_code", "year", "capb", "capb_obs_status"]]


def read_moderator(path: Path = OLDDEP_CSV, indicator: str = MODERATOR_INDICATOR) -> pd.DataFrame:
    """Moderator series by Eurostat code and year, with the Eurostat ``OBS_FLAG`` kept as a separate column."""
    frame = pd.read_csv(path)
    frame = frame[frame["indic_de"] == indicator]
    frame = frame.rename(columns={"geo": "eurostat_code", "TIME_PERIOD": "year", "OBS_VALUE": "olddep1", "OBS_FLAG": "olddep1_flag"})
    return frame[["eurostat_code", "year", "olddep1", "olddep1_flag"]].reset_index(drop=True)


def read_exposure(path: Path = EXPOSURE_CSV) -> pd.DataFrame:
    """Exposure panel written by ``src/normalize/elections.py``."""
    if not path.exists():
        raise FileNotFoundError(f"{path} missing: run `python src/normalize/elections.py` first")
    return pd.read_csv(path)


# ---------------------------------------------------------------------------------------------
# Panel and selection
# ---------------------------------------------------------------------------------------------
def build_panel(exposure: pd.DataFrame | None = None) -> pd.DataFrame:
    """Country-year panel (27 countries, 1995 to the last observed AMECO year) with CAPB, lagged moderator, exposure.

    ``olddep1_lag`` is ``OLDDEP1`` at ``t - 1``; ``olddep1_lag_flag`` its Eurostat flag. ``joint_cv`` and
    ``joint_etad`` apply the two exposure-completeness bases (see ``elections.py``).
    """
    exposure = read_exposure() if exposure is None else exposure
    capb = read_capb()
    moderator = read_moderator()
    lagged = moderator.assign(year=moderator["year"] + LAG_YEARS).rename(
        columns={"olddep1": "olddep1_lag", "olddep1_flag": "olddep1_lag_flag"}
    )
    current = moderator.rename(columns={"olddep1": "olddep1_t", "olddep1_flag": "olddep1_t_flag"})
    first_year = int(moderator["year"].min()) + LAG_YEARS
    years = range(first_year, int(capb["year"].max()) + 1)
    index = pd.MultiIndex.from_product([countries.eu27_eurostat_codes(), years], names=["eurostat_code", "year"]).to_frame(index=False)
    panel = index.merge(capb, on=["eurostat_code", "year"], how="left")
    panel = panel.merge(lagged, on=["eurostat_code", "year"], how="left").merge(current, on=["eurostat_code", "year"], how="left")
    panel = panel.merge(exposure, on=["eurostat_code", "year"], how="left")
    for flag in ("exposure_complete_cv", "exposure_complete_etad", "touches_unclassified_or_delayed", "additive_exceeds_one"):
        panel[flag] = panel[flag].fillna(False).astype(bool)  # years beyond the exposure panel carry no exposure
    for tag in ("cv", "etad"):
        complete = panel[f"exposure_complete_{tag}"]
        panel[f"joint_{tag}"] = panel["capb"].notna() & panel["olddep1_lag"].notna() & complete
    return panel


@dataclass(frozen=True)
class Selection:
    """Result of the joint-coverage rule."""

    t0: int
    end_year: int
    countries: list[str]
    sample: pd.DataFrame
    trace: pd.DataFrame


def last_common_complete_year(panel: pd.DataFrame, basis: str = "cv") -> int:
    """Last year in which every EU-27 country has complete exposure on the given basis (``cv`` or ``etad``)."""
    flag = panel[f"exposure_complete_{basis}"].fillna(False).astype(bool)  # years beyond the exposure panel are incomplete
    complete = flag.groupby(panel["year"]).all()
    return int(complete[complete].index.max())


def last_year_any_complete(panel: pd.DataFrame, basis: str = "etad") -> int:
    """Last year in which at least one country has complete exposure on the given basis."""
    flag = panel[f"exposure_complete_{basis}"].fillna(False).astype(bool)
    complete = flag.groupby(panel["year"]).any()
    return int(complete[complete].index.max())


def evaluate_start(panel: pd.DataFrame, t0: int, end_year: int, joint_col: str) -> tuple[list[str], int, bool]:
    """Retained countries, minimum yearly joint count and pass/fail for one candidate ``t0``."""
    window = panel[panel["year"].between(t0, end_year) & panel[joint_col]]
    counts = window.groupby("eurostat_code").size()
    retained = sorted(counts[counts >= MIN_OBS_PER_COUNTRY].index)
    yearly = window[window["eurostat_code"].isin(retained)].groupby("year").size().reindex(range(t0, end_year + 1), fill_value=0)
    min_count = int(yearly.min())
    return retained, min_count, bool(min_count >= MIN_COUNTRIES_PER_YEAR and len(retained) > 0)


def select_sample(panel: pd.DataFrame, end_year: int, joint_col: str = "joint_cv") -> Selection:
    """Apply the rule: earliest ``t0`` at which the yearly and per-country coverage thresholds hold up to ``end_year``."""
    first_year = int(panel["year"].min())
    rows = []
    chosen: tuple[int, list[str]] | None = None
    for t0 in range(first_year, end_year + 1):
        retained, min_count, ok = evaluate_start(panel, t0, end_year, joint_col)
        rows.append({"t0": t0, "n_retained": len(retained), "min_yearly_joint_count": min_count, "passes": ok})
        if ok and chosen is None:
            chosen = (t0, retained)
    if chosen is None:
        raise ValueError("no start year satisfies the joint-coverage rule")
    t0, retained = chosen
    sample = panel[panel["year"].between(t0, end_year) & panel[joint_col] & panel["eurostat_code"].isin(retained)].copy()
    return Selection(t0, end_year, retained, sample.reset_index(drop=True), pd.DataFrame(rows))


def per_country_coverage(sample: pd.DataFrame) -> pd.DataFrame:
    """First year, last year, number of observations and gaps inside the span, per country."""
    grouped = sample.groupby("eurostat_code")["year"]
    table = grouped.agg(first_year="min", last_year="max", n_obs="size")
    table["n_gaps_inside_span"] = table["last_year"] - table["first_year"] + 1 - table["n_obs"]
    return table.reset_index()


def missingness_table(panel: pd.DataFrame, t0: int, end_year: int, joint_col: str = "joint_cv", basis: str = "cv") -> pd.DataFrame:
    """Per-country count of country-years in ``[t0, end_year]`` lost to each reason (not mutually exclusive)."""
    window = panel[panel["year"].between(t0, end_year)]
    rows = []
    for code, sub in window.groupby("eurostat_code"):
        rows.append(
            {
                "eurostat_code": code,
                "years_in_window": len(sub),
                "missing_capb": int(sub["capb"].isna().sum()),
                "missing_moderator_lag": int(sub["olddep1_lag"].isna().sum()),
                "exposure_incomplete": int((~sub[f"exposure_complete_{basis}"].fillna(False).astype(bool)).sum()),
                "not_jointly_observed": int((~sub[joint_col]).sum()),
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------------------------
# G1 statistics for the lagged moderator
# ---------------------------------------------------------------------------------------------
def _two_way_residuals(frame: pd.DataFrame, value: str) -> np.ndarray:
    """Residuals of ``value`` on country and year dummies (exact least squares, works for unbalanced panels)."""
    countries_dummies = pd.get_dummies(frame["eurostat_code"], dtype=float)
    years_dummies = pd.get_dummies(frame["year"], dtype=float).iloc[:, 1:]
    design = np.column_stack([countries_dummies.to_numpy(), years_dummies.to_numpy()])
    y = frame[value].to_numpy(dtype=float)
    beta, *_ = np.linalg.lstsq(design, y, rcond=None)
    return y - design @ beta


def g1_statistics(sample: pd.DataFrame, value: str = "olddep1_lag") -> dict[str, float | str]:
    """Variance decomposition and two-way-demeaned SD of the lagged moderator on a (possibly unbalanced) sample.

    Shares are sums of squares about the grand mean: ``between`` = country means; ``year_after_country`` = the
    additional sum of squares explained by year effects after country effects (sequential, equal to the exact
    orthogonal share on a balanced panel); ``two_way_residual`` = residual of the country + year fixed-effects
    fit. SDs use ``RSS / N`` (population form, as in Appendix D); the degrees-of-freedom form is also given.
    ``z`` units divide by the pooled SD of the moderator on this sample.
    """
    frame = sample.dropna(subset=[value])
    y = frame[value].to_numpy(dtype=float)
    n = len(y)
    tss = float(((y - y.mean()) ** 2).sum())
    country_mean = frame.groupby("eurostat_code")[value].transform("mean").to_numpy()
    ss_country_resid = float(((y - country_mean) ** 2).sum())
    resid = _two_way_residuals(frame, value)
    rss = float((resid**2).sum())
    n_countries = frame["eurostat_code"].nunique()
    n_years = frame["year"].nunique()
    total_sd = float(np.sqrt(tss / n))
    sd_two_way = float(np.sqrt(rss / n))
    out: dict[str, float | str] = {
        "n_obs": n,
        "n_countries": n_countries,
        "n_years": n_years,
        "mean": float(y.mean()),
        "total_sd": total_sd,
        "share_between_country": 1 - ss_country_resid / tss,
        "share_common_year_after_country": (ss_country_resid - rss) / tss,
        "share_two_way_residual": rss / tss,
        "sd_two_way_demeaned_pp": sd_two_way,
        "sd_two_way_demeaned_df_corrected_pp": float(np.sqrt(rss / (n - n_countries - n_years + 1))),
        "sd_two_way_demeaned_z": sd_two_way / total_sd,
        "sd_country_means_pp": float(np.sqrt(((country_mean - y.mean()) ** 2).mean())),
    }
    out["g1_status"] = g1_status(sd_two_way, out["sd_two_way_demeaned_z"], out["share_two_way_residual"])
    return out


def g1_status(sd_pp: float, sd_z: float, residual_share: float) -> str:
    """Appendix D gate G1: green if all three thresholds hold, amber for 0.7-1.0 pp, otherwise no-go."""
    if sd_pp >= G1_GREEN_PP and sd_z >= G1_GREEN_Z and residual_share >= G1_GREEN_RESIDUAL_SHARE:
        return "GREEN (>= 1.0 pp, >= 0.20 z, residual share >= 5%)"
    if sd_pp >= G1_AMBER_PP:
        return "AMBER (0.7-1.0 pp, or other criterion unmet)"
    return "NO-GO (< 0.7 pp)"


def balanced_subset(sample: pd.DataFrame) -> pd.DataFrame:
    """Countries observed in every year of the sample window (exact orthogonal decomposition applies)."""
    years = sample["year"].nunique()
    counts = sample.groupby("eurostat_code")["year"].nunique()
    return sample[sample["eurostat_code"].isin(counts[counts == years].index)]


def moderator_at_elections(sample: pd.DataFrame, calendar: pd.DataFrame, classes: tuple[str, ...] | None = None) -> dict[str, float]:
    """Between- and within-country variation of the lagged moderator at the real election dates.

    For each in-calendar election whose year (and country) is in the sample, take ``olddep1_lag`` of that
    country-year (the value known when the election year's exposure is built), decompose it into the country
    mean over the sample (between) and the deviation from it (within), and report the SDs across elections,
    plus the SD of the country-and-year-demeaned residual at those rows. ``classes`` restricts to ``class_primary`` values (default: all elections).
    """
    elections = calendar[calendar["in_calendar"].astype(bool)].copy()
    if classes is not None:
        elections = elections[elections["class_primary"].isin(classes)]
    elections["year"] = pd.to_datetime(elections["date_used"]).dt.year
    country_mean = sample.groupby("eurostat_code")["olddep1_lag"].mean().rename("country_mean")
    sample = sample.assign(two_way_resid=_two_way_residuals(sample, "olddep1_lag"))
    merged = elections.merge(sample[["eurostat_code", "year", "olddep1_lag", "two_way_resid"]], on=["eurostat_code", "year"], how="inner")
    merged = merged.merge(country_mean, on="eurostat_code")
    within = merged["olddep1_lag"] - merged["country_mean"]
    return {
        "sd_two_way_residual_at_elections_pp": float(merged["two_way_resid"].std(ddof=0)),
        "n_elections": int(len(merged)),
        "sd_level_pp": float(merged["olddep1_lag"].std(ddof=0)),
        "sd_between_component_pp": float(merged["country_mean"].std(ddof=0)),
        "sd_within_component_pp": float(within.std(ddof=0)),
        "within_share_of_variance": float(within.var(ddof=0) / merged["olddep1_lag"].var(ddof=0)),
        "between_share_of_variance": float(merged["country_mean"].var(ddof=0) / merged["olddep1_lag"].var(ddof=0)),
    }


def sensitivity_table(panel: pd.DataFrame, end_cv: int, end_etad: int) -> pd.DataFrame:
    """Compare alternative samples: rule (cross-validated end), ETAD-trusted end, later starts, balanced subsets."""
    rows = []

    def add(label: str, frame: pd.DataFrame, end: int) -> None:
        stats = g1_statistics(frame)
        rows.append(
            {
                "sample": label,
                "t0": int(frame["year"].min()),
                "end_year": end,
                "n_countries": int(frame["eurostat_code"].nunique()),
                "n_country_years": len(frame),
                "g1_sd_two_way_pp": stats["sd_two_way_demeaned_pp"],
                "g1_share_two_way_residual": stats["share_two_way_residual"],
                "g1_status": stats["g1_status"].split(" ")[0],
            }
        )

    rule = select_sample(panel, end_cv, "joint_cv")
    add("rule (cross-validated end)", rule.sample, end_cv)
    add("rule, balanced subset", balanced_subset(rule.sample), end_cv)
    for t0 in (1996, 1997, 2002):
        window = rule.sample[rule.sample["year"] >= t0]
        counts = window.groupby("eurostat_code").size()
        window = window[window["eurostat_code"].isin(counts[counts >= MIN_OBS_PER_COUNTRY].index)]
        add(f"t0={t0} (same end, retained countries >= {MIN_OBS_PER_COUNTRY} obs)", window, end_cv)
    etad = select_sample(panel, end_etad, "joint_etad")
    add("ETAD-trusted end (country-level completeness)", etad.sample, end_etad)
    return pd.DataFrame(rows)


def main() -> None:
    """Print the selection summary (the report in ``reports/gate3_calendar_and_sample.md`` quotes this output)."""
    panel = build_panel()
    end_cv = last_common_complete_year(panel, "cv")
    end_etad = last_year_any_complete(panel, "etad")
    selection = select_sample(panel, end_cv, "joint_cv")
    print(f"rule: t0={selection.t0}, end={selection.end_year}, N={len(selection.sample)}, countries={len(selection.countries)}")
    print(per_country_coverage(selection.sample).to_string(index=False))
    print(missingness_table(panel, selection.t0, selection.end_year).to_string(index=False))
    print(selection.trace.to_string(index=False))
    print(pd.Series(g1_statistics(selection.sample)).to_string())
    print(sensitivity_table(panel, end_cv, end_etad).to_string(index=False))


if __name__ == "__main__":
    main()
