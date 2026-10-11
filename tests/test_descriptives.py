"""Tests for the Tier-1 descriptives: the freeze-rule guard, the statistics on synthetic panels, and the real-data checks."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
for sub in ("evaluate", "features", "normalize"):
    sys.path.insert(0, str(ROOT / "src" / sub))
import descriptives as d  # noqa: E402
import sample  # noqa: E402

REAL = sample.CAPB_CSV.exists() and sample.OLDDEP_CSV.exists() and (ROOT / "data" / "raw" / "eurostat_controls").exists() and d.CALENDAR_CSV.exists() and d.EXPOSURE_CSV.exists()
needs_raw = pytest.mark.skipif(not REAL, reason="raw inputs not present")


# ---------------------------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("outcome", ["capb", "capb_two_way_residual", "sec_revenue", "sec_d_capb", "sec_cyclical_component"])
@pytest.mark.parametrize("exposure", ["W_S", "W_E", "W_D", "W_U", "Post", "w_s", "W_S_gf", "date_used", "class_primary", "n_elections_held", "touches_unclassified_or_delayed"])
def test_guard_raises_for_every_outcome_exposure_pair(outcome, exposure):
    with pytest.raises(d.FreezeRuleViolation, match="freeze rule"):
        d.assert_no_exposure_with_outcome(["eurostat_code", "year", outcome, exposure])


def test_guard_allows_outcomes_alone_exposures_alone_and_completeness_flags():
    d.assert_no_exposure_with_outcome(["eurostat_code", "year", "capb", "olddep1_lag", "outgap_lag", "sec_revenue"])
    d.assert_no_exposure_with_outcome(["eurostat_code", "year", "W_S", "W_E", "W_D", "W_U", "Post", "class_primary", "date_used"])
    d.assert_no_exposure_with_outcome(["capb", "olddep1_lag", "exposure_complete_cv"])  # right-censoring flag is not an exposure value
    d.assert_no_exposure_with_outcome(["sec_revenue", "exposure_complete_etad"])
    d.assert_no_exposure_with_outcome([])


def test_guard_error_names_the_offending_columns():
    with pytest.raises(d.FreezeRuleViolation) as info:
        d.assert_no_exposure_with_outcome(["capb", "Post", "W_S"])
    assert "capb" in str(info.value) and "Post" in str(info.value) and "W_S" in str(info.value)


def test_select_columns_is_guarded_and_returns_the_requested_columns():
    frame = pd.DataFrame({"capb": [1.0], "W_S": [0.5], "olddep1_lag": [20.0]})
    assert list(d.select_columns(frame, ["capb", "olddep1_lag"]).columns) == ["capb", "olddep1_lag"]
    with pytest.raises(d.FreezeRuleViolation):
        d.select_columns(frame, ["capb", "W_S"])


def test_a_calendar_routine_cannot_be_given_an_outcome_column():
    cal = pd.DataFrame({"eurostat_code": ["AA"], "date_used": [pd.Timestamp("2000-05-01")], "class_primary": ["scheduled"], "capb": [1.0]})
    with pytest.raises(d.FreezeRuleViolation):
        d.select_columns(cal, ["eurostat_code", "date_used", "capb"])
    assert len(d.calendar_by_year(cal)) == 1  # the routine reads only its own outcome-free columns


# ---------------------------------------------------------------------------------------------
# Synthetic panel
# ---------------------------------------------------------------------------------------------
def synthetic_panel(n_countries: int = 6, years: range = range(1995, 2013), seed: int = 42) -> pd.DataFrame:
    """Gold-like panel with every column the routines read; seed documented (fixture only)."""
    rng = np.random.default_rng(seed)
    idx = pd.MultiIndex.from_product([[f"C{i}" for i in range(n_countries)], years], names=["eurostat_code", "year"]).to_frame(index=False)
    n = len(idx)
    country_fe = idx["eurostat_code"].map({f"C{i}": float(i) for i in range(n_countries)})
    year_fe = 0.2 * (idx["year"] - years.start)
    idx["capb"] = country_fe + year_fe + rng.normal(0, 1, n)
    idx["olddep1_lag"] = 20 + 0.3 * (idx["year"] - years.start) + 0.5 * country_fe + rng.normal(0, 0.3, n)
    idx["outgap_lag"] = rng.normal(0, 1, n)
    idx["debt_gdp_lag"] = rng.normal(60, 10, n)
    idx["ig_diff_lag"] = rng.normal(-1, 1, n)
    idx["euro_member"] = rng.integers(0, 2, n).astype(bool)
    for column in d.SECONDARY_SERIES:
        idx[column] = rng.normal(20, 2, n)
    idx["sec_primary_balance_edp"] = rng.normal(0, 1, n)
    idx["sec_cyclical_component"] = rng.normal(0, 1, n) * (1 + idx["eurostat_code"].map({f"C{i}": float(i) for i in range(n_countries)}))
    idx["exposure_complete_cv"] = True
    idx["in_confirmatory"] = True
    for column in d.EXPOSURE_VARIABLES:
        idx[column] = rng.uniform(0, 1, n)
    return idx


def test_two_way_demean_removes_additive_effects_exactly():
    panel = synthetic_panel()
    panel["additive"] = panel["eurostat_code"].map({f"C{i}": 3.0 * i for i in range(6)}) + 0.5 * (panel["year"] - 1995)
    resid = d.two_way_demean(panel, ["additive"])["additive"]
    assert np.abs(resid).max() < 1e-9


def test_two_way_demean_handles_unbalanced_panels_and_matches_sample_module():
    panel = synthetic_panel().drop(index=[0, 1, 30, 31, 32])
    ours = d.two_way_demean(panel, ["capb"])["capb"].to_numpy()
    theirs = sample._two_way_residuals(panel.reset_index(drop=True), "capb")
    assert np.allclose(ours, theirs, atol=1e-9)


def test_residual_cells_ranks_a_planted_outlier_first_and_uses_no_exposure():
    panel = synthetic_panel()
    panel.loc[(panel["eurostat_code"] == "C2") & (panel["year"] == 2005), "capb"] -= 25.0
    top = d.residual_cells(panel, k=3)
    assert (top.loc[0, "eurostat_code"], int(top.loc[0, "year"])) == ("C2", 2005)
    assert list(top.columns) == ["eurostat_code", "year", "capb", "capb_two_way_residual"]
    assert top["capb_two_way_residual"].abs().is_monotonic_decreasing


def test_capb_summary_decomposition_adds_up():
    s = d.capb_summary(synthetic_panel())
    assert s["share_between"] + s["share_common_year"] + s["share_two_way_residual"] == pytest.approx(1.0)
    assert s["n_obs"] == 108 and s["n_countries"] == 6
    assert s["sd_two_way"] <= s["sd_within_country"] + 1e-9 <= s["sd_pooled_pop"] + 1e-6


def test_pooled_ar1_recovers_known_coefficient_and_pairs_skip_gaps():
    rng = np.random.default_rng(42)  # seed: fixture only
    n_c, n_t, rho = 200, 40, 0.6
    e = np.zeros((n_c * n_t,))
    for c in range(n_c):
        x = rng.normal()
        for t in range(n_t):
            x = rho * x + np.sqrt(1 - rho**2) * rng.normal()
            e[c * n_t + t] = x
    codes = np.repeat(np.arange(n_c), n_t)
    years = np.tile(np.arange(n_t), n_c)
    assert d.pooled_ar1(e, codes, years, False)[0] == pytest.approx(rho, abs=0.03)
    assert d.pooled_ar1(e, codes, years, True)[0] == pytest.approx(rho, abs=0.03)
    cur, prev = d._pairs(np.array(["a", "a", "a", "b", "b"]), np.array([1, 2, 4, 1, 2]))
    assert cur.tolist() == [1, 4] and prev.tolist() == [0, 3]  # the 2 -> 4 gap is not a pair


def test_indirect_inference_correction_moves_the_estimate_up_towards_the_truth():
    rng = np.random.default_rng(7)  # seed: fixture only
    rows, rho = [], 0.6
    for c in range(27):
        x = rng.normal()
        for year in range(1995, 2022):
            x = rho * x + np.sqrt(1 - rho**2) * rng.normal()
            rows.append({"eurostat_code": f"C{c:02d}", "year": year, "capb": x})
    panel = pd.DataFrame(rows)
    table = d.persistence_table(panel)
    assert table["raw_pooled"] < table["nickell_analytic"] < 0.85
    assert table["country_standardised"] < table["simulation_corrected"]
    assert table["simulation_corrected"] == pytest.approx(rho, abs=0.12)
    assert table["n_pairs"] == 27 * 26


def test_indirect_inference_is_deterministic_for_a_fixed_seed():
    panel = synthetic_panel(n_countries=5, years=range(1995, 2010))
    a = d.corrected_rho_indirect(panel, 0.4, n_sim=100, seed=42)
    b = d.corrected_rho_indirect(panel, 0.4, n_sim=100, seed=42)
    assert a == b


def test_coverage_matrix_and_missing_cells_table():
    panel = synthetic_panel(n_countries=3, years=range(2000, 2006))
    panel.loc[(panel["eurostat_code"] == "C0") & (panel["year"].isin([2000, 2001])), "capb"] = np.nan
    panel.loc[(panel["eurostat_code"] == "C1") & (panel["year"] == 2000), "olddep1_lag"] = np.nan
    panel.loc[(panel["eurostat_code"] == "C2") & (panel["year"] == 2005), "exposure_complete_cv"] = False
    matrix = d.coverage_matrix(panel)
    assert matrix.loc["C0", 2000] == 1 and matrix.loc["C1", 2000] == 2 and matrix.loc["C2", 2005] == 4 and matrix.loc["C0", 2003] == 0
    table = d.missing_cells_table(panel)
    assert table["n"].sum() == 4 and set(table["eurostat_code"]) == {"C0", "C1", "C2"}
    assert table.loc[table["eurostat_code"] == "C0", "years"].iloc[0] == "2000-2001"


def test_capb_by_year_quantiles():
    panel = synthetic_panel()
    by_year = d.capb_by_year(panel)
    assert len(by_year) == 18 and (by_year["q25"] <= by_year["median"]).all() and (by_year["median"] <= by_year["q75"]).all()
    assert by_year["n"].eq(6).all()


def test_illustrative_countries_rule_is_deterministic_and_election_free():
    panel = synthetic_panel()
    picks = d.illustrative_countries(panel)
    chosen = picks[picks["pick"] != ""].set_index("pick")["eurostat_code"].to_dict()
    assert chosen["largest"] == "C5" and chosen["smallest"] in {"C0", "C1"}
    assert picks["mean_abs_cyclical_pp"].is_monotonic_increasing
    again = d.illustrative_countries(panel.sample(frac=1.0, random_state=42))  # seed: fixture only
    assert again["eurostat_code"].tolist() == picks["eurostat_code"].tolist()
    election_changed = panel.assign(W_S=1.0, Post=0.0)
    assert d.illustrative_countries(election_changed.drop(columns=d.EXPOSURE_VARIABLES))["pick"].tolist() == picks["pick"].tolist()


def test_within_correlations_and_vif_on_known_structure():
    rng = np.random.default_rng(123)  # seed: fixture only; differs from the panel's seed so the noise terms are independent
    panel = synthetic_panel(n_countries=8, years=range(1995, 2020))
    n = len(panel)
    base = rng.normal(0, 1, n)
    panel["outgap_lag"] = base
    panel["ig_diff_lag"] = base + rng.normal(0, 0.05, n)  # nearly collinear after demeaning
    panel["debt_gdp_lag"] = rng.normal(0, 1, n)
    matrix, pairs = d.within_correlations(panel)
    assert matrix.loc["outgap_lag", "ig_diff_lag"] > 0.95
    assert abs(matrix.loc["debt_gdp_lag", "outgap_lag"]) < 0.2
    assert (matrix.to_numpy() == matrix.to_numpy().T).all() and (np.diag(matrix) == 1).all()
    assert pairs["n"].eq(n).all() and (pairs["95% CI low"] <= pairs["r (within)"]).all() and (pairs["r (within)"] <= pairs["95% CI high"]).all()
    assert "exposure" not in " ".join(matrix.columns).lower() and not any(d.is_exposure_column(c) for c in matrix.columns)
    vif = d.within_vif(panel, ["olddep1_lag", "outgap_lag", "debt_gdp_lag", "ig_diff_lag"]).set_index("regressor")
    assert vif.loc["outgap_lag", "VIF (within)"] > d.VIF_FLAG and vif.loc["outgap_lag", "flag"] == "VIF > 5"
    assert vif.loc["debt_gdp_lag", "VIF (within)"] < 1.5


def test_within_vif_of_orthogonal_regressors_is_one():
    rng = np.random.default_rng(123)  # seed: fixture only
    panel = synthetic_panel(n_countries=10, years=range(1995, 2025))
    panel["outgap_lag"] = rng.normal(0, 1, len(panel))
    panel["debt_gdp_lag"] = rng.normal(0, 1, len(panel))
    vif = d.within_vif(panel, ["outgap_lag", "debt_gdp_lag"])
    assert (vif["VIF (within)"] < 1.1).all()


def test_ageing_groups_split_27_countries_by_accession_year():
    groups = d.ageing_groups()
    assert len(groups) == 27 and sum(g.startswith("EU-15") for g in groups.values()) == 14
    assert groups["SE"].startswith("EU-15") and groups["PL"].startswith("Accession") and groups["HR"].startswith("Accession")


def test_ageing_dispersion_and_summary_on_synthetic_panel():
    panel = synthetic_panel(n_countries=5, years=range(1995, 2022))
    disp = d.ageing_dispersion(panel)
    assert set(disp["year"]) == {1995, 2021} and disp["n"].eq(5).all()
    assert d.ageing_summary(panel)["sd_two_way_demeaned_pp"] < 1.0  # additive by construction + 0.3 noise


def calendar_fixture() -> pd.DataFrame:
    dates = ["1994-05-03", "1995-01-10", "1999-06-06", "2004-03-03", "2022-12-01", "2023-05-21"]
    classes = ["unclassified", "scheduled", "early", "scheduled", "early", "unclassified"]
    return pd.DataFrame({"eurostat_code": ["AA", "AA", "BB", "BB", "BB", "AA"], "date_used": pd.to_datetime(dates), "class_primary": classes, "class_rule": "r", "class_gap": "g"})


def test_calendar_tables_count_classes_and_window():
    cal = calendar_fixture()
    by_year = d.calendar_by_year(cal).set_index("year")
    assert by_year.loc[1994, "unclassified"] == 1 and by_year.loc[2023, "total"] == 1 and by_year["total"].sum() == 6
    by_country = d.calendar_by_country(cal).set_index("eurostat_code")
    assert by_country.loc["AA", "total"] == 2 and by_country.loc["BB", "early"] == 2  # 2023 election is outside 1994-2022
    uncl = d.unclassified_elections(cal)
    assert len(uncl) == 2 and uncl["touches_1995_2021"].tolist() == [True, False]


def test_exposure_distribution_counts_and_shares():
    exposure = pd.DataFrame({"eurostat_code": ["AA"] * 4, "year": [1995, 1996, 1997, 2030], "W_S": [0.0, 0.5, 1.0, 0.9], "W_E": 0.0, "W_D": 0.0, "W_U": 0.0, "Post": [0.2, 0.0, 0.0, 0.4]})
    table = d.exposure_distribution(exposure).set_index("variable")
    assert table.loc["W_S", "n country-years"] == 3 and table.loc["W_S", "share > 0 (%)"] == pytest.approx(200 / 3)
    assert table.loc["W_S", "share = 1 (%)"] == pytest.approx(100 / 3)
    shares = d.any_positive_share(exposure)
    assert shares["n"] == 3 and shares["any_pre_window_%"] == pytest.approx(200 / 3)


def test_every_panel_routine_goes_through_the_guard(monkeypatch):
    seen: list[list[str]] = []
    real_guard = d.assert_no_exposure_with_outcome

    def spy(columns):
        cols = list(columns)
        seen.append(cols)
        real_guard(cols)

    monkeypatch.setattr(d, "assert_no_exposure_with_outcome", spy)
    panel = synthetic_panel(n_countries=4, years=range(1995, 2010))
    routines = [
        d.coverage_matrix, d.missing_cells_table, d.capb_summary, d.residual_cells, d.capb_by_year, d.ageing_summary, d.ageing_dispersion,
        d.ageing_group_table, d.secondary_medians, d.illustrative_countries, d.within_correlations,
        lambda p: d.within_vif(p, ["olddep1_lag", "outgap_lag"]),
    ]
    for routine in routines:
        before = len(seen)
        routine(panel)  # the full panel (with exposure columns present) is passed in
        assert len(seen) > before, f"{getattr(routine, '__name__', routine)} did not call the guard"
    for columns in seen:
        assert not any(d.is_exposure_column(c) for c in columns) or not any(d.is_outcome_column(c) for c in columns)
    cal = calendar_fixture()
    for routine in (d.calendar_by_year, d.calendar_by_country, d.unclassified_elections):
        before = len(seen)
        routine(cal)
        assert len(seen) > before
    before = len(seen)
    d.exposure_distribution(panel)
    d.any_positive_share(panel)
    assert len(seen) >= before + 2
    assert not any(any(d.is_outcome_column(c) for c in columns) for columns in seen[-6:])  # exposure routines read no outcome


def test_output_tables_never_mix_outcome_and_exposure_columns():
    panel = synthetic_panel(n_countries=4, years=range(1995, 2010))
    tables = [d.residual_cells(panel), d.capb_by_year(panel), d.secondary_medians(panel), d.illustrative_countries(panel), d.within_correlations(panel)[1], d.missing_cells_table(panel)]
    for table in tables:
        cols = list(table.columns) + [str(i) for i in table.index if isinstance(i, str)]
        d.assert_no_exposure_with_outcome(cols)


# ---------------------------------------------------------------------------------------------
# Real data
# ---------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def real_extract() -> pd.DataFrame:
    panel = d.load_panel()
    return panel[panel["in_confirmatory"]].reset_index(drop=True)


@needs_raw
def test_real_ageing_two_way_sd_matches_the_audited_figure(real_extract):
    age = d.ageing_summary(real_extract)
    assert age["sd_two_way_demeaned_pp"] == pytest.approx(d.GATE3A_TWO_WAY_SD_PP, abs=0.005)
    assert age["n_obs"] == 715 and age["share_two_way_residual"] == pytest.approx(0.075, abs=0.002)


@needs_raw
def test_real_capb_outlier_and_persistence_are_near_the_gate3_figures(real_extract):
    top = d.residual_cells(real_extract)
    assert (top.loc[0, "eurostat_code"], int(top.loc[0, "year"])) == ("IE", 2010) and len(top) == 10
    summary = d.capb_summary(real_extract)
    assert summary["n_obs"] == 715 and summary["n_negative"] == 330 and summary["min"] == pytest.approx(-27.62, abs=0.01)
    rho = d.persistence_table(real_extract)
    assert rho["n_pairs"] == 688
    assert abs(rho["country_standardised"] - 0.562) < 0.05 and abs(rho["simulation_corrected"] - 0.694) < 0.05


@needs_raw
def test_real_calendar_facts():
    cal = d.load_calendar()
    assert len(cal) == 248
    uncl = d.unclassified_elections(cal)
    assert len(uncl) == 21 and int(uncl["touches_1995_2021"].sum()) == 19
    counts = cal["class_primary"].value_counts().to_dict()
    assert counts == {"scheduled": 143, "early": 75, "unclassified": 29, "delayed": 1}
    by_country = d.calendar_by_country(cal)
    assert set(by_country.loc[by_country["scheduled"] == 0, "eurostat_code"]) == {"CY", "EL", "MT"}


@needs_raw
def test_full_report_runs_through_the_guard_and_writes_300_dpi_figures(tmp_path, monkeypatch):
    seen: list[list[str]] = []
    real_guard = d.assert_no_exposure_with_outcome
    monkeypatch.setattr(d, "assert_no_exposure_with_outcome", lambda cols: (seen.append(list(cols)), real_guard(cols))[1])
    monkeypatch.setattr(d, "FIG_DIR", tmp_path / "figures")
    text = d.build_report(d.load_panel(), d.load_calendar(), pd.read_csv(d.EXPOSURE_CSV))
    assert len(seen) >= 20
    assert not any(any(d.is_exposure_column(c) for c in cols) and any(d.is_outcome_column(c) for c in cols) for cols in seen)
    pngs = sorted((tmp_path / "figures").glob("*.png"))
    assert len(pngs) == 9
    from PIL import Image

    for path in pngs:
        with Image.open(path) as image:
            dpi = image.info.get("dpi", (0, 0))
            assert round(dpi[0]) >= 300, path.name
    assert "What these descriptives do not show" in text and "preregistration-v1" in text
