# Secondary outcomes (pre-specified, `docs/secondary_spec.md`)

Status: **complete** (10 of 10 family outcomes completed). Estimator: V7: GlsEstimator(wls=True, ar1=True) on M1 with centred era terms, no controls, re-estimated on each outcome's own sample. Source: `real_gold_panel`.
Associations only: scheduled elections are predetermined, not exogenous. Units: pp of GDP, except S1c and the cyclical component (pp of potential GDP). beta_S is the coefficient of a full year (W_S = 1) of pre-election exposure to a scheduled election, at the sample-average moderator and era composition. The outcomes are not cyclically adjusted (S1c excepted), so a comparison with the CAPB result mixes policy and cyclical effects.

## beta_S for the ten family outcomes (Benjamini-Hochberg at q = 0.05 over S1a-S1g-3; Benjamini-Yekutieli beside it)

| ID | outcome | unit | N | countries | years | beta_S | 95% bootstrap-t interval | p (wild-cluster bootstrap-t) | BH q | BY q | BH decision (q <= 0.05) | interval excludes 0 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S1a | Primary balance (EDP, AMECO UBLGIE) | pp of GDP | 715 | 27 | 1995-2021 | -0.2345 | [-0.5435, 0.0727] | 0.1522 | 0.3044 | 0.8916 | no rejection | no |
| S1b | Net lending (B9) | pp of GDP | 715 | 27 | 1995-2021 | -0.1717 | [-0.4951, 0.1524] | 0.3125 | 0.4464 | 1.0000 | no rejection | no |
| S1c | Change in CAPB | pp of potential GDP | 693 | 27 | 1995-2021 | -0.7044 | [-1.1690, -0.2372] | 0.0007 | 0.0070 | 0.0205 | reject | yes |
| S1d | Primary expenditure (TE - D41PAY) | pp of GDP | 715 | 27 | 1995-2021 | +0.1305 | [-0.2337, 0.5005] | 0.4827 | 0.5379 | 1.0000 | no rejection | no |
| S1e | Total revenue (TR) | pp of GDP | 715 | 27 | 1995-2021 | -0.1748 | [-0.3996, 0.0548] | 0.1278 | 0.3044 | 0.8916 | no rejection | no |
| S1f-1 | Social benefits other than in kind (D62PAY) | pp of GDP | 715 | 27 | 1995-2021 | -0.0976 | [-0.2573, 0.0584] | 0.2322 | 0.3870 | 1.0000 | no rejection | no |
| S1f-2 | Social transfers in kind (D632PAY) | pp of GDP | 715 | 27 | 1995-2021 | +0.0203 | [-0.0047, 0.0452] | 0.1222 | 0.3044 | 0.8916 | no rejection | no |
| S1g-1 | COFOG social protection (GF10) | pp of GDP | 701 | 27 | 1995-2021 | -0.1404 | [-0.2473, -0.0303] | 0.0377 | 0.1885 | 0.5521 | no rejection | yes |
| S1g-2 | COFOG old age (GF1002) | pp of GDP | 637 | 27 | 1995-2021 | -0.0167 | [-0.1057, 0.0712] | 0.7062 | 0.7062 | 1.0000 | no rejection | no |
| S1g-3 | COFOG health (GF07) | pp of GDP | 701 | 27 | 1995-2021 | +0.0210 | [-0.0419, 0.0840] | 0.4841 | 0.5379 | 1.0000 | no rejection | no |

BH decision at q = 0.05: 1 of 10 outcomes. BY (conservative check; does not change the pre-registered BH conclusion): 1 of 10.

## Descriptive context outcomes (same model; estimate and interval only; outside the multiplicity family; no p-values or q-values)

| outcome | unit | N | countries | years | beta_S | 95% bootstrap-t interval |
|---|---|---|---|---|---|---|
| Total expenditure (TE) | pp of GDP | 715 | 27 | 1995-2021 | +0.1037 | [-0.3238, 0.5388] |
| Interest (D41PAY) | pp of GDP | 715 | 27 | 1995-2021 | -0.0437 | [-0.1104, 0.0237] |
| COFOG total | pp of GDP | 701 | 27 | 1995-2021 | +0.1286 | [-0.3198, 0.5807] |
| Cyclical component (AMECO UBLGCP) | pp of potential GDP | 715 | 27 | 1995-2021 | +0.1337 | [-0.0374, 0.3116] |

## gamma_B and gamma_W (descriptive: estimate and interval only, per +1 SD of the component of lagged OLDDEP1 on that outcome's sample)

