# Gate 3b: simulation-based power for the confirmatory model on the real election calendar and final sample

Generated 2026-10-10 by `python src/evaluate/power.py` (engine `src/evaluate/power.py`, tests `tests/test_power.py`). Offline; reads the raw data only through `src/evaluate/sample.py` (read-only). Every random stream is `numpy.random.default_rng(SeedSequence([42, key, ...]))` with `SEED = 42` and a fixed integer key per scenario and purpose, so all numbers below reproduce exactly. **No effect estimate from the real CAPB panel was computed or printed**: only residuals of the full M1 fit enter the calibration, so power is calibrated without looking at the quantities it is meant to protect.

## 0. Headline

Final sample (Gate 3a rule): 1995-2021, N = 715 country-years, 27 countries (clusters). MDE = effect with 80 per cent power at alpha = 0.05, two-sided, country-clustered CR1 with t(26) (critical value 2.056), in percentage points of potential GDP. "Estimated rho" is the corrected AR(1) persistence 0.69 (section 2). Verdicts follow the Appendix D gate G2; the interaction thresholds are the G2 line "interaction per +1 SD <= 0.75 pp", with AMBER up to 1.0 pp and NO-GO above it (the 1.0 pp NO-GO line for interactions is my extension of the election-term line).

| Target | MDE, estimated rho, CR1 | MDE, rho = 0, CR1 | MDE, estimated rho, wild bootstrap | MDE, rho = 0, wild bootstrap | G2 verdict |
|---|---|---|---|---|---|
| (a) beta_S, scheduled-election term (per W_S = 1) | 0.66 | 0.94 | 0.68 | 0.99 | **AMBER** (fails 0.50 and 0.75; rho = 0 wild-bootstrap value 0.994 sits at the 1.0 NO-GO line) |
| (b) gamma_B, per +1 SD of the between component | 0.92 | 1.17 | 1.06 | 1.30 | **NO-GO** (above 1.0 at rho = 0; AMBER at estimated rho under CR1, above 1.0 under the wild bootstrap) |
| (c) gamma_W, per +1 SD of the within component | 0.87 | 0.86 | 0.87 | 0.89 | **AMBER** (above 0.75 in every scenario, below 1.0) |

Reading: the confirmatory design cannot detect an average scheduled-election effect much below 0.7 pp (0.9-1.0 pp if CAPB is serially uncorrelated), and cannot detect heterogeneity by ageing smaller than about 0.9 pp per SD. Both literature benchmarks (0.41 and 0.49 pp) fall below the MDE of (a): power against them is 25-54 per cent (0.41 pp) and 34-68 per cent (0.49 pp) across the four noise scenarios (section 6). Placeholder numbers of Appendix D (0.37 pp at observed rho, 0.59 pp at rho = 0) were optimistic for the M1 specification for three reasons made explicit below: a fractional exposure with mean 0.17 replaces a dummy with mean 0.25, country variances are heterogeneous (Ireland SD 5.6 pp), and the nuisance terms and interactions use up variation. The Appendix D engine itself is reproduced (section 7).

## 1. Specification and scaling

M1 (proposal 9.2) estimated with country and year effects:

CAPB_it = alpha_i + lambda_t + beta_S W_S + beta_E W_E + beta_U W_U + rho Post + gamma_B W_S x Abar_i + gamma_W W_S x (A_{i,t-1} - Abar_i) + eta A_{i,t-1} + e_it

* `A` = OLDDEP1 lagged one year, standardised on the 715-observation estimation sample (mean 24.38 pp, SD 4.55 pp); `Abar_i` = country mean of `A`; between SD = 0.712 z (3.24 pp), within SD = 0.703 z (3.20 pp).
* The two interaction regressors are divided by the SD of their component, so **gamma_B and gamma_W are effects per +1 SD of the between and within component** (3.24 pp and 3.20 pp of OLDDEP1). `beta_S` is the effect of a full-year pre-election exposure (`W_S = 1`) at the sample-mean moderator; it is directly comparable to the election-year dummy of Appendix D.
* `W_U` (unclassified) enters as a separate nuisance term. `W_D` (delayed) is identically zero on the final sample (the single delayed election, HR 2000-01-03, lies outside it), so the column is dropped automatically rather than estimated; it is added if a variant has variation. Covariates (lagged output gap, debt, interest-growth differential, euro membership) are not available in this offline gate: their omission is conservative (noise SD is calibrated on a model without them).
* `beta_E` and `rho` are in the model but are not targets.
* A pooled single-interaction version (`W_S x A`, A in z units) is reported in section 5 for comparability with Appendix D.

## 2. Calibration from the real CAPB panel

The full M1 was fitted on the real CAPB panel; only the residuals are used.

