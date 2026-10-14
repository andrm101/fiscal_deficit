# Predictive module: rolling-origin forecasts of the next-year change in CAPB

Specification: `docs/predictive_spec.md` (dated 2026-10-13, SHA-256 `9901f170e6465448...`). Code: `src/models/py/predictive.py` and `predictive_report.py` (SHA-256 of `predictive.py` `9a703d6c5f37c741...`). Target: `capb_{T+1} - capb_T` in pp of potential GDP (AMECO `UBLGBP`, Spring 2026 vintage), one-step-ahead, expanding window, origins 2008-2020 (block P, 351 forecasts) and 2021-2022 (block H, 54 forecasts, descriptive). **Predictive and non-causal.** All numbers are pseudo-out-of-sample on final-vintage data, not real-time forecasts. SHAP: not run: not installed.

## 0. Deviations from the specification

1. The report assembly, figures and the command line live in `src/models/py/predictive_report.py` (a second new file); the specification names only `predictive.py`. No behaviour changes.
2. Specification section 4.3 and section 12 quote a 71.0 per cent agreement of the strict schedule rule with ETAD `sche_date`. That figure divided by all 248 calendar rows and so counted the 45 elections without a comparison as misses. The correct share among the 203 elections that have a previous election, a term length and a `sche_date` is the value printed under Status below (86.7 per cent). The rule itself, and the decision to accept it as measurement error, are unchanged; the model card uses the corrected figure.
3. Czechia has no in-calendar election before 1996, so its origin-1995 political features are undefined; that origin is unused (the first usable forecast year is 1997), so no training or test row is lost.
4. Section 3 of the specification says block H gets point metrics only; section 7 asks for cluster-bootstrap intervals of the accuracy metrics for both blocks. H intervals are computed and labelled indicative; no test is run on H.
5. Leave-one-country-out: the held-out country's own country means use its complete rows with forecast year <= T (its feature history up to the origin, the same window as a training row), not including the test row itself, to match the main-run rule of section 4.4.
6. The same bootstrap index matrix (seed key (6000, 2, k), k = 0 block P, 1 block H, 2 LOCO) is reused across all statistics of a block, so model comparisons are paired.
7. Hyperparameter ties (smaller `alpha`, `l1_ratio` order etc.) are resolved exactly as in section 5; the iteration search for P1b uses a 300-iteration cap with learning rate 0.05 as specified.

## 1. Status

| Item | Status |
|---|---|
| SHAP | not run: not installed (permutation importance and ALE used instead) |
| LightGBM / XGBoost | not installed; scikit-learn HistGradientBoostingRegressor used |
| P1c (GAM) | run (statsmodels GLMGam), descriptive |
| Oracle diagnostics | complete (60 fits, 0 failed) |
| Leave-one-country-out | complete (1404 fits, 0 failed) |
| Binary event | complete (60 fits, 0 failed) |
| Block H | complete (32 fits, 0 failed) |
| Block P | complete (208 fits, 0 failed) |

Setup checks: extract SHA-256 `2fcf20d4ca687f613d6743214b7be176ceb638b483f513eeed005bd1f73a5bb4`; gold build with end 2023 has 783 rows; last observed AMECO year 2025. Schedule rule agreement (election dates only): `date(previous) + termlength(previous)` is within 31 days of ETAD `sche_date` in 86.7% of 203 elections. Frozen files unchanged: 40 of 40 files hash-identical to docs/freeze_manifest.json.

## 2. Accuracy, block P (origins 2008-2020; forecast years 2009-2021; 351 forecasts)

RMSE and MAE in pp of potential GDP; ratio = RMSE(model)/RMSE(P0); skill = 1 - MSE(model)/MSE(P0); intervals are 95% country-cluster bootstrap (27 clusters, B = 9,999).