| ID | gamma_B | 95% interval | gamma_W | 95% interval |
|---|---|---|---|---|
| S1a | +0.1747 | [-0.0962, 0.4442] | +0.0035 | [-0.9961, 1.0013] |
| S1b | +0.0961 | [-0.2315, 0.4210] | -0.1981 | [-1.0100, 0.6226] |
| S1c | +0.0323 | [-0.5595, 0.6295] | -0.2248 | [-1.7288, 1.2779] |
| S1d | -0.0396 | [-0.4412, 0.3619] | -0.0359 | [-0.8595, 0.7555] |
| S1e | +0.0823 | [-0.1382, 0.3024] | +0.2142 | [-0.3110, 0.7234] |
| S1f-1 | -0.1126 | [-0.3419, 0.1139] | +0.1161 | [-0.2270, 0.4602] |
| S1f-2 | +0.0295 | [-0.0122, 0.0706] | -0.0409 | [-0.1102, 0.0289] |
| S1g-1 | +0.0345 | [-0.1154, 0.1846] | +0.0153 | [-0.2712, 0.3016] |
| S1g-2 | +0.0420 | [-0.0156, 0.0997] | +0.0672 | [-0.1100, 0.2470] |
| S1g-3 | +0.0163 | [-0.0596, 0.0960] | +0.0301 | [-0.0339, 0.0931] |
| C-te | +0.1420 | [-0.3522, 0.6503] | +0.0564 | [-0.6100, 0.7169] |
| C-d41 | +0.0430 | [-0.0083, 0.0954] | +0.1410 | [-0.0437, 0.3257] |
| C-cofog | +0.0781 | [-0.4335, 0.6000] | -0.0796 | [-0.8462, 0.6722] |
| C-cyc | -0.0965 | [-0.2918, 0.0943] | -0.0005 | [-0.4633, 0.4689] |

## Fit diagnostics and sample notes

| ID | rho (Nickell-corrected) | country residual SD: min (country) | median | max (country) | runs / countries with a gap | countries not entering (usable obs) | regressors dropped |
|---|---|---|---|---|---|---|---|
| S1a | 0.672 | 0.923 (FR) | 2.012 | 5.495 (IE) | 27 / 0 | none | W_D |
| S1b | 0.601 | 1.110 (FR) | 1.809 | 5.796 (IE) | 27 / 0 | none | W_D |
| S1c | -0.130 | 0.768 (FR) | 1.576 | 5.192 (IE) | 27 / 0 | none | W_D |
| S1d | 0.743 | 1.487 (NL) | 2.132 | 7.531 (IE) | 27 / 0 | none | W_D |
| S1e | 0.793 | 0.790 (AT) | 1.551 | 4.612 (IE) | 27 / 0 | none | W_D |
| S1f-1 | 0.927 | 0.438 (CZ) | 1.374 | 2.684 (EL) | 27 / 0 | none | W_D |
| S1f-2 | 0.858 | 0.143 (SI) | 0.274 | 1.216 (NL) | 27 / 0 | none | W_D |
| S1g-1 | 0.950 | 0.529 (CZ) | 1.408 | 2.472 (EL) | 27 / 0 | none | W_D |
| S1g-2 | 0.895 | 0.309 (DK) | 0.725 | 1.699 (PT) | 27 / 0 | none | W_D |
| S1g-3 | 0.856 | 0.222 (FR) | 0.438 | 0.931 (IE) | 27 / 0 | none | W_D |
| C-te | 0.735 | 1.399 (AT) | 2.186 | 7.655 (IE) | 27 / 0 | none | W_D |
| C-d41 | 0.833 | 0.310 (FI) | 0.751 | 2.488 (BG) | 27 / 0 | none | W_D |
| C-cofog | 0.734 | 1.433 (AT) | 2.188 | 7.660 (IE) | 27 / 0 | none | W_D |
| C-cyc | 0.737 | 0.619 (BE) | 0.817 | 2.867 (EL) | 27 / 0 | none | W_D |

Notes: the Nickell-corrected persistence is capped at 0.95 by the estimator; at the cap: S1g-1. Outcomes with persistence of at least 0.85 (spending-share series are close to unit-root behaviour): S1f-1, S1f-2, S1g-1, S1g-2, S1g-3; the AR(1) correction and the bootstrap were not validated at such persistence (the pre-registered power study used rho of about 0.69), so those intervals deserve less weight. Country residual SDs are those of the first-stage fit; the WLS weights are their inverse squares.

## S3: early, unclassified and post-election terms in the CAPB fit (descriptive; no test, no multiplicity adjustment)

