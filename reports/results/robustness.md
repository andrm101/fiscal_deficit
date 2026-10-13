# Robustness and diagnostics (docs/robustness_spec.md)

Associations only. Scheduled elections are predetermined, not exogenous. The headline remains the pre-registered V7 result; nothing below replaces it, selects among specifications or ranks them. Every specification is shown. Estimates are in pp of potential GDP (interactions per +1 SD of the component). Reading: SESOI 0.5 pp; label precedence excludes zero, then equivalent within +-SESOI, then inconclusive (as in `reports/results/m1_confirmatory.md`). 'SIGN DIFFERS' marks an estimate whose sign differs from the headline estimate.

## Headline (pre-registered V7, bootstrap-t B = 9,999, N = 715)

| target | estimate | 95% interval | p (wild bootstrap) | reading |
|---|---|---|---|---|
| beta_S | -0.379 | [-0.691, -0.069] | 0.0181 | excludes zero |
| gamma_B | 0.207 | [-0.069, 0.488] | 0.1445 | equivalent within +-sesoi |

## A. Inference sensitivities (cross-country dependence)

All rows use the M1 regressors as in the headline (centred era terms, no controls, N = 715). Rows with the same estimator differ only in the inference method. Intervals of the bootstrap rows are bootstrap-t percentile intervals as in the headline; CR1, Driscoll-Kraay and two-way rows use estimate +- t(26) x SE. As in the headline, the bootstrap p-value (null imposed) and the bootstrap-t interval (unrestricted) are different constructions, so near the margin an interval can exclude zero while p is above 0.05 (and the reverse).

| id | specification | inference | N | beta_S: est [95% interval]; p; reading | gamma_B: est [95% interval]; p; reading | gamma_W: est [95% interval] |
|---|---|---|---|---|---|---|
| A1-ols|cr1 | OLS two-way FE baseline (V0) | CR1 t(26) | 715 | -0.357 [-0.735, 0.022]; p=0.0635; inconclusive | 0.258 [-0.148, 0.664]; p=0.2035; inconclusive | -0.796 [-2.376, 0.785] |
| A1-ols|wcb | OLS two-way FE baseline (V0) | wild-cluster bootstrap-t, B=9999 | 715 | -0.357 [-0.754, 0.041]; p=0.0848; inconclusive | 0.258 [-0.159, 0.676]; p=0.2021; inconclusive | -0.796 [-2.314, 0.763] |
| A2-dk2 | Driscoll-Kraay, Bartlett kernel, m = 2 | Driscoll-Kraay (m=2), t(26) | 715 | -0.357 [-0.868, 0.154]; p=0.1634; inconclusive | 0.258 [-0.419, 0.934]; p=0.4406; inconclusive | -0.796 [-1.478, -0.114] |
| A2-dk4 | Driscoll-Kraay, Bartlett kernel, m = 4 | Driscoll-Kraay (m=4), t(26) | 715 | -0.357 [-0.912, 0.199]; p=0.1985; inconclusive | 0.258 [-0.361, 0.877]; p=0.3997; inconclusive | -0.796 [-1.352, -0.240] |
| A3-twoway | Two-way clustering (country, year), Cameron-Gelbach-Miller 2011 | two-way cluster, t(26) | 715 | -0.357 [-0.812, 0.099]; p=0.1197; inconclusive | 0.258 [-0.265, 0.781]; p=0.3201; inconclusive | -0.796 [-2.312, 0.721] |
| A4-ccelite|cr1 | OLS two-way FE + CCE-lite | CR1 t(26) | 715 | -0.192 [-0.628, 0.244]; p=0.3738; inconclusive | 0.375 [-0.093, 0.843]; p=0.1117; inconclusive | -0.571 [-2.227, 1.086] |
| A4-ccelite|wcb | OLS two-way FE + CCE-lite | wild-cluster bootstrap-t, B=9999 | 715 | -0.192 [-0.639, 0.248]; p=0.3758; inconclusive | 0.375 [-0.087, 0.826]; p=0.1136; inconclusive | -0.571 [-2.202, 1.097] |
| A5-v7ccelite|wcb | V7 + CCE-lite | wild-cluster bootstrap-t, B=9999 | 715 | -0.338 [-0.671, -0.004]; p=0.0599; excl. 0 | 0.256 [-0.058, 0.574]; p=0.1622; inconclusive | -0.304 [-1.630, 1.047] |
| A4-ccefull|cr1 | OLS two-way FE + CCE-full | CR1 t(26) | 715 | -0.526 [-1.041, -0.011]; p=0.0454; excl. 0 | 0.446 [-0.098, 0.991]; p=0.1039; inconclusive | 0.087 [-1.980, 2.154] |
| A4-ccefull|wcb | OLS two-way FE + CCE-full | wild-cluster bootstrap-t, B=9999 | 715 | -0.526 [-0.915, -0.135]; p=0.0111; excl. 0 | 0.446 [-0.001, 0.893]; p=0.0691; inconclusive | 0.087 [-1.768, 1.930] |
| A5-v7ccefull|wcb | V7 + CCE-full | wild-cluster bootstrap-t, B=9999 | 715 | -0.408 [-0.749, -0.065]; p=0.0225; excl. 0 | 0.143 [-0.296, 0.562]; p=0.5347; inconclusive | 0.489 [-1.225, 2.211] |