| Model | n | RMSE | RMSE 95% CI | MAE | MAE 95% CI | Ratio to P0 | Ratio 95% CI | Skill | Skill 95% CI |
|---|---|---|---|---|---|---|---|---|---|
| P0 | 351 | 2.639 | [1.831, 3.475] | 1.603 | [1.264, 2.012] | 1.000 | [1.000, 1.000] | 0.000 | [0.000, 0.000] |
| P0b | 351 | 3.989 | [2.606, 5.321] | 2.354 | [1.805, 3.025] | 1.512 | [1.406, 1.587] | -1.285 | [-1.519, -0.975] |
| P1a-B0 | 351 | 2.626 | [1.848, 3.457] | 1.639 | [1.314, 2.036] | 0.995 | [0.961, 1.027] | 0.010 | [-0.054, 0.076] |
| P1a-B1 | 351 | 2.588 | [1.822, 3.431] | 1.636 | [1.310, 2.040] | 0.981 | [0.926, 1.025] | 0.038 | [-0.051, 0.142] |
| P1a-B1-POOL | 351 | 2.568 | [1.795, 3.417] | 1.602 | [1.280, 1.998] | 0.973 | [0.922, 1.010] | 0.053 | [-0.019, 0.150] |
| P1a-B2 | 351 | 2.586 | [1.822, 3.435] | 1.635 | [1.318, 2.033] | 0.980 | [0.931, 1.016] | 0.040 | [-0.031, 0.133] |
| P1a-B2-POOL | 351 | 2.572 | [1.787, 3.436] | 1.609 | [1.287, 2.007] | 0.975 | [0.925, 1.008] | 0.050 | [-0.016, 0.145] |
| P1a-B2d | 351 | 2.563 | [1.798, 3.410] | 1.610 | [1.291, 2.008] | 0.971 | [0.919, 1.010] | 0.056 | [-0.019, 0.156] |
| P1a-B2f | 351 | 2.581 | [1.812, 3.427] | 1.632 | [1.316, 2.029] | 0.978 | [0.925, 1.016] | 0.044 | [-0.032, 0.144] |
| P1a-B2o | 351 | 2.587 | [1.822, 3.436] | 1.634 | [1.316, 2.032] | 0.980 | [0.932, 1.016] | 0.039 | [-0.032, 0.131] |
| P1a-B2p | 351 | 2.573 | [1.811, 3.420] | 1.626 | [1.307, 2.021] | 0.975 | [0.924, 1.014] | 0.049 | [-0.029, 0.147] |
| P1b-B0 | 351 | 2.636 | [1.840, 3.471] | 1.626 | [1.295, 2.027] | 0.999 | [0.981, 1.016] | 0.002 | [-0.033, 0.038] |
| P1b-B1 | 351 | 2.611 | [1.868, 3.442] | 1.651 | [1.340, 2.038] | 0.989 | [0.947, 1.034] | 0.021 | [-0.069, 0.103] |
| P1b-B1-POOL | 351 | 2.636 | [1.907, 3.446] | 1.658 | [1.343, 2.041] | 0.999 | [0.963, 1.053] | 0.002 | [-0.110, 0.072] |
| P1b-B2 | 351 | 2.640 | [1.879, 3.482] | 1.659 | [1.338, 2.057] | 1.000 | [0.969, 1.037] | -0.001 | [-0.076, 0.061] |
| P1b-B2-POOL | 351 | 2.642 | [1.885, 3.478] | 1.639 | [1.312, 2.041] | 1.001 | [0.961, 1.045] | -0.002 | [-0.093, 0.076] |
| P1b-B2d | 351 | 2.631 | [1.881, 3.460] | 1.659 | [1.349, 2.044] | 0.997 | [0.966, 1.035] | 0.006 | [-0.072, 0.068] |
| P1b-B2f | 351 | 2.639 | [1.884, 3.475] | 1.660 | [1.340, 2.060] | 1.000 | [0.967, 1.040] | 0.000 | [-0.082, 0.065] |
| P1b-B2o | 351 | 2.656 | [1.893, 3.491] | 1.675 | [1.352, 2.073] | 1.007 | [0.981, 1.044] | -0.013 | [-0.090, 0.038] |
| P1b-B2p | 351 | 2.617 | [1.865, 3.455] | 1.656 | [1.345, 2.046] | 0.992 | [0.952, 1.032] | 0.016 | [-0.065, 0.094] |
| P1c-B1 | 351 | 2.692 | [1.868, 3.632] | 1.685 | [1.352, 2.106] | 1.020 | [0.926, 1.086] | -0.041 | [-0.180, 0.143] |
| P1c-B2 | 351 | 2.718 | [1.927, 3.619] | 1.755 | [1.423, 2.173] | 1.030 | [0.952, 1.095] | -0.060 | [-0.199, 0.094] |

## 3. Diebold-Mariano tests against persistence and incremental value (the Holm family)

Two-sided DM with the Harvey-Leybourne-Newbold correction on the 13 yearly cross-country mean squared-loss differentials (positive = first-named model better), Student t with 12 df. Holm over exactly these six p-values. Companion: country-cluster paired bootstrap of the MSE difference and of the relative MSE reduction.

| Comparison | Mean loss diff (pp^2) | DM-HLN stat | raw p | Holm p | Reading | MSE diff | MSE diff 95% CI | Rel. MSE reduction | Rel. red. 95% CI |
|---|---|---|---|---|---|---|---|---|---|
| P1a-B1 vs P0 | 0.2673 | 0.693 | 0.5018 | 1.0000 | not distinguishable from persistence | 0.2673 | [-0.2835, 1.0040] | 0.0384 | [-0.0508, 0.1424] |
| P1b-B1 vs P0 | 0.1457 | 0.783 | 0.4485 | 1.0000 | not distinguishable from persistence | 0.1457 | [-0.3437, 0.7827] | 0.0209 | [-0.0694, 0.1034] |
| P1a-B2 vs P0 | 0.2789 | 0.895 | 0.3886 | 1.0000 | not distinguishable from persistence | 0.2789 | [-0.2015, 0.9293] | 0.0400 | [-0.0314, 0.1328] |
| P1b-B2 vs P0 | -0.0066 | -0.044 | 0.9657 | 1.0000 | not distinguishable from persistence | -0.0066 | [-0.3969, 0.4424] | -0.0009 | [-0.0760, 0.0606] |
| P1a: B2 vs B1 | 0.0115 | 0.072 | 0.9439 | 1.0000 | no evidence of improvement | 0.0115 | [-0.1507, 0.1705] | 0.0017 | [-0.0236, 0.0341] |
| P1b: B2 vs B1 | -0.1522 | -1.428 | 0.1789 | 1.0000 | no evidence of improvement | -0.1522 | [-0.3729, 0.0101] | -0.0223 | [-0.0538, 0.0022] |

Lag-1 autocorrelation of the yearly differentials (descriptive): P1a-B1 vs P0: 0.21; P1b-B1 vs P0: 0.15; P1a-B2 vs P0: 0.36; P1b-B2 vs P0: 0.23; P1a: B2 vs B1: -0.56; P1b: B2 vs B1: 0.04.

Sensitivity (descriptive, unadjusted): the same six DM tests without forecast years 2020-2021 (11 yearly differentials, t(10)):

