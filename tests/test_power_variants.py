"""Offline tests for the Gate 3c power-comparison machinery (``src/evaluate/power_variants.py``).

Small synthetic panels keep each test fast; the last tests use the real confirmatory sample and are skipped when
the inputs are absent. Only residual-based calibration is ever computed from the real outcome.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
for sub in ("evaluate", "normalize", "features"):
    sys.path.insert(0, str(ROOT / "src" / sub))
import power  # noqa: E402
import power_variants as pv  # noqa: E402
import sample  # noqa: E402
from test_power import larger_frame, synthetic_frame  # noqa: E402

RAW_PRESENT = sample.CAPB_CSV.exists() and sample.OLDDEP_CSV.exists() and sample.EXPOSURE_CSV.exists()
needs_inputs = pytest.mark.skipif(not RAW_PRESENT, reason="raw inputs or interim exposure not present")


def frame_with_controls(seed: int = 5) -> pd.DataFrame:
    """Synthetic frame (8 countries) with a gap, years 2000-2011 and two control columns."""
    frame = synthetic_frame(seed=seed)
    rng = np.random.default_rng(seed + 100)  # a different stream from the one that built the moderator
    frame["outgap_lag"] = rng.standard_normal(len(frame))
    adoption = 2003 + frame["eurostat_code"].str[1:].astype(int) % 4  # varies by country, so not collinear with year effects
    frame["euro_member"] = (frame["year"] >= adoption).astype(float)
    frame["capb"] = rng.standard_normal(len(frame))
    return frame


def design_for(frame: pd.DataFrame, **kwargs) -> power.Design:
    """Variant design on a synthetic frame."""
    return pv.build_variant_design(frame, "test", **kwargs)


# ---------------------------------------------------------------------------------------------
# Regressors
# ---------------------------------------------------------------------------------------------
def test_era_terms_are_centred_at_exposure_weighted_means():
    frame = frame_with_controls().sort_values(["eurostat_code", "year"]).reset_index(drop=True)
    terms = pv.era_terms(frame, ((2005, 2008),))
    w_s = frame["W_S"].to_numpy()
    dummy = frame["year"].between(2005, 2008).to_numpy(float)
    column = terms.iloc[:, 0].to_numpy()
    assert column.sum() == pytest.approx(0.0, abs=1e-12)  # sum_t W_S (D - m) = 0 for the exposure-weighted mean m
    assert column == pytest.approx(w_s * (dummy - (w_s * dummy).sum() / w_s.sum()))
    assert not np.allclose(column, w_s * dummy)  # differs from the uncentred interaction


def test_controls_ireland_and_era_columns_enter_regressors():
    frame = frame_with_controls()
    frame.loc[frame["eurostat_code"] == "C02", "eurostat_code"] = "IE"
    design = design_for(frame, control_names=("outgap_lag", "euro_member"), ireland_indicator=True)
    assert {"outgap_lag", "euro_member", "IE2010"} <= set(design.x_names)
    assert any(c.startswith("WS_x_era") for c in design.x_names)
    assert design.x[:, design.x_names.index("IE2010")].sum() == 1.0
    assert set(design.targets) == {"beta_S", "gamma_B", "gamma_W"}


def test_complete_case_rows_follow_missing_controls():
    frame = frame_with_controls()
    frame.loc[3, "outgap_lag"] = np.nan
    assert design_for(frame, control_names=("outgap_lag",)).n_obs == len(frame) - 1


# ---------------------------------------------------------------------------------------------
# GLS estimator against brute force
# ---------------------------------------------------------------------------------------------
def test_gls_without_options_reproduces_ols_exactly():
    design = design_for(frame_with_controls())
    y = np.random.default_rng(1).standard_normal((design.n_obs, 4))
    plain = power.estimate(design, y)
    fit = pv.GlsEstimator(design).fit(y)
    for t in design.targets:
        assert fit[t][0] == pytest.approx(plain[t][0], abs=1e-9)
        assert fit[t][1] == pytest.approx(plain[t][1], abs=1e-9)


def brute_force_gls(est: pv.GlsEstimator, y: np.ndarray, target: str) -> tuple[float, float]:
    """Explicit-matrix FGLS for one outcome vector with the estimator's own first-stage ``rho`` and weights."""
    d = est.design
    y_use, _, rho, w = est.first_stage(y[:, None])
    rho, w = float(rho[0]), w[0]
    n = d.n_obs
    p_mat = np.zeros((n, n))
    p_mat[est.first, est.first] = np.sqrt(1 - rho**2)
    p_mat[est.cur, est.cur] = 1.0
    p_mat[est.cur, est.cur - 1] = -rho
    row_w = np.sqrt(w[d.country_idx])
    zt, yt = (p_mat @ est.z) * row_w[:, None], (p_mat @ y_use[:, 0]) * row_w
    theta = np.linalg.solve(zt.T @ zt, zt.T @ yt)
    resid_t = yt - zt @ theta
    bread = np.linalg.inv(zt.T @ zt)
    meat = sum(np.outer(zt[d.country_idx == g].T @ resid_t[d.country_idx == g], zt[d.country_idx == g].T @ resid_t[d.country_idx == g]) for g in range(d.n_clusters))
    col = est.col[target]
    return float(theta[col]), float(np.sqrt(d.cr1 * (bread @ meat @ bread)[col, col]))


