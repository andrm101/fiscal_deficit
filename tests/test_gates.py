"""Tests for the failing quality gates (remediation R03): synthetic panels, and the no-file-on-failure rule."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "evaluate"))
import gates  # noqa: E402

N_COUNTRIES = 27
YEARS = list(range(1995, 2022))
LAST_OBSERVED = 2025


def make_panel(n_countries: int = N_COUNTRIES, years: list[int] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """A clean synthetic window panel (all rows confirmatory) and the matching source CAPB table."""
    years = YEARS if years is None else years
    rng = np.random.default_rng(42)  # seed documented: synthetic fixture only
    index = pd.MultiIndex.from_product([[f"C{i:02d}" for i in range(n_countries)], years], names=["eurostat_code", "year"]).to_frame(index=False)
    n = len(index)
    panel = index.assign(
        capb=rng.normal(-1.0, 3.0, n), olddep1_lag=rng.normal(24.0, 4.0, n), exposure_complete_cv=True, in_confirmatory=True,
        W_S=rng.uniform(0, 1, n), W_E=rng.uniform(0, 1, n), W_D=0.0, W_U=rng.uniform(0, 0.2, n), Post=rng.uniform(0, 1, n),
    )
    return panel, panel[["eurostat_code", "year", "capb"]].copy()


def cfg_for(panel: pd.DataFrame, **overrides) -> gates.GateConfig:
    """Config whose count targets match the clean synthetic extract, so a single defect trips a single gate."""
    extract = panel[panel["in_confirmatory"]]
    base = {"confirmatory_rows": len(extract), "confirmatory_countries": int(extract["eurostat_code"].nunique()), "year_max": 2030}
    return gates.GateConfig(**{**base, **overrides})


def failed(results: list[gates.GateResult]) -> set[str]:
    return {r.name for r in results if not r.passed}


def run(panel: pd.DataFrame, source: pd.DataFrame, cfg: gates.GateConfig) -> list[gates.GateResult]:
    return gates.run_gates(panel, source, LAST_OBSERVED, cfg)


def test_clean_panel_passes_every_gate():
    panel, source = make_panel()
    results = run(panel, source, cfg_for(panel))
    assert failed(results) == set()
    assert len(results) == 13


def test_contract_parameters_match_the_documented_numbers():
    cfg = gates.GateConfig.from_contract()
    assert (cfg.confirmatory_rows, cfg.confirmatory_countries) == (715, 27)
    assert (cfg.year_min, cfg.year_max, cfg.coverage_min, cfg.min_obs_per_country) == (1995, 2021, 0.97, 20)
    assert (cfg.capb_lower_exclusive, cfg.capb_upper_exclusive) == (-50.0, 30.0)


def test_panel_at_94_percent_coverage_fails_and_enforce_raises():
    panel, source = make_panel()
    drop = np.arange(len(panel)) % 17 == 0  # 43 of 729 cells, 5.9% missing
    panel.loc[drop, "capb"] = np.nan
    panel["in_confirmatory"] = panel["capb"].notna()
    cfg = cfg_for(panel)
    assert failed(run(panel, source, cfg)) == {"coverage_capb"}
    coverage = panel["capb"].notna().mean()
    assert 0.93 < coverage < 0.95
    with pytest.raises(gates.GateFailure) as info:
        gates.enforce_gates(panel, source, LAST_OBSERVED, cfg)
    assert "coverage_capb" in str(info.value) and not all(r.passed for r in info.value.results)


def test_97_percent_threshold_is_inclusive_and_96_9_fails():
    panel, source = make_panel(n_countries=10, years=list(range(1995, 2005)))  # 100 cells
    panel.loc[:2, "capb"] = np.nan  # 3 missing = 97.0%
    panel["in_confirmatory"] = panel["capb"].notna()
    assert "coverage_capb" not in failed(run(panel, source, cfg_for(panel)))
    panel.loc[3, "capb"] = np.nan  # 4 missing = 96.0%
    panel["in_confirmatory"] = panel["capb"].notna()
    assert "coverage_capb" in failed(run(panel, source, cfg_for(panel)))


def test_low_moderator_coverage_fails():
    panel, source = make_panel()
    panel.loc[np.arange(len(panel)) % 10 == 0, "olddep1_lag"] = np.nan
    panel["in_confirmatory"] = panel["olddep1_lag"].notna()
    assert failed(run(panel, source, cfg_for(panel))) == {"coverage_olddep1_lag"}


def test_duplicated_key_fails():
    panel, source = make_panel()
    panel = pd.concat([panel, panel.iloc[[5]]], ignore_index=True)
    got = failed(run(panel, source, cfg_for(panel)))
    assert "unique_key" in got


@pytest.mark.parametrize("bad", [30.0, 35.0, -50.0, -60.0])
def test_capb_out_of_range_fails(bad):
    panel, source = make_panel()
    panel.loc[10, "capb"] = bad
    source.loc[10, "capb"] = bad  # keep the source identical so only the range gate trips
    assert failed(run(panel, source, cfg_for(panel))) == {"capb_range"}


def test_capb_just_inside_the_bounds_passes():
    panel, source = make_panel()
    panel.loc[10, "capb"] = 29.99
    panel.loc[11, "capb"] = -49.99
    source[["capb"]] = panel[["capb"]]
    assert failed(run(panel, source, cfg_for(panel))) == set()


@pytest.mark.parametrize("column,bad", [("W_S", 1.2), ("W_E", -0.01), ("Post", 1.0001)])
def test_exposure_outside_unit_interval_fails(column, bad):
    panel, source = make_panel()
    panel.loc[3, column] = bad
    assert failed(run(panel, source, cfg_for(panel))) == {"exposure_range"}


def test_missing_exposure_on_extract_fails():
    panel, source = make_panel()
    panel.loc[3, "W_U"] = np.nan
    assert "exposure_range" in failed(run(panel, source, cfg_for(panel)))


def test_forecast_year_row_fails():
    panel, source = make_panel()
    extra = panel.iloc[[0]].copy()
    extra["year"] = 2026  # AMECO Spring 2026: observed through 2025, 2026-2027 are forecasts
    panel = pd.concat([panel, extra], ignore_index=True)
    source = pd.concat([source, extra[["eurostat_code", "year", "capb"]]], ignore_index=True)
    assert failed(run(panel, source, cfg_for(panel, year_max=2030))) == {"no_forecast_year"}


def test_year_after_2021_fails_the_window_gate():
    panel, source = make_panel()
    extra = panel.iloc[[0]].copy()
    extra["year"] = 2022
    extra["in_confirmatory"] = False
    panel = pd.concat([panel, extra], ignore_index=True)
    got = failed(run(panel, source, gates.GateConfig(confirmatory_rows=len(panel) - 1, confirmatory_countries=N_COUNTRIES)))
    assert got == {"year_window"}


def test_exposure_incomplete_on_extract_fails():
    panel, source = make_panel()
    panel.loc[7, "exposure_complete_cv"] = False
    assert failed(run(panel, source, cfg_for(panel))) == {"exposure_complete_on_extract"}


def test_extract_row_and_country_counts_must_equal_the_contract():
    panel, source = make_panel()
    cfg = cfg_for(panel)
    short = panel.copy()
    short.loc[0, "in_confirmatory"] = False
    assert "extract_row_count" in failed(run(short, source, cfg))
    fewer = panel[panel["eurostat_code"] != "C00"]
    assert "extract_country_count" in failed(run(fewer, source, cfg))


def test_country_with_fewer_than_20_observations_fails():
    panel, source = make_panel()
    short_rows = panel.index[(panel["eurostat_code"] == "C03") & (panel["year"] > 2012)]
    panel.loc[short_rows, "in_confirmatory"] = False  # C03 keeps 18 confirmatory rows
    got = failed(run(panel, source, cfg_for(panel)))
    assert "country_min_obs" in got


def test_a_country_with_exactly_20_observations_passes():
    panel, source = make_panel()
    short_rows = panel.index[(panel["eurostat_code"] == "C03") & (panel["year"] > 2014)]
    panel.loc[short_rows, "in_confirmatory"] = False  # 20 left
    assert "country_min_obs" not in failed(run(panel, source, cfg_for(panel)))


def test_extract_rows_without_capb_or_moderator_fail():
    panel, source = make_panel()
    panel.loc[4, "olddep1_lag"] = np.nan  # still flagged confirmatory
    assert "extract_complete_cases" in failed(run(panel, source, cfg_for(panel)))


def test_removed_negative_capb_fails():
    panel, source = make_panel()
    neg = panel.index[panel["capb"] < 0][:5]
    assert len(neg) == 5
    panel.loc[neg, "capb"] = panel.loc[neg, "capb"].abs()  # a pipeline that clipped or flipped deficits
    assert failed(run(panel, source, cfg_for(panel))) == {"negative_capb_preserved"}


def test_missing_required_column_is_reported_as_schema_failure():
    panel, source = make_panel()
    results = run(panel.drop(columns=["Post"]), source, cfg_for(panel))
    assert [r.name for r in results] == ["schema"] and not results[0].passed


def test_enforce_returns_results_when_clean():
    panel, source = make_panel()
    results = gates.enforce_gates(panel, source, LAST_OBSERVED, cfg_for(panel))
    assert all(r.passed for r in results)
    assert "PASS" in gates.format_results(results)


def test_failing_panel_writes_nothing_and_cli_exits_nonzero(tmp_path):
    """A failing build leaves no file (not even the directory) and ``main`` returns a non-zero status."""
    out = tmp_path / "gold"
    code = (
        "import sys; sys.path.insert(0, 'src/features'); sys.path.insert(0, 'tests')\n"
        "from pathlib import Path\n"
        "import numpy as np, panel, test_gates\n"
        "p, s = test_gates.make_panel(); p.loc[::17, 'capb'] = np.nan; p['in_confirmatory'] = p['capb'].notna()\n"
        "build = panel.GoldBuild(p, [], p.iloc[0:0], s, 2025, {})\n"
        "panel.build_gold_panel = lambda inputs=None: build\n"
        f"panel.GOLD_DIR = Path(r'{out}')\n"
        f"panel.write_gold_panel.__defaults__ = (Path(r'{out}'), None)\n"
        "sys.exit(panel.main())\n"
    )
    done = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=False)
    assert done.returncode == 1, done.stderr
    assert "GATE FAILURE" in done.stderr
    assert not out.exists()