| Comparison | Mean loss diff | DM-HLN | raw p | Holm p (re-adjusted over the six) |
|---|---|---|---|---|
| P1a-B1 vs P0 | 0.3799 | 0.994 | 0.3437 | 1.0000 |
| P1b-B1 vs P0 | 0.1717 | 0.813 | 0.4353 | 1.0000 |
| P1a-B2 vs P0 | 0.2660 | 0.735 | 0.4789 | 1.0000 |
| P1b-B2 vs P0 | -0.0598 | -0.352 | 0.7325 | 1.0000 |
| P1a: B2 vs B1 | -0.1139 | -2.553 | 0.0287 | 0.1722 |
| P1b: B2 vs B1 | -0.2315 | -2.196 | 0.0528 | 0.2639 |

Absolute-loss DM (descriptive, outside the family): P1a-B1 vs P0: mean -0.0331, p 0.5721; P1b-B1 vs P0: mean -0.0478, p 0.1229; P1a-B2 vs P0: mean -0.0321, p 0.4137; P1b-B2 vs P0: mean -0.0559, p 0.0867; P1a: B2 vs B1: mean 0.0010, p 0.9781; P1b: B2 vs B1: mean -0.0081, p 0.4988.

Reading of comparisons 5-6 (section 9 of the specification): (R3) no evidence that the political and demographic block improves out-of-sample prediction beyond the lagged fiscal-and-macro baseline, in 13 forecast years; the test can only detect a mean loss differential of about 0.6 SD of the yearly differential (50 per cent power) to 0.85 SD (80 per cent power).

### Descriptive decomposition and every model against persistence (unadjusted)

| Comparison | Mean loss diff | DM-HLN | raw p | Rel. MSE reduction | 95% CI |
|---|---|---|---|---|---|
| P1a: B2p vs B1 | 0.0744 | 0.489 | 0.6335 | 0.0111 | [-0.0084, 0.0386] |
| P1a: B2d vs B1 | 0.1257 | 0.858 | 0.4079 | 0.0188 | [0.0022, 0.0482] |
| P1a: B2o vs B1 | 0.0062 | 0.039 | 0.9698 | 0.0009 | [-0.0244, 0.0328] |
| P1a: B2f vs B1 | 0.0377 | 0.236 | 0.8174 | 0.0056 | [-0.0196, 0.0411] |
| P1a: B2o vs B2 | -0.0053 | -0.724 | 0.4832 | -0.0008 | [-0.0033, 0.0009] |
| P1a: B2f vs B2 | 0.0262 | 1.243 | 0.2375 | 0.0039 | [-0.0153, 0.0245] |
| P1b: B2p vs B1 | -0.0309 | -0.593 | 0.5643 | -0.0045 | [-0.0140, 0.0096] |
| P1b: B2d vs B1 | -0.1010 | -1.055 | 0.3121 | -0.0148 | [-0.0426, 0.0035] |
| P1b: B2o vs B1 | -0.2377 | -2.081 | 0.0596 | -0.0349 | [-0.0833, -0.0035] |
| P1b: B2f vs B1 | -0.1430 | -1.441 | 0.1752 | -0.0210 | [-0.0510, 0.0024] |
| P1b: B2o vs B2 | -0.0855 | -1.746 | 0.1063 | -0.0123 | [-0.0316, 0.0014] |
| P1b: B2f vs B2 | 0.0092 | 0.372 | 0.7167 | 0.0013 | [-0.0107, 0.0092] |

| Model vs P0 | Mean loss diff | DM-HLN | raw p |
|---|---|---|---|
| P0b | -8.9472 | -2.922 | 0.0128 |
| P1a-B0 | 0.0685 | 0.227 | 0.8243 |
| P1a-B1 | 0.2673 | 0.693 | 0.5018 |
| P1a-B1-POOL | 0.3722 | 0.900 | 0.3860 |
| P1a-B2 | 0.2789 | 0.895 | 0.3886 |
| P1a-B2-POOL | 0.3497 | 1.224 | 0.2444 |
| P1a-B2d | 0.3930 | 1.221 | 0.2456 |
| P1a-B2f | 0.3051 | 0.959 | 0.3567 |
| P1a-B2o | 0.2736 | 0.868 | 0.4025 |
| P1a-B2p | 0.3418 | 1.006 | 0.3344 |
| P1b-B0 | 0.0165 | 0.086 | 0.9330 |
| P1b-B1 | 0.1457 | 0.783 | 0.4485 |
| P1b-B1-POOL | 0.0135 | 0.027 | 0.9788 |
| P1b-B2 | -0.0066 | -0.044 | 0.9657 |
| P1b-B2-POOL | -0.0169 | -0.034 | 0.9733 |
| P1b-B2d | 0.0447 | 0.281 | 0.7836 |
| P1b-B2f | 0.0026 | 0.017 | 0.9870 |
| P1b-B2o | -0.0920 | -0.605 | 0.5567 |
| P1b-B2p | 0.1147 | 0.680 | 0.5097 |
| P1c-B1 | -0.2834 | -0.380 | 0.7109 |
| P1c-B2 | -0.4213 | -0.805 | 0.4365 |

## 4. Calibration (block P; realised on forecast, `y = a + b * yhat`; 95% country-cluster bootstrap intervals)