Notes:
* A4-ccelite|cr1: 52 added parameters, residual df 601
* A4-ccelite|wcb: 52 added parameters, residual df 601
* A5-v7ccelite|wcb: 52 added parameters, residual df 601
* A4-ccefull|cr1: 260 added parameters, residual df 393
* A4-ccefull|wcb: 260 added parameters, residual df 393
* A5-v7ccefull|wcb: 260 added parameters, residual df 393

### Driscoll-Kraay implementation and cross-check

Bartlett kernel; bandwidth m = floor(4 (T/100)^(2/9)) = 2 and a second run with m = 4. Small-sample factor c = T/(T-1) x (N-1)/(N-K) with T = 27 years, N = 715, K = 35 (the project's CR1 parameter count: year dummies plus regressors), critical values t(26). Factors: m=2: 1.0904; m=4: 1.0904. Cross-check against `linearmodels.PanelOLS(entity_effects=True, time_effects=True).fit(cov_type='kernel', kernel='bartlett', bandwidth=m)` on the real regressors (linearmodels' own factor n/(n - df_model) applied to the numpy sandwich): m=2: max relative difference in standard errors 2.1e-15, m=4: max relative difference in standard errors 2.9e-15; coefficients 5.7e-14.

### Two-way clustering

Cameron-Gelbach-Miller (2011) V = V_country + V_year - V_(country x year), with c_G = G/(G-1) (N-1)/(N-K), c_T = T/(T-1) (N-1)/(N-K), c_GT = N/(N-K). Variance matrix not positive semi-definite: True (smallest eigenvalue -6.620e-02, 1 negative); when it was not, the negative eigenvalues were set to zero before the standard errors were read.

### CCE designs (Pesaran 2006, country-specific coefficients on cross-sectional averages, year effects kept)

| version | CSA variables | added parameters | total parameters | residual df (N - parameters) | df exhausted | dropped exactly collinear columns |
|---|---|---|---|---|---|---|
| CCE-lite | 2 (capb, W_S) | 52 | 114 | 601 | False | 2 (one country column per CSA variable: the sum over countries of d_i x csa_t equals csa_t, a combination of the year dummies) |
| CCE-full | 10 (capb, W_S, W_E, W_U, Post, WS_x_between, WS_x_within, A_lag, WS_x_era_2008_2015, WS_x_era_2016_2021) | 260 | 322 | 393 | False | 10 (one country column per CSA variable: the sum over countries of d_i x csa_t equals csa_t, a combination of the year dummies) |

Note: the CR1 factor uses the project convention k = year dummies + regressors; with 260 added columns the CCE-full CR1 factor is large. 

### Residual cross-section dependence (Pesaran 2015 CD; mean absolute pairwise correlation)

CD is computed on pairwise correlations of the residuals over common years (351 pairs). Residuals of models with year effects have an average pairwise correlation of about -1/(N-1) = -0.038 by construction, which shifts CD to about -3.7 even under independence and pins the sum of the correlations, so the N(0,1) p-value is not informative here. Simulated benchmarks for independent errors pushed through the same projection are shown (iid errors; AR(1) errors with the estimated persistence rho = 0.623 and country SDs). The mean absolute correlation is the more informative summary.