| quantity | value |
|---|---|
| AR(1), pooled raw residuals (not standardised) | 0.594 |
| AR(1), country-standardised residuals (uncorrected estimate) | 0.562 |
| Nickell (1981) analytic correction, T = 26.5 | 0.627 |
| **Simulation (indirect-inference) correction: used as "estimated rho"** | **0.694** |
| Country residual SD: min / median / max (pp) | 1.08 / 2.00 / 5.58 (IE) |
| Max-to-median SD ratio; Levene (median) p-value | 2.79; 4.5e-10 |
| Pooled residual SD / robust (1.4826 MAD) SD (pp) | 2.45 / 2.02 |
| Df factor sqrt(N / (N - K_all)) applied to residual SDs | 1.045 |
| Cross-section dependence: mean pairwise correlation; Pesaran CD (351 pairs) | -0.036; -3.40 |
| Block bootstrap: block length (years); mean AR(1) estimate in the draws | 6; 0.413 |

How the persistence was estimated and corrected:

1. **Estimator.** The residual of the two-way-FE M1 fit has zero mean in every country by construction. Each country's residual is divided by its own residual SD (so the weights match a generator with country variances and a common rho) and the AR(1) coefficient is the pooled `sum e_t e_{t-1} / sum e_{t-1}^2` over consecutive-year pairs (688 pairs). Result 0.562; without standardisation 0.594 (this one is pulled by Ireland's 2010 spike and rebound).
2. **Nickell-type correction, analytic.** Within-demeaning biases the AR(1) coefficient downward by the Nickell (1981) large-N expression, `-(1+rho)/(T-1)` to leading order, in closed form (`nickell_bias`); with T = 26.5 observations per country, solving `rho + bias(rho) = 0.562` gives 0.627 (bias about 0.065).
3. **Nickell-type correction, by simulation (the one used).** The residual here comes from a regression with 26 year effects and 7 regressors, so the bias exceeds the pure within-demeaning term. I find the `rho` such that the same estimator (full-M1 residual, country-standardised pooled AR(1)) applied to AR(1) noise with that `rho` and the estimated country SDs averages 0.562 over 1,000 simulated panels with the real sample geometry (common random numbers; `corrected_rho_indirect`). Result **0.694**. This is higher than the Appendix D placeholder (0.61, "demeaning biases rho down by about 0.06") because that value had neither the standardisation nor the regression-induced bias corrected. A check: the mean estimate in 500 draws at 0.694 is 0.563.
4. **Variance heterogeneity** is large and significant: country SDs range from 1.08 to 5.58 pp (Ireland), a factor of 2.8 over the median; pooled SD 2.45 pp against a robust 2.02 pp. The country SDs, inflated by the degrees-of-freedom factor 1.045 (the fit absorbed 60 parameters from 715 observations), are used as the marginal SDs of the parametric noise.
5. **Cross-country dependence.** The mean pairwise residual correlation (-0.036) equals the value two-way fixed effects force mechanically (-1/(G-1) = -0.038); the negative Pesaran CD (-3.4) is that same artefact, not positive dependence. The block bootstrap nevertheless carries whatever sample-specific co-movement exists, including low-frequency co-movement (section 3.4).

## 3. Method

### 3.1 Engine (no statsmodels or row-wise .loc inside any simulation)

* Frisch-Waugh-Lovell by matrix products. An orthonormal basis `Q_fe` of the country and year dummies is built once (QR, 53 columns); the regressors are residualised on it; with `Q_z = [Q_fe, Q_x]` any outcome matrix is residualised by `Y - Q_z (Q_z' Y)`. The coefficient of target `j` is `h_j' y` with `h_j = X~ (X~'X~)^{-1} e_j`.
* CR1 variance of `b_j`: `c * sum_g (h_jg' u_g)^2`, `u` the full-model residual, `c = G/(G-1) * (N-1)/(N-K)`, `K` = 26 year effects + 7 regressors (country effects are nested in clusters and not counted: Stata `xtreg, fe vce(cluster)` / `reghdfe` convention; Appendix D likewise counted the year effects). `c = 1.087`. Tests: coefficient and standard error equal a direct OLS with all dummies (statsmodels cluster option, rescaled for the K convention) to 1e-9 on an unbalanced panel.
* Batches of 2,000 noise columns are generated and residualised in one array operation; 20,000 null draws per scenario.

### 3.2 Exact MDE (derivation)

In a linear model with fixed noise `e`, adding a true effect `beta` of regressor `x_j` to the outcome gives `y = e + beta x_j`. The residual `u = M_Z y` annihilates every column of `Z`, which contains `x_j`, so `u` and therefore the CR1 standard error `se` do not depend on `beta`; the coefficient is `b = b0 + beta` with `b0 = h_j' e`, because `h_j' x_j = 1`. From the null draws `(b0_r, se_r)`:

