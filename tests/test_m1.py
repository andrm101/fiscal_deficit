"""Offline tests for the confirmatory M1 runner (``src/models/py/m1.py``).

Every estimation test uses a SYNTHETIC outcome with a known injected effect. The real gold panel is read here only for the
columns other than ``capb`` (its sample keys, exposure and moderator); when the file is absent fully synthetic keys are used. No
test reads or analyses the real outcome, and the refusal tests prove that the runner cannot do so without the git tag.
"""
from __future__ import annotations

import ast
import dataclasses
import json
import subprocess
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import scipy

ROOT = Path(__file__).resolve().parents[1]
for sub in ("models/py", "evaluate", "normalize", "features"):
    sys.path.insert(0, str(ROOT / "src" / sub))
import m1  # noqa: E402
import power  # noqa: E402
import power_variants as pv  # noqa: E402

GOLD = ROOT / "data" / "processed" / "gold" / "panel_country_year.parquet"
NON_OUTCOME_COLUMNS = ["eurostat_code", "year", "in_confirmatory", "W_S", "W_E", "W_D", "W_U", "Post", "olddep1_lag"]  # deliberately without capb
SESOI = m1.Interpretation(sesoi_pp=0.5, status="PROPOSED")
B_TEST = 199  # modest bootstrap size in tests (the confirmatory default stays 9,999)
TRUE_BETA_S, TRUE_GAMMA_B, TRUE_GAMMA_W = -1.0, 0.8, 0.6
NOISE_RHO = 0.6


# ---------------------------------------------------------------------------------------------
# Synthetic panels
# ---------------------------------------------------------------------------------------------
def fallback_keys(seed: int = 11) -> pd.DataFrame:
    """Fully synthetic keys, exposure and moderator of the size of the real sample (27 countries, 1995-2021, 715 rows)."""
    rng = np.random.default_rng(seed)
    rows = [(f"C{c:02d}", year) for c in range(27) for year in range(1995, 2022)]
    keep = np.ones(len(rows), bool)
    keep[rng.choice(len(rows), size=len(rows) - 715, replace=False)] = False
    frame = pd.DataFrame([r for r, k in zip(rows, keep) if k], columns=["eurostat_code", "year"])
    n = len(frame)
    country = frame["eurostat_code"].str[1:].astype(int)
    frame["olddep1_lag"] = 15 + 0.2 * (frame["year"] - 1995) + 2 * rng.standard_normal(n) + country % 9
    for name, prob in (("W_S", 0.3), ("W_E", 0.15), ("W_U", 0.1)):
        frame[name] = rng.uniform(0, 1, n) * (rng.random(n) < prob)
    frame["W_D"] = 0.0
    frame["Post"] = rng.uniform(0, 1, n) * (rng.random(n) < 0.3)
    return frame


def sample_keys() -> pd.DataFrame:
    """Keys and regressors of the real confirmatory sample (no outcome column is read), or fallback synthetic keys."""
    if GOLD.exists():
        frame = pd.read_parquet(GOLD, columns=NON_OUTCOME_COLUMNS)
        assert "capb" not in frame.columns
        return frame[frame["in_confirmatory"].astype(bool)].drop(columns="in_confirmatory").reset_index(drop=True)
    return fallback_keys()


def with_outcome(keys: pd.DataFrame, effects: dict[str, float], seed: int, rho: float = NOISE_RHO) -> pd.DataFrame:
    """Add ``capb`` = injected effects x design columns + country effects + heteroskedastic AR(1) noise (country SD 1 to 3)."""
    frame = keys.sort_values(["eurostat_code", "year"]).reset_index(drop=True)
    frame["capb"] = 0.0
    design = pv.build_variant_design(frame, "synthetic", era=True)
    rng = np.random.default_rng(seed)
    sigma = rng.uniform(1.0, 3.0, design.n_clusters)[design.country_idx]
    shocks = rng.standard_normal(design.n_obs)
    u = np.empty(design.n_obs)
    for i in range(design.n_obs):
        fresh = i == 0 or design.codes[i] != design.codes[i - 1]
        u[i] = shocks[i] if fresh else rho * u[i - 1] + np.sqrt(1 - rho**2) * shocks[i]
    signal = sum(beta * design.x[:, design.x_names.index(design.targets[t])] for t, beta in effects.items())
    frame["capb"] = signal + sigma * u + rng.standard_normal(design.n_clusters)[design.country_idx]
    return frame


