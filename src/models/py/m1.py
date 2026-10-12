"""M3 confirmatory runner for model M1 (pre-registered analysis, estimator V7).

NOTHING IN THIS MODULE IS RUN ON THE REAL OUTCOME BEFORE THE FREEZE. The real gold panel is read (including its ``capb``
column) only by :func:`run_real`, which first calls :func:`require_preregistration_tag` and raises
:class:`PreregistrationTagMissing` if the git tag ``preregistration-v1`` does not exist. :func:`run_m1` itself works on any
DataFrame (tests use synthetic outcomes with a known injected effect). Output files are written to ``reports/results`` only
for results that came from the real gold panel and only while the tag exists (:func:`write_results`).

Model and estimator
-------------------
M1 (``config/registry/confirmatory.toml``), estimated by V7 = ``GlsEstimator(design, wls=True, ar1=True)`` on
``build_variant_design(frame, 'M1', era=True, control_names=())`` (Gate 3d): feasible WLS (``1 / sigma_i^2`` from the first-stage
residuals of the very data set being fitted) followed by AR(1) feasible GLS (Prais-Winsten, Nickell-corrected ``rho``), with
country and year fixed effects, no controls. Regressors (rows sorted by country, then year; a column with no variation, ``W_D`` on
the final sample, is dropped):

* ``W_S, W_E, W_D, W_U, Post``: the five exposure columns as in the gold panel, in [0, 1] (fraction of the year inside a
  12-month pre-election window of the given class; ``Post`` = 12 months after any election). ``beta_S`` is the coefficient of ``W_S``.
* ``A_lag`` = ``z``: ``olddep1_lag`` (OLDDEP1 at t-1) standardised on the estimation sample, mean 0, SD 1 (``ddof = 0``).
* ``WS_x_between`` = ``W_S * abar_i / sd(abar)`` with ``abar_i`` the country mean of ``z`` over the estimation sample. ``gamma_B`` is
  its coefficient: change in the ``W_S`` association per +1 SD of the BETWEEN component (cross-country; possibly confounded).
* ``WS_x_within`` = ``W_S * (z - abar_i) / sd(z - abar)``. ``gamma_W`` is its coefficient: change per +1 SD of the WITHIN component.
* ``WS_x_era_2008_2015`` and ``WS_x_era_2016_2021`` = ``W_S * (D_e - m_e)`` with ``D_e`` the era dummy and ``m_e = sum(W_S D_e) /
  sum(W_S)`` (exposure-weighted mean), so the reference era 1995-2007 has no term and ``beta_S`` is the average association.
* Fixed effects: country dummies and year dummies (first year dropped).

Estimates are in percentage points of potential GDP (CAPB, surplus positive); ``gamma_B`` and ``gamma_W`` are per +1 SD.

Inference
---------
* P-values (``beta_S``, ``gamma_B`` only): null-imposed wild-cluster bootstrap-t by country, Rademacher weights,
  ``B = BOOTSTRAP_DRAWS_CONFIRMATORY = 9999`` draws, the whole feasible procedure (first-stage residuals, country weights, Nickell-
  corrected rho) re-estimated in every bootstrap sample, ``p = (1 + #{|t*| >= |t|}) / (B + 1)`` via
  ``power_variants.wild_bootstrap_pvalues`` with ``seed_key = 42`` (weights from ``power.make_rng(PURPOSE_WCB_WEIGHTS, 42, 0)``).
* Intervals (all three targets): 95 per cent bootstrap-t percentile intervals from an UNRESTRICTED wild-cluster bootstrap
  (``y* = fitted_full + v * residual_full`` with the same Rademacher weights and B), ``t* = (b* - b) / se*`` (``se*`` is the CR1
  standard error of the feasible procedure in the bootstrap sample), interval ``[b - q_0.975(t*) se, b - q_0.025(t*) se]`` with
  linear-interpolation quantiles.
* CR1 estimate, standard error, t(G-1) = t(26) p-value (confirmatory targets only) and interval are reported for transparency only:
  ``not valid for this estimator (over-rejects)`` (Gate 3d: about 8-10 per cent at nominal 5).
* Multiplicity: Holm over EXACTLY the two tests {beta_S, gamma_B} (:func:`holm`), familywise alpha 0.05. ``gamma_W`` is descriptive
  ('not powered', decision D-C): an estimate and an interval, no p-value, no adjustment, no classification, no significance claim.
* Interval reading (decision D-A, ``[interpretation] smallest_effect_size_pp``): :func:`classify_interval`.

Randomness: ``power.make_rng`` key scheme, master seed 42. Language: associations only (scheduled elections are predetermined, not
exogenous; the ageing interactions are never given a causal reading).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tomllib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
from scipy import stats

_SRC = Path(__file__).resolve().parents[2]
for _sub in ("evaluate", "normalize", "features"):
    sys.path.insert(0, str(_SRC / _sub))
import power  # noqa: E402
import power_variants as pv  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_TOML = PROJECT_ROOT / "config" / "registry" / "confirmatory.toml"
GOLD_PARQUET = PROJECT_ROOT / "data" / "processed" / "gold" / "panel_country_year.parquet"
GOLD_HASH_FILE = PROJECT_ROOT / "data" / "processed" / "gold" / "panel_country_year.sha256"
RESULTS_DIR = PROJECT_ROOT / "reports" / "results"
RESULT_STEM = "m1_confirmatory"
CODE_FILES = {"m1.py": Path(__file__).resolve(), "power_variants.py": _SRC / "evaluate" / "power_variants.py"}
DEPENDENCY_FILES = {"power.py": _SRC / "evaluate" / "power.py"}  # reported beside the code hash, not part of it

PREREG_TAG = "preregistration-v1"
BOOTSTRAP_DRAWS_CONFIRMATORY = 9_999  # B; (B + 1) * 0.05 = 500 is an integer, so the bootstrap test is exact under symmetry
SEED_KEY = power.SEED  # 42: seed_key of wild_bootstrap_pvalues and of the interval bootstrap
CI_LEVEL = 0.95
MODEL_ID = "M1"
ESTIMATOR_ID = "V7: GlsEstimator(wls=True, ar1=True) on M1 with centred era terms, no controls"
CONFIRMATORY_TARGETS = ("beta_S", "gamma_B")  # the Holm family (hypotheses H1, H2B)
DESCRIPTIVE_TARGETS = ("gamma_W",)  # H2W: estimate and interval only
ALL_TARGETS = CONFIRMATORY_TARGETS + DESCRIPTIVE_TARGETS
REQUIRED_COLUMNS = ("capb", "W_S", "W_E", "W_D", "W_U", "Post", "olddep1_lag", "eurostat_code", "year")
EXPECTED_ROWS, EXPECTED_COUNTRIES = 715, 27  # Gate 3a sample (contract), checked on the real panel only
SOURCE_REAL, SOURCE_SUPPLIED = "real_gold_panel", "supplied_dataframe"
CR1_NOTE = "not valid for this estimator (over-rejects)"
TARGET_SCALING = {
    "beta_S": "coefficient of W_S (pp of potential GDP per unit of exposure; average over eras)",
    "gamma_B": "coefficient of W_S x between component of standardised lagged OLDDEP1, per +1 SD of that component",
    "gamma_W": "coefficient of W_S x within component of standardised lagged OLDDEP1, per +1 SD of that component",
}
LABEL_EXCLUDES, LABEL_EQUIVALENT, LABEL_INCONCLUSIVE = "excludes zero", "equivalent within +-sesoi", "inconclusive"


class PreregistrationTagMissing(RuntimeError):
    """The git tag ``preregistration-v1`` does not exist: the real outcome must not be touched."""


class ResultsNotAllowed(RuntimeError):
    """Results may be written to ``reports/results`` only for the real gold panel and only while the tag exists."""


# ---------------------------------------------------------------------------------------------
# Freeze guard
# ---------------------------------------------------------------------------------------------
def tag_exists(tag: str = PREREG_TAG, repo: Path | None = None) -> bool:
    """True if ``git tag --list <tag>`` run in ``repo`` (default: the project root) prints exactly that tag.

    Read-only; any git failure counts as absent. The default is resolved at call time so that tests can redirect ``PROJECT_ROOT``.
    """
    try:
        done = subprocess.run(["git", "-C", str(PROJECT_ROOT if repo is None else repo), "tag", "--list", tag], capture_output=True, text=True, check=False, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0 and tag in done.stdout.split()


def require_preregistration_tag(tag_lookup: Callable[[], bool] | None = None) -> None:
    """Raise :class:`PreregistrationTagMissing` unless the pre-registration tag exists (``tag_lookup`` is injectable for tests)."""
    present = tag_exists() if tag_lookup is None else tag_lookup()
    if not present:
        raise PreregistrationTagMissing(f"git tag {PREREG_TAG!r} not found: refusing to read or analyse the real outcome before the freeze")


# ---------------------------------------------------------------------------------------------
# Multiplicity and interval reading
# ---------------------------------------------------------------------------------------------
def holm(pvalues: Sequence[float]) -> list[float]:
    """Holm (1979) step-down adjusted p-values, in the input order.

    Sorted ascending ``p_(1) <= ... <= p_(m)``: ``adj_(j) = min(1, max_{k <= j} (m - k + 1) p_(k))``. Rejecting where
    ``adj <= alpha`` controls the familywise error rate at ``alpha``.
    """
    p = np.asarray(pvalues, float)
    m = len(p)
    if m == 0:
        return []
    if np.any((p < 0) | (p > 1)) or np.any(np.isnan(p)):
        raise ValueError("p-values must lie in [0, 1]")
    order = np.argsort(p, kind="stable")
    scaled = (m - np.arange(m)) * p[order]
    adjusted = np.minimum(1.0, np.maximum.accumulate(scaled))
    out = np.empty(m)
    out[order] = adjusted
    return [float(v) for v in out]


def interval_flags(lo: float, hi: float, sesoi: float) -> tuple[bool, bool]:
    """``(excludes_zero, equivalent)``: zero lies outside ``[lo, hi]``; ``[lo, hi]`` lies inside ``[-sesoi, +sesoi]`` (inclusive)."""
    if not (np.isfinite(lo) and np.isfinite(hi)) or lo > hi:
        raise ValueError(f"invalid interval [{lo}, {hi}]")
    if not sesoi > 0:
        raise ValueError("sesoi must be positive")
    return bool(lo > 0 or hi < 0), bool(lo >= -sesoi and hi <= sesoi)


def classify_interval(lo: float, hi: float, sesoi: float) -> str:
    """Reading of an interval (decision D-A): 'excludes zero', 'equivalent within +-sesoi' or 'inconclusive'.

    The two flags of :func:`interval_flags` are not exclusive: a narrow interval away from zero (for example [0.1, 0.3] with
    ``sesoi`` 0.5) excludes zero AND lies inside +-sesoi. PRECEDENCE: 'excludes zero' first, then 'equivalent within +-sesoi',
    otherwise 'inconclusive' (the order in which the pre-registration lists the readings). The runner reports BOTH flags
    beside the label so that no information is lost. Wide intervals that straddle zero and exceed +-sesoi are 'inconclusive'.
    """
    excludes, equivalent = interval_flags(lo, hi, sesoi)
    if excludes:
        return LABEL_EXCLUDES
    return LABEL_EQUIVALENT if equivalent else LABEL_INCONCLUSIVE


# ---------------------------------------------------------------------------------------------
# Registry, hashes, versions
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Interpretation:
    """``[interpretation]`` table of the confirmatory registry."""

    sesoi_pp: float
    status: str


def load_interpretation(path: Path = REGISTRY_TOML) -> Interpretation:
    """Read the smallest effect size of interest (pp) and its status from the registry."""
    with path.open("rb") as handle:
        table = tomllib.load(handle)["interpretation"]
    return Interpretation(sesoi_pp=float(table["smallest_effect_size_pp"]), status=str(table["status"]))


def file_sha256(path: Path) -> str:
    """SHA-256 of a text file with CRLF/CR line endings normalised to LF (working copies on Windows may be CRLF)."""
    data = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(data).hexdigest()


def code_hashes() -> dict[str, str]:
    """Per-file hashes of ``m1.py`` and ``power_variants.py``, the combined ``code_hash`` and ``power.py`` (dependency)."""
    files = {name: file_sha256(path) for name, path in CODE_FILES.items()}
    combined = hashlib.sha256("\n".join(f"{name}:{files[name]}" for name in sorted(files)).encode("utf-8")).hexdigest()
    return {**files, "code_hash": combined, **{f"dependency:{name}": file_sha256(path) for name, path in DEPENDENCY_FILES.items()}}


def library_versions() -> dict[str, str]:
    """Versions of numpy, pandas and scipy."""
    return {"numpy": np.__version__, "pandas": pd.__version__, "scipy": scipy.__version__}


# ---------------------------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class TargetResult:
    """One target: estimate, bootstrap-t interval, (confirmatory only) p-values and reading, CR1 transparency block."""

    name: str
    role: str  # 'confirmatory' (Holm family) or 'descriptive'
    scaling: str
    estimate: float
    ci_lo: float  # unrestricted wild-cluster bootstrap-t percentile interval
    ci_hi: float
    p_bootstrap: float | None  # null-imposed wild-cluster bootstrap-t; None for descriptive targets
    p_holm: float | None
    excludes_zero: bool | None
    equivalent_within_sesoi: bool | None
    reading: str | None
    cr1_se: float
    cr1_p: float | None
    cr1_ci_lo: float
    cr1_ci_hi: float
    cr1_note: str = CR1_NOTE


@dataclass(frozen=True)
class M1Results:
    """Everything the confirmatory run reports (and nothing else)."""

    source: str
    n_obs: int
    n_countries: int
    estimator: str
    registry_hash: str
    code_hash: str
    code_hashes: dict[str, str]
    seed: int
    seed_key: int
    n_boot: int
    versions: dict[str, str]
    extract_hash: str | None
    sesoi_pp: float
    sesoi_status: str
    holm_family: tuple[str, ...]
    targets: dict[str, TargetResult]

    def to_dict(self) -> dict:
        """Plain (JSON-serialisable) dictionary."""
        out = {k: v for k, v in self.__dict__.items() if k not in ("targets", "holm_family")}
        out["holm_family"] = list(self.holm_family)
        out["targets"] = {name: dict(t.__dict__) for name, t in self.targets.items()}
        return out


# ---------------------------------------------------------------------------------------------
# Estimation
# ---------------------------------------------------------------------------------------------
def validate_frame(frame: pd.DataFrame) -> None:
    """Columns present, no missing values in them, unique (country, year) keys."""
    missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(f"missing columns {missing}")
    if frame[list(REQUIRED_COLUMNS)].isna().any().any():
        raise ValueError("missing values in the confirmatory columns")
    if frame.duplicated(["eurostat_code", "year"]).any():
        raise ValueError("duplicated (eurostat_code, year) keys")


def unrestricted_bootstrap_t(est: pv.GlsEstimator, y: np.ndarray, targets: Sequence[str], n_boot: int, seed_key: int) -> dict[str, np.ndarray]:
    """Studentised statistics ``t* = (b* - b) / se*`` of an UNRESTRICTED wild-cluster bootstrap (Rademacher weights).

    The outcome ``y`` is an (N,) vector in design order. The full-model residuals and fitted values come from
    ``est.fit(y, ..., want_resid=True)``; the bootstrap outcomes are ``fitted + v * residual`` with the cluster weights of
    chunk 0 of ``power.make_rng(PURPOSE_WCB_WEIGHTS, seed_key, .)`` (the same weights as the null-imposed bootstrap p-values),
    and the whole feasible procedure is re-estimated for every bootstrap outcome.
    """
    design = est.design
    y2 = y[:, None]
    fit, resid = est.fit(y2, list(targets), want_resid=True)
    fitted = y2 - resid
    v = power.bootstrap_weights(power.make_rng(power.PURPOSE_WCB_WEIGHTS, seed_key, 0), (1, design.n_clusters, n_boot), "rademacher")[0]
    star = fitted + v[design.country_idx, :] * resid
    fit_star = est.fit(star, list(targets))
    out = {}
    for name in targets:
        t_star = (fit_star[name][0] - fit[name][0][0]) / fit_star[name][1]
        if not np.all(np.isfinite(t_star)):
            raise FloatingPointError(f"non-finite bootstrap t statistics for {name}")
        out[name] = t_star
    return out


def run_m1(frame: pd.DataFrame, *, n_boot: int = BOOTSTRAP_DRAWS_CONFIRMATORY, seed_key: int = SEED_KEY, sesoi: Interpretation | None = None,
           extract_hash: str | None = None, source: str = SOURCE_SUPPLIED) -> M1Results:
    """Pre-registered M1 / V7 analysis on a DataFrame (``REQUIRED_COLUMNS``; the real panel only through :func:`run_real`).

    ``n_boot`` is a parameter so that tests can use a modest value; the confirmatory default is 9,999.
    """
    validate_frame(frame)
    reading = load_interpretation() if sesoi is None else sesoi
    design = pv.build_variant_design(frame, MODEL_ID, era=True, control_names=())
    est = pv.GlsEstimator(design, wls=True, ar1=True)
    y = design.y
    fit = est.fit(y, list(ALL_TARGETS))
    estimate = {t: float(fit[t][0][0]) for t in ALL_TARGETS}
    cr1_se = {t: float(fit[t][1][0]) for t in ALL_TARGETS}

    p_boot = {t: float(pv.wild_bootstrap_pvalues(est, t, y[:, None], weights="rademacher", n_boot=n_boot, seed_key=seed_key)[0]) for t in CONFIRMATORY_TARGETS}
    p_adj = dict(zip(CONFIRMATORY_TARGETS, holm([p_boot[t] for t in CONFIRMATORY_TARGETS])))

    t_star = unrestricted_bootstrap_t(est, y, ALL_TARGETS, n_boot, seed_key)
    tail = (1.0 - CI_LEVEL) / 2.0
    targets: dict[str, TargetResult] = {}
    for name in ALL_TARGETS:
        q_lo, q_hi = np.quantile(t_star[name], [tail, 1.0 - tail])
        lo, hi = estimate[name] - float(q_hi) * cr1_se[name], estimate[name] - float(q_lo) * cr1_se[name]
        confirmatory = name in CONFIRMATORY_TARGETS
        flags = interval_flags(lo, hi, reading.sesoi_pp) if confirmatory else (None, None)
        targets[name] = TargetResult(
            name=name, role="confirmatory" if confirmatory else "descriptive", scaling=TARGET_SCALING[name], estimate=estimate[name], ci_lo=float(lo), ci_hi=float(hi),
            p_bootstrap=p_boot[name] if confirmatory else None, p_holm=p_adj[name] if confirmatory else None,
            excludes_zero=flags[0], equivalent_within_sesoi=flags[1], reading=classify_interval(lo, hi, reading.sesoi_pp) if confirmatory else None,
            cr1_se=cr1_se[name], cr1_p=float(2 * stats.t.sf(abs(estimate[name] / cr1_se[name]), design.n_clusters - 1)) if confirmatory else None,
            cr1_ci_lo=estimate[name] - design.t_crit * cr1_se[name], cr1_ci_hi=estimate[name] + design.t_crit * cr1_se[name],
        )
    hashes = code_hashes()
    return M1Results(
        source=source, n_obs=design.n_obs, n_countries=design.n_clusters, estimator=ESTIMATOR_ID, registry_hash=file_sha256(REGISTRY_TOML),
        code_hash=hashes["code_hash"], code_hashes=hashes, seed=power.SEED, seed_key=seed_key, n_boot=n_boot, versions=library_versions(),
        extract_hash=extract_hash, sesoi_pp=reading.sesoi_pp, sesoi_status=reading.status, holm_family=CONFIRMATORY_TARGETS, targets=targets,
    )


# ---------------------------------------------------------------------------------------------
# The real panel (guarded)
# ---------------------------------------------------------------------------------------------
def load_real_panel(path: Path = GOLD_PARQUET, hash_file: Path = GOLD_HASH_FILE, tag_lookup: Callable[[], bool] | None = None) -> tuple[pd.DataFrame, str]:
    """Confirmatory extract of the gold panel and its recomputed extract hash. The tag check comes BEFORE any file is opened.

    Raises :class:`PreregistrationTagMissing` without the tag; raises ``ValueError`` if the recomputed hash differs from the
    committed hash file or the extract is not 715 rows x 27 countries.
    """
    require_preregistration_tag(tag_lookup)
    import panel as panel_module  # noqa: E402  (lazy: heavy import, and kept out of any pre-freeze code path)

    full = pd.read_parquet(path)
    digest = panel_module.extract_hash(full)
    recorded = hash_file.read_text(encoding="utf-8").split()[0]
    if digest != recorded:
        raise ValueError(f"gold extract hash {digest} differs from the recorded {recorded}")
    extract = full[full["in_confirmatory"].astype(bool)].reset_index(drop=True)
    if len(extract) != EXPECTED_ROWS or extract["eurostat_code"].nunique() != EXPECTED_COUNTRIES:
        raise ValueError(f"extract has {len(extract)} rows and {extract['eurostat_code'].nunique()} countries, expected {EXPECTED_ROWS} and {EXPECTED_COUNTRIES}")
    return extract, digest


def run_real(n_boot: int = BOOTSTRAP_DRAWS_CONFIRMATORY, tag_lookup: Callable[[], bool] | None = None, path: Path = GOLD_PARQUET,
             hash_file: Path = GOLD_HASH_FILE) -> M1Results:
    """Confirmatory analysis of the real gold panel. Refuses (before reading anything) unless the tag ``preregistration-v1`` exists."""
    extract, digest = load_real_panel(path, hash_file, tag_lookup=tag_lookup)
    return run_m1(extract, n_boot=n_boot, extract_hash=digest, source=SOURCE_REAL)


# ---------------------------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------------------------
def _fmt(value: float | None, digits: int = 4) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def render_markdown(results: M1Results) -> str:
    """Markdown report (associations only)."""
    lines = [
        "# M1 confirmatory results",
        "",
        f"Estimator: {results.estimator}. N = {results.n_obs} country-years, {results.n_countries} countries. Source: `{results.source}`.",
        "Results are associations; scheduled elections are predetermined, not exogenous. Estimates are in pp of potential GDP (interactions per +1 SD of the component).",
        "",
        f"Interval reading: smallest effect size of interest {results.sesoi_pp} pp (registry status {results.sesoi_status}). Label precedence: excludes zero, then equivalent within +-sesoi, then inconclusive; both flags are shown.",
        "",
        "## Confirmatory family (Holm over beta_S and gamma_B)",
        "",
        "| target | estimate | 95% bootstrap-t interval | p (wild-cluster bootstrap-t) | p (Holm) | excludes zero | within +-sesoi | reading |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name in results.holm_family:
        t = results.targets[name]
        lines.append(f"| {name} | {_fmt(t.estimate)} | [{_fmt(t.ci_lo)}, {_fmt(t.ci_hi)}] | {_fmt(t.p_bootstrap, 5)} | {_fmt(t.p_holm, 5)} | {t.excludes_zero} | {t.equivalent_within_sesoi} | {t.reading} |")
    lines += ["", "## Descriptive (not powered, decision D-C): estimate and interval only", "", "| target | estimate | 95% bootstrap-t interval |", "|---|---|---|"]
    for name in DESCRIPTIVE_TARGETS:
        t = results.targets[name]
        lines.append(f"| {name} | {_fmt(t.estimate)} | [{_fmt(t.ci_lo)}, {_fmt(t.ci_hi)}] |")
    lines += ["", f"## CR1 with t({results.n_countries - 1}), shown for transparency: {CR1_NOTE}", "", "| target | estimate | CR1 SE | CR1 p | CR1 95% interval |", "|---|---|---|---|---|"]
    for name in ALL_TARGETS:
        t = results.targets[name]
        lines.append(f"| {name} | {_fmt(t.estimate)} | {_fmt(t.cr1_se)} | {_fmt(t.cr1_p, 5)} | [{_fmt(t.cr1_ci_lo)}, {_fmt(t.cr1_ci_hi)}] |")
    lines += [
        "",
        "## Provenance",
        "",
        f"* seed {results.seed}, bootstrap seed key {results.seed_key}, B = {results.n_boot} (Rademacher weights, whole feasible procedure re-estimated in every bootstrap sample)",
        f"* versions: numpy {results.versions['numpy']}, pandas {results.versions['pandas']}, scipy {results.versions['scipy']}",
        f"* registry hash (SHA-256, LF-normalised): `{results.registry_hash}`",
        f"* code hash (m1.py + power_variants.py): `{results.code_hash}`",
        f"* gold extract hash: `{results.extract_hash}`",
        "",
    ]
    return "\n".join(lines)


def write_results(results: M1Results, out_dir: Path | None = None, tag_lookup: Callable[[], bool] | None = None) -> list[Path]:
    """Write ``m1_confirmatory.json`` and ``.md``. The default folder ``reports/results`` requires real-panel results AND the tag.

    Any other folder (unit tests pass ``tmp_path``) is written without those conditions. The folder is created only after the checks.
    """
    default = out_dir is None or Path(out_dir).resolve() == RESULTS_DIR.resolve()
    if default:
        if results.source != SOURCE_REAL:
            raise ResultsNotAllowed("only results from the real gold panel may be written to reports/results")
        require_preregistration_tag(tag_lookup)
    target = RESULTS_DIR if out_dir is None else Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    json_path, md_path = target / f"{RESULT_STEM}.json", target / f"{RESULT_STEM}.md"
    json_path.write_text(json.dumps(results.to_dict(), indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    md_path.write_text(render_markdown(results), encoding="utf-8", newline="\n")
    return [json_path, md_path]


def main(argv: list[str] | None = None) -> int:
    """``python src/models/py/m1.py``: run the confirmatory analysis on the real panel and write the result files.

    Prints only the tag status and the output paths, never an estimate. ``--check`` only reports whether the run is allowed.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report whether the pre-registration tag exists and exit")
    args = parser.parse_args(argv)
    if args.check:
        present = tag_exists()
        print(f"tag {PREREG_TAG}: {'present' if present else 'ABSENT (the real outcome must not be analysed)'}")
        return 0 if present else 1
    try:
        results = run_real()
    except PreregistrationTagMissing as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 1
    for path in write_results(results):
        print(f"written {path.relative_to(PROJECT_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