| residuals | CD | mean pairwise corr | mean abs corr | CD null mean (iid / AR(1)) | mean abs corr null (iid / AR(1), sd) | excess mean abs corr vs AR(1) null |
|---|---|---|---|---|---|---|
| OLS-FE (V0) | -3.37 | -0.036 | 0.257 | -3.67 / -2.75 | 0.164 / 0.224 (0.014) | 0.032 |
| V7 (raw residuals) | -3.66 | -0.039 | 0.266 | -3.67 / -2.75 | 0.164 / 0.224 (0.014) | 0.042 |
| V7 (Prais-Winsten weighted residuals) | -3.40 | -0.036 | 0.172 | -3.67 / -2.75 | 0.164 / 0.224 (0.014) | -0.052 |
| OLS-FE + CCE-lite | -3.52 | -0.037 | 0.266 | -3.66 / -2.75 | 0.171 / 0.231 (0.015) | 0.035 |
| V7 + CCE-lite (raw residuals) | -3.70 | -0.039 | 0.276 | -3.66 / -2.75 | 0.171 / 0.231 (0.015) | 0.045 |
| V7 + CCE-lite (Prais-Winsten weighted residuals) | -3.48 | -0.037 | 0.186 | -3.66 / -2.75 | 0.171 / 0.231 (0.015) | -0.045 |
| OLS-FE + CCE-full | -3.04 | -0.032 | 0.260 | -3.62 / -2.69 | 0.209 / 0.255 (0.016) | 0.005 |
| V7 + CCE-full (raw residuals) | -3.56 | -0.037 | 0.252 | -3.62 / -2.69 | 0.209 / 0.255 (0.016) | -0.003 |
| V7 + CCE-full (Prais-Winsten weighted residuals) | -3.51 | -0.037 | 0.234 | -3.62 / -2.69 | 0.209 / 0.255 (0.016) | -0.022 |

## B. Pre-registered diagnostics (reported, never used to choose a specification)

### Groupwise heteroskedasticity (modified Wald, Greene) and serial correlation (Wooldridge)

The modified Wald statistic over-rejects when T is small (in a 400-draw check with iid normal errors the 5% test rejected 32% of the time at T = 40, 7.5% at T = 200), so a Monte Carlo p-value under iid normal errors with this panel's layout is shown beside the chi-square p-value.

| test | statistic | df | p (chi-square) | detail |
|---|---|---|---|---|
| modified Wald (OLS-FE residuals) | 900.1 | 27 | 3.08e-172 | Monte Carlo p = 0.0005 (null median 44.9, 95th percentile 91.3); country residual SD from 1.03 to 5.29 |
| modified Wald (V7 residuals) | 1468.0 | 27 | 6.76e-293 | Monte Carlo p = 0.0005 (null median 44.9, 95th percentile 91.3); country residual SD from 0.93 to 5.49 |
| Wooldridge (H0: coefficient = -0.5) | F = 43.5 | (1, 26) | 5.43e-07 | coefficient -0.218 (se 0.043), 661 residual pairs |

### Panel unit-root tests (CIPS, Pesaran 2007; lag order fixed at 1; critical values simulated for this unbalanced layout)

| series | deterministic terms | CIPS | simulated 1% / 5% / 10% critical values | p (left tail) | unit root rejected at 5% |
|---|---|---|---|---|---|
| capb | constant | -2.112 | -2.33 / -2.17 / -2.06 | 0.0725 | False |
| capb | trend | -2.728 | -2.82 / -2.65 / -2.57 | 0.0280 | True |
| lagged OLDDEP1 | constant | -1.717 | -2.33 / -2.13 / -2.06 | 0.5132 | False |
| lagged OLDDEP1 | trend | -2.090 | -2.87 / -2.69 / -2.59 | 0.7246 | False |

### Variance inflation factors of the M1 regressors (flag above 5)

