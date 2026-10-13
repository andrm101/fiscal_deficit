"""Exploratory models E1-E4 and E6 (``docs/exploratory_spec.md``; ``config/registry/exploratory.toml``).

NEW CODE ONLY. The model, estimator and inference of the confirmatory run are imported, not copied: V7 = ``GlsEstimator(wls=True,
ar1=True)`` (``power_variants``), null-imposed wild-cluster bootstrap-t p-values and unrestricted bootstrap-t intervals (Rademacher
weights, B = 9,999, seed key 42, the whole feasible procedure re-estimated in every bootstrap sample), Benjamini-Hochberg and
Benjamini-Yekutieli from ``secondary``. The real gold panel is read ONLY through :func:`m1.load_real_panel` (tag
``preregistration-v1`` required). The fiscal-rule workbook is read with the standard library (``openpyxl`` is not installed),
read-only, after its SHA-256 has been checked against ``manifest.jsonl``.

Stages
------
``power``     outcome-free design checks and the E1/E2 (and indicative E3/E4) power block; written BEFORE any estimate is computed
              (the only outcome-derived input is the Gate 3b residual noise calibration, ``power.calibrate``).
``estimates`` all models, family multiplicity (BH q = 0.05, BY beside it over the seven pre-listed coefficients), E6, outputs.

Everything is exploratory; results are associations. The fiscal-rule index is a de jure design-strength score, not enforcement.
"""
from __future__ import annotations

import os

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")  # the batched small solves of the GLS engine are very slow with many BLAS threads
import argparse
import hashlib
import json
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd

try:  # numpy may already be imported by the caller: limit the BLAS thread pool explicitly
    from threadpoolctl import threadpool_limits

    threadpool_limits(limits=1)
except ImportError:  # pragma: no cover
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m1  # noqa: E402  (guard, loader, bootstrap-t intervals, hashes)
import secondary  # noqa: E402  (Benjamini-Hochberg / Yekutieli)

pv, power = m1.pv, m1.power

PROJECT_ROOT = m1.PROJECT_ROOT
RESULTS_DIR = m1.RESULTS_DIR
FIGURES_DIR = PROJECT_ROOT / "reports" / "figures"
RESULT_STEM = "exploratory"
FIGURE_NAME = "exploratory_forest.png"
SPEC_FILE = PROJECT_ROOT / "docs" / "exploratory_spec.md"
REGISTRY_TOML = PROJECT_ROOT / "config" / "registry" / "exploratory.toml"
COUNTRIES_CSV = PROJECT_ROOT / "config" / "countries.csv"
WORKBOOK = PROJECT_ROOT / "data" / "raw" / "fiscal_governance" / "nfr_2025_update" / "Numerical-Fiscal-Rules-database-2025.xlsx"
WORKBOOK_MANIFEST = WORKBOOK.parent / "manifest.jsonl"
HEADLINE_JSON = RESULTS_DIR / "m1_confirmatory.json"

B_MAIN = m1.BOOTSTRAP_DRAWS_CONFIRMATORY  # 9,999
B_LOCO = 999
SEED_KEY = m1.SEED_KEY  # 42
EXPL_KEY = 5000  # first SeedSequence key unused elsewhere in src (power.py: 0-5, 80-99; power_variants.py: 3000 and sub-keys)
PURPOSE_NULL, PURPOSE_SIZE, PURPOSE_MDE, PURPOSE_KMEANS, PURPOSE_KMEANS_REF = 1, 2, 3, 6, 5
BH_Q = 0.05
CI_LEVEL = m1.CI_LEVEL
SOURCE_REAL, SOURCE_SUPPLIED = m1.SOURCE_REAL, m1.SOURCE_SUPPLIED
SOURCE_LINE = "Source: European Commission AMECO Spring 2026, Fiscal Governance Database 2025 update, Eurostat; author's calculations"
RULE_WINDOW = (2016, 2021)
RULE_WINDOW_LONG = (2012, 2021)
NL_BAD_INDEX_YEARS = (2021, 2022)
PROMOTION_LINE_PP, PROMOTION_G2_LINE_PP = 1.0, 0.75
UNINFORMATIVE_HALF_WIDTH_PP = 1.0
GATE3B_RHO = 0.694  # Gate 3b corrected persistence (reports/gate3_power_update.md, section 3)
KINDS = ("V7", "V3", "V0")
KIND_LABEL = {"V7": "V7: feasible WLS + AR(1) GLS", "V3": "V3: feasible WLS only", "V0": "V0: two-way OLS"}
FAMILY: tuple[tuple[str, str, str], ...] = (  # (model id, target, description)
    ("E1", "gamma_F", "W_S x lagged rule index (pooled), per +1 SD of the index"),
    ("E2", "delta_BF", "W_S x between ageing x rule index, per +1 SD of each"),
    ("E3", "delta_H", "change in the W_S x between-ageing slope above the median (hinge)"),
    ("E4a", "delta_debt_between", "W_S x high-debt country (country-mean split), high minus low"),
    ("E4b", "delta_debt_within_time", "W_S x debt above the year's cross-country median, high minus low"),
    ("E4c", "delta_accession", "W_S x accession member (2004 or later), accession minus EU-14"),
    ("E4d", "delta_euro", "W_S x euro member in year t, euro minus non-euro"),
)
FAMILY_TARGETS = tuple(t for _, t, _ in FAMILY)
DEVIATIONS = (
    "No deviation from the specified models, estimators, inference, family or reading rules.",
    "Implementation choices the spec left open (no effect on any specified quantity): the 22 power-block jobs ran in parallel worker processes (each job has its own fixed seed stream); "
    "the power block was computed by the version of `exploratory.py` before two cosmetic edits (forest-plot source note shown only when an interval is clipped, and this text), so its code hash in the provenance differs; "
    "E4d Mundlak companion centres both split interactions at the exposure-weighted mean and does not rescale them.",
    "E6 stability: only about 16% of single-start k-means seeds reproduce the reference partition (the table's n_init = 50 solution) although Ward linkage gives the same partition; this is reported as the spec requires (no threshold), not corrected.",
)
NOT_RUN = {
    "E5": "not run: data not acquired (CPDS, DPI), no download approved",
    "E7": "not run: not chosen (the single optional extension is the researcher's Week-13 choice)",
    "E4-democratic-age": "not run: data not acquired (V-Dem), no download approved",
}


# ---------------------------------------------------------------------------------------------
# Rule index: standard-library reader
# ---------------------------------------------------------------------------------------------
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main", "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def _col_letters(n: int) -> str:
    out = ""
    while n:
        n, rem = divmod(n - 1, 26)
        out = chr(65 + rem) + out
    return out


