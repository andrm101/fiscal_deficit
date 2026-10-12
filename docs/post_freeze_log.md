# Post-freeze log

Events after the pre-registration tag `preregistration-v1`. This file is not part of the freeze manifest (the decision log is, so it is left unchanged). Amendments to the pre-registered plan go in `docs/amendments.md`; none have been needed so far.

| Date | Event |
|---|---|
| 2026-10-12 | Tag `preregistration-v1` created on commit `dca415b` (all nine freeze checks passed, 438 tests). Tag message carries the manifest SHA-256 `4b8bcfa21b0104b6a4c431116f0ea14916d655e4d3ff80efb23600787b9126ee` and the extract hash `2fcf20d4ca687f613d6743214b7be176ceb638b483f513eeed005bd1f73a5bb4`. |
| 2026-10-12 | Tag pushed to `origin` (`refs/tags/preregistration-v1`, object `1653090b887bd6d93126e51c47a1caf03a4f589f`) **before** any analysis of the real outcome. |
| 2026-10-12 | Confirmatory analysis run once with `src/models/py/m1.py` (B = 9,999, seed 42, 32 s). Output: `reports/results/m1_confirmatory.json` and `.md`. Provenance verified afterwards: the registry hash, the extract hash and the SHA-256 of `m1.py` and `power_variants.py` in the results equal the frozen manifest; `git diff preregistration-v1 -- src config docs/preregistration.md` is empty. No deviation from the pre-registration. |

## Result of the pre-registered confirmatory analysis (estimator V7, N = 715, 27 countries; pp of potential GDP)

| Target | Estimate | 95% bootstrap-t interval | p (wild bootstrap) | Holm p | Pre-registered reading |
|---|---|---|---|---|---|
| β_S (a full year of pre-election exposure to a scheduled election) | −0.379 | [−0.691, −0.069] | 0.0181 | 0.0362 | excludes zero; not equivalent to zero within ±0.5 |
| γ_B (per +1 SD of between-country ageing) | +0.207 | [−0.069, 0.488] | 0.1445 | 0.1445 | interval inside ±0.5: equivalent within the SESOI; does not exclude zero |
| γ_W (per +1 SD of within-country ageing) | −0.271 | [−1.497, 0.964] | not tested | not tested | descriptive only (not powered); uninformative |

## Caveats attached to this result (all pre-registered or already known before the run)

1. Associations, not causal effects. Scheduled elections are predetermined, not exogenous.
2. The Holm-adjusted p-value for β_S (0.036) is close to 0.05. Under block-bootstrap noise that carries real cross-country co-movement, wild-bootstrap size for β_S was 11–12% (nominal 5%) in simulation, so the p-value may be too small. The Driscoll–Kraay and CCE sensitivities are the next pre-specified step.
3. The estimate (−0.38 pp) is below the design's minimum detectable effect at the estimated persistence (0.51 pp). Estimates that clear a significance filter near or below the detectable threshold tend to overstate the true effect.
4. The CAPB is a model estimate with a typical first-outturn revision of 0.64 pp, larger than the effect.
5. Cyprus, Greece and Malta have no scheduled elections in the window, so β_S is identified from 24 countries.