| Model | Slope b | b 95% CI | Intercept a | a 95% CI | Reading |
|---|---|---|---|---|---|
| P0 | n/a |  | n/a |  | constant forecast |
| P0b | -0.148 | [-0.266, -0.008] | -0.118 | [-0.212, -0.024] | over-dispersed forecasts (slope below 1) |
| P1a-B0 | 0.580 | [0.193, 1.152] | 0.011 | [-0.141, 0.198] | compatible with calibration |
| P1a-B1 | 0.784 | [0.331, 1.393] | -0.229 | [-0.401, -0.101] | compatible with calibration |
| P1a-B1-POOL | 0.866 | [0.386, 1.422] | -0.109 | [-0.238, 0.013] | compatible with calibration |
| P1a-B2 | 0.817 | [0.341, 1.458] | -0.169 | [-0.323, -0.040] | compatible with calibration |
| P1a-B2-POOL | 0.964 | [0.354, 1.620] | -0.133 | [-0.267, -0.015] | compatible with calibration |
| P1a-B2d | 0.944 | [0.421, 1.657] | -0.171 | [-0.336, -0.028] | compatible with calibration |
| P1a-B2f | 0.826 | [0.361, 1.439] | -0.173 | [-0.332, -0.042] | compatible with calibration |
| P1a-B2o | 0.811 | [0.337, 1.448] | -0.168 | [-0.321, -0.040] | compatible with calibration |
| P1a-B2p | 0.868 | [0.396, 1.478] | -0.197 | [-0.353, -0.067] | compatible with calibration |
| P1b-B0 | 0.519 | [0.127, 1.055] | -0.025 | [-0.140, 0.116] | compatible with calibration |
| P1b-B1 | 0.680 | [0.180, 1.169] | -0.160 | [-0.288, -0.041] | compatible with calibration |
| P1b-B1-POOL | 0.520 | [0.099, 0.988] | -0.117 | [-0.206, -0.035] | over-dispersed forecasts (slope below 1) |
| P1b-B2 | 0.510 | [0.004, 1.177] | -0.122 | [-0.228, -0.011] | compatible with calibration |
| P1b-B2-POOL | 0.491 | [0.094, 0.940] | -0.110 | [-0.200, -0.025] | over-dispersed forecasts (slope below 1) |
| P1b-B2d | 0.562 | [0.110, 1.003] | -0.118 | [-0.225, -0.004] | compatible with calibration |
| P1b-B2f | 0.528 | [0.036, 1.152] | -0.132 | [-0.244, -0.022] | compatible with calibration |
| P1b-B2o | 0.378 | [-0.070, 0.960] | -0.114 | [-0.213, -0.010] | over-dispersed forecasts (slope below 1) |
| P1b-B2p | 0.661 | [0.136, 1.169] | -0.154 | [-0.281, -0.035] | compatible with calibration |
| P1c-B1 | 0.484 | [0.063, 1.016] | -0.293 | [-0.549, -0.103] | compatible with calibration |
| P1c-B2 | 0.381 | [0.040, 0.799] | -0.197 | [-0.363, -0.064] | over-dispersed forecasts (slope below 1) |

## 5. Error by country, era and regime (block P; RMSE / MAE in pp; n per cell)

### By era (forecast year)

| Era | Model | n | RMSE | MAE |
|---|---|---|---|---|
| 2009-2015 | P0 | 189 | 3.082 | 1.771 |
| 2009-2015 | P1a-B1 | 189 | 2.965 | 1.720 |
| 2009-2015 | P1a-B2 | 189 | 2.991 | 1.758 |
| 2009-2015 | P1b-B1 | 189 | 3.033 | 1.785 |
| 2009-2015 | P1b-B2 | 189 | 3.073 | 1.799 |
| 2016-2021 | P0 | 162 | 2.001 | 1.406 |
| 2016-2021 | P1a-B1 | 162 | 2.062 | 1.537 |
| 2016-2021 | P1a-B2 | 162 | 2.012 | 1.491 |
| 2016-2021 | P1b-B1 | 162 | 2.011 | 1.493 |
| 2016-2021 | P1b-B2 | 162 | 2.021 | 1.495 |

Pre-2008: no test rows (first forecast year 2009). Block H (2022-2023) is in section 6.

### By regime

| Regime | Model | n | RMSE | MAE |
|---|---|---|---|---|
| euro (at origin) | P0 | 230 | 2.994 | 1.745 |
| euro (at origin) | P1a-B1 | 230 | 2.954 | 1.815 |
| euro (at origin) | P1a-B2 | 230 | 2.946 | 1.805 |
| euro (at origin) | P1b-B1 | 230 | 2.957 | 1.815 |
| euro (at origin) | P1b-B2 | 230 | 2.983 | 1.813 |
| non-euro (at origin) | P0 | 121 | 1.778 | 1.331 |
| non-euro (at origin) | P1a-B1 | 121 | 1.684 | 1.295 |
| non-euro (at origin) | P1a-B2 | 121 | 1.702 | 1.311 |
| non-euro (at origin) | P1b-B1 | 121 | 1.779 | 1.338 |
| non-euro (at origin) | P1b-B2 | 121 | 1.819 | 1.365 |
| known election exposure Wk_next >= 0.5 | P0 | 76 | 2.795 | 1.583 |
| known election exposure Wk_next >= 0.5 | P1a-B1 | 76 | 2.803 | 1.703 |
| known election exposure Wk_next >= 0.5 | P1a-B2 | 76 | 2.784 | 1.657 |
| known election exposure Wk_next >= 0.5 | P1b-B1 | 76 | 2.827 | 1.744 |
| known election exposure Wk_next >= 0.5 | P1b-B2 | 76 | 2.825 | 1.706 |
| Wk_next < 0.5 | P0 | 275 | 2.594 | 1.608 |
| Wk_next < 0.5 | P1a-B1 | 275 | 2.525 | 1.617 |
| Wk_next < 0.5 | P1a-B2 | 275 | 2.528 | 1.629 |
| Wk_next < 0.5 | P1b-B1 | 275 | 2.548 | 1.625 |
| Wk_next < 0.5 | P1b-B2 | 275 | 2.587 | 1.646 |
| ex-post: realised early-election exposure W_E > 0 (not knowable) | P0 | 53 | 4.564 | 2.744 |
| ex-post: realised early-election exposure W_E > 0 (not knowable) | P1a-B1 | 53 | 4.521 | 2.800 |
| ex-post: realised early-election exposure W_E > 0 (not knowable) | P1a-B2 | 53 | 4.535 | 2.818 |
| ex-post: realised early-election exposure W_E > 0 (not knowable) | P1b-B1 | 53 | 4.572 | 2.864 |
| ex-post: realised early-election exposure W_E > 0 (not knowable) | P1b-B2 | 53 | 4.598 | 2.866 |
| ex-post: W_E = 0 | P0 | 298 | 2.121 | 1.400 |
| ex-post: W_E = 0 | P1a-B1 | 298 | 2.062 | 1.429 |
| ex-post: W_E = 0 | P1a-B2 | 298 | 2.053 | 1.424 |
| ex-post: W_E = 0 | P1b-B1 | 298 | 2.077 | 1.435 |
| ex-post: W_E = 0 | P1b-B2 | 298 | 2.110 | 1.444 |