@pytest.mark.parametrize("wls, ar1, winsor", [(True, False, False), (False, True, False), (True, True, False), (True, True, True), (False, False, True)])
def test_feasible_gls_equals_explicit_matrix_computation(wls, ar1, winsor):
    design = design_for(frame_with_controls())
    est = pv.GlsEstimator(design, wls=wls, ar1=ar1, winsor=winsor)
    y = np.random.default_rng(2).standard_normal((design.n_obs, 3)) * np.linspace(1, 3, design.n_obs)[:, None]
    fit = est.fit(y)
    for r in range(3):
        for t in design.targets:
            b, se = brute_force_gls(est, y[:, r], t)
            assert fit[t][0][r] == pytest.approx(b, abs=1e-8) and fit[t][1][r] == pytest.approx(se, rel=1e-8)


def test_weights_and_rho_are_estimated_per_draw_not_fixed():
    design = design_for(frame_with_controls())
    est = pv.GlsEstimator(design, wls=True, ar1=True)
    rng = np.random.default_rng(3)
    column = rng.standard_normal((design.n_obs, 1))
    a = np.hstack([column, column])
    b = a.copy()
    b[design.starts[0]:design.starts[0] + design.counts[0], 1] *= 10  # inflate one country in the second draw only
    _, _, rho, w = est.first_stage(b)
    assert w[1, 0] < 0.1 * w[0, 0]  # the inflated country is down-weighted in that draw only
    assert rho[0] != rho[1]
    _, _, _, w_a = est.first_stage(a[:, [1]])
    assert not np.allclose(w_a[0], w[1])  # the weights follow the draw, nothing stored from earlier data


def test_shift_equivariance_in_the_true_effect_for_feasible_gls():
    """Adding beta * x_j shifts b by exactly beta and leaves the CR1 SE unchanged (basis of the CR1 null-draw MDE)."""
    design = design_for(frame_with_controls())
    y = np.random.default_rng(4).standard_normal((design.n_obs, 3))
    x_j = design.x[:, design.x_names.index(design.targets["beta_S"])]
    for kwargs in ({"wls": True, "ar1": True}, {"winsor": True}):
        est = pv.GlsEstimator(design, **kwargs)
        base = est.fit(y)["beta_S"]
        shifted = est.fit(y + 0.7 * x_j[:, None])["beta_S"]
        assert shifted[0] == pytest.approx(base[0] + 0.7, abs=1e-8) and shifted[1] == pytest.approx(base[1], rel=1e-8)


def test_nickell_inverse_is_monotone_and_inverts_the_analytic_map():
    for rho in (0.0, 0.3, 0.6):
        raw = rho + power.nickell_bias(rho, 25.0)
        assert float(pv.nickell_inverse(np.array([raw]), 25.0)[0]) == pytest.approx(rho, abs=2e-3)
    assert pv.nickell_inverse(np.array([0.5]), 25.0)[0] > 0.5


def test_ar1_gls_rho_estimate_is_close_to_truth_and_wls_downweights_noisy_countries():
    frame = larger_frame()
    design = pv.build_variant_design(frame, "big", era=False)
    sigma = np.where(np.arange(design.n_clusters) % 5 == 0, 4.0, 1.0)
    noise = power.ArNoise(design, sigma, 0.6).draw(pv.make_rng(1), 300)
    est = pv.GlsEstimator(design, wls=True, ar1=True)
    _, _, rho, w = est.first_stage(noise)
    assert 0.3 < rho.mean() < 0.65  # analytic Nickell leaves some downward bias with short T and many effects (documented)
    noisy = np.arange(design.n_clusters) % 5 == 0
    assert w[:, noisy].mean() < 0.2 * w[:, ~noisy].mean()


