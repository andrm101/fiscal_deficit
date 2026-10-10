"""Offline tests for the joint-coverage sample rule and the G1 statistics (Gate 3a)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "evaluate"))
sys.path.insert(0, str(ROOT / "src" / "normalize"))
import countries  # noqa: E402
import sample  # noqa: E402

RAW_PRESENT = sample.CAPB_CSV.exists() and sample.OLDDEP_CSV.exists() and sample.EXPOSURE_CSV.exists()
needs_inputs = pytest.mark.skipif(not RAW_PRESENT, reason="raw inputs or interim exposure not present")


def _synthetic_panel(start_by_country: dict[str, int], years: range, joint_end: int | None = None) -> pd.DataFrame:
    rows = []
    for code, start in start_by_country.items():
        for year in years:
            rows.append({"eurostat_code": code, "year": year, "joint": year >= start and (joint_end is None or year <= joint_end)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------------------------
# Pure-logic tests
# ---------------------------------------------------------------------------------------------
def test_rule_picks_earliest_year_with_22_countries():
    starts = {f"C{i:02d}": 2000 for i in range(22)} | {"L1": 2004, "L2": 2004, "L3": 2004}
    panel = _synthetic_panel(starts, range(1995, 2031))
    selection = sample.select_sample(panel, 2030, "joint")
    assert selection.t0 == 2000
    assert set(selection.countries) == set(starts)  # the 2004 starters still have 27 observations >= 20


def test_rule_drops_countries_with_too_few_observations():
    starts = {f"C{i:02d}": 1995 for i in range(22)} | {"SHORT": 2012}
    panel = _synthetic_panel(starts, range(1995, 2022))
    selection = sample.select_sample(panel, 2021, "joint")
    assert selection.t0 == 1995
    assert "SHORT" not in selection.countries  # only 10 observations (< 20)
    assert len(selection.sample) == 22 * 27


def test_rule_moves_start_when_early_years_are_thin():
    starts = {f"C{i:02d}": 1995 for i in range(21)} | {"LATE": 1998}
    panel = _synthetic_panel(starts, range(1995, 2022))
    assert sample.select_sample(panel, 2021, "joint").t0 == 1998


def test_rule_fails_loudly_without_enough_countries():
    panel = _synthetic_panel({f"C{i:02d}": 1995 for i in range(10)}, range(1995, 2022))
    with pytest.raises(ValueError):
        sample.select_sample(panel, 2021, "joint")


def test_g1_decomposition_of_an_additive_panel_has_zero_residual():
    rng = np.random.default_rng(42)  # seed documented: only used to draw the effects
    country_effect = rng.normal(0, 3, 6)
    year_effect = np.linspace(0, 5, 10)
    rows = [
        {"eurostat_code": f"C{i}", "year": 2000 + t, "olddep1_lag": 20 + country_effect[i] + year_effect[t]}
        for i in range(6)
        for t in range(10)
    ]
    stats = sample.g1_statistics(pd.DataFrame(rows))
    assert stats["share_two_way_residual"] == pytest.approx(0, abs=1e-12)
    assert stats["share_between_country"] + stats["share_common_year_after_country"] == pytest.approx(1.0)
    assert stats["g1_status"].startswith("NO-GO")


def test_g1_residual_sd_matches_known_noise():
    rng = np.random.default_rng(42)
    n_c, n_t = 20, 25
    noise = rng.normal(0, 1.5, (n_c, n_t))
    rows = [
        {"eurostat_code": f"C{i}", "year": 1990 + t, "olddep1_lag": 10 + i + 0.3 * t + noise[i, t]} for i in range(n_c) for t in range(n_t)
    ]
    frame = pd.DataFrame(rows)
    stats = sample.g1_statistics(frame)
    # Two-way residual SD of iid N(0, 1.5^2) noise: sqrt(((G-1)(T-1) / (G T))) * 1.5 in population form.
    expected = 1.5 * np.sqrt((n_c - 1) * (n_t - 1) / (n_c * n_t))
    assert stats["sd_two_way_demeaned_pp"] == pytest.approx(expected, rel=0.1)
    assert stats["sd_two_way_demeaned_df_corrected_pp"] == pytest.approx(1.5, rel=0.1)


@pytest.mark.parametrize(
    ("sd", "z", "share", "prefix"),
    [(1.35, 0.27, 0.074, "GREEN"), (0.85, 0.2, 0.1, "AMBER"), (1.2, 0.15, 0.1, "AMBER"), (0.6, 0.1, 0.02, "NO-GO")],
)
def test_g1_status_thresholds(sd, z, share, prefix):
    assert sample.g1_status(sd, z, share).startswith(prefix)


def test_balanced_subset_keeps_only_complete_countries():
    frame = pd.DataFrame(
        {"eurostat_code": ["A"] * 3 + ["B"] * 2, "year": [2000, 2001, 2002, 2001, 2002]}
    )
    assert set(sample.balanced_subset(frame)["eurostat_code"]) == {"A"}


# ---------------------------------------------------------------------------------------------
# Tests on the real inputs
# ---------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def panel() -> pd.DataFrame:
    return sample.build_panel()


@pytest.fixture(scope="module")
def selection(panel):
    return sample.select_sample(panel, sample.last_common_complete_year(panel, "cv"), "joint_cv")


@needs_inputs
def test_panel_has_27_countries_and_no_forecast_years(panel):
    assert set(panel["eurostat_code"]) == set(countries.eu27_eurostat_codes())
    assert panel.loc[panel["capb"].notna(), "year"].max() <= 2025  # Spring 2026 vintage: 2026-27 are forecasts
    assert panel["year"].min() == 1995  # Eurostat series starts 1994 and the moderator is lagged one year


@needs_inputs
def test_moderator_is_lagged_one_year_and_flags_are_carried(panel):
    raw = pd.read_csv(sample.OLDDEP_CSV)
    raw = raw[raw["indic_de"] == "OLDDEP1"].set_index(["geo", "TIME_PERIOD"])
    row = panel[(panel["eurostat_code"] == "FR") & (panel["year"] == 2019)].iloc[0]
    assert row["olddep1_lag"] == raw.loc[("FR", 2018), "OBS_VALUE"]
    assert row["olddep1_lag_flag"] == raw.loc[("FR", 2018), "OBS_FLAG"] == "p"
    hr = panel[(panel["eurostat_code"] == "HR") & (panel["year"] == 1996)].iloc[0]
    assert pd.isna(hr["olddep1_lag"]) and pd.isna(hr["capb"])


@needs_inputs
def test_selected_sample_matches_the_rule(selection):
    assert (selection.t0, selection.end_year) == (1995, 2021)
    assert len(selection.countries) == 27
    assert len(selection.sample) == 715
    coverage = sample.per_country_coverage(selection.sample).set_index("eurostat_code")
    assert coverage.loc["HR", ["first_year", "last_year", "n_obs"]].tolist() == [2002, 2021, 20]
    assert coverage.loc["SK", "first_year"] == 1996
    assert coverage.loc[["CY", "CZ", "SI"], "first_year"].eq(1997).all()
    assert (coverage["n_obs"] >= sample.MIN_OBS_PER_COUNTRY).all()
    assert (coverage["n_gaps_inside_span"] == 0).all()
    assert selection.sample.groupby("year").size().min() >= sample.MIN_COUNTRIES_PER_YEAR


@needs_inputs
def test_negative_capb_values_are_never_dropped(selection):
    raw = pd.read_csv(sample.CAPB_CSV)
    ireland = raw[(raw["REF_AREA"] == "IRL") & (raw["TIME_PERIOD"] == 2010)]["OBS_VALUE"].iloc[0]
    kept = selection.sample[(selection.sample["eurostat_code"] == "IE") & (selection.sample["year"] == 2010)]["capb"].iloc[0]
    assert kept == ireland < -25
    assert (selection.sample["capb"] < 0).sum() > 100


@needs_inputs
def test_sample_rows_are_jointly_observed_and_complete(selection):
    s = selection.sample
    assert s["capb"].notna().all() and s["olddep1_lag"].notna().all() and s["exposure_complete_cv"].all()
    assert s["year"].max() == 2021
    assert {"olddep1_lag_flag", "capb_obs_status", "W_S", "W_E", "Post"} <= set(s.columns)


@needs_inputs
def test_g1_on_final_sample_is_green_and_consistent(selection):
    stats = sample.g1_statistics(selection.sample)
    assert stats["n_obs"] == 715
    shares = stats["share_between_country"] + stats["share_common_year_after_country"] + stats["share_two_way_residual"]
    assert shares == pytest.approx(1.0)
    assert stats["sd_two_way_demeaned_pp"] >= sample.G1_GREEN_PP
    assert stats["g1_status"].startswith("GREEN")
    balanced = sample.g1_statistics(sample.balanced_subset(selection.sample))
    assert balanced["n_countries"] == 22 and balanced["n_obs"] == 22 * 27


@needs_inputs
def test_moderator_variation_at_real_election_dates(selection):
    calendar = pd.read_csv(sample.CALENDAR_CSV)
    stats = sample.moderator_at_elections(selection.sample, calendar)
    assert stats["n_elections"] > 150
    assert stats["sd_between_component_pp"] > 2.0 and stats["sd_within_component_pp"] > 2.0
    assert stats["between_share_of_variance"] + stats["within_share_of_variance"] == pytest.approx(1.0, abs=0.02)
    assert 0.5 < stats["sd_two_way_residual_at_elections_pp"] < stats["sd_within_component_pp"]