def small_keys(seed: int = 5) -> pd.DataFrame:
    """Balanced 30 x 12 synthetic panel for the many-dataset size study."""
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame([(f"C{c:02d}", 2000 + t) for c in range(30) for t in range(12)], columns=["eurostat_code", "year"])
    n = len(frame)
    frame["olddep1_lag"] = 20 + 0.3 * (frame["year"] - 2000) + 3 * rng.standard_normal(n) + frame["eurostat_code"].str[1:].astype(int) % 7
    for name, prob in (("W_S", 0.3), ("W_E", 0.2), ("W_U", 0.1)):
        frame[name] = rng.uniform(0, 1, n) * (rng.random(n) < prob)
    frame["W_D"] = 0.0
    frame["Post"] = rng.uniform(0, 1, n)
    return frame


@pytest.fixture(scope="module")
def keys() -> pd.DataFrame:
    return sample_keys()


@pytest.fixture(scope="module")
def one_result(keys: pd.DataFrame) -> m1.M1Results:
    frame = with_outcome(keys, {"beta_S": TRUE_BETA_S, "gamma_B": TRUE_GAMMA_B, "gamma_W": TRUE_GAMMA_W}, seed=1)
    return m1.run_m1(frame, n_boot=B_TEST, sesoi=SESOI)


# ---------------------------------------------------------------------------------------------
# Holm and interval reading
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("raw, adjusted", [
    ([0.01, 0.04], [0.02, 0.04]),
    ([0.04, 0.01], [0.04, 0.02]),  # input order is preserved
    ([0.03, 0.04], [0.06, 0.06]),  # step-down monotonicity: 2 * 0.03 = 0.06 carries over to 1 * 0.04
    ([0.01, 0.02, 0.03], [0.03, 0.04, 0.04]),
    ([0.5, 0.0004, 0.02], [0.5, 0.0012, 0.04]),
    ([0.6, 0.7], [1.0, 1.0]),  # capped at 1
    ([0.2], [0.2]),
    ([], []),
])
def test_holm_matches_hand_computed_examples(raw, adjusted):
    assert m1.holm(raw) == pytest.approx(adjusted, abs=1e-12)


def test_holm_rejects_invalid_pvalues():
    for bad in ([-0.1, 0.5], [0.5, 1.2], [float("nan"), 0.5]):
        with pytest.raises(ValueError):
            m1.holm(bad)


@pytest.mark.parametrize("lo, hi, label, excludes, equivalent", [
    (0.1, 0.9, m1.LABEL_EXCLUDES, True, False),
    (-0.9, -0.6, m1.LABEL_EXCLUDES, True, False),
    (0.1, 0.3, m1.LABEL_EXCLUDES, True, True),  # both flags true: precedence gives 'excludes zero'
    (-0.3, -0.1, m1.LABEL_EXCLUDES, True, True),
    (-0.2, 0.3, m1.LABEL_EQUIVALENT, False, True),
    (-0.5, 0.5, m1.LABEL_EQUIVALENT, False, True),  # the boundary is inclusive
    (0.0, 0.3, m1.LABEL_EQUIVALENT, False, True),  # touching zero does not exclude it
    (-0.6, 0.3, m1.LABEL_INCONCLUSIVE, False, False),
    (-0.1, 0.9, m1.LABEL_INCONCLUSIVE, False, False),
    (-1.5, 1.5, m1.LABEL_INCONCLUSIVE, False, False),
    (0.0, 0.0, m1.LABEL_EQUIVALENT, False, True),
])
def test_classify_interval_edge_cases(lo, hi, label, excludes, equivalent):
    assert m1.classify_interval(lo, hi, 0.5) == label
    assert m1.interval_flags(lo, hi, 0.5) == (excludes, equivalent)