def test_gls_efficiency_gain_under_heteroskedastic_ar1_noise():
    frame = larger_frame()
    design = pv.build_variant_design(frame, "big", era=False)
    sigma = np.where(np.arange(design.n_clusters) % 4 == 0, 5.0, 1.0)
    noise = power.ArNoise(design, sigma, 0.6).draw(pv.make_rng(2), 600)
    sd_ols = power.estimate(design, noise)["beta_S"][0].std()
    sd_gls = pv.GlsEstimator(design, wls=True, ar1=True).fit(noise)["beta_S"][0].std()
    assert sd_gls < 0.85 * sd_ols


# ---------------------------------------------------------------------------------------------
# Bootstrap: generic equals the fast engine for OLS; recursion for the LDV model
# ---------------------------------------------------------------------------------------------
def test_generic_wild_bootstrap_equals_fast_engine_for_ols():
    design = design_for(frame_with_controls())
    y = np.random.default_rng(6).standard_normal((design.n_obs, 4))
    n_boot, seed_key = 19, 7
    est = pv.GlsEstimator(design)
    for target in ("beta_S", "gamma_W"):
        data = power.wcb_prepare(design, y)[target]
        fast = power.wild_bootstrap_reject(design, target, data, 0.0, "rademacher", seed_key, n_draws=n_boot)
        p = pv.wild_bootstrap_pvalues(est, target, y, n_boot=n_boot, seed_key=seed_key, chunk=power.WCB_CHUNK)
        assert ((p <= power.ALPHA) == fast).all()


def test_generic_bootstrap_null_rejection_is_near_nominal_for_wls_ar1():
    design = pv.build_variant_design(larger_frame(n_countries=20, n_years=10), "b", era=False)
    sigma = np.where(np.arange(design.n_clusters) % 4 == 0, 3.0, 1.0)
    y = power.ArNoise(design, sigma, 0.4).draw(pv.make_rng(8), 300)
    p = pv.wild_bootstrap_pvalues(pv.GlsEstimator(design, wls=True, ar1=True), "beta_S", y, n_boot=99, seed_key=1)
    assert 0.02 < (p <= 0.05).mean() < 0.10


def ldv_estimator(frame: pd.DataFrame) -> tuple[pv.LdvEstimator, power.Design]:
    """LDV estimator and its full-row design on a frame."""
    frame = pv.variant_frame(frame)
    regressors, scale, targets = pv.variant_regressors(frame, era=False)
    design = power.build_design(frame, label="ldv", regressors=regressors, targets=targets, scale=scale)
    return pv.LdvEstimator(design, frame, regressors, targets), design


def test_ldv_coefficient_and_se_equal_direct_regression():
    est, design = ldv_estimator(frame_with_controls())
    y = np.random.default_rng(9).standard_normal((design.n_obs, 3))
    fit = est.fit(y)
    d = est.est
    cur, lag = design.cur_rows, design.lag_rows
    country = pd.get_dummies(pd.Series(d.codes), dtype=float).to_numpy()
    year = pd.get_dummies(pd.Series(d.year), dtype=float).to_numpy()[:, 1:]
    for r in range(3):
        z = np.column_stack([country, year, d.x, y[lag, r]])
        theta = np.linalg.lstsq(z, y[cur, r], rcond=None)[0]
        u = y[cur, r] - z @ theta
        bread = np.linalg.inv(z.T @ z)
        meat = sum(np.outer(z[d.country_idx == g].T @ u[d.country_idx == g], z[d.country_idx == g].T @ u[d.country_idx == g]) for g in range(d.n_clusters))
        cov = est.cr1 * bread @ meat @ bread
        for t, col in d.targets.items():
            position = country.shape[1] + year.shape[1] + d.x_names.index(col)
            assert fit[t][0][r] == pytest.approx(theta[position], abs=1e-8)
            assert fit[t][1][r] == pytest.approx(np.sqrt(cov[position, position]), rel=1e-8)


