"""Gate 4 controls at ``t - 1`` for the confirmatory model M1 and the pre-registered coverage trigger T4.

Definitions (registry ``config/registry/confirmatory.toml``; contract ``gold.panel_country_year``)
-----------------------------------------------------------------------------------------------
``outgap_lag``
    AMECO ``AVGDGP`` (output gap, per cent of potential GDP) at ``t - 1``. AMECO area codes are mapped to Eurostat
    codes through ``config/countries.csv`` (Greece is ``GRC`` in AMECO and ``EL`` in Eurostat; Romania is ``ROM``).
    The last two years of the Spring vintage are forecasts and are excluded before lagging (rule of
    ``normalize/ameco.py``); AMECO publishes no per-observation forecast flag.
``debt_gdp_lag``
    Eurostat ``gov_10dd_edpt1`` ``GD``, ``PC_GDP``, sector S13, at ``t - 1``.
``ig_diff_lag``
    Interest-growth differential at ``t - 1``, in **percentage points**::

        i_t  = D41PAY_t / GD_{t-1}                (interest paid, million euro, over lagged gross debt, million euro)
        g_t  = GDP_t / GDP_{t-1} - 1              (nominal GDP growth, B1GQ CP_MEUR)
        ig_t = 100 * (i_t - g_t) / (1 + g_t)      (the debt-dynamics term: change in the debt ratio is ig_t * d_{t-1})
        ig_diff_lag at year t = ig_{t-1}

    so the control for year ``t`` needs ``D41PAY_{t-1}``, ``GD_{t-2}``, ``GDP_{t-1}`` and ``GDP_{t-2}``. For
    ``t = 1995`` that is 1993 inputs for ``GD`` and ``GDP``. Years are matched by an explicit calendar join, never by
    a row shift, so a missing year yields a missing control instead of a misaligned one.
``euro_member``
    ``1`` in year ``t`` when ``t >= euro_adoption_year`` of ``config/countries.csv`` (the year the euro was
    adopted counts as a member year), else ``0``; countries without an adoption year are never members. The
    contract gives this column no lag suffix: it is a status known in advance, not a lagged outcome.

Observation flags (``p``, ``b``, ...) of the Eurostat inputs are carried: ``debt_gdp_lag_flag`` and
``ig_diff_lag_flag`` hold the distinct non-missing flags of the contributing observations joined by ``+``.

Trigger T4 (blueprint 7.3): on the confirmatory sample, if the joint complete-case coverage of the four controls is
below ``COVERAGE_THRESHOLD`` (97 per cent), drop ``ig_diff_lag``; if the coverage of the remaining set is still below
the threshold, drop ``debt_gdp_lag``. ``outgap_lag`` and ``euro_member`` are always kept. The rule is mechanical and
reads no outcome.
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
import eurostat  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AVGDGP_CSV = ameco.AMECO_DIR / "sdmx" / "AMECO_CHAPTER06-05_AVGDGP.csv"

COVERAGE_THRESHOLD = 0.97  # pre-registered (contract gold.panel_country_year, trigger T4)
PCT_PER_UNIT = 100.0  # i, g are fractions; the control is expressed in percentage points
DROP_ORDER = ("ig_diff_lag", "debt_gdp_lag")  # T4 order; the two controls below are never dropped
ALWAYS_KEPT = ("outgap_lag", "euro_member")
ALL_CONTROLS = ("outgap_lag", "debt_gdp_lag", "ig_diff_lag", "euro_member")

# Code values assumed in config/acquisition/gate4_controls_and_secondary.toml (dataset, unit, na_item, cofog99).
ASSUMED_CODES = [
    ("gov_10a_main", "PC_GDP", "B9", None), ("gov_10a_main", "PC_GDP", "D41PAY", None), ("gov_10a_main", "PC_GDP", "TR", None),
    ("gov_10a_main", "PC_GDP", "TE", None), ("gov_10a_main", "PC_GDP", "D62PAY", None), ("gov_10a_main", "PC_GDP", "D632PAY", None),
    ("gov_10a_main", "MIO_EUR", "D41PAY", None),
    ("gov_10a_exp", "PC_GDP", "TE", "TOTAL"), ("gov_10a_exp", "PC_GDP", "TE", "GF10"), ("gov_10a_exp", "PC_GDP", "TE", "GF1002"),
    ("gov_10a_exp", "PC_GDP", "TE", "GF07"),
    ("gov_10dd_edpt1", "PC_GDP", "GD", None), ("gov_10dd_edpt1", "MIO_EUR", "GD", None),
    ("nama_10_gdp", "CP_MEUR", "B1GQ", None),
]


# ---------------------------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------------------------
def _join_flags(*flags: pd.Series) -> pd.Series:
    """Distinct non-missing flags of aligned Series joined by ``+`` (missing when none)."""
    table = pd.concat([f.astype("object") for f in flags], axis=1)
    joined = table.apply(lambda r: "+".join(sorted({str(v) for v in r if isinstance(v, str)})), axis=1)
    return joined.where(joined != "", None)


def read_output_gap(path: Path = AVGDGP_CSV) -> pd.DataFrame:
    """AMECO ``AVGDGP`` as ``(eurostat_code, year, outgap)`` for observed years only (forecast years removed)."""
    frame = ameco.read_sdmx_csv(path)
    last_observed = ameco.last_observed_year(int(frame["TIME_PERIOD"].max()), "spring")
    to_eurostat = countries.ameco_to_eurostat()
    frame = frame[frame["REF_AREA"].isin(to_eurostat) & (frame["TIME_PERIOD"] <= last_observed)]
    out = pd.DataFrame(
        {"eurostat_code": frame["REF_AREA"].map(to_eurostat).to_numpy(), "year": frame["TIME_PERIOD"].to_numpy(), "outgap": frame["OBS_VALUE"].to_numpy(float)}
    )
    if out.duplicated(["eurostat_code", "year"]).any():
        raise ValueError("duplicate (country, year) in AVGDGP")
    return out


def output_gap_lag(outgap: pd.DataFrame) -> pd.DataFrame:
    """``outgap_lag`` at year ``t`` equals the observed output gap at ``t - 1``."""
    lagged = outgap.assign(year=outgap["year"] + 1).rename(columns={"outgap": "outgap_lag"})
    return lagged[["eurostat_code", "year", "outgap_lag"]]


def _lag_series(series: pd.DataFrame, lag: int, value: str, flag: str) -> pd.DataFrame:
    """Series ``(geo, year, value, obs_flag)`` re-indexed so that the value at ``t - lag`` appears in year ``t``."""
    shifted = series.assign(year=series["year"] + lag)
    return shifted.rename(columns={"value": value, "obs_flag": flag})[["geo", "year", value, flag]]


def interest_growth_differential(interest: pd.DataFrame, debt_mio: pd.DataFrame, gdp: pd.DataFrame) -> pd.DataFrame:
    """Contemporaneous ``ig_t = 100 (i_t - g_t) / (1 + g_t)`` by ``(geo, year)`` with the contributing flags.

    ``interest`` is ``D41PAY`` MIO_EUR, ``debt_mio`` is ``GD`` MIO_EUR, ``gdp`` is ``B1GQ`` CP_MEUR, each a
    ``(geo, year, value, obs_flag)`` series. ``i_t = D41PAY_t / GD_{t-1}`` and ``g_t = GDP_t / GDP_{t-1} - 1``.
    """
    merged = interest.rename(columns={"value": "d41", "obs_flag": "f_d41"})
    merged = merged.merge(_lag_series(debt_mio, 1, "gd_prev", "f_gd"), on=["geo", "year"], how="left")
    merged = merged.merge(gdp.rename(columns={"value": "gdp", "obs_flag": "f_gdp"}), on=["geo", "year"], how="left")
    merged = merged.merge(_lag_series(gdp, 1, "gdp_prev", "f_gdp_prev"), on=["geo", "year"], how="left")
    rate = merged["d41"] / merged["gd_prev"]
    growth = merged["gdp"] / merged["gdp_prev"] - 1.0
    merged["ig"] = PCT_PER_UNIT * (rate - growth) / (1.0 + growth)
    merged["ig_flag"] = _join_flags(merged["f_d41"], merged["f_gd"], merged["f_gdp"], merged["f_gdp_prev"])
    return merged[["geo", "year", "ig", "ig_flag"]]


def euro_member(codes: pd.Series, years: pd.Series, crosswalk: pd.DataFrame | None = None) -> pd.Series:
    """Euro-area membership in year ``t``: ``t >= euro_adoption_year`` (never for countries without adoption year)."""
    crosswalk = countries.load_countries() if crosswalk is None else crosswalk
    adoption = codes.map(dict(zip(crosswalk["eurostat_code"], crosswalk["euro_adoption_year"].astype("float"), strict=True)))
    return (years.to_numpy(float) >= adoption.to_numpy(float)).astype(int)


def build_controls(long: pd.DataFrame | None = None, outgap: pd.DataFrame | None = None) -> pd.DataFrame:
    """Controls table by ``(eurostat_code, year)`` over every year for which some input exists.

    Columns: ``outgap_lag``, ``debt_gdp_lag``, ``debt_gdp_lag_flag``, ``ig_diff_lag``, ``ig_diff_lag_flag``,
    ``euro_member``. Rows are created for the union of the available years; values are NaN where an input is missing.
    """
    long = eurostat.read_eurostat_dir() if long is None else long
    outgap = read_output_gap() if outgap is None else outgap
    debt = eurostat.select_series(long, dataset="gov_10dd_edpt1", unit="PC_GDP", na_item="GD")
    debt_lag = _lag_series(debt, 1, "debt_gdp_lag", "debt_gdp_lag_flag").rename(columns={"geo": "eurostat_code"})
    ig = interest_growth_differential(
        eurostat.select_series(long, dataset="gov_10a_main", unit="MIO_EUR", na_item="D41PAY"),
        eurostat.select_series(long, dataset="gov_10dd_edpt1", unit="MIO_EUR", na_item="GD"),
        eurostat.select_series(long, dataset="nama_10_gdp", unit="CP_MEUR", na_item="B1GQ"),
    )
    ig_lag = _lag_series(ig.rename(columns={"ig": "value", "ig_flag": "obs_flag"}), 1, "ig_diff_lag", "ig_diff_lag_flag").rename(columns={"geo": "eurostat_code"})
    table = output_gap_lag(outgap).merge(debt_lag, on=["eurostat_code", "year"], how="outer").merge(ig_lag, on=["eurostat_code", "year"], how="outer")
    table["euro_member"] = euro_member(table["eurostat_code"], table["year"])
    return table.sort_values(["eurostat_code", "year"]).reset_index(drop=True)


def attach_controls(sample_frame: pd.DataFrame, controls: pd.DataFrame | None = None) -> pd.DataFrame:
    """Left-join the controls onto a sample frame (``eurostat_code``, ``year``); the row count must not change."""
    controls = build_controls() if controls is None else controls
    merged = sample_frame.merge(controls, on=["eurostat_code", "year"], how="left", validate="one_to_one")
    if len(merged) != len(sample_frame):
        raise ValueError("control merge changed the number of rows")
    merged["euro_member"] = euro_member(merged["eurostat_code"], merged["year"])  # status is defined for every year
    return merged


# ---------------------------------------------------------------------------------------------
# Trigger T4
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class T4Result:
    """Outcome of the pre-registered coverage rule on a sample."""

    n_sample: int
    individual_coverage: dict[str, float]
    steps: list[dict[str, object]]
    surviving: list[str]
    dropped: list[str]
    n_complete: int

    @property
    def joint_coverage_final(self) -> float:
        """Joint complete-case coverage of the surviving controls."""
        return self.n_complete / self.n_sample


def joint_coverage(frame: pd.DataFrame, controls: tuple[str, ...] | list[str]) -> float:
    """Share of rows with every listed control non-missing."""
    return float(frame[list(controls)].notna().all(axis=1).mean())


def apply_t4_rule(frame: pd.DataFrame, threshold: float = COVERAGE_THRESHOLD) -> T4Result:
    """Apply the pre-registered drop order to a frame that already carries the four controls.

    Joint coverage is the share of sample rows in which *all currently retained* controls are observed. The
    drop order is ``ig_diff_lag`` then ``debt_gdp_lag``; ``outgap_lag`` and ``euro_member`` are always kept even if
    their coverage is low (it is then reported, not acted on).
    """
    retained = list(ALL_CONTROLS)
    steps: list[dict[str, object]] = [{"step": "all four controls", "retained": list(retained), "joint_coverage": joint_coverage(frame, retained)}]
    dropped: list[str] = []
    for candidate in DROP_ORDER:
        if joint_coverage(frame, retained) >= threshold:
            break
        retained.remove(candidate)
        dropped.append(candidate)
        steps.append({"step": f"drop {candidate}", "retained": list(retained), "joint_coverage": joint_coverage(frame, retained)})
    individual = {c: float(frame[c].notna().mean()) for c in ALL_CONTROLS}
    n_complete = int(frame[retained].notna().all(axis=1).sum())
    return T4Result(len(frame), individual, steps, retained, dropped, n_complete)


# ---------------------------------------------------------------------------------------------
# Verification and report
# ---------------------------------------------------------------------------------------------
def verify_assumed_codes(long: pd.DataFrame) -> pd.DataFrame:
    """For each assumed ``(dataset, unit, na_item, cofog99)``: rows present, countries, first/last year, flags, negatives."""
    rows = []
    for dataset, unit, item, cofog in ASSUMED_CODES:
        mask = (long["dataset"] == dataset) & (long["unit"] == unit) & (long["na_item"] == item)
        if cofog is not None:
            mask &= long["cofog99"] == cofog
        sub = long[mask]
        flags = sub["obs_flag"].value_counts().to_dict()
        rows.append({
            "dataset": dataset, "unit": unit, "item": item + (f"/{cofog}" if cofog else ""), "present": bool(len(sub) > 0),
            "rows": len(sub), "non_missing": int(sub["value"].notna().sum()), "countries": int(sub["geo"].nunique()),
            "first_year": int(sub["year"].min()) if len(sub) else None, "last_year": int(sub["year"].max()) if len(sub) else None,
            "flags": ", ".join(f"{k}:{v}" for k, v in sorted(flags.items())) or "none", "negatives": int((sub["value"] < 0).sum()),
        })
    return pd.DataFrame(rows)


def per_country_series_coverage(long: pd.DataFrame, outgap: pd.DataFrame) -> pd.DataFrame:
    """First year, last year and number of observations by country for the five input series of the controls."""
    series = {
        "GD % GDP": eurostat.select_series(long, dataset="gov_10dd_edpt1", unit="PC_GDP", na_item="GD").rename(columns={"geo": "eurostat_code"}),
        "GD mio EUR": eurostat.select_series(long, dataset="gov_10dd_edpt1", unit="MIO_EUR", na_item="GD").rename(columns={"geo": "eurostat_code"}),
        "D41PAY mio EUR": eurostat.select_series(long, dataset="gov_10a_main", unit="MIO_EUR", na_item="D41PAY").rename(columns={"geo": "eurostat_code"}),
        "B1GQ": eurostat.select_series(long, dataset="nama_10_gdp", unit="CP_MEUR", na_item="B1GQ").rename(columns={"geo": "eurostat_code"}),
        "AVGDGP": outgap.rename(columns={"outgap": "value"}),
    }
    pieces = []
    for label, frame in series.items():
        ok = frame.dropna(subset=["value"])
        agg = ok.groupby("eurostat_code")["year"].agg(["min", "max", "count"])
        agg.columns = [f"{label} first", f"{label} last", f"{label} n"]
        pieces.append(agg)
    return pd.concat(pieces, axis=1).reset_index()


def coverage_by_year(frame: pd.DataFrame) -> pd.DataFrame:
    """Per year of the sample: rows and number of non-missing values of each control."""
    grouped = frame.groupby("year")
    out = pd.DataFrame({"rows": grouped.size()})
    for c in ALL_CONTROLS:
        out[c] = grouped[c].apply(lambda s: int(s.notna().sum()))
    return out.reset_index()


def main() -> None:
    """Write ``reports/gate4_controls_coverage.md`` from the raw files and the confirmatory sample (no outcome model)."""
    sys.path.insert(0, str(PROJECT_ROOT / "src" / "evaluate"))
    import power  # noqa: E402  (md_table only)
    import sample  # noqa: E402

    long = eurostat.read_eurostat_dir()
    outgap = read_output_gap()
    codes = verify_assumed_codes(long)
    panel = sample.build_panel()
    final = sample.select_sample(panel, sample.last_common_complete_year(panel, "cv"), "joint_cv").sample
    frame = attach_controls(final)
    t4 = apply_t4_rule(frame)
    by_year = coverage_by_year(frame)
    fmt = power.md_table
    lines = [
        "# Gate 4: Eurostat controls, verified codes and the T4 coverage trigger",
        "",
        "Generated by `python src/features/controls.py` (reader `src/normalize/eurostat.py`, controls `src/features/controls.py`, tests `tests/test_eurostat_sdmx.py`, `tests/test_controls.py`). Offline; raw files are read-only. No outcome model was run: only the presence of control values on the confirmatory sample is counted.",
        "",
        "## 1. Verified code values (config/acquisition/gate4_controls_and_secondary.toml)",
        "",
        fmt(codes),
        "",
        f"All {int(codes['present'].sum())} of {len(codes)} assumed code combinations are present. Negative values are preserved by the reader (R01): "
        f"{int((long['value'] < 0).sum())} negative observations across the six files. Flags found: {long['obs_flag'].value_counts().to_dict()}.",
        "",
        "## 2. Input availability by country (first year, last year, observations)",
        "",
        fmt(per_country_series_coverage(long, outgap), floatfmt=".0f"),
        "",
        "## 3. Control definitions",
        "",
        "See the module docstring of `src/features/controls.py`. In short: `outgap_lag` = AMECO AVGDGP at t-1 (forecast years excluded); `debt_gdp_lag` = GD % of GDP at t-1; `ig_diff_lag` = (i-g)/(1+g) at t-1 in percentage points with i_t = D41PAY_t / GD_{t-1} and g_t = GDP_t / GDP_{t-1} - 1, which needs D41PAY_{t-1}, GD_{t-2}, GDP_{t-1}, GDP_{t-2}; `euro_member` = 1 when year >= euro adoption year.",
        "",
        "## 4. Trigger T4 on the confirmatory sample",
        "",
        f"Confirmatory sample: N = {t4.n_sample} country-years, {frame['eurostat_code'].nunique()} countries, {int(frame['year'].min())}-{int(frame['year'].max())}.",
        "",
        "Individual coverage (share of the 715 rows with the control observed):",
        "",
        fmt(pd.DataFrame({"control": list(t4.individual_coverage), "coverage": [f"{100 * v:.1f}%" for v in t4.individual_coverage.values()]})),
        "",
        "Pre-registered sequential rule (drop `ig_diff_lag` first, then `debt_gdp_lag`; keep `outgap_lag` and `euro_member`; threshold 97%):",
        "",
        fmt(pd.DataFrame([{"step": s["step"], "retained": ", ".join(s["retained"]), "joint coverage": f"{100 * s['joint_coverage']:.1f}%"} for s in t4.steps])),
        "",
        f"**Surviving controls: {', '.join(t4.surviving)}. Dropped: {', '.join(t4.dropped) or 'none'}. N with all surviving controls observed: {t4.n_complete} of {t4.n_sample} ({100 * t4.joint_coverage_final:.1f}%).**",
        "",
        "Observations of the sample by year with each control observed:",
        "",
        fmt(by_year, floatfmt=".0f"),
        "",
    ]
    lost = frame[~frame[t4.surviving].notna().all(axis=1)]
    if len(lost):
        lines += ["Rows lost to the surviving controls (country year): " + ", ".join(f"{c} {y}" for c, y in zip(lost["eurostat_code"], lost["year"])) + ".", ""]
    lines += ["## 5. Why the dropped controls fail, and what it implies", ""]
    for control, why in (
        ("ig_diff_lag", "needs `GD_{t-2}`, `GDP_{t-2}` and `D41PAY_{t-1}`. Eurostat's EDP debt series starts in 1995, so the control cannot exist for 1995 and 1996 in any country (and Denmark's debt starts in 2000)"),
        ("debt_gdp_lag", "needs `GD_{t-1}`; for t = 1995 that is 1994, which Eurostat does not publish (all 1995 rows are missing), and Denmark's series starts in 2000"),
    ):
        miss = frame[frame[control].isna()]
        by_year = miss.groupby("year").size()
        lines.append(f"* `{control}` is missing in {len(miss)} of {len(frame)} rows ({100 * len(miss) / len(frame):.1f}%); it {why}. Missing rows by year: " + ", ".join(f"{y}: {n}" for y, n in by_year.items()) + ".")
    gap = frame[frame["outgap_lag"].isna()]
    lines += [
        f"* `outgap_lag` is missing in {len(gap)} rows: AMECO's AVGDGP starts in 1995 for several new members and in 1996-2001 for others, so the lag exists only from the second year. It is always kept, so the model sample shrinks.",
        "",
        f"**Consequences (not acted on; decisions for the registry freeze).** (1) The T4 rule as written drops debt on a margin of {100 * (COVERAGE_THRESHOLD - t4.individual_coverage['debt_gdp_lag']):.1f} points; a debt series reaching back to 1994 (not in the acquired files) would have kept it. (2) Keeping `outgap_lag` makes the model sample N = {t4.n_complete}, not 715, which conflicts with the contract line 'exactly 715 rows'; either the contract is amended for the controls model or the 715-row extract is kept and the control model is reported on the complete-case subset. "
        "(3) Euro membership has full coverage (status convention: member in year t when t >= adoption year, from `config/countries.csv`).",
        "",
    ]
    out_path = PROJECT_ROOT / "reports" / "gate4_controls_coverage.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out_path.relative_to(PROJECT_ROOT)}; surviving {t4.surviving}; N {t4.n_complete}")


if __name__ == "__main__":
    main()