def test_classify_interval_scales_with_sesoi_and_validates_input():
    assert m1.classify_interval(-0.4, 0.4, 0.5) == m1.LABEL_EQUIVALENT
    assert m1.classify_interval(-0.4, 0.4, 0.3) == m1.LABEL_INCONCLUSIVE
    for lo, hi, sesoi in ((0.5, 0.1, 0.5), (float("nan"), 1.0, 0.5), (0.1, float("inf"), 0.5), (-0.1, 0.1, 0.0), (-0.1, 0.1, -1.0)):
        with pytest.raises(ValueError):
            m1.classify_interval(lo, hi, sesoi)


# ---------------------------------------------------------------------------------------------
# Estimation on synthetic data with known effects
# ---------------------------------------------------------------------------------------------
def test_effects_are_recovered_across_seeds(keys):
    errors = {"beta_S": [], "gamma_B": [], "gamma_W": []}
    covered = {t: 0 for t in errors}
    seeds = range(1, 9)
    truth = {"beta_S": TRUE_BETA_S, "gamma_B": TRUE_GAMMA_B, "gamma_W": TRUE_GAMMA_W}
    for seed in seeds:
        res = m1.run_m1(with_outcome(keys, truth, seed=seed), n_boot=B_TEST, sesoi=SESOI)
        for t, value in truth.items():
            tr = res.targets[t]
            errors[t].append(tr.estimate - value)
            covered[t] += tr.ci_lo <= value <= tr.ci_hi
            assert tr.ci_lo < tr.estimate < tr.ci_hi
    for t in ("beta_S", "gamma_B"):
        assert max(abs(e) for e in errors[t]) < 0.6, errors[t]  # SE is about 0.15-0.3 in this design
        assert abs(np.mean(errors[t])) < 0.25
        assert covered[t] >= 6  # 95% nominal on 8 seeds
    assert abs(np.mean(errors["gamma_W"])) < 0.4  # gamma_W is imprecise by design (not powered)


def test_strong_effects_are_detected_with_the_right_sign_and_reading(one_result):
    beta, gamma_b = one_result.targets["beta_S"], one_result.targets["gamma_B"]
    assert beta.estimate < 0 < gamma_b.estimate
    assert beta.p_bootstrap <= 0.05 and gamma_b.p_bootstrap <= 0.05
    assert beta.reading == m1.LABEL_EXCLUDES and beta.excludes_zero and not beta.equivalent_within_sesoi
    assert m1.holm([beta.p_bootstrap, gamma_b.p_bootstrap]) == pytest.approx([beta.p_holm, gamma_b.p_holm])


def test_null_rejection_rate_and_interval_coverage_are_plausible():
    keys = small_keys()
    datasets, rejections, covered = 40, {"beta_S": 0, "gamma_B": 0}, {"beta_S": 0, "gamma_B": 0}
    for seed in range(100, 100 + datasets):
        res = m1.run_m1(with_outcome(keys, {}, seed=seed, rho=NOISE_RHO), n_boot=99, sesoi=SESOI)
        for t in rejections:
            tr = res.targets[t]
            rejections[t] += tr.p_bootstrap <= 0.05
            covered[t] += tr.ci_lo <= 0.0 <= tr.ci_hi
    for t in rejections:
        assert rejections[t] / datasets <= 0.15, rejections  # nominal 5%: 40 datasets, P(more than 6 rejections) is below 1%
        assert covered[t] / datasets >= 0.80, covered