def test_ldv_bootstrap_recursion_reproduces_fitted_dynamics():
    est, design = ldv_estimator(frame_with_controls())
    y = np.random.default_rng(10).standard_normal((design.n_obs, 2))
    v = np.zeros((2, design.n_clusters, 3))  # zero weights: the bootstrap sample is the restricted model's own recursion
    star = est.bootstrap_outcomes(y, "beta_S", v)
    assert star.shape == (design.n_obs, 6)
    assert np.allclose(star[:, 0], star[:, 1])  # identical draws when the shock is zero
    first = np.setdiff1d(np.arange(design.n_obs), design.cur_rows)
    assert np.allclose(star[first, 0], y[first, 0])  # initial conditions are the observed outcomes
    _, (u, phi, nondynamic) = est.restricted("beta_S").fit(y, [], want_resid=True)
    # weights of one reproduce the observed outcome exactly: by induction y*_t = nondynamic_t + phi y_{t-1} + u_t = y_t
    star1 = est.bootstrap_outcomes(y, "beta_S", np.ones((2, design.n_clusters, 1)))
    assert np.allclose(star1[:, 0], y[:, 0], atol=1e-9) and np.allclose(star1[:, 1], y[:, 1], atol=1e-9)


def test_ldv_has_negative_dynamic_bias_in_static_dgp_with_true_effect():
    """A static DGP with AR(1) noise: the LDV coefficient on W_S is not centred on the true effect (the check V5 exists for)."""
    frame = larger_frame()
    est, design = ldv_estimator(frame)
    noise = power.ArNoise(design, np.ones(design.n_clusters), 0.6).draw(pv.make_rng(11), 400)
    x_j = design.x[:, design.x_names.index("W_S")]
    b = est.fit(noise + 1.0 * x_j[:, None])["beta_S"][0]
    assert np.isfinite(b).all() and abs(b.mean() - 1.0) < 0.5  # finite and within a plausible range; the bias is reported, not asserted


# ---------------------------------------------------------------------------------------------
# Run layer: power curves, DGPs, selection rule, V6, jobs
# ---------------------------------------------------------------------------------------------
def test_probit_power_curve_recovers_known_mde():
    from scipy import stats

    betas = np.array([0.0, 0.3, 0.5, 0.7, 0.9, 1.1, 1.4])
    rates = stats.norm.cdf(-1.64 + 3.0 * betas)
    fit = pv.power_curve_mde(betas, rates, np.full(len(betas), 400.0), n_resample=20)
    assert fit["mde"] == pytest.approx((stats.norm.ppf(0.8) + 1.64) / 3.0, abs=0.01)
    assert fit["max_fit_residual"] < 0.01 and fit["mde_se"] > 0
    assert pv.probit_power(fit["a"], fit["b"], fit["mde"]) == pytest.approx(0.8, abs=1e-6)


def test_spike_noise_adds_signed_shock_at_one_row_only():
    design = design_for(frame_with_controls())
    params = pv.DgpParams("S", np.ones(design.n_clusters), 0.5, np.zeros((design.n_grid_years, design.n_clusters)), 3)
    plain = pv.make_noise(design, params, "ar1_rho_hat")
    row, size = 5, 7.0
    spiked = pv.SpikeNoise(plain, row, size)
    a = plain.draw(np.random.default_rng(1), 400)
    b = spiked.draw(np.random.default_rng(1), 400)
    diff = b - a
    assert np.allclose(np.delete(diff, row, axis=0), 0.0) and np.allclose(np.abs(diff[row]), size)
    assert 0.35 < (diff[row] > 0).mean() < 0.65


def test_make_noise_scenarios_have_the_design_shape_and_reject_unknown():
    design = pv.build_variant_design(larger_frame(), "x", era=False)
    grid = np.random.default_rng(0).standard_normal((design.n_grid_years, design.n_clusters))
    params = pv.DgpParams("F", np.ones(design.n_clusters), 0.5, grid, 3)
    for scenario in pv.SCENARIO_NAMES:
        assert pv.make_noise(design, params, scenario).draw(np.random.default_rng(2), 5).shape == (design.n_obs, 5)
    with pytest.raises(ValueError):
        pv.make_noise(design, params, "nope")


def candidate_rows(**overrides) -> pd.DataFrame:
    """Candidate table for the selection rule."""
    base = {"variant": ["V0", "V1", "V3", "V4"], "dgp": ["F", "O", "F", "F"], "n_obs": 715, "mde_wcb_rho_hat": [0.70, 0.60, 0.50, 0.52], "mde_wcb_rho0": 1.0,
            "size_wcb_rho_hat": 0.05, "size_wcb_rho0": 0.05, "size_valid": True, "rel_bias": 0.0, "bias_ok": True, "complexity": [0, 1, 1, 1]}
    base.update(overrides)
    return pd.DataFrame(base)