### Pre-listed sensitivities of the pooled table

| Sample | Model | n | RMSE | MAE |
|---|---|---|---|---|
| all | P0 | 351 | 2.639 | 1.603 |
| all | P1a-B1 | 351 | 2.588 | 1.636 |
| all | P1a-B2 | 351 | 2.586 | 1.635 |
| all | P1b-B1 | 351 | 2.611 | 1.651 |
| all | P1b-B2 | 351 | 2.640 | 1.659 |
| excluding IE 2010-2011 | P0 | 349 | 2.246 | 1.506 |
| excluding IE 2010-2011 | P1a-B1 | 349 | 2.185 | 1.539 |
| excluding IE 2010-2011 | P1a-B2 | 349 | 2.183 | 1.538 |
| excluding IE 2010-2011 | P1b-B1 | 349 | 2.211 | 1.554 |
| excluding IE 2010-2011 | P1b-B2 | 349 | 2.242 | 1.562 |
| excluding 2020-2021 | P0 | 297 | 2.594 | 1.467 |
| excluding 2020-2021 | P1a-B1 | 297 | 2.519 | 1.478 |
| excluding 2020-2021 | P1a-B2 | 297 | 2.542 | 1.507 |
| excluding 2020-2021 | P1b-B1 | 297 | 2.560 | 1.511 |
| excluding 2020-2021 | P1b-B2 | 297 | 2.605 | 1.528 |

### By country (RMSE, 13 forecasts each)

| Country | P0 | P1a-B1 | P1a-B2 | P1b-B1 | P1b-B2 |
|---|---|---|---|---|---|
| AT | 1.47 | 1.45 | 1.41 | 1.48 | 1.52 |
| BE | 1.36 | 1.48 | 1.46 | 1.43 | 1.38 |
| BG | 2.46 | 2.29 | 2.25 | 2.37 | 2.40 |
| CY | 4.94 | 4.10 | 4.18 | 4.24 | 4.52 |
| CZ | 1.41 | 1.39 | 1.38 | 1.49 | 1.47 |
| DE | 1.51 | 1.52 | 1.54 | 1.51 | 1.48 |
| DK | 1.78 | 1.56 | 1.65 | 1.57 | 1.68 |
| EE | 2.20 | 1.92 | 1.98 | 2.17 | 2.24 |
| EL | 4.75 | 4.71 | 4.63 | 4.54 | 4.60 |
| ES | 2.01 | 2.39 | 2.31 | 2.28 | 2.39 |
| FI | 1.15 | 1.70 | 1.68 | 1.97 | 1.88 |
| FR | 0.84 | 1.32 | 1.21 | 1.37 | 1.33 |
| HR | 1.52 | 1.25 | 1.38 | 1.55 | 1.53 |
| HU | 1.73 | 1.84 | 1.72 | 1.91 | 1.96 |
| IE | 7.82 | 7.88 | 7.91 | 7.87 | 7.91 |
| IT | 1.56 | 2.05 | 1.79 | 1.86 | 1.80 |
| LT | 2.15 | 1.88 | 2.06 | 1.95 | 1.98 |
| LU | 1.65 | 1.49 | 1.54 | 1.52 | 1.48 |
| LV | 1.97 | 2.09 | 2.00 | 1.97 | 1.89 |
| MT | 2.11 | 2.28 | 2.23 | 2.21 | 2.12 |
| NL | 1.15 | 1.09 | 1.11 | 1.17 | 1.13 |
| PL | 1.77 | 1.63 | 1.82 | 1.69 | 1.73 |
| PT | 2.69 | 2.60 | 2.51 | 2.63 | 2.69 |
| RO | 1.65 | 1.84 | 1.76 | 1.84 | 1.87 |
| SE | 0.89 | 0.85 | 0.85 | 0.76 | 0.73 |
| SI | 3.16 | 2.74 | 2.86 | 2.96 | 2.97 |
| SK | 1.68 | 1.70 | 1.64 | 1.70 | 1.69 |

## 6. Block H: forecast years 2022-2023 (descriptive, never pooled with P, no test)