def test_pvalues_are_on_the_bootstrap_grid_and_use_seed_key_42(keys):
    frame = with_outcome(keys, {"beta_S": -0.5}, seed=3)
    res = m1.run_m1(frame, n_boot=99, sesoi=SESOI)
    assert res.seed == 42 and res.seed_key == 42 and res.n_boot == 99
    for t in m1.CONFIRMATORY_TARGETS:
        p = res.targets[t].p_bootstrap
        assert p * 100 == pytest.approx(round(p * 100)) and 0.01 <= p <= 1.0  # (1 + count) / (B + 1)
    again = m1.run_m1(frame, n_boot=99, sesoi=SESOI)
    assert again.to_dict() == res.to_dict()  # deterministic
    other = m1.run_m1(frame, n_boot=99, seed_key=7, sesoi=SESOI)
    assert other.targets["beta_S"].estimate == res.targets["beta_S"].estimate  # the point estimate does not depend on the bootstrap seed


def test_bootstrap_statistics_are_studentised_from_the_unrestricted_fit(keys):
    frame = with_outcome(keys, {"beta_S": -0.5}, seed=4)
    design = pv.build_variant_design(frame, "M1", era=True)
    est = pv.GlsEstimator(design, wls=True, ar1=True)
    t_star = m1.unrestricted_bootstrap_t(est, design.y, m1.ALL_TARGETS, 50, 42)
    fit, resid = est.fit(design.y[:, None], list(m1.ALL_TARGETS), want_resid=True)
    v = power.bootstrap_weights(power.make_rng(power.PURPOSE_WCB_WEIGHTS, 42, 0), (1, design.n_clusters, 50), "rademacher")[0]
    star = (design.y[:, None] - resid) + v[design.country_idx, :] * resid
    fit_star = est.fit(star, list(m1.ALL_TARGETS))
    for t in m1.ALL_TARGETS:
        assert t_star[t] == pytest.approx((fit_star[t][0] - fit[t][0][0]) / fit_star[t][1])
        assert abs(np.mean(t_star[t])) < 0.6 and 0.5 < np.std(t_star[t]) < 2.0  # roughly centred, roughly unit scale
    assert set(np.unique(v)) == {-1.0, 1.0}  # Rademacher


def test_gamma_w_is_descriptive_with_no_pvalue_or_adjustment(one_result):
    gw = one_result.targets["gamma_W"]
    assert gw.role == "descriptive"
    assert gw.p_bootstrap is None and gw.p_holm is None and gw.cr1_p is None
    assert gw.reading is None and gw.excludes_zero is None and gw.equivalent_within_sesoi is None
    assert gw.ci_lo < gw.estimate < gw.ci_hi
    assert one_result.holm_family == ("beta_S", "gamma_B")
    flat = one_result.to_dict()["targets"]["gamma_W"]
    assert all(flat[k] is None for k in ("p_bootstrap", "p_holm", "cr1_p"))
    for t in m1.CONFIRMATORY_TARGETS:
        tr = one_result.targets[t]
        assert tr.p_bootstrap is not None and tr.p_holm is not None and tr.p_holm >= tr.p_bootstrap
        assert tr.cr1_note == "not valid for this estimator (over-rejects)"


def test_cr1_block_is_the_t26_transparency_report(one_result):
    n_clusters = one_result.n_countries
    tcrit = scipy.stats.t.ppf(0.975, n_clusters - 1)
    for t in m1.ALL_TARGETS:
        tr = one_result.targets[t]
        assert tr.cr1_ci_lo == pytest.approx(tr.estimate - tcrit * tr.cr1_se) and tr.cr1_ci_hi == pytest.approx(tr.estimate + tcrit * tr.cr1_se)
    tr = one_result.targets["beta_S"]
    assert tr.cr1_p == pytest.approx(2 * scipy.stats.t.sf(abs(tr.estimate / tr.cr1_se), n_clusters - 1))


