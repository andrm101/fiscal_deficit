"""Pre-specified secondary-outcomes analysis (``docs/secondary_spec.md``; ``docs/preregistration.md`` section 10).

The model, estimator and inference are those of the confirmatory run (``m1.py``), imported and not copied: M1 with centred era terms
and no controls, estimated by V7 = ``GlsEstimator(wls=True, ar1=True)``; null-imposed wild-cluster bootstrap-t p-values and
unrestricted bootstrap-t percentile intervals (Rademacher weights, B = 9,999, seed key 42, the whole feasible procedure re-estimated
in every bootstrap sample). The real gold panel is read only through :func:`m1.load_real_panel`, which refuses unless the tag
``preregistration-v1`` exists.

Per-outcome sample
------------------
The estimation sample of an outcome is the confirmatory rows with that outcome observed. A gap inside a country's series breaks the run
(``power.build_design`` marks a row as continuing a run only if the same country has the previous calendar year in the sample, so the
Prais-Winsten step restarts after a gap: ``tests/test_secondary.py`` checks this against a dense reference). A country needs at least
``MIN_OBS = 5`` usable observations to enter; the clusters remain the countries. The moderator standardisation, its Mundlak split and
the era centring are recomputed on each outcome's own sample by the same functions as the headline (``power.regressors_from_frame``,
``power_variants.era_terms``); a regressor with no variation on the sample (``W_D``) is dropped automatically and reported.

Reporting
---------
* ``beta_S`` per outcome: estimate, 95% unrestricted bootstrap-t interval, null-imposed bootstrap p; Benjamini-Hochberg q (the
  pre-registered adjustment) and Benjamini-Yekutieli q (conservative check) over the ten outcomes S1a-S1g-3.
* ``gamma_B`` and ``gamma_W``: estimate and interval only (descriptive; no p-value is computed or stored).
* Descriptive-context outcomes: the same model, estimate and interval only, outside the multiplicity family.
* S3: ``beta_E``, ``beta_U`` and ``rho`` (the ``Post`` coefficient) from the same CAPB fit as the headline (extra named targets of the
  same design), descriptive; the headline ``beta_S``, ``gamma_B``, ``gamma_W`` of this fit are compared with ``m1_confirmatory.json``.

Everything is described as associations; the non-CAPB outcomes are not cyclically adjusted, so a match or mismatch with the CAPB
result mixes policy and cyclical effects.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m1  # noqa: E402  (the confirmatory runner: guard, loader, bootstrap-t intervals, hashes)

pv, power = m1.pv, m1.power

PROJECT_ROOT = m1.PROJECT_ROOT
RESULTS_DIR = m1.RESULTS_DIR
FIGURES_DIR = PROJECT_ROOT / "reports" / "figures"
RESULT_STEM = "secondary"
FIGURE_NAME = "secondary_forest.png"
SPEC_FILE = PROJECT_ROOT / "docs" / "secondary_spec.md"
REGISTRY_TOML = PROJECT_ROOT / "config" / "registry" / "secondary.toml"
HEADLINE_JSON = RESULTS_DIR / "m1_confirmatory.json"

MIN_OBS = 5  # a country needs at least this many usable observations to enter an outcome
BH_Q = 0.05
CI_LEVEL = m1.CI_LEVEL
SOURCE_LINE = "Source: European Commission, AMECO Spring 2026; Eurostat; ETAD; ParlGov; author's calculations"
SELF_CHECK_TOLERANCE = 1e-8
EXTRA_TARGETS = {"beta_E": "W_E", "beta_U": "W_U", "rho_Post": "Post"}  # S3: named targets of the headline design
S3_NAMES = tuple(EXTRA_TARGETS)
HEADLINE_NAMES = ("beta_S", "gamma_B", "gamma_W")
SOURCE_REAL, SOURCE_SUPPLIED = m1.SOURCE_REAL, m1.SOURCE_SUPPLIED

# (id, column, label, unit, group, direction of a weaker budget balance: +1 = higher value, -1 = lower value)
FAMILY: tuple[dict, ...] = (
    {"id": "S1a", "column": "sec_primary_balance_edp", "label": "Primary balance (EDP, AMECO UBLGIE)", "unit": "pp of GDP", "group": "Balances", "weaker": -1},
    {"id": "S1b", "column": "sec_net_lending_b9", "label": "Net lending (B9)", "unit": "pp of GDP", "group": "Balances", "weaker": -1},
    {"id": "S1c", "column": "sec_d_capb", "label": "Change in CAPB", "unit": "pp of potential GDP", "group": "Balances", "weaker": -1},
    {"id": "S1d", "column": "sec_primary_expenditure", "label": "Primary expenditure (TE - D41PAY)", "unit": "pp of GDP", "group": "Primary expenditure", "weaker": +1},
    {"id": "S1e", "column": "sec_revenue", "label": "Total revenue (TR)", "unit": "pp of GDP", "group": "Revenue", "weaker": -1},
    {"id": "S1f-1", "column": "sec_social_benefits_d62", "label": "Social benefits other than in kind (D62PAY)", "unit": "pp of GDP", "group": "Social benefits", "weaker": +1},
    {"id": "S1f-2", "column": "sec_social_transfers_kind_d632", "label": "Social transfers in kind (D632PAY)", "unit": "pp of GDP", "group": "Social benefits", "weaker": +1},
    {"id": "S1g-1", "column": "sec_cofog_gf10", "label": "COFOG social protection (GF10)", "unit": "pp of GDP", "group": "COFOG", "weaker": +1},
    {"id": "S1g-2", "column": "sec_cofog_gf1002", "label": "COFOG old age (GF1002)", "unit": "pp of GDP", "group": "COFOG", "weaker": +1},
    {"id": "S1g-3", "column": "sec_cofog_gf07", "label": "COFOG health (GF07)", "unit": "pp of GDP", "group": "COFOG", "weaker": +1},
)
CONTEXT: tuple[dict, ...] = (
    {"id": "C-te", "column": "sec_total_expenditure", "label": "Total expenditure (TE)", "unit": "pp of GDP", "group": "Descriptive context", "weaker": +1},
    {"id": "C-d41", "column": "sec_interest_d41pay", "label": "Interest (D41PAY)", "unit": "pp of GDP", "group": "Descriptive context", "weaker": +1},
    {"id": "C-cofog", "column": "sec_cofog_total", "label": "COFOG total", "unit": "pp of GDP", "group": "Descriptive context", "weaker": +1},
    {"id": "C-cyc", "column": "sec_cyclical_component", "label": "Cyclical component (AMECO UBLGCP)", "unit": "pp of potential GDP", "group": "Descriptive context", "weaker": 0},
)
FAMILY_IDS = tuple(o["id"] for o in FAMILY)


# ---------------------------------------------------------------------------------------------
# Multiplicity
# ---------------------------------------------------------------------------------------------
def benjamini_hochberg(pvalues: Sequence[float]) -> list[float]:
    """Benjamini-Hochberg (1995) adjusted p-values (q-values), in the input order.

    Sorted ascending ``p_(1) <= ... <= p_(m)``: ``q_(i) = min(1, min_{k >= i} m p_(k) / k)`` (the running minimum from the largest
    p-value downward makes the adjusted values monotone). Rejecting where ``q <= alpha`` controls the false discovery rate at
    ``alpha`` for independent or positively dependent tests.
    """
    p = np.asarray(pvalues, float)
    m = len(p)
    if m == 0:
        return []
    if np.any(np.isnan(p)) or np.any((p < 0) | (p > 1)):
        raise ValueError("p-values must lie in [0, 1]")
    order = np.argsort(p, kind="stable")
    scaled = p[order] * m / np.arange(1, m + 1)
    adjusted = np.minimum(1.0, np.minimum.accumulate(scaled[::-1])[::-1])
    out = np.empty(m)
    out[order] = adjusted
    return [float(v) for v in out]


def benjamini_yekutieli(pvalues: Sequence[float]) -> list[float]:
    """Benjamini-Yekutieli (2001) adjusted p-values: the BH values times ``c(m) = sum_{i=1..m} 1 / i`` (capped at 1).

    Valid under arbitrary dependence between the tests, hence conservative; shown beside BH as a check.
    """
    m = len(pvalues)
    if m == 0:
        return []
    harmonic = float(np.sum(1.0 / np.arange(1, m + 1)))
    p = np.asarray(pvalues, float)
    if np.any(np.isnan(p)) or np.any((p < 0) | (p > 1)):
        raise ValueError("p-values must lie in [0, 1]")
    order = np.argsort(p, kind="stable")
    scaled = p[order] * m * harmonic / np.arange(1, m + 1)
    adjusted = np.minimum(1.0, np.minimum.accumulate(scaled[::-1])[::-1])
    out = np.empty(m)
    out[order] = adjusted
    return [float(v) for v in out]


# ---------------------------------------------------------------------------------------------
# Per-outcome sample and design
# ---------------------------------------------------------------------------------------------
def _runs_in(codes: np.ndarray, years: np.ndarray) -> tuple[int, int]:
    """``(number of runs of consecutive years, number of countries with at least one gap)`` for rows sorted by country and year."""
    if len(codes) == 0:
        return 0, 0
    new_run = np.r_[True, (codes[1:] != codes[:-1]) | (years[1:] - years[:-1] != 1)]
    new_country = np.r_[True, codes[1:] != codes[:-1]]
    gap_country = np.unique(codes[new_run & ~new_country])
    return int(new_run.sum()), int(len(gap_country))


def usable_sample(extract: pd.DataFrame, column: str, min_obs: int = MIN_OBS) -> tuple[pd.DataFrame, dict]:
    """Estimation sample of an outcome: confirmatory rows with ``column`` observed, countries with fewer than ``min_obs`` removed.

    Returns ``(sample, info)``; ``info`` reports the rows without the outcome, the countries that do not enter (with their usable
    observation counts, 0 when the country has none), the number of runs and the countries with an internal gap (a gap breaks the
    run, the cluster stays the country).
    """
    frame = extract[extract["in_confirmatory"].astype(bool)] if "in_confirmatory" in extract.columns else extract
    frame = frame.sort_values(["eurostat_code", "year"]).reset_index(drop=True)
    observed = frame[frame[column].notna()]
    counts = observed.groupby("eurostat_code").size()
    all_codes = sorted(frame["eurostat_code"].unique())
    excluded = {code: int(counts.get(code, 0)) for code in all_codes if counts.get(code, 0) < min_obs}
    sample = observed[~observed["eurostat_code"].isin(excluded)].reset_index(drop=True)
    n_runs, n_gap = _runs_in(sample["eurostat_code"].to_numpy(), sample["year"].to_numpy(int))
    info = {
        "rows_in_confirmatory": int(len(frame)), "rows_without_outcome": int(len(frame) - len(observed)),
        "countries_excluded": excluded, "rows_dropped_short_countries": int(sum(excluded.values())),
        "n_runs": n_runs, "countries_with_gaps": n_gap,
    }
    return sample, info


def build_secondary_design(sample: pd.DataFrame, column: str, label: str, *, extra: bool = False) -> power.Design:
    """V7 design of M1 (era terms, no controls) with the outcome ``column`` as the dependent variable.

    The regressors, scale constants and the three headline targets come from ``power_variants.variant_regressors`` (the functions the
    headline uses, evaluated on THIS sample). ``extra`` adds the named targets ``beta_E``, ``beta_U`` and ``rho_Post`` (coefficients of
    ``W_E``, ``W_U`` and ``Post``) that are present as regressors; this changes no existing target.
    """
    frame = sample.sort_values(["eurostat_code", "year"]).reset_index(drop=True).copy()
    needed = [c for c in m1.REQUIRED_COLUMNS if c != "capb"]
    if frame[needed].isna().any().any():
        raise ValueError("missing values in the exposure or moderator columns of the estimation sample")
    if frame[column].isna().any():
        raise ValueError(f"outcome {column} has missing values in the estimation sample")
    frame["capb"] = frame[column].astype(float)  # build_design reads the dependent variable from this column
    regressors, scale, targets = pv.variant_regressors(frame, era=True, control_names=())
    targets = dict(targets)
    if extra:
        targets.update({name: col for name, col in EXTRA_TARGETS.items() if col in regressors.columns})
    missing = [t for t in ("beta_S",) if t not in targets]
    if missing or "W_S" not in regressors.columns:
        raise ValueError("W_S has no variation on the estimation sample")
    return power.build_design(frame, label=label, regressors=regressors, targets=targets, scale=scale)


# ---------------------------------------------------------------------------------------------
# Estimation of one outcome
# ---------------------------------------------------------------------------------------------
def _interval(t_star: np.ndarray, estimate: float, se: float) -> tuple[float, float]:
    tail = (1.0 - CI_LEVEL) / 2.0
    q_lo, q_hi = np.quantile(t_star, [tail, 1.0 - tail])
    return float(estimate - q_hi * se), float(estimate - q_lo * se)


def fit_design(design: power.Design, names: Sequence[str], *, n_boot: int, seed_key: int, p_target: str | None) -> dict:
    """Fit V7 on ``design``; estimate, CR1 SE and unrestricted bootstrap-t interval of ``names``; null-imposed p of ``p_target`` only.

    Also the fit diagnostics from the first stage of the very same fit: the Nickell-corrected persistence and the range of the
    country residual SDs (the WLS weights are their inverse squares).
    """
    est = pv.GlsEstimator(design, wls=True, ar1=True)
    y = design.y
    names = [n for n in names if n in design.targets]
    fit = est.fit(y, names)
    t_star = m1.unrestricted_bootstrap_t(est, y, names, n_boot, seed_key)
    out: dict = {"targets": {}}
    for name in names:
        estimate, se = float(fit[name][0][0]), float(fit[name][1][0])
        lo, hi = _interval(t_star[name], estimate, se)
        out["targets"][name] = {"estimate": estimate, "cr1_se": se, "ci_lo": lo, "ci_hi": hi}
    if p_target is not None:
        out["targets"][p_target]["p_bootstrap"] = float(pv.wild_bootstrap_pvalues(est, p_target, y[:, None], weights="rademacher", n_boot=n_boot, seed_key=seed_key)[0])
    _, u1, rho, _ = est.first_stage(y[:, None])
    sd = np.sqrt(np.add.reduceat(u1[:, 0] ** 2, design.starts) / design.counts)
    code_of = design.codes[design.starts]
    out["diagnostics"] = {
        "rho_nickell": float(rho[0]), "resid_sd_min": float(sd.min()), "resid_sd_max": float(sd.max()),
        "resid_sd_min_country": str(code_of[int(np.argmin(sd))]), "resid_sd_max_country": str(code_of[int(np.argmax(sd))]),
        "resid_sd_median": float(np.median(sd)),
    }
    return out


def run_outcome(extract: pd.DataFrame, spec: dict, *, n_boot: int, seed_key: int = m1.SEED_KEY) -> dict:
    """One outcome end to end: sample, design, fit. Never raises on a modelling failure; records ``status = 'failed'`` and the reason."""
    base = {k: spec[k] for k in ("id", "column", "label", "unit", "group")}
    base["role"] = "family" if spec["id"] in FAMILY_IDS else "context"
    sample, info = usable_sample(extract, spec["column"])
    base.update(info)
    if len(sample) == 0 or sample["eurostat_code"].nunique() < 3:
        return {**base, "status": "failed", "error": "fewer than three countries with the required observations", "n_obs": int(len(sample))}
    years = sample["year"].to_numpy(int)
    base.update({"n_obs": int(len(sample)), "n_countries": int(sample["eurostat_code"].nunique()), "year_min": int(years.min()), "year_max": int(years.max()),
                 "countries": sorted(sample["eurostat_code"].unique().tolist())})
    try:
        design = build_secondary_design(sample, spec["column"], label=spec["id"])
        fitted = fit_design(design, HEADLINE_NAMES, n_boot=n_boot, seed_key=seed_key, p_target="beta_S" if base["role"] == "family" else None)
    except (ValueError, np.linalg.LinAlgError, FloatingPointError) as error:
        return {**base, "status": "failed", "error": f"{type(error).__name__}: {error}"}
    all_regressors = ["W_S", "W_E", "W_D", "W_U", "Post"]
    base["regressors_dropped_constant"] = [c for c in all_regressors if c not in design.x_names]
    base["era_terms"] = [c for c in design.x_names if c.startswith("WS_x_era_")]
    base["scale"] = {k: float(v) for k, v in design.scale.items()}
    for name, entry in fitted["targets"].items():
        entry["role"] = ("family" if base["role"] == "family" else "context") if name == "beta_S" else "descriptive"
    return {**base, "status": "ok", "targets": fitted["targets"], "diagnostics": fitted["diagnostics"]}


def apply_multiplicity(outcomes: list[dict], q: float = BH_Q) -> dict:
    """Add BH and BY q-values and the decision at ``q`` to ``beta_S`` of the family outcomes (in place). Returns a status block.

    The adjustment needs all ten family p-values; with fewer completed outcomes nothing is added (``complete`` is False).
    """
    family = [o for o in outcomes if o["id"] in FAMILY_IDS]
    ok = [o for o in family if o.get("status") == "ok"]
    for o in family:
        for field in ("q_bh", "q_by", "bh_reject", "by_reject"):
            o.get("targets", {}).get("beta_S", {}).pop(field, None)
    complete = len(family) == len(FAMILY_IDS) and len(ok) > 0  # all ten attempted; a failed outcome would be reported and m reduced
    if complete:
        raw = [o["targets"]["beta_S"]["p_bootstrap"] for o in ok]
        for o, bh, by in zip(ok, benjamini_hochberg(raw), benjamini_yekutieli(raw)):
            entry = o["targets"]["beta_S"]
            entry.update({"q_bh": bh, "q_by": by, "bh_reject": bool(bh <= q), "by_reject": bool(by <= q)})
    return {"complete": complete, "n_family_done": len(ok), "n_family": len(FAMILY_IDS), "m_used": len(ok) if complete else None, "alpha": q,
            "n_bh_reject": int(sum(o["targets"]["beta_S"].get("bh_reject", False) for o in ok)) if complete else None,
            "n_by_reject": int(sum(o["targets"]["beta_S"].get("by_reject", False) for o in ok)) if complete else None}


# ---------------------------------------------------------------------------------------------
# S3: early and unclassified elections, post-election term, from the headline fit
# ---------------------------------------------------------------------------------------------
def run_s3(extract: pd.DataFrame, *, n_boot: int, seed_key: int = m1.SEED_KEY, headline: dict | None = None) -> dict:
    """The headline CAPB fit with the extra named targets; descriptive ``beta_E``, ``beta_U``, ``rho_Post`` with intervals.

    ``headline`` (the parsed ``m1_confirmatory.json``) enables the self-check: the three headline targets of this fit must reproduce the
    committed estimates and intervals (and the ``beta_S`` p-value) to ``SELF_CHECK_TOLERANCE``.
    """
    frame = extract[extract["in_confirmatory"].astype(bool)] if "in_confirmatory" in extract.columns else extract
    sample = frame.sort_values(["eurostat_code", "year"]).reset_index(drop=True)
    design = build_secondary_design(sample, "capb", label="S3 (CAPB)", extra=True)
    fitted = fit_design(design, (*HEADLINE_NAMES, *S3_NAMES), n_boot=n_boot, seed_key=seed_key, p_target="beta_S")
    for name, entry in fitted["targets"].items():
        entry["role"] = "headline reproduction (self-check)" if name == "beta_S" else "descriptive"
    out = {"n_obs": design.n_obs, "n_countries": design.n_clusters, "targets": fitted["targets"], "diagnostics": fitted["diagnostics"],
           "descriptions": {"beta_E": "coefficient of W_E (early-election exposure); early elections are endogenous", "beta_U": "coefficient of W_U (unclassified-election exposure)",
                            "rho_Post": "coefficient of Post (share of the year within 12 months after any election)"}}
    if headline is not None:
        out["self_check"] = self_check(fitted["targets"], headline, n_boot)
    return out


def self_check(targets: dict, headline: dict, n_boot: int) -> dict:
    """Compare beta_S, gamma_B, gamma_W of the S3 fit with ``m1_confirmatory.json``; only meaningful if ``n_boot`` equals the headline B."""
    rows, worst = {}, 0.0
    for name in HEADLINE_NAMES:
        ref = headline["targets"][name]
        diffs = {k: abs(targets[name][k] - ref[k]) for k in ("estimate", "ci_lo", "ci_hi")}
        if name == "beta_S" and ref.get("p_bootstrap") is not None and "p_bootstrap" in targets[name]:
            diffs["p_bootstrap"] = abs(targets[name]["p_bootstrap"] - ref["p_bootstrap"])
        rows[name] = {"max_abs_difference": float(max(diffs.values())), **{f"diff_{k}": float(v) for k, v in diffs.items()}}
        worst = max(worst, rows[name]["max_abs_difference"])
    comparable = int(headline["n_boot"]) == int(n_boot)
    return {"comparable_n_boot": comparable, "headline_n_boot": int(headline["n_boot"]), "max_abs_difference": float(worst),
            "tolerance": SELF_CHECK_TOLERANCE, "passed": bool(comparable and worst <= SELF_CHECK_TOLERANCE), "per_target": rows}


# ---------------------------------------------------------------------------------------------
# Whole analysis
# ---------------------------------------------------------------------------------------------
def file_hashes() -> dict[str, str]:
    """LF-normalised SHA-256 of the files that define the analysis."""
    files = {"secondary.py": Path(__file__).resolve(), "m1.py": Path(m1.__file__).resolve(), "power_variants.py": Path(pv.__file__).resolve(),
             "power.py": Path(power.__file__).resolve(), "docs/secondary_spec.md": SPEC_FILE, "config/registry/secondary.toml": REGISTRY_TOML}
    return {name: m1.file_sha256(path) for name, path in files.items()}


def new_results(*, source: str, n_boot: int, seed_key: int, extract_hash: str | None) -> dict:
    return {
        "source": source, "status": "partial", "n_boot": n_boot, "seed": power.SEED, "seed_key": seed_key, "ci_level": CI_LEVEL, "bh_alpha": BH_Q,
        "family": list(FAMILY_IDS), "min_obs_per_country": MIN_OBS, "versions": m1.library_versions(), "file_hashes": file_hashes(),
        "extract_hash": extract_hash, "estimator": m1.ESTIMATOR_ID, "outcomes": [], "multiplicity": None, "s3": None,
    }


def run_all(extract: pd.DataFrame, *, n_boot: int = m1.BOOTSTRAP_DRAWS_CONFIRMATORY, seed_key: int = m1.SEED_KEY, source: str = SOURCE_SUPPLIED,
            extract_hash: str | None = None, headline: dict | None = None, previous: dict | None = None,
            on_update: Callable[[dict], None] | None = None, specs: Sequence[dict] | None = None, run_s3_block: bool = True) -> dict:
    """Run every outcome (family first, then the descriptive context), then S3. ``on_update`` is called after each step with the partial results.

    ``previous`` (an earlier partial result with the same ``n_boot``, ``seed_key`` and ``extract_hash``) lets an interrupted run resume:
    outcomes with ``status == 'ok'`` in it are reused as they are.
    """
    results = new_results(source=source, n_boot=n_boot, seed_key=seed_key, extract_hash=extract_hash)
    reusable = {}
    if previous is not None and (previous.get("n_boot"), previous.get("seed_key"), previous.get("extract_hash")) == (n_boot, seed_key, extract_hash):
        reusable = {o["id"]: o for o in previous.get("outcomes", []) if o.get("status") == "ok"}
        if previous.get("s3") is not None and run_s3_block:
            results["s3"] = previous["s3"]
    for spec in (specs if specs is not None else (*FAMILY, *CONTEXT)):
        outcome = reusable.get(spec["id"]) or run_outcome(extract, spec, n_boot=n_boot, seed_key=seed_key)
        results["outcomes"].append(outcome)
        results["multiplicity"] = apply_multiplicity(results["outcomes"])
        if on_update is not None:
            on_update(results)
    if run_s3_block and results["s3"] is None:
        results["s3"] = run_s3(extract, n_boot=n_boot, seed_key=seed_key, headline=headline)
        if on_update is not None:
            on_update(results)
    results["status"] = "complete"
    return results


def load_headline(path: Path = HEADLINE_JSON) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run_real(n_boot: int = m1.BOOTSTRAP_DRAWS_CONFIRMATORY, tag_lookup: Callable[[], bool] | None = None, on_update: Callable[[dict], None] | None = None,
             previous: dict | None = None, **loader_kwargs) -> dict:
    """Secondary analysis of the real gold panel. Reads it ONLY through :func:`m1.load_real_panel` (refuses unless the tag exists)."""
    extract, digest = m1.load_real_panel(tag_lookup=tag_lookup, **loader_kwargs)
    return run_all(extract, n_boot=n_boot, source=SOURCE_REAL, extract_hash=digest, headline=load_headline(), previous=previous, on_update=on_update)


# ---------------------------------------------------------------------------------------------
# Reading of the pattern
# ---------------------------------------------------------------------------------------------
def _ok(results: dict, oid: str) -> dict | None:
    for o in results["outcomes"]:
        if o["id"] == oid and o.get("status") == "ok":
            return o
    return None


def _f(value: float, digits: int = 2) -> str:
    return f"{value:+.{digits}f}"


def reading_lines(results: dict, headline: dict | None) -> list[str]:
    """Neutral, quantitative description of the signs and sizes of beta_S across components (associations only)."""
    lines: list[str] = []
    fam = [o for o in results["outcomes"] if o["id"] in FAMILY_IDS and o.get("status") == "ok"]
    if not fam:
        return ["No family outcome has been completed yet."]
    if headline is not None:
        h = headline["targets"]["beta_S"]
        lines.append(f"CAPB result (pre-registered): beta_S = {_f(h['estimate'], 3)} pp of potential GDP, 95% interval [{h['ci_lo']:.3f}, {h['ci_hi']:.3f}]; a lower value is a weaker cyclically adjusted primary balance.")
    weaker = {s["id"]: s["weaker"] for s in (*FAMILY, *CONTEXT)}
    same_dir = [o for o in fam if np.sign(o["targets"]["beta_S"]["estimate"]) == weaker[o["id"]]]
    excl = [o for o in fam if o["targets"]["beta_S"]["ci_lo"] > 0 or o["targets"]["beta_S"]["ci_hi"] < 0]
    opposite = [o["id"] for o in fam if o not in same_dir]
    lines.append(f"Signs: {len(same_dir)} of {len(fam)} family point estimates are in the direction of a weaker budget balance (a lower balance, lower revenue, higher spending); "
                 f"the other {len(opposite)} ({', '.join(opposite) if opposite else 'none'}) point the other way. {len(excl)} of {len(fam)} 95% intervals exclude zero (unadjusted): "
                 f"{', '.join(o['id'] for o in excl) if excl else 'none'}.")
    if headline is not None:
        h = headline["targets"]["beta_S"]
        parts = []
        for oid in ("S1a", "S1b"):
            o = _ok(results, oid)
            if o is not None:
                t = o["targets"]["beta_S"]
                same = np.sign(t["estimate"]) == np.sign(h["estimate"])
                inside = t["ci_lo"] <= h["estimate"] <= t["ci_hi"]
                parts.append(f"{oid} has {'the same' if same else 'the opposite'} sign as the CAPB estimate, a point estimate {abs(t['estimate']) / abs(h['estimate']):.2f} times its size, "
                             f"an interval that {'includes' if t['ci_lo'] <= 0 <= t['ci_hi'] else 'excludes'} zero and {'includes' if inside else 'excludes'} the CAPB estimate")
        if parts:
            lines.append("Consistency with the CAPB result: " + "; ".join(parts) + ".")
        c = _ok(results, "S1c")
        if c is not None:
            t = c["targets"]["beta_S"]
            lines.append(f"The change in CAPB (S1c) is a different quantity from the CAPB level: its beta_S ({_f(t['estimate'], 3)} pp of potential GDP, interval [{t['ci_lo']:.3f}, {t['ci_hi']:.3f}]) "
                         f"is {abs(t['estimate']) / abs(h['estimate']):.1f} times the size of the level estimate. Its sign {'agrees' if np.sign(t['estimate']) == np.sign(h['estimate']) else 'differs'} from the CAPB result; the sizes are not directly comparable.")
    mult = results.get("multiplicity") or {}
    if mult.get("complete"):
        survivors = [o["id"] for o in fam if o["targets"]["beta_S"]["bh_reject"]]
        by_surv = [o["id"] for o in fam if o["targets"]["beta_S"]["by_reject"]]
        lines.append(f"Benjamini-Hochberg at q = {BH_Q}: {mult['n_bh_reject']} of {mult['n_family']} outcomes ({', '.join(survivors) if survivors else 'none'}); "
                     f"Benjamini-Yekutieli: {mult['n_by_reject']} ({', '.join(by_surv) if by_surv else 'none'}).")
    else:
        lines.append(f"The multiplicity adjustment is pending ({mult.get('n_family_done', 0)} of {len(FAMILY_IDS)} family outcomes completed).")
    parts = []
    for oid in ("S1a", "S1b", "S1c"):
        o = _ok(results, oid)
        if o is None:
            continue
        t = o["targets"]["beta_S"]
        parts.append(f"{oid} {_f(t['estimate'])} [{t['ci_lo']:.2f}, {t['ci_hi']:.2f}] ({o['unit']})")
    if parts:
        lines.append("Balance outcomes: " + "; ".join(parts) + ".")
    s1d, s1e = _ok(results, "S1d"), _ok(results, "S1e")
    if s1d and s1e:
        d, e = s1d["targets"]["beta_S"]["estimate"], s1e["targets"]["beta_S"]["estimate"]
        lines.append(f"Spending and revenue: beta_S is {_f(d)} pp of GDP for primary expenditure and {_f(e)} pp of GDP for revenue, so the revenue minus primary expenditure difference is {_f(e - d)} pp. "
                     "This is arithmetic on two separate fits (own samples and weights), not an exact decomposition of S1a.")
    comp = [o for o in fam if o["group"] in ("Social benefits", "COFOG")]
    if comp:
        lines.append("Social components: " + "; ".join(f"{o['id']} {_f(o['targets']['beta_S']['estimate'])} [{o['targets']['beta_S']['ci_lo']:.2f}, {o['targets']['beta_S']['ci_hi']:.2f}]" for o in comp) + " pp of GDP.")
    lines.append("Caveat on comparison with the CAPB result: the outcomes other than the change in CAPB are not cyclically adjusted. A match or a mismatch between their beta_S and the CAPB beta_S therefore mixes policy and cyclical effects and cannot be read as policy composition alone. Everything here is an association with predetermined, not exogenous, election timing.")
    return lines


# ---------------------------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------------------------
def _fmt(value: float | None, digits: int = 3) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def _iv(entry: dict, digits: int = 3) -> str:
    return f"[{entry['ci_lo']:.{digits}f}, {entry['ci_hi']:.{digits}f}]"


def render_markdown(results: dict, headline: dict | None = None) -> str:
    """Markdown report. Rows of failed outcomes are listed with the reason; the BH/BY columns show 'pending' until all ten family outcomes are in."""
    mult = results.get("multiplicity") or {}
    complete = bool(mult.get("complete"))
    lines = [
        "# Secondary outcomes (pre-specified, `docs/secondary_spec.md`)",
        "",
        f"Status: **{results['status']}** ({mult.get('n_family_done', 0)} of {len(FAMILY_IDS)} family outcomes completed). Estimator: {results['estimator']}, re-estimated on each outcome's own sample. Source: `{results['source']}`.",
        "Associations only: scheduled elections are predetermined, not exogenous. Units: pp of GDP, except S1c and the cyclical component (pp of potential GDP). beta_S is the coefficient of a full year (W_S = 1) of pre-election exposure to a scheduled election, at the sample-average moderator and era composition. The outcomes are not cyclically adjusted (S1c excepted), so a comparison with the CAPB result mixes policy and cyclical effects.",
        "",
        f"## beta_S for the ten family outcomes (Benjamini-Hochberg at q = {BH_Q} over S1a-S1g-3; Benjamini-Yekutieli beside it)",
        "",
        "| ID | outcome | unit | N | countries | years | beta_S | 95% bootstrap-t interval | p (wild-cluster bootstrap-t) | BH q | BY q | BH decision (q <= 0.05) | interval excludes 0 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for spec in FAMILY:
        o = next((x for x in results["outcomes"] if x["id"] == spec["id"]), None)
        if o is None:
            lines.append(f"| {spec['id']} | {spec['label']} | {spec['unit']} | - | - | - | not yet run | | | | | | |")
            continue
        if o.get("status") != "ok":
            lines.append(f"| {o['id']} | {o['label']} | {o['unit']} | {o.get('n_obs', '-')} | - | - | NOT RUN: {o.get('error')} | | | | | | |")
            continue
        t = o["targets"]["beta_S"]
        decision = ("reject" if t["bh_reject"] else "no rejection") if complete else "pending"
        lines.append(f"| {o['id']} | {o['label']} | {o['unit']} | {o['n_obs']} | {o['n_countries']} | {o['year_min']}-{o['year_max']} | {t['estimate']:+.4f} | {_iv(t, 4)} | {t['p_bootstrap']:.4f} | "
                     f"{_fmt(t.get('q_bh'), 4) if complete else 'pending'} | {_fmt(t.get('q_by'), 4) if complete else 'pending'} | {decision} | {'yes' if (t['ci_lo'] > 0 or t['ci_hi'] < 0) else 'no'} |")
    if complete:
        lines += ["", f"BH decision at q = {BH_Q}: {mult['n_bh_reject']} of {mult['n_family']} outcomes. BY (conservative check; does not change the pre-registered BH conclusion): {mult['n_by_reject']} of {mult['n_family']}."]
    lines += ["", "## Descriptive context outcomes (same model; estimate and interval only; outside the multiplicity family; no p-values or q-values)", "",
              "| outcome | unit | N | countries | years | beta_S | 95% bootstrap-t interval |", "|---|---|---|---|---|---|---|"]
    for spec in CONTEXT:
        o = next((x for x in results["outcomes"] if x["id"] == spec["id"]), None)
        if o is None:
            lines.append(f"| {spec['label']} | {spec['unit']} | - | - | - | not yet run | |")
        elif o.get("status") != "ok":
            lines.append(f"| {o['label']} | {o['unit']} | {o.get('n_obs', '-')} | - | - | NOT RUN: {o.get('error')} | |")
        else:
            t = o["targets"]["beta_S"]
            lines.append(f"| {o['label']} | {o['unit']} | {o['n_obs']} | {o['n_countries']} | {o['year_min']}-{o['year_max']} | {t['estimate']:+.4f} | {_iv(t, 4)} |")
    lines += ["", "## gamma_B and gamma_W (descriptive: estimate and interval only, per +1 SD of the component of lagged OLDDEP1 on that outcome's sample)", "",
              "| ID | gamma_B | 95% interval | gamma_W | 95% interval |", "|---|---|---|---|---|"]
    for o in results["outcomes"]:
        if o.get("status") == "ok":
            b, w = o["targets"].get("gamma_B"), o["targets"].get("gamma_W")
            lines.append(f"| {o['id']} | {b['estimate']:+.4f} | {_iv(b, 4)} | {w['estimate']:+.4f} | {_iv(w, 4)} |" if b and w else f"| {o['id']} | not identified | | | |")
    lines += ["", "## Fit diagnostics and sample notes", "",
              "| ID | rho (Nickell-corrected) | country residual SD: min (country) | median | max (country) | runs / countries with a gap | countries not entering (usable obs) | regressors dropped |",
              "|---|---|---|---|---|---|---|---|"]
    for o in results["outcomes"]:
        if o.get("status") != "ok":
            continue
        d = o["diagnostics"]
        excluded = ", ".join(f"{k} ({v})" for k, v in o["countries_excluded"].items()) or "none"
        lines.append(f"| {o['id']} | {d['rho_nickell']:.3f} | {d['resid_sd_min']:.3f} ({d['resid_sd_min_country']}) | {d['resid_sd_median']:.3f} | {d['resid_sd_max']:.3f} ({d['resid_sd_max_country']}) | "
                     f"{o['n_runs']} / {o['countries_with_gaps']} | {excluded} | {', '.join(o['regressors_dropped_constant']) or 'none'} |")
    capped = [o["id"] for o in results["outcomes"] if o.get("status") == "ok" and o["diagnostics"]["rho_nickell"] >= pv.RHO_CAP - 1e-9]
    persistent = [o["id"] for o in results["outcomes"] if o.get("status") == "ok" and o["diagnostics"]["rho_nickell"] >= 0.85]
    lines += ["", f"Notes: the Nickell-corrected persistence is capped at {pv.RHO_CAP} by the estimator; at the cap: {', '.join(capped) if capped else 'none'}. "
              f"Outcomes with persistence of at least 0.85 (spending-share series are close to unit-root behaviour): {', '.join(persistent) if persistent else 'none'}; "
              "the AR(1) correction and the bootstrap were not validated at such persistence (the pre-registered power study used rho of about 0.69), so those intervals deserve less weight. "
              "Country residual SDs are those of the first-stage fit; the WLS weights are their inverse squares."]
    s3 = results.get("s3")
    lines += ["", "## S3: early, unclassified and post-election terms in the CAPB fit (descriptive; no test, no multiplicity adjustment)", ""]
    if s3 is None:
        lines.append("Not yet run.")
    else:
        lines += [f"Same fit as the headline (N = {s3['n_obs']}, {s3['n_countries']} countries; pp of potential GDP). Early elections are endogenous.", "",
                  "| term | meaning | estimate | 95% bootstrap-t interval |", "|---|---|---|---|"]
        for name in S3_NAMES:
            if name in s3["targets"]:
                t = s3["targets"][name]
                lines.append(f"| {name} | {s3['descriptions'][name]} | {t['estimate']:+.4f} | {_iv(t, 4)} |")
        sc = s3.get("self_check")
        if sc is not None:
            lines += ["", f"Self-check against `m1_confirmatory.json` (beta_S, gamma_B, gamma_W estimates and intervals, beta_S p): max absolute difference {sc['max_abs_difference']:.2e} (tolerance {sc['tolerance']:.0e}); "
                      f"headline B = {sc['headline_n_boot']}, this run B = {results['n_boot']}; **{'PASSED' if sc['passed'] else 'NOT PASSED'}**."]
    lines += ["", "## Reading of the pattern across components", ""]
    lines += [f"* {line}" for line in reading_lines(results, headline)]
    lines += ["", "## Provenance", "",
              f"* seed {results['seed']}, bootstrap seed key {results['seed_key']}, B = {results['n_boot']} (Rademacher weights, whole feasible procedure re-estimated in every bootstrap sample); a country needs at least {results['min_obs_per_country']} usable observations",
              f"* versions: numpy {results['versions']['numpy']}, pandas {results['versions']['pandas']}, scipy {results['versions']['scipy']}",
              f"* gold extract hash: `{results['extract_hash']}`"]
    lines += [f"* {name} (SHA-256, LF-normalised): `{digest}`" for name, digest in results["file_hashes"].items()]
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------
# Forest plot
# ---------------------------------------------------------------------------------------------
def forest_plot(results: dict, path: Path, headline: dict | None = None) -> Path:
    """Forest plot of beta_S (95% interval) per outcome in pp of GDP; filled markers = BH q <= 0.05; 300 dpi; zero line; source line."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows: list[tuple[str, dict | None, str]] = []  # (label, entry, kind)
    if headline is not None:
        rows.append(("CAPB, headline (pp of potential GDP)", headline["targets"]["beta_S"], "headline"))
        rows.append(("", None, "gap"))
    groups = []
    for spec in FAMILY:
        if spec["group"] not in groups:
            groups.append(spec["group"])
    mult = results.get("multiplicity") or {}
    for group in groups:
        rows.append((group, None, "group"))
        for spec in (s for s in FAMILY if s["group"] == group):
            o = _ok(results, spec["id"])
            unit_note = " (pp pot. GDP)" if "potential" in spec["unit"] else ""
            rows.append((f"{spec['id']}  {spec['label']}{unit_note}", o["targets"]["beta_S"] if o else None, "family"))
    rows.append(("Descriptive context (outside the family; no q-values)", None, "group"))
    for spec in CONTEXT:
        o = _ok(results, spec["id"])
        unit_note = " (pp pot. GDP)" if "potential" in spec["unit"] else ""
        rows.append((f"{spec['label']}{unit_note}", o["targets"]["beta_S"] if o else None, "context"))
    height = 0.34 * len(rows) + 1.6
    fig, ax = plt.subplots(figsize=(9.6, height))
    ink, muted, accent = "#1f2933", "#7b8794", "#b3261e"
    for i, (label, entry, kind) in enumerate(rows):
        y = len(rows) - 1 - i
        if kind == "group":
            ax.text(-0.01, y, label, transform=ax.get_yaxis_transform(), ha="right", va="center", fontsize=8.5, fontweight="bold", color=ink)
            continue
        if kind == "gap":
            continue
        ax.text(-0.01, y, label, transform=ax.get_yaxis_transform(), ha="right", va="center", fontsize=8.5, color=ink if kind != "context" else muted)
        if entry is None:
            continue
        reject = bool(mult.get("complete")) and entry.get("bh_reject", False)
        colour = accent if kind == "headline" else (ink if kind == "family" else muted)
        ax.plot([entry["ci_lo"], entry["ci_hi"]], [y, y], color=colour, lw=1.6, solid_capstyle="butt")
        filled = kind == "headline" or (kind == "family" and reject)
        ax.plot([entry["estimate"]], [y], "o", ms=6.5, mfc=colour if filled else "white", mec=colour, mew=1.4)
    ax.axvline(0.0, color=muted, lw=1.0, ls="--", zorder=0)
    ax.set_yticks([])
    ax.set_ylim(-0.8, len(rows) - 0.2)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.set_xlabel("beta_S: association with a full year of pre-election exposure to a scheduled election\n(pp of GDP; pp of potential GDP where marked)", fontsize=9)
    fig.suptitle("Secondary outcomes: beta_S with 95% bootstrap-t intervals\nFilled marker: Benjamini-Hochberg q <= 0.05 over the ten family outcomes; hollow: not rejected", x=0.01, ha="left", fontsize=10, color=ink)
    fig.text(0.01, 0.005, SOURCE_LINE + ". Outcomes other than the change in CAPB are not cyclically adjusted.", fontsize=7, color=muted, ha="left", va="bottom")
    fig.subplots_adjust(left=0.47, right=0.97, top=0.9, bottom=0.12)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=300)
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------------------------
# Output (guarded like m1.write_results)
# ---------------------------------------------------------------------------------------------
def to_json(results: dict) -> str:
    return json.dumps(results, indent=2, allow_nan=False) + "\n"