| regressor | VIF after partialling out country and year effects | VIF on the raw columns |
|---|---|---|
| W_S | 1.05 | 1.08 |
| W_E | 1.02 | 1.03 |
| W_U | 1.00 | 1.02 |
| Post | 1.02 | 1.02 |
| WS_x_between | 1.00 | 1.17 |
| WS_x_within | 4.90 | 4.67 |
| A_lag | 1.25 | 1.37 |
| WS_x_era_2008_2015 | 2.08 | 2.02 |
| WS_x_era_2016_2021 | 5.32 (flag) | 5.18 (flag) |

### Hausman FE vs RE

* Mundlak/Wooldridge regression form with country-clustered covariance: Wald = 66.89 on 9 country-mean coefficients, F(9, 26) p = 2.7e-05 (chi-square p = 6.2e-11); dropped exactly collinear country means: none.
* Classical Hausman (linearmodels FE vs RE, homoskedastic covariances; coefficients on the M1 regressors and the year dummies): H = 0.10, df = 2, p = 0.9526; negative eigenvalues of V_FE - V_RE: 33. The estimated random-effects variance is zero (theta = 0), so the RE estimator is pooled OLS and V_FE - V_RE is far from positive semi-definite: this classical statistic is not interpretable here; the Mundlak form above is the Hausman result.

### Binned linearity and common support: between component of ageing (three equal-count bins; OLS-FE, CR1)

| bin | component range (SD units) | obs | countries | exposed obs (W_S > 0) | exposed countries | binned effect of W_S [95% CI] | linear-model prediction | thin support (< 5 exposed countries) |
|---|---|---|---|---|---|---|---|---|
| 1 | -2.02 to -0.26 | 263 | 10 | 77 | 8 | -0.797 [-1.475, -0.119] | -0.625 | False |
| 2 | -0.12 to 0.55 | 216 | 8 | 87 | 8 | -0.225 [-0.745, 0.296] | -0.307 | False |
| 3 | 0.59 to 1.75 | 236 | 9 | 76 | 8 | 0.027 [-0.785, 0.838] | -0.101 | False |

Linearity (adding W_S x bin 2 and W_S x bin 3 to the linear model): F(2, 26) = 0.93, p = 0.4058. Linear OLS-FE coefficients: beta_S -0.357, interaction 0.258.

### Binned linearity and common support: within component of ageing (three equal-count bins; OLS-FE, CR1)

| bin | component range (SD units) | obs | countries | exposed obs (W_S > 0) | exposed countries | binned effect of W_S [95% CI] | linear-model prediction | thin support (< 5 exposed countries) |
|---|---|---|---|---|---|---|---|---|
| 1 | -2.08 to -0.52 | 239 | 26 | 78 | 22 | 1.116 [-1.680, 3.911] | 0.437 | False |
| 2 | -0.52 to 0.24 | 238 | 27 | 77 | 20 | -0.203 [-1.486, 1.080] | -0.188 | False |
| 3 | 0.26 to 3.08 | 238 | 26 | 85 | 22 | -1.865 [-4.302, 0.573] | -1.320 | False |

Linearity (adding W_S x bin 2 and W_S x bin 3 to the linear model): F(2, 26) = 0.60, p = 0.5537. Linear OLS-FE coefficients: beta_S -0.357, interaction -0.796.

### Lead placebo (V7; W_S_lead = share of year t inside months 13-24 before a scheduled election; the pre-window itself is months 1-12)

| sample | N | W_S_lead: estimate [95% bootstrap-t interval]; p | beta_S in the augmented model | gamma_B in the augmented model |
|---|---|---|---|---|
| as specified: 1995-2021 | 715 | -0.075 [-0.535, 0.391]; p = 0.7605 | -0.406 [-0.780, -0.032] | 0.210 [-0.059, 0.486] |
| to 2020 (the lead window of 2021 reaches into 2023, where the election calendar is incomplete) | 688 | -0.018 [-0.451, 0.418]; p = 0.9271 | -0.326 [-0.663, 0.010] | 0.199 [-0.052, 0.455] |

## C. Sample variants (V7, wild-cluster bootstrap-t B = 9,999; leave-one-out B = 999)

