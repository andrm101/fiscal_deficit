"""Offline tests for the Gate 3b power machinery (``src/evaluate/power.py``).

Synthetic panels keep every test fast; the last tests use the real final sample and are skipped when the
interim exposure file or the raw inputs are missing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "evaluate"))
sys.path.insert(0, str(ROOT / "src" / "normalize"))
import power  # noqa: E402
import sample  # noqa: E402

RAW_PRESENT = sample.CAPB_CSV.exists() and sample.OLDDEP_CSV.exists() and sample.EXPOSURE_CSV.exists()
needs_inputs = pytest.mark.skipif(not RAW_PRESENT, reason="raw inputs or interim exposure not present")


def synthetic_frame(n_countries: int = 8, first_year: int = 2000, last_year: int = 2011, seed: int = 1, drop: tuple[tuple[int, int], ...] = ((4, 2005),)) -> pd.DataFrame:
    """Unbalanced synthetic panel with the columns that ``build_design`` needs (``W_D`` is identically zero)."""
    rng = np.random.default_rng(seed)
    rows = [
        {"eurostat_code": f"C{c:02d}", "year": year}
        for c in range(n_countries)
        for year in range(first_year + (c % 3), last_year + 1)
        if (c, year) not in drop
    ]
    frame = pd.DataFrame(rows)
    n = len(frame)
    country_no = frame["eurostat_code"].str[1:].astype(int)
    frame["olddep1_lag"] = 20 + 0.3 * (frame["year"] - first_year) + 3 * rng.standard_normal(n) + country_no
    frame["W_S"] = rng.uniform(0, 1, n) * (rng.random(n) < 0.3)
    frame["W_E"] = rng.uniform(0, 1, n) * (rng.random(n) < 0.2)
    frame["W_D"] = 0.0
    frame["W_U"] = rng.uniform(0, 1, n) * (rng.random(n) < 0.1)
    frame["Post"] = rng.uniform(0, 1, n)
    frame["capb"] = rng.standard_normal(n)
    return frame


def larger_frame(n_countries: int = 30, n_years: int = 12, seed: int = 3) -> pd.DataFrame:
    """Balanced panel with enough clusters and variation for size/power checks."""
    rng = np.random.default_rng(seed)
    codes = [f"C{c:02d}" for c in range(n_countries)]
    frame = pd.DataFrame([(c, 2000 + t) for c in codes for t in range(n_years)], columns=["eurostat_code", "year"])
    n = len(frame)
    frame["olddep1_lag"] = 20 + 0.3 * (frame["year"] - 2000) + 3 * rng.standard_normal(n) + frame["eurostat_code"].str[1:].astype(int) % 7
    for name, prob in (("W_S", 0.3), ("W_E", 0.2), ("W_U", 0.1)):
        frame[name] = rng.uniform(0, 1, n) * (rng.random(n) < prob)
    frame["W_D"] = 0.0
    frame["Post"] = rng.uniform(0, 1, n)
    frame["capb"] = 0.0
    return frame


# ---------------------------------------------------------------------------------------------
# FWL / CR1 versus a direct OLS
# ---------------------------------------------------------------------------------------------
def test_fwl_and_cr1_equal_direct_ols_with_dummies():
    frame = synthetic_frame()
    design = power.build_design(frame)
    rng = np.random.default_rng(10)
    y = rng.standard_normal(design.n_obs) + 0.5 * design.x[:, 0]
    result = power.estimate(design, y)
    country = pd.get_dummies(pd.Series(design.codes), dtype=float).to_numpy()
    year = pd.get_dummies(pd.Series(design.year), dtype=float).to_numpy()[:, 1:]
    full = np.column_stack([country, year, design.x])
    fit = sm.OLS(y, full).fit(cov_type="cluster", cov_kwds={"groups": design.country_idx, "use_correction": True})
    g, n = design.n_clusters, design.n_obs
    statsmodels_c = g / (g - 1) * (n - 1) / (n - np.linalg.matrix_rank(full))
    for target, column in design.targets.items():
        position = country.shape[1] + year.shape[1] + design.x_names.index(column)
        b, se = result[target]
        assert b[0] == pytest.approx(fit.params[position], abs=1e-9)
        assert se[0] ** 2 == pytest.approx(fit.bse[position] ** 2 * design.cr1 / statsmodels_c, rel=1e-9)


def test_wild_bootstrap_matches_brute_force():
    frame = synthetic_frame()
    design = power.build_design(frame)
    rng = np.random.default_rng(11)
    y_noise = rng.standard_normal((design.n_obs, 3))
    data = power.wcb_prepare(design, y_noise)
    country = pd.get_dummies(pd.Series(design.codes), dtype=float).to_numpy()
    year = pd.get_dummies(pd.Series(design.year), dtype=float).to_numpy()[:, 1:]
    z_full = np.column_stack([country, year, design.x])
    target = "gamma_W"
    col = country.shape[1] + year.shape[1] + design.x_names.index(design.targets[target])
    x_j = design.x[:, design.x_names.index(design.targets[target])]

    def ols(z: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        theta = np.linalg.lstsq(z, y, rcond=None)[0]
        return theta, y - z @ theta

    def se_of(z: np.ndarray, u: np.ndarray) -> float:
        bread = np.linalg.inv(z.T @ z)
        meat = sum(np.outer(z[design.country_idx == g].T @ u[design.country_idx == g], z[design.country_idx == g].T @ u[design.country_idx == g]) for g in range(design.n_clusters))
        return float(np.sqrt((bread @ meat @ bread * design.cr1)[col, col]))

    beta, n_boot = 0.4, 6
    for r in range(3):
        y = y_noise[:, r] + beta * x_j
        _, restricted_resid = ols(np.delete(z_full, col, axis=1), y)
        fit = y - restricted_resid
        v = power.bootstrap_weights(power.make_rng(5, r), (design.n_clusters, n_boot), "rademacher")
        brute = []
        for b in range(n_boot):
            y_star = fit + v[design.country_idx, b] * restricted_resid
            theta, u_star = ols(z_full, y_star)
            brute.append(theta[col] / se_of(z_full, u_star))
        d = data[target]
        b_hat = d.b0[r] + beta
        alpha = d.alpha_u[r] + b_hat * d.alpha_r
        s = d.s_u[r] + b_hat * d.s_r
        a_mat = np.diag(alpha) - design.gamma[target] @ s.T
        fast = (alpha @ v) / np.sqrt(design.cr1 * ((a_mat @ v) ** 2).sum(axis=0))
        assert np.allclose(brute, fast, atol=1e-9)


# ---------------------------------------------------------------------------------------------
# Effect recovery, size and power
# ---------------------------------------------------------------------------------------------
def test_known_effect_is_recovered_and_power_matches_theory():
    design = power.build_design(larger_frame())
    rng = np.random.default_rng(12)
    true_effect, n_draws = 0.8, 4000
    column = design.x[:, design.x_names.index("W_S")]
    y = rng.standard_normal((design.n_obs, n_draws)) + true_effect * column[:, None]
    b, se = power.estimate(design, y, ["beta_S"])["beta_S"]
    assert b.mean() == pytest.approx(true_effect, abs=4 * b.std() / np.sqrt(n_draws))
    # the CR1 standard error does not depend on the true effect
    _, se_null = power.estimate(design, rng.standard_normal((design.n_obs, 50)), ["beta_S"])["beta_S"]
    assert np.median(se_null) == pytest.approx(np.median(se), rel=0.08)


def test_null_rejection_is_close_to_five_percent():
    design = power.build_design(larger_frame(n_countries=40, n_years=15))
    rng = np.random.default_rng(13)
    y = rng.standard_normal((design.n_obs, 6000))
    for target, (b, se) in power.estimate(design, y).items():
        rate = np.mean(np.abs(b / se) > design.t_crit)
        upper = 0.09 if target == "gamma_B" else 0.065  # the between interaction is a cluster-level moderator: CR1 over-rejects mildly
        assert 0.035 < rate < upper, (target, rate)


def test_solve_mde_gives_eighty_percent_power_and_matches_theory():
    rng = np.random.default_rng(14)
    n = 200_000
    se = np.full(n, 0.25)
    b0 = rng.normal(0.0, 0.25, n)
    crit = 2.0
    mde = power.solve_mde(b0, se, crit)
    assert power.power_at(b0, se, crit, mde) == pytest.approx(0.80, abs=0.003)
    assert mde == pytest.approx(0.25 * (crit + 0.8416), rel=0.02)  # (t + z_0.8) * se


def test_wild_bootstrap_null_rejection_and_mde_monotone():
    design = power.build_design(larger_frame(n_countries=30, n_years=12))
    noise = power.ArNoise(design, np.ones(design.n_clusters), 0.3)
    data = power.wcb_prepare(design, noise.draw(power.make_rng(21), 500))["beta_S"]
    rate = power.wild_bootstrap_reject(design, "beta_S", data, 0.0, "rademacher", 1, n_draws=199).mean()
    assert 0.02 < rate < 0.09
    low = power.wild_bootstrap_reject(design, "beta_S", data, 0.3, "rademacher", 1, n_draws=199).mean()
    high = power.wild_bootstrap_reject(design, "beta_S", data, 1.2, "rademacher", 1, n_draws=199).mean()
    assert high > low


# ---------------------------------------------------------------------------------------------
# Noise generators and seeds
# ---------------------------------------------------------------------------------------------
def test_seeds_reproduce_and_streams_are_independent():
    design = power.build_design(synthetic_frame())
    noise = power.ArNoise(design, np.ones(design.n_clusters), 0.5)
    a, b = noise.draw(power.make_rng(1, 2), 5), noise.draw(power.make_rng(1, 2), 5)
    c = noise.draw(power.make_rng(1, 3), 5)
    assert np.array_equal(a, b)
    assert not np.allclose(a, c)
    assert power.make_rng().integers(0, 10**9) == np.random.default_rng(np.random.SeedSequence([42])).integers(0, 10**9)


def test_ar1_noise_has_requested_variance_and_autocorrelation():
    design = power.build_design(larger_frame(n_countries=30, n_years=40))
    sigma = np.linspace(1.0, 3.0, design.n_clusters)
    noise = power.ArNoise(design, sigma, 0.6).draw(power.make_rng(2), 400)
    sd = np.sqrt(np.add.reduceat(noise**2, design.starts, axis=0).sum(axis=1) / (design.counts * 400))
    assert np.allclose(sd, sigma, rtol=0.1)
    lagged, current = noise[design.lag_rows] / sigma[design.country_idx[design.lag_rows], None], noise[design.cur_rows] / sigma[design.country_idx[design.cur_rows], None]
    assert (lagged * current).mean() == pytest.approx(0.6, abs=0.03)


def test_block_bootstrap_keeps_each_years_cross_section_together():
    design = power.build_design(larger_frame(n_countries=5, n_years=12))
    grid = np.add.outer(np.arange(design.n_grid_years) * 100.0, np.arange(design.n_clusters))  # value encodes (year, country)
    draws = power.BlockBootstrapNoise(design, grid, 3).draw(power.make_rng(3), 20)
    source_year = np.floor(draws / 100).astype(int)
    for col in range(20):
        by_year = pd.DataFrame({"year": design.year_pos, "src": source_year[:, col]}).groupby("year")["src"].nunique()
        assert (by_year == 1).all()  # every country in a simulated year comes from one drawn year
        sources = pd.Series(source_year[:, col]).groupby(design.year_pos).first().to_numpy()
        # blocks of 3 consecutive source years, apart from the final truncation
        assert (np.diff(sources[:3]) == 1).all()


def test_pooled_ar1_estimator_and_nickell_correction():
    design = power.build_design(larger_frame(n_countries=30, n_years=27))
    noise = power.ArNoise(design, np.ones(design.n_clusters), 0.6).draw(power.make_rng(4), 300)
    estimated = power._pair_ar1(power.residuals(design, noise), design).mean()
    assert estimated < 0.6  # demeaning biases the AR(1) coefficient downward
    assert power.nickell_bias(0.6, 27) < 0 and power.nickell_bias(0.6, 27) == pytest.approx(-(1.6) / 26, rel=0.2)
    assert power.nickell_corrected_rho(0.5, 27) > 0.5
    assert power.nickell_corrected_rho(0.6 + power.nickell_bias(0.6, 27), 27) == pytest.approx(0.6, abs=1e-6)


# ---------------------------------------------------------------------------------------------
# Real final sample
# ---------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def final_design() -> power.Design:
    panel = sample.build_panel()
    final = sample.select_sample(panel, sample.last_common_complete_year(panel, "cv"), "joint_cv").sample
    return power.build_design(final)


@needs_inputs
def test_final_sample_design_shape(final_design):
    assert (final_design.n_obs, final_design.n_clusters) == (715, 27)
    assert "W_D" not in final_design.x_names  # no delayed election in the final sample: dropped, not estimated
    assert {"W_S", "W_E", "W_U", "Post", "WS_x_between", "WS_x_within", "A_lag"} <= set(final_design.x_names)
    assert final_design.t_crit == pytest.approx(2.0555, abs=1e-3)


@needs_inputs
def test_calibration_runs_and_is_plausible(final_design):
    cal = power.calibrate(final_design)
    assert 0.3 < cal.rho_raw_standardised < cal.rho_corrected < 0.95
    assert cal.sigma.min() > 0.5 and cal.heterogeneity["sigma_argmax_country"] == "IE"
    assert np.isfinite(cal.grid[final_design.year_pos, final_design.country_idx]).all()


# ---------------------------------------------------------------------------------------------
# Block length rule, gate verdicts, tables, design variants
# ---------------------------------------------------------------------------------------------
def test_block_length_rule_is_bounded_and_reproducible():
    design = power.build_design(larger_frame(n_countries=10, n_years=20))
    resid = power.residuals(design, np.random.default_rng(5).standard_normal(design.n_obs))
    cal = power.Calibration(
        resid=resid, sigma=np.ones(design.n_clusters), df_factor=1.0, grid=power.residual_grid(design, resid), rho_raw_pooled=0.0,
        rho_raw_standardised=0.0, rho_nickell_corrected=0.0, rho_corrected=0.0, mean_t=20.0, heterogeneity={}, dependence={}, winsorised=False,
    )
    block = power.choose_block_length(design, cal)
    assert power.MIN_BLOCK <= block <= design.n_grid_years // 2
    assert block == power.choose_block_length(design, cal)


def test_gate_verdicts_follow_appendix_d_thresholds():
    assert power.gate_verdict("beta_S", 0.45, 0.70) == "GO"
    assert power.gate_verdict("beta_S", 0.55, 0.70) == "AMBER"
    assert power.gate_verdict("beta_S", 0.45, 1.01) == "NO-GO"
    assert power.gate_verdict("gamma_B", 0.74, 0.74) == "GO"
    assert power.gate_verdict("gamma_W", 0.80, 0.90) == "AMBER"
    assert power.gate_verdict("gamma_W", 0.80, 1.20) == "NO-GO"


def test_md_table_formats_floats_and_text():
    table = power.md_table(pd.DataFrame({"a": [1.23456], "b": ["x"]}), ".2f")
    assert table.splitlines()[0] == "| a | b |" and "1.23" in table.splitlines()[2]


def test_pooled_and_period_specs_have_expected_columns():
    frame = larger_frame()
    pooled = power.build_design(frame, "pooled")
    assert "WS_x_A" in pooled.x_names and set(pooled.targets) == {"beta_S", "gamma_pooled"}
    period = power.build_design(frame, "m1_period")
    assert "WS_x_2008_2019" in period.x_names and "WS_x_2020_on" not in period.x_names  # no 2020+ rows here: constant column dropped
    with pytest.raises(ValueError):
        power.regressors_from_frame(frame, "unknown")


def test_scaled_interactions_have_unit_sd():
    frame = larger_frame()
    regs, scale, _ = power.regressors_from_frame(frame, "m1")
    w_s = frame["W_S"].to_numpy()
    a = frame["olddep1_lag"].to_numpy()
    z = (a - a.mean()) / a.std()
    abar = pd.Series(z).groupby(frame["eurostat_code"].to_numpy()).transform("mean").to_numpy()
    assert regs["WS_x_between"].to_numpy() == pytest.approx(w_s * abar / abar.std())
    assert regs["WS_x_within"].to_numpy() == pytest.approx(w_s * (z - abar) / (z - abar).std())
    assert scale["sd_between_z"] == pytest.approx(abar.std())


def test_placeholder_rule_moderator_has_audited_two_way_sd():
    frame = larger_frame(n_countries=27, n_years=6)
    frame["year"] = frame["year"] + 16  # 2016-2021
    moderator, two_way_sd = power.placeholder_rule_moderator(frame, power.make_rng(7))
    assert two_way_sd == pytest.approx(power.RULE_TWO_WAY_SD_Z, abs=0.02)
    assert len(moderator) == len(frame)


def test_centred_period_terms_have_zero_mean_dummies():
    frame = larger_frame()
    frame["year"] = frame["year"] + 5  # 2005-2016 so that the middle period is non-degenerate
    regs, _, _ = power.regressors_from_frame(frame, "m1_period_centered")
    raw, _, _ = power.regressors_from_frame(frame, "m1_period")
    w_s = frame["W_S"].to_numpy()
    middle = ((frame["year"] >= 2008) & (frame["year"] <= 2019)).to_numpy(float)
    assert regs["WS_x_2008_2019"].to_numpy() == pytest.approx(w_s * (middle - middle.mean()))
    assert raw["WS_x_2008_2019"].to_numpy() == pytest.approx(w_s * middle)