Origins 2021 and 2022, 54 forecasts; the same fixed procedure. Intervals are country-cluster bootstrap intervals and are indicative only (two forecast years).

| Model | n | RMSE | RMSE 95% CI | MAE | Ratio to P0 | Ratio 95% CI | RMSE 2022 | RMSE 2023 |
|---|---|---|---|---|---|---|---|---|
| P0 | 54 | 1.579 | [1.213, 1.937] | 1.217 | 1.000 | [1.000, 1.000] | 1.597 | 1.560 |
| P0b | 54 | 2.555 | [1.894, 3.209] | 1.972 | 1.619 | [1.391, 1.821] | 2.821 | 2.258 |
| P1a-B0 | 54 | 1.381 | [1.055, 1.709] | 1.086 | 0.875 | [0.773, 0.983] | 1.332 | 1.428 |
| P1a-B1 | 54 | 1.491 | [1.144, 1.832] | 1.135 | 0.945 | [0.909, 0.981] | 1.495 | 1.488 |
| P1a-B1-POOL | 54 | 1.417 | [1.094, 1.740] | 1.081 | 0.897 | [0.825, 0.982] | 1.364 | 1.467 |
| P1a-B2 | 54 | 1.491 | [1.144, 1.832] | 1.135 | 0.945 | [0.909, 0.981] | 1.495 | 1.488 |
| P1a-B2-POOL | 54 | 1.417 | [1.094, 1.740] | 1.081 | 0.897 | [0.825, 0.982] | 1.364 | 1.467 |
| P1a-B2d | 54 | 1.491 | [1.144, 1.832] | 1.135 | 0.945 | [0.909, 0.981] | 1.495 | 1.488 |
| P1a-B2f | 54 | 1.491 | [1.144, 1.832] | 1.135 | 0.945 | [0.909, 0.981] | 1.495 | 1.488 |
| P1a-B2o | 54 | 1.491 | [1.144, 1.832] | 1.135 | 0.945 | [0.909, 0.981] | 1.495 | 1.488 |
| P1a-B2p | 54 | 1.491 | [1.144, 1.832] | 1.135 | 0.945 | [0.909, 0.981] | 1.495 | 1.488 |
| P1b-B0 | 54 | 1.509 | [1.219, 1.813] | 1.218 | 0.956 | [0.873, 1.071] | 1.537 | 1.480 |
| P1b-B1 | 54 | 1.412 | [1.068, 1.746] | 1.078 | 0.894 | [0.818, 0.965] | 1.400 | 1.423 |
| P1b-B1-POOL | 54 | 1.500 | [1.204, 1.797] | 1.180 | 0.950 | [0.858, 1.069] | 1.514 | 1.486 |
| P1b-B2 | 54 | 1.441 | [1.094, 1.782] | 1.108 | 0.913 | [0.826, 0.995] | 1.464 | 1.419 |
| P1b-B2-POOL | 54 | 1.500 | [1.204, 1.797] | 1.180 | 0.950 | [0.858, 1.069] | 1.514 | 1.486 |
| P1b-B2d | 54 | 1.432 | [1.088, 1.769] | 1.105 | 0.907 | [0.820, 0.992] | 1.445 | 1.419 |
| P1b-B2f | 54 | 1.441 | [1.094, 1.782] | 1.108 | 0.913 | [0.826, 0.995] | 1.464 | 1.419 |
| P1b-B2o | 54 | 1.441 | [1.094, 1.782] | 1.108 | 0.913 | [0.826, 0.995] | 1.464 | 1.419 |
| P1b-B2p | 54 | 1.412 | [1.068, 1.746] | 1.078 | 0.894 | [0.818, 0.965] | 1.400 | 1.423 |
| P1c-B1 | 54 | 1.473 | [1.085, 1.855] | 1.121 | 0.933 | [0.777, 1.106] | 1.369 | 1.571 |
| P1c-B2 | 54 | 1.997 | [1.600, 2.406] | 1.615 | 1.265 | [1.074, 1.508] | 2.157 | 1.822 |

Calibration slopes in H (point values): P1a-B1: 1.58; P1a-B2: 1.58; P1b-B1: 0.93; P1b-B2: 0.76.

## 7. Oracle diagnostics (look-ahead; NOT forecasts and never evidence of predictive value)

B2o replaces `Wk_next`, `Wk_now` by the same quantities built from ETAD `sche_date` (an ex-post record); B2f adds the frozen realised `W_S`, `W_E`, `W_U` of the forecast year. Both leak the future by construction.

| Model | RMSE (pp) | Ratio to P0 | Skill vs P0 |
|---|---|---|---|
| P1a-B2 | 2.586 | 0.980 | 0.040 |
| P1a-B2o | 2.587 | 0.980 | 0.039 |
| P1a-B2f | 2.581 | 0.978 | 0.044 |
| P1b-B2 | 2.640 | 1.000 | -0.001 |
| P1b-B2o | 2.656 | 1.007 | -0.013 |
| P1b-B2f | 2.639 | 1.000 | 0.000 |