The estimator is the pre-registered V7 in every row; the sample is changed as stated. Estimates and intervals follow the headline procedure (bootstrap-t percentile interval; p from the null-imposed bootstrap). CR1 numbers for each row are stored in the json (`extra.cr1_transparency`).

| id | specification | inference | N | beta_S: est [95% interval]; p; reading | gamma_B: est [95% interval]; p; reading | gamma_W: est [95% interval] |
|---|---|---|---|---|---|---|
| C1-balanced22 | Balanced-22 (countries observed in all 27 years) | wild-cluster bootstrap-t, B=9999 | 594 | -0.276 [-0.612, 0.058]; p=0.1085; inconclusive | 0.270 [-0.021, 0.563]; p=0.0502; inconclusive | -0.402 [-1.760, 0.908] |
| C2-drop-unclassified-delayed | Drop country-years touching unclassified or delayed elections | wild-cluster bootstrap-t, B=9999 | 683 | -0.356 [-0.668, -0.046]; p=0.0258; excl. 0 | 0.207 [-0.051, 0.469]; p=0.1143; equiv. +-0.5 | -0.238 [-1.462, 0.980] |
| C3-gapfilled | Gap-filled election classes (*_gf exposure columns) | wild-cluster bootstrap-t, B=9999 | 715 | -0.353 [-0.700, -0.006]; p=0.0577; excl. 0 | 0.123 [-0.170, 0.419]; p=0.4339; equiv. +-0.5 | -0.125 [-1.343, 1.091] |
| C5-ireland-winsor | Ireland 2010 handled by residual-tail winsorising (V2w rule, 1st/99th percentile) | wild-cluster bootstrap-t, B=9999 | 715 | -0.396 [-0.702, -0.134]; p=0.0105; excl. 0 | 0.211 [-0.070, 0.508]; p=0.1414; inconclusive | -0.299 [-1.461, 0.941] |
| C6a-drop-2008-2012 | Drop 2008-2012 | wild-cluster bootstrap-t, B=9999 | 580 | -0.489 [-0.762, -0.206]; p=0.0008; excl. 0 | 0.246 [-0.158, 0.651]; p=0.1509; inconclusive | -0.570 [-2.148, 1.027] |
| C6b-drop-2020-2021 | Drop 2020-2021 | wild-cluster bootstrap-t, B=9999 | 661 | -0.333 [-0.668, 0.011]; p=0.0586; inconclusive | 0.274 [0.020, 0.537]; p=0.0617; excl. 0 | -0.136 [-1.394, 1.110] |
| C6c-drop-both | Drop 2008-2012 and 2020-2021 | wild-cluster bootstrap-t, B=9999 | 526 | -0.469 [-0.794, -0.137]; p=0.0094; excl. 0 | 0.275 [-0.079, 0.632]; p=0.0544; inconclusive | -0.306 [-2.176, 1.587] |
| C8-controls | Robustness-controls model (adds lagged output gap and euro membership) | wild-cluster bootstrap-t, B=9999 | 703 | -0.351 [-0.673, -0.030]; p=0.0283; excl. 0 | 0.144 [-0.222, 0.510]; p=0.3801; inconclusive | -0.244 [-1.531, 1.023] |
| C7-extension-2022 | 2022 extension (ETAD-trusted exposure for 22 countries) | wild-cluster bootstrap-t, B=9999 | 737 | -0.365 [-0.644, -0.086]; p=0.0168; excl. 0 | 0.223 [-0.046, 0.500]; p=0.1179; inconclusive | 0.081 [-0.706, 0.868] |

Notes:
* C1-balanced22: 22 countries
* C2-drop-unclassified-delayed: 32 country-years dropped; W_U and W_D are then identically zero and drop out of the model
* C5-ireland-winsor: winsorising is applied to the first-stage residuals in every bootstrap sample, as in the project's V2w
* C8-controls: complete cases of the two controls: N = 703 (specification: 703)
* C7-extension-2022: +22 country-years in 2022; no 2022 for AT, CY, EL, MT, PL

2022 extension: built with the frozen panel assembler (`assemble_gold_panel(..., end=2022)`); the 1995-2021 part reproduces the confirmatory extract exactly. N = 737 (+22); no 2022 for AT, CY, EL, MT, PL (exposure not complete on the ETAD basis). Exposure for 2022 is complete only on trust in ETAD.