power(beta) = mean_r 1{ |b0_r + beta| > t_{0.975, G-1} * se_r }.

This is monotone in `beta`; the MDE is the `beta` at which it equals 0.80, found by bisection to 1e-7 (exact for the simulated population, no normal approximation). The textbook shortcut `(t + 0.8416) * median(se)` is reported as a cross-check ("analytic"): it is within 2-15 per cent of the exact value, and lower than the exact value where the sampling distribution of `b0` has a larger spread than the median `se` suggests (gamma_B). **Verification by direct simulation:** fresh independent noise (10,000 draws) with `mde * x_j` added to the outcome and the full estimation repeated: CR1 rejection rates 0.792-0.812 (tables), i.e. 0.80 within Monte Carlo error (SE 0.004).

A third column, "CR1 size-adjusted", replaces the t critical value by the empirical 95th percentile of `|b0|/se` from the null draws; it is the MDE of a test with exact size and is what a CR1 test would need if it over-rejects.

### 3.3 Wild-cluster bootstrap-t

Null imposed (restricted residuals), 999 bootstrap draws per dataset, 2,000 simulated datasets per scenario (task minimum 300), p-value `(1 + #{|t*| >= |t|})/(B+1)` rejecting at p <= 0.05 ((B+1) alpha = 50, an integer, so the test is exact under symmetry). The residual of the restricted fit is `u + b r_j` (`r_j` = target regressor residualised on everything else), the restricted fit is annihilated by `h_j`, and so for cluster weights `v` the bootstrap coefficient is `alpha' v` and the bootstrap cluster scores are `A v` with the G x G matrix `A = diag(alpha) - Gamma S'`; this is evaluated with one small matrix product for all 999 draws of a dataset (`wild_bootstrap_reject`). Tests: identical to a brute-force bootstrap (full OLS and sandwich on every bootstrap sample) to 1e-9. Because the restricted residuals contain the true effect, the bootstrap critical value depends on `beta`; the WCB MDE is therefore found by **direct simulation** (bisection on the rejection rate over `beta`, common random numbers, tolerance 0.002 pp, Monte Carlo error of the rate about 0.009, i.e. about +-0.03 pp on the MDE).

**Weights: Rademacher (+-1) as baseline, Webb six-point as a check.** With G = 27 clusters Rademacher has 2^27 (about 1.3e8) distinct weight vectors, so the discreteness that motivates Webb (2014) (few clusters, G below about 12; MacKinnon and Webb 2017) is absent, and Rademacher is the efficient choice under symmetric residuals. Webb weights are reported for the null rejection rate in every scenario; they are indistinguishable from Rademacher (differences at most 0.003).

### 3.4 Noise scenarios

* **AR(1)** (parametric): `e_it = sigma_i nu_it`, `nu` stationary AR(1) with unit variance, independent across countries, rho in {0, 0.694 (estimated, corrected), 0.8}; `sigma_i` = country residual SDs (section 2).
* **Block bootstrap**: whole year-residual vectors (all countries of the same year together) are resampled in moving blocks of consecutive years, so cross-country dependence, heteroskedasticity and serial structure inside blocks are inherited. The 14 country-years missing in the calibration grid are filled by a draw from the same country's residuals. **Block length 6 years**: chosen by a residual-only rule (smallest block that retains 90 per cent of the serial dependence retained by the longest admissible block, T/2 = 13). The textbook rate T^(1/3) = 3 breaks too many serial links for rho near 0.6; sensitivity to 3 and 12 in section 8. Even at 6 years the draws carry an AR(1) estimate of only 0.41 (observed 0.56): block joins and the second fixed-effect projection of resampled residuals lower it. **The block-bootstrap scenario therefore sits between the rho = 0 and estimated-rho AR(1) scenarios in persistence and should be read as a robustness scenario for tails and cross-country structure, not as the persistence benchmark.**

## 4. Results for M1 (three targets, four scenarios)

All MDEs in pp of potential GDP. Sizes are rejection rates at nominal 5 per cent under the null (CR1: 20,000 draws, Monte Carlo SE 0.0015; WCB: 2,000 datasets, SE 0.005).

