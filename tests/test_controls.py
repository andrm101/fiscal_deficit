"""Offline tests for the Gate 4 controls (``src/features/controls.py``) and the T4 coverage rule."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "features"))
sys.path.insert(0, str(ROOT / "src" / "normalize"))
import controls  # noqa: E402
import eurostat  # noqa: E402


def series(geo: str, years: list[int], values: list[float], flags: dict[int, str] | None = None) -> pd.DataFrame:
    """A ``(geo, year, value, obs_flag)`` series."""
    flags = flags or {}
    return pd.DataFrame({"geo": geo, "year": years, "value": values, "obs_flag": [flags.get(y) for y in years]})


YEARS = [2000, 2001, 2002, 2003]
D41 = series("AA", YEARS, [10.0, 12.0, 11.0, 9.0], {2001: "p"})
GD = series("AA", YEARS, [200.0, 220.0, 230.0, 240.0])
GDP = series("AA", YEARS, [1000.0, 1050.0, 1100.0, 1200.0], {2000: "b"})


def test_interest_growth_formula_on_synthetic_frame():
    ig = controls.interest_growth_differential(D41, GD, GDP).set_index("year")["ig"]
    i_2001, g_2001 = 12.0 / 200.0, 1050.0 / 1000.0 - 1
    i_2002, g_2002 = 11.0 / 220.0, 1100.0 / 1050.0 - 1
    assert np.isnan(ig.loc[2000])  # needs GD_1999 and GDP_1999
    assert ig.loc[2001] == pytest.approx(100 * (i_2001 - g_2001) / (1 + g_2001))
    assert ig.loc[2001] == pytest.approx(0.952381, abs=1e-6)  # percentage points
    assert ig.loc[2002] == pytest.approx(100 * (i_2002 - g_2002) / (1 + g_2002))


def test_negative_differential_survives():
    gdp_fast = series("AA", YEARS, [1000.0, 1200.0, 1500.0, 1800.0])
    ig = controls.interest_growth_differential(D41, GD, gdp_fast)
    assert (ig["ig"].dropna() < 0).all() and ig["ig"].notna().sum() == 3


def test_flags_of_contributing_inputs_are_carried_and_joined():
    ig = controls.interest_growth_differential(D41, GD, GDP).set_index("year")["ig_flag"]
    assert ig.loc[2001] == "b+p"  # D41PAY_2001 = p, GDP_{2000} = b
    assert ig.loc[2002] is None or pd.isna(ig.loc[2002])


def test_missing_year_gives_missing_control_not_a_misaligned_one():
    gdp_gap = GDP[GDP["year"] != 2001].reset_index(drop=True)
    ig = controls.interest_growth_differential(D41, GD, gdp_gap).set_index("year")["ig"]
    assert np.isnan(ig.loc[2001]) and np.isnan(ig.loc[2002])  # both need GDP_2001
    assert ig.loc[2003] == pytest.approx(100 * ((9.0 / 230.0) - (1200 / 1100 - 1)) / (1200 / 1100))


def long_table() -> pd.DataFrame:
    """Synthetic silver table with the three Eurostat inputs for one country, 2000-2003, plus the t=1995-style gap."""
    rows = []
    for dataset, unit, item, frame in (
        ("gov_10a_main", "MIO_EUR", "D41PAY", D41), ("gov_10dd_edpt1", "MIO_EUR", "GD", GD), ("nama_10_gdp", "CP_MEUR", "B1GQ", GDP),
        ("gov_10dd_edpt1", "PC_GDP", "GD", series("AA", YEARS, [20.0, 21.0, 20.9, 20.0], {2003: "p"})),
    ):
        rows.append(frame.assign(dataset=dataset, unit=unit, na_item=item, sector="S13", cofog99=None).rename(columns={"geo": "geo"}))
    return pd.concat(rows, ignore_index=True)[["geo", "year", "dataset", "unit", "sector", "cofog99", "na_item", "value", "obs_flag"]]


def test_build_controls_lags_every_control_by_one_year():
    outgap = pd.DataFrame({"eurostat_code": "AA", "year": YEARS, "outgap": [-1.0, 0.5, 1.5, -2.0]})
    table = controls.build_controls(long_table(), outgap).set_index("year")
    assert table.loc[2001, "outgap_lag"] == -1.0 and table.loc[2004, "outgap_lag"] == -2.0
    assert table.loc[2002, "debt_gdp_lag"] == 21.0 and table.loc[2004, "debt_gdp_lag_flag"] == "p"
    ig = controls.interest_growth_differential(D41, GD, GDP).set_index("year")["ig"]
    assert table.loc[2003, "ig_diff_lag"] == pytest.approx(ig.loc[2002])  # ig at t-1
    assert np.isnan(table.loc[2001, "ig_diff_lag"])  # needs ig_2000, which needs GD_1999 and GDP_1999
    assert table.loc[2002, "ig_diff_lag"] == pytest.approx(ig.loc[2001])  # first year with a value: inputs reach back to t-2


def test_euro_membership_convention_adoption_year_counts():
    crosswalk = pd.DataFrame({"eurostat_code": ["EL", "DK", "SK"], "euro_adoption_year": pd.array([2001, pd.NA, 2009], dtype="Int64")})
    codes = pd.Series(["EL", "EL", "EL", "DK", "SK", "SK"])
    years = pd.Series([2000, 2001, 2002, 2020, 2008, 2009])
    assert controls.euro_member(codes, years, crosswalk).tolist() == [0, 1, 1, 0, 0, 1]


def ameco_csv(tmp_path: Path) -> Path:
    """AMECO-format SDMX-CSV with GRC, ROM, a non-EU aggregate and two forecast years (2026, 2027)."""
    rows = [(a, y, v) for a, base in (("GRC", 1.0), ("ROM", 2.0), ("EU27", 9.0), ("USA", 7.0)) for y, v in zip(range(2023, 2028), [base + k for k in range(5)])]
    frame = pd.DataFrame(rows, columns=["REF_AREA", "TIME_PERIOD", "OBS_VALUE"])
    path = tmp_path / "AVGDGP.csv"
    frame.to_csv(path, index=False)
    return path


def test_forecast_years_excluded_and_ameco_codes_mapped(tmp_path):
    gap = controls.read_output_gap(ameco_csv(tmp_path))
    assert set(gap["eurostat_code"]) == {"EL", "RO"}  # GRC -> EL, ROM -> RO; aggregates and non-members dropped
    assert gap["year"].max() == 2025  # Spring vintage ending 2027: 2026 and 2027 are forecasts
    lagged = controls.output_gap_lag(gap)
    assert lagged["year"].max() == 2026 and lagged[lagged["eurostat_code"] == "EL"].set_index("year").loc[2024, "outgap_lag"] == 1.0


def test_negative_output_gap_survives(tmp_path):
    path = ameco_csv(tmp_path)
    frame = pd.read_csv(path)
    frame.loc[frame["REF_AREA"] == "GRC", "OBS_VALUE"] *= -1
    frame.to_csv(path, index=False)
    assert (controls.read_output_gap(path).query("eurostat_code == 'EL'")["outgap"] < 0).all()


def make_t4_frame(n: int, missing_ig: int, missing_debt: int, missing_gap: int = 0) -> pd.DataFrame:
    """Frame of ``n`` rows with the given numbers of missing values placed on disjoint rows."""
    frame = pd.DataFrame({c: np.ones(n) for c in controls.ALL_CONTROLS})
    frame.loc[:missing_ig - 1, "ig_diff_lag"] = np.nan
    frame.loc[missing_ig:missing_ig + missing_debt - 1, "debt_gdp_lag"] = np.nan
    start = missing_ig + missing_debt
    frame.loc[start:start + missing_gap - 1, "outgap_lag"] = np.nan
    return frame


def test_t4_keeps_everything_when_coverage_is_sufficient():
    result = controls.apply_t4_rule(make_t4_frame(1000, 10, 10))
    assert result.dropped == [] and result.n_complete == 980


def test_t4_drops_interest_growth_first_then_debt():
    result = controls.apply_t4_rule(make_t4_frame(1000, 50, 20))  # joint 93%; without ig 98%
    assert result.dropped == ["ig_diff_lag"] and result.surviving == ["outgap_lag", "debt_gdp_lag", "euro_member"] and result.n_complete == 980
    result = controls.apply_t4_rule(make_t4_frame(1000, 50, 50))  # without ig still 95%
    assert result.dropped == ["ig_diff_lag", "debt_gdp_lag"] and result.surviving == ["outgap_lag", "euro_member"]


def test_t4_never_drops_output_gap_or_euro_membership():
    result = controls.apply_t4_rule(make_t4_frame(1000, 50, 50, missing_gap=200))
    assert "outgap_lag" in result.surviving and "euro_member" in result.surviving
    assert result.joint_coverage_final < controls.COVERAGE_THRESHOLD  # reported, not acted on


# ---------------------------------------------------------------------------------------------
# Real data (read-only); skipped when absent
# ---------------------------------------------------------------------------------------------
needs_raw = pytest.mark.skipif(
    not ((eurostat.EUROSTAT_DIR / "gov_10dd_edpt1_gd_pc_gdp_1993_2025.csv").exists() and controls.AVGDGP_CSV.exists()), reason="raw inputs absent"
)


@needs_raw
def test_real_output_gap_maps_greece_and_excludes_forecasts():
    gap = controls.read_output_gap()
    assert "EL" in set(gap["eurostat_code"]) and "GR" not in set(gap["eurostat_code"]) and "RO" in set(gap["eurostat_code"])
    assert gap["eurostat_code"].nunique() == 27 and gap["year"].max() == 2025
    assert (gap["outgap"] < 0).any()


@needs_raw
def test_real_controls_have_no_row_beyond_expected_lags_and_euro_status_is_binary():
    table = controls.build_controls()
    assert set(table["euro_member"].unique()) <= {0, 1}
    el = table[(table["eurostat_code"] == "EL")].set_index("year")
    assert el.loc[2000, "euro_member"] == 0 and el.loc[2001, "euro_member"] == 1
    assert el.loc[2000, "outgap_lag"] == pytest.approx(controls.read_output_gap().query("eurostat_code == 'EL' and year == 1999")["outgap"].iloc[0])
    long = eurostat.read_eurostat_dir()
    gd = eurostat.select_series(long, dataset="gov_10dd_edpt1", unit="PC_GDP", na_item="GD").set_index(["geo", "year"])["value"]
    assert el.loc[2005, "debt_gdp_lag"] == gd.loc[("EL", 2004)]
