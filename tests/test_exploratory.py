"""Offline tests for the exploratory runner (``src/models/py/exploratory.py``; ``docs/exploratory_spec.md``).

Panels are SYNTHETIC with known injected effects. The one test that touches the real gold panel reads ONLY non-outcome columns
(``capb`` is replaced by a zero placeholder), and the refusal test proves the runner cannot reach the real outcome without the tag.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
for sub in ("models/py", "evaluate", "normalize", "features"):
    sys.path.insert(0, str(ROOT / "src" / sub))
import exploratory as ex  # noqa: E402
import m1  # noqa: E402
import power  # noqa: E402
import power_variants as pv  # noqa: E402
import secondary  # noqa: E402

GOLD = ROOT / "data" / "processed" / "gold" / "panel_country_year.parquet"
B_TEST = 19


# ---------------------------------------------------------------------------------------------
# Synthetic data
# ---------------------------------------------------------------------------------------------
def make_codes(n: int = 27) -> list[str]:
    codes = [f"C{i:02d}" for i in range(n)]
    codes[3] = "NL"
    return codes


def make_panel(seed: int = 5, n: int = 27, first: int = 1995, last: int = 2021) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    codes = make_codes(n)
    rows = [(c, y) for c in codes for y in range(first, last + 1)]
    f = pd.DataFrame(rows, columns=["eurostat_code", "year"])
    m = len(f)
    cidx = f["eurostat_code"].map({c: i for i, c in enumerate(codes)}).to_numpy()
    f["olddep1_lag"] = 15 + 0.25 * (f["year"] - first) + 1.5 * rng.standard_normal(m) + cidx % 9
    for name, prob in (("W_S", 0.35), ("W_E", 0.15), ("W_U", 0.1)):
        f[name] = rng.uniform(0, 1, m) * (rng.random(m) < prob)
    f["W_D"] = 0.0
    f["Post"] = rng.uniform(0, 1, m) * (rng.random(m) < 0.3)
    f["debt_gdp_lag"] = 30 + 4 * cidx + 0.5 * (f["year"] - first) + 5 * rng.standard_normal(m)
    adopt = np.where(cidx % 3 == 0, 9999, 1999 + cidx % 10)
    f["euro_member"] = (f["year"].to_numpy() >= adopt).astype(float)
    f["sec_interest_d41pay"] = 2 + 0.1 * cidx + rng.standard_normal(m) * 0.3
    f["capb"] = rng.standard_normal(m)
    f["in_confirmatory"] = True
    return f


def make_rule(n: int = 27, seed: int = 9) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    codes = make_codes(n)
    years = list(range(1990, 2025))
    base = rng.uniform(6, 20, n)
    vals = base[:, None] + np.cumsum(rng.normal(0, 0.4, (n, len(years))) * (rng.random((n, len(years))) < 0.3), axis=1)
    rule = pd.DataFrame(vals, index=codes, columns=years)
    rule.loc[codes[5], [2015, 2016]] = np.nan  # a country missing two lag years: its first two window rows must drop
    rule.loc[codes[7], [2011, 2012, 2013, 2014]] = np.nan  # long-window gaps so that the presence dummy varies
    rule.loc[codes[8], [2012, 2013]] = np.nan
    rule.loc["NL", [2021, 2022]] = 1.0  # the suspected-error values
    return rule


def accession_for(n: int = 27) -> dict[str, int]:
    return {c: (1995 if i < 14 else 2004) for i, c in enumerate(make_codes(n))}


def prepared(seed: int = 5, **kw) -> pd.DataFrame:
    return ex.prepare(make_panel(seed), make_rule(), accession=accession_for(), **kw)


# ---------------------------------------------------------------------------------------------
# Rule reader and NL rule (real workbook, read-only)
# ---------------------------------------------------------------------------------------------
@pytest.mark.skipif(not ex.WORKBOOK.exists(), reason="rule workbook not present")
def test_workbook_hash_matches_manifest_and_reader_reproduces_the_spec_facts():
    sha = ex.verify_workbook()
    assert sha == "7f4c291315ddaee55ccf8ebd70f69a44f1ea04c99679ed58ddd10497d340a6a9"
    values, info = ex.read_cfrsi()
    assert values.shape == (27, 35) and list(values.columns) == list(range(1990, 2025)) and "EL" in values.index and "GR" not in values.index
    dots = info["dot_cells_by_year"]
    assert [dots[y] for y in range(2012, 2018)] == [4, 3, 2, 1, 1, 0]
    assert all(dots[y] == 0 for y in range(2017, 2025))
    assert values.loc["NL", 2020] == pytest.approx(19.6163, abs=1e-4) and values.loc["NL", 2021] == pytest.approx(12.9158, abs=1e-4)
    assert values.loc["NL", 2022] == pytest.approx(12.9158, abs=1e-4) and values.loc["NL", 2023] == pytest.approx(19.7639, abs=1e-4)
    assert values.loc["CZ", [2015, 2016]].isna().all() and values.loc["CZ", 2017] == values.loc["CZ", 2017]


def test_verify_workbook_detects_a_tampered_file(tmp_path):
    f = tmp_path / "a.xlsx"
    f.write_bytes(b"not the workbook")
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(json.dumps({"dest": "x/a.xlsx", "sha256": "0" * 64}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        ex.verify_workbook(f, manifest)
    manifest.write_text(json.dumps({"dest": "x/other.xlsx", "sha256": "0" * 64}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        ex.verify_workbook(f, manifest)


def test_nl_policy_sets_missing_never_imputes_and_include_keeps():
    rule = make_rule()
    out = ex.apply_nl_policy(rule, "exclude")
    assert out.loc["NL", [2021, 2022]].isna().all() and out.loc["NL", 2020] == rule.loc["NL", 2020] and out.loc["NL", 2023] == rule.loc["NL", 2023]
    assert ex.apply_nl_policy(rule, "include").equals(rule)
    assert not np.shares_memory(out.to_numpy(), rule.to_numpy())
    with pytest.raises(ValueError):
        ex.apply_nl_policy(rule, "impute")


def test_lag_uses_previous_index_year_and_nl_frames_are_identical_up_to_2021():
    panel, rule = make_panel(), make_rule()
    exc = ex.prepare(panel, rule, accession=accession_for())
    inc = ex.prepare(panel, rule, nl_policy="include", accession=accession_for())
    row = exc[(exc["eurostat_code"] == "C00") & (exc["year"] == 2018)].iloc[0]
    assert row["F_raw"] == rule.loc["C00", 2017]
    a = exc[exc["year"] <= 2021][["eurostat_code", "year", "F_raw"]].reset_index(drop=True)
    b = inc[inc["year"] <= 2021][["eurostat_code", "year", "F_raw"]].reset_index(drop=True)
    assert a.equals(b)  # the NL index years 2021-22 would only be the lag of t = 2022, 2023
    nl = ex.nl_sensitivity(panel, rule, exc)
    assert nl["frames_identical_for_year_le_2021"] and nl["max_nl_index_year_used"] <= 2020
    assert not exc.loc[(exc["eurostat_code"] == "NL") & (exc["year"] <= 2021), "F_raw"].eq(1.0).any()


# ---------------------------------------------------------------------------------------------
# Designs
# ---------------------------------------------------------------------------------------------
def test_e1_design_sample_columns_and_standardisation():
    prep = prepared()
    w = ex.window_frame(prep, 2016, 2021)
    miss = make_codes()[5]
    assert len(w) == 27 * 6 - 2 and len(w[w["eurostat_code"] == miss]) == 4 and w["year"].min() == 2016
    d = ex.build_e1(w, "pooled")
    assert d.n_obs == 160 and d.n_clusters == 27
    assert not any(c.startswith("WS_x_era") for c in d.x_names) and "W_D" not in d.x_names
    assert set(d.x_names) == {"W_S", "W_E", "W_U", "Post", "WS_x_between", "WS_x_within", "A_lag", "F_z", "WS_x_F"}
    fz = d.x[:, d.x_names.index("F_z")]
    assert fz.mean() == pytest.approx(0, abs=1e-12) and fz.std() == pytest.approx(1, abs=1e-12)
    assert d.x[:, d.x_names.index("WS_x_F")] == pytest.approx(w["W_S"].to_numpy() * fz)
    assert d.scale["sd_F_raw"] == pytest.approx(w["F_raw"].std(ddof=0))
    assert d.targets["gamma_F"] == "WS_x_F"


def test_e1_split_and_noage_and_long_window_and_presence():
    prep = prepared()
    w = ex.window_frame(prep, 2016, 2021)
    s = ex.build_e1(w, "split")
    assert {"gamma_F_B", "gamma_F_W"} <= set(s.targets) and "WS_x_F" not in s.x_names and "F_z" in s.x_names
    n = ex.build_e1(w, "noage")
    assert "WS_x_between" not in n.x_names and "A_lag" in n.x_names and "gamma_F" in n.targets
    lg = ex.build_e1(ex.window_frame(prep, 2012, 2021), "pooled", single_era=True)
    assert "WS_x_era_2016_2021" in lg.x_names and "WS_x_era_2008_2015" not in lg.x_names
    p = ex.build_presence(ex.window_frame(prep, 2012, 2021, need_rule=False))
    assert p.n_obs == 270 and "P" in p.x_names and p.targets["delta_P"] == "WS_x_P"
    f = ex.sorted_frame(ex.window_frame(prep, 2012, 2021, need_rule=False))
    P = f["F_raw"].notna().to_numpy(float)
    w_s = f["W_S"].to_numpy(float)
    assert (w_s * (P - (w_s * P).sum() / w_s.sum())).sum() == pytest.approx(0, abs=1e-9)


def test_e2_triple_term_and_between_component_agree_with_m1():
    prep = prepared()
    w = ex.window_frame(prep, 2016, 2021)
    d = ex.build_e1(w, "e2", label="E2")
    assert len(d.x_names) == 11
    b = ex.between_component(ex.sorted_frame(w))
    m1_regs, _, _ = pv.variant_regressors(ex.sorted_frame(w), era=False)
    ws = ex.sorted_frame(w)["W_S"].to_numpy()
    assert m1_regs["WS_x_between"].to_numpy() == pytest.approx(ws * b)
    fz = d.x[:, d.x_names.index("F_z")]
    assert d.x[:, d.x_names.index("WS_x_B_x_F")] == pytest.approx(ws * b * fz)
    assert d.x[:, d.x_names.index("B_x_F")] == pytest.approx(b * fz)


def test_e3_hinge_knot_slopes_and_terciles():
    prep = prepared()
    d, info = ex.build_e3(prep, "hinge")
    assert info["n_countries_above_knot"] == 13 and info["n_countries_at_or_below_knot"] == 14
    b = ex.between_component(prep)
    kappa = info["knot"]
    assert d.x[:, d.x_names.index("WS_x_hinge")] == pytest.approx(prep["W_S"].to_numpy() * np.maximum(b - kappa, 0))
    assert d.targets["delta_H"] == "WS_x_hinge" and "WS_x_between" in d.x_names and "WS_x_within" in d.x_names and any(c.startswith("WS_x_era") for c in d.x_names)
    s, _ = ex.build_e3(prep, "slopes")
    s1, s2 = s.x[:, s.x_names.index("WS_x_S1")], s.x[:, s.x_names.index("WS_x_S2")]
    assert (s1 + s2) == pytest.approx(prep["W_S"].to_numpy() * b)
    t, tinfo = ex.build_e3(prep, "terciles")
    assert tinfo["tercile_sizes"] == [9, 9, 9] and set(t.targets) >= {"tau_mid", "tau_top"} and "WS_x_between" not in t.x_names
    low_b = max(b[prep["eurostat_code"] == c][0] for c in tinfo["tercile_members"]["low"])
    top_b = min(b[prep["eurostat_code"] == c][0] for c in tinfo["tercile_members"]["top"])
    assert low_b <= top_b


@pytest.mark.parametrize("which, n_expected", [("a", 27 * 27), ("c", 27 * 27), ("d", 27 * 27)])
def test_e4_groups_centring_and_counts(which, n_expected):
    prep = prepared()
    d, info = ex.build_e4(prep, which, "pooled")
    assert d.n_obs == n_expected
    frame, dummy, tname, varies, _ = ex.e4_moderator(prep, which)
    ws = frame["W_S"].to_numpy()
    assert (ws * ex._centre(dummy, ws)).sum() == pytest.approx(0, abs=1e-9)  # exposure-weighted centring
    assert ("D_main" in d.x_names) == varies
    if which == "c":
        assert info == {"n_accession": 13, "n_eu14": 14}
    if which == "a":
        assert info["n_high"] + info["n_low"] == 27 and info["n_high"] == 13


def test_e4b_drops_rows_without_lagged_debt_and_splits_within_year():
    panel = make_panel()
    panel.loc[panel["year"] == 1995, "debt_gdp_lag"] = np.nan
    prep = ex.prepare(panel, make_rule(), accession=accession_for())
    d, info = ex.build_e4(prep, "b", "pooled")
    assert d.n_obs == 27 * 26 and d.n_clusters == 27
    frame, high, *_ = ex.e4_moderator(prep, "b")
    med = frame.groupby("year")["debt_gdp_lag"].transform("median")
    assert (high == (frame["debt_gdp_lag"] > med).to_numpy(float)).all()
    assert high.reshape(-1)[frame["year"].to_numpy() == 2000].sum() in (13.0, 14.0)  # strictly above the median of 27


def test_e4_pooled_interaction_equals_difference_of_group_coefficients():
    prep = prepared()
    for which in "acd":
        pooled, _ = ex.build_e4(prep, which, "pooled")
        groups, _ = ex.build_e4(prep, which, "groups")
        y = pooled.y
        tname = [t for t in pooled.targets if t.startswith("delta")][0]
        p = ex.make_estimator(pooled, "V7").fit(y, [tname])[tname][0][0]
        g = ex.make_estimator(groups, "V7").fit(y, ["beta_S_D1", "beta_S_D0"])
        assert float(p) == pytest.approx(float(g["beta_S_D1"][0][0] - g["beta_S_D0"][0][0]), abs=1e-7)


# ---------------------------------------------------------------------------------------------
# Known-effect recovery
# ---------------------------------------------------------------------------------------------
def _recover(design: power.Design, target: str, beta: float, kind: str = "V7", seed: int = 3, scale: float = 0.3) -> float:
    rng = np.random.default_rng(seed)
    col = design.x[:, design.x_names.index(design.targets[target])]
    y = beta * col + scale * rng.standard_normal(design.n_obs)
    return float(ex.make_estimator(design, kind).fit(y, [target])[target][0][0])


def test_known_interactions_are_recovered_by_every_model_family():
    prep = prepared()
    w = ex.window_frame(prep, 2016, 2021)
    cases = [(ex.build_e1(w, "pooled"), "gamma_F", 1.5), (ex.build_e1(w, "e2"), "delta_BF", 1.5), (ex.build_e3(prep, "hinge")[0], "delta_H", 1.5),
             (ex.build_e4(prep, "c", "pooled")[0], "delta_accession", 1.5), (ex.build_e4(prep, "d", "pooled")[0], "delta_euro", 1.5), (ex.build_e4(prep, "b", "pooled")[0], "delta_debt_within_time", 1.5),
             (ex.build_e4(prep, "a", "pooled")[0], "delta_debt_between", 1.5)]
    for design, target, beta in cases:
        assert _recover(design, target, beta) == pytest.approx(beta, abs=0.45), design.label
    for kind in ("V3", "V0"):
        assert _recover(ex.build_e1(w, "pooled"), "gamma_F", 1.5, kind) == pytest.approx(1.5, abs=0.45)


def test_fit_model_returns_intervals_for_all_targets_and_p_for_requested():
    prep = prepared()
    d = ex.build_e1(ex.window_frame(prep, 2016, 2021), "pooled")
    res = ex.fit_model(d, "V7", p_targets=["gamma_F"], n_boot=B_TEST)
    assert res["status"] == "ok" and set(res["targets"]) == set(d.targets)
    assert "p_bootstrap" in res["targets"]["gamma_F"] and "p_bootstrap" not in res["targets"]["beta_S"]
    t = res["targets"]["gamma_F"]
    assert t["ci_lo"] < t["estimate"] < t["ci_hi"] and 1 / (B_TEST + 1) <= t["p_bootstrap"] <= 1


# ---------------------------------------------------------------------------------------------
# Feasibility ladder
# ---------------------------------------------------------------------------------------------
def test_feasibility_flags_have_the_specified_structure():
    prep = prepared()
    d = ex.build_e1(ex.window_frame(prep, 2016, 2021), "pooled")
    f7 = ex.feasibility(d, "V7")
    assert {"F1_full_rank", "F2_nickell_invertible", "F3_variance_floor_ok", "raw_rho", "corrected_rho", "plim_min", "plim_max", "passed"} <= set(f7)
    assert f7["plim_min"] < -0.9 and 0.9 < f7["plim_max"] < 1.0 and f7["mean_years"] == pytest.approx(160 / 27)
    assert ex.feasibility(d, "V0")["passed"] is True and ex.feasibility(d, "V3")["F2_nickell_invertible"] is None


def test_ladder_falls_back_mechanically_and_always_reports_all_three(monkeypatch):
    prep = prepared()
    fn = lambda: ex.build_e1(ex.window_frame(prep, 2016, 2021), "pooled")  # noqa: E731
    base = ex.fit_ladder(fn, p_targets=["gamma_F"], n_boot=B_TEST, log=lambda s: None)
    assert set(base["by_estimator"]) == {"V7", "V3", "V0"} and all(r["status"] in ("ok", "infeasible") for r in base["by_estimator"].values())
    real = ex.feasibility

    def deny_v7(design, kind):
        out = real(design, kind)
        if kind == "V7":
            out["passed"] = False
        return out

    monkeypatch.setattr(ex, "feasibility", deny_v7)
    lad = ex.fit_ladder(fn, p_targets=["gamma_F"], n_boot=B_TEST, log=lambda s: None)
    assert lad["by_estimator"]["V7"]["status"] == "infeasible" and lad["in_force"] == "V3" and lad["fallback_triggered"] and lad["main"]["estimator"] == "V3"

    def deny_both(design, kind):
        out = real(design, kind)
        out["passed"] = kind == "V0"
        return out

    monkeypatch.setattr(ex, "feasibility", deny_both)
    assert ex.fit_ladder(fn, p_targets=["gamma_F"], n_boot=B_TEST, log=lambda s: None)["in_force"] == "V0"


def test_a_rank_deficient_design_is_reported_as_failed_not_respecified():
    prep = prepared()

    def bad():
        w = ex.window_frame(prep, 2016, 2021)
        w = w.assign(W_E=w["W_S"])  # duplicate column
        return ex.build_e1(w, "pooled")

    res = ex.safe_fit(bad, "V7", p_targets=["gamma_F"], n_boot=B_TEST)
    assert res["status"] == "failed" and "rank" in res["error"]


# ---------------------------------------------------------------------------------------------
# Multiplicity and reading
# ---------------------------------------------------------------------------------------------
def _fake_main(p: float, est: float = 0.1, lo: float = -0.2, hi: float = 0.4) -> dict:
    return {"status": "ok", "estimator": "V7", "n_obs": 10, "n_countries": 3, "targets": {}, "_p": p, "_e": (est, lo, hi)}


def _fake_models(ps: list[float | None]) -> dict:
    models = {}
    for (mid, target, _), p in zip(ex.FAMILY, ps):
        if p is None:
            models[mid] = {"main": {"status": "failed"}}
        else:
            models[mid] = {"main": {"status": "ok", "estimator": "V7", "n_obs": 10, "n_countries": 3,
                                    "targets": {target: {"estimate": 0.1, "ci_lo": -0.2, "ci_hi": 0.4, "cr1_se": 0.1, "p_bootstrap": p}}}}
    return models


def test_family_has_seven_coefficients_and_bh_by_match_the_reused_functions():
    assert len(ex.FAMILY) == 7 and len({t for _, t, _ in ex.FAMILY}) == 7
    ps = [0.001, 0.02, 0.04, 0.3, 0.5, 0.0005, 0.9]
    out = ex.apply_family(_fake_models(ps))
    got_bh = [r["q_bh"] for r in out["rows"]]
    assert got_bh == pytest.approx(secondary.benjamini_hochberg(ps))
    assert [r["q_by"] for r in out["rows"]] == pytest.approx(secondary.benjamini_yekutieli(ps))
    assert out["m_used"] == 7 and out["complete"] and out["alpha"] == 0.05
    assert [r["bh_reject"] for r in out["rows"]] == [q <= 0.05 for q in got_bh]


def test_failed_model_stays_listed_and_reduces_m():
    out = ex.apply_family(_fake_models([0.01, None, 0.2, 0.3, 0.4, 0.5, 0.6]))
    assert out["m_listed"] == 7 and out["m_used"] == 6 and not out["complete"]
    assert out["rows"][1]["status"] == "failed"
    ps = [0.01, 0.2, 0.3, 0.4, 0.5, 0.6]
    assert [r["q_bh"] for r in out["rows"] if r["status"] == "ok"] == pytest.approx(secondary.benjamini_hochberg(ps))


def test_reading_labels():
    assert ex.reading({"ci_lo": -1, "ci_hi": 1}, 0.5)["label"] == "interval contains zero"
    assert ex.reading({"ci_lo": 0.1, "ci_hi": 0.5}, 0.2)["excludes_zero"] and "nominal" in ex.reading({"ci_lo": 0.1, "ci_hi": 0.5}, 0.2)["label"]
    assert ex.reading({"ci_lo": 0.1, "ci_hi": 0.5}, 0.04)["label"] == "BH-rejected"
    assert ex.reading({"ci_lo": -2.5, "ci_hi": 2.5}, 1.0)["uninformative"] and not ex.reading({"ci_lo": -0.5, "ci_hi": 0.5}, 1.0)["uninformative"]


# ---------------------------------------------------------------------------------------------
# E6
# ---------------------------------------------------------------------------------------------
def _clustered_extract() -> pd.DataFrame:
    rng = np.random.default_rng(2)
    rows = []
    for i, code in enumerate(make_codes()):
        c = i // 9
        for year in range(1995, 2022):
            rows.append({"eurostat_code": code, "year": year, "debt_gdp_lag": 30 + 40 * c + rng.normal(0, 1), "sec_interest_d41pay": 1 + 3 * c + rng.normal(0, 0.1),
                         "capb": 2 - 3 * c + rng.normal(0, 0.5 + c), "olddep1_lag": 15 + 4 * c + rng.normal(0, 0.2), "in_confirmatory": True})
    return pd.DataFrame(rows)


def test_e6_recovers_three_known_clusters_and_is_stable():
    out = ex.run_e6(_clustered_extract())
    assert out["chosen_k"] == 3 and out["silhouette"] > 0.7 and out["silhouette_reading"] == "strong structure"
    assert sorted(out["cluster_sizes"].values()) == [9, 9, 9]
    assert out["stability"]["share_equal_to_reference"] == 1.0 and out["stability"]["ari_min"] == 1.0 and out["stability"]["ari_ward_vs_reference"] == 1.0
    members = {frozenset(v) for v in out["membership"].values()}
    codes = make_codes()
    assert members == {frozenset(codes[0:9]), frozenset(codes[9:18]), frozenset(codes[18:27])}
    assert [r["k"] for r in out["k_table"]] == [2, 3, 4, 5, 6]


def test_e6_rule_excludes_k_with_tiny_clusters_and_reports_no_admissible_k():
    rng = np.random.default_rng(0)
    codes = make_codes()
    rows = [{"eurostat_code": c, "year": y, "debt_gdp_lag": 50.0 + (500.0 if i < 2 else 0) + rng.normal(0, 1), "sec_interest_d41pay": 2.0 + rng.normal(0, 0.1),
             "capb": rng.normal(0, 1), "olddep1_lag": 20.0 + rng.normal(0, 0.1)} for i, c in enumerate(codes) for y in range(2000, 2010)]
    out = ex.run_e6(pd.DataFrame(rows), k_range=(2,), n_seeds=5, min_size=3)
    assert out["chosen_k"] is None and out["note"] == "no admissible k"


def test_silhouette_scale_labels():
    assert [ex.silhouette_label(v) for v in (0.8, 0.6, 0.4, 0.25, 0.1)] == ["strong structure", "reasonable structure", "weak structure", "no substantial structure", "no substantial structure"]


# ---------------------------------------------------------------------------------------------
# Power block (small settings), guard, output
# ---------------------------------------------------------------------------------------------
def test_power_job_runs_on_synthetic_data_and_has_the_specified_shape():
    settings = pv.Settings(n_null=300, size_generic=8, mde_generic=8, n_boot=19)
    panel = make_panel()
    cal, ref = ex.calibration(panel)
    prep = prepared()
    d = ex.build_e1(ex.window_frame(prep, 2016, 2021), "pooled")
    assert np.array_equal(d.codes[d.starts], ref.codes[ref.starts])
    key, res = ex._power_job((("E1", "V0", "ar1_rho0"), d, "V0", "gamma_F", cal.sigma, 0.0, 1, 0, 2, settings, True))
    assert key == ("E1", "V0", "ar1_rho0") and res["cr1"]["mde"] > 0 and res["wcb"]["mde"] > 0 and 0 <= res["wcb"]["size"] <= 1


def test_promotion_check_uses_the_one_point_zero_line():
    block = {"models": {"E1": {"by_estimator": {"V7": {"ar1_rho_hat": {"wcb": {"mde": 0.9}}, "ar1_rho0": {"wcb": {"mde": 1.4}}},
                                                 "V0": {"ar1_rho_hat": {"wcb": {"mde": 1.2}}, "ar1_rho0": {"wcb": {"mde": 1.6}}}}}}}
    pc = ex.promotion_check(block)
    assert pc["V7"]["within_1.0pp"] and not pc["V7"]["within_0.75pp"] and not pc["V0"]["within_1.0pp"] and pc["lines_pp"] == {"promotion": 1.0, "g2_interaction": 0.75}


def test_real_run_is_refused_without_the_tag(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the real outcome was touched without the tag")

    monkeypatch.setattr(pd, "read_parquet", boom)
    with pytest.raises(m1.PreregistrationTagMissing):
        ex.run_real("all", tag_lookup=lambda: False)


def test_default_output_folder_refuses_non_real_results(tmp_path):
    res = ex.new_results(source=ex.SOURCE_SUPPLIED, n_boot=B_TEST, extract_hash=None, workbook_sha=None)
    with pytest.raises(m1.ResultsNotAllowed):
        ex.write_results(res)
    paths = ex.write_results(res, out_dir=tmp_path, figure=False)
    assert all(p.exists() for p in paths)
    assert json.loads((tmp_path / "exploratory.json").read_text(encoding="utf-8"))["status"] == "partial"


def test_report_language_labels_exploratory_family_and_not_run_and_no_causal_verbs(tmp_path):
    prep = prepared()
    results = ex.new_results(source=ex.SOURCE_SUPPLIED, n_boot=B_TEST, extract_hash=None, workbook_sha=None)
    w = ex.window_frame(prep, 2016, 2021)
    results["models"]["E1"] = ex.fit_ladder(lambda: ex.build_e1(w, "pooled"), p_targets=["gamma_F"], n_boot=B_TEST, log=lambda s: None)
    results["models"]["E1"].update({"companion_split": {"status": "failed", "error": "x"}, "sensitivities": {}, "loo": {"estimator": "V7", "n_boot": 9, "fits": []}})
    results["multiplicity"] = ex.apply_family(results["models"])
    results["e6"] = ex.run_e6(_clustered_extract(), prep)
    text = ex.render_markdown(ex.clean(results))
    assert "Exploratory" in text and "associations" in text and "not enforcement" in text
    assert "not run: data not acquired (CPDS, DPI)" in text and "not chosen" in text
    for word in ("causes", "caused by", "impact of"):
        assert word not in text
    png = ex.forest_plot(ex.clean({**results, "multiplicity": ex.apply_family(_fake_models([0.01, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]))}), tmp_path / "f.png")
    assert png.exists() and png.stat().st_size > 5000


def test_json_is_strict(tmp_path):
    res = ex.new_results(source=ex.SOURCE_SUPPLIED, n_boot=3, extract_hash=None, workbook_sha=None)
    res["x"] = {"a": float("nan"), "b": np.float64(1.5), "c": np.int64(2), "d": (1, 2)}
    parsed = json.loads(ex.to_json(res))
    assert parsed["x"] == {"a": None, "b": 1.5, "c": 2, "d": [1, 2]}


# ---------------------------------------------------------------------------------------------
# Frozen files and the real sample (non-outcome columns only)
# ---------------------------------------------------------------------------------------------
def test_frozen_files_are_byte_identical_to_the_manifest():
    manifest = json.loads((ROOT / "docs" / "freeze_manifest.json").read_text(encoding="utf-8"))["files"]
    checked = 0
    for name, entry in manifest.items():
        if not (name.startswith(("src/", "config/", "scripts/")) or name in ("docs/preregistration.md", "requirements.lock")):
            continue
        path = ROOT / name
        assert path.exists(), name
        assert m1.file_sha256(path) == entry["sha256"], name
        checked += 1
    assert checked >= 20


@pytest.mark.skipif(not (GOLD.exists() and ex.WORKBOOK.exists()), reason="gold panel or workbook not present")
def test_real_e1_sample_matches_the_spec_facts_without_reading_the_outcome():
    cols = ["eurostat_code", "year", "W_S", "W_E", "W_D", "W_U", "Post", "olddep1_lag", "debt_gdp_lag", "euro_member", "in_confirmatory"]
    g = pd.read_parquet(GOLD, columns=cols)
    g["capb"] = 0.0  # placeholder: the outcome is never read here
    g["sec_interest_d41pay"] = 0.0
    values, _ = ex.read_cfrsi()
    prep = ex.prepare(g, values)
    w = ex.window_frame(prep, 2016, 2021)
    assert len(w) == 160 and w["eurostat_code"].nunique() == 27
    assert w.groupby("eurostat_code").size().to_dict()["CZ"] == 4 and set(w.groupby("eurostat_code").size()) == {4, 6}
    nl = w[w["eurostat_code"] == "NL"]
    assert (nl["F_raw"] > 19).all() and (nl["year"] - 1 <= 2020).all()
    assert int((w["W_S"] > 0).sum()) == 55 and w.loc[w["W_S"] > 0, "eurostat_code"].nunique() == 22
    assert w["F_raw"].std(ddof=0) == pytest.approx(3.759, abs=1e-3)
    d = ex.build_e1(w, "pooled")
    assert d.n_obs == 160 and d.k_params == 14
    long = ex.window_frame(prep, 2012, 2021)
    assert len(long) == 254 and len(ex.window_frame(prep, 2012, 2021, need_rule=False)) == 270
    d4, info = ex.build_e4(prep, "b", "pooled")
    assert d4.n_obs == 688 and ex.build_e4(prep, "a", "pooled")[1]["n_high"] == 13 and ex.build_e4(prep, "c", "pooled")[1] == {"n_accession": 13, "n_eu14": 14}