def write_results(results: dict, out_dir: Path | None = None, fig_dir: Path | None = None, tag_lookup: Callable[[], bool] | None = None,
                  headline: dict | None = None, figure: bool = True) -> list[Path]:
    """Write ``secondary.json``, ``secondary.md`` and the forest plot. The default folders need real-panel results AND the tag (as in ``m1``)."""
    default = out_dir is None or Path(out_dir).resolve() == RESULTS_DIR.resolve()
    if default:
        if results["source"] != SOURCE_REAL:
            raise m1.ResultsNotAllowed("only results from the real gold panel may be written to reports/results")
        m1.require_preregistration_tag(tag_lookup)
    target = RESULTS_DIR if out_dir is None else Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    paths = [target / f"{RESULT_STEM}.json", target / f"{RESULT_STEM}.md"]
    paths[0].write_text(to_json(results), encoding="utf-8", newline="\n")
    paths[1].write_text(render_markdown(results, headline), encoding="utf-8", newline="\n")
    if figure and any(o.get("status") == "ok" for o in results["outcomes"]):
        paths.append(forest_plot(results, (FIGURES_DIR if fig_dir is None else Path(fig_dir)) / FIGURE_NAME, headline))
    return paths


def main(argv: list[str] | None = None) -> int:
    """``python src/models/py/secondary.py``: run the secondary analysis on the real panel, updating the result files after every outcome."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report whether the pre-registration tag exists and exit")
    parser.add_argument("--n-boot", type=int, default=m1.BOOTSTRAP_DRAWS_CONFIRMATORY)
    parser.add_argument("--fresh", action="store_true", help="ignore an earlier partial secondary.json instead of resuming from it")
    args = parser.parse_args(argv)
    if args.check:
        present = m1.tag_exists()
        print(f"tag {m1.PREREG_TAG}: {'present' if present else 'ABSENT (the real outcome must not be analysed)'}")
        return 0 if present else 1
    headline = load_headline()
    previous = None
    json_path = RESULTS_DIR / f"{RESULT_STEM}.json"
    if json_path.exists() and not args.fresh:
        previous = json.loads(json_path.read_text(encoding="utf-8"))

    def update(partial: dict) -> None:
        write_results(partial, headline=headline, figure=False)
        print(f"updated: {len([o for o in partial['outcomes'] if o.get('status') == 'ok'])} outcomes ok, {len(partial['outcomes'])} attempted", flush=True)

    try:
        results = run_real(n_boot=args.n_boot, on_update=update, previous=previous)
    except m1.PreregistrationTagMissing as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 1
    for path in write_results(results, headline=headline):
        print(f"written {path.relative_to(PROJECT_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