### Leave-one-country-out (27 fits, B = 999)

* beta_S: headline -0.379; leave-one-out estimates range from -0.422 (without LU) to -0.266 (without RO); largest shift from the headline when RO is removed (-0.266, shift 0.113); 27/27 keep the sign; interval excludes zero in 26/27; bootstrap p between 0.0050 and 0.0880.
* gamma_B: headline 0.207; leave-one-out estimates range from 0.132 (without RO) to 0.299 (without HR); largest shift from the headline when HR is removed (0.299, shift 0.093); 27/27 keep the sign; interval excludes zero in 1/27; bootstrap p between 0.0150 and 0.3420.

| left out | beta_S: est [95% interval]; p; reading | gamma_B: est [95% interval]; p; reading |
|---|---|---|
| AT | -0.389 [-0.733, -0.056]; p=0.0380; excl. 0 | 0.187 [-0.102, 0.474]; p=0.2100; equiv. +-0.5 |
| BE | -0.404 [-0.736, -0.087]; p=0.0180; excl. 0 | 0.176 [-0.101, 0.452]; p=0.2360; equiv. +-0.5 |
| BG | -0.408 [-0.688, -0.123]; p=0.0090; excl. 0 | 0.169 [-0.100, 0.432]; p=0.2220; equiv. +-0.5 |
| CY | -0.370 [-0.663, -0.085]; p=0.0090; excl. 0 | 0.197 [-0.075, 0.462]; p=0.1490; equiv. +-0.5 |
| CZ | -0.369 [-0.678, -0.075]; p=0.0230; excl. 0 | 0.216 [-0.073, 0.485]; p=0.1360; equiv. +-0.5 |
| DE | -0.402 [-0.729, -0.078]; p=0.0170; excl. 0 | 0.169 [-0.112, 0.456]; p=0.2620; equiv. +-0.5 |
| DK | -0.408 [-0.683, -0.136]; p=0.0110; excl. 0 | 0.213 [-0.101, 0.502]; p=0.1510; inconclusive |
| EE | -0.416 [-0.722, -0.119]; p=0.0110; excl. 0 | 0.201 [-0.100, 0.475]; p=0.1690; equiv. +-0.5 |
| EL | -0.375 [-0.671, -0.092]; p=0.0200; excl. 0 | 0.217 [-0.043, 0.456]; p=0.0860; equiv. +-0.5 |
| ES | -0.375 [-0.684, -0.070]; p=0.0160; excl. 0 | 0.206 [-0.094, 0.493]; p=0.1680; equiv. +-0.5 |
| FI | -0.404 [-0.696, -0.120]; p=0.0100; excl. 0 | 0.199 [-0.093, 0.478]; p=0.1690; equiv. +-0.5 |
| FR | -0.379 [-0.688, -0.092]; p=0.0210; excl. 0 | 0.219 [-0.057, 0.495]; p=0.1350; equiv. +-0.5 |
| HR | -0.333 [-0.622, -0.071]; p=0.0300; excl. 0 | 0.299 [0.050, 0.528]; p=0.0150; excl. 0 |
| HU | -0.387 [-0.685, -0.098]; p=0.0140; excl. 0 | 0.213 [-0.076, 0.471]; p=0.1130; equiv. +-0.5 |
| IE | -0.357 [-0.686, -0.049]; p=0.0270; excl. 0 | 0.189 [-0.094, 0.443]; p=0.1590; equiv. +-0.5 |
| IT | -0.387 [-0.689, -0.100]; p=0.0200; excl. 0 | 0.219 [-0.083, 0.471]; p=0.1170; equiv. +-0.5 |
| LT | -0.401 [-0.728, -0.090]; p=0.0210; excl. 0 | 0.225 [-0.075, 0.490]; p=0.1070; equiv. +-0.5 |
| LU | -0.422 [-0.707, -0.146]; p=0.0050; excl. 0 | 0.271 [-0.059, 0.560]; p=0.0530; inconclusive |
| LV | -0.349 [-0.673, -0.069]; p=0.0230; excl. 0 | 0.224 [-0.048, 0.477]; p=0.0970; equiv. +-0.5 |
| MT | -0.364 [-0.698, -0.060]; p=0.0220; excl. 0 | 0.209 [-0.070, 0.482]; p=0.1340; equiv. +-0.5 |
| NL | -0.403 [-0.704, -0.144]; p=0.0100; excl. 0 | 0.215 [-0.077, 0.504]; p=0.1420; inconclusive |
| PL | -0.346 [-0.796, 0.073]; p=0.0880; inconclusive | 0.237 [-0.238, 0.686]; p=0.3420; inconclusive |
| PT | -0.391 [-0.751, -0.089]; p=0.0200; excl. 0 | 0.224 [-0.051, 0.497]; p=0.1250; equiv. +-0.5 |
| RO | -0.266 [-0.555, -0.023]; p=0.0540; excl. 0 | 0.132 [-0.100, 0.354]; p=0.3110; equiv. +-0.5 |
| SE | -0.409 [-0.715, -0.108]; p=0.0150; excl. 0 | 0.169 [-0.130, 0.454]; p=0.2450; equiv. +-0.5 |
| SI | -0.374 [-0.710, -0.041]; p=0.0350; excl. 0 | 0.201 [-0.070, 0.463]; p=0.1450; equiv. +-0.5 |
| SK | -0.360 [-0.668, -0.062]; p=0.0260; excl. 0 | 0.191 [-0.102, 0.467]; p=0.1930; equiv. +-0.5 |