def file_sha256_bytes(path: Path) -> str:
    """SHA-256 of the raw bytes (binary file; no line-ending normalisation)."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_workbook(path: Path = WORKBOOK, manifest: Path = WORKBOOK_MANIFEST) -> str:
    """Raise unless the SHA-256 of the workbook equals the manifest entry of the same file name; returns the digest."""
    digest = file_sha256_bytes(path)
    for line in Path(manifest).read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        if entry["dest"].endswith(Path(path).name):
            if entry["sha256"] != digest:
                raise ValueError(f"{Path(path).name}: SHA-256 {digest} differs from the manifest {entry['sha256']}")
            return digest
    raise ValueError(f"{Path(path).name} not listed in {manifest}")


def read_cfrsi(path: Path = WORKBOOK, sheet: str = "C-FRSI", first_row: int = 7, last_row: int = 33, header_row: int = 6) -> tuple[pd.DataFrame, dict]:
    """Raw C-FRSI sheet as a (country x index year) float table; "." and blank cells become NaN. Read-only, standard library only.

    Returns ``(values, info)``; ``info`` has the counts of "." cells and of blank cells per index year. Country codes are column B
    of rows 7-33 (27 countries, "EL" for Greece); the index years are the header cells of row 6, columns C onwards (1990-2024).
    """
    with zipfile.ZipFile(path) as z:  # opened read-only
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = {r.attrib["Id"]: r.attrib["Target"] for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
        target = None
        for s in wb.find("m:sheets", _NS):
            if s.attrib["name"] == sheet:
                target = rels[s.attrib["{%s}id" % _NS["r"]]]
        if target is None:
            raise ValueError(f"sheet {sheet!r} not found")
        strings = [
            "".join(t.text or "" for t in si.iter("{%s}t" % _NS["m"])) for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", _NS)
        ]
        root = ET.fromstring(z.read("xl/" + target.lstrip("/").replace("xl/", "")))
        cells: dict[str, Any] = {}
        for c in root.iter("{%s}c" % _NS["m"]):
            v = c.find("m:v", _NS)
            kind = c.attrib.get("t")
            if v is None:
                continue
            cells[c.attrib["r"]] = strings[int(v.text)] if kind == "s" else (v.text if kind in ("str", "e", "b") else float(v.text))
    years: dict[int, str] = {}
    col = 3
    while isinstance(cells.get(f"{_col_letters(col)}{header_row}"), float):
        years[int(cells[f"{_col_letters(col)}{header_row}"])] = _col_letters(col)
        col += 1
    if not years or min(years) != 1990 or max(years) != 2024:
        raise ValueError(f"unexpected header years {sorted(years)[:3]}...{sorted(years)[-3:]}")
    codes = [cells.get(f"B{r}") for r in range(first_row, last_row + 1)]
    if len(codes) != 27 or len(set(codes)) != 27 or any(not isinstance(c, str) for c in codes):
        raise ValueError(f"unexpected country rows {codes}")
    values = pd.DataFrame(np.nan, index=codes, columns=sorted(years), dtype=float)
    dots = {y: 0 for y in years}
    blank = {y: 0 for y in years}
    for r, code in zip(range(first_row, last_row + 1), codes):
        for y, letter in years.items():
            v = cells.get(f"{letter}{r}")
            if isinstance(v, float):
                values.at[code, y] = v
            elif v == ".":
                dots[y] += 1
            else:
                blank[y] += 1
    return values, {"dot_cells_by_year": dots, "blank_cells_by_year": blank, "index_years": [min(years), max(years)]}


def apply_nl_policy(rule: pd.DataFrame, policy: str = "exclude") -> pd.DataFrame:
    """NL raw index of 2021 and 2022 set to missing (``exclude``, the chosen rule) or kept (``include``). Never imputed."""
    out = rule.copy()
    if policy == "exclude" and "NL" in out.index:
        for y in NL_BAD_INDEX_YEARS:
            if y in out.columns:
                out.at["NL", y] = np.nan
    elif policy not in ("exclude", "include"):
        raise ValueError(policy)
    return out


# ---------------------------------------------------------------------------------------------
# Panel preparation and model designs
# ---------------------------------------------------------------------------------------------
def sorted_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.sort_values(["eurostat_code", "year"]).reset_index(drop=True)


def prepare(extract: pd.DataFrame, rule: pd.DataFrame, *, nl_policy: str = "exclude", accession: dict[str, int] | None = None) -> pd.DataFrame:
    """Confirmatory rows sorted by country and year with ``F_raw`` (raw index at t-1, NaN where missing), accession year and float euro flag."""
    f = extract[extract["in_confirmatory"].astype(bool)] if "in_confirmatory" in extract.columns else extract
    f = sorted_frame(f).copy()
    r = apply_nl_policy(rule, nl_policy)
    lookup = {(c, int(y)): v for c, row in r.iterrows() for y, v in row.items()}
    f["F_raw"] = [lookup.get((c, int(y) - 1), np.nan) for c, y in zip(f["eurostat_code"], f["year"])]
    if "eu_accession_year" not in f.columns:
        if accession is None:
            accession = pd.read_csv(COUNTRIES_CSV).set_index("eurostat_code")["eu_accession_year"].to_dict()
        f["eu_accession_year"] = f["eurostat_code"].map(accession)
    f["euro_member"] = f["euro_member"].astype(float)
    return f


def between_component(frame: pd.DataFrame) -> np.ndarray:
    """``B_i = abar_i / sd(abar)``: the standardised between component of lagged ageing, expanded to rows (as ``WS_x_between`` / W_S)."""
    a = frame["olddep1_lag"].to_numpy(float)
    z = (a - a.mean()) / a.std(ddof=0)
    abar = pd.Series(z).groupby(frame["eurostat_code"].to_numpy()).transform("mean").to_numpy()
    return abar / abar.std(ddof=0)


def _centre(values: np.ndarray, w_s: np.ndarray) -> np.ndarray:
    """``D - sum(W_S D) / sum(W_S)``: centred at the exposure-weighted mean (the rule that centres the era terms)."""
    if w_s.sum() <= 0:
        raise ValueError("W_S has no exposure on the estimation sample")
    return values - float((w_s * values).sum() / w_s.sum())


def _standardise(x: pd.Series) -> np.ndarray:
    v = x.to_numpy(float)
    return (v - v.mean()) / v.std(ddof=0)


def finish(frame: pd.DataFrame, regs: pd.DataFrame, targets: dict[str, str], scale: dict[str, float], label: str) -> power.Design:
    """Design on the (sorted) frame; a column with no variation is dropped first (as the M1 builder does)."""
    regs = regs.reset_index(drop=True)
    regs = regs.loc[:, [bool(np.ptp(regs[c].to_numpy(float)) > 0) for c in regs.columns]]
    targets = {t: c for t, c in targets.items() if c in regs.columns}
    frame = frame.copy()
    frame["capb"] = frame["capb"].astype(float)
    return power.build_design(frame, label=label, regressors=regs, targets=targets, scale=scale)


def window_frame(prep: pd.DataFrame, first: int, last: int, *, need_rule: bool = True) -> pd.DataFrame:
    f = prep[(prep["year"] >= first) & (prep["year"] <= last)]
    if need_rule:
        f = f[f["F_raw"].notna()]
    return sorted_frame(f)


def build_e1(frame: pd.DataFrame, kind: str = "pooled", *, single_era: bool = False, label: str = "E1") -> power.Design:
    """E1 design on a rule-window frame (rows with a numeric lagged index). ``kind``: pooled | split | noage | e2.

    Base: M1 terms without the multi-era terms (``era=False``; ``single_era`` adds the one centred term 2016-2021 of the long window),
    ``F_z`` (index at t-1 standardised on THIS sample) and ``WS_x_F``.
    """
    frame = sorted_frame(frame)
    regs, scale, targets = pv.variant_regressors(frame, era=False, control_names=())
    regs, scale, targets = regs.reset_index(drop=True), dict(scale), dict(targets)
    if single_era:
        regs = pd.concat([regs, pv.era_terms(frame, breaks=((2016, 2021),)).reset_index(drop=True)], axis=1)
    f = frame["F_raw"]
    fz = _standardise(f)
    ws = frame["W_S"].to_numpy(float)
    scale.update({"sd_F_raw": float(f.std(ddof=0)), "mean_F_raw": float(f.mean())})
    if kind == "noage":
        for c in ("WS_x_between", "WS_x_within"):
            regs = regs.drop(columns=[c])
        targets = {t: c for t, c in targets.items() if t == "beta_S"}
    regs["F_z"] = fz
    if kind in ("pooled", "noage", "e2"):
        regs["WS_x_F"] = ws * fz
        targets["gamma_F"] = "WS_x_F"
    if kind == "e2":
        b = between_component(frame)
        regs["B_x_F"] = b * fz
        regs["WS_x_B_x_F"] = ws * b * fz
        targets["delta_BF"] = "WS_x_B_x_F"
    if kind == "split":
        code = frame["eurostat_code"].to_numpy()
        fbar = pd.Series(fz).groupby(code).transform("mean").to_numpy()
        fdev = fz - fbar
        regs["WS_x_Fbetween"] = ws * fbar / fbar.std(ddof=0)
        regs["WS_x_Fwithin"] = ws * fdev / fdev.std(ddof=0)
        targets.update({"gamma_F_B": "WS_x_Fbetween", "gamma_F_W": "WS_x_Fwithin"})
    if kind not in ("pooled", "noage", "e2", "split"):
        raise ValueError(kind)
    return finish(frame, regs, targets, scale, label)


def build_presence(frame: pd.DataFrame, *, label: str = "E1-presence") -> power.Design:
    """Rule-presence dummy on the long window: ``P = 1`` if the lagged index is numeric ("." coded 0), centred interaction ``WS_x_P``."""
    frame = sorted_frame(frame)
    regs, scale, targets = pv.variant_regressors(frame, era=False, control_names=())
    regs = pd.concat([regs.reset_index(drop=True), pv.era_terms(frame, breaks=((2016, 2021),)).reset_index(drop=True)], axis=1)
    p = frame["F_raw"].notna().to_numpy(float)
    ws = frame["W_S"].to_numpy(float)
    regs["P"] = p
    regs["WS_x_P"] = ws * _centre(p, ws)
    targets = dict(targets)
    targets["delta_P"] = "WS_x_P"
    return finish(frame, regs, dict(targets), dict(scale), label)


def country_level(values: np.ndarray, frame: pd.DataFrame) -> pd.Series:
    return pd.Series(values).groupby(frame["eurostat_code"].to_numpy()).first()


def build_e3(frame: pd.DataFrame, kind: str = "hinge", *, label: str = "E3") -> tuple[power.Design, dict]:
    """E3 on the full sample: hinge | slopes | terciles. The nonlinearity is imposed on the between component only."""
    frame = sorted_frame(frame)
    regs, scale, targets = pv.variant_regressors(frame, era=True, control_names=())
    regs, scale, targets = regs.reset_index(drop=True), dict(scale), dict(targets)
    b = between_component(frame)
    ws = frame["W_S"].to_numpy(float)
    cb = country_level(b, frame)
    kappa = float(cb.median())
    info: dict[str, Any] = {"knot": kappa, "n_countries_above_knot": int((cb > kappa).sum()), "n_countries_at_or_below_knot": int((cb <= kappa).sum())}
    if kind == "hinge":
        regs["WS_x_hinge"] = ws * np.maximum(b - kappa, 0.0)
        targets.pop("gamma_B")
        targets.update({"gamma_B_low": "WS_x_between", "delta_H": "WS_x_hinge"})
    elif kind == "slopes":
        regs = regs.drop(columns=["WS_x_between"])
        regs["WS_x_S1"] = ws * np.minimum(b, kappa)
        regs["WS_x_S2"] = ws * np.maximum(b - kappa, 0.0)
        targets.pop("gamma_B")
        targets.update({"slope_below": "WS_x_S1", "slope_above": "WS_x_S2"})
    elif kind == "terciles":
        order = sorted(cb.index, key=lambda c: (cb[c], c))
        groups = np.array_split(np.array(order, dtype=object), 3)
        info["tercile_sizes"] = [len(g) for g in groups]
        info["tercile_members"] = {n: [str(c) for c in g] for n, g in zip(("low", "mid", "top"), groups)}
        code = frame["eurostat_code"].to_numpy()
        regs = regs.drop(columns=["WS_x_between"])
        for name, grp in (("mid", groups[1]), ("top", groups[2])):
            d = np.isin(code, grp).astype(float)
            regs[f"WS_x_{name}"] = ws * _centre(d, ws)
            targets[f"tau_{name}"] = f"WS_x_{name}"
        targets.pop("gamma_B")
    else:
        raise ValueError(kind)
    return finish(frame, regs, targets, scale, label), info


def e4_moderator(frame: pd.DataFrame, which: str) -> tuple[pd.DataFrame, np.ndarray, str, bool, dict]:
    """``(frame used, D, target name, D varies within country, info)`` for E4a-E4d on the full-sample frame."""
    frame = sorted_frame(frame)
    info: dict[str, Any] = {}
    if which == "a":
        cm = frame.groupby("eurostat_code")["debt_gdp_lag"].mean()
        med = float(cm.median())
        high = frame["eurostat_code"].map(cm > med).to_numpy(float)
        info.update({"median_country_mean_debt": med, "n_high": int((cm > med).sum()), "n_low": int((cm <= med).sum())})
        return frame, high, "delta_debt_between", False, info
    if which == "b":
        frame = sorted_frame(frame[frame["debt_gdp_lag"].notna()])
        med_t = frame.groupby("year")["debt_gdp_lag"].transform("median")
        high = (frame["debt_gdp_lag"] > med_t).to_numpy(float)
        info.update({"share_high_rows": float(high.mean())})
        return frame, high, "delta_debt_within_time", True, info
    if which == "c":
        acc = (frame["eu_accession_year"].to_numpy(float) >= 2004).astype(float)
        info.update({"n_accession": int(country_level(acc, frame).sum()), "n_eu14": int((1 - country_level(acc, frame)).sum())})
        return frame, acc, "delta_accession", False, info
    if which == "d":
        eu = frame["euro_member"].to_numpy(float)
        info.update({"rows_euro": int(eu.sum()), "countries_never_euro": int((pd.Series(eu).groupby(frame["eurostat_code"].to_numpy()).max() == 0).sum())})
        return frame, eu, "delta_euro", True, info
    raise ValueError(which)


def build_e4(frame: pd.DataFrame, which: str, kind: str = "pooled", *, label: str | None = None) -> tuple[power.Design, dict]:
    """E4 design. ``pooled``: M1 + centred ``WS_x_D`` (+ the main effect of D if it varies within country). ``groups``: ``W_S*D`` and
    ``W_S*(1-D)`` replace ``W_S`` and the interaction (same column space). ``mundlak`` (euro only): between/within split of D."""
    frame, d, tname, varies, info = e4_moderator(frame, which)
    regs, scale, targets = pv.variant_regressors(frame, era=True, control_names=())
    regs, scale, targets = regs.reset_index(drop=True), dict(scale), dict(targets)
    ws = frame["W_S"].to_numpy(float)
    if varies:
        regs["D_main"] = d
    if kind == "pooled":
        regs["WS_x_D"] = ws * _centre(d, ws)
        targets[tname] = "WS_x_D"
    elif kind == "groups":
        regs = regs.drop(columns=["W_S"])
        regs["WS_D1"] = ws * d
        regs["WS_D0"] = ws * (1.0 - d)
        targets.pop("beta_S")
        targets.update({"beta_S_D1": "WS_D1", "beta_S_D0": "WS_D0"})
    elif kind == "mundlak":
        if which != "d":
            raise ValueError("the Mundlak split is defined for E4d only")
        code = frame["eurostat_code"].to_numpy()
        dbar = pd.Series(d).groupby(code).transform("mean").to_numpy()
        regs["WS_x_ebar"] = ws * _centre(dbar, ws)
        regs["WS_x_edev"] = ws * _centre(d - dbar, ws)
        targets.update({"delta_euro_between": "WS_x_ebar", "delta_euro_within": "WS_x_edev"})
    else:
        raise ValueError(kind)
    return finish(frame, regs, targets, scale, label or f"E4{which}"), info


# ---------------------------------------------------------------------------------------------
# Estimation: estimator ladder, feasibility checks, bootstrap inference
# ---------------------------------------------------------------------------------------------
def make_estimator(design: power.Design, kind: str) -> pv.GlsEstimator:
    if kind not in KINDS:
        raise ValueError(kind)
    return pv.GlsEstimator(design, wls=kind in ("V7", "V3"), ar1=kind == "V7")


def feasibility(design: power.Design, kind: str) -> dict:
    """Mechanical checks F1-F3 of the spec on the point-estimate fit (F1 is the successful build of ``design``); F4 is checked in the bootstrap."""
    out: dict[str, Any] = {"F1_full_rank": True, "F2_nickell_invertible": None, "F3_variance_floor_ok": None}
    if kind == "V0":
        out["passed"] = True
        return out
    est = make_estimator(design, kind)
    _, u1, rho, _ = est.first_stage(design.y[:, None])
    var = np.add.reduceat(u1[:, 0] ** 2, design.starts) / design.counts
    out["F3_variance_floor_ok"] = bool(var.min() > 1e-12 * var.max())
    out["country_sd_min"], out["country_sd_max"] = float(np.sqrt(var.min())), float(np.sqrt(var.max()))
    if kind == "V7":
        raw = float(power._pair_ar1(u1, design, standardise=True)[0])
        t_mean = float(design.counts.mean())
        plim = np.array([r + power.nickell_bias(r, t_mean) for r in pv.RHO_GRID])
        out.update({"raw_rho": raw, "corrected_rho": float(rho[0]), "plim_min": float(plim.min()), "plim_max": float(plim.max()), "mean_years": t_mean})
        out["F2_nickell_invertible"] = bool(plim.min() < raw < plim.max() and float(rho[0]) < pv.RHO_CAP - 1e-12)
    out["passed"] = bool(out["F3_variance_floor_ok"] and out["F2_nickell_invertible"] is not False)
    return out


def _target_entry(name: str, estimate: float, se: float, lo: float, hi: float) -> dict:
    return {"estimate": float(estimate), "cr1_se": float(se), "ci_lo": float(lo), "ci_hi": float(hi)}


def fit_model(design: power.Design, kind: str, *, p_targets: Sequence[str], n_boot: int, seed_key: int = SEED_KEY) -> dict:
    """Fit ``kind`` on ``design``: estimate, CR1 SE and unrestricted bootstrap-t interval of EVERY target; null-imposed p of ``p_targets``."""
    est = make_estimator(design, kind)
    y = design.y
    names = list(design.targets)
    fit = est.fit(y, names)
    t_star = m1.unrestricted_bootstrap_t(est, y, names, n_boot, seed_key)  # raises FloatingPointError on non-finite t* (check F4)
    tail = (1.0 - CI_LEVEL) / 2.0
    targets = {}
    for name in names:
        b, se = float(fit[name][0][0]), float(fit[name][1][0])
        q_lo, q_hi = np.quantile(t_star[name], [tail, 1.0 - tail])
        targets[name] = _target_entry(name, b, se, b - float(q_hi) * se, b - float(q_lo) * se)
    for name in p_targets:
        p = float(pv.wild_bootstrap_pvalues(est, name, y[:, None], weights="rademacher", n_boot=n_boot, seed_key=seed_key)[0])
        if not np.isfinite(p):
            raise FloatingPointError(f"non-finite bootstrap p-value for {name}")
        targets[name]["p_bootstrap"] = p
    _, u1, rho, _ = est.first_stage(y[:, None])
    sd = np.sqrt(np.add.reduceat(u1[:, 0] ** 2, design.starts) / design.counts)
    codes = design.codes[design.starts]
    return {
        "status": "ok", "estimator": kind, "n_obs": int(design.n_obs), "n_countries": int(design.n_clusters), "year_min": int(design.year.min()), "year_max": int(design.year.max()),
        "n_params": int(design.k_params), "x_names": list(design.x_names), "targets": targets, "scale": {k: float(v) for k, v in design.scale.items()},
        "diagnostics": {"rho_nickell": float(rho[0]), "resid_sd_min": float(sd.min()), "resid_sd_max": float(sd.max()), "resid_sd_min_country": str(codes[int(np.argmin(sd))]),
                        "resid_sd_max_country": str(codes[int(np.argmax(sd))])},
    }


def safe_fit(design_fn: Callable[[], power.Design], kind: str, *, p_targets: Sequence[str], n_boot: int, seed_key: int = SEED_KEY) -> dict:
    """Build and fit; any modelling failure is reported as ``status == 'failed'`` with the reason (never re-specified)."""
    try:
        design = design_fn()
        flags = feasibility(design, kind)
        if not flags["passed"]:
            return {"status": "infeasible", "estimator": kind, "checks": flags, "error": "feasibility check failed"}
        out = fit_model(design, kind, p_targets=p_targets, n_boot=n_boot, seed_key=seed_key)
        out["checks"] = {**flags, "F4_bootstrap_finite": True}
        return out
    except (ValueError, np.linalg.LinAlgError, FloatingPointError, KeyError) as error:
        return {"status": "failed", "estimator": kind, "error": f"{type(error).__name__}: {error}"}


def fit_ladder(design_fn: Callable[[], power.Design], *, p_targets: Sequence[str], n_boot: int, seed_key: int = SEED_KEY, log: Callable = print) -> dict:
    """V7, V3 and V0 on the same design. The estimator in force is the first of V7, V3, V0 whose checks pass and whose fit succeeds."""
    by = {}
    for kind in KINDS:
        by[kind] = safe_fit(design_fn, kind, p_targets=p_targets, n_boot=n_boot, seed_key=seed_key)
        log(f"    {kind}: {by[kind]['status']}")
    in_force = next((k for k in KINDS if by[k]["status"] == "ok"), None)
    return {"in_force": in_force, "by_estimator": by,
            "fallback_triggered": in_force != "V7", "main": by[in_force] if in_force else {"status": "failed", "error": "no estimator succeeded"}}


# ---------------------------------------------------------------------------------------------
# Multiplicity
# ---------------------------------------------------------------------------------------------
def reading(entry: dict, q_bh: float | None) -> dict:
    lo, hi = entry["ci_lo"], entry["ci_hi"]
    excludes = bool(lo > 0 or hi < 0)
    if q_bh is not None and q_bh <= BH_Q:
        label = "BH-rejected"
    elif excludes:
        label = "interval excludes zero, not BH-rejected (nominal only)"
    else:
        label = "interval contains zero"
    return {"excludes_zero": excludes, "label": label, "half_width": float((hi - lo) / 2.0), "uninformative": bool((hi - lo) / 2.0 > UNINFORMATIVE_HALF_WIDTH_PP)}


def apply_family(models: dict, power_block: dict | None = None) -> dict:
    """BH (q = 0.05) and BY q-values over the pre-listed family; a missing or failed model stays listed as failed and m is reduced."""
    rows, ok = [], []
    for mid, target, desc in FAMILY:
        m = models.get(mid)
        main = (m or {}).get("main") if m else None
        good = bool(main and main.get("status") == "ok" and target in main.get("targets", {}) and "p_bootstrap" in main["targets"][target])
        row = {"model": mid, "target": target, "description": desc, "status": "ok" if good else "failed"}
        if good:
            row.update(main["targets"][target])
            row.update({"estimator": main["estimator"], "n_obs": main["n_obs"], "n_countries": main["n_countries"]})
            ok.append(row)
        rows.append(row)
    if ok:
        raw = [r["p_bootstrap"] for r in ok]
        for r, bh, by in zip(ok, secondary.benjamini_hochberg(raw), secondary.benjamini_yekutieli(raw)):
            r.update({"q_bh": float(bh), "q_by": float(by), "bh_reject": bool(bh <= BH_Q), "by_reject": bool(by <= BH_Q)})
    for r in ok:
        r.update(reading(r, r["q_bh"]))
        if power_block:
            r["mde"] = family_mde(power_block, r["model"], r["target"], r.get("estimator"))
    return {"m_listed": len(FAMILY), "m_used": len(ok), "alpha": BH_Q, "complete": len(ok) == len(FAMILY),
            "n_bh_reject": int(sum(r["bh_reject"] for r in ok)), "n_by_reject": int(sum(r["by_reject"] for r in ok)), "rows": rows}


def family_mde(power_block: dict, model: str, target: str, estimator: str | None) -> dict | None:
    entry = (power_block.get("models") or {}).get(model)
    if not entry:
        return None
    kind = estimator if estimator in entry.get("by_estimator", {}) else "V7"
    sc = entry["by_estimator"].get(kind, {})
    out = {"estimator": kind}
    for scen, res in sc.items():
        out[scen] = {"wild_bootstrap_mde": (res.get("wcb") or {}).get("mde"), "cr1_mde_size_adjusted": res["cr1"].get("mde_size_adjusted"), "cr1_mde": res["cr1"].get("mde")}
    return out


# ---------------------------------------------------------------------------------------------
# Power block (design properties; the only outcome-derived input is the Gate 3b residual noise calibration)
# ---------------------------------------------------------------------------------------------
def calibration(extract: pd.DataFrame) -> tuple[power.Calibration, power.Design]:
    """``power.calibrate`` of the V0n design (M1 without era terms), as in Gate 3b (``Context.cal_ref``)."""
    f = extract[extract["in_confirmatory"].astype(bool)] if "in_confirmatory" in extract.columns else extract
    design = pv.build_variant_design(f, "V0n", era=False, control_names=())
    return power.calibrate(design), design


def _power_job(args: tuple) -> tuple:
    """One (model, estimator kind, scenario) cell: CR1 null draws and, if requested, the simulated wild-bootstrap power curve."""
    (key, design, kind, target, sigma, rho, scen_i, model_i, kind_i, settings, with_wcb) = args
    est = make_estimator(design, kind)
    var = SimpleNamespace(design=design, estimator=est)
    noise = power.ArNoise(design, sigma, rho)
    cr1_all = pv.cr1_from_null_draws(var, noise, power.make_rng(EXPL_KEY, PURPOSE_NULL, model_i, scen_i), settings.n_null)
    result: dict[str, Any] = {"cr1": cr1_all[target], "rho_dgp": float(rho)}
    if with_wcb:
        n_size, n_mde = settings.size_generic, settings.mde_generic
        e_size = noise.draw(power.make_rng(EXPL_KEY, PURPOSE_SIZE, model_i, scen_i), n_size)
        e_mde = noise.draw(power.make_rng(EXPL_KEY, PURPOSE_MDE, model_i, scen_i), n_mde)
        seed_key = 6000 + 100 * model_i + 10 * scen_i + kind_i
        size = pv.bootstrap_rate(var, target, e_size, 0.0, seed_key, settings.n_boot, None)
        betas = pv.effect_grid(cr1_all[target]["mde"], target)
        rates = np.array([pv.bootstrap_rate(var, target, e_mde, float(b), seed_key, settings.n_boot, None) for b in betas])
        curve = pv.power_curve_mde(np.r_[0.0, betas], np.r_[size, rates], np.r_[float(n_size), np.full(len(betas), float(n_mde))])
        result["wcb"] = {"size": float(size), "mde": float(curve["mde"]), "mde_se": float(curve["mde_se"]), "betas": betas.tolist(), "rates": rates.tolist(),
                         "max_fit_residual": float(curve["max_fit_residual"]), "n_size": n_size, "n_grid": n_mde}
    return key, result


def power_block(extract: pd.DataFrame, rule: pd.DataFrame, *, settings: pv.Settings = pv.FULL, workers: int = 1, log: Callable = print,
                on_update: Callable[[dict], None] | None = None) -> dict:
    """The power block of the spec. Design-only apart from the noise calibration; computes no coefficient of the real outcome."""
    prep = prepare(extract, rule)
    cal, ref = calibration(extract)
    ref_codes = ref.codes[ref.starts]
    out: dict[str, Any] = {"settings": dict(settings.__dict__), "calibration": {
        "rho_corrected": float(cal.rho_corrected), "rho_gate3b": GATE3B_RHO, "reproduces_gate3b": bool(abs(cal.rho_corrected - GATE3B_RHO) < 0.01),
        "sigma_min": float(cal.sigma.min()), "sigma_max": float(cal.sigma.max())}, "models": {}, "design_information": {}, "scenarios": ["ar1_rho_hat", "ar1_rho0"]}
    rhos = {"ar1_rho_hat": float(cal.rho_corrected), "ar1_rho0": 0.0}
    full = prep
    designs: dict[str, tuple[power.Design, str, bool, tuple]] = {}
    designs["E1"] = (build_e1(window_frame(prep, *RULE_WINDOW), "pooled"), "gamma_F", True, KINDS)
    designs["E2"] = (build_e1(window_frame(prep, *RULE_WINDOW), "e2", label="E2"), "delta_BF", True, KINDS)
    designs["E3"] = (build_e3(full, "hinge")[0], "delta_H", False, ("V7",))
    for w in "abcd":
        d, _ = build_e4(full, w, "pooled")
        designs[f"E4{w}"] = (d, {"a": "delta_debt_between", "b": "delta_debt_within_time", "c": "delta_accession", "d": "delta_euro"}[w], False, ("V7",))
    jobs = []
    for mi, (mid, (design, target, with_wcb, kinds)) in enumerate(designs.items()):
        if not np.array_equal(design.codes[design.starts], ref_codes):
            raise ValueError(f"{mid}: country set differs from the calibration design")
        for ki, kind in enumerate(kinds):
            for si, scen in enumerate(out["scenarios"]):
                jobs.append(((mid, kind, scen), design, kind, target, cal.sigma, rhos[scen], si, mi, ki, settings, with_wcb))
        out["design_information"][mid] = {"target": target, "r_squared_norm": float(design.r[target] @ design.r[target]), "n_obs": int(design.n_obs),
                                          "sd_F_raw": design.scale.get("sd_F_raw")}
        out["models"][mid] = {"target": target, "n_obs": int(design.n_obs), "n_countries": int(design.n_clusters), "by_estimator": {}}
    m1_design = pv.build_variant_design(extract[extract["in_confirmatory"].astype(bool)] if "in_confirmatory" in extract.columns else extract, "M1", era=True, control_names=())
    out["design_information"]["M1_beta_S"] = {"target": "beta_S", "r_squared_norm": float(m1_design.r["beta_S"] @ m1_design.r["beta_S"]), "n_obs": int(m1_design.n_obs)}
    t0 = time.time()

    def store(key: tuple, res: dict) -> None:
        mid, kind, scen = key
        out["models"][mid]["by_estimator"].setdefault(kind, {})[scen] = res
        sd = out["design_information"][mid].get("sd_F_raw")
        if res.get("wcb") and sd:
            res["wcb"]["mde_index_points"] = res["wcb"]["mde"] / sd
        log(f"  power {key} done ({time.time() - t0:.0f}s)" + (f", wcb mde {res['wcb']['mde']:.3f}" if res.get("wcb") else f", cr1 sa mde {res['cr1']['mde_size_adjusted']:.3f}"))
        if on_update:
            on_update(out)

    if workers > 1:
        from concurrent.futures import ProcessPoolExecutor

        with ProcessPoolExecutor(max_workers=workers) as pool:
            for key, res in pool.map(_power_job, jobs):
                store(key, res)
    else:
        for job in jobs:
            store(*_power_job(job))
    out["promotion_check"] = promotion_check(out)
    return out


def promotion_check(block: dict) -> dict:
    """E1 promotion condition: wild-bootstrap MDE per +1 SD at the estimated persistence at most 1.0 pp (the 0.75 pp G2 line reported beside it)."""
    res = {}
    for kind, sc in block["models"]["E1"]["by_estimator"].items():
        m = sc.get("ar1_rho_hat", {}).get("wcb", {}).get("mde")
        res[kind] = {"wcb_mde_pp_per_sd_rho_hat": m, "within_1.0pp": None if m is None else bool(m <= PROMOTION_LINE_PP),
                     "within_0.75pp": None if m is None else bool(m <= PROMOTION_G2_LINE_PP),
                     "wcb_mde_pp_per_sd_rho0": sc.get("ar1_rho0", {}).get("wcb", {}).get("mde")}
    res["lines_pp"] = {"promotion": PROMOTION_LINE_PP, "g2_interaction": PROMOTION_G2_LINE_PP}
    return res


# ---------------------------------------------------------------------------------------------
# E6: country typology (descriptive)
# ---------------------------------------------------------------------------------------------
E6_FEATURES = (("mean_debt", "debt_gdp_lag", "% of GDP"), ("mean_interest", "sec_interest_d41pay", "% of GDP"), ("mean_capb", "capb", "pp of potential GDP"),
               ("iqr_capb", "capb", "pp of potential GDP"), ("mean_ageing", "olddep1_lag", "persons 65+ per 100 aged 15-64"))
KR_SCALE = ((0.70, "strong structure"), (0.50, "reasonable structure"), (0.25, "weak structure"), (-1.0, "no substantial structure"))


def silhouette_label(value: float) -> str:
    for cut, label in KR_SCALE:
        if value > cut:
            return label
    return KR_SCALE[-1][1]


def e6_features(extract: pd.DataFrame) -> pd.DataFrame:
    f = extract[extract["in_confirmatory"].astype(bool)] if "in_confirmatory" in extract.columns else extract
    g = f.groupby("eurostat_code")
    feats = pd.DataFrame({
        "mean_debt": g["debt_gdp_lag"].mean(), "mean_interest": g["sec_interest_d41pay"].mean(), "mean_capb": g["capb"].mean(),
        "iqr_capb": g["capb"].apply(lambda s: float(np.quantile(s.dropna(), 0.75) - np.quantile(s.dropna(), 0.25))), "mean_ageing": g["olddep1_lag"].mean()})
    return feats.sort_index()


def run_e6(extract: pd.DataFrame, prep: pd.DataFrame | None = None, k_range: Sequence[int] = (2, 3, 4, 5, 6), n_seeds: int = 100, min_size: int = 3) -> dict:
    """k-means typology on z-scored country features with k chosen by the pre-stated silhouette rule, plus seed stability and a Ward cross-check."""
    from scipy.cluster.hierarchy import fcluster, linkage
    from sklearn.cluster import KMeans
    from sklearn.metrics import adjusted_rand_score, silhouette_score

    feats = e6_features(extract)
    if feats.isna().any().any():
        raise ValueError("missing country features")
    z = ((feats - feats.mean()) / feats.std(ddof=0)).to_numpy()
    table = []
    labels_by_k = {}
    for k in k_range:
        seed = int(power.make_rng(EXPL_KEY, PURPOSE_KMEANS_REF, int(k)).integers(2**31 - 1))
        km = KMeans(n_clusters=k, init="k-means++", n_init=50, algorithm="lloyd", random_state=seed).fit(z)
        sizes = np.bincount(km.labels_, minlength=k)
        sil = float(silhouette_score(z, km.labels_, metric="euclidean")) if 2 <= len(set(km.labels_)) < len(z) else float("nan")
        table.append({"k": int(k), "silhouette": sil, "smallest_cluster": int(sizes.min()), "inertia": float(km.inertia_), "admissible": bool(sizes.min() >= min_size)})
        labels_by_k[k] = km.labels_
    admissible = [r for r in table if r["admissible"] and np.isfinite(r["silhouette"])]
    out: dict[str, Any] = {"status": "descriptive", "features": [{"name": n, "column": c, "unit": u} for n, c, u in E6_FEATURES], "k_table": table, "n_countries": int(len(feats)),
                           "rule": "highest mean silhouette among k with smallest cluster >= 3 countries; ties to the smaller k"}
    if not admissible:
        out["chosen_k"] = None
        out["note"] = "no admissible k"
        return out
    best = max(r["silhouette"] for r in admissible)
    k = min(r["k"] for r in admissible if abs(r["silhouette"] - best) < 1e-12)
    out["chosen_k"] = int(k)
    out["silhouette"] = best
    out["silhouette_reading"] = silhouette_label(best)
    runs = []
    for j in range(n_seeds):
        seed = int(power.make_rng(EXPL_KEY, PURPOSE_KMEANS, j).integers(2**31 - 1))
        km = KMeans(n_clusters=k, init="k-means++", n_init=1, algorithm="lloyd", random_state=seed).fit(z)
        runs.append((float(km.inertia_), j, km.labels_))
    ref_inertia, ref_j, ref = min(runs, key=lambda r: (r[0], r[1]))
    aris = np.array([adjusted_rand_score(ref, lab) for _, _, lab in runs])
    ward = fcluster(linkage(z, method="ward"), t=k, criterion="maxclust")
    out["stability"] = {"n_seeds": n_seeds, "reference_run": int(ref_j), "reference_inertia": ref_inertia, "share_equal_to_reference": float(np.mean(aris == 1.0)),
                        "ari_min": float(aris.min()), "ari_median": float(np.median(aris)), "share_reaching_best_inertia": float(np.mean([abs(r[0] - ref_inertia) < 1e-9 for r in runs])),
                        "ari_ward_vs_reference": float(adjusted_rand_score(ref, ward))}
    order = sorted(set(ref), key=lambda c: (-int((ref == c).sum()), c))  # relabel by size (descending) for stable reporting
    relabel = {c: i + 1 for i, c in enumerate(order)}
    lab = pd.Series([relabel[c] for c in ref], index=feats.index, name="cluster")
    out["membership"] = {str(i): [str(c) for c in lab.index[lab == i]] for i in sorted(lab.unique())}
    out["cluster_means"] = {str(i): {n: float(feats.loc[lab == i, n].mean()) for n, _, _ in E6_FEATURES} for i in sorted(lab.unique())}
    out["cluster_sizes"] = {str(i): int((lab == i).sum()) for i in sorted(lab.unique())}
    if prep is not None and "eu_accession_year" in prep.columns:
        acc = prep.groupby("eurostat_code")["eu_accession_year"].first()
        eu = pd.Series(np.where(acc.reindex(lab.index) >= 2004, "accession", "EU-14"), index=lab.index)
        e21 = prep[prep["year"] == prep["year"].max()].set_index("eurostat_code")["euro_member"].reindex(lab.index)
        cm = prep.groupby("eurostat_code")["debt_gdp_lag"].mean()
        debt_hi = pd.Series(np.where(cm.reindex(lab.index) > cm.median(), "high debt", "low debt"), index=lab.index)
        out["crosstabs"] = {
            "eu_group": pd.crosstab(lab, eu).to_dict(orient="index"),
            "euro_member_last_year": pd.crosstab(lab, e21.map({1.0: "euro", 0.0: "non-euro"})).to_dict(orient="index"),
            "e4a_debt_split": pd.crosstab(lab, debt_hi).to_dict(orient="index")}
        out["crosstabs"] = {k_: {str(a): {str(b): int(c) for b, c in v.items()} for a, v in d.items()} for k_, d in out["crosstabs"].items()}
    return out


# ---------------------------------------------------------------------------------------------
# Whole analysis
# ---------------------------------------------------------------------------------------------
def availability_facts(prep: pd.DataFrame, rule: pd.DataFrame, rule_info: dict, workbook_sha: str | None) -> dict:
    """Counts reported in the output (no outcome column used)."""
    w = prep[(prep["year"] >= RULE_WINDOW[0]) & (prep["year"] <= RULE_WINDOW[1])]
    e1 = w[w["F_raw"].notna()]
    long = prep[(prep["year"] >= RULE_WINDOW_LONG[0]) & (prep["year"] <= RULE_WINDOW_LONG[1])]
    nl = {int(y): float(rule.at["NL", y]) for y in range(2017, 2025)} if "NL" in rule.index else {}
    nl_rows = e1[e1["eurostat_code"] == "NL"]
    return {
        "workbook_sha256": workbook_sha, "dot_cells_by_index_year_2012_2024": {int(y): int(rule_info["dot_cells_by_year"][y]) for y in range(2012, 2025)} if rule_info else None,
        "window_rows": int(len(w)), "e1_rows": int(len(e1)), "e1_countries": int(e1["eurostat_code"].nunique()),
        "e1_rows_dropped": [(str(c), int(y)) for c, y in w.loc[w["F_raw"].isna(), ["eurostat_code", "year"]].itertuples(index=False)],
        "e1_rows_per_country": {str(k): int(v) for k, v in e1.groupby("eurostat_code").size().items() if v != e1.groupby("eurostat_code").size().max()},
        "e1_ws_positive_rows": int((e1["W_S"] > 0).sum()), "e1_ws_positive_countries": int(e1.loc[e1["W_S"] > 0, "eurostat_code"].nunique()), "e1_mean_ws": float(e1["W_S"].mean()),
        "e1_index": {"mean": float(e1["F_raw"].mean()), "sd_pop": float(e1["F_raw"].std(ddof=0)), "min": float(e1["F_raw"].min()), "max": float(e1["F_raw"].max())},
        "long_window_rows": int(len(long)), "long_window_numeric_rows": int(long["F_raw"].notna().sum()), "long_window_countries": int(long["eurostat_code"].nunique()),
        "long_window_dot_rows": {str(c): [int(y) for y in g["year"]] for c, g in long[long["F_raw"].isna()].groupby("eurostat_code")},
        "nl_raw_index_2017_2024": nl, "nl_rows_in_e1_index_years": sorted(set(int(y) - 1 for y in nl_rows["year"])), "nl_rows_in_e1_values": [float(v) for v in nl_rows["F_raw"]],
        "debt_missing_rows_full_sample": int(prep["debt_gdp_lag"].isna().sum()), "full_sample_rows": int(len(prep)),
    }


def file_hashes() -> dict[str, str]:
    files = {"exploratory.py": Path(__file__).resolve(), "m1.py": Path(m1.__file__).resolve(), "power_variants.py": Path(pv.__file__).resolve(), "power.py": Path(power.__file__).resolve(),
             "secondary.py": Path(secondary.__file__).resolve(), "docs/exploratory_spec.md": SPEC_FILE, "config/registry/exploratory.toml": REGISTRY_TOML}
    return {name: m1.file_sha256(path) for name, path in files.items()}


def new_results(*, source: str, n_boot: int, extract_hash: str | None, workbook_sha: str | None) -> dict:
    return {"source": source, "status": "partial", "stage": "start", "n_boot": n_boot, "n_boot_loo": B_LOCO, "seed": power.SEED, "seed_key": SEED_KEY, "expl_key": EXPL_KEY,
            "ci_level": CI_LEVEL, "bh_alpha": BH_Q, "family": [list(f) for f in FAMILY], "versions": {**m1.library_versions()}, "file_hashes": file_hashes(), "extract_hash": extract_hash,
            "workbook_sha256": workbook_sha, "estimator": m1.ESTIMATOR_ID, "not_run": NOT_RUN, "deviations": list(DEVIATIONS), "availability": None, "power": None, "models": {}, "e6": None, "multiplicity": None}


def run_estimates(extract: pd.DataFrame, rule: pd.DataFrame, results: dict, *, n_boot: int = B_MAIN, n_boot_loo: int = B_LOCO, log: Callable = print,
                  on_update: Callable[[dict], None] | None = None, only: Sequence[str] | None = None) -> dict:
    """All models. ``results`` may already hold earlier models (resume): a model with ``status == 'done'`` is reused."""
    prep = prepare(extract, rule)
    models = results["models"]

    def done(mid: str) -> bool:
        return mid in models and models[mid].get("done", False) and (only is None or True)

    def update() -> None:
        results["multiplicity"] = apply_family(models, results.get("power"))
        if on_update:
            on_update(results)

    def want(mid: str) -> bool:
        return only is None or mid in only

    win = lambda: window_frame(prep, *RULE_WINDOW)  # noqa: E731
    # ---- E1
    if want("E1") and not done("E1"):
        log("E1 ...")
        m = fit_ladder(lambda: build_e1(win(), "pooled", label="E1"), p_targets=["gamma_F"], n_boot=n_boot, log=log)
        m["sensitivities"] = {}
        in_force = m["in_force"] or "V0"
        m["companion_split"] = safe_fit(lambda: build_e1(win(), "split", label="E1-split"), in_force, p_targets=[], n_boot=n_boot)
        m["sensitivities"]["noage"] = safe_fit(lambda: build_e1(win(), "noage", label="E1-noage"), in_force, p_targets=["gamma_F"], n_boot=n_boot)
        long_f = lambda: window_frame(prep, *RULE_WINDOW_LONG)  # noqa: E731
        m["sensitivities"]["window_2012_2021"] = safe_fit(lambda: build_e1(long_f(), "pooled", single_era=True, label="E1-2012"), in_force, p_targets=["gamma_F"], n_boot=n_boot)
        m["sensitivities"]["presence_2012_2021"] = safe_fit(lambda: build_presence(window_frame(prep, *RULE_WINDOW_LONG, need_rule=False)), in_force, p_targets=["delta_P"], n_boot=n_boot)
        m["sensitivities"]["nl_include"] = nl_sensitivity(extract, rule, prep)
        m["loo"] = leave_one_out(win(), in_force, m["main"], n_boot_loo, log)
        m["done"] = True
        models["E1"] = m
        update()
    # ---- E2
    if want("E2") and not done("E2"):
        log("E2 ...")
        m = fit_ladder(lambda: build_e1(win(), "e2", label="E2"), p_targets=["delta_BF"], n_boot=n_boot, log=log)
        m["done"] = True
        models["E2"] = m
        update()
    # ---- E3
    if want("E3") and not done("E3"):
        log("E3 ...")
        main = safe_fit(lambda: build_e3(prep, "hinge")[0], "V7", p_targets=["delta_H"], n_boot=n_boot)
        m = {"in_force": "V7", "main": main, "by_estimator": {"V7": main}, "knot_info": build_e3(prep, "hinge")[1]}
        m["slopes"] = safe_fit(lambda: build_e3(prep, "slopes")[0], "V7", p_targets=[], n_boot=n_boot)
        m["terciles"] = safe_fit(lambda: build_e3(prep, "terciles")[0], "V7", p_targets=[], n_boot=n_boot)
        m["terciles_info"] = build_e3(prep, "terciles")[1]
        m["done"] = True
        models["E3"] = m
        update()
    # ---- E4
    for w in "abcd":
        mid = f"E4{w}"
        if want(mid) and not done(mid):
            log(f"{mid} ...")
            design, info = build_e4(prep, w, "pooled")
            tname = {"a": "delta_debt_between", "b": "delta_debt_within_time", "c": "delta_accession", "d": "delta_euro"}[w]
            main = safe_fit(lambda w=w: build_e4(prep, w, "pooled")[0], "V7", p_targets=[tname], n_boot=n_boot)
            m = {"in_force": "V7", "main": main, "by_estimator": {"V7": main}, "info": info}
            m["groups"] = safe_fit(lambda w=w: build_e4(prep, w, "groups")[0], "V7", p_targets=[], n_boot=n_boot)
            if main["status"] == "ok" and m["groups"]["status"] == "ok":
                g = m["groups"]["targets"]
                m["groups_difference_check"] = {"pooled_estimate": main["targets"][tname]["estimate"], "difference_of_group_estimates": g["beta_S_D1"]["estimate"] - g["beta_S_D0"]["estimate"]}
            if w == "d":
                m["mundlak"] = safe_fit(lambda: build_e4(prep, "d", "mundlak")[0], "V7", p_targets=[], n_boot=n_boot)
            m["done"] = True
            models[mid] = m
            update()
    # ---- E6
    if only is None or "E6" in only:
        if results.get("e6") is None:
            log("E6 ...")
            results["e6"] = run_e6(extract, prep)
            update()
    results["status"] = "complete" if all(models.get(mid, {}).get("done") for mid, _, _ in FAMILY if mid in ("E1", "E2", "E3", "E4a", "E4b", "E4c", "E4d")) and results.get("e6") else "partial"
    update()
    return results


def nl_sensitivity(extract: pd.DataFrame, rule: pd.DataFrame, prep: pd.DataFrame) -> dict:
    """The NL-including sensitivity is identical by construction (not re-estimated): asserts the frames are equal for year <= 2021."""
    inc = prepare(extract, rule, nl_policy="include", accession=None if "eu_accession_year" not in extract.columns else None)
    a = prep[prep["year"] <= 2021][["eurostat_code", "year", "F_raw"]].reset_index(drop=True)
    b = inc[inc["year"] <= 2021][["eurostat_code", "year", "F_raw"]].reset_index(drop=True)
    identical = bool(a.equals(b))
    nl_rows = prep[(prep["eurostat_code"] == "NL") & (prep["year"] <= 2021)]
    max_index_year = int(nl_rows.loc[nl_rows["F_raw"].notna(), "year"].max() - 1)
    return {"status": "not re-estimated: identical by construction", "frames_identical_for_year_le_2021": identical, "max_nl_index_year_used": max_index_year}


def leave_one_out(frame: pd.DataFrame, kind: str, main: dict, n_boot: int, log: Callable) -> dict:
    """E1 leave-one-country-out: gamma_F estimate, interval and p of every fit (estimator in force, B = 999)."""
    rows = []
    for c in sorted(frame["eurostat_code"].unique()):
        sub = frame[frame["eurostat_code"] != c]
        res = safe_fit(lambda sub=sub: build_e1(sub, "pooled", label=f"E1-loo-{c}"), kind, p_targets=["gamma_F"], n_boot=n_boot)
        row = {"dropped": str(c), "status": res["status"], "n_obs": res.get("n_obs")}
        if res["status"] == "ok":
            row.update(res["targets"]["gamma_F"])
        else:
            row["error"] = res.get("error")
        rows.append(row)
    ok = [r for r in rows if r["status"] == "ok"]
    out: dict[str, Any] = {"estimator": kind, "n_boot": n_boot, "fits": rows}
    if ok and main.get("status") == "ok":
        b0 = main["targets"]["gamma_F"]["estimate"]
        ex0 = main["targets"]["gamma_F"]["ci_lo"] > 0 or main["targets"]["gamma_F"]["ci_hi"] < 0
        est = np.array([r["estimate"] for r in ok])
        out.update({"min_estimate": float(est.min()), "max_estimate": float(est.max()), "most_influential": max(ok, key=lambda r: abs(r["estimate"] - b0))["dropped"],
                    "n_sign_changes": int(sum(np.sign(r["estimate"]) != np.sign(b0) for r in ok)),
                    "n_exclude_zero_changes": int(sum((r["ci_lo"] > 0 or r["ci_hi"] < 0) != ex0 for r in ok)), "n_failed": len(rows) - len(ok)})
    log(f"    LOO done ({len(ok)} ok)")
    return out


# ---------------------------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------------------------
def clean(obj: Any) -> Any:
    """JSON-safe copy (numpy scalars to Python, NaN/inf to None, tuples to lists)."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        v = float(obj)
        return v if np.isfinite(v) else None
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