| scenario | target | CR1 size | WCB size (Rad.) | WCB size (Webb) | MDE CR1 | MDE CR1 size-adj. | MDE WCB | analytic | power at CR1 MDE (sim.) | WCB power at CR1 MDE | WCB power at WCB MDE |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ar1_rho0 | beta_S | 0.057 | 0.049 | 0.048 | 0.939 | 0.958 | 0.994 | 0.901 | 0.802 | 0.763 | 0.800 |
| ar1_rho0 | gamma_B | 0.086 | 0.050 | 0.053 | 1.168 | 1.296 | 1.295 | 1.014 | 0.804 | 0.741 | 0.800 |
| ar1_rho0 | gamma_W | 0.052 | 0.049 | 0.050 | 0.859 | 0.863 | 0.889 | 0.840 | 0.794 | 0.772 | 0.802 |
| ar1_rho_hat | beta_S | 0.046 | 0.047 | 0.049 | 0.664 | 0.654 | 0.679 | 0.640 | 0.799 | 0.785 | 0.800 |
| ar1_rho_hat | gamma_B | 0.069 | 0.051 | 0.054 | 0.924 | 0.982 | 1.062 | 0.784 | 0.800 | 0.742 | 0.801 |
| ar1_rho_hat | gamma_W | 0.042 | 0.048 | 0.046 | 0.872 | 0.848 | 0.874 | 0.838 | 0.797 | 0.798 | 0.800 |
| ar1_rho0.8 | beta_S | 0.044 | 0.056 | 0.056 | 0.575 | 0.566 | 0.600 | 0.548 | 0.812 | 0.762 | 0.802 |
| ar1_rho0.8 | gamma_B | 0.068 | 0.045 | 0.046 | 0.789 | 0.834 | 0.896 | 0.672 | 0.795 | 0.749 | 0.800 |
| ar1_rho0.8 | gamma_W | 0.036 | 0.045 | 0.046 | 0.887 | 0.849 | 0.887 | 0.837 | 0.798 | 0.800 | 0.800 |
| block_bootstrap | beta_S | 0.100 | 0.098 | 0.099 | 0.844 | 0.951 | 0.895 | 0.716 | 0.797 | 0.766 | 0.800 |
| block_bootstrap | gamma_B | 0.101 | 0.084 | 0.086 | 1.084 | 1.279 | 1.204 | 0.857 | 0.800 | 0.740 | 0.800 |
| block_bootstrap | gamma_W | 0.035 | 0.043 | 0.046 | 0.940 | 0.901 | 0.990 | 0.878 | 0.792 | 0.768 | 0.800 |

Compact view with the G2 verdicts. "(CR1)" applies the gate to the CR1 MDEs as defined in Appendix D; "(conservative)" applies it to the largest of the CR1, size-adjusted and wild-bootstrap MDEs in each scenario.

| target | ar1_rho0 CR1 | ar1_rho0 WCB | ar1_rho_hat CR1 | ar1_rho_hat WCB | ar1_rho0.8 CR1 | ar1_rho0.8 WCB | block_bootstrap CR1 | block_bootstrap WCB | G2 (CR1) | G2 (conservative) |
|---|---|---|---|---|---|---|---|---|---|---|
| beta_S | 0.939 | 0.994 | 0.664 | 0.679 | 0.575 | 0.600 | 0.844 | 0.895 | AMBER | AMBER |
| gamma_B | 1.168 | 1.295 | 0.924 | 1.062 | 0.789 | 0.896 | 1.084 | 1.204 | NO-GO | NO-GO |
| gamma_W | 0.859 | 0.889 | 0.872 | 0.874 | 0.887 | 0.887 | 0.940 | 0.990 | AMBER | AMBER |

### 4.1 Size distortion of CR1 (27 clusters)

* **beta_S and gamma_W: CR1 is close to nominal in the AR(1) scenarios** (beta_S 0.057 / 0.046 / 0.044, gamma_W 0.052 / 0.042 / 0.036 at rho = 0 / 0.69 / 0.8). It is conservative for gamma_W at high rho.
* **gamma_B: CR1 over-rejects, 6.8-8.6 per cent** at nominal 5 per cent in all AR(1) scenarios and 10.1 per cent under the block bootstrap. The between interaction is effectively a cross-sectional regressor (identified from 27 country means), the textbook few-cluster case. The wild bootstrap repairs it (4.5-5.1 per cent in the AR(1) scenarios); its MDE is correspondingly larger than the CR1 MDE (1.06 against 0.92 at the estimated rho, 1.30 against 1.17 at rho = 0). The CR1 MDE for gamma_B is anti-conservative; use the wild-bootstrap or size-adjusted figure.
* **Block bootstrap: both CR1 and the wild bootstrap over-reject for beta_S (10.0 and 9.8 per cent) and gamma_B (10.1 and 8.4 per cent)**, while the AR(1) scenarios do not. The block-bootstrap data-generating process treats the sample's own low-frequency cross-country co-movement and Ireland's 2010 spike as population features; neither a country-cluster variance nor a country-cluster bootstrap captures dependence across countries. Where this scenario is relevant the size-adjusted MDE (0.95 for beta_S, 1.28 for gamma_B) is the valid one. Driscoll-Kraay and CCE (proposal 9.2) are the intended sensitivity checks for this.
* The wild bootstrap with Rademacher and Webb weights has null rejection 4.5-5.6 per cent across all AR(1) scenarios and targets (inside the 4.0-6.0 per cent band expected from 2,000 datasets).

