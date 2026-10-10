# AMECO, Spring 2026 vintage

- **Provider:** European Commission, DG ECFIN. Landing page: https://economy-finance.ec.europa.eu/economic-research-and-databases/economic-databases/ameco-database_en
- **Release:** Spring 2026 Economic Forecast, page "last update 03 June 2026". The zip's server `Last-Modified` is 2026-06-02 14:51 UTC; SDMX `LAST UPDATE` stamps are `03/06/26` (see `manifest.jsonl`).
- **Downloaded:** 2026-10-10 (UTC timestamps and SHA-256 per file in `manifest.jsonl`).
- **Redistribution:** terms not stated by the provider ("free of charge"); these files are **not committed**. Re-acquire with `python src/ingest/acquire.py --manifest config/acquisition/gate1_ameco_2026_spring.toml --allow-network` and check the hashes.

| File | Content |
|---|---|
| `ameco_all_csv.zip` | All AMECO chapters as CSV (18 chapter files); chapter 17 holds cyclically adjusted series |
| `sdmx/AMECO_CHAPTER17-01_UBLGBP.csv` | **Primary outcome.** Net lending excluding interest, adjusted for the cyclical component, potential-GDP basis |
| `sdmx/AMECO_CHAPTER17-01_UBLGAP.csv`, `..._UBLGCP.csv` | Cyclically adjusted net lending; cyclical component (potential-GDP basis) |
| `sdmx/AMECO_CHAPTER06-05_AVGDGP.csv` | Output gap relative to potential GDP |
| `sdmx/AMECO_CHAPTER16-04_UBLGIE.csv` | Headline EDP primary balance (extract mixes three units; select by the denominator text) |
| `sdmx/DSD_AMECO_1.4.xml` | Official code lists (exact English labels) |
| `docs/` | Variable help texts (dated 21 May 2026) and AMECO reference metadata |

## Variable definitions (as verified in `tests/test_ameco_metadata.py`)

- `UBLGBP`: "Net lending (+) or net borrowing (-) excluding interest of general government adjusted for the cyclical component :- Adjustment based on potential GDP Excessive deficit procedure". Unit text: "(Percentage of potential GDP at current prices)". Surplus positive. Always a model estimate.
- Numeric unit code 319 is shared by %-of-GDP and %-of-potential-GDP series: **never infer the denominator from it**.
- Forecast years: AMECO publishes no flag; by the AMECO reference metadata the last two years of a Spring vintage (2026, 2027) are forecasts.
- Country codes in chapter flows are ISO-3-like (Greece `GRC`, Romania `ROM`).
