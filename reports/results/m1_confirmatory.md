# M1 confirmatory results

Estimator: V7: GlsEstimator(wls=True, ar1=True) on M1 with centred era terms, no controls. N = 715 country-years, 27 countries. Source: `real_gold_panel`.
Results are associations; scheduled elections are predetermined, not exogenous. Estimates are in pp of potential GDP (interactions per +1 SD of the component).

Interval reading: smallest effect size of interest 0.5 pp (registry status CONFIRMED). Label precedence: excludes zero, then equivalent within +-sesoi, then inconclusive; both flags are shown.

## Confirmatory family (Holm over beta_S and gamma_B)

| target | estimate | 95% bootstrap-t interval | p (wild-cluster bootstrap-t) | p (Holm) | excludes zero | within +-sesoi | reading |
|---|---|---|---|---|---|---|---|
| beta_S | -0.3794 | [-0.6912, -0.0693] | 0.01810 | 0.03620 | True | False | excludes zero |
| gamma_B | 0.2066 | [-0.0691, 0.4882] | 0.14450 | 0.14450 | False | True | equivalent within +-sesoi |

## Descriptive (not powered, decision D-C): estimate and interval only

| target | estimate | 95% bootstrap-t interval |
|---|---|---|
| gamma_W | -0.2708 | [-1.4973, 0.9642] |

## CR1 with t(26), shown for transparency: not valid for this estimator (over-rejects)

| target | estimate | CR1 SE | CR1 p | CR1 95% interval |
|---|---|---|---|---|
| beta_S | -0.3794 | 0.1331 | 0.00844 | [-0.6530, -0.1058] |
| gamma_B | 0.2066 | 0.1317 | 0.12882 | [-0.0641, 0.4773] |
| gamma_W | -0.2708 | 0.4505 | - | [-1.1968, 0.6551] |

## Provenance

* seed 42, bootstrap seed key 42, B = 9999 (Rademacher weights, whole feasible procedure re-estimated in every bootstrap sample)
* versions: numpy 2.4.4, pandas 3.0.2, scipy 1.17.1
* registry hash (SHA-256, LF-normalised): `8bb8383691e4acc2b102d805ee576410308c667f649a3b41d185e924137c03ee`
* code hash (m1.py + power_variants.py): `8823d782c2669d5c2848dfa92554da013065e4fa36a05ea7f2d5318357bd3d2c`
* gold extract hash: `2fcf20d4ca687f613d6743214b7be176ceb638b483f513eeed005bd1f73a5bb4`
