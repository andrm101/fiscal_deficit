"""Tests of the thesis results figures (``src/evaluate/figures.py``).

Fast: every figure function runs on small synthetic inputs and must write a non-empty 300-dpi PNG without mutating its inputs. The JSON helpers
are also run on the committed result files (read only). Two tests use the real gold panel through ``m1.load_real_panel`` (tag-guarded,
hash-checked) and are skipped, with the reason, if it cannot be loaded.
"""
from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
from PIL import Image  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
import sys  # noqa: E402

for sub in ("models/py", "evaluate", "normalize", "features"):
    sys.path.insert(0, str(ROOT / "src" / sub))
import figures  # noqa: E402
import power_variants as pv  # noqa: E402

HEADLINE_JSON = ROOT / "reports" / "results" / "m1_confirmatory.json"
ROBUSTNESS_JSON = ROOT / "reports" / "results" / "robustness.json"


# ---------------------------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------------------------
def _target(estimate: float, lo: float, hi: float, p_holm: float | None, reading: str | None, role: str) -> dict:
    return {"name": "x", "role": role, "estimate": estimate, "ci_lo": lo, "ci_hi": hi, "p_bootstrap": p_holm, "p_holm": p_holm, "reading": reading}


@pytest.fixture()
def headline() -> dict:
    return {"source": "supplied", "n_obs": 100, "n_countries": 8, "sesoi_pp": 0.5, "targets": {
        "beta_S": _target(-0.4, -0.7, -0.1, 0.03, "excludes zero", "confirmatory"),
        "gamma_B": _target(0.2, -0.1, 0.5, 0.15, "equivalent within +-sesoi", "confirmatory"),
        "gamma_W": _target(-0.3, -1.5, 1.0, None, None, "descriptive")}}


def _row(rid: str, group: str, lo: float, est: float, hi: float, status: str = "ok") -> dict:
    return {"id": rid, "group": group, "label": f"spec {rid}", "inference": "CR1", "status": status,
            "targets": {"beta_S": {"estimate": est, "ci_lo": lo, "ci_hi": hi}} if status == "ok" else {}}


@pytest.fixture()
def robustness(headline: dict) -> dict:
    return {"meta": {"sesoi_pp": 0.5}, "headline": {"targets": {"beta_S": headline["targets"]["beta_S"]}},
            "sections": {"A": {"rows": [_row("z-last-id", "A", -0.8, -0.4, 0.1), _row("a-first-id", "A", -0.9, -0.3, -0.05), _row("m", "A", -0.5, -0.2, 0.2)]},
                         "B": {"rho_hat": 0.6},  # a section without rows is ignored
                         "C": {"rows": [_row("c1", "C", -0.5, -0.4, -0.3)]}}}


@pytest.fixture()
def panel() -> pd.DataFrame:
    rng = np.random.default_rng(3)
    rows = [(code, year) for code in ("AT", "EL", "BE", "CY", "DE") for year in range(1995, 2011)]
    frame = pd.DataFrame(rows, columns=["eurostat_code", "year"])
    frame["capb"] = rng.normal(0, 2, len(frame))
    frame.loc[(frame["eurostat_code"] == "CY") & (frame["year"] < 1999), "capb"] = np.nan
    return frame


@pytest.fixture()
def events() -> pd.DataFrame:
    return pd.DataFrame({"eurostat_code": ["AT", "AT", "EL", "BE", "CY", "DE", "DE"], "year": [1999, 2003, 2000, 2007, 2005, 1998, 2002]})


@pytest.fixture()
def design():
    rng = np.random.default_rng(5)
    rows = [(f"C{c}", year) for c in range(8) for year in range(2000, 2022)]
    frame = pd.DataFrame(rows, columns=["eurostat_code", "year"])
    n = len(frame)
    frame["W_S"] = np.where(rng.random(n) < 0.35, rng.random(n), 0.0)
    frame["W_E"] = np.where(rng.random(n) < 0.2, rng.random(n), 0.0)
    frame["W_D"] = 0.0
    frame["W_U"] = np.where(rng.random(n) < 0.1, rng.random(n), 0.0)
    frame["Post"] = np.where(rng.random(n) < 0.3, rng.random(n), 0.0)
    frame["olddep1_lag"] = 20 + frame["eurostat_code"].str[1:].astype(int) * 1.5 + (frame["year"] - 2000) * 0.2 + rng.normal(0, 0.3, n)
    frame["capb"] = -0.5 * frame["W_S"] + rng.normal(0, 1, n)
    return pv.build_variant_design(frame, "synthetic", era=True, control_names=())


def _assert_png(path: Path) -> None:
    assert path.exists() and path.stat().st_size > 1000
    with Image.open(path) as image:
        assert image.format == "PNG"
        dpi = image.info.get("dpi")
        assert dpi is not None and round(dpi[0]) == figures.DPI and round(dpi[1]) == figures.DPI
        assert image.size[0] > 500 and image.size[1] > 300


