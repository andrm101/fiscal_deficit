"""THROW-AWAY FEASIBILITY PROBE -- NOT THE PRODUCTION PIPELINE.

Purpose: indicative week-2 gate numbers for an EU-27 country-year panel (1995-2023):
  (1) ageing variation (Eurostat demo_pjanind: OLDDEP1, PC_Y65_MAX, MEDAGEPOP),
  (2) CAPB variance (AMECO UBLGBP via DBnomics) and an indicative Monte Carlo
      minimum detectable effect (MDE) for election-cycle dummies,
  (3) effective estimation sample,
  (4) numbers used to propose go/no-go gates.

Everything is fetched from small JSON endpoints and kept IN MEMORY (nothing is written to disk).
Election calendars are RANDOM PLACEHOLDERS -> MDEs are indicative only.
Run:  python scripts/feasibility_probe.py     (takes ~1-3 minutes; needs internet)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # unused for I/O; kept for path hygiene
SEED = 42
np.random.seed(SEED)
RNG = np.random.default_rng(SEED)

Y0, Y1 = 1995, 2023
YEARS = list(range(Y0, Y1 + 1))
N_REPS = 3000
ALPHA, POWER = 0.05, 0.80

# Eurostat convention (EL = Greece). AMECO uses ISO3-like codes (rom = Romania, grc = Greece).
EU27 = ["AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "EL", "HU", "IE",
        "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"]
ISO3 = {"AT": "aut", "BE": "bel", "BG": "bgr", "HR": "hrv", "CY": "cyp", "CZ": "cze", "DK": "dnk",
        "EE": "est", "FI": "fin", "FR": "fra", "DE": "deu", "EL": "grc", "HU": "hun", "IE": "irl",
        "IT": "ita", "LV": "lva", "LT": "ltu", "LU": "lux", "MT": "mlt", "NL": "nld", "PL": "pol",
        "PT": "prt", "RO": "rom", "SK": "svk", "SI": "svn", "ES": "esp", "SE": "swe"}
EU15 = {"AT", "BE", "DE", "DK", "EL", "ES", "FI", "FR", "IE", "IT", "LU", "NL", "PT", "SE"}  # EU-27 members of EU-15
POST2004 = set(EU27) - EU15  # 2004/2007/2013 accession (incl. CY, MT -> not strictly CEE)

EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/demo_pjanind"
DBN = "https://api.db.nomics.world/v22/series/AMECO/{code}?observations=1&format=json"


def banner(s: str) -> None:
    print("\n" + "=" * 100 + f"\n{s}\n" + "=" * 100)


# ----------------------------------------------------------------------------- data access
def fetch_eurostat(indic: list[str]) -> pd.DataFrame:
    """JSON-stat 2.0 -> long DataFrame (geo, year, indic, value). In memory only."""
    params = [("format", "JSON"), ("lang", "EN"), ("sinceTimePeriod", str(Y0)), ("untilTimePeriod", str(Y1))]
    params += [("indic_de", i) for i in indic] + [("geo", g) for g in EU27]
    r = requests.get(EUROSTAT, params=params, timeout=120)
    r.raise_for_status()
    j = r.json()
    ids, size = j["id"], j["size"]
    cats = {d: list(j["dimension"][d]["category"]["index"].keys()) for d in ids}
    vals = np.full(int(np.prod(size)), np.nan)
    for k, v in j["value"].items():
        vals[int(k)] = v
    cube = vals.reshape(size)
    idx = pd.MultiIndex.from_product([cats[d] for d in ids], names=ids)
    df = pd.DataFrame({"value": cube.ravel()}, index=idx).reset_index()
    df = df.rename(columns={"time": "year"})
    df["year"] = df["year"].astype(int)
    return df[["geo", "year", "indic_de", "value"]]


def fetch_ameco(code: str) -> tuple[pd.DataFrame, dict]:
    j = requests.get(DBN.format(code=code), timeout=120).json()
    meta = {"name": j["dataset"]["name"], "indexed_at": j["dataset"]["indexed_at"]}
    rows = []
    inv = {v: k for k, v in ISO3.items()}
    for s in j["series"]["docs"]:
        g = s["dimensions"]["geo"]
        if g not in inv:
            continue
        meta["unit"] = s["dimensions"]["unit"]
        for p, v in zip(s["period"], s["value"]):
            rows.append((inv[g], int(p), np.nan if v == "NA" else float(v)))
    return pd.DataFrame(rows, columns=["geo", "year", code]), meta


# ----------------------------------------------------------------------------- panel helpers
def to_matrix(df: pd.DataFrame, col: str) -> np.ndarray:
    """countries x years matrix (NaN where unobserved)."""
    m = df.pivot(index="geo", columns="year", values=col).reindex(index=EU27, columns=YEARS)
    return m.to_numpy(float)


def twoway_demean(x: np.ndarray, tol: float = 1e-12, maxit: int = 5000) -> np.ndarray:
    """Alternating-projection removal of country and year means; handles NaN (unbalanced) panels."""
    r = x.copy()
    obs = ~np.isnan(r)
    r = np.where(obs, r, 0.0)
    for _ in range(maxit):
        old = r.copy()
        cm = r.sum(1) / obs.sum(1)
        r = np.where(obs, r - cm[:, None], 0.0)
        ym = r.sum(0) / obs.sum(0)
        r = np.where(obs, r - ym[None, :], 0.0)
        if np.max(np.abs(r - old)) < tol:
            break
    return np.where(obs, r, np.nan)


def sd(a: np.ndarray) -> float:
    a = a[~np.isnan(a)]
    return float(a.std(ddof=0))


def decomposition(x: np.ndarray, label: str) -> dict:
    """Balanced-panel exact SS decomposition: total = between + year + two-way residual."""
    assert not np.isnan(x).any(), "decomposition() expects a balanced panel"
    n, t = x.shape
    gm = x.mean()
    cm = x.mean(1)
    ym = x.mean(0)
    ss_tot = ((x - gm) ** 2).sum()
    ss_c = t * ((cm - gm) ** 2).sum()
    ss_y = n * ((ym - gm) ** 2).sum()
    ss_r = ss_tot - ss_c - ss_y
    within = x - cm[:, None]
    res = twoway_demean(x)
    assert abs((res ** 2).sum() - ss_r) / ss_tot < 1e-9
    d1995, d2023 = x[:, 0], x[:, -1]
    delta = d2023 - d1995
    common = delta.mean()
    out = dict(
        label=label,
        mean=gm, sd_total=np.sqrt(ss_tot / x.size),
        share_between=ss_c / ss_tot, share_year=ss_y / ss_tot, share_resid=ss_r / ss_tot,
        share_within=1 - ss_c / ss_tot,
        sd_within=sd(within), sd_between_means=float(cm.std(ddof=0)), sd_twoway=sd(res),
        year_share_of_within=ss_y / (ss_y + ss_r),
        sd_1995=float(d1995.std(ddof=0)), sd_2023=float(d2023.std(ddof=0)),
        mean_change=common, sd_change=float(delta.std(ddof=0)),
        common_share_of_change_ss=n * common ** 2 / (delta ** 2).sum(),
        resid_sd_over_total_sd=sd(res) / np.sqrt(ss_tot / x.size),
    )
    return out


def print_decomp(d: dict) -> None:
    print(f"\n--- {d['label']} ---")
    print(f"mean={d['mean']:.3f}  total SD={d['sd_total']:.3f}")
    print(f"variance shares: between-country={d['share_between']:.3f}  year effects={d['share_year']:.3f}  "
          f"two-way residual={d['share_resid']:.3f}   (within-country total={d['share_within']:.3f})")
    print(f"SD of country-demeaned (within) component={d['sd_within']:.3f}")
    print(f"SD of between component (country means)={d['sd_between_means']:.3f}")
    print(f"SD after country+year FE (two-way)={d['sd_twoway']:.3f}   ({d['resid_sd_over_total_sd']:.3f} of total SD)")
    print(f"year effects as share of within-country variance={d['year_share_of_within']:.3f}")
    print(f"cross-country SD: 1995={d['sd_1995']:.3f}  2023={d['sd_2023']:.3f}")
    print(f"1995->2023 change: mean={d['mean_change']:.3f}  cross-country SD={d['sd_change']:.3f}; "
          f"common (mean-shift) share of sum-of-squared changes={d['common_share_of_change_ss']:.3f}, "
          f"country-specific share={1 - d['common_share_of_change_ss']:.3f}")


# ----------------------------------------------------------------------------- placeholder election calendars
def draw_calendars(rng: np.random.Generator, reps: int, n: int, t: int) -> tuple[np.ndarray, np.ndarray]:
    """PLACEHOLDER calendars: random phase in {0..3}, strict 4-year spacing. Returns (election, pre) dummies (reps,n,t)."""
    phase = rng.integers(0, 4, size=(reps, n, 1))
    yrs = np.arange(t)[None, None, :]
    elec = ((yrs - phase) % 4 == 0).astype(float)
    pre = ((yrs + 1 - phase) % 4 == 0).astype(float)
    return elec, pre


def ar1_noise(rng: np.random.Generator, reps: int, n: int, t: int, sigma: float, rho: float) -> np.ndarray:
    """Stationary AR(1) with marginal SD sigma."""
    u = rng.standard_normal((reps, n, t))
    e = np.empty_like(u)
    e[..., 0] = sigma * u[..., 0]
    s_inn = sigma * np.sqrt(1 - rho ** 2)
    for k in range(1, t):
        e[..., k] = rho * e[..., k - 1] + s_inn * u[..., k]
    return e


def build_annihilator(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Residual-maker M for country+year FE on the observed cells (stacked country-major)."""
    n, t = mask.shape
    ci, ti = np.where(mask)
    nobs = len(ci)
    Z = np.zeros((nobs, n + t - 1))
    Z[np.arange(nobs), ci] = 1.0
    keep = ti > 0
    Z[np.arange(nobs)[keep], n + ti[keep] - 1] = 1.0
    M = np.eye(nobs) - Z @ np.linalg.pinv(Z)
    return M, ci, ti


