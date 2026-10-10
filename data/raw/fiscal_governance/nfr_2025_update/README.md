# EC Fiscal Governance Database: numerical fiscal rules (2025 update)

- **Provider:** European Commission, DG ECFIN. Page: https://economy-finance.ec.europa.eu/economic-research-and-databases/economic-databases/fiscal-governance-database_en
- **Release:** 2025 update, page date 5 March 2026; old-methodology file dated 6 March 2017.
- **Downloaded:** 2026-10-10 (hashes in `manifest.jsonl`).
- **Redistribution:** no licence or reuse statement on the page; the workbooks are **not committed**. Re-acquire with `config/acquisition/gate2_fiscal_governance.toml`.

| File | Content |
|---|---|
| `Numerical-Fiscal-Rules-database-2025.xlsx` | 8 sheets; rule database and the Fiscal Rule Index 1990–2024 (raw `C-FRSI` and a standardised sheet) |
| `fiscal_rules_database_en_old_methodology.xls` | 2016 update, 1990–2015, old methodology (audit only; never spliced) |

## What the audit found (full detail: `reports/gate2_fiscal_governance_audit.md`)

The index is a de jure design-strength score of national rules (not enforcement or compliance), with 149 of 783 EU-27 country-years (1995–2023) coded "." in the raw sheet, a back-cast before 2016, and a standardised sheet that turns "." into one constant. Use of it is therefore **exploratory only** (decision log, Gate 2).