## 5. Pooled single-interaction version (comparability with Appendix D)

Same engine and calibration, model with `W_S`, `W_E`, `W_U`, `Post`, `W_S x A` (A in z units), main effect of `A`; target `gamma_pooled` is per +1 SD of the moderator (4.55 pp of OLDDEP1), `beta_S` is at the mean moderator.

| scenario | target | CR1 size | WCB size (Rad.) | WCB size (Webb) | MDE CR1 | MDE CR1 size-adj. | MDE WCB | analytic | power at CR1 MDE (sim.) | WCB power at CR1 MDE | WCB power at WCB MDE |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ar1_rho0 | beta_S | 0.054 | 0.047 | 0.049 | 0.949 | 0.963 | 0.994 | 0.912 | 0.803 | 0.768 | 0.801 |
| ar1_rho0 | gamma_pooled | 0.056 | 0.051 | 0.052 | 1.030 | 1.045 | 1.063 | 0.968 | 0.802 | 0.779 | 0.800 |
| ar1_rho_hat | beta_S | 0.044 | 0.047 | 0.046 | 0.669 | 0.654 | 0.678 | 0.645 | 0.800 | 0.793 | 0.800 |
| ar1_rho_hat | gamma_pooled | 0.043 | 0.051 | 0.051 | 0.920 | 0.899 | 0.932 | 0.873 | 0.801 | 0.792 | 0.800 |
| ar1_rho0.8 | beta_S | 0.041 | 0.051 | 0.052 | 0.583 | 0.567 | 0.599 | 0.556 | 0.810 | 0.778 | 0.800 |
| ar1_rho0.8 | gamma_pooled | 0.040 | 0.043 | 0.043 | 0.882 | 0.854 | 0.897 | 0.832 | 0.800 | 0.793 | 0.800 |
| block_bootstrap | beta_S | 0.083 | 0.084 | 0.085 | 0.847 | 0.920 | 0.881 | 0.731 | 0.801 | 0.773 | 0.800 |
| block_bootstrap | gamma_pooled | 0.042 | 0.043 | 0.044 | 1.064 | 1.037 | 1.086 | 0.958 | 0.802 | 0.787 | 0.800 |

| target | ar1_rho0 CR1 | ar1_rho0 WCB | ar1_rho_hat CR1 | ar1_rho_hat WCB | ar1_rho0.8 CR1 | ar1_rho0.8 WCB | block_bootstrap CR1 | block_bootstrap WCB | G2 (CR1) | G2 (conservative) |
|---|---|---|---|---|---|---|---|---|---|---|
| beta_S | 0.949 | 0.994 | 0.669 | 0.678 | 0.583 | 0.599 | 0.847 | 0.881 | AMBER | AMBER |
| gamma_pooled | 1.030 | 1.063 | 0.920 | 0.932 | 0.882 | 0.897 | 1.064 | 1.086 | NO-GO | NO-GO |

Reading and comparison with the placeholder numbers (Appendix D: election-year dummy 0.37 pp at the observed rho 0.61 and 0.59 pp at rho = 0 with random strict four-year calendars; interaction per +1 SD 0.38 / 0.58 pp). The pooled calibration gives rho = 0.70. `beta_S` is 0.67 pp (estimated rho) and 0.95 pp (rho = 0) under CR1, 0.68 / 0.99 under the wild bootstrap, practically the same as in the split model; the pooled interaction per +1 SD of the moderator needs 0.92 / 1.03 pp (CR1) and 0.93 / 1.06 pp (wild bootstrap), about 2.4 times and 1.8 times the placeholder values. The pooled interaction is well-behaved in size (CR1 4.0-5.6 per cent in the AR(1) scenarios), unlike the between component of M1, because it mixes the 27-unit cross-section with the within variation. Its gate verdict is NO-GO at the 1.0 pp line at rho = 0 (1.03 CR1, 1.06 wild bootstrap) and AMBER at the estimated rho (0.92-0.93): the same conclusion as for gamma_B.

## 6. Gate verdicts and what the MDEs can and cannot detect

**G2 (election term beta_S): AMBER.** MDE 0.66 pp at the estimated rho (gate: <= 0.50) and 0.94 pp at rho = 0 (gate: <= 0.75); both fail the GO line, neither exceeds the 1.0 pp NO-GO line under CR1. The conservative figure at rho = 0 is 0.994 pp (wild bootstrap), 0.006 pp below NO-GO: treat the verdict as AMBER-borderline. Sensitivity: with the proposal's `W_S x period` terms uncentred, `beta_S` is the pre-2008 effect and its MDE is 1.78 / 1.91 pp (NO-GO); centring the period terms restores 0.67 / 0.93 pp (section 8).