def cluster_ols(Xt: np.ndarray, et: np.ndarray, ci: np.ndarray, n_clusters: int, k_fe: int):
    """FWL on pre-residualised X (nobs,k) and y (nobs,reps). Returns beta (reps,k), se (reps,k).
    CR1 small-sample factor G/(G-1)*(N-1)/(N-K), K = k + year FEs (country FE nested in clusters)."""
    nobs, k = Xt.shape
    reps = et.shape[1]
    XtX_inv = np.linalg.inv(Xt.T @ Xt)
    beta = XtX_inv @ (Xt.T @ et)                  # (k,reps)
    u = et - Xt @ beta                            # (nobs,reps)
    C = np.zeros((n_clusters, nobs))
    C[ci, np.arange(nobs)] = 1.0
    se = np.empty((reps, k))
    corr = n_clusters / (n_clusters - 1) * (nobs - 1) / (nobs - (k + k_fe))
    for r in range(reps):
        sc = C @ (Xt * u[:, [r]])                 # (G,k)
        V = XtX_inv @ (sc.T @ sc) @ XtX_inv * corr
        se[r] = np.sqrt(np.diag(V))
    return beta.T, se


def mde_from_draws(b0: np.ndarray, se: np.ndarray, tcrit: float, power: float = POWER) -> float:
    """SE does not depend on the true effect (FWL: residuals invariant to beta), so power(beta) = P(|beta+b0|/se > tcrit)."""
    def pw(beta: float) -> float:
        return float(np.mean(np.abs(beta + b0) / se > tcrit))
    lo, hi = 0.0, 50 * float(np.median(se))
    for _ in range(60):
        mid = (lo + hi) / 2
        (lo, hi) = (mid, hi) if pw(mid) < power else (lo, mid)
    return (lo + hi) / 2