def to_json(results: dict) -> str:
    return json.dumps(clean(results), indent=2, allow_nan=False) + "\n"


def _f(v: float | None, d: int = 3) -> str:
    return "-" if v is None else f"{v:.{d}f}"


def _iv(e: dict, d: int = 3) -> str:
    return f"{_f(e['estimate'], d)} [{_f(e['ci_lo'], d)}, {_f(e['ci_hi'], d)}]"


def _targets_table(res: dict, names: Sequence[str] | None = None, p: bool = True) -> list[str]:
    if res.get("status") != "ok":
        return [f"*{res.get('status')}: {res.get('error')}*", ""]
    lines = ["| target | estimate [95% bootstrap-t interval] | raw p |", "|---|---|---|"]
    for name, e in res["targets"].items():
        if names is not None and name not in names:
            continue
        lines.append(f"| {name} | {_iv(e)} | {_f(e.get('p_bootstrap'), 4) if 'p_bootstrap' in e else 'not tested'} |")
    lines.append("")
    return lines


def render_markdown(results: dict) -> str:
    L: list[str] = []
    L += ["# Exploratory models E1-E4, E6", "",
          f"Status: {results['status']} (stage {results.get('stage')}). Source: `{results['source']}`. **Exploratory.** All results are associations; scheduled elections are predetermined, not exogenous. "
          "The fiscal-rule index is a de jure design-strength score of national numerical rules, not enforcement or compliance. Specification: `docs/exploratory_spec.md` (written before any exploratory result). "
          f"Estimates are in pp of potential GDP (CAPB, `UBLGBP`, surplus positive). B = {results['n_boot']} (leave-one-out {results['n_boot_loo']}), seed key {results['seed_key']}, Rademacher weights, "
          "whole feasible procedure re-estimated in every bootstrap sample. CR1 p-values are not primary results and are not shown.", ""]
    L += ["## Deviations", ""]
    devs = results.get("deviations") or []
    L += [f"* {d}" for d in devs] if devs else ["None recorded."]
    L += [""]
    av = results.get("availability")
    if av:
        L += ["## Availability facts (no outcome column used)", "",
              f"* Workbook SHA-256 `{av['workbook_sha256']}` (equals the manifest). E1 window 2016-2021: {av['window_rows']} country-years, **E1 N = {av['e1_rows']}**, {av['e1_countries']} countries; dropped (lagged index missing): {av['e1_rows_dropped']}; countries with fewer rows: {av['e1_rows_per_country']}.",
              f"* W_S > 0 in {av['e1_ws_positive_rows']} rows ({av['e1_ws_positive_countries']} countries), mean W_S {av['e1_mean_ws']:.3f}. Lagged raw index: mean {av['e1_index']['mean']:.3f}, SD {av['e1_index']['sd_pop']:.3f}, range {av['e1_index']['min']:.3f} to {av['e1_index']['max']:.3f}.",
              f"* Long window 2012-2021: {av['long_window_rows']} rows, numeric lagged index in {av['long_window_numeric_rows']}; '.' rows by country: {av['long_window_dot_rows']}.",
              f"* NL raw index 2017-2024: {av['nl_raw_index_2017_2024']}; NL index years used by E1 rows: {av['nl_rows_in_e1_index_years']} (values {[round(v, 4) for v in av['nl_rows_in_e1_values']]}).",
              f"* Lagged debt missing in {av['debt_missing_rows_full_sample']} of {av['full_sample_rows']} full-sample rows.", ""]
    pw = results.get("power")
    if pw:
        c = pw["calibration"]
        L += ["## Power block (written before any E1/E2 estimate was computed)", "",
              f"Noise calibration (Gate 3b, `power.calibrate` of the V0n design): corrected rho {c['rho_corrected']:.3f} (Gate 3b {c['rho_gate3b']}; reproduces: {c['reproduces_gate3b']}), country residual SD {c['sigma_min']:.2f} to {c['sigma_max']:.2f} pp. "
              f"Settings: {pw['settings']}. Scenarios: AR(1) at the corrected rho and at rho = 0; the block-bootstrap scenario is not run for the window (its residual grid is indexed to 27 years). "
              "MDE = effect with 80% power, alpha 0.05, two-sided, in the target's units (E1: pp per +1 SD of the index, 1 SD = the sd_F_raw index points).", "",
              "| model | target | estimator | scenario | CR1 size | CR1 MDE | CR1 MDE size-adj. | wild-bootstrap size | wild-bootstrap MDE | MDE, index points |", "|---|---|---|---|---|---|---|---|---|---|"]
        for mid, entry in pw["models"].items():
            for kind, sc in entry["by_estimator"].items():
                for scen, r in sc.items():
                    w = r.get("wcb") or {}
                    L.append(f"| {mid} | {entry['target']} | {kind} | {scen} | {_f(r['cr1']['size'], 3)} | {_f(r['cr1']['mde'])} | {_f(r['cr1']['mde_size_adjusted'])} | {_f(w.get('size'), 3)} | {_f(w.get('mde'))} | {_f(w.get('mde_index_points'))} |")
        di = pw["design_information"]
        L += ["", "Design information (squared norm of the residualised target regressor; larger = more information): " + "; ".join(f"{k} {v['r_squared_norm']:.2f}" for k, v in di.items()) + ".", ""]
        pc = pw.get("promotion_check")
        if pc:
            L += ["**E1 promotion check** (wild-bootstrap MDE of `gamma_F` per +1 SD at the estimated rho; line 1.0 pp, G2 interaction line 0.75 pp beside it):", ""]
            for kind in KINDS:
                if kind in pc:
                    L.append(f"* {kind}: MDE {_f(pc[kind]['wcb_mde_pp_per_sd_rho_hat'])} pp (rho 0: {_f(pc[kind]['wcb_mde_pp_per_sd_rho0'])}); within 1.0 pp: {pc[kind]['within_1.0pp']}; within 0.75 pp: {pc[kind]['within_0.75pp']}.")
            L += ["", "Promotion would require an amendment in `docs/amendments.md`; this run promotes nothing and E1 stays exploratory.", ""]
    mult = results.get("multiplicity")
    if mult:
        L += ["## Family (Benjamini-Hochberg q = 0.05 over the pre-listed seven coefficients; Benjamini-Yekutieli beside it)", "",
              f"m listed {mult['m_listed']}, m used {mult['m_used']}; BH rejections {mult['n_bh_reject']}; BY rejections {mult['n_by_reject']}. Raw p: null-imposed wild-cluster bootstrap-t; q: adjusted within this family.", "",
              "| model | coefficient | estimator | N (countries) | estimate [95% interval] | raw p | BH q | BY q | MDE (wild bootstrap, rho-hat / rho 0) | reading |", "|---|---|---|---|---|---|---|---|---|---|"]
        for r in mult["rows"]:
            if r["status"] != "ok":
                L.append(f"| {r['model']} | {r['target']} | - | - | failed | - | - | - | - | - |")
                continue
            mde = r.get("mde") or {}
            hat, z0 = (mde.get("ar1_rho_hat") or {}), (mde.get("ar1_rho0") or {})
            md = (f"{_f(hat.get('wild_bootstrap_mde'))} / {_f(z0.get('wild_bootstrap_mde'))}" if hat.get("wild_bootstrap_mde") is not None
                  else f"CR1 size-adj. {_f(hat.get('cr1_mde_size_adjusted'))} / {_f(z0.get('cr1_mde_size_adjusted'))}")
            L.append(f"| {r['model']} | {r['target']} | {r['estimator']} | {r['n_obs']} ({r['n_countries']}) | {_iv(r)} | {_f(r['p_bootstrap'], 4)} | {_f(r['q_bh'], 4)} | {_f(r['q_by'], 4)} | {md} | {r['label']}{'; uninformative (half-width above 1.0 pp)' if r['uninformative'] else ''} |")
        L += ["", "Units: E1, E2, E3 per +1 SD of the moderator(s) as defined in the spec; E4 the difference between the two groups. No equivalence reading against 0.5 pp (that threshold was set for beta_S only).", ""]
    models = results.get("models", {})
    e1 = models.get("E1")
    if e1:
        L += ["## E1: fiscal-rule moderation, 2016-2021", "", f"Estimator in force: **{e1['in_force']}**; fallback triggered: {e1['fallback_triggered']}.", "", "Feasibility checks (F1-F4):", ""]
        for kind in KINDS:
            r = e1["by_estimator"][kind]
            L.append(f"* {KIND_LABEL[kind]}: {r['status']}; checks {r.get('checks')}" + (f"; error {r.get('error')}" if r.get("error") else ""))
        L += ["", "### Primary (estimator in force), all targets", ""] + _targets_table(e1["main"])
        L += ["### Estimator ladder for `gamma_F` (V7, V3, V0; sensitivity rows, none selected)", "", "| estimator | status | N | gamma_F [95% interval] | raw p |", "|---|---|---|---|---|"]
        for kind in KINDS:
            r = e1["by_estimator"][kind]
            if r["status"] == "ok":
                t = r["targets"]["gamma_F"]
                L.append(f"| {kind}{' (in force)' if kind == e1['in_force'] else ''} | ok | {r['n_obs']} | {_iv(t)} | {_f(t.get('p_bootstrap'), 4)} |")
            else:
                L.append(f"| {kind} | {r['status']} | - | - | - |")
        L += ["", "### Companion (descriptive, interval only): between/within split of the index", ""] + _targets_table(e1["companion_split"], ["gamma_F_B", "gamma_F_W"])
        for key, title, tgt in (("noage", "Without the ageing interactions", "gamma_F"), ("window_2012_2021", "Long window 2012-2021 (back-cast zone 2012-2015 flagged; single era term)", "gamma_F"),
                                ("presence_2012_2021", "Rule-presence dummy, 2012-2021 ('.' coded 0; ambiguous reading)", "delta_P")):
            r = e1["sensitivities"].get(key)
            if r is None:
                continue
            L += [f"### Sensitivity: {title}", ""]
            if r["status"] == "ok":
                t = r["targets"][tgt]
                L += [f"N = {r['n_obs']} ({r['n_countries']} countries), estimator {r['estimator']}: **{tgt} = {_iv(t)}**, raw p {_f(t.get('p_bootstrap'), 4)}.", ""]
            else:
                L += [f"{r['status']}: {r.get('error')}", ""]
        nl = e1["sensitivities"].get("nl_include")
        if nl:
            L += ["### Sensitivity: NL 2021-22 included", "", f"{nl['status']}. Frames identical for year <= 2021: {nl['frames_identical_for_year_le_2021']}; largest NL index year used: {nl['max_nl_index_year_used']}.", ""]
        loo = e1.get("loo") or {"estimator": "-", "n_boot": 0, "fits": []}
        L += [f"### Leave-one-country-out ({len(loo['fits'])} fits, {loo['estimator']}, B = {loo['n_boot']})", ""]
        if "min_estimate" in loo:
            L += [f"Range of `gamma_F`: {_f(loo['min_estimate'])} to {_f(loo['max_estimate'])}; most influential country: {loo['most_influential']}; sign changes: {loo['n_sign_changes']}; changes of the exclude-zero reading: {loo['n_exclude_zero_changes']}; failed fits: {loo['n_failed']}.", ""]
        L += ["| dropped | N | gamma_F [95% interval] | raw p |", "|---|---|---|---|"]
        for r in loo["fits"]:
            L.append(f"| {r['dropped']} | {r['n_obs']} | {_iv(r) if r['status'] == 'ok' else r['status']} | {_f(r.get('p_bootstrap'), 3) if r['status'] == 'ok' else '-'} |")
        L += [""]
    e2 = models.get("E2")
    if e2:
        L += ["## E2: triple interaction (E1 window; severely underpowered)", "", f"Estimator in force: **{e2['in_force']}**; fallback triggered: {e2['fallback_triggered']}.", ""] + _targets_table(e2["main"])
        L += ["| estimator | status | delta_BF [95% interval] | raw p |", "|---|---|---|---|"]
        for kind in KINDS:
            r = e2["by_estimator"][kind]
            L.append(f"| {kind} | {r['status']} | " + (f"{_iv(r['targets']['delta_BF'])} | {_f(r['targets']['delta_BF'].get('p_bootstrap'), 4)} |" if r["status"] == "ok" else "- | - |"))
        L += [""]
    e3 = models.get("E3")
    if e3:
        L += ["## E3: nonlinear ageing (between component, knot at the country median)", "", f"Knot and group sizes: {e3['knot_info']}.", ""] + _targets_table(e3["main"], ["beta_S", "gamma_B_low", "delta_H", "gamma_W"])
        L += ["Slopes below / above the knot (descriptive, interval only):", ""] + _targets_table(e3["slopes"], ["slope_below", "slope_above"])
        L += [f"Terciles of the between component (descriptive, interval only; members {e3['terciles_info']}):", ""] + _targets_table(e3["terciles"], ["tau_mid", "tau_top"])
    for w in "abcd":
        e4 = models.get(f"E4{w}")
        if not e4:
            continue
        L += [f"## E4{w}", "", f"Info: {e4['info']}.", ""] + _targets_table(e4["main"], ["beta_S", {"a": "delta_debt_between", "b": "delta_debt_within_time", "c": "delta_accession", "d": "delta_euro"}[w]])
        L += ["Group-specific associations (descriptive, interval only):", ""] + _targets_table(e4["groups"], ["beta_S_D1", "beta_S_D0"])
        if "groups_difference_check" in e4:
            L += [f"Check: pooled difference {e4['groups_difference_check']['pooled_estimate']:.6f} vs difference of group estimates {e4['groups_difference_check']['difference_of_group_estimates']:.6f}.", ""]
        if "mundlak" in e4:
            L += ["Mundlak split of the euro dummy (descriptive, interval only):", ""] + _targets_table(e4["mundlak"], ["delta_euro_between", "delta_euro_within"])
    e6 = results.get("e6")
    if e6:
        L += ["## E6: country typology (descriptive only; not causal; no inference on membership)", "",
              "Features (country means over the confirmatory rows; z-scored over the 27 countries): " + "; ".join(f"{f['name']} ({f['column']}, {f['unit']})" for f in e6["features"]) + ".", "",
              "| k | silhouette | smallest cluster | inertia | admissible |", "|---|---|---|---|---|"]
        for r in e6["k_table"]:
            L.append(f"| {r['k']} | {_f(r['silhouette'])} | {r['smallest_cluster']} | {_f(r['inertia'], 2)} | {r['admissible']} |")
        if e6.get("chosen_k"):
            s = e6["stability"]
            L += ["", f"Chosen k = {e6['chosen_k']} (rule: {e6['rule']}); silhouette {e6['silhouette']:.3f} ({e6['silhouette_reading']}, Kaufman-Rousseeuw scale).",
                  f"Stability over {s['n_seeds']} single-start seeds: share equal to the reference partition {s['share_equal_to_reference']:.2f}; share reaching the best inertia {s['share_reaching_best_inertia']:.2f}; ARI min {s['ari_min']:.3f}, median {s['ari_median']:.3f}; ARI Ward vs reference {s['ari_ward_vs_reference']:.3f}.", "",
                  "| cluster | n | members | " + " | ".join(f["name"] for f in e6["features"]) + " |", "|---|---|---|" + "---|" * len(e6["features"])]
            for c, members in e6["membership"].items():
                L.append(f"| {c} | {e6['cluster_sizes'][c]} | {', '.join(members)} | " + " | ".join(_f(e6["cluster_means"][c][f["name"]], 2) for f in e6["features"]) + " |")
            for name, tab in (e6.get("crosstabs") or {}).items():
                L += ["", f"Cross-tab with {name}: {tab}"]
        else:
            L += ["", f"{e6.get('note')}"]
        L += [""]
    L += ["## Not run", ""] + [f"* {k}: {v}" for k, v in results["not_run"].items()]
    L += ["", "## Provenance", "", f"* extract hash `{results.get('extract_hash')}`; versions {results['versions']}", "* code and spec hashes: " + "; ".join(f"{k} `{v[:12]}`" for k, v in results["file_hashes"].items()), ""]
    return "\n".join(L)