# ---------------------------------------------------------------------------------------------
# JSON helpers (also on the committed files)
# ---------------------------------------------------------------------------------------------
def test_headline_rows_and_sesoi(headline: dict) -> None:
    rows = figures.headline_rows(headline)
    assert [r["name"] for r in rows] == ["beta_S", "gamma_B", "gamma_W"]
    assert rows[2]["p_holm"] is None and rows[0]["p_holm"] == 0.03
    assert figures.sesoi_of(headline) == 0.5
    with pytest.raises(KeyError):
        figures.headline_rows({"targets": {"beta_S": headline["targets"]["beta_S"]}})


def test_ladder_rows_order_skip_and_counts(robustness: dict) -> None:
    rows, skipped = figures.ladder_rows(robustness)
    assert [r["id"] for r in rows] == ["headline", "z-last-id", "a-first-id", "m"]  # file order, not sorted by id or estimate
    assert skipped == 0 and [r["excludes_zero"] for r in rows[1:]] == [False, True, False]
    robustness["sections"]["A"]["rows"].append(_row("bad", "A", 0, 0, 0, status="failed"))
    rows2, skipped2 = figures.ladder_rows(robustness)
    assert skipped2 == 1 and len(rows2) == len(rows)
    both, _ = figures.ladder_rows(robustness, sections=("A", "C"))
    assert both[-1]["id"] == "c1"
    assert figures.sesoi_of(robustness) == 0.5


@pytest.mark.skipif(not (HEADLINE_JSON.exists() and ROBUSTNESS_JSON.exists()), reason="committed result files not present")
def test_json_helpers_on_the_real_files() -> None:
    headline = figures.load_json(HEADLINE_JSON)
    rows = figures.headline_rows(headline)
    assert len(rows) == 3 and rows[0]["p_holm"] is not None and rows[2]["p_holm"] is None
    robustness = figures.load_json(ROBUSTNESS_JSON)
    ladder, skipped = figures.ladder_rows(robustness)
    section = robustness["sections"]["A"]["rows"]
    assert ladder[0]["kind"] == "headline" and len(ladder) - 1 + skipped == len(section)
    assert [r["id"] for r in ladder[1:]] == [r["id"] for r in section if r["status"] == "ok"]
    summary = robustness["summary"]["A"]
    assert sum(r["excludes_zero"] for r in ladder[1:]) == summary["beta_S"]["excludes_zero"]
    assert figures.sesoi_of(robustness) == figures.sesoi_of(headline)


# ---------------------------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------------------------
def test_clustered_mean_ci_matches_hand_computation() -> None:
    x = np.array([1.0, 3.0, 2.0, 6.0, np.nan])
    g = np.array(["a", "a", "b", "c", "c"])
    out = figures.clustered_mean_ci(x, g)
    se = np.sqrt(3 / 2 * (4.0 + 1.0 + 9.0)) / 4  # cluster sums of (x - mean): -2, -1, +3; G = 3, n = 4
    assert out["n"] == 4 and out["n_clusters"] == 3 and out["mean"] == pytest.approx(3.0)
    from scipy import stats

    half = stats.t.ppf(0.975, 2) * se
    assert out["ci_lo"] == pytest.approx(3.0 - half) and out["ci_hi"] == pytest.approx(3.0 + half)
    single = figures.clustered_mean_ci([1.0, 2.0], ["a", "a"])
    assert np.isnan(single["ci_lo"]) and single["n"] == 2


def test_event_window_values_k_and_gap_handling() -> None:
    panel = pd.DataFrame({"eurostat_code": ["AA"] * 5, "year": [2000, 2001, 2003, 2004, 2005], "capb": [1.0, 2.0, 5.0, 4.0, 6.0]})
    events = pd.DataFrame({"eurostat_code": ["AA"], "year": [2003]})
    out = figures.event_window_values(panel, events, window=2).set_index("k")
    assert sorted(out.index) == [-2, 0, 1, 2]  # 2002 (k=-1) is not observed
    assert out.loc[0, "deviation"] == pytest.approx(5.0 - 3.6)
    assert np.isnan(out.loc[0, "change"])  # 2002 is not observed: no year-on-year change in 2003
    assert out.loc[1, "change"] == pytest.approx(-1.0)


def test_fwl_slope_equals_the_ols_coefficient(design) -> None:
    out = figures.partial_association_inputs(design)
    ols_coefficient = float(design.h["beta_S"] @ design.y)
    assert out["slope"] == pytest.approx(ols_coefficient, rel=1e-8, abs=1e-10)
    assert len(out["x"]) == design.n_obs and out["bins"]["n"].sum() == design.n_obs


def test_heatmap_matrix_orders_by_iso_code_not_by_outcome(panel: pd.DataFrame) -> None:
    matrix = figures.heatmap_matrix(panel, {"AT": "AT", "EL": "GR", "BE": "BE", "CY": "CY", "DE": "DE"})
    assert list(matrix.index) == ["AT", "BE", "CY", "DE", "GR"]
    assert list(matrix.columns) == sorted(matrix.columns) and matrix.shape == (5, 16)
    assert matrix.loc["CY"].isna().sum() == 4


