"""Offline tests for the secondary-outcomes runner (``src/models/py/secondary.py``).

Everything here uses SYNTHETIC panels (fully synthetic keys, exposure and outcomes with known injected effects). No test reads the
real gold panel, and the refusal tests prove that the runner cannot reach it without the git tag (it only calls ``m1.load_real_panel``).
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
for sub in ("models/py", "evaluate", "normalize", "features"):
    sys.path.insert(0, str(ROOT / "src" / sub))
import m1  # noqa: E402
import power  # noqa: E402
import power_variants as pv  # noqa: E402
import secondary  # noqa: E402

B_TEST = 99
NOISE_RHO = 0.5


# ---------------------------------------------------------------------------------------------
# Synthetic panels
# ---------------------------------------------------------------------------------------------
def make_keys(n_countries: int = 27, first: int = 1995, last: int = 2021, seed: int = 11, drop_share: float = 0.0) -> pd.DataFrame:
    """Synthetic keys, exposure and moderator in the shape of the gold panel (columns without any sec_ outcome)."""
    rng = np.random.default_rng(seed)
    rows = [(f"C{c:02d}", year) for c in range(n_countries) for year in range(first, last + 1)]
    frame = pd.DataFrame(rows, columns=["eurostat_code", "year"])
    if drop_share:
        frame = frame[rng.random(len(frame)) >= drop_share].reset_index(drop=True)
    n = len(frame)
    country = frame["eurostat_code"].str[1:].astype(int)
    frame["olddep1_lag"] = 15 + 0.2 * (frame["year"] - first) + 2 * rng.standard_normal(n) + country % 9
    for name, prob in (("W_S", 0.3), ("W_E", 0.15), ("W_U", 0.1)):
        frame[name] = rng.uniform(0, 1, n) * (rng.random(n) < prob)
    frame["W_D"] = 0.0
    frame["Post"] = rng.uniform(0, 1, n) * (rng.random(n) < 0.3)
    frame["in_confirmatory"] = True
    return frame


def add_outcome(frame: pd.DataFrame, column: str, effects: dict[str, float], seed: int, rho: float = NOISE_RHO, noise_scale: float = 1.0) -> pd.DataFrame:
    """Add ``column`` = injected effects x design columns + country effects + AR(1) heteroskedastic noise (rows must already be complete)."""
    frame = frame.sort_values(["eurostat_code", "year"]).reset_index(drop=True).copy()
    frame[column] = 0.0
    design = secondary.build_secondary_design(frame, column, "synthetic", extra=True)
    rng = np.random.default_rng(seed)
    sigma = noise_scale * rng.uniform(0.7, 1.5, design.n_clusters)[design.country_idx]
    shocks = rng.standard_normal(design.n_obs)
    u = np.empty(design.n_obs)
    for i in range(design.n_obs):
        fresh = i == 0 or design.codes[i] != design.codes[i - 1] or design.year[i] - design.year[i - 1] != 1
        u[i] = shocks[i] if fresh else rho * u[i - 1] + np.sqrt(1 - rho**2) * shocks[i]
    signal = sum(beta * design.x[:, design.x_names.index(design.targets[t])] for t, beta in effects.items())
    frame[column] = signal + sigma * u + rng.standard_normal(design.n_clusters)[design.country_idx]
    return frame


# ---------------------------------------------------------------------------------------------
# Multiplicity: hand-computed examples
# ---------------------------------------------------------------------------------------------
P_TEN = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216]
# m p_(k) / k = 0.01, 0.04, 0.13, 0.1025, 0.084, 0.1, 0.105714, 0.25625, 0.235556, 0.216; running minimum from the right gives:
BH_TEN = [0.01, 0.04, 0.084, 0.084, 0.084, 0.1, 0.1057142857, 0.216, 0.216, 0.216]
HARMONIC_10 = 7381 / 2520  # 1 + 1/2 + ... + 1/10


def test_bh_matches_hand_computed_example_with_monotone_adjustment():
    assert secondary.benjamini_hochberg(P_TEN) == pytest.approx(BH_TEN, abs=1e-9)
    # the raw scaled values 0.13 and 0.1025 are NOT monotone; the adjusted values must be non-decreasing in p
    assert all(a <= b + 1e-15 for a, b in zip(BH_TEN, BH_TEN[1:]))


@pytest.mark.parametrize("raw, adjusted", [
    ([0.01, 0.02, 0.03, 0.04, 0.05], [0.05] * 5),
    ([0.04, 0.01], [0.04, 0.02]),  # input order preserved
    ([0.5, 0.0004, 0.02], [0.5, 0.0012, 0.03]),
    ([0.6, 0.7], [0.7, 0.7]),
    ([0.2], [0.2]),
    ([], []),
])
def test_bh_small_examples(raw, adjusted):
    assert secondary.benjamini_hochberg(raw) == pytest.approx(adjusted, abs=1e-12)


def test_by_is_bh_times_harmonic_sum_capped_at_one():
    by = secondary.benjamini_yekutieli(P_TEN)
    assert by == pytest.approx([min(1.0, q * HARMONIC_10) for q in BH_TEN], abs=1e-9)
    assert by[0] == pytest.approx(0.01 * HARMONIC_10)
    assert secondary.benjamini_yekutieli([0.9, 0.95]) == pytest.approx([1.0, 1.0])  # capped
    assert secondary.benjamini_yekutieli([0.01]) == pytest.approx([0.01])  # c(1) = 1
    assert secondary.benjamini_yekutieli([]) == []


def test_bh_input_validation():
    for bad in ([1.2], [-0.1], [float("nan")]):
        with pytest.raises(ValueError):
            secondary.benjamini_hochberg(bad)
        with pytest.raises(ValueError):
            secondary.benjamini_yekutieli(bad)


def test_family_is_exactly_the_ten_pre_specified_tests():
    assert secondary.FAMILY_IDS == ("S1a", "S1b", "S1c", "S1d", "S1e", "S1f-1", "S1f-2", "S1g-1", "S1g-2", "S1g-3")
    assert {o["id"] for o in secondary.CONTEXT}.isdisjoint(secondary.FAMILY_IDS)
    assert [o["column"] for o in secondary.CONTEXT] == ["sec_total_expenditure", "sec_interest_d41pay", "sec_cofog_total", "sec_cyclical_component"]


def test_apply_multiplicity_adds_q_values_only_when_all_ten_are_in():
    outcomes = [{"id": oid, "status": "ok", "targets": {"beta_S": {"p_bootstrap": p}}} for oid, p in zip(secondary.FAMILY_IDS, P_TEN)]
    partial = secondary.apply_multiplicity(outcomes[:6])
    assert not partial["complete"] and "q_bh" not in outcomes[0]["targets"]["beta_S"]
    block = secondary.apply_multiplicity(outcomes)
    assert block["complete"] and block["n_bh_reject"] == 2 and block["n_by_reject"] == 1  # BH q 0.01, 0.04; BY q 0.0293, 0.117
    assert [o["targets"]["beta_S"]["q_bh"] for o in outcomes] == pytest.approx(BH_TEN, abs=1e-9)
    assert [o["targets"]["beta_S"]["bh_reject"] for o in outcomes] == [True, True] + [False] * 8
    # re-applying after a change removes stale values
    outcomes[0]["targets"]["beta_S"]["p_bootstrap"] = 0.9
    secondary.apply_multiplicity(outcomes)
    assert outcomes[0]["targets"]["beta_S"]["q_bh"] > 0.2


# ---------------------------------------------------------------------------------------------
# Per-outcome sample builder
# ---------------------------------------------------------------------------------------------
def sample_frame() -> pd.DataFrame:
    keys = make_keys(n_countries=8, first=2000, last=2015, seed=3)
    keys["sec_x"] = np.arange(len(keys), dtype=float)
    # C00: complete (16 obs). C01: gap 2005-2006 -> two runs. C02: only 4 usable obs -> excluded. C03: no observation at all -> excluded.
    # C04: isolated single observation between two gaps. C05: first year missing (like a first difference).
    keys.loc[(keys.eurostat_code == "C01") & keys.year.isin([2005, 2006]), "sec_x"] = np.nan
    keys.loc[(keys.eurostat_code == "C02") & ~keys.year.isin([2000, 2001, 2002, 2003]), "sec_x"] = np.nan
    keys.loc[keys.eurostat_code == "C03", "sec_x"] = np.nan
    keys.loc[(keys.eurostat_code == "C04") & keys.year.isin([2003, 2005, 2006, 2007]), "sec_x"] = np.nan
    keys.loc[(keys.eurostat_code == "C05") & (keys.year == 2000), "sec_x"] = np.nan
    return keys


def test_usable_sample_drops_short_countries_and_reports_them():
    sample, info = secondary.usable_sample(sample_frame(), "sec_x")
    assert info["countries_excluded"] == {"C02": 4, "C03": 0}
    assert set(sample.eurostat_code) == {"C00", "C01", "C04", "C05", "C06", "C07"}
    assert info["rows_dropped_short_countries"] == 4
    assert sample["sec_x"].notna().all()
    assert info["rows_in_confirmatory"] == 8 * 16 and info["rows_without_outcome"] == 2 + 12 + 16 + 4 + 1


def test_usable_sample_threshold_is_five_observations_inclusive():
    frame = make_keys(n_countries=3, first=2000, last=2010, seed=5)
    frame["sec_x"] = 1.0
    frame.loc[(frame.eurostat_code == "C00") & (frame.year >= 2005), "sec_x"] = np.nan  # 5 observations: enters
    frame.loc[(frame.eurostat_code == "C01") & (frame.year >= 2004), "sec_x"] = np.nan  # 4 observations: out
    sample, info = secondary.usable_sample(frame, "sec_x")
    assert info["countries_excluded"] == {"C01": 4} and "C00" in set(sample.eurostat_code)


def test_only_confirmatory_rows_enter():
    frame = make_keys(n_countries=3, first=2000, last=2010, seed=5)
    frame["sec_x"] = 1.0
    frame.loc[frame.year == 2010, "in_confirmatory"] = False
    sample, _ = secondary.usable_sample(frame, "sec_x")
    assert sample.year.max() == 2009


def test_runs_and_gap_countries_are_counted():
    sample, info = secondary.usable_sample(sample_frame(), "sec_x")
    # C01: 2 runs; C04: runs 2000-2002, 2004, 2008-2015 -> 3 runs; the other four countries have one run each
    assert info["n_runs"] == 4 + 2 + 3 and info["countries_with_gaps"] == 2


def test_design_marks_the_row_after_a_gap_as_a_run_start():
    sample, _ = secondary.usable_sample(sample_frame(), "sec_x")
    design = secondary.build_secondary_design(sample, "sec_x", "t")
    pos = {(c, y): i for i, (c, y) in enumerate(zip(design.codes, design.year))}
    cur = set(design.cur_rows.tolist())
    assert pos[("C01", 2007)] not in cur and pos[("C01", 2004)] in cur  # 2007 follows the gap 2005-2006
    assert pos[("C04", 2004)] not in cur and pos[("C04", 2008)] not in cur and pos[("C04", 2009)] in cur  # isolated single observation 2004
    assert design.n_clusters == 6  # the cluster stays the country


def test_constant_columns_are_dropped_and_the_moderator_is_recomputed_on_the_sample():
    sample, _ = secondary.usable_sample(sample_frame(), "sec_x")
    design = secondary.build_secondary_design(sample, "sec_x", "t")
    assert "W_D" not in design.x_names  # identically zero
    z = design.x[:, design.x_names.index("A_lag")]
    assert z.mean() == pytest.approx(0.0, abs=1e-12) and z.std(ddof=0) == pytest.approx(1.0, abs=1e-12)
    ordered = sample.sort_values(["eurostat_code", "year"]).reset_index(drop=True)
    a = ordered["olddep1_lag"].to_numpy()
    assert design.scale["sd_a_pp"] == pytest.approx(a.std(ddof=0))  # standardised on THIS sample
    between = design.x[:, design.x_names.index("WS_x_between")]
    abar = pd.Series((a - a.mean()) / a.std(ddof=0)).groupby(ordered["eurostat_code"]).transform("mean").to_numpy()
    assert between == pytest.approx(ordered["W_S"].to_numpy() * abar / design.scale["sd_between_z"])
    # era centring recomputed on the sample: the exposure-weighted mean of every era term is zero
    w = design.x[:, design.x_names.index("W_S")]
    for name in (c for c in design.x_names if c.startswith("WS_x_era_")):
        assert design.x[:, design.x_names.index(name)].sum() == pytest.approx(0.0, abs=1e-9) and w.sum() > 0


def test_headline_design_is_reproduced_exactly_and_extra_targets_change_nothing():
    frame = add_outcome(make_keys(), "capb", {"beta_S": -0.5}, seed=1)
    frame = frame.assign(capb=frame["capb"])
    head = pv.build_variant_design(frame, "M1", era=True, control_names=())
    mine = secondary.build_secondary_design(frame, "capb", "mine")
    extra = secondary.build_secondary_design(frame, "capb", "extra", extra=True)
    assert head.x_names == mine.x_names == extra.x_names
    assert np.array_equal(head.x, mine.x) and np.array_equal(head.y, mine.y)
    for t in m1.ALL_TARGETS:
        assert np.array_equal(head.h[t], extra.h[t])
    assert set(extra.targets) == {"beta_S", "gamma_B", "gamma_W", "beta_E", "beta_U", "rho_Post"}
    assert extra.targets["rho_Post"] == "Post" and extra.targets["beta_E"] == "W_E" and extra.targets["beta_U"] == "W_U"


def test_missing_exposure_or_outcome_is_rejected():
    frame = make_keys(n_countries=4, first=2000, last=2010)
    frame["sec_x"] = 1.0
    broken = frame.copy()
    broken.loc[3, "olddep1_lag"] = np.nan
    with pytest.raises(ValueError, match="missing"):
        secondary.build_secondary_design(broken, "sec_x", "t")
    broken = frame.copy()
    broken.loc[3, "sec_x"] = np.nan
    with pytest.raises(ValueError, match="missing"):
        secondary.build_secondary_design(broken, "sec_x", "t")


# ---------------------------------------------------------------------------------------------
# Gaps break the run: the V7 estimator against a dense brute-force reference
# ---------------------------------------------------------------------------------------------
def reference_v7(design: power.Design, y: np.ndarray, *, break_runs: bool = True) -> dict[str, float]:
    """Dense reference for V7: runs are the maximal blocks of consecutive years of a country (or whole countries if ``break_runs`` is False).

    First-stage OLS, country weights 1 / sigma_i^2, pooled AR(1) of the country-standardised residuals over within-run pairs, Nickell
    inversion at the mean number of observations, explicit Prais-Winsten matrix per run, weighted least squares.
    """
    n, g = design.n_obs, design.n_clusters
    codes, years, cidx = design.codes, design.year, design.country_idx
    country_d = np.zeros((n, g))
    country_d[np.arange(n), cidx] = 1.0
    ys = np.unique(years)
    year_d = (years[:, None] == ys[None, 1:]).astype(float)
    z = np.hstack([country_d, year_d, design.x])
    u1 = y - z @ np.linalg.lstsq(z, y, rcond=None)[0]
    sigma2 = np.array([np.mean(u1[cidx == c] ** 2) for c in range(g)])
    std = u1 / np.sqrt(sigma2[cidx])
    cont = np.array([i for i in range(1, n) if codes[i] == codes[i - 1] and (not break_runs or years[i] - years[i - 1] == 1)])
    rho_hat = float((std[cont] * std[cont - 1]).sum() / (std[cont - 1] ** 2).sum())
    rho = float(pv.nickell_inverse(np.array([rho_hat]), float(design.counts.mean()))[0])
    p = np.zeros((n, n))
    for i in range(n):
        if i in set(cont.tolist()):
            p[i, i], p[i, i - 1] = 1.0, -rho
        else:
            p[i, i] = np.sqrt(1.0 - rho**2)
    w = np.sqrt(1.0 / sigma2[cidx])
    theta = np.linalg.lstsq((p @ z) * w[:, None], (p @ y) * w, rcond=None)[0]
    offset = g + len(ys) - 1
    return {t: float(theta[offset + design.x_names.index(col)]) for t, col in design.targets.items()}


def gap_panel() -> pd.DataFrame:
    frame = make_keys(n_countries=10, first=2000, last=2013, seed=21)
    frame = add_outcome(frame, "sec_x", {"beta_S": -1.0}, seed=2)
    frame.loc[(frame.eurostat_code == "C01") & frame.year.isin([2005, 2006, 2007]), "sec_x"] = np.nan  # gap -> two pieces
    frame.loc[(frame.eurostat_code == "C04") & frame.year.isin([2003, 2007]), "sec_x"] = np.nan  # three pieces, one isolated
    frame.loc[(frame.eurostat_code == "C06") & (frame.year < 2004), "sec_x"] = np.nan  # late start
    return frame


def test_estimator_on_an_unbalanced_panel_with_gaps_equals_the_two_pieces_as_separate_runs():
    sample, info = secondary.usable_sample(gap_panel(), "sec_x")
    assert info["countries_with_gaps"] == 2 and info["n_runs"] == 10 + 1 + 2
    design = secondary.build_secondary_design(sample, "sec_x", "gap", extra=True)
    est = pv.GlsEstimator(design, wls=True, ar1=True)
    fit = est.fit(design.y, list(design.targets))
    ref = reference_v7(design, design.y, break_runs=True)
    for t in design.targets:
        assert float(fit[t][0][0]) == pytest.approx(ref[t], abs=1e-8), t
    # the reference has power: pretending the pieces are consecutive gives a different answer
    naive = reference_v7(design, design.y, break_runs=False)
    assert max(abs(naive[t] - ref[t]) for t in ref) > 1e-4


def test_balanced_panel_matches_the_reference_too():
    frame = add_outcome(make_keys(n_countries=8, first=2000, last=2011, seed=4), "sec_x", {"beta_S": -0.8}, seed=6)
    design = secondary.build_secondary_design(frame, "sec_x", "bal")
    fit = pv.GlsEstimator(design, wls=True, ar1=True).fit(design.y, list(design.targets))
    ref = reference_v7(design, design.y)
    assert all(float(fit[t][0][0]) == pytest.approx(ref[t], abs=1e-8) for t in design.targets)


# ---------------------------------------------------------------------------------------------
# Recovery of a known beta_S and the S3 self-check
# ---------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def recovery_panel() -> pd.DataFrame:
    frame = make_keys(n_countries=27, first=1995, last=2021, seed=11, drop_share=0.15)
    frame = add_outcome(frame, "sec_primary_expenditure", {"beta_S": 1.5, "gamma_B": 0.6}, seed=3, noise_scale=0.6)
    # a gap and a short country, as in the real data
    frame.loc[(frame.eurostat_code == "C02") & frame.year.isin([2005, 2006]), "sec_primary_expenditure"] = np.nan
    frame.loc[(frame.eurostat_code == "C03") & (frame.year > 1998), "sec_primary_expenditure"] = np.nan
    return frame


def test_known_beta_s_is_recovered_with_interval_and_p_value(recovery_panel):
    spec = next(s for s in secondary.FAMILY if s["id"] == "S1d")
    out = secondary.run_outcome(recovery_panel, spec, n_boot=199)
    assert out["status"] == "ok" and out["role"] == "family"
    t = out["targets"]["beta_S"]
    assert abs(t["estimate"] - 1.5) < 0.35 and t["ci_lo"] < 1.5 < t["ci_hi"]
    assert t["p_bootstrap"] <= 0.05 and 1 / 200 <= t["p_bootstrap"] <= 1.0
    assert "C03" in out["countries_excluded"] and "C03" not in out["countries"]
    assert out["regressors_dropped_constant"] == ["W_D"]
    assert 0.0 < out["diagnostics"]["resid_sd_min"] <= out["diagnostics"]["resid_sd_median"] <= out["diagnostics"]["resid_sd_max"]
    assert -0.95 <= out["diagnostics"]["rho_nickell"] <= 0.95
    assert out["n_obs"] == len(secondary.usable_sample(recovery_panel, "sec_primary_expenditure")[0])
    # descriptive targets carry no p-value of any kind
    for name in ("gamma_B", "gamma_W"):
        assert set(out["targets"][name]) == {"estimate", "cr1_se", "ci_lo", "ci_hi", "role"} and out["targets"][name]["role"] == "descriptive"


def test_context_outcomes_get_estimate_and_interval_only(recovery_panel):
    spec = secondary.CONTEXT[0]
    frame = recovery_panel.assign(**{spec["column"]: recovery_panel["sec_primary_expenditure"]})
    out = secondary.run_outcome(frame, spec, n_boot=B_TEST)
    assert out["status"] == "ok" and out["role"] == "context"
    assert set(out["targets"]["beta_S"]) == {"estimate", "cr1_se", "ci_lo", "ci_hi", "role"}


def test_failure_is_recorded_not_raised():
    frame = make_keys(n_countries=3, first=2000, last=2010)
    frame["sec_cofog_gf10"] = np.nan  # nothing observed
    out = secondary.run_outcome(frame, next(s for s in secondary.FAMILY if s["id"] == "S1g-1"), n_boot=B_TEST)
    assert out["status"] == "failed" and "fewer than three countries" in out["error"]


def fake_headline(res: m1.M1Results) -> dict:
    return res.to_dict()


def test_s3_reproduces_the_headline_fit_and_exposes_the_extra_terms():
    frame = add_outcome(make_keys(), "capb", {"beta_S": -1.0, "beta_E": 0.7, "rho_Post": -0.4}, seed=8)
    head = m1.run_m1(frame, n_boot=B_TEST, sesoi=m1.Interpretation(0.5, "PROPOSED"))
    s3 = secondary.run_s3(frame, n_boot=B_TEST, headline=fake_headline(head))
    assert s3["self_check"]["passed"] and s3["self_check"]["max_abs_difference"] <= secondary.SELF_CHECK_TOLERANCE
    for name in m1.ALL_TARGETS:
        assert s3["targets"][name]["estimate"] == head.targets[name].estimate
    assert set(secondary.S3_NAMES) <= set(s3["targets"])
    assert abs(s3["targets"]["beta_E"]["estimate"] - 0.7) < 1.0 and abs(s3["targets"]["rho_Post"]["estimate"] + 0.4) < 1.0
    for name in secondary.S3_NAMES:
        assert s3["targets"][name]["ci_lo"] < s3["targets"][name]["estimate"] < s3["targets"][name]["ci_hi"]
        assert "p_bootstrap" not in s3["targets"][name]  # descriptive: no test


def test_self_check_fails_when_the_headline_differs():
    frame = add_outcome(make_keys(), "capb", {"beta_S": -1.0}, seed=8)
    head = fake_headline(m1.run_m1(frame, n_boot=B_TEST, sesoi=m1.Interpretation(0.5, "PROPOSED")))
    head["targets"]["beta_S"]["estimate"] += 0.01
    s3 = secondary.run_s3(frame, n_boot=B_TEST, headline=head)
    assert not s3["self_check"]["passed"]
    head["targets"]["beta_S"]["estimate"] -= 0.01
    head["n_boot"] = 9999  # not comparable: a different B changes the intervals
    assert not secondary.run_s3(frame, n_boot=B_TEST, headline=head)["self_check"]["passed"]


# ---------------------------------------------------------------------------------------------
# Output: no p-value for gamma, resume, markdown, figure, write guard
# ---------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def small_results() -> dict:
    frame = make_keys(n_countries=12, first=2000, last=2015, seed=17)
    for k, spec in enumerate((*secondary.FAMILY, *secondary.CONTEXT)):
        frame = add_outcome(frame, spec["column"], {"beta_S": 0.5 * (1 if spec["weaker"] >= 0 else -1)}, seed=100 + k)
    frame["capb"] = frame["sec_primary_balance_edp"]
    head = fake_headline(m1.run_m1(frame, n_boot=B_TEST, sesoi=m1.Interpretation(0.5, "PROPOSED")))
    res = secondary.run_all(frame, n_boot=B_TEST, headline=head)
    res["_headline"] = head
    return res


def walk(node, path=()):
    if isinstance(node, dict):
        for key, value in node.items():
            yield path, key
            yield from walk(value, (*path, key))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from walk(value, (*path, i))


def test_output_json_has_no_p_value_like_field_for_gamma(small_results):
    data = json.loads(secondary.to_json({k: v for k, v in small_results.items() if k != "_headline"}))
    assert data["status"] == "complete" and len(data["outcomes"]) == 14
    pattern = ("p_", "q_", "pval", "p-val", "bh_", "by_", "signif", "reject")
    checked = 0
    for path, key in walk(data):
        if "gamma_B" in path or "gamma_W" in path:
            assert not any(str(key).lower().startswith(w) or w in str(key).lower() for w in pattern), (path, key)
            checked += 1
    assert checked > 20
    # p-values and q-values exist only on beta_S of the family outcomes; the context outcomes and S3 carry none
    for o in data["outcomes"]:
        has = {k for k in o["targets"]["beta_S"] if k in ("p_bootstrap", "q_bh", "q_by")}
        assert has == ({"p_bootstrap", "q_bh", "q_by"} if o["role"] == "family" else set())
    # S3: the headline beta_S p-value exists only for the self-check; the descriptive terms carry none
    for name in ("gamma_B", "gamma_W", *secondary.S3_NAMES):
        assert set(data["s3"]["targets"][name]) == {"estimate", "cr1_se", "ci_lo", "ci_hi", "role"}


def test_run_all_gives_complete_multiplicity_and_resume_reuses_finished_outcomes(small_results):
    res = {k: v for k, v in small_results.items() if k != "_headline"}
    assert res["multiplicity"]["complete"] and res["multiplicity"]["m_used"] == 10
    fam = [o for o in res["outcomes"] if o["role"] == "family"]
    raw = [o["targets"]["beta_S"]["p_bootstrap"] for o in fam]
    assert [o["targets"]["beta_S"]["q_bh"] for o in fam] == pytest.approx(secondary.benjamini_hochberg(raw))
    assert [o["id"] for o in res["outcomes"]] == [*secondary.FAMILY_IDS, *(c["id"] for c in secondary.CONTEXT)]
    # resume: a previous result with the same B / seed / hash is reused without recomputation
    called = []
    original = secondary.run_outcome
    try:
        secondary.run_outcome = lambda *a, **k: called.append(1) or original(*a, **k)  # type: ignore[assignment]
        again = secondary.run_all(pd.DataFrame(), n_boot=B_TEST, previous=res, headline=None, run_s3_block=True)
    finally:
        secondary.run_outcome = original
    assert called == [] and [o["id"] for o in again["outcomes"]] == [o["id"] for o in res["outcomes"]]


def test_markdown_figure_and_write_guard(small_results, monkeypatch, tmp_path):
    head = small_results["_headline"]
    res = {k: v for k, v in small_results.items() if k != "_headline"}
    text = secondary.render_markdown(res, head)
    for needle in ("S1a", "S1g-3", "BH q", "BY q", "descriptive", "not cyclically adjusted", "Self-check", "PASSED", "Reading of the pattern"):
        assert needle in text
    assert "cause" not in text.lower().replace("because", "")  # no causal language
    paths = secondary.write_results(res, out_dir=tmp_path / "res", fig_dir=tmp_path / "fig", headline=head)
    assert [p.name for p in paths] == ["secondary.json", "secondary.md", "secondary_forest.png"]
    from PIL import Image

    with Image.open(paths[2]) as image:
        assert round(image.info["dpi"][0]) == 300 and image.size[0] > 1500
    # the default folders need real-panel results and the tag
    results_dir = tmp_path / "reports" / "results"
    monkeypatch.setattr(secondary, "RESULTS_DIR", results_dir)
    monkeypatch.setattr(m1, "RESULTS_DIR", results_dir)
    with pytest.raises(m1.ResultsNotAllowed):
        secondary.write_results(res, tag_lookup=lambda: True, figure=False)
    real = {**res, "source": secondary.SOURCE_REAL}
    with pytest.raises(m1.PreregistrationTagMissing):
        secondary.write_results(real, tag_lookup=lambda: False, figure=False)
    assert not results_dir.exists()
    assert all(p.parent == results_dir for p in secondary.write_results(real, tag_lookup=lambda: True, figure=False))


def test_pending_markdown_before_all_family_outcomes_are_in(small_results):
    res = {k: v for k, v in small_results.items() if k != "_headline"}
    partial = {**res, "status": "partial", "outcomes": res["outcomes"][:3], "multiplicity": None, "s3": None}
    partial["multiplicity"] = secondary.apply_multiplicity(partial["outcomes"])
    text = secondary.render_markdown(partial)
    assert "pending" in text and "Not yet run" in text


# ---------------------------------------------------------------------------------------------
# Guard: the real panel is reachable only through m1.load_real_panel
# ---------------------------------------------------------------------------------------------
def test_runner_refuses_the_real_panel_without_the_tag(monkeypatch, tmp_path):
    def boom(*args, **kwargs):
        raise AssertionError("the real outcome was touched without the tag")

    monkeypatch.setattr(pd, "read_parquet", boom)
    monkeypatch.setattr(secondary, "run_all", boom)
    with pytest.raises(m1.PreregistrationTagMissing):
        secondary.run_real(tag_lookup=lambda: False)
    monkeypatch.setattr(m1, "PROJECT_ROOT", tmp_path)  # the default tag lookup, against a folder that is not a repository
    with pytest.raises(m1.PreregistrationTagMissing):
        secondary.run_real()


def test_runner_uses_the_m1_loader_and_never_reads_parquet_itself():
    tree = ast.parse((ROOT / "src" / "models" / "py" / "secondary.py").read_text(encoding="utf-8"))
    called = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert "read_parquet" not in called and "run" not in called  # no direct file read, no subprocess/git of its own
    assert "load_real_panel" in called
    assert secondary.m1 is m1 and secondary.pv is pv  # reused, not copied
