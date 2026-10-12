# Secondary outcomes specification (written and committed before the analysis was run)

Date: 2026-10-13, after the confirmatory result and before any secondary-outcome result. It fixes the details that `docs/preregistration.md` section 10 and `config/registry/secondary.toml` leave open. No pre-registered quantity changes. Results are reported whatever they show; later changes need a dated entry in `docs/amendments.md`. Frozen files stay byte-identical; code is new (`src/models/py/secondary.py`, `tests/test_secondary.py`).

## Question

Does the pre-registered CAPB association with scheduled-election exposure coincide with changes in the components of the budget (spending, revenue, social benefits), or does it hide composition shifts? The outcomes are *not* cyclically adjusted, so an association there mixes policy and cyclical effects; this limits what a match or mismatch with the CAPB result can mean.

## Outcomes (gold-panel columns; all in per cent of GDP except the change in CAPB, in pp of potential GDP; sign as published)

| ID | Column | Definition |
|---|---|---|
| S1a | `sec_primary_balance_edp` | headline EDP primary balance (AMECO `UBLGIE`, actual-GDP text) |
| S1b | `sec_net_lending_b9` | net lending (+) / borrowing (−), Eurostat `B9` |
| S1c | `sec_d_capb` | first difference of CAPB within country (consecutive years only) |
| S1d | `sec_primary_expenditure` | `TE − D41PAY` |
| S1e | `sec_revenue` | total revenue `TR` |
| S1f-1 | `sec_social_benefits_d62` | social benefits other than in kind `D62PAY` |
| S1f-2 | `sec_social_transfers_kind_d632` | social transfers in kind `D632PAY` |
| S1g-1 | `sec_cofog_gf10` | COFOG social protection |
| S1g-2 | `sec_cofog_gf1002` | COFOG old age (starts 2000/2001 for 11 states) |
| S1g-3 | `sec_cofog_gf07` | COFOG health |

Descriptive context only, outside the multiplicity family: `sec_total_expenditure`, `sec_interest_d41pay`, `sec_cofog_total`, `sec_cyclical_component` (AMECO `UBLGCP`).

## Model, samples, inference

- Same model and estimator as the headline (M1, centred era terms, no controls, V7 = feasible WLS + AR(1) GLS). **Sample per outcome:** the 715 confirmatory rows with the outcome observed; gaps inside a country's series break the run (the Prais–Winsten step restarts); a country needs at least 5 usable observations to enter. The moderator, its Mundlak split and the era centring are recomputed on each outcome's own estimation sample (the rule in the registry: "standardised on the estimation sample").
- P-values for β_S: null-imposed wild-cluster bootstrap-t, Rademacher weights, B = 9,999, seed key 42, whole procedure re-estimated per bootstrap sample (as in the headline). Intervals: 95% unrestricted bootstrap-t percentile intervals. γ_B and γ_W are reported as estimates with intervals only (descriptive), as in the registry.
- **Multiplicity:** Benjamini–Hochberg at q = 0.05 over the **ten** β_S p-values S1a–S1g-3 (ordered p-values, monotone adjusted q-values). BH assumes independent or positively dependent tests; the outcomes are strongly related, so the Benjamini–Yekutieli adjusted values are shown beside it as a conservative check, without changing the pre-registered BH conclusion.
- No equivalence reading against 0.5 pp is applied to these outcomes (that threshold was set for the CAPB); report "excludes zero" and the BH decision only.

## S3: early-election and nuisance terms (CAPB, descriptive)

From the same fit as the headline, report estimates and intervals for β_E (early elections), β_U (unclassified elections) and ρ (the post-election term). Early elections are endogenous, so these are descriptive and carry no test and no multiplicity adjustment.

## Outputs

`reports/results/secondary.md` and `.json` (every outcome with N, countries, years, β_S, γ_B, γ_W, intervals, raw p, BH q, BY q, the first-stage persistence and variance range); `reports/figures/secondary_forest.png` (β_S in pp of GDP across outcomes, 300 dpi, units, source line); a plain description of whether the sign and size pattern of β_S across components is consistent with the CAPB result, with the cyclical caveat above.
