# Progress checklist

Status on 2026-10-13. "Committed" means on `origin/main` (latest commit `d1c3ccd`); the pre-registration tag is `preregistration-v1`. This file is not part of the freeze manifest.

## Done and committed

| Stage | Item | Evidence |
|---|---|---|
| A/B | Proposal, literature matrix (full-text reads of Carnazza et al. and Bednář), source-to-variable map, feasibility gates | `reports/proposal.md`, `reports/appendix_A..D`, `reports/literature_fulltext_*.md` |
| Data | Acquisition manifest, offline-first acquisition tool (hash-checked, bounded retries), licences note | `reports/acquisition_manifest_2026-10-10.md`, `src/ingest/acquire.py`, `data/external/LICENSES.md` |
| Data | AMECO Spring 2026 normaliser (unit text, no reliance on code 319), vintages, Eurostat reader, ETAD/ParlGov calendar | `src/normalize/*`, `reports/gate3_*.md` |
| Gates | Gates 2, 3, 3c, 3d (calendar and sample, power, specification, V7 candidate), Gate 4 (controls), Gate 5 (real-time feasibility) | `reports/gate*.md`, `config/acquisition/` |
| Panel | Gold panel N = 715 (27 countries, 1995–2021), audit | `src/features/panel.py`, `reports/gold_panel_audit.md` |
| Descriptives | Tier-1 descriptives and nine figures | `reports/tier1_descriptives.md`, `reports/figures/t1_*.png` |
| Freeze | Pre-registration, registry, SESOI 0.5 pp, manifest, tag pushed before analysis | `docs/preregistration.md`, `docs/freeze_manifest.json`, tag `preregistration-v1` |
| Confirmatory | M1 under V7, run once, provenance verified | `reports/results/m1_confirmatory.{md,json}` |
| Specs | Robustness and secondary specifications fixed before any result | `docs/robustness_spec.md`, `docs/secondary_spec.md` |
| Secondary | Ten outcomes with BH/BY, S3 descriptives, forest plot, self-check | `reports/results/secondary.{md,json}`, `reports/figures/secondary_forest.png` |
| Hygiene | Stale pre-freeze test made tag-aware; post-freeze log; pinned `.venv`; Quarto wrapper | `docs/post_freeze_log.md`, `tests/test_freeze.py` |

## Written, not yet committed (agent still running; not reviewed)

| Item | Files |
|---|---|
| Robustness suite: section A (inference sensitivities, Driscoll–Kraay cross-checked against `linearmodels`, CCE, CD) is in the report; diagnostics, sample variants, leave-one-out and definition variants are not yet in the report | `src/models/py/robustness.py`, `tests/test_robustness.py`, `reports/results/robustness.{md,json}` |

## Gaps (open, in priority order)

1. **Finish and review the robustness suite** (issues 22, 23, 24, 27, 28): sections B–D, the forest plot, the lead placebo.
2. **Figures for the results chapter**: headline estimates with the pre-registered reading, a robustness forest, election-window plots (deferred until after the freeze, now allowed). Existing figures need a consistent style and the 300 dpi / source-line check (issue 34).
3. **Thesis skeleton and draft** in Quarto with `references.bib` (issue 33). A first draft exists under `thesis/` once the draft task finishes; results chapters must be filled from the committed JSON, never typed by hand.
4. **Exploratory models E1–E6** (issue 29) and the **CAPB revision appendix S4** (issue 30): both pre-specified as descriptive.
5. **Predictive module** (issue 31) and the **single optional extension** decision (issue 32).
6. **Engineering and reproducibility**: CI workflow (issue 4), Makefile / `run_pipeline.py` (issue 6), static tests for absolute paths and network use (issue 5), `verify_manifest()` (issue 8), AMECO silver builder with forecast flag (issue 10), DuckDB writer (issue 12), contracts enforced in code (issue 14), README-claims check (issue 35), seed audit (issue 36), model card (issue 37), clean-clone reproduction (issue 38).
7. **Licence terms** for AMECO, EC Fiscal Governance Database and ETAD (issue 3).
8. **Issue hygiene**: the open decision issues 19 and 20 (SESOI, demotion rule) are resolved in the registry and can be closed with a link to the freeze commit; issues 21 and 26 can be closed or updated now.
9. **Administrative**: deadline and official length limit (plan assumes 16 weeks and 60–80 pages); issues for the original `andrm101` repositories (deferred).

## Interpretation to carry into the thesis

* The confirmatory β_S (−0.379 pp, Holm p = 0.036) keeps its sign in every robustness specification run so far, but its interval excludes zero in only four of eleven inference variants. It must be reported as fragile.
* Of ten secondary outcomes, one survives BH (change in CAPB); no spending or revenue component clearly drives the CAPB association.