def test_estimator_is_v7_on_the_registry_m1_design(keys):
    frame = with_outcome(keys, {}, seed=2)
    design = pv.build_variant_design(frame, "M1", era=True, control_names=())
    assert not any(c in design.x_names for c in ("outgap_lag", "euro_member"))  # no controls in the primary model
    assert {"WS_x_between", "WS_x_within", "WS_x_era_2008_2015", "WS_x_era_2016_2021", "A_lag", "W_S"} <= set(design.x_names)
    spec = pv.GATE3D_SPECS["V7"]
    assert spec.estimator == "gls" and spec.wls and spec.ar1 and not spec.winsor and not spec.use_controls
    res = m1.run_m1(frame, n_boot=29, sesoi=SESOI)
    fit = pv.GlsEstimator(design, wls=True, ar1=True).fit(design.y)
    for t in m1.ALL_TARGETS:
        assert res.targets[t].estimate == pytest.approx(float(fit[t][0][0]), abs=1e-12)
        assert res.targets[t].cr1_se == pytest.approx(float(fit[t][1][0]), abs=1e-12)


def test_input_validation(keys):
    frame = with_outcome(keys, {}, seed=2)
    with pytest.raises(ValueError, match="missing columns"):
        m1.run_m1(frame.drop(columns="Post"), n_boot=9, sesoi=SESOI)
    bad = frame.copy()
    bad.loc[3, "capb"] = np.nan
    with pytest.raises(ValueError, match="missing values"):
        m1.run_m1(bad, n_boot=9, sesoi=SESOI)
    with pytest.raises(ValueError, match="duplicated"):
        m1.run_m1(pd.concat([frame, frame.iloc[[0]]]), n_boot=9, sesoi=SESOI)


# ---------------------------------------------------------------------------------------------
# Hashes, registry, output
# ---------------------------------------------------------------------------------------------
def test_sesoi_is_read_from_the_registry():
    interp = m1.load_interpretation()
    assert interp.sesoi_pp == 0.5 and interp.status in {"PROPOSED", "CONFIRMED"}


def test_file_hash_is_line_ending_independent(tmp_path):
    lf, crlf = tmp_path / "a.txt", tmp_path / "b.txt"
    lf.write_bytes(b"x = 1\ny = 2\n")
    crlf.write_bytes(b"x = 1\r\ny = 2\r\n")
    assert m1.file_sha256(lf) == m1.file_sha256(crlf)
    hashes = m1.code_hashes()
    assert {"m1.py", "power_variants.py", "code_hash", "dependency:power.py"} == set(hashes)
    assert all(len(v) == 64 for v in hashes.values())


def test_output_carries_the_hashes_versions_and_estimates(one_result, tmp_path):
    paths = m1.write_results(one_result, tmp_path / "out")
    assert [p.name for p in paths] == ["m1_confirmatory.json", "m1_confirmatory.md"]
    def strict(constant: str):
        raise ValueError(f"non-finite JSON constant {constant}")
    data = json.loads(paths[0].read_text(encoding="utf-8"), parse_constant=strict)
    assert data["registry_hash"] == m1.file_sha256(m1.REGISTRY_TOML) and len(data["registry_hash"]) == 64
    assert data["code_hash"] == m1.code_hashes()["code_hash"]
    assert set(data["code_hashes"]) >= {"m1.py", "power_variants.py"}
    assert data["seed"] == 42 and data["n_boot"] == B_TEST
    assert data["versions"] == {"numpy": np.__version__, "pandas": pd.__version__, "scipy": scipy.__version__}
    assert "extract_hash" in data and data["extract_hash"] is None  # synthetic runs have no gold extract hash
    assert data["n_obs"] == one_result.n_obs and data["n_countries"] == one_result.n_countries
    assert data["estimator"].startswith("V7") and data["sesoi_pp"] == 0.5 and data["sesoi_status"] in {"PROPOSED", "CONFIRMED"}
    assert set(data["targets"]) == {"beta_S", "gamma_B", "gamma_W"}
    assert data["targets"]["beta_S"]["estimate"] == one_result.targets["beta_S"].estimate
    text = paths[1].read_text(encoding="utf-8")
    for needle in ("not valid for this estimator (over-rejects)", "Holm", "Descriptive", "registry hash", "code hash", "gold extract hash"):
        assert needle in text
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["m1_confirmatory.json", "m1_confirmatory.md"]  # no other output