**Interaction (b), gamma_B: NO-GO** under the stated rule (1.17 pp at rho = 0 under CR1, 1.30 under the wild bootstrap; 0.92 / 1.06 at the estimated rho). It would be AMBER on the CR1 estimated-rho figure alone, but CR1 over-rejects for this target.

**Interaction (c), gamma_W: AMBER** (0.86-0.89 pp in every AR(1) scenario; 0.94-0.99 under the block bootstrap). The within interaction is not helped by persistence: the lagged-ageing within component is a low-frequency regressor (mostly the common trend that the year effects remove, two-way SD 1.25 pp), so its MDE does not fall with rho. With the proposal's period terms included it rises to 1.59-1.60 pp (NO-GO).

Consequences for the design (decision-relevant, not changes made):

1. The scheduled-election term is the only target near the GO region, and only if CAPB is persistent. Treat it as estimable to a confidence interval of roughly +-0.7 pp (+-0.9-1.0 pp at rho = 0), not as a precise test.
2. Both ageing interactions are better described as "estimated with a wide interval" than as tests: an effect would have to exceed roughly 0.9-1.3 pp per SD (3.2 pp of OLDDEP1) to be detected with 80 per cent power, which is larger than the average election effects in the literature.
3. The confirmatory design should set the period terms so that `beta_S` stays an average effect (centred), and accept that `gamma_W` then needs about 1.6 pp, or drop the period terms from the within interaction and report `gamma_W` as trend-confounded.

**What the MDEs can and cannot detect (indicative: outcomes differ).** Bednar (2019, system GMM, EU-28, 1995-2016): structural balance about 0.41 pp lower in the year before elections (abstract-level, Appendix A row B8). Afonso, Alves and Leal (2026, quarterly TWFE, 27 EU states, 2000-2024): elections associated with about 0.49 pp higher primary expenditure in the baseline (full-text read, Appendix A section 0.2); CAPB is only descriptive there (election-year mean change -0.29 against +0.07 outside, difference -0.36). These outcomes (CAPB, structural balance, primary expenditure, changes) are not the same variable as the level of AMECO CAPB: the comparison is indicative.

Power of the CR1 test for beta_S against effects of those sizes (same null draws as section 4; indicative):

| scenario | power at 0.41 pp | power at 0.49 pp |
|---|---|---|
| ar1_rho0 | 0.253 | 0.335 |
| ar1_rho_hat | 0.427 | 0.556 |
| ar1_rho0.8 | 0.535 | 0.680 |
| block_bootstrap | 0.368 | 0.462 |

* A scheduled-election effect of the size reported by Bednar (0.41) or Afonso et al. (0.49) is **below** the MDE in every scenario: CR1 power is 25-43 per cent (0.41) and 34-56 per cent (0.49) at rho = 0 and at the estimated rho, 54 and 68 per cent only at rho = 0.8. The design can detect effects of roughly 0.7 pp and above if CAPB is persistent as estimated, 0.9-1.0 pp if not.
* A null result on `beta_S` would therefore not reject effects of the literature's size; it would rule out effects above roughly 0.7-1.0 pp.
* Neither ageing interaction could detect a moderation effect equal in size to the main election effects reported in the literature.

## 7. Validation of the engine against Appendix D

Re-running the Appendix D election-year-dummy design with this engine (random strict four-year calendars, a fresh calendar per 40 draws over 150 calendars, homogeneous AR(1) with SD 2.368, CR1 with t(26), final sample):

| rho | this engine (pp) | Appendix D probe (pp) |
|---|---|---|
| 0.00 | 0.613 | 0.590 |
| 0.61 | 0.389 | 0.370 |
| 0.80 | 0.283 | 0.270 |

Agreement within 5 per cent (different sample: 715 against 770 cells, and the K convention). The step from 0.37-0.59 pp (placeholder dummy) to 0.66-0.94 pp (M1, fractional exposure) is therefore caused by the specification and noise structure, not by the engine.

## 8. Sensitivity of the MDE (CR1, 10,000 null draws, each variant re-calibrated from its own residuals)

