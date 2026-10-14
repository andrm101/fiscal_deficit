"""Assembly, report and figures of the predictive module (stages are run and cached by ``predictive.py``).

Usage: ``.venv/Scripts/python.exe src/models/py/predictive_report.py --stage all`` (stages P, H, oracle, loco, event run in that order;
each stage's fits are cached under ``data/interim/predictive_cache`` and the JSON/markdown are rewritten after every stage).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import predictive as pr  # noqa: E402

YEARS_P = list(range(2009, 2022))
YEARS_H = [2022, 2023]
TABLE_MODELS = ["P0", "P1a-B1", "P1a-B2", "P1b-B1", "P1b-B2"]
ERA_P = {"2009-2015": range(2009, 2016), "2016-2021": range(2016, 2022)}


def _clean(o: Any) -> Any:
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def _f(x: Any, d: int = 3) -> str:
    return "n/a" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{d}f}"


def _ci(ci: Any, d: int = 3) -> str:
    return "n/a" if ci is None else f"[{ci[0]:.{d}f}, {ci[1]:.{d}f}]"


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


# ---------------------------------------------------------------------------------------------
# Computation
# ---------------------------------------------------------------------------------------------
def forecasts(op: pd.DataFrame, results: list[dict[str, Any]], origins: tuple[int, ...]) -> pd.DataFrame:
    f = pr.collect_forecasts(op, results, pr.model_label)
    return pd.concat([f, pr.add_benchmarks(op, origins)], ignore_index=True)


def cubes_of(f: pd.DataFrame, codes: list[str], years: list[int]) -> dict[str, np.ndarray]:
    return {m: pr.error_cube(f, m, codes, years) for m in sorted(f["model"].unique())}


def block_tables(f: pd.DataFrame, codes: list[str], years: list[int], idx: np.ndarray) -> dict[str, Any]:
    cubes = cubes_of(f, codes, years)
    acc = {m: pr.accuracy_row(c) for m, c in cubes.items()}
    ci = pr.boot_accuracy(cubes, idx)
    p0 = acc["P0"]["rmse"]
    for m in acc:
        acc[m].update(ci[m])
        acc[m]["ratio"] = acc[m]["rmse"] / p0
        acc[m]["skill"] = 1 - (acc[m]["rmse"] / p0) ** 2
        acc[m]["complete"] = acc[m]["n"] == len(codes) * len(years)
    by_year = {m: [pr.rmse(c[:, j][np.isfinite(c[:, j])]) for j in range(len(years))] for m, c in cubes.items()}
    return {"cubes": cubes, "accuracy": acc, "rmse_by_year": by_year}


def calibration_table(f: pd.DataFrame, codes: list[str], idx: np.ndarray) -> dict[str, Any]:
    out = {}
    for m in sorted(f["model"].unique()):
        s = f[f["model"] == m]
        if s["yhat"].nunique() <= 1:
            out[m] = {"slope": None, "intercept": None, "note": "constant forecast"}
            continue
        per = np.zeros((len(codes), 5))
        for i, c in enumerate(codes):
            q = s[s["code"] == c]
            x, y = q["yhat"].to_numpy(float), q["y"].to_numpy(float)
            per[i] = [len(q), x.sum(), y.sum(), (x * x).sum(), (x * y).sum()]
        r = pr.calibration_boot(per, idx)
        lo, hi = r["slope_ci"]
        r["reading"] = "over-dispersed forecasts (slope below 1)" if hi < 1 else ("under-dispersed forecasts (slope above 1)" if lo > 1 else "compatible with calibration")
        out[m] = r
    return out


def group_tables(f: pd.DataFrame, ref: pd.DataFrame, models: list[str]) -> dict[str, Any]:
    d = f[f["model"].isin(models)].merge(ref, on=["code", "fy"], how="left")
    d["e"] = d["y"] - d["yhat"]

    def cell(df: pd.DataFrame) -> dict[str, Any]:
        return {m: {"rmse": pr.rmse(g["e"]), "mae": pr.mae(g["e"]), "n": int(len(g))} for m, g in df.groupby("model")}

    out: dict[str, Any] = {"country": {c: cell(g) for c, g in d.groupby("code")}}
    out["era"] = {name: cell(d[d["fy"].isin(list(yrs))]) for name, yrs in ERA_P.items()}
    out["era"]["pre-2008"] = "no test rows"
    out["regime"] = {
        "euro (at origin)": cell(d[d["euro_T"] == 1]), "non-euro (at origin)": cell(d[d["euro_T"] == 0]),
        "known election exposure Wk_next >= 0.5": cell(d[d["Wk_next"] >= 0.5]), "Wk_next < 0.5": cell(d[d["Wk_next"] < 0.5]),
        "ex-post: realised early-election exposure W_E > 0 (not knowable)": cell(d[d["fW_E"] > 0]), "ex-post: W_E = 0": cell(d[d["fW_E"] == 0]),
    }
    out["sensitivity"] = {"all": cell(d), "excluding IE 2010-2011": cell(d[~((d["code"] == "IE") & d["fy"].isin([2010, 2011]))]), "excluding 2020-2021": cell(d[~d["fy"].isin([2020, 2021])])}
    return out


def importance_summary(res: list[dict[str, Any]], model: str, codes: list[str], idx: np.ndarray) -> dict[str, Any]:
    rs = [r for r in res if r["model"] == model and r["set"] == "B2" and r["scheme"] == "CD" and r.get("status") == "ok" and "importance" in r]
    if not rs:
        return {}
    items = list(rs[0]["importance"]["inc"].keys())
    base = np.zeros(len(codes))
    inc = {k: np.zeros(len(codes)) for k in items}
    by_origin = {k: {} for k in items}
    for r in rs:
        imp = r["importance"]
        cidx = [codes.index(c) for c in imp["codes"]]
        b = np.array(imp["base_e2"])
        np.add.at(base, cidx, b)
        for k in items:
            v = np.array(imp["inc"][k])
            np.add.at(inc[k], cidx, v)
            by_origin[k][r["origin"]] = float(100 * v.sum() / b.sum())
    out = {}
    for k in items:
        pooled = 100 * inc[k].sum() / base.sum()
        boot = 100 * inc[k][idx].sum(axis=1) / base[idx].sum(axis=1)
        out[k] = {"pooled_pct": float(pooled), "ci": pr.pct_interval(boot), "by_origin": by_origin[k]}
    ale = [r["importance"].get("ale") for r in rs if r["origin"] == pr.ORIGINS_P[-1]]
    return {"items": out, "ale": ale[0] if ale and ale[0] else {}, "n_origins": len(rs)}


def hyper_summary(res: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for r in res:
        if r.get("status") != "ok":
            continue
        key = pr.model_label(r)
        h = r["hyper"]
        out.setdefault(key, []).append({"origin": r["origin"], **{k: v for k, v in h.items() if k != "dropped"}})
    return out


def compute_main(op: pd.DataFrame, resP: list[dict[str, Any]], resH: list[dict[str, Any]] | None, resO: list[dict[str, Any]] | None) -> dict[str, Any]:
    codes = sorted(op["code"].unique())
    idx = pr.boot_indices(len(codes), key=0)
    ref = op[["code", "forecast_year", "euro_T", "Wk_next", "fW_E"]].rename(columns={"forecast_year": "fy"})
    out: dict[str, Any] = {"codes": codes}
    failed = [pr.job_name(r) for r in resP + (resH or []) + (resO or []) if r.get("status") != "ok"]
    out["failed_jobs"] = failed
    allP = resP + (resO or [])
    fP = forecasts(op, [r for r in allP if r["origin"] in pr.ORIGINS_P], pr.ORIGINS_P)
    bt = block_tables(fP, codes, YEARS_P, idx)
    cubes = bt["cubes"]
    out["P"] = {"accuracy": bt["accuracy"], "rmse_by_year": bt["rmse_by_year"], "years": YEARS_P}
    fam = pr.family_tests({m: cubes[m] for m in cubes}, idx)
    out["family"] = fam
    out["family_sensitivity_excl_2020_2021"] = pr.family_tests(cubes, idx, drop_years=(2020, 2021), years=YEARS_P)
    # absolute-loss DM (descriptive) and DM of every model vs P0 (descriptive, unadjusted)
    out["dm_abs"] = {name: pr.dm_hln(pr.loss_differential(cubes[b], cubes[m], "abs")) for name, m, b in pr.HOLM_FAMILY if m in cubes and b in cubes}
    out["dm_vs_p0_all"] = {m: pr.dm_hln(pr.loss_differential(cubes["P0"], c)) for m, c in cubes.items() if m != "P0"}
    desc = {}
    for model in ("P1a", "P1b"):
        for s in ("B2p", "B2d", "B2o", "B2f"):
            a, b = f"{model}-{s}", f"{model}-B1"
            if a in cubes and b in cubes:
                desc[f"{model}: {s} vs B1"] = {**pr.dm_hln(pr.loss_differential(cubes[b], cubes[a])), **pr.cluster_mse_difference(cubes[b], cubes[a], idx)}
        for s in ("B2o", "B2f"):
            a, b = f"{model}-{s}", f"{model}-B2"
            if a in cubes and b in cubes:
                desc[f"{model}: {s} vs B2"] = {**pr.dm_hln(pr.loss_differential(cubes[b], cubes[a])), **pr.cluster_mse_difference(cubes[b], cubes[a], idx)}
    out["descriptive_dm"] = desc
    out["autocorr_lag1"] = {r["comparison"]: r.get("lag1") for r in fam if r["status"] == "ok"}
    out["calibration"] = calibration_table(fP, codes, idx)
    out["groups"] = group_tables(fP, ref, TABLE_MODELS)
    out["groups_all_models"] = group_tables(fP, ref, sorted(fP["model"].unique()))["sensitivity"]["all"]
    out["hyper"] = hyper_summary([r for r in resP if r.get("status") == "ok" and r["origin"] in pr.ORIGINS_P and r["scheme"] == "CD" and r["set"] in ("B1", "B2")])
    out["importance"] = {m: importance_summary(resP, m, codes, idx) for m in ("P1a", "P1b")}
    if resH:
        fH = forecasts(op, resH + [r for r in (resO or []) if r["origin"] in pr.ORIGINS_H], pr.ORIGINS_H)
        bh = block_tables(fH, codes, YEARS_H, pr.boot_indices(len(codes), key=1))
        out["H"] = {"accuracy": bh["accuracy"], "rmse_by_year": bh["rmse_by_year"], "years": YEARS_H}
        out["H_calibration_point"] = {m: v for m, v in calibration_table(fH, codes, pr.boot_indices(len(codes), key=1)).items()}
    fP.to_csv(pr.CACHE_DIR.parent / "predictive_forecasts_P.csv", index=False)
    return out


def compute_loco(op: pd.DataFrame, resL: list[dict[str, Any]], mainP: dict[str, Any], fP_cubes: dict[str, np.ndarray]) -> dict[str, Any]:
    codes = sorted(op["code"].unique())
    idx = pr.boot_indices(len(codes), key=2)
    f = pr.collect_forecasts(op, resL, pr.model_label)
    f = pd.concat([f, pr.add_benchmarks(op, pr.ORIGINS_P)], ignore_index=True)
    cubes = cubes_of(f, codes, YEARS_P)
    out: dict[str, Any] = {"failed_jobs": [pr.job_name(r) for r in resL if r.get("status") != "ok"]}
    acc = {}
    p0 = pr.accuracy_row(cubes["P0"])["rmse"]
    for m, c in cubes.items():
        if not m.endswith(" (LOCO)"):
            continue
        base = m.replace(" (LOCO)", "")
        a = pr.accuracy_row(c)
        a["ratio_to_p0"] = a["rmse"] / p0
        a["main_rmse"] = pr.accuracy_row(fP_cubes[base])["rmse"] if base in fP_cubes else None
        a["ratio_to_main"] = a["rmse"] / a["main_rmse"] if a["main_rmse"] else None
        a["complete"] = a["n"] == len(codes) * len(YEARS_P)
        d = pr.loss_differential(cubes["P0"], c)
        a["dm_vs_p0"] = pr.dm_hln(d)
        per = {}
        for i, cc in enumerate(codes):
            e = c[i][np.isfinite(c[i])]
            e0 = cubes["P0"][i][np.isfinite(cubes["P0"][i])]
            em = fP_cubes[base][i][np.isfinite(fP_cubes[base][i])] if base in fP_cubes else np.array([np.nan])
            per[cc] = {"loco_rmse": pr.rmse(e), "p0_rmse": pr.rmse(e0), "main_rmse": pr.rmse(em), "ratio_to_main": pr.rmse(e) / pr.rmse(em), "ratio_to_p0": pr.rmse(e) / pr.rmse(e0)}
        a["per_country"] = per
        a["share_countries_below_p0"] = float(np.mean([v["loco_rmse"] < v["p0_rmse"] for v in per.values()]))
        a["worst_countries"] = sorted(per, key=lambda k: -per[k]["ratio_to_main"])[:5]
        acc[m] = a
    out["accuracy"] = acc
    return out


def compute_event(op: pd.DataFrame, resE: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"failed_jobs": [pr.job_name(r) for r in resE if r.get("status") != "ok"]}
    for block, origins in (("P", pr.ORIGINS_P), ("H", pr.ORIGINS_H)):
        for model in ("P1a", "P1b"):
            for s in ("B1", "B2"):
                rows = []
                for r in resE:
                    if r.get("status") == "ok" and r["model"] == model and r["set"] == s and r["origin"] in origins:
                        p = r["preds"]
                        rows.append(pd.DataFrame({"y": p["y"], "p": p["p"], "rate": p["rate"]}))
                if rows:
                    out[f"{block}:{model}-{s}"] = pr.event_metrics(pd.concat(rows, ignore_index=True))
    return out


# ---------------------------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------------------------
def render_md(res: dict[str, Any], meta: dict[str, Any], deviations: list[str], status: dict[str, str]) -> str:
    L: list[str] = []
    a = L.append
    a("# Predictive module: rolling-origin forecasts of the next-year change in CAPB")
    a("")
    a("Specification: `docs/predictive_spec.md` (dated 2026-10-13, SHA-256 `" + meta["spec_sha256"][:16] + "...`). Code: `src/models/py/predictive.py` and `predictive_report.py` (SHA-256 of `predictive.py` `" + meta["code_sha256"][:16] + "...`). "
      "Target: `capb_{T+1} - capb_T` in pp of potential GDP (AMECO `UBLGBP`, Spring 2026 vintage), one-step-ahead, expanding window, origins 2008-2020 (block P, 351 forecasts) and 2021-2022 (block H, 54 forecasts, descriptive). "
      "**Predictive and non-causal.** All numbers are pseudo-out-of-sample on final-vintage data, not real-time forecasts. SHAP: not run: not installed.")
    a("")
    a("## 0. Deviations from the specification")
    a("")
    for i, d in enumerate(deviations, 1):
        a(f"{i}. {d}")
    a("")
    a("## 1. Status")
    a("")
    a(_table(["Item", "Status"], [[k, v] for k, v in status.items()]))
    a("")
    sa = meta["schedule_agreement"]
    a(f"Setup checks: extract SHA-256 `{meta['extract_sha256']}`; gold build with end 2023 has {meta['gold_rows_2023_build']} rows; last observed AMECO year {meta['last_observed_ameco_year']}. "
      f"Schedule rule agreement (election dates only): `date(previous) + termlength(previous)` is within {sa['tolerance_days']} days of ETAD `sche_date` in {100 * sa['share_within_tolerance']:.1f}% of {sa['n_pairs']} elections. "
      f"Frozen files unchanged: {meta['frozen_ok']}.")
    a("")
    if "P" not in res:
        return "\n".join(L)
    P, fam = res["P"], res["family"]
    a("## 2. Accuracy, block P (origins 2008-2020; forecast years 2009-2021; 351 forecasts)")
    a("")
    a("RMSE and MAE in pp of potential GDP; ratio = RMSE(model)/RMSE(P0); skill = 1 - MSE(model)/MSE(P0); intervals are 95% country-cluster bootstrap (27 clusters, B = 9,999).")
    a("")
    rows = []
    for m in sorted(P["accuracy"], key=lambda k: (k.split("-")[0] if k not in ("P0", "P0b") else "0" + k, k)):
        x = P["accuracy"][m]
        rows.append([m, x["n"], _f(x["rmse"]), _ci(x["rmse_ci"]), _f(x["mae"]), _ci(x["mae_ci"]), _f(x["ratio"]), _ci(x["ratio_ci"]), _f(x["skill"]), _ci(x["skill_ci"])])
    a(_table(["Model", "n", "RMSE", "RMSE 95% CI", "MAE", "MAE 95% CI", "Ratio to P0", "Ratio 95% CI", "Skill", "Skill 95% CI"], rows))
    a("")
    a("## 3. Diebold-Mariano tests against persistence and incremental value (the Holm family)")
    a("")
    a("Two-sided DM with the Harvey-Leybourne-Newbold correction on the 13 yearly cross-country mean squared-loss differentials (positive = first-named model better), Student t with 12 df. Holm over exactly these six p-values. Companion: country-cluster paired bootstrap of the MSE difference and of the relative MSE reduction.")
    a("")
    rows = []
    for r in fam:
        if r["status"] != "ok":
            rows.append([r["comparison"], "failed"] + [""] * 8)
            continue
        rows.append([r["comparison"], _f(r["mean"], 4), _f(r["hln"], 3), _f(r["p"], 4), _f(r["p_holm"], 4), r["reading"], _f(r["mse_diff"], 4), _ci(r["mse_diff_ci"], 4), _f(r["rel_reduction"], 4), _ci(r["rel_reduction_ci"], 4)])
    a(_table(["Comparison", "Mean loss diff (pp^2)", "DM-HLN stat", "raw p", "Holm p", "Reading", "MSE diff", "MSE diff 95% CI", "Rel. MSE reduction", "Rel. red. 95% CI"], rows))
    a("")
    a("Lag-1 autocorrelation of the yearly differentials (descriptive): " + "; ".join(f"{k}: {_f(v, 2)}" for k, v in res["autocorr_lag1"].items()) + ".")
    a("")
    a("Sensitivity (descriptive, unadjusted): the same six DM tests without forecast years 2020-2021 (11 yearly differentials, t(10)):")
    a("")
    rows = [[r["comparison"], _f(r.get("mean"), 4), _f(r.get("hln"), 3), _f(r.get("p"), 4), _f(r.get("p_holm"), 4)] for r in res["family_sensitivity_excl_2020_2021"] if r["status"] == "ok"]
    a(_table(["Comparison", "Mean loss diff", "DM-HLN", "raw p", "Holm p (re-adjusted over the six)"], rows))
    a("")
    a("Absolute-loss DM (descriptive, outside the family): " + "; ".join(f"{k}: mean {_f(v['mean'], 4)}, p {_f(v['p'], 4)}" for k, v in res["dm_abs"].items()) + ".")
    a("")
    a("Reading of comparisons 5-6 (section 9 of the specification): " + res["incremental_reading"])
    a("")
    a("### Descriptive decomposition and every model against persistence (unadjusted)")
    a("")
    rows = [[k, _f(v["mean"], 4), _f(v["hln"], 3), _f(v["p"], 4), _f(v.get("rel_reduction"), 4), _ci(v.get("rel_reduction_ci"), 4)] for k, v in res["descriptive_dm"].items()]
    a(_table(["Comparison", "Mean loss diff", "DM-HLN", "raw p", "Rel. MSE reduction", "95% CI"], rows))
    a("")
    rows = [[k, _f(v["mean"], 4), _f(v["hln"], 3), _f(v["p"], 4)] for k, v in res["dm_vs_p0_all"].items()]
    a(_table(["Model vs P0", "Mean loss diff", "DM-HLN", "raw p"], rows))
    a("")
    a("## 4. Calibration (block P; realised on forecast, `y = a + b * yhat`; 95% country-cluster bootstrap intervals)")
    a("")
    rows = []
    for m, v in res["calibration"].items():
        rows.append([m, "n/a" if v["slope"] is None else _f(v["slope"]), "" if v["slope"] is None else _ci(v["slope_ci"]), "n/a" if v["slope"] is None else _f(v["intercept"]), "" if v["slope"] is None else _ci(v["intercept_ci"]), v.get("reading", v.get("note", ""))])
    a(_table(["Model", "Slope b", "b 95% CI", "Intercept a", "a 95% CI", "Reading"], rows))
    a("")
    G = res["groups"]
    a("## 5. Error by country, era and regime (block P; RMSE / MAE in pp; n per cell)")
    a("")
    a("### By era (forecast year)")
    a("")
    rows = []
    for era in ("2009-2015", "2016-2021"):
        for m in TABLE_MODELS:
            c = G["era"][era][m]
            rows.append([era, m, c["n"], _f(c["rmse"]), _f(c["mae"])])
    a(_table(["Era", "Model", "n", "RMSE", "MAE"], rows))
    a("")
    a("Pre-2008: no test rows (first forecast year 2009). Block H (2022-2023) is in section 6.")
    a("")
    a("### By regime")
    a("")
    rows = []
    for reg, cells in G["regime"].items():
        for m in TABLE_MODELS:
            if m in cells:
                c = cells[m]
                rows.append([reg, m, c["n"], _f(c["rmse"]), _f(c["mae"])])
    a(_table(["Regime", "Model", "n", "RMSE", "MAE"], rows))
    a("")
    a("### Pre-listed sensitivities of the pooled table")
    a("")
    rows = []
    for sens, cells in G["sensitivity"].items():
        for m in TABLE_MODELS:
            c = cells[m]
            rows.append([sens, m, c["n"], _f(c["rmse"]), _f(c["mae"])])
    a(_table(["Sample", "Model", "n", "RMSE", "MAE"], rows))
    a("")
    a("### By country (RMSE, 13 forecasts each)")
    a("")
    rows = [[c] + [_f(G["country"][c][m]["rmse"], 2) for m in TABLE_MODELS] for c in res["codes"]]
    a(_table(["Country"] + TABLE_MODELS, rows))
    a("")
    if "H" in res:
        H = res["H"]
        a("## 6. Block H: forecast years 2022-2023 (descriptive, never pooled with P, no test)")
        a("")
        a("Origins 2021 and 2022, 54 forecasts; the same fixed procedure. Intervals are country-cluster bootstrap intervals and are indicative only (two forecast years).")
        a("")
        rows = []
        for m in sorted(H["accuracy"], key=lambda k: (k.split("-")[0] if k not in ("P0", "P0b") else "0" + k, k)):
            x = H["accuracy"][m]
            rows.append([m, x["n"], _f(x["rmse"]), _ci(x["rmse_ci"]), _f(x["mae"]), _f(x["ratio"]), _ci(x["ratio_ci"]), _f(H["rmse_by_year"][m][0]), _f(H["rmse_by_year"][m][1])])
        a(_table(["Model", "n", "RMSE", "RMSE 95% CI", "MAE", "Ratio to P0", "Ratio 95% CI", "RMSE 2022", "RMSE 2023"], rows))
        a("")
        cal = res["H_calibration_point"]
        a("Calibration slopes in H (point values): " + "; ".join(f"{m}: {_f(v['slope'], 2)}" for m, v in cal.items() if v.get("slope") is not None and m in TABLE_MODELS) + ".")
        a("")
    if "oracle" in res:
        a("## 7. Oracle diagnostics (look-ahead; NOT forecasts and never evidence of predictive value)")
        a("")
        a("B2o replaces `Wk_next`, `Wk_now` by the same quantities built from ETAD `sche_date` (an ex-post record); B2f adds the frozen realised `W_S`, `W_E`, `W_U` of the forecast year. Both leak the future by construction.")
        a("")
        rows = []
        for m in ("P1a-B2", "P1a-B2o", "P1a-B2f", "P1b-B2", "P1b-B2o", "P1b-B2f"):
            if m in P["accuracy"]:
                x = P["accuracy"][m]
                rows.append([m, _f(x["rmse"]), _f(x["ratio"]), _f(x["skill"])])
        a(_table(["Model", "RMSE (pp)", "Ratio to P0", "Skill vs P0"], rows))
        a("")
        rows = [[k, _f(v["mean"], 4), _f(v["p"], 4), _f(v.get("rel_reduction"), 4), _ci(v.get("rel_reduction_ci"), 4)] for k, v in res["descriptive_dm"].items() if ("B2o" in k or "B2f" in k)]
        a(_table(["Comparison", "Mean loss diff", "raw p (unadjusted)", "Rel. MSE reduction", "95% CI"], rows))
        a("")
        a("Inflation reading: " + res["oracle_reading"])
        a("")
    if "loco" in res:
        a("## 8. Leave-one-country-out stress (descriptive, outside the family)")
        a("")
        a("Each country's rows are removed from fitting, standardisation, the other countries' means and the inner validation at every origin 2008-2020; the held-out country's own training-window feature history supplies its country means.")
        a("")
        rows = []
        for m, v in res["loco"]["accuracy"].items():
            rows.append([m, _f(v["rmse"]), _f(v["mae"]), _f(v["ratio_to_p0"]), _f(v["main_rmse"]), _f(v["ratio_to_main"]), _f(v["dm_vs_p0"]["hln"], 2), _f(v["dm_vs_p0"]["p"], 3), _f(v["share_countries_below_p0"], 2), ", ".join(v["worst_countries"])])
        a(_table(["Model", "LOCO RMSE", "LOCO MAE", "Ratio to P0", "Main-run RMSE", "Ratio to main", "DM-HLN vs P0", "raw p", "Share of countries below P0", "Largest deterioration"], rows))
        a("")
        for m, v in res["loco"]["accuracy"].items():
            r = [x["ratio_to_main"] for x in v["per_country"].values()]
            a(f"- {m}: per-country LOCO/main RMSE ratio ranges from {min(r):.2f} to {max(r):.2f}; per-country LOCO/P0 ratio from {min(x['ratio_to_p0'] for x in v['per_country'].values()):.2f} to {max(x['ratio_to_p0'] for x in v['per_country'].values()):.2f}.")
        a("")
    imp = res["importance"]
    a("## 9. Interpretation (predictive only): permutation importance and ALE")
    a("")
    a("Out-of-sample permutation importance on the test rows of each origin 2008-2020 (R = 200, whole rows of a group permuted jointly across the 27 test rows): percentage increase in squared error relative to the unpermuted forecast. 95% interval: country-cluster bootstrap of the pooled value. It says which inputs the forecast relies on, nothing about what produces the outcome.")
    a("")
    rows = []
    for model in ("P1a", "P1b"):
        items = imp.get(model, {}).get("items", {})
        for k in ("group:fiscal_macro", "group:political", "group:demographic"):
            if k in items:
                rows.append([f"{model}-B2", k.replace("group:", ""), _f(items[k]["pooled_pct"], 2), _ci(items[k]["ci"], 2)])
    a(_table(["Model", "Group", "Pooled increase in squared error (%)", "95% CI"], rows))
    a("")
    rows = []
    for model in ("P1a", "P1b"):
        items = imp.get(model, {}).get("items", {})
        cols = sorted((k for k in items if k.startswith("col:")), key=lambda k: -items[k]["pooled_pct"])
        for k in cols:
            rows.append([f"{model}-B2", k.replace("col:", ""), _f(items[k]["pooled_pct"], 2), _ci(items[k]["ci"], 2)])
    a(_table(["Model", "Column", "Pooled increase (%)", "95% CI"], rows))
    a("")
    a("First-order ALE curves (training rows of the last primary origin 2020; ten equal-count bins; pre-listed features) are in `reports/figures/predictive_importance.png` and in the JSON.")
    a("")
    a("## 10. Selected hyperparameters (per origin, CD scheme; full detail in the JSON)")
    a("")
    rows = []
    for m, lst in res["hyper"].items():
        if m.startswith("P1a"):
            kinds = pd.Series([h["kind"] for h in lst]).value_counts().to_dict()
            rows.append([m, f"kinds {kinds}; median alpha {np.median([h['alpha'] for h in lst]):.3g}; median non-zero coefficients {np.median([h['n_nonzero'] for h in lst]):.0f}"])
        elif m.startswith("P1b"):
            rows.append([m, f"median iterations {np.median([h['n_iter'] for h in lst]):.0f}; depth counts {pd.Series([h['max_depth'] for h in lst]).value_counts().to_dict()}; leaf counts {pd.Series([h['min_samples_leaf'] for h in lst]).value_counts().to_dict()}"])
    a(_table(["Model", "Summary over the 13 primary origins"], rows))
    a("")
    if "event" in res:
        a("## 11. Optional binary deterioration event (`y < -0.5` pp; descriptive, outside the family)")
        a("")
        rows = [[k, v["n"], _f(v["prevalence"]), _f(v["brier"], 4), _f(v["brier_benchmark"], 4), _f(v["brier_skill"], 3), _f(v["log_loss"], 3), _f(v["log_loss_benchmark"], 3), _f(v["auc"], 3), _f(v.get("calibration_slope"), 2)]
                for k, v in res["event"].items() if isinstance(v, dict) and "brier" in v]
        a(_table(["Block:model", "n", "Prevalence", "Brier", "Brier (training rate)", "Brier skill", "Log-loss", "Log-loss (rate)", "AUC", "Logit calibration slope"], rows))
        a("")
    a("## 12. Limitations (model card, section 10 of the specification)")
    a("")
    a("Ex-post revised target and features (pseudo-out-of-sample; CAPB revision SD 0.97 pp, mean absolute 0.64 pp); AMECO forecast years 2026-2027 never used, last forecast year 2023; 13 forecast years in P (the DM test has 12 df); regime shifts and one-offs; the political schedule is measured with error; demographic features are near country identity; no common-factor information; no SHAP/LightGBM; associations only.")
    return "\n".join(L)


# ---------------------------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------------------------
def make_figures(res: dict[str, Any]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pr.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    colors = {"P0": "#222222", "P1a-B1": "#1f77b4", "P1a-B2": "#6baed6", "P1b-B1": "#d95f02", "P1b-B2": "#fdae6b"}
    styles = {"P0": "-", "P1a-B1": "--", "P1a-B2": "-", "P1b-B1": "--", "P1b-B2": "-"}
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.2), gridspec_kw={"width_ratios": [1.5, 1]})
    years = res["P"]["years"] + (res["H"]["years"] if "H" in res else [])
    for m in TABLE_MODELS:
        yv = list(res["P"]["rmse_by_year"][m]) + (list(res["H"]["rmse_by_year"][m]) if "H" in res else [])
        ax1.plot(years, yv, styles[m], marker="o", ms=3.5, color=colors[m], label=m, lw=1.6)
    if "H" in res:
        ax1.axvspan(2021.5, 2023.5, color="#dddddd", alpha=0.6, lw=0)
        ax1.text(2022.5, ax1.get_ylim()[1] * 0.97, "block H\n(descriptive)", ha="center", va="top", fontsize=8)
    ax1.set_xlabel("Forecast year")
    ax1.set_ylabel("RMSE across 27 countries (pp of potential GDP)")
    ax1.set_title("A. Out-of-sample RMSE by forecast year")
    ax1.legend(fontsize=8, ncol=2, frameon=False)
    ax1.grid(alpha=0.25)
    models = [m for m in TABLE_MODELS if m != "P0"]
    for k, (block, marker) in enumerate((("P", "o"), ("H", "s"))):
        if block not in res:
            continue
        acc = res[block]["accuracy"]
        ypos = np.arange(len(models))[::-1] + (0.15 if block == "P" else -0.15)
        r = [acc[m]["ratio"] for m in models]
        lo = [acc[m]["ratio"] - acc[m]["ratio_ci"][0] for m in models]
        hi = [acc[m]["ratio_ci"][1] - acc[m]["ratio"] for m in models]
        ax2.errorbar(r, ypos, xerr=[lo, hi], fmt=marker, color="#1f77b4" if block == "P" else "#d95f02", capsize=3, label="Block P (2009-2021)" if block == "P" else "Block H (2022-2023, indicative)")
    ax2.axvline(1.0, color="#222222", lw=1)
    ax2.set_yticks(np.arange(len(models))[::-1])
    ax2.set_yticklabels(models)
    ax2.set_xlabel("RMSE ratio to persistence P0 (1 = equal; below 1 = better)")
    ax2.set_title("B. Ratio to persistence, 95% country-cluster intervals")
    ax2.legend(fontsize=8, frameon=False, loc="best")
    ax2.grid(alpha=0.25)
    fig.text(0.01, 0.005, pr.SOURCE_LINE, fontsize=7, color="#555555")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(pr.ERRORS_FIG, dpi=300)
    plt.close(fig)

    imp = res["importance"]
    fig = plt.figure(figsize=(13, 9.5))
    gs = fig.add_gridspec(3, 3, height_ratios=[1.1, 1, 1])
    axa = fig.add_subplot(gs[0, :])
    groups = ["group:fiscal_macro", "group:political", "group:demographic"]
    for k, (model, col) in enumerate((("P1a", "#1f77b4"), ("P1b", "#d95f02"))):
        items = imp.get(model, {}).get("items", {})
        if not items:
            continue
        ypos = np.arange(3)[::-1] + (0.18 if k == 0 else -0.18)
        v = [items[g]["pooled_pct"] for g in groups]
        lo = [items[g]["pooled_pct"] - items[g]["ci"][0] for g in groups]
        hi = [items[g]["ci"][1] - items[g]["pooled_pct"] for g in groups]
        axa.barh(ypos, v, height=0.32, color=col, alpha=0.85, label=f"{model}-B2")
        axa.errorbar(v, ypos, xerr=[lo, hi], fmt="none", ecolor="#222222", capsize=3)
    axa.set_yticks(np.arange(3)[::-1])
    axa.set_yticklabels(["fiscal-macro (lagged)", "political (calendar)", "demographic"])
    axa.set_xlabel("Increase in squared error when the group is permuted across countries within a year (%)")
    axa.set_title("A. Out-of-sample grouped permutation importance (origins 2008-2020; 95% country-cluster intervals)")
    axa.axvline(0, color="#222222", lw=0.8)
    axa.legend(frameon=False, fontsize=8)
    axa.grid(alpha=0.25, axis="x")
    labels = {"capb_T_dm": "CAPB level, deviation from country mean (pp)", "dcapb_T_dm": "Last change in CAPB, deviation (pp)", "debt_gdp_T_dm": "Debt, deviation (% of GDP)",
              "outgap_T_dm": "Output gap, deviation (% of potential)", "Wk_next": "Known pre-election exposure, forecast year (share)", "olddep1_T_dm": "Old-age dependency, deviation (per 100)"}
    for i, feat in enumerate(pr.ALE_FEATURES):
        ax = fig.add_subplot(gs[1 + i // 3, i % 3])
        for model, col in (("P1a", "#1f77b4"), ("P1b", "#d95f02")):
            ale = imp.get(model, {}).get("ale", {}).get(feat)
            if ale:
                ax.plot(ale["edges"], ale["ale"], marker="o", ms=3, color=col, lw=1.4, label=f"{model}-B2")
        ax.axhline(0, color="#888888", lw=0.7)
        ax.set_xlabel(labels[feat], fontsize=8)
        ax.set_ylabel("ALE: change in forecast (pp)" if i % 3 == 0 else "", fontsize=8)
        ax.tick_params(labelsize=8)
        ax.grid(alpha=0.25)
        if i == 0:
            ax.legend(frameon=False, fontsize=8)
    fig.suptitle("B. First-order accumulated local effects (model at origin 2020; predictive description, not causal)", y=0.635, fontsize=10)
    fig.text(0.01, 0.005, pr.SOURCE_LINE, fontsize=7, color="#555555")
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.subplots_adjust(hspace=0.55)
    fig.savefig(pr.IMPORTANCE_FIG, dpi=300)
    plt.close(fig)


# ---------------------------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------------------------
BASE_DEVIATIONS = [
    "The report assembly, figures and the command line live in `src/models/py/predictive_report.py` (a second new file); the specification names only `predictive.py`. No behaviour changes.",
    "Specification section 4.3 and section 12 quote a 71.0 per cent agreement of the strict schedule rule with ETAD `sche_date`. That figure divided by all 248 calendar rows and so counted the 45 elections without a comparison as misses. The correct share among the 203 elections that have a previous election, a term length and a `sche_date` is the value printed under Status below (86.7 per cent). The rule itself, and the decision to accept it as measurement error, are unchanged; the model card uses the corrected figure.",
    "Czechia has no in-calendar election before 1996, so its origin-1995 political features are undefined; that origin is unused (the first usable forecast year is 1997), so no training or test row is lost.",
    "Section 3 of the specification says block H gets point metrics only; section 7 asks for cluster-bootstrap intervals of the accuracy metrics for both blocks. H intervals are computed and labelled indicative; no test is run on H.",
    "Leave-one-country-out: the held-out country's own country means use its complete rows with forecast year <= T (its feature history up to the origin, the same window as a training row), not including the test row itself, to match the main-run rule of section 4.4.",
    "The same bootstrap index matrix (seed key (6000, 2, k), k = 0 block P, 1 block H, 2 LOCO) is reused across all statistics of a block, so model comparisons are paired.",
    "Hyperparameter ties (smaller `alpha`, `l1_ratio` order etc.) are resolved exactly as in section 5; the iteration search for P1b uses a 300-iteration cap with learning rate 0.05 as specified.",
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all", choices=["all", "P", "H", "oracle", "loco", "event", "report"])
    ap.add_argument("--jobs", type=int, default=20)
    args = ap.parse_args(argv)
    op, meta = pr.load_real()
    codes = sorted(op["code"].unique())
    pr.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ok_frozen = pr.frozen_unchanged()
    meta["frozen_ok"] = f"{sum(ok_frozen.values())} of {len(ok_frozen)} files hash-identical to docs/freeze_manifest.json"
    status = {"SHAP": "not run: not installed (permutation importance and ALE used instead)", "LightGBM / XGBoost": "not installed; scikit-learn HistGradientBoostingRegressor used",
              "P1c (GAM)": "run (statsmodels GLMGam), descriptive", "Oracle diagnostics": "pending", "Leave-one-country-out": "pending", "Binary event": "pending", "Block H": "pending"}
    order = ["P", "H", "oracle", "loco", "event"]
    labels = {"P": "Block P", "H": "Block H", "oracle": "Oracle diagnostics", "loco": "Leave-one-country-out", "event": "Binary event"}
    run_now = order if args.stage == "all" else ([] if args.stage == "report" else [args.stage])
    cache: dict[str, list[dict[str, Any]]] = {}
    for st in order:
        if st in run_now:
            cache[st] = pr.run_stage(st, op, args.jobs)
        else:
            jobs = pr.jobs_for(st, op)
            if all((pr.CACHE_DIR / f"{pr.job_name(j)}.json").exists() for j in jobs):
                cache[st] = [pr.run_job(j, op) for j in jobs]
        if st in cache:
            status[labels[st]] = f"complete ({len(cache[st])} fits, {sum(r.get('status') != 'ok' for r in cache[st])} failed)"
            if "P" in cache:
                write_all(op, meta, cache, status, codes)
    return 0


def write_all(op: pd.DataFrame, meta: dict[str, Any], cache: dict[str, list[dict[str, Any]]], status: dict[str, str], codes: list[str]) -> None:
    res = compute_main(op, cache["P"], cache.get("H"), cache.get("oracle"))
    cubes_main = None
    fP = pd.read_csv(pr.CACHE_DIR.parent / "predictive_forecasts_P.csv")
    cubes_main = cubes_of(fP, codes, YEARS_P)
    devs = list(BASE_DEVIATIONS)
    if res["failed_jobs"]:
        devs.append(f"{len(res['failed_jobs'])} fits failed and are reported as failed (never re-specified): " + ", ".join(res["failed_jobs"][:12]) + (" ..." if len(res["failed_jobs"]) > 12 else ""))
    fam = res["family"]
    if all(r["status"] == "ok" for r in fam):
        p5, p6 = fam[4], fam[5]
        r1 = all(r["p_holm"] <= 0.05 and r["mean"] > 0 and r["rel_reduction_ci"][0] > 0 for r in (p5, p6))
        r2 = any(r["p_holm"] <= 0.05 and r["mean"] > 0 and r["rel_reduction_ci"][0] > 0 for r in (p5, p6))
        res["incremental_reading"] = ("(R1) the political and demographic block improves out-of-sample prediction of next-year CAPB changes in this sample, in both model classes." if r1 else
                                      "(R2) mixed and model-dependent: the block improves one model class only." if r2 else
                                      "(R3) no evidence that the political and demographic block improves out-of-sample prediction beyond the lagged fiscal-and-macro baseline, in 13 forecast years; the test can only detect a mean loss differential of about 0.6 SD of the yearly differential (50 per cent power) to 0.85 SD (80 per cent power).")
    else:
        res["incremental_reading"] = "not available (a family fit failed)"
    if "oracle" in cache:
        res["oracle"] = True
        acc = res["P"]["accuracy"]
        parts = []
        for model in ("P1a", "P1b"):
            for s in ("B2o", "B2f"):
                if f"{model}-{s}" in acc and f"{model}-B2" in acc:
                    parts.append(f"{model}-{s} RMSE {acc[f'{model}-{s}']['rmse']:.3f} against {acc[f'{model}-B2']['rmse']:.3f} for {model}-B2 (ratio {acc[f'{model}-{s}']['rmse'] / acc[f'{model}-B2']['rmse']:.3f})")
        ratios = [acc[f"{m}-{s}"]["rmse"] / acc[f"{m}-B2"]["rmse"] for m in ("P1a", "P1b") for s in ("B2o", "B2f") if f"{m}-{s}" in acc and f"{m}-B2" in acc]
        verdict = (" No inflation is visible: the leaking sets do not lower RMSE by more than 1% relative to the strict B2 in either model class (so the strict calendar rule is not hiding a gain that the leaked information would reveal; the political columns carry little signal either way)." if ratios and min(ratios) >= 0.99
                   else f" Inflation: the leaking sets lower RMSE by up to {100 * (1 - min(ratios)):.1f}% relative to the strict B2.")
        res["oracle_reading"] = "; ".join(parts) + "." + verdict
    if "loco" in cache:
        res["loco"] = compute_loco(op, cache["loco"], res, cubes_main)
    if "event" in cache:
        res["event"] = compute_event(op, cache["event"])
    md = render_md(res, meta, devs, status)
    lowered = md.lower()
    hits = [w for w in pr.FORBIDDEN_WORDS if w in lowered.replace("`", "")]
    if hits:
        md += "\n\n> Vocabulary check failed: " + ", ".join(hits)
    pr.MD_PATH.write_text(md + "\n", encoding="utf-8")
    payload = {"meta": meta, "status": status, "deviations": devs, "results": {k: v for k, v in res.items()}}
    pr.JSON_PATH.write_text(json.dumps(_clean(payload), indent=1), encoding="utf-8")
    make_figures(res)
    print("wrote", pr.MD_PATH, pr.JSON_PATH, flush=True)


if __name__ == "__main__":
    sys.exit(main())