def test_gamma_w_has_no_pvalue_in_the_markdown(one_result):
    text = m1.render_markdown(one_result)
    section = text.split("## Descriptive")[1].split("## CR1")[0]
    assert "gamma_W" in section and "p (" not in section
    cr1 = text.split("## CR1")[1].split("## Provenance")[0]
    row = next(line for line in cr1.splitlines() if line.startswith("| gamma_W"))
    assert row.split("|")[4].strip() == "-"  # CR1 p column is empty for gamma_W


# ---------------------------------------------------------------------------------------------
# The freeze guard: no tag, no real outcome
# ---------------------------------------------------------------------------------------------
def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.org", "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", "-C", str(repo), *args],
                   check=True, capture_output=True)


@pytest.fixture
def temp_repo(tmp_path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / "f.txt").write_text("x\n", encoding="utf-8")
    git(repo, "add", "f.txt")
    git(repo, "commit", "-q", "-m", "init")
    return repo


def test_tag_lookup_on_a_temporary_repository(temp_repo, tmp_path):
    assert not m1.tag_exists(repo=temp_repo)
    git(temp_repo, "tag", "-a", "preregistration-v10", "-m", "other")
    assert not m1.tag_exists(repo=temp_repo)  # a different tag with the same prefix does not count
    git(temp_repo, "tag", "-a", m1.PREREG_TAG, "-m", "freeze")
    assert m1.tag_exists(repo=temp_repo)
    assert not m1.tag_exists(repo=tmp_path)  # not a repository: absent


def forbid_everything(monkeypatch):
    """Make any read of a Parquet file or any estimation fail the test."""
    def boom(*args, **kwargs):
        raise AssertionError("the real outcome was touched without the tag")
    monkeypatch.setattr(pd, "read_parquet", boom)
    monkeypatch.setattr(m1, "run_m1", boom)
    monkeypatch.setattr(m1.pv, "GlsEstimator", boom)
    monkeypatch.setattr(m1.pv, "build_variant_design", boom)


def test_real_panel_refused_without_tag_before_any_read_or_computation(monkeypatch, temp_repo):
    forbid_everything(monkeypatch)
    with pytest.raises(m1.PreregistrationTagMissing):
        m1.run_real(tag_lookup=lambda: False)
    with pytest.raises(m1.PreregistrationTagMissing):
        m1.load_real_panel(tag_lookup=lambda: False)
    monkeypatch.setattr(m1, "PROJECT_ROOT", temp_repo)  # default lookup against a repository that has no tag
    with pytest.raises(m1.PreregistrationTagMissing):
        m1.run_real()
    with pytest.raises(m1.PreregistrationTagMissing):
        m1.require_preregistration_tag()


def test_main_refuses_without_tag(monkeypatch, temp_repo, capsys):
    forbid_everything(monkeypatch)
    monkeypatch.setattr(m1, "PROJECT_ROOT", temp_repo)
    assert m1.main([]) == 1
    assert "REFUSED" in capsys.readouterr().err
    assert m1.main(["--check"]) == 1
    git(temp_repo, "tag", "-a", m1.PREREG_TAG, "-m", "freeze")
    assert m1.main(["--check"]) == 0


def test_only_load_real_panel_reads_parquet():
    tree = ast.parse(Path(m1.__file__).read_text(encoding="utf-8"))
    readers = {}
    for func in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        for node in ast.walk(func):
            if isinstance(node, ast.Attribute) and node.attr in ("read_parquet", "read_csv"):
                readers.setdefault(func.name, 0)
                readers[func.name] += 1
    assert readers == {"load_real_panel": 1}
    load_src = ast.get_source_segment(Path(m1.__file__).read_text(encoding="utf-8"), next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "load_real_panel"))
    assert load_src.index("require_preregistration_tag") < load_src.index("read_parquet")  # the guard precedes the read
    source = Path(m1.__file__).read_text(encoding="utf-8")
    assert "C:\\" not in source and "/Users/" not in source