## D. Definition variants (V7, wild-cluster bootstrap-t B = 9,999)

Windows are rebuilt from `data/interim/election_calendar_eu27.csv` by the share-of-year union construction (new code; the 12-month rebuild reproduces the frozen exposure columns to 1e-12, checked in the tests). The post-election window stays 12 months in the 6- and 18-month variants.

| id | specification | inference | N | beta_S: est [95% interval]; p; reading | gamma_B: est [95% interval]; p; reading | gamma_W: est [95% interval] |
|---|---|---|---|---|---|---|
| D1-window-6m | Pre-election window of 6 months (all classes rebuilt; Post stays 12 months) | wild-cluster bootstrap-t, B=9999 | 715 | -0.545 [-0.953, -0.155]; p=0.0020; excl. 0 | 0.122 [-0.423, 0.655]; p=0.5959; inconclusive | -0.812 [-2.594, 0.967] |
| D2-window-18m | Pre-election window of 18 months (all classes rebuilt; Post stays 12 months) | wild-cluster bootstrap-t, B=9999 | 715 | -0.298 [-0.616, 0.019]; p=0.0664; inconclusive | 0.279 [-0.062, 0.614]; p=0.1476; inconclusive | -0.134 [-0.824, 0.562] |
| D3-calendar-year-dummy | Calendar-year election dummies in place of the fractional pre-window exposure (W_S, W_E, W_D, W_U; Post kept) | wild-cluster bootstrap-t, B=9999 | 715 | -0.235 [-0.424, -0.053]; p=0.0092; excl. 0 | 0.051 [-0.138, 0.235]; p=0.5623; equiv. +-0.5 | -0.405 [-1.122, 0.303] |
| D4-olddep3 | Moderator: OLDDEP3 lag (re-standardised, same Mundlak split) | wild-cluster bootstrap-t, B=9999 | 715 | -0.381 [-0.698, -0.066]; p=0.0191; excl. 0 | 0.202 [-0.072, 0.489]; p=0.1573; equiv. +-0.5 | -0.236 [-1.376, 0.908] |
| D5-medage | Moderator: median age lag (re-standardised, same Mundlak split) | wild-cluster bootstrap-t, B=9999 | 715 | -0.329 [-0.610, -0.050]; p=0.0347; excl. 0 | 0.207 [-0.117, 0.532]; p=0.2546; inconclusive | -0.494 [-1.985, 0.979] |

