# AMECO archive vintages, Autumn 2014 to Autumn 2025

- **Provider:** European Commission, DG ECFIN. Archive page: https://economy-finance.ec.europa.eu/economic-research-and-databases/economic-databases/ameco-database/ameco-archive_en
- **Downloaded:** 2026-10-10 (26 zipped text vintages, about 180 MB; UTC timestamps, SHA-256 and sizes in `manifest.jsonl`). Re-acquire with `python src/ingest/acquire.py --manifest config/acquisition/gate5_ameco_archive.toml --allow-network`.
- **Redistribution:** terms not stated by the provider; the zips are **not committed**.
- **Purpose:** real-time CAPB feasibility check (S4, trigger T3): what the Commission reported for the cyclically adjusted primary balance at each forecast round, to compare with the pinned Spring 2026 final values. Vintages from Autumn 2014 are used because the cyclical-adjustment method is homogeneous only from then (ECP536; Appendix B 1.3).
- **Caveats:** the printed date of the file listed as "Autumn 2025" is 3 June 2025, 15 days after Spring 2025, which is implausible for an autumn release. Its internal date is checked in `reports/gate5_realtime_feasibility.md` before it is used as a vintage.
- **Directory layout:** `<year>_<season>/ameco_<season><year>.zip`.