| variant | N | rho_hat | target | MDE rho=0 | MDE rho_hat | MDE block bootstrap | CR1 size (rho_hat) |
|---|---|---|---|---|---|---|---|
| final (reference) | 715 | 0.694 | beta_S | 0.929 | 0.665 | 0.843 | 0.045 |
| final (reference) | 715 | 0.694 | gamma_B | 1.175 | 0.922 | 1.096 | 0.068 |
| final (reference) | 715 | 0.694 | gamma_W | 0.863 | 0.870 | 0.938 | 0.041 |
| drop Ireland 2010 | 714 | 0.698 | beta_S | 0.861 | 0.601 | 0.746 | 0.049 |
| drop Ireland 2010 | 714 | 0.698 | gamma_B | 0.948 | 0.703 | 0.827 | 0.077 |
| drop Ireland 2010 | 714 | 0.698 | gamma_W | 0.844 | 0.843 | 0.912 | 0.042 |
| winsorise residuals 1/99 | 715 | 0.714 | beta_S | 0.844 | 0.581 | 0.739 | 0.049 |
| winsorise residuals 1/99 | 715 | 0.714 | gamma_B | 0.956 | 0.705 | 0.858 | 0.075 |
| winsorise residuals 1/99 | 715 | 0.714 | gamma_W | 0.816 | 0.811 | 0.877 | 0.041 |
| 2022 extension (N=737) | 737 | 0.698 | beta_S | 0.919 | 0.657 | 0.826 | 0.048 |
| 2022 extension (N=737) | 737 | 0.698 | gamma_B | 1.164 | 0.913 | 0.991 | 0.076 |
| 2022 extension (N=737) | 737 | 0.698 | gamma_W | 0.851 | 0.858 | 0.888 | 0.046 |
| balanced-22 (N=594) | 594 | 0.726 | beta_S | 1.017 | 0.699 | 0.903 | 0.042 |
| balanced-22 (N=594) | 594 | 0.726 | gamma_B | 1.248 | 0.989 | 1.212 | 0.074 |
| balanced-22 (N=594) | 594 | 0.726 | gamma_W | 0.977 | 1.018 | 1.009 | 0.037 |
| M1 + W_S x period terms (beta_S = pre-2008) | 715 | 0.696 | beta_S | 1.910 | 1.778 | 2.056 | 0.042 |
| M1 + W_S x period terms (beta_S = pre-2008) | 715 | 0.696 | gamma_B | 1.175 | 0.917 | 1.093 | 0.069 |
| M1 + W_S x period terms (beta_S = pre-2008) | 715 | 0.696 | gamma_W | 1.604 | 1.587 | 1.736 | 0.043 |
| M1 + W_S x period terms, centred (beta_S = average) | 715 | 0.696 | beta_S | 0.929 | 0.666 | 0.838 | 0.044 |
| M1 + W_S x period terms, centred (beta_S = average) | 715 | 0.696 | gamma_B | 1.175 | 0.917 | 1.093 | 0.069 |
| M1 + W_S x period terms, centred (beta_S = average) | 715 | 0.696 | gamma_W | 1.604 | 1.587 | 1.736 | 0.043 |
| block length 3 (T^(1/3) rate) | 715 | 0.694 | beta_S | 0.929 | 0.665 | 0.874 | 0.045 |
| block length 3 (T^(1/3) rate) | 715 | 0.694 | gamma_B | 1.175 | 0.922 | 1.057 | 0.068 |
| block length 3 (T^(1/3) rate) | 715 | 0.694 | gamma_W | 0.863 | 0.870 | 0.885 | 0.041 |
| block length 12 | 715 | 0.694 | beta_S | 0.929 | 0.665 | 0.994 | 0.045 |
| block length 12 | 715 | 0.694 | gamma_B | 1.175 | 0.922 | 1.235 | 0.068 |
| block length 12 | 715 | 0.694 | gamma_W | 0.863 | 0.870 | 1.079 | 0.041 |

Highlights:

* **(1) Ireland 2010.** Dropping the single observation (CAPB -27.6 pp) lowers the beta_S MDE from 0.66 to 0.60 pp (rho_hat) and from 0.93 to 0.86 pp (rho = 0), and lowers the gamma_B MDE sharply, 0.92 to 0.70 pp and 1.18 to 0.95 pp (gamma_B is the target most exposed to a single country). Winsorising the residuals at the 1st and 99th percentiles gives the same picture (beta_S 0.58 / 0.84 pp, gamma_B 0.71 / 0.96 pp). Ireland's residual drives most of the variance heterogeneity; the verdict for beta_S is unchanged (AMBER), gamma_B moves to GO at the estimated rho and AMBER at rho = 0 (CR1 only, size caveat above).
* **(2) The 2022 extension (N = 737)** changes nothing material: beta_S 0.66 / 0.92, gamma_B 0.91 / 1.16, gamma_W 0.86 / 0.85. Adding 22 country-years from 22 countries is too little information to matter.
* **(3) Balanced-22 (N = 594)** raises the MDEs by 5-10 per cent (beta_S 0.70 / 1.02, gamma_B 0.99 / 1.25, gamma_W 1.02 / 0.98): the five dropped countries (CY, CZ, HR, SI, SK) contribute information. gamma_W slightly exceeds the NO-GO line at the estimated rho (1.02).
* **Period terms (proposal 9.2).** Uncentred, beta_S is the pre-2008 effect and its MDE is 1.78 / 1.91 pp; centred, it is 0.67 / 0.93 pp. gamma_W rises to 1.59 / 1.60 pp in both coding variants; gamma_B is unchanged.
* **Block length.** The block-bootstrap beta_S MDE is 0.87 (block 3), 0.84 (block 6, reference) and 0.99 pp (block 12); gamma_B 1.06 / 1.10 / 1.24 pp.

