# Exploratory models E1-E4, E6

Status: complete (stage estimates). Source: `real_gold_panel`. **Exploratory.** All results are associations; scheduled elections are predetermined, not exogenous. The fiscal-rule index is a de jure design-strength score of national numerical rules, not enforcement or compliance. Specification: `docs/exploratory_spec.md` (written before any exploratory result). Estimates are in pp of potential GDP (CAPB, `UBLGBP`, surplus positive). B = 9999 (leave-one-out 999), seed key 42, Rademacher weights, whole feasible procedure re-estimated in every bootstrap sample. CR1 p-values are not primary results and are not shown.

## Deviations

* No deviation from the specified models, estimators, inference, family or reading rules.
* Implementation choices the spec left open (no effect on any specified quantity): the 22 power-block jobs ran in parallel worker processes (each job has its own fixed seed stream); the power block was computed by the version of `exploratory.py` before two cosmetic edits (forest-plot source note shown only when an interval is clipped, and this text), so its code hash in the provenance differs; E4d Mundlak companion centres both split interactions at the exposure-weighted mean and does not rescale them.
* E6 stability: only about 16% of single-start k-means seeds reproduce the reference partition (the table's n_init = 50 solution) although Ward linkage gives the same partition; this is reported as the spec requires (no threshold), not corrected.

## Availability facts (no outcome column used)

* Workbook SHA-256 `7f4c291315ddaee55ccf8ebd70f69a44f1ea04c99679ed58ddd10497d340a6a9` (equals the manifest). E1 window 2016-2021: 162 country-years, **E1 N = 160**, 27 countries; dropped (lagged index missing): [['CZ', 2016], ['CZ', 2017]]; countries with fewer rows: {'CZ': 4}.
* W_S > 0 in 55 rows (22 countries), mean W_S 0.172. Lagged raw index: mean 13.665, SD 3.759, range 4.697 to 22.256.
* Long window 2012-2021: 270 rows, numeric lagged index in 254; '.' rows by country: {'CZ': [2012, 2013, 2014, 2015, 2016, 2017], 'EL': [2012], 'HU': [2012, 2013], 'MT': [2012, 2013, 2014], 'SI': [2012, 2013, 2014, 2015]}.
* NL raw index 2017-2024: {'2017': 19.6163055555556, '2018': 19.6163055555556, '2019': 19.6163055555556, '2020': 19.6163055555556, '2021': 12.915753246346219, '2022': 12.915753246346219, '2023': 19.763888888888893, '2024': 19.930555555555557}; NL index years used by E1 rows: [2015, 2016, 2017, 2018, 2019, 2020] (values [21.0784, 21.8766, 19.6163, 19.6163, 19.6163, 19.6163]).
* Lagged debt missing in 27 of 715 full-sample rows.

## Power block (written before any E1/E2 estimate was computed)

Noise calibration (Gate 3b, `power.calibrate` of the V0n design): corrected rho 0.694 (Gate 3b 0.694; reproduces: True), country residual SD 1.08 to 5.58 pp. Settings: {'n_null': 20000, 'size_fast': 4000, 'mde_fast': 1500, 'size_generic': 1500, 'mde_generic': 500, 'n_boot': 399, 'n_bias': 5000, 'n_ldv_cr1': 6000}. Scenarios: AR(1) at the corrected rho and at rho = 0; the block-bootstrap scenario is not run for the window (its residual grid is indexed to 27 years). MDE = effect with 80% power, alpha 0.05, two-sided, in the target's units (E1: pp per +1 SD of the index, 1 SD = the sd_F_raw index points).

| model | target | estimator | scenario | CR1 size | CR1 MDE | CR1 MDE size-adj. | wild-bootstrap size | wild-bootstrap MDE | MDE, index points |
|---|---|---|---|---|---|---|---|---|---|
| E1 | gamma_F | V7 | ar1_rho_hat | 0.179 | 1.002 | 1.345 | 0.058 | 1.423 | 0.378 |
| E1 | gamma_F | V7 | ar1_rho0 | 0.189 | 1.537 | 2.084 | 0.055 | 2.182 | 0.581 |
| E1 | gamma_F | V3 | ar1_rho_hat | 0.188 | 1.061 | 1.449 | 0.063 | 1.559 | 0.415 |
| E1 | gamma_F | V3 | ar1_rho0 | 0.186 | 1.544 | 2.081 | 0.054 | 2.186 | 0.582 |
| E1 | gamma_F | V0 | ar1_rho_hat | 0.064 | 1.493 | 1.559 | 0.057 | 1.652 | 0.440 |
| E1 | gamma_F | V0 | ar1_rho0 | 0.061 | 2.098 | 2.176 | 0.046 | 2.314 | 0.615 |
| E2 | delta_BF | V7 | ar1_rho_hat | 0.220 | 1.033 | 1.541 | 0.057 | 2.043 | 0.544 |
| E2 | delta_BF | V7 | ar1_rho0 | 0.231 | 1.683 | 2.556 | 0.045 | 3.170 | 0.843 |
| E2 | delta_BF | V3 | ar1_rho_hat | 0.218 | 1.148 | 1.719 | 0.063 | 2.253 | 0.599 |
| E2 | delta_BF | V3 | ar1_rho0 | 0.228 | 1.686 | 2.546 | 0.045 | 3.224 | 0.858 |
| E2 | delta_BF | V0 | ar1_rho_hat | 0.117 | 1.509 | 1.793 | 0.058 | 2.332 | 0.620 |
| E2 | delta_BF | V0 | ar1_rho0 | 0.102 | 2.164 | 2.529 | 0.051 | 3.271 | 0.870 |
| E3 | delta_H | V7 | ar1_rho_hat | 0.104 | 1.714 | 2.004 | - | - | - |
| E3 | delta_H | V7 | ar1_rho0 | 0.107 | 2.748 | 3.240 | - | - | - |
| E4a | delta_debt_between | V7 | ar1_rho_hat | 0.087 | 1.157 | 1.291 | - | - | - |
| E4a | delta_debt_between | V7 | ar1_rho0 | 0.088 | 1.822 | 2.027 | - | - | - |
| E4b | delta_debt_within_time | V7 | ar1_rho_hat | 0.080 | 1.105 | 1.212 | - | - | - |
| E4b | delta_debt_within_time | V7 | ar1_rho0 | 0.087 | 1.759 | 1.945 | - | - | - |
| E4c | delta_accession | V7 | ar1_rho_hat | 0.089 | 1.017 | 1.143 | - | - | - |
| E4c | delta_accession | V7 | ar1_rho0 | 0.093 | 1.628 | 1.842 | - | - | - |
| E4d | delta_euro | V7 | ar1_rho_hat | 0.082 | 0.977 | 1.076 | - | - | - |
| E4d | delta_euro | V7 | ar1_rho0 | 0.080 | 1.550 | 1.689 | - | - | - |

Design information (squared norm of the residualised target regressor; larger = more information): E1 8.69; E2 6.98; E3 3.48; E4a 9.77; E4b 9.22; E4c 10.65; E4d 11.21; M1_beta_S 47.31.

**E1 promotion check** (wild-bootstrap MDE of `gamma_F` per +1 SD at the estimated rho; line 1.0 pp, G2 interaction line 0.75 pp beside it):

* V7: MDE 1.423 pp (rho 0: 2.182); within 1.0 pp: False; within 0.75 pp: False.
* V3: MDE 1.559 pp (rho 0: 2.186); within 1.0 pp: False; within 0.75 pp: False.
* V0: MDE 1.652 pp (rho 0: 2.314); within 1.0 pp: False; within 0.75 pp: False.

Promotion would require an amendment in `docs/amendments.md`; this run promotes nothing and E1 stays exploratory.

## Family (Benjamini-Hochberg q = 0.05 over the pre-listed seven coefficients; Benjamini-Yekutieli beside it)

m listed 7, m used 7; BH rejections 0; BY rejections 0. Raw p: null-imposed wild-cluster bootstrap-t; q: adjusted within this family.

| model | coefficient | estimator | N (countries) | estimate [95% interval] | raw p | BH q | BY q | MDE (wild bootstrap, rho-hat / rho 0) | reading |
|---|---|---|---|---|---|---|---|---|---|
| E1 | gamma_F | V7 | 160 (27) | 0.242 [-0.172, 0.654] | 0.3667 | 0.7495 | 1.0000 | 1.423 / 2.182 | interval contains zero |
| E2 | delta_BF | V7 | 160 (27) | 0.259 [-0.061, 0.585] | 0.2060 | 0.7210 | 1.0000 | 2.043 / 3.170 | interval contains zero |
| E3 | delta_H | V7 | 715 (27) | -0.203 [-0.710, 0.295] | 0.4283 | 0.7495 | 1.0000 | CR1 size-adj. 2.004 / 3.240 | interval contains zero |
| E4a | delta_debt_between | V7 | 715 (27) | -0.066 [-0.767, 0.636] | 0.8523 | 0.8523 | 1.0000 | CR1 size-adj. 1.291 / 2.027 | interval contains zero |
| E4b | delta_debt_within_time | V7 | 688 (27) | 0.163 [-0.440, 0.766] | 0.5695 | 0.7973 | 1.0000 | CR1 size-adj. 1.212 / 1.945 | interval contains zero |
| E4c | delta_accession | V7 | 715 (27) | -0.747 [-1.494, -0.027] | 0.0745 | 0.5215 | 1.0000 | CR1 size-adj. 1.143 / 1.842 | interval excludes zero, not BH-rejected (nominal only) |
| E4d | delta_euro | V7 | 715 (27) | 0.074 [-0.561, 0.724] | 0.8196 | 0.8523 | 1.0000 | CR1 size-adj. 1.076 / 1.689 | interval contains zero |

Units: E1, E2, E3 per +1 SD of the moderator(s) as defined in the spec; E4 the difference between the two groups. No equivalence reading against 0.5 pp (that threshold was set for beta_S only).

## E1: fiscal-rule moderation, 2016-2021

Estimator in force: **V7**; fallback triggered: False.

Feasibility checks (F1-F4):

* V7: feasible WLS + AR(1) GLS: ok; checks {'F1_full_rank': True, 'F2_nickell_invertible': True, 'F3_variance_floor_ok': True, 'country_sd_min': 0.14241067356275963, 'country_sd_max': 2.919532904229889, 'raw_rho': 0.042870887499792544, 'corrected_rho': 0.2661420187466775, 'plim_min': -0.9583113636264196, 'plim_max': 0.9248076702881252, 'mean_years': 5.925925925925926, 'passed': True, 'F4_bootstrap_finite': True}
* V3: feasible WLS only: ok; checks {'F1_full_rank': True, 'F2_nickell_invertible': None, 'F3_variance_floor_ok': True, 'country_sd_min': 0.14241067356275963, 'country_sd_max': 2.919532904229889, 'passed': True, 'F4_bootstrap_finite': True}
* V0: two-way OLS: ok; checks {'F1_full_rank': True, 'F2_nickell_invertible': None, 'F3_variance_floor_ok': None, 'passed': True, 'F4_bootstrap_finite': True}

### Primary (estimator in force), all targets

| target | estimate [95% bootstrap-t interval] | raw p |
|---|---|---|
| beta_S | -0.516 [-0.873, -0.153] | not tested |
| gamma_B | -0.685 [-1.079, -0.299] | not tested |
| gamma_W | -0.444 [-1.339, 0.472] | not tested |
| gamma_F | 0.242 [-0.172, 0.654] | 0.3667 |

### Estimator ladder for `gamma_F` (V7, V3, V0; sensitivity rows, none selected)

| estimator | status | N | gamma_F [95% interval] | raw p |
|---|---|---|---|---|
| V7 (in force) | ok | 160 | 0.242 [-0.172, 0.654] | 0.3667 |
| V3 | ok | 160 | 0.252 [-0.122, 0.629] | 0.2684 |
| V0 | ok | 160 | 0.298 [-0.366, 0.964] | 0.4013 |

### Companion (descriptive, interval only): between/within split of the index

| target | estimate [95% bootstrap-t interval] | raw p |
|---|---|---|
| gamma_F_B | 0.353 [-0.163, 0.871] | not tested |
| gamma_F_W | -0.195 [-1.679, 1.322] | not tested |

### Sensitivity: Without the ageing interactions

N = 160 (27 countries), estimator V7: **gamma_F = 0.123 [-0.414, 0.654]**, raw p 0.6807.

### Sensitivity: Long window 2012-2021 (back-cast zone 2012-2015 flagged; single era term)

N = 254 (27 countries), estimator V7: **gamma_F = -0.188 [-1.262, 0.892]**, raw p 0.6745.

### Sensitivity: Rule-presence dummy, 2012-2021 ('.' coded 0; ambiguous reading)

N = 270 (27 countries), estimator V7: **delta_P = -0.210 [-1.265, 0.847]**, raw p 0.6779.

### Sensitivity: NL 2021-22 included

not re-estimated: identical by construction. Frames identical for year <= 2021: True; largest NL index year used: 2020.

### Leave-one-country-out (27 fits, V7, B = 999)

Range of `gamma_F`: 0.179 to 0.392; most influential country: LT; sign changes: 0; changes of the exclude-zero reading: 1; failed fits: 0.

| dropped | N | gamma_F [95% interval] | raw p |
|---|---|---|---|
| AT | 154 | 0.320 [-0.126, 0.789] | 0.272 |
| BE | 154 | 0.229 [-0.202, 0.693] | 0.406 |
| BG | 154 | 0.258 [-0.166, 0.689] | 0.405 |
| CY | 154 | 0.236 [-0.206, 0.693] | 0.382 |
| CZ | 156 | 0.191 [-0.235, 0.636] | 0.461 |
| DE | 154 | 0.232 [-0.227, 0.677] | 0.406 |
| DK | 154 | 0.242 [-0.171, 0.641] | 0.329 |
| EE | 154 | 0.240 [-0.180, 0.655] | 0.345 |
| EL | 154 | 0.217 [-0.260, 0.721] | 0.455 |
| ES | 154 | 0.221 [-0.238, 0.662] | 0.441 |
| FI | 154 | 0.228 [-0.222, 0.651] | 0.388 |
| FR | 154 | 0.224 [-0.220, 0.670] | 0.437 |
| HR | 154 | 0.230 [-0.222, 0.717] | 0.416 |
| HU | 154 | 0.179 [-0.272, 0.636] | 0.511 |
| IE | 154 | 0.318 [-0.072, 0.707] | 0.188 |
| IT | 154 | 0.241 [-0.211, 0.733] | 0.427 |
| LT | 154 | 0.392 [0.152, 0.650] | 0.006 |
| LU | 154 | 0.256 [-0.165, 0.681] | 0.347 |
| LV | 154 | 0.239 [-0.196, 0.685] | 0.409 |
| MT | 154 | 0.233 [-0.185, 0.640] | 0.381 |
| NL | 154 | 0.230 [-0.368, 0.843] | 0.569 |
| PL | 154 | 0.197 [-0.179, 0.588] | 0.445 |
| PT | 154 | 0.244 [-0.152, 0.654] | 0.342 |
| RO | 154 | 0.179 [-0.345, 0.759] | 0.639 |
| SE | 154 | 0.244 [-0.179, 0.679] | 0.359 |
| SI | 154 | 0.198 [-0.175, 0.606] | 0.443 |
| SK | 154 | 0.268 [-0.149, 0.708] | 0.359 |

## E2: triple interaction (E1 window; severely underpowered)

Estimator in force: **V7**; fallback triggered: False.

| target | estimate [95% bootstrap-t interval] | raw p |
|---|---|---|
| beta_S | -0.491 [-0.912, -0.073] | not tested |
| gamma_B | -0.675 [-1.013, -0.345] | not tested |
| gamma_W | -0.545 [-1.212, 0.142] | not tested |
| gamma_F | 0.066 [-0.583, 0.716] | not tested |
| delta_BF | 0.259 [-0.061, 0.585] | 0.2060 |

| estimator | status | delta_BF [95% interval] | raw p |
|---|---|---|---|
| V7 | ok | 0.259 [-0.061, 0.585] | 0.2060 |
| V3 | ok | 0.276 [-0.050, 0.607] | 0.1695 |
| V0 | ok | 0.449 [0.002, 0.884] | 0.1089 |

## E3: nonlinear ageing (between component, knot at the country median)

Knot and group sizes: {'knot': 0.20003921540299469, 'n_countries_above_knot': 13, 'n_countries_at_or_below_knot': 14}.

| target | estimate [95% bootstrap-t interval] | raw p |
|---|---|---|
| beta_S | -0.326 [-0.673, 0.020] | not tested |
| gamma_W | -0.274 [-1.509, 0.968] | not tested |
| gamma_B_low | 0.277 [0.014, 0.537] | not tested |
| delta_H | -0.203 [-0.710, 0.295] | 0.4283 |

Slopes below / above the knot (descriptive, interval only):

| target | estimate [95% bootstrap-t interval] | raw p |
|---|---|---|
| slope_below | 0.277 [0.014, 0.537] | not tested |
| slope_above | 0.074 [-0.425, 0.562] | not tested |

Terciles of the between component (descriptive, interval only; members {'knot': 0.20003921540299469, 'n_countries_above_knot': 13, 'n_countries_at_or_below_knot': 14, 'tercile_sizes': [9, 9, 9], 'tercile_members': {'low': ['IE', 'SK', 'CY', 'PL', 'LU', 'MT', 'RO', 'CZ', 'NL'], 'mid': ['SI', 'HU', 'LT', 'AT', 'DK', 'ES', 'EE', 'LV', 'FI'], 'top': ['FR', 'BE', 'BG', 'PT', 'HR', 'EL', 'DE', 'SE', 'IT']}}):

| target | estimate [95% bootstrap-t interval] | raw p |
|---|---|---|
| tau_mid | 0.373 [-0.287, 1.034] | not tested |
| tau_top | 0.477 [-0.394, 1.371] | not tested |

## E4a

Info: {'median_country_mean_debt': 57.08076923076923, 'n_high': 13, 'n_low': 14}.

| target | estimate [95% bootstrap-t interval] | raw p |
|---|---|---|
| beta_S | -0.377 [-0.702, -0.055] | not tested |
| delta_debt_between | -0.066 [-0.767, 0.636] | 0.8523 |

Group-specific associations (descriptive, interval only):

| target | estimate [95% bootstrap-t interval] | raw p |
|---|---|---|
| beta_S_D1 | -0.419 [-0.833, -0.001] | not tested |
| beta_S_D0 | -0.353 [-0.867, 0.165] | not tested |

Check: pooled difference -0.065823 vs difference of group estimates -0.065823.

## E4b

Info: {'share_high_rows': 0.48255813953488375}.

| target | estimate [95% bootstrap-t interval] | raw p |
|---|---|---|
| beta_S | -0.312 [-0.604, -0.030] | not tested |
| delta_debt_within_time | 0.163 [-0.440, 0.766] | 0.5695 |

Group-specific associations (descriptive, interval only):

| target | estimate [95% bootstrap-t interval] | raw p |
|---|---|---|
| beta_S_D1 | -0.211 [-0.454, 0.027] | not tested |
| beta_S_D0 | -0.373 [-0.877, 0.119] | not tested |

Check: pooled difference 0.162764 vs difference of group estimates 0.162764.

## E4c

Info: {'n_accession': 13, 'n_eu14': 14}.

| target | estimate [95% bootstrap-t interval] | raw p |
|---|---|---|
| beta_S | -0.396 [-0.663, -0.128] | not tested |
| delta_accession | -0.747 [-1.494, -0.027] | 0.0745 |

Group-specific associations (descriptive, interval only):

| target | estimate [95% bootstrap-t interval] | raw p |
|---|---|---|
| beta_S_D1 | -0.765 [-1.365, -0.187] | not tested |
| beta_S_D0 | -0.018 [-0.304, 0.258] | not tested |

Check: pooled difference -0.746582 vs difference of group estimates -0.746582.

## E4d

Info: {'rows_euro': 356, 'countries_never_euro': 8}.

| target | estimate [95% bootstrap-t interval] | raw p |
|---|---|---|
| beta_S | -0.380 [-0.696, -0.064] | not tested |
| delta_euro | 0.074 [-0.561, 0.724] | 0.8196 |

Group-specific associations (descriptive, interval only):

| target | estimate [95% bootstrap-t interval] | raw p |
|---|---|---|
| beta_S_D1 | -0.339 [-0.721, 0.043] | not tested |
| beta_S_D0 | -0.412 [-0.949, 0.109] | not tested |

Check: pooled difference 0.073804 vs difference of group estimates 0.073804.

Mundlak split of the euro dummy (descriptive, interval only):

| target | estimate [95% bootstrap-t interval] | raw p |
|---|---|---|
| delta_euro_between | 0.828 [-0.146, 1.810] | not tested |
| delta_euro_within | -1.497 [-2.282, -0.690] | not tested |

## E6: country typology (descriptive only; not causal; no inference on membership)

Features (country means over the confirmatory rows; z-scored over the 27 countries): mean_debt (debt_gdp_lag, % of GDP); mean_interest (sec_interest_d41pay, % of GDP); mean_capb (capb, pp of potential GDP); iqr_capb (capb, pp of potential GDP); mean_ageing (olddep1_lag, persons 65+ per 100 aged 15-64).

| k | silhouette | smallest cluster | inertia | admissible |
|---|---|---|---|---|
| 2 | 0.431 | 3 | 88.44 | True |
| 3 | 0.258 | 3 | 64.17 | True |
| 4 | 0.264 | 3 | 51.70 | True |
| 5 | 0.267 | 3 | 41.42 | True |
| 6 | 0.270 | 3 | 34.18 | True |

Chosen k = 2 (rule: highest mean silhouette among k with smallest cluster >= 3 countries; ties to the smaller k); silhouette 0.431 (weak structure, Kaufman-Rousseeuw scale).
Stability over 100 single-start seeds: share equal to the reference partition 0.16; share reaching the best inertia 0.16; ARI min -0.015, median 0.218; ARI Ward vs reference 1.000.

| cluster | n | members | mean_debt | mean_interest | mean_capb | iqr_capb | mean_ageing |
|---|---|---|---|---|---|---|---|
| 1 | 24 | AT, BG, CY, CZ, DE, DK, EE, ES, FI, FR, HR, HU, IE, LT, LU, LV, MT, NL, PL, PT, RO, SE, SI, SK | 50.34 | 2.16 | -0.23 | 2.81 | 23.90 |
| 2 | 3 | BE, EL, IT | 121.07 | 5.13 | 1.96 | 4.90 | 28.21 |

Cross-tab with eu_group: {'1': {'EU-14': 11, 'accession': 13}, '2': {'EU-14': 3, 'accession': 0}}

Cross-tab with euro_member_last_year: {'1': {'euro': 16, 'non-euro': 8}, '2': {'euro': 3, 'non-euro': 0}}

Cross-tab with e4a_debt_split: {'1': {'high debt': 10, 'low debt': 14}, '2': {'high debt': 3, 'low debt': 0}}

## Not run

* E5: not run: data not acquired (CPDS, DPI), no download approved
* E7: not run: not chosen (the single optional extension is the researcher's Week-13 choice)
* E4-democratic-age: not run: data not acquired (V-Dem), no download approved

## Provenance

* extract hash `2fcf20d4ca687f613d6743214b7be176ceb638b483f513eeed005bd1f73a5bb4`; versions {'numpy': '2.4.4', 'pandas': '3.0.2', 'scipy': '1.17.1'}
* code and spec hashes: exploratory.py `2b9b579e208d`; m1.py `01fd7b728e35`; power_variants.py `f0bdd1105e79`; power.py `838b9535c474`; secondary.py `54b5d50de775`; docs/exploratory_spec.md `85e08684e390`; config/registry/exploratory.toml `d084cee6d3ad`