| Comparison | Mean loss diff | raw p (unadjusted) | Rel. MSE reduction | 95% CI |
|---|---|---|---|---|
| P1a: B2o vs B1 | 0.0062 | 0.9698 | 0.0009 | [-0.0244, 0.0328] |
| P1a: B2f vs B1 | 0.0377 | 0.8174 | 0.0056 | [-0.0196, 0.0411] |
| P1a: B2o vs B2 | -0.0053 | 0.4832 | -0.0008 | [-0.0033, 0.0009] |
| P1a: B2f vs B2 | 0.0262 | 0.2375 | 0.0039 | [-0.0153, 0.0245] |
| P1b: B2o vs B1 | -0.2377 | 0.0596 | -0.0349 | [-0.0833, -0.0035] |
| P1b: B2f vs B1 | -0.1430 | 0.1752 | -0.0210 | [-0.0510, 0.0024] |
| P1b: B2o vs B2 | -0.0855 | 0.1063 | -0.0123 | [-0.0316, 0.0014] |
| P1b: B2f vs B2 | 0.0092 | 0.7167 | 0.0013 | [-0.0107, 0.0092] |

Inflation reading: P1a-B2o RMSE 2.587 against 2.586 for P1a-B2 (ratio 1.000); P1a-B2f RMSE 2.581 against 2.586 for P1a-B2 (ratio 0.998); P1b-B2o RMSE 2.656 against 2.640 for P1b-B2 (ratio 1.006); P1b-B2f RMSE 2.639 against 2.640 for P1b-B2 (ratio 0.999). No inflation is visible: the leaking sets do not lower RMSE by more than 1% relative to the strict B2 in either model class (so the strict calendar rule is not hiding a gain that the leaked information would reveal; the political columns carry little signal either way).

## 8. Leave-one-country-out stress (descriptive, outside the family)

Each country's rows are removed from fitting, standardisation, the other countries' means and the inner validation at every origin 2008-2020; the held-out country's own training-window feature history supplies its country means.

| Model | LOCO RMSE | LOCO MAE | Ratio to P0 | Main-run RMSE | Ratio to main | DM-HLN vs P0 | raw p | Share of countries below P0 | Largest deterioration |
|---|---|---|---|---|---|---|---|---|---|
| P1a-B1 (LOCO) | 2.578 | 1.634 | 0.977 | 2.588 | 0.996 | 0.35 | 0.731 | 0.59 | RO, FR, ES, FI, SE |
| P1a-B2 (LOCO) | 2.565 | 1.636 | 0.972 | 2.586 | 0.992 | 0.45 | 0.658 | 0.63 | FI, FR, ES, SE, HU |
| P1b-B1 (LOCO) | 2.661 | 1.697 | 1.008 | 2.611 | 1.019 | -0.63 | 0.540 | 0.52 | FI, FR, HU, SE, CY |
| P1b-B2 (LOCO) | 2.656 | 1.692 | 1.006 | 2.640 | 1.006 | -0.71 | 0.492 | 0.52 | FI, SE, FR, CY, LU |

- P1a-B1 (LOCO): per-country LOCO/main RMSE ratio ranges from 0.98 to 1.04; per-country LOCO/P0 ratio from 0.82 to 1.60.
- P1a-B2 (LOCO): per-country LOCO/main RMSE ratio ranges from 0.97 to 1.20; per-country LOCO/P0 ratio from 0.85 to 1.75.
- P1b-B1 (LOCO): per-country LOCO/main RMSE ratio ranges from 0.94 to 1.31; per-country LOCO/P0 ratio from 0.89 to 2.23.
- P1b-B2 (LOCO): per-country LOCO/main RMSE ratio ranges from 0.96 to 1.23; per-country LOCO/P0 ratio from 0.90 to 2.01.

## 9. Interpretation (predictive only): permutation importance and ALE

Out-of-sample permutation importance on the test rows of each origin 2008-2020 (R = 200, whole rows of a group permuted jointly across the 27 test rows): percentage increase in squared error relative to the unpermuted forecast. 95% interval: country-cluster bootstrap of the pooled value. It says which inputs the forecast relies on, nothing about what produces the outcome.

| Model | Group | Pooled increase in squared error (%) | 95% CI |
|---|---|---|---|
| P1a-B2 | fiscal_macro | 10.85 | [3.04, 23.51] |
| P1a-B2 | political | -0.25 | [-1.36, 0.85] |
| P1a-B2 | demographic | -0.39 | [-0.74, -0.11] |
| P1b-B2 | fiscal_macro | 6.32 | [1.12, 13.74] |
| P1b-B2 | political | -0.05 | [-0.43, 0.40] |
| P1b-B2 | demographic | -0.30 | [-0.72, 0.31] |

