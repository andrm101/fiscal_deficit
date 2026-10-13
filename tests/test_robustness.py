"""Offline tests for the robustness suite (``src/models/py/robustness.py``, specification ``docs/robustness_spec.md``).

Every estimator test uses a SYNTHETIC outcome with a known effect or a simulated panel with a known answer. The real outcome is not read
by any test here (the real-panel run is done by the module's ``main``); the only real-data inputs are the interim election calendar and the
non-outcome columns of the gold panel, which the section C/D rebuild tests need.
"""
from __future__ import annotations

import hashlib
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
import power  # noqa: E402
import power_variants as pv  # noqa: E402
import robustness as rb  # noqa: E402

MANIFEST = ROOT / "docs" / "freeze_manifest.json"
FROZEN_PREFIXES = ("src/", "config/")
FROZEN_FILES = ("docs/preregistration.md", "scripts/freeze.py", "requirements.lock")


# ---------------------------------------------------------------------------------------------
# Frozen files
# ---------------------------------------------------------------------------------------------
def test_frozen_files_are_byte_identical_to_the_freeze_manifest():
    """LF-normalised SHA-256 of every frozen file under src/, config/, docs/preregistration.md, scripts/freeze.py and requirements.lock."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
    frozen = sorted(k for k in manifest if k.startswith(FROZEN_PREFIXES) or k in FROZEN_FILES)
    assert len(frozen) >= 20 and "src/models/py/m1.py" in frozen and "requirements.lock" in frozen
    mismatches = []
    for rel in frozen:
        data = (ROOT / rel).read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        if hashlib.sha256(data).hexdigest() != manifest[rel]["sha256"]:
            mismatches.append(rel)
    assert not mismatches, f"frozen files changed: {mismatches}"


# ---------------------------------------------------------------------------------------------
# Synthetic panels
# ---------------------------------------------------------------------------------------------
def synthetic_frame(seed: int = 3, n_countries: int = 27, first: int = 1995, last: int = 2021, balanced: bool = False) -> pd.DataFrame:
    """Panel with the columns of the confirmatory extract (no real data): exposure, moderator, an outcome set to zero."""
    rng = np.random.default_rng(seed)
    rows = [(f"C{c:02d}", y) for c in range(n_countries) for y in range(first, last + 1)]
    frame = pd.DataFrame(rows, columns=["eurostat_code", "year"])
    if not balanced:  # series starts for a few countries (contiguous spans, as in the real panel)
        late = {"C03": 2, "C07": 4, "C11": 6}
        frame = frame[[not (c in late and y < first + late[c]) for c, y in zip(frame["eurostat_code"], frame["year"])]].reset_index(drop=True)
    n = len(frame)
    country = frame["eurostat_code"].str[1:].astype(int).to_numpy()
    frame["olddep1_lag"] = 18 + 0.2 * (frame["year"] - first) + 2.0 * rng.standard_normal(n) + country % 9
    for name, prob in (("W_S", 0.3), ("W_E", 0.15), ("W_U", 0.1)):
        frame[name] = rng.uniform(0, 1, n) * (rng.random(n) < prob)
    frame["W_D"] = 0.0
    frame["Post"] = rng.uniform(0, 1, n) * (rng.random(n) < 0.3)
    frame["capb"] = 0.0
    return frame


def simulate_outcome(design: power.Design, beta_s: float = -1.0, gamma_b: float = 0.8, rho: float = 0.4, seed: int = 5, factor: bool = False) -> np.ndarray:
    """Outcome = known M1 effects + country/year effects + AR(1) noise (+ optionally a heterogeneous common factor)."""
    rng = np.random.default_rng(seed)
    d = design
    b = np.zeros(d.x.shape[1])
    b[d.x_names.index("W_S")] = beta_s
    b[d.x_names.index("WS_x_between")] = gamma_b
    noise = power.ArNoise(d, np.full(d.n_clusters, 1.0), rho).draw(rng, 1)[:, 0]
    country_fe = rng.standard_normal(d.n_clusters)[d.country_idx]
    year_fe = rng.standard_normal(d.n_grid_years)[d.year_pos]
    y = d.x @ b + country_fe + year_fe + noise
    if factor:
        f = rng.standard_normal(d.n_grid_years)
        lam = 1.0 + rng.standard_normal(d.n_clusters)
        y = y + lam[d.country_idx] * f[d.year_pos]
    return y


@pytest.fixture(scope="module")
def frame_unbalanced() -> pd.DataFrame:
    return synthetic_frame()


@pytest.fixture(scope="module")
def design_unbalanced(frame_unbalanced) -> power.Design:
    return rb.m1_design(frame_unbalanced)


# ---------------------------------------------------------------------------------------------
# A. OLS algebra, Driscoll-Kraay, two-way clustering
# ---------------------------------------------------------------------------------------------
def with_outcome(frame: pd.DataFrame, **kwargs) -> pd.DataFrame:
    design = rb.m1_design(frame)
    y = simulate_outcome(design, **kwargs)
    out = rb.sorted_frame(frame).copy()
    out["capb"] = y
    return out


def test_fe_ols_matches_the_engine_and_cr1(frame_unbalanced):
    frame = with_outcome(frame_unbalanced)
    design = rb.m1_design(frame)
    fe = rb.FeOls(design)
    ref = power.estimate(design, design.y)
    for t in rb.TARGETS:
        assert fe.beta[fe.index(t)] == pytest.approx(ref[t][0][0], abs=1e-10)
        assert np.sqrt(fe.cr1()[fe.index(t), fe.index(t)]) == pytest.approx(ref[t][1][0], rel=1e-9)


@pytest.mark.parametrize("balanced", [True, False])
@pytest.mark.parametrize("bandwidth", [0, 2, 4])
def test_driscoll_kraay_equals_linearmodels(balanced, bandwidth):
    """Numpy Driscoll-Kraay (Bartlett) against linearmodels.PanelOLS(entity_effects, time_effects).fit(cov_type='kernel'), synthetic data."""
    frame = with_outcome(synthetic_frame(seed=8, n_countries=15, balanced=balanced), seed=9)
    design = rb.m1_design(frame)
    out = rb.dk_crosscheck(design, (bandwidth,))
    assert out["bandwidths"][str(bandwidth)]["max_rel_diff_se"] < 1e-9
    assert out["max_rel_diff_coefficients"] < 1e-9


def test_driscoll_kraay_bandwidth_zero_is_year_clustering(design_unbalanced):
    """With m = 0 the Driscoll-Kraay score sum is the year-cluster sandwich, computed here independently with loops."""
    design = design_unbalanced
    design = rb.m1_design(with_outcome(synthetic_frame(), seed=2))
    fe = rb.FeOls(design)
    omega = np.zeros((fe.xt.shape[1],) * 2)
    for yr in np.unique(design.year):
        s = (fe.xt[design.year == yr] * fe.resid[design.year == yr, None]).sum(axis=0)
        omega += np.outer(s, s)
    assert np.allclose(fe.driscoll_kraay(0, small_sample=False), fe.xtx_inv @ omega @ fe.xtx_inv, rtol=1e-10, atol=1e-12)


def test_two_way_clustering_matches_statsmodels_without_small_sample_factors():
    import statsmodels.api as sm
    from statsmodels.stats.sandwich_covariance import cov_cluster_2groups

    design = rb.m1_design(with_outcome(synthetic_frame(seed=4, n_countries=12), seed=6))
    fe = rb.FeOls(design)
    y_tilde = design.y - design.q_fe @ (design.q_fe.T @ design.y)  # outcome with the fixed effects partialled out (Frisch-Waugh-Lovell)
    res = sm.OLS(y_tilde, fe.xt).fit()
    expected, _, _ = cov_cluster_2groups(res, design.country_idx, design.year, use_correction=False)
    cov, _ = fe.two_way(small_sample=False, psd_fix=False)
    assert np.allclose(cov, expected, rtol=1e-8, atol=1e-12)


def test_two_way_eigenvalue_fix_makes_the_matrix_psd():
    """Force a non-PSD middle matrix (a tiny panel with few years) and check the repaired covariance is PSD with unchanged positive part."""
    for seed in range(40):
        design = rb.m1_design(with_outcome(synthetic_frame(seed=seed, n_countries=20, first=2000, last=2007, balanced=True), seed=seed))
        cov, info = rb.FeOls(design).two_way()
        assert np.linalg.eigvalsh((cov + cov.T) / 2).min() > -1e-10
        if info["psd_fix_applied"]:
            assert info["min_eigenvalue_of_V"] < 0 and info["n_negative_eigenvalues"] >= 1
            return
    pytest.skip("no draw produced a non-PSD two-way covariance")


def test_ols_recovers_known_effects_and_inference_is_finite():
    frame = with_outcome(synthetic_frame(seed=21), beta_s=-1.0, gamma_b=0.8, rho=0.3, seed=22)
    design = rb.m1_design(frame)
    fe = rb.FeOls(design)
    assert abs(fe.beta[fe.index("beta_S")] + 1.0) < 0.35 and abs(fe.beta[fe.index("gamma_B")] - 0.8) < 0.35
    for cov in (fe.cr1(), fe.driscoll_kraay(2), fe.driscoll_kraay(4), fe.two_way()[0]):
        assert np.all(np.isfinite(cov)) and np.all(np.diag(cov) > 0)


# ---------------------------------------------------------------------------------------------
# A. CCE
# ---------------------------------------------------------------------------------------------
def test_cce_columns_and_dimensions():
    frame = with_outcome(synthetic_frame(seed=31))
    design_lite, rep_lite = rb.cce_design(frame, "lite")
    design_full, rep_full = rb.cce_design(frame, "full")
    g = 27
    assert rep_lite["added_parameters"] == 2 * (g - 1) and rep_lite["n_csa_variables"] == 2
    assert rep_full["added_parameters"] == rep_full["n_csa_variables"] * (g - 1)
    assert rep_lite["residual_df"] == design_lite.n_obs - rep_lite["n_parameters_total"]
    assert not rep_lite["df_exhausted"]
    base = rb.m1_design(frame)
    assert design_lite.x.shape[1] == base.x.shape[1] + rep_lite["added_parameters"]
    # the CSA of capb is the year mean over the countries present
    sub = rb.sorted_frame(frame)
    csa = sub.groupby("year")["capb"].transform("mean").to_numpy()
    col = design_lite.x[:, design_lite.x_names.index("CSA[capb]xC00")]
    assert np.allclose(col, np.where(design_lite.codes == "C00", csa, 0.0))
    # headline targets are still the M1 targets
    assert set(design_lite.targets) == {"beta_S", "gamma_B", "gamma_W"}


def test_cce_recovers_the_effect_under_a_heterogeneous_common_factor_where_ols_is_biased():
    """The exposure carries the same latent factor as the outcome (country-specific loadings): CCE removes the bias that year effects cannot."""
    rng = np.random.default_rng(77)
    frame = synthetic_frame(seed=40, balanced=True)
    design = rb.m1_design(frame)
    d = design
    f = rng.standard_normal(d.n_grid_years)
    load_y = 1.0 + rng.standard_normal(d.n_clusters)
    load_x = 1.0 + rng.standard_normal(d.n_clusters)
    w_s = np.clip(0.3 + 0.25 * load_x[d.country_idx] * f[d.year_pos] + 0.1 * rng.standard_normal(d.n_obs), 0.0, 1.0)
    frame = rb.sorted_frame(frame)
    frame["W_S"] = w_s
    d = rb.m1_design(frame)
    f_year = f[d.year_pos]
    noise = 0.5 * rng.standard_normal(d.n_obs)
    b = np.zeros(d.x.shape[1])
    b[d.x_names.index("W_S")] = -1.0
    frame["capb"] = d.x @ b + load_y[d.country_idx] * f_year * 2.0 + noise
    ols = rb.FeOls(rb.m1_design(frame))
    cce_design, _ = rb.cce_design(frame, "lite")
    cce = rb.FeOls(cce_design)
    err_ols = abs(ols.beta[ols.index("beta_S")] + 1.0)
    err_cce = abs(cce.beta[cce.index("beta_S")] + 1.0)
    assert err_cce < err_ols / 3 and err_cce < 0.5


# ---------------------------------------------------------------------------------------------
# A. Pesaran CD
# ---------------------------------------------------------------------------------------------
def test_pesaran_cd_vectorised_equals_the_loop_and_the_project_function():
    rng = np.random.default_rng(1)
    grid = rng.standard_normal((27, 20))
    grid[:5, 3] = np.nan
    grid[:9, 7] = np.nan
    a = rb.pesaran_cd(grid)
    b = rb._pesaran_cd_loop(grid)
    assert a["cd"] == pytest.approx(b["cd"], rel=1e-10) and a["mean_abs_corr"] == pytest.approx(b["mean_abs_corr"], rel=1e-10)
    assert a["n_pairs"] == b["n_pairs"]
    dense = rng.standard_normal((30, 12))
    ref = power.cross_section_dependence(dense)
    assert rb.pesaran_cd(dense)["cd"] == pytest.approx(ref["pesaran_cd"], rel=1e-10)


def test_pesaran_cd_near_zero_under_independence_and_large_under_a_common_factor():
    rng = np.random.default_rng(2)
    values = []
    for _ in range(40):
        values.append(rb.pesaran_cd(rng.standard_normal((40, 20)))["cd"])
    assert abs(np.mean(values)) < 0.5 and 0.6 < np.std(values) < 1.5  # N(0, 1)
    factor = rng.standard_normal((40, 1))
    loadings = 1.0 + 0.3 * rng.standard_normal((1, 20))
    common = factor @ loadings + rng.standard_normal((40, 20))
    assert rb.pesaran_cd(common)["cd"] > 10.0


def test_cd_null_reflects_the_mechanical_negative_shift_of_year_demeaning(design_unbalanced):
    null = rb.cd_null(design_unbalanced, n_sim=30)
    assert null["cd_mean"] < -3.0
    noise = np.random.default_rng(4).standard_normal(design_unbalanced.n_obs)
    out = rb.pesaran_cd(power.residual_grid(design_unbalanced, power.residuals(design_unbalanced, noise)))
    assert out["mean_corr"] == pytest.approx(-1 / (design_unbalanced.n_clusters - 1), abs=0.01)


# ---------------------------------------------------------------------------------------------
# A. Row construction (synthetic, small B)
# ---------------------------------------------------------------------------------------------
HEADLINE_STUB = {"targets": {"beta_S": {"estimate": -0.3794}, "gamma_B": {"estimate": 0.2066}, "gamma_W": {"estimate": -0.2708}}}


def test_bootstrap_block_reproduces_the_headline_procedure_on_synthetic_data():
    """The generic block gives the same numbers as m1.run_m1 (V7, same seed key and B) on a synthetic outcome."""
    frame = with_outcome(synthetic_frame(seed=51), seed=52)
    ref = m1.run_m1(frame, n_boot=39, sesoi=m1.Interpretation(0.5, "TEST"))
    est = rb.v7_estimator(rb.m1_design(frame))
    block = rb.bootstrap_block(est, 39)
    for t in rb.TARGETS:
        assert block["targets"][t]["estimate"] == pytest.approx(ref.targets[t].estimate, abs=1e-10)
        assert block["targets"][t]["boot_lo"] == pytest.approx(ref.targets[t].ci_lo, abs=1e-10)
        assert block["targets"][t]["boot_hi"] == pytest.approx(ref.targets[t].ci_hi, abs=1e-10)
    for t in rb.TESTED:
        assert block["targets"][t]["p_boot"] == pytest.approx(ref.targets[t].p_bootstrap, abs=1e-12)


def test_rows_carry_reading_sign_and_flags():
    frame = with_outcome(synthetic_frame(seed=61), beta_s=-1.0, seed=62)
    design = rb.m1_design(frame)
    block = rb.bootstrap_block(rb.ols_estimator(design), 39)
    rows = rb.rows_from_block(block, HEADLINE_STUB, 0.5, spec_id="T", group="A", label="t", estimator="OLS", design=design)
    assert [r["id"] for r in rows] == ["T|cr1", "T|wcb"]
    for r in rows:
        bs = r["targets"]["beta_S"]
        assert bs["same_sign_as_headline"] is True and bs["reading"] in (m1.LABEL_EXCLUDES, m1.LABEL_EQUIVALENT, m1.LABEL_INCONCLUSIVE)
        assert r["targets"]["gamma_W"]["reading"] is None and r["targets"]["gamma_W"]["p"] is None  # descriptive target: no test, no reading
    assert rows[0]["targets"]["beta_S"]["p"] is not None


def test_failed_rows_are_reported_not_dropped():
    row = rb.failed_row("X", "A", "label", "est", "inf", ValueError("singular"))
    assert row["status"] == "failed" and "singular" in row["error"]
    summary = rb.summarise({"sections": {"A": {"rows": [row]}}})
    assert summary["A"]["n_specifications"] == 1 and summary["A"]["n_failed"] == 1 and summary["A"]["beta_S"]["n"] == 0


# ---------------------------------------------------------------------------------------------
# B. Diagnostics with a known answer
# ---------------------------------------------------------------------------------------------
def with_y(frame: pd.DataFrame, y: np.ndarray) -> pd.DataFrame:
    out = rb.sorted_frame(frame).copy()
    out["capb"] = y
    return out


def panel_starts(n_units: int, t_obs: int) -> tuple[np.ndarray, np.ndarray]:
    return np.arange(n_units) * t_obs, np.full(n_units, t_obs)


def test_modified_wald_rejects_groupwise_heteroskedasticity_and_not_homoskedasticity():
    starts, counts = panel_starts(20, 200)
    rejections = 0
    for seed in range(30):
        e = np.random.default_rng(seed).standard_normal(20 * 200)
        rejections += rb.modified_wald(e, starts, counts)["p_value"] < 0.05
    assert rejections <= 6  # nominal 5% of 30 draws is 1.5; the statistic over-rejects when T is small (see modified_wald_mc)
    starts, counts = panel_starts(20, 40)
    sd = np.repeat(np.linspace(0.4, 3.0, 20), 40)
    hetero = rb.modified_wald(np.random.default_rng(1).standard_normal(20 * 40) * sd, starts, counts)
    assert hetero["p_value"] < 1e-8 and hetero["df"] == 20


def test_modified_wald_matches_a_loop_implementation():
    starts, counts = np.array([0, 5, 12]), np.array([5, 7, 6])
    e = np.random.default_rng(3).standard_normal(18)
    s2 = np.mean(e**2)
    w = 0.0
    for a, c in zip(starts, counts):
        x = e[a:a + c] ** 2
        s_i = x.mean()
        v_i = ((x - s_i) ** 2).sum() / (c * (c - 1))
        w += (s_i - s2) ** 2 / v_i
    assert rb.modified_wald(e, starts, counts)["statistic"] == pytest.approx(w, rel=1e-12)


def test_wooldridge_detects_ar1_errors_and_not_independent_errors():
    frame = synthetic_frame(seed=71, balanced=True)
    design = rb.m1_design(frame)
    b = np.zeros(design.x.shape[1])
    iid, ar = [], []
    for seed in range(8):
        rng = np.random.default_rng(seed)
        fe = rng.standard_normal(design.n_clusters)[design.country_idx]
        e_iid = rng.standard_normal(design.n_obs)
        e_ar = power.ArNoise(design, np.ones(design.n_clusters), 0.6).draw(rng, 1)[:, 0]
        iid.append(rb.wooldridge_serial(design, design.x @ b + fe + e_iid))
        ar.append(rb.wooldridge_serial(design, design.x @ b + fe + e_ar))
    assert np.mean([r["coefficient"] for r in iid]) == pytest.approx(-0.5, abs=0.06)
    assert sum(r["p_value"] < 0.05 for r in iid) <= 2
    assert all(r["p_value"] < 0.01 for r in ar) and np.mean([r["coefficient"] for r in ar]) > -0.35


def cips_panel(kind: str, seed: int, n: int = 20, t: int = 30) -> np.ndarray:
    rng = np.random.default_rng(seed)
    f = rng.standard_normal((t, 1))
    load = 1.0 + 0.3 * rng.standard_normal((1, n))
    shocks = f @ load + rng.standard_normal((t, n))
    if kind == "random_walk":
        return np.cumsum(shocks, axis=0)
    out = np.zeros((t, n))
    for i in range(1, t):
        out[i] = 0.5 * out[i - 1] + shocks[i]
    return out


@pytest.mark.parametrize("trend", [False, True])
def test_cips_rejects_a_stationary_panel_and_not_a_random_walk_panel(trend):
    reject_stationary = [rb.cips_test(cips_panel("stationary", s), 1, trend, n_sim=150, seed=s)["reject_5pct"] for s in range(5)]
    reject_walk = [rb.cips_test(cips_panel("random_walk", s), 1, trend, n_sim=150, seed=s)["reject_5pct"] for s in range(5)]
    assert all(reject_stationary)
    assert sum(reject_walk) <= 1


def test_cips_handles_unbalanced_contiguous_spans_and_rejects_noncontiguous():
    grid = cips_panel("stationary", 5)
    grid[:6, 2] = np.nan
    assert np.isfinite(rb.cips_statistic(grid, 1, False)["cips"])
    grid[10, 4] = np.nan
    with pytest.raises(ValueError):
        rb.cips_statistic(grid, 1, False)


def test_vif_matches_the_regression_definition(design_unbalanced):
    out = rb.vif_table(design_unbalanced)
    fe = rb.FeOls(design_unbalanced)
    j = design_unbalanced.x_names.index("WS_x_between")
    others = np.delete(fe.xt, j, axis=1)
    coef, *_ = np.linalg.lstsq(others, fe.xt[:, j], rcond=None)
    r2 = 1 - ((fe.xt[:, j] - others @ coef) ** 2).sum() / (fe.xt[:, j] ** 2).sum()
    assert out["vif_within"][j] == pytest.approx(1 / (1 - r2), rel=1e-9)
    assert all(v >= 1 - 1e-9 for v in out["vif_within"] + out["vif_raw"])


def test_mundlak_hausman_rejects_correlated_effects_and_not_uncorrelated_effects():
    base = synthetic_frame(seed=81, balanced=True)
    d = rb.m1_design(base)
    post = d.x[:, d.x_names.index("Post")]
    post_mean = (np.bincount(d.country_idx, weights=post) / d.counts)[d.country_idx]
    rng = np.random.default_rng(9)
    noise = rng.standard_normal(d.n_obs)
    random_effect = rng.standard_normal(d.n_clusters)[d.country_idx]
    ok = rb.mundlak_hausman(rb.m1_design(with_y(base, random_effect + noise)))
    bad = rb.mundlak_hausman(rb.m1_design(with_y(base, 40.0 * post_mean + noise)))
    assert bad["p_value_f"] < 0.01 < ok["p_value_f"]
    assert ok["q"] >= 6


def test_classical_hausman_runs_and_is_larger_when_effects_are_correlated_with_regressors():
    base = synthetic_frame(seed=91, balanced=True)
    d = rb.m1_design(base)
    post = d.x[:, d.x_names.index("Post")]
    post_mean = (np.bincount(d.country_idx, weights=post) / d.counts)[d.country_idx]
    rng = np.random.default_rng(10)
    noise = rng.standard_normal(d.n_obs)
    ok = rb.classical_hausman(rb.m1_design(with_y(base, rng.standard_normal(d.n_clusters)[d.country_idx] + noise)))
    bad = rb.classical_hausman(rb.m1_design(with_y(base, 40.0 * post_mean + noise)))
    assert np.isfinite(ok["statistic"]) and ok["df"] >= 1
    # with strongly correlated effects the RE residual variance explodes and V_FE - V_RE loses positive semi-definiteness: the documented failure of the classical test
    assert bad["statistic"] > ok["statistic"] or bad["n_negative_eigenvalues"] > 0


def test_binned_diagnostic_flags_a_nonlinear_interaction_and_not_a_linear_one():
    base = synthetic_frame(seed=101, balanced=True)
    d = rb.m1_design(base)
    rng = np.random.default_rng(11)
    w_s = d.x[:, d.x_names.index("W_S")]
    a = rb.sorted_frame(base)["olddep1_lag"].to_numpy()
    z = (a - a.mean()) / a.std()
    abar = pd.Series(z).groupby(d.codes).transform("mean").to_numpy()
    xb = abar / abar.std()
    noise = 0.3 * rng.standard_normal(d.n_obs)
    linear = w_s * (-1.0 + 0.8 * xb) + noise
    step = w_s * np.where(xb > np.quantile(xb, 2 / 3), -4.0, 0.0) + noise
    out_lin = rb.binned_diagnostic(with_y(base, linear), "between")
    out_step = rb.binned_diagnostic(with_y(base, step), "between")
    assert out_lin["linearity_p"] > 0.05 and out_step["linearity_p"] < 0.01
    assert len(out_lin["bins"]) == 3 and sum(b["n_obs"] for b in out_lin["bins"]) == d.n_obs
    within = rb.binned_diagnostic(with_y(base, linear), "within")
    assert len(within["bins"]) == 3 and np.isfinite(within["linearity_f"])


# ---------------------------------------------------------------------------------------------
# C/D building blocks: the exposure rebuild
# ---------------------------------------------------------------------------------------------
CALENDAR = ROOT / "data" / "interim" / "election_calendar_eu27.csv"
EXPOSURE = ROOT / "data" / "interim" / "exposure_eu27.csv"


@pytest.mark.skipif(not CALENDAR.exists(), reason="interim calendar not available")
def test_rebuild_reproduces_the_frozen_12_month_exposure_columns():
    import elections  # noqa: PLC0415  (frozen module, used read-only as the reference)

    cal = rb.load_calendar()
    frozen = elections.build_exposure(cal)
    new = rb.rebuild_exposure(cal)
    assert (frozen[["eurostat_code", "year"]].to_numpy() == new[["eurostat_code", "year"]].to_numpy()).all()
    for col in ("W_S", "W_E", "W_D", "W_U", "Post"):
        assert np.max(np.abs(frozen[col].to_numpy() - new[col].to_numpy())) < 1e-12, col
    gf_frozen = elections.build_exposure(cal, class_col="class_gapfill", suffix="_gf")
    gf_new = rb.rebuild_exposure(cal, class_col="class_gapfill")
    for col in ("W_S", "W_E", "W_D", "W_U", "Post"):
        assert np.max(np.abs(gf_frozen[f"{col}_gf"].to_numpy() - gf_new[col].to_numpy())) < 1e-12, col
    csv = pd.read_csv(EXPOSURE).merge(new, on=["eurostat_code", "year"], suffixes=("_csv", ""))
    for col in ("W_S", "W_E", "W_D", "W_U", "Post"):
        assert np.max(np.abs(csv[f"{col}_csv"] - csv[col])) < 6e-7, col  # the interim csv stores 6 decimals


def toy_calendar(date: str, cls: str = "scheduled") -> pd.DataFrame:
    return pd.DataFrame({"eurostat_code": ["XX"], "date_used": [pd.Timestamp(date)], "in_calendar": [True], "class_primary": [cls]})


def test_rebuild_windows_have_the_analytic_share_of_year():
    cal = toy_calendar("2000-07-01")
    w6 = rb.rebuild_exposure(cal, pre_months=6, years=range(1998, 2002)).set_index("year")
    assert w6.loc[2000, "W_S"] == pytest.approx(182 / 366) and w6.loc[1999, "W_S"] == 0.0
    w18 = rb.rebuild_exposure(cal, pre_months=18, years=range(1998, 2002)).set_index("year")
    assert w18.loc[1999, "W_S"] == pytest.approx(1.0) and w18.loc[2000, "W_S"] == pytest.approx(182 / 366)
    lead = rb.rebuild_exposure(cal, pre_months=12, lead_offset_months=12, years=range(1997, 2002)).set_index("year")
    assert lead.loc[1998, "W_S"] == pytest.approx(184 / 365) and lead.loc[1999, "W_S"] == pytest.approx(181 / 365) and lead.loc[2000, "W_S"] == 0.0
    assert w6.loc[2000, "Post"] == pytest.approx(184 / 366) and w6.loc[2001, "Post"] == pytest.approx(181 / 365)  # the post window stays 12 months
    early = rb.rebuild_exposure(toy_calendar("2000-07-01", "early"), pre_months=6, years=range(1999, 2002)).set_index("year")
    assert early.loc[2000, "W_E"] > 0 and early.loc[2000, "W_S"] == 0.0
    unclassified = rb.rebuild_exposure(toy_calendar("2000-07-01", "unavailable"), pre_months=6, years=range(1999, 2002)).set_index("year")
    assert unclassified.loc[2000, "W_U"] > 0


def test_election_year_dummies():
    cal = pd.DataFrame({"eurostat_code": ["XX", "XX", "XX"], "date_used": pd.to_datetime(["2000-03-01", "2000-11-01", "2003-05-05"]), "in_calendar": [True] * 3,
                        "class_primary": ["scheduled", "early", "scheduled"]})
    d = rb.election_year_dummies(cal, years=range(1999, 2005)).set_index("year")
    assert list(d["W_S"]) == [0, 1, 0, 0, 1, 0] and list(d["W_E"]) == [0, 1, 0, 0, 0, 0]


def test_modified_wald_monte_carlo_p_value_is_calibrated_and_powerful():
    design = rb.m1_design(synthetic_frame(seed=111, balanced=True))
    rng = np.random.default_rng(12)
    pvals = [rb.modified_wald_mc(power.residuals(design, rng.standard_normal(design.n_obs)), design, n_sim=200, seed=s)["p_value_mc"] for s in range(20)]
    assert np.mean(np.array(pvals) < 0.05) <= 0.25 and min(pvals) > 0.0
    sd = np.linspace(0.4, 3.0, design.n_clusters)[design.country_idx]
    hetero = rb.modified_wald_mc(power.residuals(design, rng.standard_normal(design.n_obs) * sd), design, n_sim=200)
    assert hetero["p_value_mc"] < 0.01


# ---------------------------------------------------------------------------------------------
# C/D: variant rows, summaries, outputs
# ---------------------------------------------------------------------------------------------
def stub_row(spec_id: str, group: str, b_est: float, b_lo: float, b_hi: float, g_est: float = 0.2, g_lo: float = -0.1, g_hi: float = 0.5, status: str = "ok") -> dict:
    if status != "ok":
        return rb.failed_row(spec_id, group, spec_id, "V7", "wcb", RuntimeError("boom"))
    return rb.make_row(spec_id, group, spec_id, "V7", "wcb", 715, 27, {
        "beta_S": rb.target_entry("beta_S", b_est, b_lo, b_hi, 0.03, 0.1, HEADLINE_STUB, 0.5),
        "gamma_B": rb.target_entry("gamma_B", g_est, g_lo, g_hi, 0.2, 0.1, HEADLINE_STUB, 0.5),
        "gamma_W": rb.target_entry("gamma_W", -0.3, -1.0, 0.4, None, 0.3, HEADLINE_STUB, 0.5)})


def stub_results() -> dict:
    head = {"source": "real_gold_panel", "n_obs": 715, "sesoi_pp": 0.5, "registry_hash": "r", "code_hash": "c",
            "targets": {"beta_S": {"estimate": -0.3794, "ci_lo": -0.69, "ci_hi": -0.07, "p_bootstrap": 0.018, "reading": "excludes zero"},
                        "gamma_B": {"estimate": 0.2066, "ci_lo": -0.07, "ci_hi": 0.49, "p_bootstrap": 0.14, "reading": "equivalent within +-sesoi"}, "gamma_W": {"estimate": -0.27}}}
    rows_a = [stub_row("A1", "A", -0.35, -0.7, 0.01), stub_row("A2", "A", 0.1, -0.3, 0.5, g_est=-0.2, g_lo=-0.45, g_hi=0.05), stub_row("A3", "A", 0, 0, 0, status="failed")]
    rows_c = [stub_row("C1", "C", -0.4, -0.8, -0.1), stub_row("C4-loco-AT", "C-LOCO", -0.3, -0.6, 0.0)]
    rows_d = [stub_row("D1", "D", -0.5, -1.2, 0.2)]
    return {"meta": {"sesoi_pp": 0.5, "b_main": 9999, "b_loco": 999}, "headline": head,
            "sections": {"A": {"rows": rows_a, "cce": {}, "dependence": [], "rho_hat": 0.6}, "C": {"rows": rows_c, "notes": {}}, "D": {"rows": rows_d}}}


def test_summary_counts_by_group_and_failures_are_listed():
    res = stub_results()
    s = rb.summarise(res)
    assert s["all"]["n_specifications"] == 6 and s["all"]["n_failed"] == 1 and s["all"]["failed_ids"] == ["A3"]
    assert s["A"]["beta_S"]["n"] == 2 and s["A"]["beta_S"]["keeps_sign"] == 1  # A2 has a positive estimate
    assert s["A"]["beta_S"]["excludes_zero"] == 0 and s["C"]["beta_S"]["excludes_zero"] == 1 and s["D"]["beta_S"]["excludes_zero"] == 0
    assert s["C-LOCO"]["n_specifications"] == 1 and s["all_excluding_LOCO"]["n_specifications"] == 5
    assert s["A"]["gamma_B"]["within_sesoi"] == 2 and s["D"]["beta_S"]["within_sesoi"] == 0
    assert s["all"]["gamma_B"]["keeps_sign"] == 4 and s["all"]["gamma_B"]["n"] == 5


def test_results_files_are_written_and_the_markdown_has_the_required_sections(tmp_path, monkeypatch):
    monkeypatch.setattr(rb, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(rb, "JSON_PATH", tmp_path / "robustness.json")
    monkeypatch.setattr(rb, "MD_PATH", tmp_path / "robustness.md")
    res = stub_results()
    res["sections"]["A"]["dk_crosscheck_real"] = {}
    rb.write_results(res)
    saved = json.loads((tmp_path / "robustness.json").read_text(encoding="utf-8"))
    assert saved["summary"]["all"]["n_specifications"] == 6
    md = (tmp_path / "robustness.md").read_text(encoding="utf-8")
    assert "## What this does not show" in md and "SIGN DIFFERS" in md and "FAILED" in md
    assert "Summary counts" in md and "associations" in md.lower()


def test_forest_plot_is_written_at_300_dpi(tmp_path):
    from PIL import Image

    out = rb.forest_plot(stub_results(), tmp_path / "forest.png")
    assert out.exists() and out.stat().st_size > 10_000
    with Image.open(out) as img:
        assert round(img.info["dpi"][0]) == 300


def test_with_columns_replaces_by_key_and_refuses_gaps():
    frame = pd.DataFrame({"eurostat_code": ["A", "A", "B"], "year": [2000, 2001, 2000], "W_S": [0.1, 0.2, 0.3]})
    new = pd.DataFrame({"eurostat_code": ["A", "A", "B"], "year": [2000, 2001, 2000], "W_S": [1.0, 2.0, 3.0]})
    assert list(rb.with_columns(frame, new, ["W_S"])["W_S"]) == [1.0, 2.0, 3.0]
    with pytest.raises(ValueError):
        rb.with_columns(frame, new.iloc[:2], ["W_S"])


def test_v7_variant_row_matches_the_headline_procedure_and_loco_summary():
    frame = with_outcome(synthetic_frame(seed=121), seed=122)
    row = rb.v7_variant_row(frame, HEADLINE_STUB, 0.5, 39, spec_id="T", group="C", label="t")
    ref = m1.run_m1(frame, n_boot=39, sesoi=m1.Interpretation(0.5, "TEST"))
    assert row["id"] == "T" and row["n_obs"] == len(frame)
    assert row["targets"]["beta_S"]["estimate"] == pytest.approx(ref.targets["beta_S"].estimate, abs=1e-10)
    assert row["targets"]["beta_S"]["ci_lo"] == pytest.approx(ref.targets["beta_S"].ci_lo, abs=1e-10)
    assert row["targets"]["beta_S"]["p"] == pytest.approx(ref.targets["beta_S"].p_bootstrap, abs=1e-12)
    assert "cr1_transparency" in row["extra"]
    rows = [stub_row(f"C4-loco-{c}", "C-LOCO", b, b - 0.3, b + 0.3) for c, b in (("AT", -0.2), ("BE", -0.5), ("CY", -0.39))]
    summary = rb.loco_summary(rows, HEADLINE_STUB)
    assert summary["beta_S"]["most_influential"] == "AT" and summary["beta_S"]["min"] == -0.5 and summary["beta_S"]["argmin"] == "BE"
    assert summary["n_fits"] == 3


def test_ols_and_v7_designs_with_cce_run_through_the_bootstrap_on_synthetic_data():
    frame = with_outcome(synthetic_frame(seed=131), seed=132)
    for kind in ("lite", "full"):
        design, report = rb.cce_design(frame, kind)
        for est in (rb.ols_estimator(design), rb.v7_estimator(design)):
            block = rb.bootstrap_block(est, 19)
            assert all(np.isfinite(v["cr1_se"]) for v in block["targets"].values())
        assert report["residual_df"] > 0
