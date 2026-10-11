# Third-party data: terms and redistribution status

Read from the providers' own pages on 2026-10-10 unless marked otherwise. "Committed" means the raw file is in this repository; "re-acquire" means it is excluded by `.gitignore` and restored with `src/ingest/acquire.py --allow-network`, then checked against the SHA-256 in the committed `manifest.jsonl`. **Where the terms are not stated, this table says so and the file is not redistributed.** This is a working record, not legal advice.

| Dataset | Files | Provider terms (as seen) | Redistribution here | Citation |
|---|---|---|---|---|
| AMECO, Spring 2026 | `data/raw/ameco/2026_spring/*` | Page states only that the data are "made available free of charge"; no licence text. Commission legal notice not read. | **Not committed** (re-acquire) until terms are confirmed | European Commission, DG ECFIN (2026), AMECO database, Spring 2026 forecast release (update 3 June 2026), https://economy-finance.ec.europa.eu/economic-research-and-databases/economic-databases/ameco-database_en |
| EC Fiscal Governance Database | `data/raw/fiscal_governance/nfr_2025_update/*` | No licence or reuse statement on the page. | **Not committed** (re-acquire) | European Commission, DG ECFIN, Fiscal Governance Database (numerical fiscal rules, 2025 update, 5 March 2026) |
| ETAD v1.0.0 | `data/raw/elections_ageing/etad/*` | Dataset licence not stated; the accompanying paper is CC BY-NC; citation requested. | **Not committed** (re-acquire) | Higashijima, M., Shimizu, N., Washida, H., & Yanai, Y. (2025). *Electoral Studies*, 96, 102964. https://doi.org/10.1016/j.electstud.2025.102964 |
| ParlGov 2024 stable release | `data/raw/elections_ageing/parlgov_2024_stable/*` | CC0 1.0 (Dataverse metadata, SPDX `CC0-1.0`). | Committed | Döring, H., & Manow, P. (2024). ParlGov 2024 stable release. Harvard Dataverse, https://doi.org/10.7910/DVN/2VZ5ZC |
| Eurostat extracts (`demo_pjanind`, `gov_10a_main`, `gov_10a_exp`, `gov_10dd_edpt1`, `nama_10_gdp`) | `data/raw/elections_ageing/eurostat_demo_pjanind/*`, `data/raw/eurostat_controls/*` | Reuse allowed with acknowledgement of the source (Eurostat copyright notice). | Committed | Eurostat (2026), accessed 2026-10-10, datasets as named; DOIs in each `data/raw/*/README.md` |
| V-Dem v16 (not acquired in this repository) | none | CC BY-SA 4.0 | n/a | Coppedge, M., et al. (2026). V-Dem v16. https://doi.org/10.23696/vdemds26 |
| DPI2023, CPDS (not acquired) | none | DPI2023: CC BY 4.0 per the IDB portal; CPDS: not read | n/a | Cruz, C., Keefer, P., Scartascini, C., & Simpser, A., https://doi.org/10.60966/8tx1xs4i; Armingeon, K., et al. (2025) |

## Literature PDFs

`data/external/literature/` is gitignored and never redistributed. Carnazza, Liberati & Sacchi (2025) is open access (CC BY). Bednář (2019) is publisher-copyrighted; cite it from the publisher or an institutional copy.

## Open items

AMECO, EC Fiscal Governance Database and ETAD terms are unverified (R07). Until they are read from the providers, those raw files stay out of version control. The code in this repository is MIT-licensed (see `LICENSE`).

## Derived tables and figures

Figures and tables in `reports/` that summarise AMECO, Eurostat, ParlGov or ETAD data carry a source line on the figure itself. The gold panel (`data/processed/gold/`) is not committed because it contains AMECO-derived series; its SHA-256 is.