def forest_plot(results: dict, path: Path) -> Path:
    """Forest plot of the seven family coefficients (95% bootstrap-t intervals), units per row, BH decision marked; 300 dpi; source line."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    mult = results["multiplicity"]
    rows = [r for r in mult["rows"]]
    labels = {"E1": "E1  rule index (pooled), per +1 SD of index", "E2": "E2  ageing x rule index, per +1 SD each (E1 window)", "E3": "E3  ageing slope change above median (hinge)",
              "E4a": "E4a  high- minus low-debt country", "E4b": "E4b  debt above vs below year median", "E4c": "E4c  accession member minus EU-14", "E4d": "E4d  euro minus non-euro"}
    ok = [r for r in rows if r["status"] == "ok"]
    lo_all = min([r["ci_lo"] for r in ok] + [0.0])
    hi_all = max([r["ci_hi"] for r in ok] + [0.0])
    # clip the axis to the central part so that the narrow intervals stay readable; clipped intervals get arrow heads
    spans = sorted(r["ci_hi"] - r["ci_lo"] for r in ok)
    clip = max(4.0, 1.6 * spans[len(spans) // 2]) if ok else 4.0
    xlo, xhi = max(lo_all, -clip), min(hi_all, clip)
    pad = 0.08 * (xhi - xlo)
    xlo, xhi = xlo - pad, xhi + pad
    fig, ax = plt.subplots(figsize=(10.5, 0.62 * len(rows) + 2.2))
    ink, muted, accent = "#1f2933", "#7b8794", "#b3261e"
    for i, r in enumerate(rows):
        y = len(rows) - 1 - i
        label = labels[r["model"]]
        ax.text(-0.01, y, label, transform=ax.get_yaxis_transform(), ha="right", va="center", fontsize=9, color=ink)
        if r["status"] != "ok":
            ax.text(0.0, y, "failed", va="center", fontsize=8, color=muted)
            continue
        lo, hi = r["ci_lo"], r["ci_hi"]
        ax.plot([max(lo, xlo), min(hi, xhi)], [y, y], color=ink, lw=1.8, solid_capstyle="butt")
        if lo < xlo:
            ax.annotate("", xy=(xlo, y), xytext=(xlo + 0.02 * (xhi - xlo), y), arrowprops=dict(arrowstyle="->", color=ink, lw=1.4))
        if hi > xhi:
            ax.annotate("", xy=(xhi, y), xytext=(xhi - 0.02 * (xhi - xlo), y), arrowprops=dict(arrowstyle="->", color=ink, lw=1.4))
        ax.plot([r["estimate"]], [y], "o", ms=7, mfc=accent if r["bh_reject"] else "white", mec=accent if r["bh_reject"] else ink, mew=1.5)
        ax.text(1.01, y, f"{r['estimate']:+.2f} [{lo:+.2f}, {hi:+.2f}]\np {r['p_bootstrap']:.3f}, q {r['q_bh']:.3f}, N {r['n_obs']}", transform=ax.get_yaxis_transform(), va="center", fontsize=7.5, color=ink)
    ax.axvline(0.0, color=muted, lw=1.0, ls="--", zorder=0)
    ax.set_yticks([])
    ax.set_ylim(-0.7, len(rows) - 0.3)
    ax.set_xlim(xlo, xhi)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.set_xlabel("Association with a full year of pre-election exposure to a scheduled election (W_S), difference in pp of potential GDP\n(unit per row: per +1 SD of the moderator, or difference between groups)", fontsize=9)
    fig.suptitle(f"Exploratory models: coefficients with 95% bootstrap-t intervals (wild-cluster, B = {results['n_boot']})\nFilled marker: Benjamini-Hochberg q <= 0.05 over the seven family coefficients; hollow: not rejected. Associations only.", x=0.01, ha="left", fontsize=10, color=ink)
    clipped = any(r["status"] == "ok" and (r["ci_lo"] < xlo or r["ci_hi"] > xhi) for r in rows)
    fig.text(0.01, 0.005, SOURCE_LINE + (". Arrows: interval extends beyond the axis." if clipped else "."), fontsize=7, color=muted, ha="left", va="bottom")
    fig.subplots_adjust(left=0.34, right=0.80, top=0.84, bottom=0.17)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=300)
    plt.close(fig)
    return path


def write_results(results: dict, out_dir: Path | None = None, fig_dir: Path | None = None, tag_lookup: Callable[[], bool] | None = None, figure: bool = True) -> list[Path]:
    """Write ``exploratory.json``, ``.md`` and the forest plot. Default folders need real-panel results AND the tag (as in ``m1``)."""
    default = out_dir is None or Path(out_dir).resolve() == RESULTS_DIR.resolve()
    if default:
        if results["source"] != SOURCE_REAL:
            raise m1.ResultsNotAllowed("only results from the real gold panel may be written to reports/results")
        m1.require_preregistration_tag(tag_lookup)
    target = RESULTS_DIR if out_dir is None else Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    paths = [target / f"{RESULT_STEM}.json", target / f"{RESULT_STEM}.md"]
    paths[0].write_text(to_json(results), encoding="utf-8", newline="\n")
    paths[1].write_text(render_markdown(clean(results)), encoding="utf-8", newline="\n")
    if figure and results.get("multiplicity") and results["multiplicity"]["m_used"] > 0:
        paths.append(forest_plot(clean(results), (FIGURES_DIR if fig_dir is None else Path(fig_dir)) / FIGURE_NAME))
    return paths


# ---------------------------------------------------------------------------------------------
# Real panel runner (guarded)
# ---------------------------------------------------------------------------------------------
def run_real(stage: str = "all", *, n_boot: int = B_MAIN, n_boot_loo: int = B_LOCO, workers: int = 1, tag_lookup: Callable[[], bool] | None = None,
             previous: dict | None = None, on_update: Callable[[dict], None] | None = None, power_settings: pv.Settings = pv.FULL, log: Callable = print) -> dict:
    """Run the stages on the real gold panel (read only through :func:`m1.load_real_panel`, which refuses without the tag)."""
    extract, digest = m1.load_real_panel(tag_lookup=tag_lookup)
    sha = verify_workbook()
    rule, info = read_cfrsi()
    same = previous is not None and (previous.get("n_boot"), previous.get("extract_hash")) == (n_boot, digest)
    results = previous if same else new_results(source=SOURCE_REAL, n_boot=n_boot, extract_hash=digest, workbook_sha=sha)
    results["file_hashes"] = file_hashes()
    results["deviations"] = list(DEVIATIONS)
    prep = prepare(extract, rule)
    results["availability"] = availability_facts(prep, rule, info, sha)
    if stage in ("power", "all") and results.get("power") is None:
        log("power block ...")
        results["stage"] = "power"
        results["power"] = power_block(extract, rule, settings=power_settings, workers=workers, log=log)
        if on_update:
            on_update(results)
    if stage in ("estimates", "all"):
        if results.get("power") is None:
            raise RuntimeError("the power block must be written before the estimates (run --stage power first)")
        results["stage"] = "estimates"
        run_estimates(extract, rule, results, n_boot=n_boot, n_boot_loo=n_boot_loo, log=log, on_update=on_update)
    return results


def main(argv: list[str] | None = None) -> int:
    """``python src/models/py/exploratory.py --stage power|estimates|all``: the power block is written before any estimate exists."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report whether the pre-registration tag exists and exit")
    parser.add_argument("--stage", choices=("power", "estimates", "all"), default="all")
    parser.add_argument("--n-boot", type=int, default=B_MAIN)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--fresh", action="store_true", help="ignore an earlier partial exploratory.json")
    args = parser.parse_args(argv)
    if args.check:
        present = m1.tag_exists()
        print(f"tag {m1.PREREG_TAG}: {'present' if present else 'ABSENT (the real outcome must not be analysed)'}")
        return 0 if present else 1
    json_path = RESULTS_DIR / f"{RESULT_STEM}.json"
    previous = json.loads(json_path.read_text(encoding="utf-8")) if json_path.exists() and not args.fresh else None

    def update(partial: dict) -> None:
        write_results(partial, figure=False)
        print(f"updated ({partial.get('stage')})", flush=True)

    try:
        results = run_real(args.stage, n_boot=args.n_boot, workers=args.workers, previous=previous, on_update=update, log=lambda s: print(s, flush=True))
    except m1.PreregistrationTagMissing as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 1
    for path in write_results(results):
        print(f"written {path.relative_to(PROJECT_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