## 9. Stretch: exploratory fiscal-rule interaction, 2016-2021, placeholder moderator

**Labelled placeholder.** The moderator is not Fiscal Governance data. It has the audited within variation: a country level (SD 0.565 z) plus 32 step changes in 22 countries (counts per year 7, 8, 5, 5, 7 for 2016-2020, as in the Gate 2 audit; the moderator enters lagged, so changes dated 2016-2020 show in rows 2017-2021), signs with the audit's 78 per cent increases, magnitudes |N(0,1)|, scaled so that the two-way-demeaned SD on the 162-observation window sample equals 0.214 z. Model: country and year effects, `W_S`, `W_E`, `W_U`, `Post`, the moderator and `W_S x moderator`. Noise: AR(1) with the Gate 3b country SDs. 30 random placements of the changes; CR1; 10,000 null draws each.

| rho | MDE per +1 z of the index: median [min, max] (pp) | per +1 total SD (0.612 z) | per +1 two-way SD (0.214 z) | CR1 size, median |
|---|---|---|---|---|
| 0 | 2.67 [1.71, 4.04] | 1.64 [1.04, 2.47] | 0.57 [0.37, 0.86] | 0.076 |
| 0.69 | 1.83 [1.20, 2.91] | 1.12 [0.73, 1.78] | 0.39 [0.26, 0.62] | 0.073 |

Reading: with 162 observations, the interaction between scheduled-election exposure and the rule index needs about 1.1-1.6 pp per total SD of the index (0.4-0.6 pp per two-way SD) to be detected, under a CR1 test that over-rejects by 2-3 points. Per total SD this is above the 0.75 pp interaction line: promotion of S2 from exploratory to secondary is **not supported** by power. The per-two-way-SD figures look small only because 0.214 z is a short step on the index; the interaction is identified from the full moderator (including its between part), so the per-z and per-total-SD numbers are the meaningful ones.

## 10. Tests

`python -m pytest tests -q -p no:cacheprovider`: **116 passed** (97 existing tests plus the 19 new ones).

`tests/test_power.py` (19 tests, offline, about 15 s): FWL coefficient and CR1 standard error equal a direct OLS with dummies; the fast wild bootstrap equals a brute-force bootstrap; a known simulated effect is recovered and the CR1 standard error does not depend on it; null rejection near 5 per cent (CR1, 40 clusters); `solve_mde` returns 80 per cent power and matches theory; wild-bootstrap null rejection and monotone power; seeds reproduce and streams differ; AR(1) noise has the requested variance and autocorrelation; the block bootstrap keeps each year's cross-section together; Nickell bias sign, magnitude and inversion; block-length rule bounded and reproducible; gate verdict thresholds; interaction scaling; centred period terms; placeholder-moderator two-way SD; real final-sample design shape and calibration (skipped if inputs are absent).

## 11. Caveats

1. Gaussian innovations and a homogeneous AR(1) coefficient across countries; the block bootstrap relaxes both but understates persistence (0.41 against 0.56 observed).
2. CAPB is the ex-post revised AMECO series; the residual SD includes revision noise from potential-output re-estimation and the 2020-21 treatment.
3. No lagged covariates (output gap, debt, interest-growth differential, euro membership). If they reduce the residual SD, all MDEs scale down proportionally (MDE is linear in sigma).
4. The estimated rho depends on the residual specification (0.56 raw, 0.63 analytic Nickell, 0.69 by simulation). At rho = 0.56 the MDE for beta_S would lie between the figures shown at 0 and 0.69.
5. Cross-country dependence in the parametric scenarios is zero by construction; the block bootstrap shows that dependence of the sample's size would lift both CR1 and wild-bootstrap size to about 10 per cent for beta_S and gamma_B.
6. Power is for single coefficients tested one at a time at 5 per cent; no multiplicity adjustment across the three targets.
7. Literature benchmarks are indicative; outcomes and designs differ from the AMECO CAPB level used here.

## 12. Files

`src/evaluate/power.py`, `tests/test_power.py`, this report. Regenerate the tables with `python src/evaluate/power.py` (about 25 minutes; `--sections main pooled sensitivity validation stretch literature` selects parts).
