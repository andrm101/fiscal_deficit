"""Offline tests for the predictive module (``src/models/py/predictive.py``; specification ``docs/predictive_spec.md``).

Every forecasting test uses SYNTHETIC panels and calendars. The real outcome is not read by any test; the only real-data inputs are the
interim election calendar and exposure table (election dates only) and the freeze manifest.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
for sub in ("models/py", "evaluate", "normalize", "features"):
    sys.path.insert(0, str(ROOT / "src" / sub))
import m1  # noqa: E402
import panel as panel_module  # noqa: E402
import predictive as pr  # noqa: E402
import predictive_report as rep  # noqa: E402

TS = pd.Timestamp


# ---------------------------------------------------------------------------------------------
# Synthetic data
# ---------------------------------------------------------------------------------------------
def make_calendar(codes: list[str], with_poison_after: int | None = None) -> pd.DataFrame:
    rows = []
    for i, c in enumerate(codes):
        for k, d in enumerate([TS(1992 + i % 3, 5, 10), TS(1996 + i % 3, 6, 1), TS(2000 + i % 3, 3, 15), TS(2004 + i % 3, 9, 20), TS(2008 + i % 3, 4, 5), TS(2012 + i % 3, 11, 2)]):
            rows.append({"eurostat_code": c, "date_used": d, "termlength": 4.0, "sche_date": d, "in_calendar": True})
    cal = pd.DataFrame(rows)
    if with_poison_after is not None:
        late = cal["date_used"] > TS(with_poison_after, 12, 31)
        cal.loc[late, "date_used"] = cal.loc[late, "date_used"] - pd.Timedelta(days=200)
        cal.loc[late, "date_used"] = cal.loc[late, "date_used"].clip(lower=TS(with_poison_after + 1, 1, 5))
        cal.loc[late, "termlength"] = 99.0
        cal.loc[late, "sche_date"] = TS(2000, 1, 1)
    return cal.sort_values(["eurostat_code", "date_used"]).reset_index(drop=True)


def make_gold(n_codes: int = 6, first: int = 1995, last: int = 2014, seed: int = 0, gap: tuple[str, int] | None = None) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_codes):
        capb = np.cumsum(rng.normal(size=last - first + 1))
        for k, y in enumerate(range(first, last + 1)):
            rows.append({"eurostat_code": f"C{i}", "year": y, "capb": capb[k], "debt_gdp_lag": 50 + 5 * rng.normal(), "outgap_lag": rng.normal(),
                         "ig_diff_lag": rng.normal(), "euro_member": y >= 2000 + i, "olddep1_lag": 20 + 0.3 * (y - first) + i, "olddep3_lag": 18 + 0.2 * (y - first) + i,
                         "medage_lag": 35 + 0.2 * (y - first) + i, "W_S": rng.uniform(), "W_E": rng.uniform(), "W_U": rng.uniform()})
    df = pd.DataFrame(rows)
    if gap:
        df.loc[(df["eurostat_code"] == gap[0]) & (df["year"] == gap[1]), "capb"] = np.nan
    delta = panel_module._capb_delta(df[["eurostat_code", "year", "capb"]].dropna())  # the frozen explicit calendar join
    df = df.merge(delta.rename(columns={"value": "sec_d_capb"})[["eurostat_code", "year", "sec_d_capb"]], on=["eurostat_code", "year"], how="left")
    return df


@pytest.fixture(scope="module")
def synth():
    gold = make_gold()
    cal = make_calendar(sorted(gold["eurostat_code"].unique()))
    return gold, cal, pr.build_origin_panel(gold, cal)


# ---------------------------------------------------------------------------------------------
# Constants and splits
# ---------------------------------------------------------------------------------------------
def test_origin_blocks_match_the_specification():
    assert pr.ORIGINS_P[0] == 2008 and pr.ORIGINS_P[-1] == 2020 and len(pr.ORIGINS_P) == 13
    assert pr.ORIGINS_H == (2021, 2022)
    assert pr.SEED_KEY == 6000
    assert [h[0] for h in pr.HOLM_FAMILY] == ["P1a-B1 vs P0", "P1b-B1 vs P0", "P1a-B2 vs P0", "P1b-B2 vs P0", "P1a: B2 vs B1", "P1b: B2 vs B1"]
    assert len(pr.HGB_GRID) == 8 and len(pr._linear_configs()) == 44


def test_rolling_origin_splits_are_expanding_and_one_step_ahead(synth):
    _, _, op = synth
    for t in (2005, 2006, 2007):
        tr, te = pr.training_window(op, t), pr.test_rows(op, t)
        assert tr["forecast_year"].max() == t and tr["forecast_year"].min() >= pr.FIRST_TRAIN_YEAR
        assert (te["forecast_year"] == t + 1).all() and (te["origin"] == t).all()
        assert set(pr.training_window(op, t).index) <= set(pr.training_window(op, t + 1).index)  # expanding
        for lo, va in pr.inner_folds(tr, t):
            assert lo["forecast_year"].max() < va["forecast_year"].min()  # the validation year never enters its own fit
            assert va["forecast_year"].nunique() == 1 and va["forecast_year"].iloc[0] <= t
    folds = pr.inner_folds(pr.training_window(op, 2008), 2008)
    assert [v["forecast_year"].iloc[0] for _, v in folds] == [2004, 2005, 2006, 2007, 2008]


def test_first_usable_forecast_year_is_1997(synth):
    _, _, op = synth
    assert op[op["complete"]]["forecast_year"].min() == 1997  # 1996 targets need dcapb at 1995 (two earlier CAPB years)


# ---------------------------------------------------------------------------------------------
# Target and the origin panel
# ---------------------------------------------------------------------------------------------
def test_target_is_the_consecutive_year_difference_and_missing_across_a_gap():
    gold = make_gold(gap=("C1", 2003))
    cal = make_calendar(sorted(gold["eurostat_code"].unique()))
    op = pr.build_origin_panel(gold, cal)
    capb = gold.set_index(["eurostat_code", "year"])["capb"]
    for _, r in op.iterrows():
        a, b = capb.get((r["code"], r["forecast_year"]), np.nan), capb.get((r["code"], r["origin"]), np.nan)
        expected = a - b
        assert (np.isnan(r["y"]) and np.isnan(expected)) or abs(r["y"] - expected) < 1e-12
    row = op[(op["code"] == "C1") & (op["origin"].isin([2002, 2003]))]
    assert row["y"].isna().all()  # forecast years 2003 and 2004 touch the missing 2003 value
    assert not row["complete"].any()


def test_lag_columns_are_read_from_the_forecast_year_row(synth):
    gold, _, op = synth
    g = gold.set_index(["eurostat_code", "year"])
    r = op[(op["code"] == "C2") & (op["origin"] == 2005)].iloc[0]
    assert r["debt_gdp_T"] == g.loc[("C2", 2006), "debt_gdp_lag"] and r["olddep1_T"] == g.loc[("C2", 2006), "olddep1_lag"]
    assert r["capb_T"] == g.loc[("C2", 2005), "capb"] and r["dcapb_T"] == g.loc[("C2", 2005), "sec_d_capb"] and r["euro_T"] == float(g.loc[("C2", 2005), "euro_member"])
    assert r["y"] == g.loc[("C2", 2006), "sec_d_capb"]


# ---------------------------------------------------------------------------------------------
# Election features: schedule rule, no look-ahead
# ---------------------------------------------------------------------------------------------
def test_known_exposure_on_a_handmade_calendar():
    cal = pd.DataFrame({"eurostat_code": ["A", "A"], "date_used": [TS(1996, 5, 10), TS(2000, 5, 10)], "termlength": [4.0, 4.0], "sche_date": [TS(1996, 5, 10), TS(2000, 5, 10)], "in_calendar": [True, True]})
    out = pr.known_exposure(cal, 2002)  # last election 2000-05-10, scheduled 2000-05-10 + round(365.25 * 4) days
    sched = TS(2000, 5, 10) + pd.Timedelta(days=round(365.25 * 4))
    days = lambda a, b: (b - a).days  # noqa: E731
    exp_next = days(max(sched - pd.DateOffset(years=1), TS(2003, 1, 1)), min(sched, TS(2004, 1, 1))) / 365.0
    assert out["Wk_next"] == pytest.approx(exp_next)
    assert out["Postk_now"] == pytest.approx(0.0) and out["Wk_now"] == pytest.approx(0.0)
    out2 = pr.known_exposure(cal, 2000)  # election day inside the origin year: realised window in year T, post window in T
    assert out2["Wk_now"] == pytest.approx(days(TS(2000, 1, 1), TS(2000, 5, 10)) / 366.0)
    assert out2["Postk_now"] == pytest.approx(days(TS(2000, 5, 10), TS(2001, 1, 1)) / 366.0)
    assert out2["Postk_next"] == pytest.approx(days(TS(2001, 1, 1), TS(2001, 5, 10)) / 365.0)
    assert all(0.0 <= v <= 1.0 for v in out.values())


def test_statutory_term_fallbacks():
    held = pd.DataFrame({"termlength": [4.0, np.nan]})
    assert pr.statutory_term(held) == 4.0  # last non-missing
    assert pr.statutory_term(pd.DataFrame({"termlength": [np.nan, np.nan]})) == pr.DEFAULT_TERM == 5.0


def test_overdue_election_contributes_nothing_to_the_forecast_year():
    cal = pd.DataFrame({"eurostat_code": ["A"], "date_used": [TS(1990, 1, 1)], "termlength": [4.0], "sche_date": [TS(1990, 1, 1)], "in_calendar": [True]})
    out = pr.known_exposure(cal, 2000)  # scheduled 1994, never held in the calendar: the window lies far in the past
    assert out["Wk_next"] == 0.0 and out["Postk_next"] == 0.0


def test_poisoned_future_calendar_leaves_strict_features_unchanged_and_changes_the_oracle():
    codes = [f"C{i}" for i in range(4)]
    cal, poisoned = make_calendar(codes), make_calendar(codes, with_poison_after=2005)
    for origin in (2003, 2004, 2005):
        a = pr.political_features(cal, codes, [origin])
        b = pr.political_features(poisoned, codes, [origin])
        pd.testing.assert_frame_equal(a, b)
    a = pr.political_features(cal, codes, [2005], oracle=True)
    b = pr.political_features(poisoned, codes, [2005], oracle=True)
    assert not np.allclose(a["Wk_next"], b["Wk_next"])  # the leak canary: the oracle reads the future record


def test_postk_now_equals_the_frozen_post_column_on_the_real_calendar():
    cal = pr.load_calendar()
    frozen = pd.read_csv(ROOT / "data" / "interim" / "exposure_eu27.csv").set_index(["eurostat_code", "year"])["Post"]
    codes = sorted(cal["eurostat_code"].unique())
    pol = pr.political_features(cal, codes, list(range(1996, 2023)))  # CZ has no calendar election before 1996 (origin 1995 unused)
    mine = pol.set_index(["code", "origin"])["Postk_now"]
    ref = frozen.reindex(mine.index.set_names(["eurostat_code", "year"]))
    assert np.allclose(mine.to_numpy(), ref.to_numpy(), atol=2e-6)  # the interim CSV is rounded to six decimals
    assert not pol[["Wk_next", "Wk_now", "Postk_next", "Postk_now"]].isna().any().any()  # no row lost to the political block
    assert pol[["Wk_next", "Wk_now", "Postk_next", "Postk_now"]].min().min() >= 0.0 and pol[["Wk_next", "Wk_now", "Postk_next", "Postk_now"]].max().max() <= 1.0


def test_schedule_agreement_check_on_election_dates_only():
    out = pr.schedule_agreement(pr.load_calendar())
    assert out["n_pairs"] > 150 and 0.8 < out["share_within_tolerance"] < 0.95  # 86.7 per cent of the 203 comparable pairs (the spec's 71 per cent counted missing comparisons as misses)


# ---------------------------------------------------------------------------------------------
# No look-ahead on a constructed panel whose future is poisoned
# ---------------------------------------------------------------------------------------------
def _poison_gold(gold: pd.DataFrame, origin: int) -> pd.DataFrame:
    g = gold.copy()
    g["euro_member"] = g["euro_member"].astype(float)
    future = g["year"] > origin + 1
    num = [c for c in g.columns if c not in ("eurostat_code", "year")]
    g.loc[future, num] = 1e6
    nxt = g["year"] == origin + 1  # the forecast-year row: only its lag columns (dated T) are legitimate
    for c in ("capb", "sec_d_capb", "euro_member", "W_S", "W_E", "W_U"):
        g.loc[nxt, c] = 1e6
    return g


FEATURES = ["capb_T", "dcapb_T", "debt_gdp_T", "outgap_T", "ig_diff_T", "euro_T", "olddep1_T", "olddep3_T", "medage_T", "Wk_next", "Wk_now", "Postk_next", "Postk_now"]


def test_poisoned_future_does_not_change_features_or_forecasts(synth):
    gold, cal, op = synth
    t = 2007
    pgold = _poison_gold(gold, t)
    pcal = make_calendar(sorted(gold["eurostat_code"].unique()), with_poison_after=t)
    pop = pr.build_origin_panel(pgold, pcal)
    both = op.merge(pop, on=["code", "origin"], suffixes=("", "_p"))
    usable = both[both["origin"] <= t]
    for c in FEATURES:
        assert np.allclose(usable[c].to_numpy(float), usable[c + "_p"].to_numpy(float), equal_nan=True), c
    done = usable[usable["forecast_year"] <= t]  # realised targets
    assert np.allclose(done["y"].to_numpy(float), done["y_p"].to_numpy(float), equal_nan=True)
    # forecasts of every model class at origin t are bit-identical
    for fit in (lambda d: pr.fit_linear(d, t, "B2", alphas=(0.1, 10.0), l1=(0.5,)),
                lambda d: pr.fit_hgb(d, t, "B2", grid=((2, 20, 0.0),), max_iter=25),
                lambda d: pr.fit_gam(d, t, "B1", alphas=(10.0,))):
        f1, f2 = fit(pr.training_window(op, t)), fit(pr.training_window(pop, t))
        p1, p2 = f1.predict(pr.test_rows(op, t)), f2.predict(pr.test_rows(pop, t))
        assert np.array_equal(p1, p2)
    # canary: a feature built from the frozen realised exposure of the forecast year DOES change under the poison
    assert not np.allclose(op[op["origin"] == t]["fW_S"], pop[pop["origin"] == t]["fW_S"])
    # and the target of the test rows is the (poisoned) future, which no feature carries
    assert (pop[pop["origin"] == t]["y"] > 1e5).all()


# ---------------------------------------------------------------------------------------------
# Transformer: training-window statistics only
# ---------------------------------------------------------------------------------------------
def test_country_means_and_standardisation_use_the_training_window_only(synth):
    _, _, op = synth
    t = 2008
    tr, te = pr.training_window(op, t), pr.test_rows(op, t)
    tf = pr.Transformer(*pr.SETS["B2"], "CD").fit(tr)
    m0 = tf.means.copy()
    te2 = te.copy()
    te2["capb_T"] = te2["capb_T"] + 100.0
    x1, x2 = tf.transform(te), tf.transform(te2)
    pd.testing.assert_frame_equal(m0, tf.means)  # the means are fixed by the training window
    assert not np.allclose(x1, x2)
    z = tf.transform(tr)
    assert np.allclose(z.mean(axis=0), 0, atol=1e-9) and np.allclose(z.std(axis=0), 1, atol=1e-9)
    names = tf.names
    j = names.index("capb_T_bar")
    codes = tr["code"].to_numpy()
    for c in np.unique(codes):
        assert np.ptp(z[codes == c, j]) < 1e-12  # the between part is constant within country
    assert len(names) == 21 and not tf.dropped
    assert set(te["code"]) <= set(tr["code"])  # no country without a training row at an origin


def test_constant_columns_are_dropped_and_reported(synth):
    _, _, op = synth
    tr = pr.training_window(op, 2008).copy()
    tr["euro_T"] = 1.0
    tf = pr.Transformer(*pr.SETS["B1"], "CD").fit(tr)
    assert "euro_T" in tf.dropped and "euro_T" not in tf.names


# ---------------------------------------------------------------------------------------------
# Models: inner validation, early stopping, determinism
# ---------------------------------------------------------------------------------------------
def _signal_op(strength: float, seed: int = 3) -> pd.DataFrame:
    gold = make_gold(n_codes=8, last=2012, seed=seed)
    cal = make_calendar(sorted(gold["eurostat_code"].unique()))
    op = pr.build_origin_panel(gold, cal)
    rng = np.random.default_rng(seed)
    op["y"] = strength * np.sin(2 * op["debt_gdp_T"].fillna(0) / 5) + rng.normal(scale=1.0, size=len(op))
    return op


def test_early_stopping_iteration_grows_with_signal_and_is_small_for_noise():
    noise, signal = _signal_op(0.0), _signal_op(3.0)
    t = 2008
    a = pr.fit_hgb(pr.training_window(noise, t), t, "B1", grid=((2, 20, 0.0),), max_iter=300)
    b = pr.fit_hgb(pr.training_window(signal, t), t, "B1", grid=((2, 20, 0.0),), max_iter=300)
    assert a.info["n_iter"] < b.info["n_iter"] and b.info["n_iter"] > 20


def test_fits_are_deterministic_and_inner_validation_picks_regularisation():
    op = _signal_op(0.0)
    t = 2008
    tr, te = pr.training_window(op, t), pr.test_rows(op, t)
    f1, f2 = pr.fit_linear(tr, t, "B2"), pr.fit_linear(tr, t, "B2")
    assert np.array_equal(f1.predict(te), f2.predict(te)) and f1.info["alpha"] == f2.info["alpha"]
    assert f1.info["n_nonzero"] <= 3  # pure noise: a sparse, strongly shrunk model wins the inner validation (21 inputs)
    h1, h2 = pr.fit_hgb(tr, t, "B1", grid=((2, 20, 0.0),), max_iter=30), pr.fit_hgb(tr, t, "B1", grid=((2, 20, 0.0),), max_iter=30)
    assert np.array_equal(h1.predict(te), h2.predict(te))


def test_pick_breaks_ties_towards_the_more_regularised_configuration():
    assert pr._pick(np.array([1.0, 1.0, 2.0]), [(-1,), (-10,), (0,)]) == 1


def test_loco_removes_the_country_and_forecasts_only_it():
    op = _signal_op(1.0)
    job = {"kind": "main", "model": "P1a", "set": "B1", "scheme": "CD", "loco": "C3", "origin": 2008}
    assert "C3" not in set(pr.training_window(op, 2008, exclude="C3")["code"])
    res = pr.run_job(job, op, cache=None)
    assert res["status"] == "ok" and set(res["preds"]["code"]) == {"C3"} and np.isfinite(res["preds"]["yhat"]).all()


def test_failed_fit_is_reported_not_raised():
    op = _signal_op(1.0)
    res = pr.run_job({"kind": "main", "model": "P1z", "set": "B1", "scheme": "CD", "loco": None, "origin": 2008}, op, cache=None)
    assert res["status"] == "failed" and "unknown model" in res["error"]


def test_job_cache_roundtrip(tmp_path):
    op = _signal_op(1.0)
    job = {"kind": "main", "model": "P1a", "set": "B0", "scheme": "CD", "loco": None, "origin": 2008}
    a = pr.run_job(job, op, cache=tmp_path)
    b = pr.run_job(job, op, cache=tmp_path)
    assert a["preds"] == b["preds"] and list(tmp_path.glob("*.json"))


# ---------------------------------------------------------------------------------------------
# Interpretation tools
# ---------------------------------------------------------------------------------------------
def test_ale_recovers_an_additive_function():
    rng = np.random.default_rng(1)
    x = rng.normal(size=(2000, 3))
    f = lambda z: 2.0 * z[:, 0] + z[:, 1] ** 2  # noqa: E731
    edges, ale = pr.ale_first_order(f, x, 0)
    assert np.allclose(np.diff(ale) / np.diff(edges), 2.0, atol=1e-9)
    assert abs(np.average((ale[:-1] + ale[1:]) / 2)) < 0.3
    _, ale2 = pr.ale_first_order(f, x, 2)
    assert np.allclose(ale2, 0.0, atol=1e-12)
    e1, a1 = pr.ale_first_order(f, x, 1)
    assert a1.max() - a1.min() > 1.0  # the quadratic shape is recovered


def test_permutation_importance_ranks_the_informative_group_first():
    op = _signal_op(0.0, seed=5)
    rng = np.random.default_rng(5)
    op["y"] = 2.0 * op["capb_T"] + rng.normal(scale=0.3, size=len(op))
    t = 2008
    tr, te = pr.training_window(op, t), pr.test_rows(op, t)
    f = pr.fit_linear(tr, t, "B2", alphas=(0.1,), l1=())
    out = pr.permutation_and_ale(f, te, tr, t, 1, reps=30, do_ale=True)
    inc = {k: np.sum(v) for k, v in out["inc"].items()}
    assert inc["group:fiscal_macro"] > 5 * max(inc["group:political"], inc["group:demographic"], 1e-9)
    assert "capb_T_dm" in out["ale"]


# ---------------------------------------------------------------------------------------------
# Metrics and tests
# ---------------------------------------------------------------------------------------------
def test_dm_hln_matches_the_paired_t_statistic_on_a_known_differential():
    d = np.array([0.5, 0.2, -0.1, 0.4, 0.3, 0.6, 0.1, 0.0, 0.35, 0.25, 0.45, 0.15, 0.3])
    r = pr.dm_hln(d)
    n = len(d)
    g0 = np.mean((d - d.mean()) ** 2)
    assert r["dm"] == pytest.approx(d.mean() / np.sqrt(g0 / n))
    assert r["hln"] == pytest.approx(r["dm"] * np.sqrt((n - 1) / n))  # HLN factor for h = 1
    t = stats.ttest_1samp(d, 0.0)
    assert r["hln"] == pytest.approx(t.statistic) and r["p"] == pytest.approx(t.pvalue) and r["df"] == 12
    assert pr.dm_hln(-d)["hln"] == pytest.approx(-r["hln"]) and pr.dm_hln(-d)["p"] == pytest.approx(r["p"])


def test_loss_differential_sign_and_axis():
    e_bench = np.array([[1.0, 2.0], [3.0, 2.0]])
    e_model = np.array([[0.5, 2.0], [1.0, 3.0]])
    d = pr.loss_differential(e_bench, e_model)
    assert d == pytest.approx([np.mean([1 - 0.25, 9 - 1]), np.mean([4 - 4, 4 - 9])])  # positive favours the model
    assert pr.loss_differential(e_bench, e_model, "abs") == pytest.approx([np.mean([0.5, 2.0]), np.mean([0.0, -1.0])])


def test_calibration_slope_on_known_cases():
    x = np.linspace(-2, 2, 50)
    assert pr.calibration_fit(2 * x + 0.5, x) == pytest.approx((2.0, 0.5))
    assert pr.calibration_fit(x, x) == pytest.approx((1.0, 0.0))
    b, a = pr.calibration_fit(np.ones(5), np.zeros(5))
    assert np.isnan(b) and np.isnan(a)
    per = []
    for k in range(5):
        xs, ys = x[k * 10:(k + 1) * 10], (2 * x + 0.5)[k * 10:(k + 1) * 10]
        per.append([10, xs.sum(), ys.sum(), (xs * xs).sum(), (xs * ys).sum()])
    out = pr.calibration_boot(np.array(per), pr.boot_indices(5, b=200, key=9))
    assert out["slope"] == pytest.approx(2.0) and out["intercept"] == pytest.approx(0.5) and out["slope_ci"][0] == pytest.approx(2.0)


def test_rmse_mae_holm_and_bootstrap_reproducibility():
    e = np.array([1.0, -2.0, 2.0, 0.0])
    assert pr.rmse(e) == pytest.approx(np.sqrt(9 / 4)) and pr.mae(e) == pytest.approx(1.25)
    assert pr.holm_adjust([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    a, b = pr.boot_indices(27, b=50, key=0), pr.boot_indices(27, b=50, key=0)
    assert np.array_equal(a, b) and not np.array_equal(a, pr.boot_indices(27, b=50, key=1)) and a.max() < 27


def test_family_tests_on_planted_cubes_and_holm_is_monotone():
    rng = np.random.default_rng(0)
    base = rng.normal(size=(27, 13))
    cubes = {"P0": base, "P1a-B1": base * 0.8, "P1b-B1": base * 1.0, "P1a-B2": base * 0.7, "P1b-B2": base * 1.0 + 0.0}
    idx = pr.boot_indices(27, b=300, key=3)
    fam = pr.family_tests(cubes, idx)
    assert len(fam) == 6 and all(r["status"] == "ok" for r in fam)
    assert fam[0]["mean"] > 0 and fam[0]["p_holm"] >= fam[0]["p"]
    assert fam[1]["p"] == 1.0 or np.isnan(fam[1]["p"]) or fam[1]["mean"] == pytest.approx(0.0)
    assert all("rel_reduction_ci" in r for r in fam)


def test_event_metrics_known_case():
    rows = pd.DataFrame({"y": [1, 0, 1, 0, 0, 1], "p": [0.8, 0.2, 0.6, 0.4, 0.1, 0.9], "rate": [0.5] * 6})
    m = pr.event_metrics(rows)
    assert m["brier"] == pytest.approx(np.mean((rows["y"] - rows["p"]) ** 2)) and m["auc"] == pytest.approx(1.0) and m["brier_skill"] > 0


# ---------------------------------------------------------------------------------------------
# Guards, frozen files, vocabulary
# ---------------------------------------------------------------------------------------------
def test_real_panel_is_refused_without_the_tag(monkeypatch):
    monkeypatch.setattr(m1, "tag_exists", lambda: False)
    with pytest.raises(m1.PreregistrationTagMissing):
        pr.load_real()


def test_frozen_files_are_byte_identical_to_the_manifest():
    status = pr.frozen_unchanged()
    assert status and all(status.values()), [k for k, v in status.items() if not v]


def test_rendered_report_has_no_forbidden_vocabulary_and_states_required_phrases():
    md = pr.MD_PATH
    if not md.exists():
        pytest.skip("report not yet generated")
    text = md.read_text(encoding="utf-8").lower().replace("`", "")
    assert not [w for w in pr.FORBIDDEN_WORDS if w in text]
    for phrase in ("predictive", "shap: not run: not installed", "deviations", "holm", "raw p"):
        assert phrase in text
    card = ROOT / "docs" / "model_card.md"
    if card.exists():
        assert not [w for w in pr.FORBIDDEN_WORDS if w in card.read_text(encoding="utf-8").lower()]


def test_json_output_is_valid_when_present():
    if not pr.JSON_PATH.exists():
        pytest.skip("report not yet generated")
    data = json.loads(pr.JSON_PATH.read_text(encoding="utf-8"))
    assert {"meta", "status", "deviations", "results"} <= set(data)