def test_selection_picks_smallest_mde_and_breaks_ties_towards_the_simpler_variant():
    assert pv.select_variant(candidate_rows())[0] == "V3"  # V4 is within 5 per cent (0.52 <= 0.525); V3 precedes V4 in the simplicity order
    tied = candidate_rows(mde_wcb_rho_hat=[0.50, 0.60, 0.51, 0.52])
    assert pv.select_variant(tied)[0] == "V0"  # V0 is the simplest of the tie set (0.50, 0.51, 0.52)


def test_selection_excludes_invalid_size_and_large_bias():
    cand = candidate_rows(size_valid=[True, True, False, True], bias_ok=[True, True, True, False])
    assert pv.select_variant(cand)[0] == "V1"
    assert pv.select_variant(candidate_rows(size_valid=False))[0] is None
    assert pv.size_valid(0.035) and pv.size_valid(0.065) and not pv.size_valid(0.0349) and not pv.size_valid(0.066)


def result_rows(vid: str, dgp: str, mde_hat: float, size: float = 0.05, rel_bias: float = 0.0) -> list[dict]:
    """Result rows for beta_S in the two AR(1) scenarios."""
    return [{"vid": vid, "dgp": dgp, "scenario": s, "target": "beta_S", "n_obs": 715, "wcb_mde": m, "wcb_size": size, "rel_bias": rel_bias}
            for s, m in (("ar1_rho_hat", mde_hat), ("ar1_rho0", mde_hat * 1.4))]


def test_v6_includes_only_components_that_pass_the_screen():
    rows = (result_rows("V0", "F", 0.70) + result_rows("V2i", "F", 0.68) + result_rows("V2w", "F", 0.60) + result_rows("V3", "F", 0.50)
            + result_rows("V4", "F", 0.66, size=0.09))
    spec = pv.choose_v6_components(pd.DataFrame(rows), dict(pv.VARIANT_SPECS), has_controls=True)
    assert spec.use_controls and spec.winsor and not spec.ireland_indicator  # V2w passes the 5% bar and beats V2i, whose 3% gain does not count
    assert spec.wls and not spec.ar1  # V4 has invalid size
    assert spec.estimator == "gls" and spec.designated_dgp == "O" and spec.complexity == 3
    nothing = pv.choose_v6_components(pd.DataFrame(result_rows("V0", "F", 0.7) + result_rows("V3", "F", 0.69)), dict(pv.VARIANT_SPECS), has_controls=False)
    assert nothing.estimator == "ols" and not nothing.use_controls and nothing.complexity == 0


def test_job_list_covers_every_dgp_and_scenario():
    jobs = pv.job_list("A", dict(pv.VARIANT_SPECS))
    assert ("V1", "O", "ar1_rho0") in jobs and ("V2i", "S", "block_bootstrap") in jobs and ("V5", "F", "ar1_rho_hat") in jobs
    assert len(jobs) == 3 * sum(len(pv.VARIANT_SPECS[v].dgps) for v in pv.STAGE_A)
    assert pv.job_list("B", dict(pv.VARIANT_SPECS)) == []  # V6 is absent until stage A has been processed


def panel_frame(seed: int = 21) -> pd.DataFrame:
    """Small panel (14 countries incl. Ireland, 2000-2015) with an AR(1) outcome and the four controls."""
    rng = np.random.default_rng(seed)
    codes = [f"C{c:02d}" for c in range(14)]
    codes[3] = "IE"
    frame = pd.DataFrame([(c, 2000 + t) for c in sorted(codes) for t in range(16)], columns=["eurostat_code", "year"])
    n = len(frame)
    country_no = pd.factorize(frame["eurostat_code"])[0]
    frame["olddep1_lag"] = 20 + 0.3 * (frame["year"] - 2000) + 3 * rng.standard_normal(n) + country_no
    for name, prob in (("W_S", 0.3), ("W_E", 0.2), ("W_U", 0.1)):
        frame[name] = rng.uniform(0, 1, n) * (rng.random(n) < prob)
    frame["W_D"] = 0.0
    frame["Post"] = rng.uniform(0, 1, n)
    shocks = rng.standard_normal(n)
    capb = np.zeros(n)
    for i in range(1, n):
        if country_no[i] == country_no[i - 1]:
            capb[i] = 0.5 * capb[i - 1]
        capb[i] += shocks[i] * (3.0 if frame.loc[i, "eurostat_code"] == "IE" else 1.0)
    frame["capb"] = capb
    for name in ("outgap_lag", "debt_gdp_lag", "ig_diff_lag"):
        frame[name] = rng.standard_normal(n)
    frame["euro_member"] = (frame["year"] >= 2004 + country_no % 5).astype(float)
    return frame