Same fit as the headline (N = 715, 27 countries; pp of potential GDP). Early elections are endogenous.

| term | meaning | estimate | 95% bootstrap-t interval |
|---|---|---|---|
| beta_E | coefficient of W_E (early-election exposure); early elections are endogenous | -0.5273 | [-1.1614, 0.0918] |
| beta_U | coefficient of W_U (unclassified-election exposure) | +0.8407 | [-3.4152, 5.2498] |
| rho_Post | coefficient of Post (share of the year within 12 months after any election) | -0.4995 | [-0.8154, -0.1768] |

Self-check against `m1_confirmatory.json` (beta_S, gamma_B, gamma_W estimates and intervals, beta_S p): max absolute difference 0.00e+00 (tolerance 1e-08); headline B = 9999, this run B = 9999; **PASSED**.

## Reading of the pattern across components

* CAPB result (pre-registered): beta_S = -0.379 pp of potential GDP, 95% interval [-0.691, -0.069]; a lower value is a weaker cyclically adjusted primary balance.
* Signs: 7 of 10 family point estimates are in the direction of a weaker budget balance (a lower balance, lower revenue, higher spending); the other 3 (S1f-1, S1g-1, S1g-2) point the other way. 2 of 10 95% intervals exclude zero (unadjusted): S1c, S1g-1.
* Consistency with the CAPB result: S1a has the same sign as the CAPB estimate, a point estimate 0.62 times its size, an interval that includes zero and includes the CAPB estimate; S1b has the same sign as the CAPB estimate, a point estimate 0.45 times its size, an interval that includes zero and includes the CAPB estimate.
* The change in CAPB (S1c) is a different quantity from the CAPB level: its beta_S (-0.704 pp of potential GDP, interval [-1.169, -0.237]) is 1.9 times the size of the level estimate. Its sign agrees from the CAPB result; the sizes are not directly comparable.
* Benjamini-Hochberg at q = 0.05: 1 of 10 outcomes (S1c); Benjamini-Yekutieli: 1 (S1c).
* Balance outcomes: S1a -0.23 [-0.54, 0.07] (pp of GDP); S1b -0.17 [-0.50, 0.15] (pp of GDP); S1c -0.70 [-1.17, -0.24] (pp of potential GDP).
* Spending and revenue: beta_S is +0.13 pp of GDP for primary expenditure and -0.17 pp of GDP for revenue, so the revenue minus primary expenditure difference is -0.31 pp. This is arithmetic on two separate fits (own samples and weights), not an exact decomposition of S1a.
* Social components: S1f-1 -0.10 [-0.26, 0.06]; S1f-2 +0.02 [-0.00, 0.05]; S1g-1 -0.14 [-0.25, -0.03]; S1g-2 -0.02 [-0.11, 0.07]; S1g-3 +0.02 [-0.04, 0.08] pp of GDP.
* Caveat on comparison with the CAPB result: the outcomes other than the change in CAPB are not cyclically adjusted. A match or a mismatch between their beta_S and the CAPB beta_S therefore mixes policy and cyclical effects and cannot be read as policy composition alone. Everything here is an association with predetermined, not exogenous, election timing.

## Provenance

* seed 42, bootstrap seed key 42, B = 9999 (Rademacher weights, whole feasible procedure re-estimated in every bootstrap sample); a country needs at least 5 usable observations
* versions: numpy 2.4.4, pandas 3.0.2, scipy 1.17.1
* gold extract hash: `2fcf20d4ca687f613d6743214b7be176ceb638b483f513eeed005bd1f73a5bb4`
* secondary.py (SHA-256, LF-normalised): `54b5d50de7755b57c9d43fb156e5a3b66b188e0d6958575bdf00ed10e0d17629`
* m1.py (SHA-256, LF-normalised): `01fd7b728e3583921d6ad1d9920b5743a0fa83c4d92dbf93e1f72fd816925c85`
* power_variants.py (SHA-256, LF-normalised): `f0bdd1105e791276f3ef6c8de7eeea1621a8f313e05eb18c0b6cd81f4a20051e`
* power.py (SHA-256, LF-normalised): `838b9535c474f27171165edf4229584669106ff017137c5c1e0c6760ac3b0de6`
* docs/secondary_spec.md (SHA-256, LF-normalised): `bb7f3bb994a6d870fbcdd98262e1f3cc820a03813941ec754e3d7a5a5e97252d`
* config/registry/secondary.toml (SHA-256, LF-normalised): `5db7830e8160e748b0dc39088abe12d86c494481c3032200a255cb53e75d7334`
