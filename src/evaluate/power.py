"""Gate 3b: simulation-based power of the confirmatory model M1 on the real election calendar and final sample.

Model (proposal 9.2, M1), with country effects ``alpha_i`` and year effects ``lambda_t``::

    CAPB_it = alpha_i + lambda_t + beta_S W_S + beta_E W_E + beta_U W_U [+ beta_D W_D] + rho Post
              + gamma_B W_S * Abar_i + gamma_W W_S * (A_{i,t-1} - Abar_i) + eta A_{i,t-1} + e_it

``A`` is OLDDEP1 lagged one year, standardised on the estimation sample; ``Abar_i`` is its country mean. The
between and within interaction regressors are scaled to unit standard deviation so that ``gamma_B`` and
``gamma_W`` are effects *per +1 SD of the respective component*. ``W_U`` (unclassified) and ``W_D`` (delayed)
enter as separate nuisance terms (Gate 3a default); a zero-variance column (``W_D`` on the final sample) is
dropped automatically.

Method (everything below is vectorised; no ``statsmodels`` call and no row-wise ``.loc`` in any simulation)
--------------------------------------------------------------------------------------------------------
* Frisch-Waugh-Lovell: an orthonormal basis ``Q_fe`` of the country and year dummies is built once (QR). Any
  outcome or noise matrix is residualised on the fixed effects *and* on the regressors by matrix products
  with ``Q_z = [Q_fe, Q_x]``. For target ``j`` the OLS coefficient is the linear functional ``b_j = h_j' y`` with
  ``h_j = X~ (X~'X~)^{-1} e_j`` and ``X~`` the regressors residualised on the fixed effects.
* CR1 (country-clustered) variance of ``b_j``: ``c * sum_g (h_jg' u_g)^2`` with ``u = y - Z theta`` the full-model
  residual and ``c = G/(G-1) * (N-1)/(N-K)``. ``K`` counts the year effects and the regressors, not the
  country effects, which are nested in the clusters (Stata ``xtreg, fe vce(cluster)`` / ``reghdfe`` convention).
* Because the model is linear and ``u = M_Z y`` annihilates every column of ``Z``, adding a true effect
  ``beta * x_j`` to the outcome shifts ``b_j`` by exactly ``beta`` and leaves ``u`` and the CR1 standard error
  unchanged. Hence one set of null draws ``(b0_r, se_r)`` gives the power at every ``beta``:
  ``power(beta) = mean_r 1{ |b0_r + beta| > t_crit * se_r }`` and the 80 per cent minimum detectable effect
  (MDE) solves ``power(beta) = 0.80`` exactly (bisection on this monotone function).
* Wild-cluster bootstrap-t with the null imposed (Cameron, Gelbach and Miller 2008; Roodman et al. 2019). The
  restricted residual is ``u~ = u + b_j r_j`` (``r_j`` = target regressor residualised on the fixed effects and
  the other regressors). The bootstrap numerator is ``alpha' v`` and the bootstrap cluster scores are
  ``A v`` with the ``G x G`` matrix ``A = diag(alpha) - Gamma S'``; so thousands of bootstrap draws cost one
  small matrix product each (see ``wild_bootstrap_reject``).

Randomness: every generator is ``numpy.random.default_rng(SeedSequence([SEED, *keys]))`` with ``SEED = 42``
and a documented integer key per scenario and purpose, so each result is reproducible and scenarios are
independent. Raw data are read through ``sample.py`` (read-only). Real-data *effect estimates* are never
computed or printed: only residuals enter the calibration (power is calibrated without peeking at estimates).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
from scipy import optimize, stats

_EVALUATE = Path(__file__).resolve().parent
sys.path.insert(0, str(_EVALUATE))
import sample  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]

SEED = 42  # master seed; every stream is SeedSequence([SEED, key, ...])
ALPHA = 0.05  # two-sided test size
TARGET_POWER = 0.80  # conventional power for the MDE
N_NULL_DRAWS = 20_000  # null draws per scenario for the CR1 MDE (Monte Carlo SE of a 5% rejection rate: 0.0015)
BATCH = 2_000  # noise matrices are generated and residualised in batches of this many columns
N_WCB_DATASETS = 2_000  # simulated datasets per scenario for the wild-cluster bootstrap (task minimum: 300)
N_WCB_DRAWS = 999  # bootstrap draws per dataset; (B+1) * alpha = 50 is an integer so the test is exact
WINSOR_TAIL = 0.01  # winsorise calibration residuals at the 1st / 99th percentile (sensitivity)
MIN_CD_OVERLAP = 10  # minimum common years for a country pair in the cross-section dependence diagnostic
RANK_TOL = 1e-9  # relative tolerance for the rank checks of the design

TARGETS_M1 = {"beta_S": "W_S", "gamma_B": "WS_x_between", "gamma_W": "WS_x_within"}
TARGETS_POOLED = {"beta_S": "W_S", "gamma_pooled": "WS_x_A"}

# Seed keys (documented, fixed): scenario index in SCENARIOS, then purpose.
PURPOSE_NULL = 1
PURPOSE_VERIFY = 2
PURPOSE_WCB = 3
PURPOSE_CALIB = 4
PURPOSE_WCB_WEIGHTS = 5


def make_rng(*keys: int) -> np.random.Generator:
    """``default_rng`` seeded by ``SeedSequence([SEED, *keys])`` (``SEED = 42``)."""
    return np.random.default_rng(np.random.SeedSequence([SEED, *keys]))


# ---------------------------------------------------------------------------------------------
# Design
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Design:
    """Pre-computed linear-algebra objects of one regression design (rows sorted by country, then year).

    ``h[name]`` and ``r[name]`` are the FWL functional and the residualised target regressor (``h = r / r'r``);
    ``gamma[name]`` stacks ``h_g' Q_z,g`` by cluster; ``cr1`` is the CR1 small-sample constant.
    """

    label: str
    codes: np.ndarray
    country_idx: np.ndarray
    year: np.ndarray
    year_pos: np.ndarray
    n_grid_years: int
    y: np.ndarray
    x_names: list[str]
    x: np.ndarray
    q_fe: np.ndarray
    q_z: np.ndarray
    starts: np.ndarray
    counts: np.ndarray
    lag_rows: np.ndarray
    cur_rows: np.ndarray
    targets: dict[str, str]
    h: dict[str, np.ndarray]
    r: dict[str, np.ndarray]
    gamma: dict[str, np.ndarray]
    n_obs: int
    n_clusters: int
    n_years: int
    k_params: int
    cr1: float
    t_crit: float
    scale: dict[str, float] = field(default_factory=dict)

    @property
    def sample_label(self) -> str:
        """Short description used in report tables."""
        return f"{self.label}: N={self.n_obs}, G={self.n_clusters}"


def _orthonormal_basis(matrix: np.ndarray, what: str) -> np.ndarray:
    """Orthonormal basis of the column space of a full-column-rank matrix (QR); raise if rank deficient."""
    q, r = np.linalg.qr(matrix, mode="reduced")
    diag = np.abs(np.diag(r))
    if diag.min() <= RANK_TOL * max(diag.max(), 1.0):
        raise ValueError(f"{what}: design is rank deficient (min |R_jj| = {diag.min():.3g})")
    return q


def _fixed_effect_basis(country_idx: np.ndarray, year: np.ndarray) -> np.ndarray:
    """Orthonormal basis of country dummies plus year dummies (first year dropped)."""
    n = len(country_idx)
    g = int(country_idx.max()) + 1
    years = np.unique(year)
    dummies = np.zeros((n, g + len(years) - 1))
    dummies[np.arange(n), country_idx] = 1.0
    year_col = np.searchsorted(years, year)
    keep = year_col > 0
    dummies[np.arange(n)[keep], g + year_col[keep] - 1] = 1.0
    return _orthonormal_basis(dummies, "fixed effects")


def regressors_from_frame(frame: pd.DataFrame, spec: str = "m1") -> tuple[pd.DataFrame, dict[str, float], dict[str, str]]:
    """Regressor frame, scale constants and target map for a specification.

    ``spec`` is ``"m1"`` (between/within split), ``"pooled"`` (single interaction ``W_S * A``),
    ``"m1_period"`` (M1 plus ``W_S`` x period dummies for 2008-2019 and 2020 on, proposal 9.2; ``beta_S`` is then
    the pre-2008 effect) or ``"m1_period_centered"`` (the same with the period dummies centred on their sample
    means, so ``beta_S`` is the average-period effect). ``A`` is the lagged
    OLDDEP1 standardised to mean 0 and SD 1 (population SD) on the frame passed in, i.e. the estimation sample.
    """
    a = frame["olddep1_lag"].to_numpy(float)
    z = (a - a.mean()) / a.std(ddof=0)
    code = frame["eurostat_code"].to_numpy()
    abar = pd.Series(z).groupby(code).transform("mean").to_numpy()
    within = z - abar
    sd_between, sd_within = float(abar.std(ddof=0)), float(within.std(ddof=0))
    cols: dict[str, np.ndarray] = {}
    for name in ("W_S", "W_E", "W_D", "W_U", "Post"):
        values = frame[name].to_numpy(float)
        if np.ptp(values) > 0:  # a constant (all-zero) column is not identified: W_D on the final sample
            cols[name] = values
    w_s = frame["W_S"].to_numpy(float)
    if spec in ("m1", "m1_period", "m1_period_centered"):
        cols["WS_x_between"] = w_s * abar / sd_between
        cols["WS_x_within"] = w_s * within / sd_within
        targets = dict(TARGETS_M1)
    elif spec == "pooled":
        cols["WS_x_A"] = w_s * z
        targets = dict(TARGETS_POOLED)
    else:
        raise ValueError(f"unknown spec {spec!r}")
    cols["A_lag"] = z
    if spec in ("m1_period", "m1_period_centered"):
        year = frame["year"].to_numpy()
        middle, late = ((year >= 2008) & (year <= 2019)).astype(float), (year >= 2020).astype(float)
        if spec == "m1_period_centered":
            middle, late = middle - middle.mean(), late - late.mean()
        cols["WS_x_2008_2019"] = w_s * middle
        cols["WS_x_2020_on"] = w_s * late
    cols = {name: values for name, values in cols.items() if np.ptp(values) > 0}  # drop constant columns (e.g. no 2020+ rows)
    scale = {"sd_between_z": sd_between, "sd_within_z": sd_within, "sd_a_pp": float(a.std(ddof=0))}
    return pd.DataFrame(cols), scale, targets


def build_design(frame: pd.DataFrame, spec: str = "m1", label: str = "final", regressors: pd.DataFrame | None = None,
                 targets: dict[str, str] | None = None, scale: dict[str, float] | None = None) -> Design:
    """Build the :class:`Design` for a sample frame (columns of ``sample.build_panel``).

    ``regressors``/``targets`` may be supplied directly (used by the fiscal-rule stretch and by tests).
    """
    frame = frame.sort_values(["eurostat_code", "year"]).reset_index(drop=True)
    if regressors is None:
        regressors, scale, targets = regressors_from_frame(frame, spec)
    assert targets is not None
    codes = frame["eurostat_code"].to_numpy()
    country_idx = pd.factorize(codes)[0]
    year = frame["year"].to_numpy(int)
    n, g = len(frame), int(country_idx.max()) + 1
    q_fe = _fixed_effect_basis(country_idx, year)
    x = regressors.to_numpy(float)
    x_tilde = x - q_fe @ (q_fe.T @ x)
    q_x = _orthonormal_basis(x_tilde, "regressors after fixed effects")
    q_z = np.hstack([q_fe, q_x])
    gram_inv = np.linalg.inv(x_tilde.T @ x_tilde)
    h_all = x_tilde @ gram_inv
    starts = np.flatnonzero(np.r_[True, codes[1:] != codes[:-1]])
    counts = np.diff(np.r_[starts, n])
    n_years = len(np.unique(year))
    k_params = (n_years - 1) + x.shape[1]
    cr1 = g / (g - 1) * (n - 1) / (n - k_params)
    names = list(regressors.columns)
    h, r, gamma = {}, {}, {}
    for tname, col in targets.items():
        vec = h_all[:, names.index(col)]
        h[tname] = vec
        r[tname] = vec / float(vec @ vec)
        gamma[tname] = np.add.reduceat(vec[:, None] * q_z, starts, axis=0)
    prev_ok = np.r_[False, (codes[1:] == codes[:-1]) & (year[1:] - year[:-1] == 1)]
    cur_rows = np.flatnonzero(prev_ok)
    year_min = int(year.min())
    return Design(
        label=label, codes=codes, country_idx=country_idx, year=year, year_pos=year - year_min,
        n_grid_years=int(year.max()) - year_min + 1, y=frame["capb"].to_numpy(float), x_names=names, x=x,
        q_fe=q_fe, q_z=q_z, starts=starts, counts=counts, lag_rows=cur_rows - 1, cur_rows=cur_rows,
        targets=targets, h=h, r=r, gamma=gamma, n_obs=n, n_clusters=g, n_years=n_years, k_params=k_params,
        cr1=float(cr1), t_crit=float(stats.t.ppf(1 - ALPHA / 2, g - 1)), scale=scale or {},
    )


def residuals(design: Design, y: np.ndarray) -> np.ndarray:
    """Full-model residuals ``u = y - Z theta`` for a vector or matrix of outcomes (columns = datasets)."""
    return y - design.q_z @ (design.q_z.T @ y)


def estimate(design: Design, y: np.ndarray, names: list[str] | None = None) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """OLS coefficient and CR1 standard error of each target for a matrix of outcomes ``y`` (N x B).

    Returns ``{target: (b, se)}`` with arrays of length B. No regression routine is called: the coefficient is
    ``h'y`` and the variance is ``cr1 * sum_g (h_g' u_g)^2`` (see module docstring).
    """
    y2 = y[:, None] if y.ndim == 1 else y
    u = residuals(design, y2)
    out = {}
    for name in names or list(design.targets):
        h = design.h[name]
        scores = np.add.reduceat(h[:, None] * u, design.starts, axis=0)
        out[name] = (h @ y2, np.sqrt(design.cr1 * (scores**2).sum(axis=0)))
    return out


# ---------------------------------------------------------------------------------------------
# Calibration from the real CAPB panel
# ---------------------------------------------------------------------------------------------
def _pair_ar1(u: np.ndarray, design: Design, standardise: bool = True) -> np.ndarray:
    """Pooled AR(1) coefficient of residuals over consecutive-year pairs (columns = datasets).

    The residual already has zero mean in every country (country effects are in ``Z``). With ``standardise`` each
    country's residual is divided by its own residual SD, so that the weights match a generator with
    country-specific variances and a common ``rho``.
    """
    u2 = u[:, None] if u.ndim == 1 else u
    if standardise:
        ss = np.add.reduceat(u2**2, design.starts, axis=0) / design.counts[:, None]
        u2 = u2 / np.sqrt(ss)[design.country_idx]
    lagged, current = u2[design.lag_rows], u2[design.cur_rows]
    rho = (lagged * current).sum(axis=0) / (lagged**2).sum(axis=0)
    return rho[0] if u.ndim == 1 else rho


def nickell_bias(rho: float, t_obs: float) -> float:
    """Nickell (1981) large-N asymptotic bias ``plim(rho_hat) - rho`` of the within estimator of an AR(1).

    Exact expression for ``T`` observations per unit (leading term ``-(1+rho)/(T-1)``).
    """
    t = float(t_obs)
    geo = float(np.sum(rho ** np.arange(int(round(t)))))  # (1 - rho^T) / (1 - rho), T rounded to an integer
    numerator = -(1 + rho) / (t - 1) * (1 - geo / t)
    denominator = 1 - 2 * rho / ((1 - rho) * (t - 1)) * (1 - geo / t)
    return float(numerator / denominator)


def nickell_corrected_rho(rho_hat: float, t_obs: float) -> float:
    """Solve ``rho + nickell_bias(rho, T) = rho_hat`` for ``rho`` (analytic Nickell correction)."""
    return float(optimize.brentq(lambda rho: rho + nickell_bias(rho, t_obs) - rho_hat, -0.9, 0.99))


@dataclass(frozen=True)
class ArNoise:
    """Gaussian AR(1) noise with country-specific marginal SDs, generated on the full (country x year) grid.

    ``nu_t = rho nu_{t-1} + sqrt(1 - rho^2) xi_t`` with ``nu_0 ~ N(0, 1)`` (stationary start), scaled by
    ``sigma[country]``. Countries are independent. Missing years inside a span are handled by indexing the grid.
    """

    design: Design
    sigma: np.ndarray
    rho: float

    def draw(self, rng: np.random.Generator, n_draws: int) -> np.ndarray:
        """N x ``n_draws`` matrix of noise aligned with the design rows."""
        d = self.design
        xi = rng.standard_normal((d.n_clusters, d.n_grid_years, n_draws))
        nu = np.empty_like(xi)
        nu[:, 0] = xi[:, 0]
        scale = np.sqrt(1 - self.rho**2)
        for t in range(1, d.n_grid_years):
            nu[:, t] = self.rho * nu[:, t - 1] + scale * xi[:, t]
        return nu[d.country_idx, d.year_pos] * self.sigma[d.country_idx][:, None]


@dataclass(frozen=True)
class BlockBootstrapNoise:
    """Moving-block bootstrap of whole year-residual vectors (keeps each year's cross-section together).

    ``grid`` is a (years x countries) matrix of calibration residuals with NaN where a cell is not in the
    sample. A simulated sample of ``T`` years is the concatenation of blocks of ``block`` consecutive years
    drawn with uniformly random start years (truncated to ``T``); simulated year ``s`` takes the whole
    residual vector of the drawn year, so cross-country dependence, heteroskedasticity and serial dependence
    within blocks are inherited. A cell that is NaN in the drawn year (a country not observed then, 14 cells)
    is replaced by a residual drawn uniformly from the same country's observed years.
    """

    design: Design
    grid: np.ndarray
    block: int

    def draw(self, rng: np.random.Generator, n_draws: int) -> np.ndarray:
        """N x ``n_draws`` matrix of resampled residuals aligned with the design rows."""
        d, t = self.design, self.design.n_grid_years
        n_blocks = int(np.ceil(t / self.block))
        starts = rng.integers(0, t - self.block + 1, size=(n_draws, n_blocks))
        idx = (starts[:, :, None] + np.arange(self.block)).reshape(n_draws, -1)[:, :t]
        values = self.grid[idx]  # (draws, T, G)
        missing = np.isnan(values)
        if missing.any():
            for g in range(d.n_clusters):
                cells = missing[:, :, g]
                if cells.any():
                    pool = self.grid[:, g][~np.isnan(self.grid[:, g])]
                    values[:, :, g][cells] = rng.choice(pool, size=int(cells.sum()))
        return values[:, d.year_pos, d.country_idx].T


@dataclass(frozen=True)
class Calibration:
    """Noise calibration from the real-panel residuals of the full M1 fit."""

    resid: np.ndarray
    sigma: np.ndarray
    df_factor: float
    grid: np.ndarray
    rho_raw_pooled: float
    rho_raw_standardised: float
    rho_nickell_corrected: float
    rho_corrected: float
    mean_t: float
    heterogeneity: dict[str, float]
    dependence: dict[str, float]
    winsorised: bool


def residual_grid(design: Design, resid: np.ndarray) -> np.ndarray:
    """(years x countries) matrix of residuals with NaN for cells not in the sample."""
    grid = np.full((design.n_grid_years, design.n_clusters), np.nan)
    grid[design.year_pos, design.country_idx] = resid
    return grid


def cross_section_dependence(grid: np.ndarray) -> dict[str, float]:
    """Mean pairwise correlation and Pesaran (2015) CD statistic of residual columns (pairs with enough overlap).

    ``CD = sqrt(2 / (G (G - 1))) * sum_{i<j} sqrt(T_ij) rho_ij``, the unbalanced-panel form; asymptotically N(0,1)
    under cross-sectional independence.
    """
    g = grid.shape[1]
    rhos, stats_ = [], []
    for i in range(g):
        for j in range(i + 1, g):
            ok = ~np.isnan(grid[:, i]) & ~np.isnan(grid[:, j])
            if ok.sum() >= MIN_CD_OVERLAP:
                rho_ij = float(np.corrcoef(grid[ok, i], grid[ok, j])[0, 1])
                rhos.append(rho_ij)
                stats_.append(np.sqrt(ok.sum()) * rho_ij)
    return {
        "mean_pairwise_corr": float(np.mean(rhos)),
        "pesaran_cd": float(np.sqrt(2 / (g * (g - 1))) * np.sum(stats_)),
        "n_pairs": float(len(rhos)),
        "share_positive": float(np.mean(np.array(rhos) > 0)),
    }


def winsorise(values: np.ndarray, tail: float = WINSOR_TAIL) -> np.ndarray:
    """Clip to the ``tail`` and ``1 - tail`` sample quantiles."""
    lo, hi = np.quantile(values, [tail, 1 - tail])
    return np.clip(values, lo, hi)


def corrected_rho_indirect(design: Design, sigma: np.ndarray, rho_hat: float, n_sim: int = 1_000) -> float:
    """Indirect-inference (simulation) bias correction of the AR(1) estimate.

    Find ``rho`` such that the average of the *same* estimator (residual from the full M1 fit, standardised
    pooled AR(1)) applied to AR(1) noise with that ``rho`` equals the observed estimate ``rho_hat``. Common random
    numbers (fixed seed per evaluation) keep the objective smooth. This corrects the within-demeaning
    (Nickell) bias and the small-sample bias of the two-way residual projection in one step, on the actual
    sample geometry.
    """
    def gap(rho: float) -> float:
        noise = ArNoise(design, sigma, rho).draw(make_rng(PURPOSE_CALIB, 0), n_sim)
        return float(_pair_ar1(residuals(design, noise), design).mean() - rho_hat)

    return float(optimize.brentq(gap, -0.5, 0.97, xtol=1e-4))


def calibrate(design: Design, winsorised: bool = False) -> Calibration:
    """Calibrate noise from the residuals of the full M1 fit on the real CAPB panel.

    Steps: (1) residuals ``u`` of the fit (optionally winsorised at the 1st/99th percentile); (2) country SDs
    ``sigma_i = sqrt(mean_i u^2 * N / (N - K_all))`` with the degrees-of-freedom factor for the ``K_all``
    parameters (fixed effects and regressors) absorbed by the fit; (3) pooled AR(1) coefficient on the
    country-standardised residuals, and its bias corrections: the analytic Nickell (1981) correction at the mean
    number of observations per country, and the simulation (indirect-inference) correction, which is the one
    used; (4) the (year x country) residual grid for the block bootstrap; (5) cross-section-dependence and
    heteroskedasticity diagnostics.
    """
    u = residuals(design, design.y)
    if winsorised:
        u = winsorise(u)
        u = u - np.add.reduceat(u, design.starts)[design.country_idx] / design.counts[design.country_idx]  # re-centre by country
    k_all = design.q_z.shape[1]
    df_factor = float(np.sqrt(design.n_obs / (design.n_obs - k_all)))
    raw_sigma = np.sqrt(np.add.reduceat(u**2, design.starts) / design.counts)
    sigma = raw_sigma * df_factor
    rho_std = float(_pair_ar1(u, design, standardise=True))
    rho_raw = float(_pair_ar1(u, design, standardise=False))
    mean_t = float(design.counts.mean())
    rho_nickell = nickell_corrected_rho(rho_std, mean_t)
    rho_ii = corrected_rho_indirect(design, sigma, rho_std)
    grid = residual_grid(design, u * df_factor)
    sd_order = np.sort(sigma)
    heterogeneity = {
        "sigma_min": float(sd_order[0]), "sigma_median": float(np.median(sigma)), "sigma_max": float(sd_order[-1]),
        "sigma_max_to_median": float(sd_order[-1] / np.median(sigma)),
        "sigma_pooled": float(np.sqrt((u**2).mean()) * df_factor),
        "sigma_robust_mad": float(1.4826 * np.median(np.abs(u - np.median(u))) * df_factor),
        "sigma_argmax_country": str(design.codes[design.starts][int(np.argmax(sigma))]),
        "levene_p": float(stats.levene(*np.split(u, np.cumsum(design.counts)[:-1]), center="median").pvalue),
    }
    return Calibration(
        resid=u * df_factor, sigma=sigma, df_factor=df_factor, grid=grid, rho_raw_pooled=rho_raw,
        rho_raw_standardised=rho_std, rho_nickell_corrected=rho_nickell, rho_corrected=rho_ii, mean_t=mean_t,
        heterogeneity=heterogeneity, dependence=cross_section_dependence(grid), winsorised=winsorised,
    )


# ---------------------------------------------------------------------------------------------
# CR1 null draws, MDE solution
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class NullDraws:
    """Coefficient and CR1 SE draws under the null, for each target."""

    b0: dict[str, np.ndarray]
    se: dict[str, np.ndarray]


def null_draws(design: Design, noise: "ArNoise | BlockBootstrapNoise", n_draws: int, rng: np.random.Generator,
               batch: int = BATCH) -> NullDraws:
    """Simulate ``n_draws`` null datasets (outcome = noise) and collect ``(b0, se)`` per target."""
    b0 = {t: [] for t in design.targets}
    se = {t: [] for t in design.targets}
    done = 0
    while done < n_draws:
        size = min(batch, n_draws - done)
        result = estimate(design, noise.draw(rng, size))
        for t, (b, s) in result.items():
            b0[t].append(b)
            se[t].append(s)
        done += size
    return NullDraws({t: np.concatenate(v) for t, v in b0.items()}, {t: np.concatenate(v) for t, v in se.items()})


def power_at(b0: np.ndarray, se: np.ndarray, crit: float, beta: float) -> float:
    """Rejection rate of ``|t| > crit`` when a true effect ``beta`` is added: ``mean 1{|b0 + beta| > crit * se}``."""
    return float(np.mean(np.abs(b0 + beta) > crit * se))


def solve_mde(b0: np.ndarray, se: np.ndarray, crit: float, power: float = TARGET_POWER, tol: float = 1e-7) -> float:
    """Smallest ``beta > 0`` with ``power_at(...) >= power`` (bisection; the power curve is monotone in ``beta``)."""
    hi = (crit + 3.0) * float(np.median(se))
    while power_at(b0, se, crit, hi) < power:
        hi *= 2.0
    lo = 0.0
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        if power_at(b0, se, crit, mid) >= power:
            hi = mid
        else:
            lo = mid
    return hi


def analytic_mde(median_se: float, crit: float, power: float = TARGET_POWER) -> float:
    """Textbook cross-check ``(t_crit + z_power) * se`` (one-sided power approximation)."""
    return float((crit + stats.norm.ppf(power)) * median_se)


def summarise_cr1(draws: NullDraws, design: Design) -> dict[str, dict[str, float]]:
    """Per target: CR1 size, MDE, size-adjusted MDE (empirical 95% critical value) and the analytic cross-check."""
    out = {}
    for t in design.targets:
        b0, se = draws.b0[t], draws.se[t]
        t_abs = np.abs(b0) / se
        crit_emp = float(np.quantile(t_abs, 1 - ALPHA))
        out[t] = {
            "size_cr1": float(np.mean(t_abs > design.t_crit)),
            "median_se": float(np.median(se)),
            "sd_b0": float(b0.std()),
            "crit_empirical": crit_emp,
            "mde_cr1": solve_mde(b0, se, design.t_crit),
            "mde_cr1_size_adjusted": solve_mde(b0, se, crit_emp),
            "mde_analytic": analytic_mde(float(np.median(se)), design.t_crit),
        }
    return out


# ---------------------------------------------------------------------------------------------
# Wild-cluster bootstrap-t (null imposed), vectorised across bootstrap draws and datasets
# ---------------------------------------------------------------------------------------------
WEBB_VALUES = np.array([-np.sqrt(1.5), -1.0, -np.sqrt(0.5), np.sqrt(0.5), 1.0, np.sqrt(1.5)])  # Webb (2014) six-point law
WCB_CHUNK = 50  # datasets per vectorised bootstrap chunk


def bootstrap_weights(rng: np.random.Generator, shape: tuple[int, ...], kind: str) -> np.ndarray:
    """Cluster-level bootstrap weights: ``rademacher`` (+-1 with prob 1/2) or ``webb`` (six-point, mean 0, variance 1)."""
    if kind == "rademacher":
        return rng.integers(0, 2, size=shape).astype(float) * 2.0 - 1.0
    if kind == "webb":
        return WEBB_VALUES[rng.integers(0, 6, size=shape)]
    raise ValueError(f"unknown weight kind {kind!r}")


@dataclass(frozen=True)
class WcbData:
    """Per-dataset building blocks of the wild bootstrap for one target.

    ``alpha_u[r, g] = h_g' u_g`` and ``s_u[r, g, :] = Q_z,g' u_g`` for the unrestricted residual ``u`` of dataset
    ``r``; ``alpha_r`` and ``s_r`` are the same objects for the residualised target regressor ``r_j``. The
    restricted residual for a coefficient ``b`` is ``u + b r_j`` so every bootstrap quantity is linear in ``b``.
    """

    b0: np.ndarray
    se: np.ndarray
    alpha_u: np.ndarray
    s_u: np.ndarray
    alpha_r: np.ndarray
    s_r: np.ndarray


def _cluster_cross(design: Design, left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """Per-cluster ``left_g' right_g`` for (N x k) ``left`` and (N x B) ``right``: array (B, G, k)."""
    out = np.empty((right.shape[1], design.n_clusters, left.shape[1]))
    for g, (a, c) in enumerate(zip(design.starts, design.starts + design.counts)):
        out[:, g, :] = (left[a:c].T @ right[a:c]).T
    return out


def wcb_prepare(design: Design, y: np.ndarray) -> dict[str, WcbData]:
    """Compute :class:`WcbData` for every target from an (N x R) matrix of simulated outcomes."""
    u = residuals(design, y)
    s_u = _cluster_cross(design, design.q_z, u)
    out = {}
    for name in design.targets:
        h, r = design.h[name], design.r[name]
        alpha_u = np.add.reduceat(h[:, None] * u, design.starts, axis=0).T
        scores = alpha_u.T
        out[name] = WcbData(
            b0=h @ y, se=np.sqrt(design.cr1 * (scores**2).sum(axis=0)), alpha_u=alpha_u, s_u=s_u,
            alpha_r=np.add.reduceat(h * r, design.starts), s_r=np.add.reduceat(design.q_z * r[:, None], design.starts, axis=0),
        )
    return out


def wild_bootstrap_reject(design: Design, target: str, data: WcbData, beta: float, weights: str, seed_key: int,
                          n_draws: int = N_WCB_DRAWS) -> np.ndarray:
    """Wild-cluster bootstrap-t rejection indicators (null imposed) for each simulated dataset.

    The dataset is outcome ``= noise + beta * x_j``, so the coefficient is ``b = b0 + beta`` and the standard error
    is unchanged. With ``v`` the cluster weights, the bootstrap outcome is ``y* = fit_restricted + v * u~`` and
    (i) its coefficient is ``alpha' v`` (the restricted fit is annihilated by ``h``), (ii) its cluster scores are
    ``A v`` with ``A = diag(alpha) - Gamma S'``, where ``alpha_g = h_g' u~_g`` and ``S_gk = Q_z,g,k' u~_g``. The
    p-value is ``(1 + #{|t*| >= |t|}) / (n_draws + 1)``; reject at ``p <= ALPHA`` (``(n_draws + 1) * ALPHA`` is an
    integer for the default so the test has exact size under symmetry). Weights are redrawn per chunk from a
    stream seeded by ``seed_key`` so repeated calls at different ``beta`` use common random numbers.
    """
    b = data.b0 + beta
    t_obs = np.abs(b / data.se)
    alpha = data.alpha_u + b[:, None] * data.alpha_r[None, :]
    s = data.s_u + b[:, None, None] * data.s_r[None, :, :]
    gamma = design.gamma[target]
    n_data, g = len(b), design.n_clusters
    reject = np.empty(n_data, dtype=bool)
    for chunk, first in enumerate(range(0, n_data, WCB_CHUNK)):
        sl = slice(first, min(first + WCB_CHUNK, n_data))
        v = bootstrap_weights(make_rng(PURPOSE_WCB_WEIGHTS, seed_key, chunk), (sl.stop - sl.start, g, n_draws), weights)
        a_mat = -np.einsum("gk,chk->cgh", gamma, s[sl])
        idx = np.arange(g)
        a_mat[:, idx, idx] += alpha[sl]
        a_star = a_mat @ v
        t_star = np.abs(np.einsum("cg,cgb->cb", alpha[sl], v) / np.sqrt(design.cr1 * (a_star**2).sum(axis=1)))
        exceed = (t_star >= t_obs[sl, None]).sum(axis=1)
        reject[sl] = (1 + exceed) / (n_draws + 1) <= ALPHA
    return reject


def wild_bootstrap_mde(design: Design, target: str, data: WcbData, start: float, seed_key: int,
                       weights: str = "rademacher", tol: float = 2e-3) -> tuple[float, float]:
    """Effect at which the wild-bootstrap rejection rate reaches ``TARGET_POWER`` (bisection, common random numbers).

    Unlike CR1, the bootstrap critical value depends on the true effect (the restricted residuals contain it), so
    power is evaluated by direct simulation at each trial ``beta``. Returns ``(mde, rejection rate at mde)``.
    """
    def rate(beta: float) -> float:
        return float(wild_bootstrap_reject(design, target, data, beta, weights, seed_key).mean())

    hi = max(start, tol)
    while rate(hi) < TARGET_POWER:
        hi *= 1.5
    lo = 0.0
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        if rate(mid) >= TARGET_POWER:
            hi = mid
        else:
            lo = mid
    return hi, rate(hi)


# ---------------------------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------------------------
RHO_HIGH = 0.8  # high-persistence planning value used in Appendix D
SCENARIO_NAMES = ("ar1_rho0", "ar1_rho_hat", "ar1_rho0.8", "block_bootstrap")
N_VERIFY = 10_000  # fresh draws for the direct-simulation check of the MDE


BLOCK_RHO_SHARE = 0.90  # the block bootstrap must preserve at least this share of the observed lag-1 autocorrelation
BLOCK_SIM = 300  # draws used to choose the block length
MIN_BLOCK = 2


def block_length_rate(n_years: int) -> int:
    """Textbook rate ``ceil(T^(1/3))`` (Hall, Horowitz and Jing 1995): 3 for T = 27; too short for rho near 0.6."""
    return int(np.ceil(n_years ** (1 / 3)))


def choose_block_length(design: Design, cal: Calibration, share: float = BLOCK_RHO_SHARE) -> int:
    """Smallest block length that keeps ``share`` of the serial dependence the longest admissible block keeps.

    Block joins break one serial link per block, and the resampled residuals are projected on the fixed effects a
    second time (they were already projected once to obtain them), which lowers the AR(1) estimate again. The
    estimate therefore rises with the block length but saturates well below the observed value. The rule
    compares the country-standardised pooled AR(1) estimate (same estimator as in the calibration) of the
    projected draws for each block with the value at the longest admissible block ``T // 2`` and takes the
    smallest block reaching ``share`` of it. Residuals only; the result is 6 years on the final sample.
    """
    longest = design.n_grid_years // 2

    def mean_rho(block: int) -> float:
        draws = BlockBootstrapNoise(design, cal.grid, block).draw(make_rng(PURPOSE_CALIB, 1), BLOCK_SIM)
        return float(_pair_ar1(residuals(design, draws), design).mean())

    target = share * mean_rho(longest)
    for block in range(MIN_BLOCK, longest):
        if mean_rho(block) >= target:
            return block
    return longest


def make_scenarios(design: Design, cal: Calibration, block: int | None = None) -> dict[str, "ArNoise | BlockBootstrapNoise"]:
    """The four noise scenarios: AR(1) at rho in {0, corrected estimate, 0.8} with country SDs, and the block bootstrap."""
    block = block or choose_block_length(design, cal)
    return {
        "ar1_rho0": ArNoise(design, cal.sigma, 0.0),
        "ar1_rho_hat": ArNoise(design, cal.sigma, cal.rho_corrected),
        "ar1_rho0.8": ArNoise(design, cal.sigma, RHO_HIGH),
        "block_bootstrap": BlockBootstrapNoise(design, cal.grid, block),
    }


@dataclass
class ScenarioResult:
    """Everything reported for one noise scenario and one design."""

    name: str
    design_label: str
    cr1: dict[str, dict[str, float]]
    verified_power: dict[str, float]
    wcb: dict[str, dict[str, float]]
    mean_rho_in_draws: float


def verify_power(design: Design, noise: "ArNoise | BlockBootstrapNoise", mdes: dict[str, float], key: int,
                 n_draws: int = N_VERIFY) -> dict[str, float]:
    """Direct simulation: add ``mde * x_j`` to fresh noise and report the CR1 rejection rate (should be 0.80)."""
    out = {}
    for t, mde in mdes.items():
        x_j = design.x[:, design.x_names.index(design.targets[t])]
        rng = make_rng(key, PURPOSE_VERIFY)
        hits, done = 0, 0
        while done < n_draws:
            size = min(BATCH, n_draws - done)
            y = noise.draw(rng, size) + mde * x_j[:, None]
            b, se = estimate(design, y, [t])[t]
            hits += int(np.sum(np.abs(b / se) > design.t_crit))
            done += size
        out[t] = hits / n_draws
    return out


def run_scenario(design: Design, name: str, noise: "ArNoise | BlockBootstrapNoise", key: int,
                 n_null: int = N_NULL_DRAWS, n_wcb: int = N_WCB_DATASETS, with_wcb: bool = True) -> ScenarioResult:
    """CR1 null draws, MDEs, direct verification and (optionally) the wild-bootstrap size and MDE for one scenario."""
    draws = null_draws(design, noise, n_null, make_rng(key, PURPOSE_NULL))
    cr1 = summarise_cr1(draws, design)
    verified = verify_power(design, noise, {t: v["mde_cr1"] for t, v in cr1.items()}, key)
    probe = noise.draw(make_rng(key, PURPOSE_NULL, 99), 500)
    mean_rho = float(_pair_ar1(residuals(design, probe), design).mean())
    wcb: dict[str, dict[str, float]] = {}
    if with_wcb:
        datasets = wcb_prepare(design, noise.draw(make_rng(key, PURPOSE_WCB), n_wcb))
        for t, data in datasets.items():
            seed_key = key * 100 + list(design.targets).index(t)
            size_rad = wild_bootstrap_reject(design, t, data, 0.0, "rademacher", seed_key).mean()
            size_webb = wild_bootstrap_reject(design, t, data, 0.0, "webb", seed_key).mean()
            mde, rate = wild_bootstrap_mde(design, t, data, cr1[t]["mde_cr1"], seed_key)
            at_cr1 = wild_bootstrap_reject(design, t, data, cr1[t]["mde_cr1"], "rademacher", seed_key).mean()
            wcb[t] = {
                "n_datasets": float(n_wcb), "size_cr1": float(np.mean(np.abs(data.b0 / data.se) > design.t_crit)),
                "size_wcb_rademacher": float(size_rad), "size_wcb_webb": float(size_webb), "mde_wcb": mde,
                "power_wcb_at_mde": rate, "power_wcb_at_cr1_mde": float(at_cr1),
            }
    return ScenarioResult(name, design.label, cr1, verified, wcb, mean_rho)


def run_all_scenarios(design: Design, cal: Calibration, with_wcb: bool = True, names: tuple[str, ...] = SCENARIO_NAMES,
                      n_null: int = N_NULL_DRAWS, n_wcb: int = N_WCB_DATASETS, block: int | None = None) -> dict[str, ScenarioResult]:
    """Run the requested scenarios (seed key = position in ``SCENARIO_NAMES``)."""
    scenarios = make_scenarios(design, cal, block)
    return {n: run_scenario(design, n, scenarios[n], SCENARIO_NAMES.index(n), n_null, n_wcb, with_wcb) for n in names}


# ---------------------------------------------------------------------------------------------
# Samples and sensitivity variants
# ---------------------------------------------------------------------------------------------
IE_CODE, IE_YEAR = "IE", 2010  # single large residual (bank recapitalisation, CAPB = -27.6 pp)


def load_samples() -> dict[str, pd.DataFrame]:
    """Final sample (Gate 3a), the ETAD-trusted 2022 extension, the balanced-22 subset and the Ireland-2010 drop."""
    panel = sample.build_panel()
    final = sample.select_sample(panel, sample.last_common_complete_year(panel, "cv"), "joint_cv").sample
    extension = sample.select_sample(panel, sample.last_year_any_complete(panel, "etad"), "joint_etad").sample
    drop = final[~((final["eurostat_code"] == IE_CODE) & (final["year"] == IE_YEAR))]
    return {"final": final, "ext2022": extension, "balanced22": sample.balanced_subset(final), "drop_IE2010": drop}


SENSITIVITY_SCENARIOS = ("ar1_rho0", "ar1_rho_hat", "block_bootstrap")


def sensitivity_runs(samples: dict[str, pd.DataFrame], n_null: int = 10_000) -> dict[str, tuple[Design, Calibration, dict[str, ScenarioResult]]]:
    """CR1 MDEs (no bootstrap) for the sensitivity variants; each variant is re-calibrated from its own residuals."""
    runs: dict[str, tuple[Design, Calibration, dict[str, ScenarioResult]]] = {}
    specs = {
        "final (reference)": (samples["final"], "m1", False, None),
        "drop Ireland 2010": (samples["drop_IE2010"], "m1", False, None),
        "winsorise residuals 1/99": (samples["final"], "m1", True, None),
        "2022 extension (N=737)": (samples["ext2022"], "m1", False, None),
        "balanced-22 (N=594)": (samples["balanced22"], "m1", False, None),
        "M1 + W_S x period terms (beta_S = pre-2008)": (samples["final"], "m1_period", False, None),
        "M1 + W_S x period terms, centred (beta_S = average)": (samples["final"], "m1_period_centered", False, None),
        "block length 3 (T^(1/3) rate)": (samples["final"], "m1", False, 3),
        "block length 12": (samples["final"], "m1", False, 12),
    }
    for label, (frame, spec, wins, block) in specs.items():
        design = build_design(frame, spec, label)
        cal = calibrate(design, winsorised=wins)
        runs[label] = (design, cal, run_all_scenarios(design, cal, with_wcb=False, names=SENSITIVITY_SCENARIOS, n_null=n_null, block=block))
    return runs


# ---------------------------------------------------------------------------------------------
# Validation against the Appendix D placeholder probe
# ---------------------------------------------------------------------------------------------
APPENDIX_D_SIGMA = 2.368  # observed two-way residual SD used by the placeholder probe (Appendix D, section 2)
APPENDIX_D_RHOS = (0.0, 0.61, 0.8)
PLACEHOLDER_CYCLE = 4  # strict four-year spacing, random phase per country (Appendix D)
APPENDIX_D_MDE = {0.0: 0.59, 0.61: 0.37, 0.8: 0.27}  # election-year dummy, pp potential GDP


def placeholder_replication(frame: pd.DataFrame, n_calendars: int = 150, draws_per_calendar: int = 40) -> dict[float, float]:
    """Re-run the Appendix D election-year-dummy design with this machinery (validation of the engine).

    Random strict four-year calendars with a random phase per country, homogeneous AR(1) noise with SD 2.368, CR1
    with t(G-1); draws pooled over calendars (a fresh calendar per block of ``draws_per_calendar`` draws), as in
    the probe. Returns the 80 per cent MDE per rho. The sample is the final sample (the probe used 1995-2023).
    """
    results = {}
    fr = frame.sort_values(["eurostat_code", "year"]).reset_index(drop=True)
    country_no = pd.factorize(fr["eurostat_code"])[0]
    for rho in APPENDIX_D_RHOS:
        rng = make_rng(90, int(rho * 100))
        b_all, se_all = [], []
        for _ in range(n_calendars):
            phase = rng.integers(0, PLACEHOLDER_CYCLE, size=int(country_no.max()) + 1)
            election = ((fr["year"].to_numpy() - phase[country_no]) % PLACEHOLDER_CYCLE == 0).astype(float)
            design = build_design(fr, label="placeholder", regressors=pd.DataFrame({"E": election}), targets={"election_dummy": "E"})
            noise = ArNoise(design, np.full(design.n_clusters, APPENDIX_D_SIGMA), rho)
            b, se = estimate(design, noise.draw(rng, draws_per_calendar))["election_dummy"]
            b_all.append(b)
            se_all.append(se)
        results[rho] = solve_mde(np.concatenate(b_all), np.concatenate(se_all), design.t_crit)
    return results


# ---------------------------------------------------------------------------------------------
# Stretch: exploratory fiscal-rule interaction in the restricted 2016-2021 window (placeholder moderator)
# ---------------------------------------------------------------------------------------------
RULE_WINDOW_START = 2016  # restricted window of the Gate 2 audit (2016-2023), truncated at the Gate 3 end year 2021
RULE_TWO_WAY_SD_Z = 0.214  # audited two-way SD of the standardised index in 2016-2023 (Gate 2 audit, section 8)
RULE_TOTAL_SD_Z = 0.612  # audited total SD of the standardised index, 2016-2023 (same table)
RULE_BETWEEN_SD_Z = 0.565  # sqrt(total SD 0.612^2 - within SD 0.235^2), same table
RULE_CHANGES_BY_YEAR = {2016: 7, 2017: 8, 2018: 5, 2019: 5, 2020: 7}  # audit counts of year-on-year changes (moderator enters lagged)
RULE_COUNTRIES_WITH_CHANGE = 22  # countries with at least one change (audit)
RULE_SHARE_INCREASES = 140 / (140 + 39)  # increases among changes, full window (audit)
N_PLACEHOLDERS = 30  # random placements of the placeholder changes


def placeholder_rule_moderator(frame: pd.DataFrame, rng: np.random.Generator) -> tuple[np.ndarray, float]:
    """One placeholder realisation of the lagged fiscal-rule moderator ``F_{i,t-1}`` on a 2016-2021 frame.

    Returns ``(F, two_way_sd)``. The path is a country level (SD ``RULE_BETWEEN_SD_Z``) plus step changes:
    ``RULE_CHANGES_BY_YEAR`` changes (a change dated ``s`` shows in the lagged moderator from row ``s+1``), spread
    over ``RULE_COUNTRIES_WITH_CHANGE`` countries (each has at least one, at most one per year), signs with the
    audit's share of increases, magnitudes |N(0,1)|; the step part is scaled so that the two-way-demeaned SD of
    the moderator on the window sample equals ``RULE_TWO_WAY_SD_Z``. The values are placeholders, not workbook data.
    """
    codes = np.sort(frame["eurostat_code"].unique())
    years = sorted(RULE_CHANGES_BY_YEAR)
    n_changes = sum(RULE_CHANGES_BY_YEAR.values())
    touched = rng.choice(len(codes), size=RULE_COUNTRIES_WITH_CHANGE, replace=False)
    year_left = dict(RULE_CHANGES_BY_YEAR)
    chosen: list[tuple[int, int]] = []
    for c in rng.permutation(touched):  # one guaranteed change per touched country
        options = [y for y in years if year_left[y] > 0]
        y = int(rng.choice(options))
        chosen.append((int(c), y))
        year_left[y] -= 1
    while len(chosen) < n_changes:
        candidates = [(int(c), y) for c in touched for y in years if year_left[y] > 0 and (int(c), y) not in chosen]
        c, y = candidates[int(rng.integers(len(candidates)))]
        chosen.append((c, y))
        year_left[y] -= 1
    steps = np.abs(rng.standard_normal(n_changes)) * np.where(rng.random(n_changes) < RULE_SHARE_INCREASES, 1.0, -1.0)
    row_code = pd.Series(frame["eurostat_code"]).map({c: i for i, c in enumerate(codes)}).to_numpy()
    row_year = frame["year"].to_numpy()
    path = np.zeros(len(frame))
    for (c, y), step in zip(chosen, steps):
        path += step * ((row_code == c) & (row_year >= y + 1))
    path *= RULE_TWO_WAY_SD_Z / float(sample._two_way_residuals(frame.assign(_f=path), "_f").std())
    moderator = path + rng.standard_normal(len(codes))[row_code] * RULE_BETWEEN_SD_Z
    return moderator, float(sample._two_way_residuals(frame.assign(_f=moderator), "_f").std())


def fiscal_rule_mde(final_frame: pd.DataFrame, cal: Calibration, n_null: int = 10_000) -> pd.DataFrame:
    """Indicative CR1 MDE of the exploratory ``W_S x F`` interaction in 2016-2021 over random placeholder placements.

    Model: country and year effects, ``W_S, W_E, W_U, Post``, the moderator ``F`` (lagged) and ``W_S x F``; target =
    the interaction coefficient, per +1 z of ``F`` and per +1 two-way SD (0.214 z). Noise: AR(1) with the Gate 3b
    country SDs and rho in {0, corrected estimate}. Returned: one row per placeholder x rho.
    """
    window = final_frame[final_frame["year"] >= RULE_WINDOW_START].sort_values(["eurostat_code", "year"]).reset_index(drop=True)
    rows = []
    for i in range(N_PLACEHOLDERS):
        moderator, two_way_sd = placeholder_rule_moderator(window, make_rng(80, i))
        regs = pd.DataFrame({
            "W_S": window["W_S"], "W_E": window["W_E"], "W_U": window["W_U"], "Post": window["Post"],
            "F": moderator, "WS_x_F": window["W_S"].to_numpy() * moderator,
        })
        design = build_design(window, label="fiscal-rule placeholder", regressors=regs, targets={"gamma_F": "WS_x_F"})
        for rho_label, rho in (("rho0", 0.0), ("rho_hat", cal.rho_corrected)):
            draws = null_draws(design, ArNoise(design, cal.sigma, rho), n_null, make_rng(81, i, int(rho * 1000)))
            summary = summarise_cr1(draws, design)["gamma_F"]
            rows.append({"placeholder": i, "rho": rho_label, "two_way_sd_z": two_way_sd, "n_obs": design.n_obs,
                         "mde_cr1_per_z": summary["mde_cr1"], "mde_cr1_per_total_sd": summary["mde_cr1"] * RULE_TOTAL_SD_Z,
                         "mde_cr1_per_two_way_sd": summary["mde_cr1"] * RULE_TWO_WAY_SD_Z,
                         "size_cr1": summary["size_cr1"]})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------------------------
# Literature benchmarks (indicative: outcomes differ from CAPB)
# ---------------------------------------------------------------------------------------------
LITERATURE_EFFECTS = {
    "Bednar 2019: structural balance, year before election (pp, abstract-level)": 0.41,
    "Afonso et al. 2026: primary expenditure, 12-month window (pp, full text)": 0.49,
}


def literature_power(design: Design, cal: Calibration, block: int, n_draws: int = N_NULL_DRAWS) -> pd.DataFrame:
    """CR1 power of ``beta_S`` against literature-sized effects in each noise scenario (same draws as the main run)."""
    rows = []
    scenarios = make_scenarios(design, cal, block)
    for key, name in enumerate(SCENARIO_NAMES):
        draws = null_draws(design, scenarios[name], n_draws, make_rng(key, PURPOSE_NULL))
        row: dict[str, object] = {"scenario": name}
        for label, effect in LITERATURE_EFFECTS.items():
            row[f"power at {effect:.2f} pp"] = power_at(draws.b0["beta_S"], draws.se["beta_S"], design.t_crit, effect)
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------------------------
# Gate verdicts and reporting
# ---------------------------------------------------------------------------------------------
G2_ELECTION_GO_RHO_HAT = 0.50  # Appendix D, G2: election term, at the estimated autocorrelation (pp)
G2_ELECTION_GO_RHO0 = 0.75  # at rho = 0
G2_NOGO = 1.00  # NO-GO above 1.0 pp
G2_INTERACTION_GO = 0.75  # interaction per +1 SD (the NO-GO line is extended from the election term, an assumption)


def gate_verdict(target: str, mde_rho_hat: float, mde_rho0: float) -> str:
    """GO / AMBER / NO-GO under the Appendix D G2 thresholds (see module constants)."""
    go_hat = G2_ELECTION_GO_RHO_HAT if target.startswith("beta") else G2_INTERACTION_GO
    go_zero = G2_ELECTION_GO_RHO0 if target.startswith("beta") else G2_INTERACTION_GO
    if max(mde_rho_hat, mde_rho0) > G2_NOGO:
        return "NO-GO"
    if mde_rho_hat <= go_hat and mde_rho0 <= go_zero:
        return "GO"
    return "AMBER"


def md_table(frame: pd.DataFrame, floatfmt: str = ".3f") -> str:
    """Render a DataFrame as a GitHub markdown table."""
    cols = [str(c) for c in frame.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, row in frame.iterrows():
        cells = [format(v, floatfmt) if isinstance(v, (float, np.floating)) else str(v) for v in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def calibration_table(cal: Calibration, results: dict[str, ScenarioResult], block: int) -> str:
    """Markdown summary of the noise calibration."""
    h, dep = cal.heterogeneity, cal.dependence
    block_rho = results["block_bootstrap"].mean_rho_in_draws if "block_bootstrap" in results else float("nan")
    rows = [
        ("AR(1), pooled raw residuals (not standardised)", f"{cal.rho_raw_pooled:.3f}"),
        ("AR(1), country-standardised residuals (uncorrected estimate)", f"{cal.rho_raw_standardised:.3f}"),
        (f"Nickell (1981) analytic correction, T = {cal.mean_t:.1f}", f"{cal.rho_nickell_corrected:.3f}"),
        ("Simulation (indirect-inference) correction: USED as 'estimated rho'", f"{cal.rho_corrected:.3f}"),
        ("Mean AR(1) estimate in block-bootstrap draws (same estimator)", f"{block_rho:.3f}"),
        ("Country residual SD: min / median / max (pp)", f"{h['sigma_min']:.2f} / {h['sigma_median']:.2f} / {h['sigma_max']:.2f} ({h['sigma_argmax_country']})"),
        ("Max-to-median SD ratio; Levene (median) p-value", f"{h['sigma_max_to_median']:.2f}; {h['levene_p']:.1e}"),
        ("Pooled residual SD / robust (1.4826 MAD) SD (pp)", f"{h['sigma_pooled']:.2f} / {h['sigma_robust_mad']:.2f}"),
        ("Df factor sqrt(N / (N - K_all)) applied to residual SDs", f"{cal.df_factor:.3f}"),
        (f"Cross-section dependence: mean pairwise corr.; Pesaran CD ({dep['n_pairs']:.0f} pairs)", f"{dep['mean_pairwise_corr']:.3f}; {dep['pesaran_cd']:.2f}"),
        ("Block-bootstrap block length (years)", str(block)),
    ]
    return md_table(pd.DataFrame(rows, columns=["quantity", "value"]))


def main_tables(design: Design, results: dict[str, ScenarioResult]) -> tuple[str, str]:
    """Detailed per-scenario table and compact gate table for one design (CR1 and wild bootstrap)."""
    nan = float("nan")
    detail = []
    for name, res in results.items():
        for t in design.targets:
            c, w = res.cr1[t], res.wcb.get(t, {})
            detail.append({
                "scenario": name, "target": t, "CR1 size": c["size_cr1"], "WCB size (Rad.)": w.get("size_wcb_rademacher", nan),
                "WCB size (Webb)": w.get("size_wcb_webb", nan), "MDE CR1": c["mde_cr1"], "MDE CR1 size-adj.": c["mde_cr1_size_adjusted"],
                "MDE WCB": w.get("mde_wcb", nan), "analytic": c["mde_analytic"], "power at CR1 MDE (sim.)": res.verified_power[t],
                "WCB power at CR1 MDE": w.get("power_wcb_at_cr1_mde", nan), "WCB power at WCB MDE": w.get("power_wcb_at_mde", nan),
            })
    compact = []
    for t in design.targets:
        row: dict[str, object] = {"target": t}
        for name in results:
            row[f"{name} CR1"] = results[name].cr1[t]["mde_cr1"]
            row[f"{name} WCB"] = results[name].wcb.get(t, {}).get("mde_wcb", nan)
        hat, zero = results["ar1_rho_hat"], results["ar1_rho0"]

        def conservative(r: ScenarioResult, target: str = t) -> float:
            return max(r.cr1[target]["mde_cr1"], r.cr1[target]["mde_cr1_size_adjusted"], r.wcb.get(target, {}).get("mde_wcb", 0.0))

        row["G2 (CR1)"] = gate_verdict(t, hat.cr1[t]["mde_cr1"], zero.cr1[t]["mde_cr1"])
        row["G2 (conservative)"] = gate_verdict(t, conservative(hat), conservative(zero))
        compact.append(row)
    return md_table(pd.DataFrame(detail)), md_table(pd.DataFrame(compact))


def sensitivity_table(runs: dict[str, tuple[Design, Calibration, dict[str, ScenarioResult]]]) -> str:
    """Markdown table: CR1 MDE by variant x scenario x target, with rho-hat and CR1 size."""
    rows = []
    for label, (design, cal, res) in runs.items():
        for t in design.targets:
            rows.append({
                "variant": label, "N": design.n_obs, "rho_hat": cal.rho_corrected, "target": t,
                "MDE rho=0": res["ar1_rho0"].cr1[t]["mde_cr1"], "MDE rho_hat": res["ar1_rho_hat"].cr1[t]["mde_cr1"],
                "MDE block bootstrap": res["block_bootstrap"].cr1[t]["mde_cr1"], "CR1 size (rho_hat)": res["ar1_rho_hat"].cr1[t]["size_cr1"],
            })
    return md_table(pd.DataFrame(rows))


def main(argv: list[str] | None = None) -> None:
    """Print the Gate 3b markdown tables (``reports/gate3_power_update.md`` quotes this output).

    Sections: ``main`` (calibration, M1 scenarios with wild bootstrap), ``pooled``, ``sensitivity``,
    ``validation`` (Appendix D replication), ``stretch`` (fiscal-rule placeholder). Default: all.
    """
    import argparse

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("--sections", nargs="*", default=["main", "pooled", "sensitivity", "validation", "stretch", "literature"])
    args = parser.parse_args(argv)
    samples = load_samples()
    design = build_design(samples["final"])
    cal = calibrate(design)
    block = choose_block_length(design, cal)
    if "main" in args.sections:
        results = run_all_scenarios(design, cal, block=block)
        print("## Calibration\n\n" + calibration_table(cal, results, block))
        detail, compact = main_tables(design, results)
        print("\n## M1 detail\n\n" + detail + "\n\n## M1 compact\n\n" + compact, flush=True)
    if "pooled" in args.sections:
        pooled = build_design(samples["final"], "pooled", "final, pooled interaction")
        pcal = calibrate(pooled)
        detail, compact = main_tables(pooled, run_all_scenarios(pooled, pcal, block=choose_block_length(pooled, pcal)))
        print(f"\n## Pooled (rho_hat = {pcal.rho_corrected:.3f})\n\n" + detail + "\n\n" + compact, flush=True)
    if "sensitivity" in args.sections:
        print("\n## Sensitivity\n\n" + sensitivity_table(sensitivity_runs(samples)), flush=True)
    if "validation" in args.sections:
        rep = placeholder_replication(samples["final"])
        rows = [{"rho": r, "this engine (pp)": v, "Appendix D (pp)": APPENDIX_D_MDE[r]} for r, v in rep.items()]
        print("\n## Validation (election dummy, random 4-year calendars)\n\n" + md_table(pd.DataFrame(rows)), flush=True)
    if "literature" in args.sections:
        print("\n## Power against literature-sized effects (beta_S, CR1)\n\n" + md_table(literature_power(design, cal, block)), flush=True)
    if "stretch" in args.sections:
        frame = fiscal_rule_mde(samples["final"], cal)
        cols = ["n_obs", "two_way_sd_z", "mde_cr1_per_z", "mde_cr1_per_total_sd", "mde_cr1_per_two_way_sd", "size_cr1"]
        summary = frame.groupby("rho")[cols].agg(["median", "min", "max"])
        summary.columns = [f"{a} ({b})" for a, b in summary.columns]
        print("\n## Stretch: fiscal-rule placeholder\n\n" + md_table(summary.reset_index()), flush=True)


if __name__ == "__main__":
    main()
