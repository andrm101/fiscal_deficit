"""S4: tests of the CAPB-revision appendix (``src/evaluate/revisions.py``).

Synthetic: small hand-made vintage tables (statistics, first-outturn rule, ROM and GRC chapter-flow codes, one-year changes, exposure
contrast, results rendering). Two real-data tests run on the committed outputs / vintage table and are skipped if those are absent.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
for sub in ("normalize", "evaluate", "models/py", "features"):
    sys.path.insert(0, str(ROOT / "src" / sub))
import ameco_vintages as av  # noqa: E402
import revisions as rv  # noqa: E402


# ---------------------------------------------------------------------------------------------
# Hand-made vintage table
# ---------------------------------------------------------------------------------------------
def _spec(season: str, year: int, order: int) -> av.VintageSpec:
    return av.VintageSpec(f"{season.capitalize()} {year}", order, season, year, Path("unused.zip"), date(year, 5, 1))


SPECS = [_spec("autumn", 2014, 1), _spec("spring", 2015, 2), _spec("autumn", 2015, 3), _spec("spring", 2016, 4)]


def _rows(order: int, label: str, values: dict[tuple[str, int], float]) -> list[dict]:
    return [
        {"vintage_label": label, "vintage_order": order, "eurostat_code": c, "item": av.CAPB_ITEM, "year": y, "value": v}
        for (c, y), v in values.items()
    ]


def make_long() -> pd.DataFrame:
    """Two countries (AA, BB), years 2012-2016. Autumn 2014 ends 2016 (3 forecast years, last outturn 2013); Spring 2015 ends 2016 (2 forecast
    years, last outturn 2014); Autumn 2015 ends 2017 (last outturn 2014); Spring 2016 ends 2017 (last outturn 2015); final ends 2017."""
    rows = []
    rows += _rows(1, "Autumn 2014", {("AA", 2012): 1.0, ("AA", 2013): 2.0, ("AA", 2014): 3.0, ("AA", 2015): 3.0, ("AA", 2016): 3.0,
                                      ("BB", 2012): -1.0, ("BB", 2013): -2.0, ("BB", 2014): -3.0, ("BB", 2015): -3.0, ("BB", 2016): -3.0})
    rows += _rows(2, "Spring 2015", {("AA", 2012): 1.0, ("AA", 2013): 2.0, ("AA", 2014): 2.5, ("AA", 2015): 4.0, ("AA", 2016): 4.0,
                                      ("BB", 2012): -1.0, ("BB", 2013): -2.0, ("BB", 2014): 0.5, ("BB", 2015): -4.0, ("BB", 2016): -4.0})
    rows += _rows(3, "Autumn 2015", {("AA", 2013): 2.0, ("AA", 2014): 2.6, ("AA", 2015): 3.5, ("AA", 2016): 3.5, ("AA", 2017): 3.5,
                                      ("BB", 2013): -2.0, ("BB", 2014): 0.4, ("BB", 2015): -4.0, ("BB", 2016): -4.0, ("BB", 2017): -4.0})
    rows += _rows(4, "Spring 2016", {("AA", 2013): 2.0, ("AA", 2014): 2.6, ("AA", 2015): 3.0, ("AA", 2016): 3.5, ("AA", 2017): 3.5,
                                      ("BB", 2013): -2.0, ("BB", 2014): 0.4, ("BB", 2015): -3.0, ("BB", 2016): -4.0, ("BB", 2017): -4.0})
    rows += _rows(av.FINAL_ORDER, "Spring 2026", {("AA", 2013): 2.0, ("AA", 2014): 2.0, ("AA", 2015): 3.5, ("AA", 2016): 3.0, ("AA", 2017): 3.0,
                                                 ("BB", 2013): -2.0, ("BB", 2014): -1.5, ("BB", 2015): -3.0, ("BB", 2016): -5.0, ("BB", 2017): -5.0})
    return pd.DataFrame(rows)


def test_first_outturn_rule_spring_two_autumn_three() -> None:
    table = rv.revision_table(make_long(), SPECS, window=(2013, 2015)).set_index(["eurostat_code", "year"])
    # 2013 is outturn in Autumn 2014 (3 forecast years: last outturn 2016 - 3 = 2013); 2014 first outturn in Spring 2015; 2015 in Spring 2016 (not Autumn 2015).
    assert table.loc[("AA", 2013), "first_vintage"] == "Autumn 2014"
    assert table.loc[("AA", 2014), "first_vintage"] == "Spring 2015"
    assert table.loc[("AA", 2015), "first_vintage"] == "Spring 2016"
    assert table.loc[("AA", 2015), "first"] == 3.0
    assert table.loc[("BB", 2014), "first"] == 0.5
    assert table.loc[("AA", 2014), "first_order"] == 2


def test_revision_is_final_minus_first_and_window_filters() -> None:
    table = rv.revision_table(make_long(), SPECS, window=(2014, 2015)).set_index(["eurostat_code", "year"])
    assert set(table.index.get_level_values("year")) == {2014, 2015}
    assert table.loc[("AA", 2014), "revision"] == pytest.approx(2.0 - 2.5)
    assert table.loc[("BB", 2014), "revision"] == pytest.approx(-1.5 - 0.5)
    assert table.loc[("AA", 2015), "revision"] == pytest.approx(3.5 - 3.0)
    assert table.loc[("BB", 2015), "revision"] == pytest.approx(0.0)


def test_one_year_changes_use_the_same_vintage() -> None:
    table = rv.revision_table(make_long(), SPECS, window=(2014, 2014)).set_index(["eurostat_code", "year"])
    # AA 2014: first-outturn vintage Spring 2015 holds 2013 = 2.0 and 2014 = 2.5 -> +0.5; final: 2.0 - 2.0 = 0.0
    assert table.loc[("AA", 2014), "d_first"] == pytest.approx(0.5)
    assert table.loc[("AA", 2014), "d_final"] == pytest.approx(0.0)
    # BB 2014: first 0.5 - (-2.0) = +2.5; final -1.5 - (-2.0) = +0.5 (same sign)
    assert table.loc[("BB", 2014), "d_first"] == pytest.approx(2.5)
    assert table.loc[("BB", 2014), "d_final"] == pytest.approx(0.5)


def test_country_year_without_final_is_dropped() -> None:
    long = make_long()
    long = long[~((long["eurostat_code"] == "BB") & (long["year"] == 2014) & (long["vintage_order"] == av.FINAL_ORDER))]
    table = rv.revision_table(long, SPECS, window=(2014, 2014))
    assert list(table["eurostat_code"]) == ["AA"]


# ---------------------------------------------------------------------------------------------
# Statistics on hand-computed values
# ---------------------------------------------------------------------------------------------
FIRST = np.array([1.0, 2.0, -1.0, 0.5, -2.0, 3.0])
FINAL = np.array([1.5, 1.0, -0.5, 0.5, -1.0, 4.0])  # revisions: +0.5, -1.0, +0.5, 0.0, +1.0, +1.0


def test_core_stats_hand_computed() -> None:
    stat = rv.core_stats(FIRST, FINAL, sesoi=0.5)
    rev = FINAL - FIRST
    assert stat["n"] == 6
    assert stat["mean_revision"] == pytest.approx(rev.mean())
    assert stat["mean_revision"] == pytest.approx(0.3333333, abs=1e-6)
    assert stat["mean_abs_revision"] == pytest.approx(4.0 / 6)
    assert stat["sd_revision"] == pytest.approx(rev.std(ddof=1))
    assert stat["median_revision"] == pytest.approx(0.5)
    assert stat["median_abs_revision"] == pytest.approx(0.75)
    assert stat["share_abs_gt_sesoi"] == pytest.approx(3 / 6)  # strictly greater than 0.5: the -1.0 and the two +1.0 revisions; the +0.5 revisions do not count
    assert stat["corr_first_final"] == pytest.approx(np.corrcoef(FIRST, FINAL)[0, 1])
    slope, intercept = np.polyfit(FIRST, FINAL, 1)
    assert stat["slope_final_on_first"] == pytest.approx(slope)
    assert stat["intercept_final_on_first"] == pytest.approx(intercept)
    assert stat["reliability"] == pytest.approx(FINAL.var(ddof=1) / FIRST.var(ddof=1))
    assert stat["slope_first_on_final"] == pytest.approx(np.polyfit(FINAL, FIRST, 1)[0])


def test_share_above_sesoi_is_strict() -> None:
    stat = rv.core_stats([0.0, 0.0, 0.0], [0.5, 0.6, -0.7], sesoi=0.5)
    assert stat["share_abs_gt_sesoi"] == pytest.approx(2 / 3)


def test_sign_change_level_and_zeros() -> None:
    assert list(rv.sign_change([1.0, -1.0, 0.0, 2.0, np.nan], [-1.0, -2.0, 1.0, 0.0, 1.0])) == [True, False, False, False, False]
    stat = rv.core_stats([1.0, -1.0, 2.0, -2.0], [-1.0, -2.0, 1.0, 1.0])
    assert stat["share_sign_change_level"] == pytest.approx(2 / 4)


def test_sign_of_change_uses_only_pairs_with_both_changes() -> None:
    stat = rv.core_stats([1, 2, 3, 4], [1, 2, 3, 4], d_first=[1.0, -1.0, np.nan, 2.0], d_final=[-1.0, -2.0, 1.0, np.nan])
    assert stat["n_delta"] == 2
    assert stat["share_sign_change_delta"] == pytest.approx(1 / 2)


def test_reliability_news_versus_noise_cases() -> None:
    rng = np.random.default_rng(0)
    truth = rng.normal(size=4000)
    noisy_first = truth + rng.normal(scale=0.5, size=4000)  # classical noise in the first outturn: reliability < 1
    assert rv.core_stats(noisy_first, truth)["reliability"] < 1
    first = truth
    news_final = first + rng.normal(scale=0.5, size=4000)  # revision is news: reliability > 1, revision uncorrelated with first
    news = rv.core_stats(first, news_final)
    assert news["reliability"] > 1
    assert abs(news["corr_rev_first"]) < 0.05


def test_quantiles_and_group_summary() -> None:
    table = pd.DataFrame({"eurostat_code": ["A", "A", "B", "B"], "year": [1, 2, 1, 2], "first": [0.0, 1.0, 2.0, -1.0], "final": [1.0, 1.0, 1.0, 0.5],
                          "revision": [1.0, 0.0, -1.0, 1.5]})
    q = rv.revision_quantiles(table)
    assert q["revision"]["0.5"] == pytest.approx(0.5)
    assert q["abs_revision"]["0.5"] == pytest.approx(1.0)
    by = rv.group_summary(table, "eurostat_code", sesoi=0.5).set_index("eurostat_code")
    assert by.loc["A", "mean_abs_revision"] == pytest.approx(0.5)
    assert by.loc["B", "mean_abs_revision"] == pytest.approx(1.25)
    assert by.loc["B", "share_sign_change_level"] == pytest.approx(0.5)  # B year 2: -1.0 -> 0.5 changes sign
    assert by.loc["A", "share_abs_gt_sesoi"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------------------------
# ROM / GRC chapter-flow codes
# ---------------------------------------------------------------------------------------------
def test_rom_and_grc_codes_map_to_eurostat_codes() -> None:
    header = "CODE;COUNTRY;SUB-CHAPTER;TITLE;UNIT;2012;2013;2014;2015"
    body = "\r\n".join([
        header,
        "ROM.1.0.319.0.UBLGBP;Romania;01 x;Net lending CAPB ;(Percentage of potential GDP at current prices) ;-1.0;-2.0;-3.0;-3.0",
        "GRC.1.0.319.0.UBLGBP;Greece;01 x;Net lending CAPB ;(Percentage of potential GDP at current prices) ;1.0;2.0;3.0;3.0",
        "EU28.1.0.319.0.UBLGBP;European Union;01 x;Net lending CAPB ;(Percentage of potential GDP at current prices) ;0.0;0.0;0.0;0.0",
        "",
    ]).encode("latin-1")
    long = av._attach_metadata(av.parse_ameco_txt(body, items=("UBLGBP",)), _spec("spring", 2015, 2))
    assert set(long["eurostat_code"]) == {"RO", "EL"}  # chapter-flow ROM and GRC; the EU aggregate is dropped
    # and the revision table works on the mapped codes
    final = long.assign(vintage_order=av.FINAL_ORDER, vintage_label="Spring 2026")
    first = long.assign(value=long["value"] + 1.0)
    table = rv.revision_table(pd.concat([first, final], ignore_index=True), [_spec("spring", 2015, 2)], window=(2012, 2013))
    assert set(table["eurostat_code"]) == {"RO", "EL"}
    assert (table["revision"] == -1.0).all()


# ---------------------------------------------------------------------------------------------
# Intervals and exposure contrast
# ---------------------------------------------------------------------------------------------
def test_cr1_difference_equals_difference_of_means_and_scales() -> None:
    y = np.array([1.0, 2.0, 3.0, 4.0, 2.0, 5.0, 0.0, 1.0])
    d = np.array([0, 0, 1, 1, 0, 1, 0, 1], float)
    clusters = np.array(list("AABBCCDD"))
    out = rv.cr1_difference(y, d, clusters)
    assert out["difference"] == pytest.approx(y[d == 1].mean() - y[d == 0].mean())
    assert out["ci_lo"] < out["difference"] < out["ci_hi"]
    assert out["n_clusters"] == 4
    degenerate = rv.cr1_difference(y, np.zeros(8), clusters)
    assert np.isnan(degenerate["difference"])


def test_cluster_bootstrap_is_reproducible_and_brackets_the_estimate() -> None:
    rng = np.random.default_rng(1)
    codes = np.repeat([f"C{i}" for i in range(12)], 5)
    values = rng.normal(loc=0.3, size=codes.size)
    one = lambda idx: {"m": float(values[idx].mean())}  # noqa: E731
    a = rv.cluster_draws(codes, one, n_boot=200, seed=7)
    b = rv.cluster_draws(codes, one, n_boot=200, seed=7)
    assert a.equals(b)
    lo, hi = rv.percentile_interval(a)["m"]
    assert lo < values.mean() < hi


def test_exposure_contrast_on_synthetic_panel() -> None:
    rng = np.random.default_rng(3)
    codes = np.repeat([f"C{i}" for i in range(10)], 6)
    exposed = np.tile([True, False, False, True, False, False], 10)
    revision = np.where(exposed, -0.5, 0.5) + rng.normal(scale=0.05, size=codes.size)
    table = pd.DataFrame({"eurostat_code": codes, "year": np.tile(np.arange(6), 10), "first": np.zeros(codes.size), "final": revision, "revision": revision, "exposed": exposed})
    out = rv.exposure_contrast(table, n_boot=300, seed=5)
    assert out["strata"]["exposed"]["n"] == 20 and out["strata"]["unexposed"]["n"] == 40
    d = out["difference_mean_revision"]
    assert d["cr1"]["difference"] == pytest.approx(-1.0, abs=0.05)
    assert d["bootstrap_ci"][1] < 0  # the planted difference of -1 pp is far from zero relative to its sampling variation
    assert out["strata"]["exposed"]["mean_revision"]["mean"] == pytest.approx(-0.5, abs=0.05)


def test_twoway_demean_removes_country_and_year_means() -> None:
    frame = pd.DataFrame({"eurostat_code": list("AABB"), "year": [1, 2, 1, 2], "capb": [1.0, 3.0, 2.0, 6.0]})
    resid = rv.twoway_demean(frame, "capb")
    frame["r"] = resid
    assert frame.groupby("eurostat_code")["r"].mean().abs().max() < 1e-8
    assert frame.groupby("year")["r"].mean().abs().max() < 1e-8


def test_gate5_comparison_flags_disagreement() -> None:
    stat = {"mean_abs_revision": 0.639, "sd_revision": 0.9750, "share_sign_change_level": 0.0972, "corr_first_final": 0.933}
    rows = {r["statistic"]: r for r in rv.gate5_comparison(stat)}
    assert all(r["agrees_with_table"] for r in rows.values())
    assert rows["mean_abs_revision"]["agrees_with_quoted"]
    stat["mean_abs_revision"] = 0.70
    assert not {r["statistic"]: r for r in rv.gate5_comparison(stat)}["mean_abs_revision"]["agrees_with_table"]


# ---------------------------------------------------------------------------------------------
# End to end on the synthetic table: compute-free rendering and the figure
# ---------------------------------------------------------------------------------------------
def _fake_results(n_boot: int = 50) -> tuple[dict, pd.DataFrame]:
    rng = np.random.default_rng(11)
    codes = np.repeat([f"C{i:02d}" for i in range(8)], 6)
    years = np.tile(np.arange(2014, 2020), 8)
    first = rng.normal(0, 2, codes.size)
    final = first + rng.normal(0.1, 0.8, codes.size)
    table = pd.DataFrame({"eurostat_code": codes, "year": years, "first_vintage": [f"Spring {y + 1}" for y in years], "first_order": 2, "first": first, "final": final})
    table["revision"] = table["final"] - table["first"]
    table["d_first"] = table.groupby("eurostat_code")["first"].diff()
    table["d_final"] = table.groupby("eurostat_code")["final"].diff()
    table["W_S"] = rng.choice([0.0, 0.0, 0.5], codes.size)
    table["exposed"] = table["W_S"] > 0
    panel = table.rename(columns={"final": "capb"})[["eurostat_code", "year", "capb", "W_S"]]
    headline = {"sesoi_pp": 0.5, "targets": {"beta_S": {"estimate": -0.38, "ci_lo": -0.69, "ci_hi": -0.07}}}
    stat = rv.table_stats(table, 0.5)
    by_year = rv.group_summary(table, "year", 0.5)
    by_year["n_exposed"] = 2
    by_year["in_confirmatory_sample"] = True
    block = {
        "n": len(table), "n_countries": 8, "years": [2014, 2019], "first_vintage_counts": {"Spring 2015": 8}, "stats": stat,
        "bootstrap_ci": rv.bootstrap_core(table, 0.5, n_boot, 1), "mean_revision_cr1": rv.fg.clustered_mean_ci(table["revision"], table["eurostat_code"]),
        "quantiles": rv.revision_quantiles(table), "top_revisions": rv.top_revisions(table, 3),
    }
    results = {
        "meta": {"spec": "docs/s4_spec.md", "spec_sha256": "0" * 64, "sesoi_pp": 0.5, "n_boot": n_boot, "seed": 1, "level": 0.95, "interim_csv_sha256": "x",
                 "forecast_years_by_season": av.FORECAST_YEARS_BY_SEASON, "final_vintage": av.FINAL_LABEL, "versions": {"numpy": "n", "pandas": "p", "scipy": "s"}},
        "checks": {"n_rows": len(table), "n_matched_to_panel": len(table), "max_abs_panel_minus_final": 0.0},
        "primary": block, "extended": block, "by_year": by_year.to_dict(orient="records"),
        "by_country": rv.group_summary(table, "eurostat_code", 0.5).to_dict(orient="records"),
        "exposure": rv.exposure_contrast(table, n_boot=50, seed=1),
        "signal": rv.signal_scales(table, panel, headline, stat),
        "gate5": rv.gate5_comparison(stat),
    }
    return results, table


def test_markdown_and_figure_render_from_results(tmp_path: Path) -> None:
    from PIL import Image

    results, table = _fake_results()
    text = rv.render_markdown(results)
    assert "descriptive" in text.lower() and "S4" in text
    assert f"{results['primary']['stats']['mean_abs_revision']:.3f}" in text  # numbers in the report come from the results dictionary
    assert " causes " not in text.lower() and " caused " not in text.lower()
    json.dumps(rv._clean(results))  # JSON-serialisable (NaN to None)
    path = rv.figure_revisions(table, results, tmp_path / "s4.png")
    with Image.open(path) as image:
        assert image.size[0] > 1500
        assert image.info.get("dpi", (0, 0))[0] >= 299


# ---------------------------------------------------------------------------------------------
# Real data (skipped when absent)
# ---------------------------------------------------------------------------------------------
@pytest.mark.skipif(not Path(av.INTERIM_CSV).exists(), reason="interim vintage table not built")
def test_real_primary_sample_reproduces_gate5_table() -> None:
    long = rv.load_long()
    table = rv.revision_table(long, av.vintage_specs(), rv.PRIMARY_WINDOW)
    assert len(table) == 216 and table["eurostat_code"].nunique() == 27
    assert set(table["first_vintage"]) == {f"Spring {y + 1}" for y in range(2014, 2022)}
    stat = rv.table_stats(table, 0.5)
    for row in rv.gate5_comparison(stat):
        assert row["agrees_with_table"], row


@pytest.mark.skipif(not (rv.RESULTS_DIR / "s4_revisions.json").exists(), reason="S4 results not generated")
def test_committed_results_are_consistent_with_the_markdown() -> None:
    results = json.loads((rv.RESULTS_DIR / "s4_revisions.json").read_text(encoding="utf-8"))
    markdown = (rv.RESULTS_DIR / "s4_revisions.md").read_text(encoding="utf-8")
    assert f"{results['primary']['stats']['mean_abs_revision']:.3f}" in markdown
    assert results["meta"]["sesoi_pp"] == 0.5 and results["meta"]["seed"] == 42
    assert results["primary"]["n"] == 216