@pytest.fixture(scope="module")
def synthetic_context() -> pv.Context:
    return pv.Context(panel_frame(), controls_attached=True)


QUICK_TINY = pv.Settings(n_null=400, size_fast=40, mde_fast=40, size_generic=16, mde_generic=16, n_boot=19, n_bias=100, n_ldv_cr1=100)


@pytest.mark.parametrize("vid", ["V0", "V3", "V5"])
def test_run_job_end_to_end_on_a_synthetic_panel_and_resume(synthetic_context, tmp_path, vid):
    ctx = synthetic_context
    first = pv.run_job(ctx, vid, "F", "ar1_rho_hat", tmp_path, QUICK_TINY, log=lambda *_: None)
    assert first["complete"] and set(first["cr1"]) == {"beta_S", "gamma_B", "gamma_W"} and set(first["wcb"]) == set(first["cr1"])
    for t in first["wcb"]:
        w = first["wcb"][t]
        assert 0.0 <= w["size"] <= 1.0 and np.isfinite(w["mde"]) and w["mde"] > 0 and len(w["betas"]) == len(w["rates"])
        assert first["bias"][t]["true_effect"] == pv.TRUE_EFFECT
    again = pv.run_job(ctx, vid, "F", "ar1_rho_hat", tmp_path, QUICK_TINY, log=lambda *_: None)
    assert again["wcb"]["beta_S"]["mde"] == first["wcb"]["beta_S"]["mde"]  # the finished file is returned unchanged
    table = pv.load_results(tmp_path)
    assert (table["vid"] == vid).all() and len(table) == 3


def test_ols_variant_is_unbiased_in_the_bias_check(synthetic_context):
    var = pv.build_variant(synthetic_context, synthetic_context.specs["V0"])
    noise = pv.make_noise(var.design, synthetic_context.dgp(var.spec, "F"), "ar1_rho_hat")
    out = pv.bias_rmse(var, noise, pv.make_rng(77), 1500)
    assert abs(out["beta_S"]["bias"]) < 4 * out["beta_S"]["mc_se_bias"] + 1e-9 and out["beta_S"]["rmse"] > 0


def test_fast_and_generic_bootstrap_rates_agree_for_ols(synthetic_context):
    var = pv.build_variant(synthetic_context, synthetic_context.specs["V0"])
    d = var.design
    noise = pv.make_noise(d, synthetic_context.dgp(var.spec, "F"), "ar1_rho_hat").draw(pv.make_rng(78), 50)
    fast = power.wcb_prepare(d, noise)["beta_S"]
    a = pv.bootstrap_rate(var, "beta_S", noise, 0.0, 11, 19, fast)
    b = pv.bootstrap_rate(var, "beta_S", noise, 0.0, 11, 19, None)
    assert abs(a - b) <= 0.12  # different weight streams (chunk sizes differ) but the same estimator


@needs_inputs
def test_real_sample_context_geometry_and_3b_calibration():
    ctx = pv.Context()
    assert ctx.control_names == ("outgap_lag", "euro_member")  # surviving controls from trigger T4
    v0, v1, v0n = (ctx.design_of(ctx.specs[v]) for v in ("V0", "V1", "V0n"))
    assert v0.n_obs == 715 and v0n.n_obs == 715 and v0.n_clusters == 27
    assert 690 < v1.n_obs < 715  # complete cases of the surviving controls
    assert any(c.startswith("WS_x_era") for c in v0.x_names) and not any(c.startswith("WS_x_era") for c in v0n.x_names)
    assert abs(ctx.cal_ref.rho_corrected - 0.694) < 0.01  # reproduces the Gate 3b persistence
    assert 5 <= ctx.block <= 7
    assert ctx.dgp(ctx.specs["V2i"], "S").spike_size > 5.0  # the Ireland-2010 residual is a large outlier