def fake_gold(n_countries: int = 5, n_years: int = 6) -> pd.DataFrame:
    """Synthetic stand-in for the gold file (with an outcome column) used only to test the loader's checks."""
    frame = small_keys().query("eurostat_code < 'C%02d' and year < %d" % (n_countries, 2000 + n_years)).copy()
    frame["in_confirmatory"] = True
    frame["capb"] = 0.0
    return frame


def test_loader_checks_hash_and_extract_size(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "panel", types.SimpleNamespace(extract_hash=lambda frame: "ab" * 32))
    gold = fake_gold()
    monkeypatch.setattr(pd, "read_parquet", lambda *a, **k: gold)
    monkeypatch.setattr(m1, "EXPECTED_ROWS", len(gold))
    monkeypatch.setattr(m1, "EXPECTED_COUNTRIES", gold["eurostat_code"].nunique())

    def run(recorded: str):
        hash_file = tmp_path / "h.sha256"
        hash_file.write_text(f"{recorded}  label\n", encoding="utf-8")
        return m1.load_real_panel(tmp_path / "p.parquet", hash_file, tag_lookup=lambda: True)

    extract, digest = run("ab" * 32)
    assert digest == "ab" * 32 and len(extract) == len(gold)
    with pytest.raises(ValueError, match="differs from the recorded"):
        run("cd" * 32)
    monkeypatch.setattr(m1, "EXPECTED_ROWS", len(gold) + 1)
    with pytest.raises(ValueError, match="expected"):
        run("ab" * 32)


def test_write_results_to_the_default_folder_needs_real_source_and_tag(one_result, monkeypatch, tmp_path):
    results_dir = tmp_path / "reports" / "results"
    monkeypatch.setattr(m1, "RESULTS_DIR", results_dir)
    with pytest.raises(m1.ResultsNotAllowed):
        m1.write_results(one_result, tag_lookup=lambda: True)  # synthetic results never go to reports/results
    real = dataclasses.replace(one_result, source=m1.SOURCE_REAL, extract_hash="ab" * 32)
    with pytest.raises(m1.PreregistrationTagMissing):
        m1.write_results(real, tag_lookup=lambda: False)
    with pytest.raises(m1.PreregistrationTagMissing):
        m1.write_results(real, results_dir, tag_lookup=lambda: False)  # naming the default folder explicitly does not bypass it
    assert not results_dir.exists() and not results_dir.parent.exists()  # the folder is created only when allowed
    paths = m1.write_results(real, tag_lookup=lambda: True)
    assert all(p.parent == results_dir and p.exists() for p in paths)
    assert json.loads(paths[0].read_text(encoding="utf-8"))["extract_hash"] == "ab" * 32


def test_run_real_end_to_end_with_a_stubbed_loader(monkeypatch, keys, tmp_path):
    """With the tag 'present' and a stubbed Parquet read of a SYNTHETIC panel, the real path labels results as real and records the hash."""
    gold = with_outcome(keys, {"beta_S": -0.5}, seed=9).assign(in_confirmatory=True)
    monkeypatch.setitem(sys.modules, "panel", types.SimpleNamespace(extract_hash=lambda f: "ef" * 32))
    monkeypatch.setattr(pd, "read_parquet", lambda *a, **k: gold)
    monkeypatch.setattr(m1, "EXPECTED_ROWS", len(gold))
    monkeypatch.setattr(m1, "EXPECTED_COUNTRIES", gold["eurostat_code"].nunique())
    hash_file = tmp_path / "h.sha256"
    hash_file.write_text("ef" * 32 + "  label\n", encoding="utf-8")
    res = m1.run_real(n_boot=29, tag_lookup=lambda: True, hash_file=hash_file)
    assert res.source == m1.SOURCE_REAL and res.extract_hash == "ef" * 32 and res.n_boot == 29