# ============================================================================== MAIN
def main() -> None:
    print("THROW-AWAY FEASIBILITY PROBE -- NOT THE PRODUCTION PIPELINE. Placeholder election calendars; indicative only.")
    print(f"seed={SEED}, python={sys.version.split()[0]}, numpy={np.__version__}, pandas={pd.__version__}")

    # ------------------------------------------------------------------ (1) ageing variation
    banner("(1) AGEING VARIATION -- Eurostat demo_pjanind, EU-27, 1995-2023")
    es = fetch_eurostat(["OLDDEP1", "PC_Y65_MAX", "MEDAGEPOP"])
    mats = {}
    for ind, lab in [("OLDDEP1", "OLDDEP1 (65+/15-64, %)"), ("PC_Y65_MAX", "65+ population share (%)"),
                     ("MEDAGEPOP", "Median age (years)")]:
        sub = es[es.indic_de == ind].rename(columns={"value": ind})
        m = to_matrix(sub, ind)
        mats[ind] = m
        print(f"\n{lab}: observed cells={int((~np.isnan(m)).sum())} of {m.size}; "
              f"countries with gaps={[EU27[i] for i in range(len(EU27)) if np.isnan(m[i]).any()]}")
        full = ~np.isnan(m).any(1)
        if not full.all():
            gaps = {EU27[i]: [YEARS[j] for j in range(len(YEARS)) if np.isnan(m[i, j])] for i in np.where(~full)[0]}
            print(f"  gaps: {gaps} -> exact SS decomposition on the balanced subset ({full.sum()} countries); "
                  f"unbalanced two-way SD on all 27 reported separately")
        d = decomposition(m[full], lab + (f" [balanced subset: {full.sum()} countries]" if not full.all() else ""))
        print_decomp(d)
        print(f"  two-way SD on all 27 countries (unbalanced alternating projections)={sd(twoway_demean(m)):.3f}")

    old = mats["OLDDEP1"]
    cmean = np.nanmean(old, 1)
    is15 = np.array([g in EU15 for g in EU27], float)
    print("\nMembership structure of country-mean OLDDEP1:")
    print(f"  EU-15 members in EU-27: {int(is15.sum())}; post-2004 accession: {int((1 - is15).sum())} (includes CY, MT)")
    r_pb = np.corrcoef(cmean, is15)[0, 1]
    print(f"  point-biserial corr(country-mean OLDDEP1, EU15 dummy) = {r_pb:+.3f}  (R^2 = {r_pb ** 2:.3f}); "
          f"mean EU15={cmean[is15 == 1].mean():.2f}, mean post-2004={cmean[is15 == 0].mean():.2f}")
    for ind in ("PC_Y65_MAX", "MEDAGEPOP"):
        cm_ = np.nanmean(mats[ind], 1)
        print(f"  corr(country-mean {ind}, EU15 dummy) = {np.corrcoef(cm_, is15)[0, 1]:+.3f}")

    # SD of the level at (placeholder) election dates and its between component
    elec_cal, pre_cal = draw_calendars(np.random.default_rng(SEED), 1, 27, len(YEARS))
    el = elec_cal[0].astype(bool)
    el = el & ~np.isnan(old)
    lvl = old[el]
    cm_rep = np.repeat(cmean[:, None], len(YEARS), 1)[el]
    print(f"\nAt PLACEHOLDER election dates ({lvl.size} country-elections): SD of OLDDEP1 level={lvl.std():.3f}; "
          f"SD of its between-country component (country means)={cm_rep.std():.3f}; "
          f"SD of within component (level - country mean)={(lvl - cm_rep).std():.3f}")
    # within-between (Mundlak) variation on the full panel
    wcomp = old - cmean[:, None]
    print(f"Mundlak split of OLDDEP1 (27 countries): between SD={cmean.std():.3f}; within SD={np.nanstd(wcomp):.3f}; "
          f"within SD after removing year FE (two-way)={sd(twoway_demean(old)):.3f}")
    # moderator-after-FE variation in the interaction ElectionWindow x OLDDEP1
    z_all = (old - np.nanmean(old)) / np.nanstd(old)
    print(f"Standardised moderator z (pooled mean/SD): country-mean z SD={np.nanmean(z_all, 1).std():.3f}; "
          f"two-way-demeaned z SD={sd(twoway_demean(z_all)):.3f} (z units)")

    # ------------------------------------------------------------------ (2) CAPB
    banner("(2) CAPB -- AMECO UBLGBP via DBnomics; UBLGAP checked")
    capb_long, meta = fetch_ameco("UBLGBP")
    cab_long, meta2 = fetch_ameco("UBLGAP")
    print(f"UBLGBP: {meta['name']}\n  unit={meta['unit']}; DBnomics indexed_at={meta['indexed_at']}")
    print(f"UBLGAP: {meta2['name']}\n  unit={meta2['unit']}")
    mm = capb_long.merge(cab_long, on=["geo", "year"])
    mm = mm[(mm.year.between(Y0, Y1))].dropna()
    gap = mm["UBLGAP"] - mm["UBLGBP"]
    print(f"  UBLGAP - UBLGBP (= minus cyclically-adjusted net interest, % pot. GDP; expect <=0): mean={gap.mean():.2f}, "
          f"share<=0 = {(gap <= 1e-9).mean():.3f}  -> UBLGBP is the primary (ex-interest) CAB; UBLGAP is the total CAB.")
    idx_year = int(meta["indexed_at"][:4])
    # AMECO/DBnomics does not flag forecast years. Rule: the vintage is indexed in 2026-06 => Spring-2026 forecast;
    # forecast years are t and t+1 (=2026, 2027), latest outturn t-1 = 2025.
    last_series_year = int(capb_long.dropna().year.max())
    last_obs = idx_year - 1
    print(f"  Last year in series={last_series_year}; vintage year={idx_year} (June => Spring forecast). Rule: outturn <= {last_obs}; "
          f"series years > {last_obs} are forecasts. Window cap Y1={Y1} <= {last_obs}, so no forecast years enter (AMECO flags nothing in the API; rule-based).")
    capb_df = capb_long[capb_long.year.between(Y0, min(Y1, last_obs))]
    capb = to_matrix(capb_df, "UBLGBP")
    obs = ~np.isnan(capb)
    n_per = obs.sum(1)
    print(f"\nCountries: N={len(EU27)}; balanced (all {len(YEARS)} years)={int((n_per == len(YEARS)).sum())}; "
          f"unbalanced={int((n_per < len(YEARS)).sum())}; country-years observed={int(obs.sum())} of {capb.size}")
    miss = {EU27[i]: [YEARS[j] for j in range(len(YEARS)) if not obs[i, j]] for i in range(len(EU27)) if n_per[i] < len(YEARS)}
    print("Missing by country (years):")
    for g, ys in miss.items():
        print(f"  {g}: {len(ys)} missing -> {ys[0]}-{ys[-1] if len(ys) > 1 else ys[0]} ({ys if len(ys) < 9 else str(ys[:3]) + '...'})")
    flat = capb[obs]
    print(f"\nCAPB pooled: mean={flat.mean():.3f} SD={flat.std():.3f} min={flat.min():.2f} max={flat.max():.2f}")
    cm_ = np.nanmean(capb, 1)
    within = capb - cm_[:, None]
    res = twoway_demean(capb)
    print(f"within-country SD (country-demeaned)={sd(within):.3f}; between SD of country means={cm_.std():.3f}; "
          f"SD after country+year FE={sd(res):.3f}")
    fullc = ~np.isnan(capb).any(1)
    dc = decomposition(capb[fullc], f"CAPB [balanced subset: {fullc.sum()} countries]")
    print(f"CAPB variance shares (balanced subset, {fullc.sum()} countries): between={dc['share_between']:.3f}, "
          f"year={dc['share_year']:.3f}, two-way residual={dc['share_resid']:.3f}")
    rr_ = res[~np.isnan(res)]
    mad_sd = 1.4826 * np.median(np.abs(rr_ - np.median(rr_)))
    top = sorted(((round(float(abs(res[i, j])), 1), EU27[i], YEARS[j], round(float(capb[i, j]), 1)) for i in range(len(EU27))
                  for j in range(len(YEARS)) if not np.isnan(res[i, j])), reverse=True)[:5]
    print(f"Robust residual SD (1.4826*MAD)={mad_sd:.3f} vs classical {sd(res):.3f}; "
          f"largest |residuals| (|res|, geo, year, CAPB): {top}")
    num = den = 0.0
    rhos = []
    for i in range(len(EU27)):
        e = res[i]
        ok = ~np.isnan(e[1:]) & ~np.isnan(e[:-1])
        a, b = e[1:][ok], e[:-1][ok]
        num += (a * b).sum()
        den += (b * b).sum()
        if len(a) > 5:
            rhos.append((a * b).sum() / (b * b).sum())
    rho_obs = num / den
    print(f"AR(1) of two-way residual: pooled rho={rho_obs:.3f}; mean of per-country rho={np.mean(rhos):.3f} "
          f"(range {np.min(rhos):.2f} to {np.max(rhos):.2f}); note FE-demeaning biases rho downward by ~ -(1+rho)/T = {-(1 + rho_obs) / len(YEARS):.3f}")
    print(f"Effective cluster count = {len(EU27)} (t critical, df=26: {stats.t.ppf(1 - ALPHA / 2, 26):.3f})")

    # ------------------------------------------------------------------ (3) effective sample
    banner("(3) EFFECTIVE SAMPLE: OLDDEP1 and CAPB both observed, 1995-2023")
    both = obs & ~np.isnan(old)
    print(f"Effective country-years={int(both.sum())} of {both.size} ({both.sum() / both.size:.1%}); countries={int((both.sum(1) > 0).sum())}")
    print("Earliest usable CAPB year per country (CAPB observed; both-observed year in brackets):")
    first = {}
    for i, g in enumerate(EU27):
        fc = YEARS[int(np.argmax(obs[i]))] if obs[i].any() else None
        fb = YEARS[int(np.argmax(both[i]))] if both[i].any() else None
        first[g] = (fc, fb)
    print("  " + "; ".join(f"{g}:{a}" + (f"[{b}]" if b != a else "") for g, (a, b) in first.items()))
    print(f"  countries with CAPB from 1995 = {sum(1 for a, _ in first.values() if a == 1995)}; "
          f"later start: {[(g, a) for g, (a, _) in first.items() if a != 1995]}")

    # ------------------------------------------------------------------ (2b) MDE Monte Carlo
    banner(f"(2b) INDICATIVE MDE -- Monte Carlo, reps={N_REPS}, seed={SEED}, alpha={ALPHA}, power={POWER}; "
           "ELECTION CALENDARS ARE PLACEHOLDERS")
    M, ci, ti = build_annihilator(both)
    nobs = len(ci)
    n_c, n_t = both.shape
    sigma = sd(twoway_demean(np.where(both, capb, np.nan)))
    tcrit = stats.t.ppf(1 - ALPHA / 2, n_c - 1)
    zstd = np.where(both, (old - np.nanmean(np.where(both, old, np.nan))) / np.nanstd(np.where(both, old, np.nan)), np.nan)
    z_vec = zstd[ci, ti]
    Mz = M @ z_vec
    print(f"Estimation sample N={nobs}, clusters={n_c}; residual SD used (two-way, estimation sample)={sigma:.3f} pp pot. GDP; "
          f"t crit (df={n_c - 1})={tcrit:.3f}; z standardised on estimation sample (z main effect included in the interaction model).")
    print("Model: y = b1*Elec + [b2*z + b3*Elec*z] + country FE + year FE + AR(1) noise; country-clustered CR1 SEs. "
          "Dummy models are y = b*D + FE.")

    scen_rho = {"rho=0": 0.0, f"rho=observed ({rho_obs:.2f})": rho_obs, "rho=0.8": 0.8}
    results = {}
    batch = 500
    for rname, rho in scen_rho.items():
        draws = {k: ([], []) for k in ("election", "pre-election", "interaction")}
        done = 0
        while done < N_REPS:
            rr = min(batch, N_REPS - done)
            elec, pre = draw_calendars(RNG, rr, n_c, n_t)
            e = ar1_noise(RNG, rr, n_c, n_t, sigma, rho)
            ey = np.stack([e[r][ci, ti] for r in range(rr)], 1)          # (nobs,rr)
            ey_t = M @ ey
            # dummy-only models: X is replicate-specific -> loop in small chunks via per-rep X
            for key, cal in (("election", elec), ("pre-election", pre)):
                bs, ss = [], []
                Dm = np.stack([cal[r][ci, ti] for r in range(rr)], 1)
                Dt = M @ Dm
                for r in range(rr):
                    b, s = cluster_ols(Dt[:, [r]], ey_t[:, [r]], ci, n_c, n_t - 1)
                    bs.append(b[0, 0]); ss.append(s[0, 0])
                draws[key][0].append(np.array(bs)); draws[key][1].append(np.array(ss))
            # interaction model: regressors [Elec, z, Elec*z]
            bs, ss = [], []
            Dm = np.stack([elec[r][ci, ti] for r in range(rr)], 1)
            for r in range(rr):
                X = np.column_stack([Dm[:, r], z_vec, Dm[:, r] * z_vec])
                Xt = M @ X
                b, s = cluster_ols(Xt, ey_t[:, [r]], ci, n_c, n_t - 1)
                bs.append(b[0, 2]); ss.append(s[0, 2])
            draws["interaction"][0].append(np.array(bs)); draws["interaction"][1].append(np.array(ss))
            done += rr
        results[rname] = {}
        for key, (b_l, s_l) in draws.items():
            b0, se = np.concatenate(b_l), np.concatenate(s_l)
            mde = mde_from_draws(b0, se, tcrit)
            size = float(np.mean(np.abs(b0 / se) > tcrit))
            results[rname][key] = (mde, float(np.median(se)), size, float(b0.std()))
    print(f"\n{'scenario':<24}{'effect':<14}{'MDE (pp pot. GDP)':>19}{'median SE':>11}{'MC SD(b)':>10}{'null rej. rate':>16}{'MDE/sigma':>11}")
    for rname, d in results.items():
        for key, (mde, se_med, size, sdb) in d.items():
            lab = key + (" (per +1 SD z)" if key == "interaction" else "")
            print(f"{rname:<24}{lab:<14}{mde:>19.3f}{se_med:>11.3f}{sdb:>10.3f}{size:>16.3f}{mde / sigma:>11.3f}")
    print(f"MDE scales linearly in sigma: with the robust sigma ({mad_sd:.2f}) the MDEs are x{mad_sd / sigma:.2f} of the above (outlier-robust lower bound).")
    print("\nAnalytic cross-check MDE ~ (t_crit + z_0.8) * median SE =", {r: {k: round(float((tcrit + stats.norm.ppf(POWER)) * v[1]), 3) for k, v in d.items()} for r, d in results.items()})
    print("\nLiterature (see report for verification status): Shi & Svensson (2006, JPubE 90:1367-1389) report election-year headline "
          "deficits rising by close to 1% of GDP on average (abstract, verified via search summary only). "
          "Structural/cyclically-adjusted EU evidence is small: Bednar (2019, system-GMM, EU-28 1995-2016) reports about -0.41 pp "
          "structural balance in the year before elections (second-hand via search snippet; NOT verified against the paper).")

    # ------------------------------------------------------------------ (4) gate inputs
    banner("(4) GATE INPUTS (proposals computed in the report from these)")
    tw_old = sd(twoway_demean(old))
    print(f"G1 input: OLDDEP1 two-way SD={tw_old:.3f} pp; within SD={np.nanstd(old - cmean[:, None]):.3f} pp; "
          f"z-units two-way SD={sd(twoway_demean(z_all)):.3f}")
    print(f"G2 input: election-dummy MDE (rho observed)={results[f'rho=observed ({rho_obs:.2f})']['election'][0]:.3f} pp; "
          f"rho=0.8: {results['rho=0.8']['election'][0]:.3f} pp")
    print(f"G3 input: effective country-years={int(both.sum())}/{both.size}; CAPB countries from 1995={sum(1 for a, _ in first.values() if a == 1995)}/27; "
          f"min per-country CAPB obs={int(n_per.min())}")
    print("\nDONE (nothing written to disk).")


if __name__ == "__main__":
    main()