| Model | Column | Pooled increase (%) | 95% CI |
|---|---|---|---|
| P1a-B2 | capb_T_dm | 14.40 | [6.56, 26.46] |
| P1a-B2 | debt_gdp_T_dm | 6.93 | [3.54, 12.93] |
| P1a-B2 | euro_T | 0.34 | [0.06, 0.88] |
| P1a-B2 | capb_T_bar | 0.22 | [0.06, 0.59] |
| P1a-B2 | Postk_next | 0.20 | [-0.18, 0.79] |
| P1a-B2 | Wk_now | 0.13 | [-0.67, 1.44] |
| P1a-B2 | ig_diff_T_dm | 0.04 | [-0.27, 0.73] |
| P1a-B2 | medage_T_bar | 0.02 | [-0.08, 0.09] |
| P1a-B2 | olddep3_T_bar | -0.01 | [-0.06, 0.06] |
| P1a-B2 | olddep1_T_bar | -0.01 | [-0.05, 0.03] |
| P1a-B2 | outgap_T_bar | -0.01 | [-0.04, 0.03] |
| P1a-B2 | debt_gdp_T_bar | -0.02 | [-0.05, 0.01] |
| P1a-B2 | dcapb_T_bar | -0.02 | [-0.44, 0.69] |
| P1a-B2 | ig_diff_T_bar | -0.04 | [-0.18, 0.03] |
| P1a-B2 | olddep3_T_dm | -0.05 | [-0.13, 0.05] |
| P1a-B2 | medage_T_dm | -0.10 | [-0.32, 0.08] |
| P1a-B2 | Wk_next | -0.13 | [-0.37, 0.05] |
| P1a-B2 | olddep1_T_dm | -0.24 | [-0.41, -0.07] |
| P1a-B2 | outgap_T_dm | -0.28 | [-0.58, 0.20] |
| P1a-B2 | dcapb_T_dm | -0.30 | [-1.02, 0.81] |
| P1a-B2 | Postk_now | -0.35 | [-1.32, 0.14] |
| P1b-B2 | capb_T_dm | 6.09 | [1.67, 12.27] |
| P1b-B2 | debt_gdp_T_dm | 2.11 | [-0.62, 6.35] |
| P1b-B2 | dcapb_T_dm | 1.50 | [0.18, 3.26] |
| P1b-B2 | capb_T_bar | 0.04 | [-0.09, 0.14] |
| P1b-B2 | Postk_now | 0.04 | [-0.06, 0.17] |
| P1b-B2 | dcapb_T_bar | 0.03 | [-0.03, 0.12] |
| P1b-B2 | olddep1_T_dm | 0.01 | [-0.20, 0.33] |
| P1b-B2 | euro_T | 0.00 | [-0.01, 0.02] |
| P1b-B2 | ig_diff_T_bar | 0.00 | [0.00, 0.00] |
| P1b-B2 | debt_gdp_T_bar | -0.00 | [-0.02, 0.02] |
| P1b-B2 | olddep3_T_bar | -0.00 | [-0.01, 0.00] |
| P1b-B2 | Wk_next | -0.01 | [-0.06, 0.04] |
| P1b-B2 | Postk_next | -0.01 | [-0.06, 0.00] |
| P1b-B2 | ig_diff_T_dm | -0.02 | [-0.29, 0.39] |
| P1b-B2 | outgap_T_bar | -0.03 | [-0.27, 0.20] |
| P1b-B2 | olddep1_T_bar | -0.03 | [-0.07, 0.00] |
| P1b-B2 | outgap_T_dm | -0.04 | [-0.17, 0.06] |
| P1b-B2 | medage_T_bar | -0.04 | [-0.10, 0.04] |
| P1b-B2 | Wk_now | -0.11 | [-0.46, 0.31] |
| P1b-B2 | medage_T_dm | -0.11 | [-0.20, 0.05] |
| P1b-B2 | olddep3_T_dm | -0.15 | [-0.41, 0.12] |

First-order ALE curves (training rows of the last primary origin 2020; ten equal-count bins; pre-listed features) are in `reports/figures/predictive_importance.png` and in the JSON.

## 10. Selected hyperparameters (per origin, CD scheme; full detail in the JSON)

| Model | Summary over the 13 primary origins |
|---|---|
| P1a-B1 | kinds {'ridge': 9, 'enet': 4}; median alpha 100; median non-zero coefficients 11 |
| P1a-B2 | kinds {'enet': 9, 'ridge': 4}; median alpha 1; median non-zero coefficients 10 |
| P1b-B1 | median iterations 23; depth counts {3: 9, 2: 4}; leaf counts {40: 7, 20: 6} |
| P1b-B2 | median iterations 24; depth counts {3: 8, 2: 5}; leaf counts {20: 10, 40: 3} |

## 11. Optional binary deterioration event (`y < -0.5` pp; descriptive, outside the family)

| Block:model | n | Prevalence | Brier | Brier (training rate) | Brier skill | Log-loss | Log-loss (rate) | AUC | Logit calibration slope |
|---|---|---|---|---|---|---|---|---|---|
| P:P1a-B1 | 351 | 0.382 | 0.2281 | 0.2387 | 0.044 | 0.651 | 0.671 | 0.604 | 0.87 |
| P:P1a-B2 | 351 | 0.382 | 0.2342 | 0.2387 | 0.019 | 0.674 | 0.671 | 0.594 | 0.45 |
| P:P1b-B1 | 351 | 0.382 | 0.2345 | 0.2387 | 0.018 | 0.662 | 0.671 | 0.596 | 0.64 |
| P:P1b-B2 | 351 | 0.382 | 0.2352 | 0.2387 | 0.015 | 0.664 | 0.671 | 0.565 | 0.57 |
| H:P1a-B1 | 54 | 0.111 | 0.1506 | 0.1747 | 0.138 | 0.483 | 0.540 | 0.385 | -0.64 |
| H:P1a-B2 | 54 | 0.111 | 0.1899 | 0.1747 | -0.087 | 0.568 | 0.540 | 0.413 | -0.45 |
| H:P1b-B1 | 54 | 0.111 | 0.1710 | 0.1747 | 0.021 | 0.531 | 0.540 | 0.453 | -0.83 |
| H:P1b-B2 | 54 | 0.111 | 0.2056 | 0.1747 | -0.177 | 0.602 | 0.540 | 0.455 | -0.92 |

## 12. Limitations (model card, section 10 of the specification)

Ex-post revised target and features (pseudo-out-of-sample; CAPB revision SD 0.97 pp, mean absolute 0.64 pp); AMECO forecast years 2026-2027 never used, last forecast year 2023; 13 forecast years in P (the DM test has 12 df); regime shifts and one-offs; the political schedule is measured with error; demographic features are near country identity; no common-factor information; no SHAP/LightGBM; associations only.