Notes:
* D1-window-6m: exposure for 2021 needs elections through 2022-06; beta_S is per full year inside a 6-month window, so a unit of exposure covers a different span of calendar time than in the headline (12 months): compare sign and interval, not magnitude
* D2-window-18m: exposure for 2021 needs elections through 2023-06 (ParlGov coverage ends 2023-06; ETAD 2023 is partial); beta_S is per full year inside a 18-month window, so a unit of exposure covers a different span of calendar time than in the headline (12 months): compare sign and interval, not magnitude
* D3-calendar-year-dummy: scale differs from the headline: 1 = an election of the class occurs in year t, versus the share of the year inside the 12-month window
* D4-olddep3: rows with olddep3_lag observed: 715 of 715
* D5-medage: rows with medage_lag observed: 715 of 715

## Summary counts (descriptive; specifications are not independent)

| group | specifications | failed | beta_S keeps sign | beta_S interval excludes 0 | beta_S interval inside +-0.5 | gamma_B keeps sign | gamma_B interval excludes 0 | gamma_B interval inside +-0.5 |
|---|---|---|---|---|---|---|---|---|
| all specifications | 52 | 0 | 52/52 | 41/52 | 1/52 | 52/52 | 2/52 | 26/52 |
| all excluding the 27 leave-one-out fits | 25 | 0 | 25/25 | 15/25 | 1/25 | 25/25 | 1/25 | 4/25 |
| A inference | 11 | 0 | 11/11 | 4/11 | 0/11 | 11/11 | 0/11 | 0/11 |
| C sample variants (excl. leave-one-out) | 9 | 0 | 9/9 | 7/9 | 0/9 | 9/9 | 1/9 | 2/9 |
| C leave-one-country-out fits | 27 | 0 | 27/27 | 26/27 | 0/27 | 27/27 | 1/27 | 22/27 |
| D definitions | 5 | 0 | 5/5 | 4/5 | 1/5 | 5/5 | 0/5 | 2/5 |

## E. Outputs and tests

* Files: `reports/results/robustness.md` (this file), `reports/results/robustness.json` (every specification with all numbers, the dependence diagnostics and the summary counts), `reports/figures/robustness_forest.png` (beta_S and gamma_B, point estimates and 95% intervals, 300 dpi).
* Tests (`tests/test_robustness.py`) use synthetic panels with a known answer: the numpy Driscoll-Kraay standard errors equal `linearmodels` (bandwidths 0, 2, 4; balanced and unbalanced); two-way clustering equals statsmodels' `cov_cluster_2groups` without small-sample factors; CCE removes the bias of a heterogeneous common factor that year effects cannot; Pesaran CD is N(0,1)-like under independence and large under a common factor; the modified Wald, Wooldridge, CIPS, Mundlak-Hausman and binned tests reject where they should and not where they should not; the 12-month exposure rebuild reproduces the frozen exposure columns to 1e-12; and the frozen files match `docs/freeze_manifest.json` byte for byte (LF-normalised SHA-256).

## What this does not show

* The results are associations. Scheduled elections are predetermined, not exogenous, and the ageing interactions (especially gamma_B, a cross-country contrast) have no causal reading.
* The specifications are not independent: they share one panel, many are nested, and several rows are the same estimate under different inference. Counts of specifications that keep a sign or exclude zero are descriptive, not a vote and not a probability.
* No specification is preferred. The headline remains the pre-registered V7 result; sensitivities are reported whatever they show.
* The CAPB is a model estimate with a typical first-outturn revision of 0.64 pp, as large as the SESOI; none of these checks addresses measurement error.
* Diagnostics (section B) describe the data and were not used to choose any specification.

## Provenance

* seed 42, bootstrap seed key 42; B = 9999 (main), 999 (each leave-one-country-out fit); Rademacher weights, whole feasible procedure re-estimated in every bootstrap sample
* versions: numpy 2.4.4, pandas 3.0.2, scipy 1.17.1
* gold extract hash: `2fcf20d4ca687f613d6743214b7be176ceb638b483f513eeed005bd1f73a5bb4`
* robustness.py SHA-256 (LF-normalised): `c413b4f3dbc06d86590fd3a61df32bfa2b61607b561b49e9f8ec282c9ef61e03`
* headline registry hash `8bb8383691e4acc2b102d805ee576410308c667f649a3b41d185e924137c03ee`; headline code hash `8823d782c2669d5c2848dfa92554da013065e4fa36a05ea7f2d5318357bd3d2c`