# ---------------------------------------------------------------------------------------------
# Figures: PNG, 300 dpi, inputs untouched
# ---------------------------------------------------------------------------------------------
def test_f1_headline_estimates(tmp_path: Path, headline: dict) -> None:
    before = copy.deepcopy(headline)
    _assert_png(figures.figure_headline_estimates(headline, tmp_path / "f1.png"))
    assert headline == before


def test_f2_election_window_profile(tmp_path: Path, panel: pd.DataFrame, events: pd.DataFrame) -> None:
    p0, e0 = panel.copy(), events.copy()
    _assert_png(figures.figure_election_window_profile(panel, events, tmp_path / "f2.png"))
    pd.testing.assert_frame_equal(panel, p0)
    pd.testing.assert_frame_equal(events, e0)


def test_f3_partial_association(tmp_path: Path, design, headline: dict) -> None:
    x0, y0, q0 = design.x.copy(), design.y.copy(), design.q_fe.copy()
    h0 = copy.deepcopy(headline)
    _assert_png(figures.figure_partial_association(design, headline, tmp_path / "f3.png"))
    assert np.array_equal(design.x, x0) and np.array_equal(design.y, y0) and np.array_equal(design.q_fe, q0) and headline == h0


def test_f4_inference_ladder_regenerates_with_more_rows(tmp_path: Path, robustness: dict) -> None:
    before = copy.deepcopy(robustness)
    small = figures.figure_inference_ladder(robustness, tmp_path / "f4a.png")
    _assert_png(small)
    assert robustness == before
    robustness["sections"]["A"]["rows"] += [_row(f"extra{i}", "A", -0.6, -0.3, 0.0 + 0.05 * i) for i in range(6)]
    big = figures.figure_inference_ladder(robustness, tmp_path / "f4b.png")
    _assert_png(big)
    with Image.open(small) as a, Image.open(big) as b:
        assert b.size[1] > a.size[1]  # taller: the added rows are drawn


def test_f5_heatmap(tmp_path: Path, panel: pd.DataFrame, events: pd.DataFrame) -> None:
    p0, e0 = panel.copy(), events.copy()
    _assert_png(figures.figure_capb_heatmap(panel, events, tmp_path / "f5.png", iso2={"EL": "GR"}))
    pd.testing.assert_frame_equal(panel, p0)
    pd.testing.assert_frame_equal(events, e0)


# ---------------------------------------------------------------------------------------------
# Module hygiene
# ---------------------------------------------------------------------------------------------
def test_backend_is_selected_only_inside_main() -> None:
    tree = ast.parse((ROOT / "src" / "evaluate" / "figures.py").read_text(encoding="utf-8"))
    imported = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert not any("pyplot" in ast.dump(n) for n in imported)
    uses = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "use"]
    assert len(uses) == 1
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    assert uses[0] in list(ast.walk(main))


def test_figure_names_are_the_requested_ones() -> None:
    assert set(figures.FIGURE_NAMES.values()) == {"f1_headline_estimates.png", "f2_election_window_profile.png", "f3_exposure_vs_capb_partial.png",
                                                 "f4_inference_ladder.png", "f5_capb_country_year_heatmap.png"}


# ---------------------------------------------------------------------------------------------
# Real panel (skipped with a reason if it cannot be loaded)
# ---------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def real_extract() -> pd.DataFrame:
    try:
        import m1

        extract, _ = m1.load_real_panel()
    except Exception as error:  # noqa: BLE001  (tag absent, parquet missing, hash mismatch ...)
        pytest.skip(f"real gold panel not loadable here: {type(error).__name__}: {error}")
    return extract


def test_real_panel_ols_slope_equals_the_robustness_ols_baseline(real_extract: pd.DataFrame) -> None:
    if not ROBUSTNESS_JSON.exists():
        pytest.skip("robustness.json not present")
    design = pv.build_variant_design(real_extract, "M1", era=True, control_names=())
    slope = figures.partial_association_inputs(design)["slope"]
    ols = next(r for r in figures.load_json(ROBUSTNESS_JSON)["sections"]["A"]["rows"] if r["id"].startswith("A1-ols"))
    assert slope == pytest.approx(ols["targets"]["beta_S"]["estimate"], abs=1e-6)


def test_real_calendar_events_match_the_sample(real_extract: pd.DataFrame) -> None:
    calendar = ROOT / "data" / "interim" / "election_calendar_eu27.csv"
    if not calendar.exists():
        pytest.skip("election calendar not present")
    events = figures.load_scheduled_events(calendar)
    assert len(events) == 143 and set(events["eurostat_code"]) <= set(real_extract["eurostat_code"])
    summary = figures.event_window_summary(real_extract, events)
    assert summary["n"].max() > 100 and summary["ci_lo"].notna().all()
