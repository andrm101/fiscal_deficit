"""Write data/interim/ameco_2026_spring_snapshot.json: derived facts about the pinned AMECO snapshot.

Offline. Reads the raw manifest and the UBLGBP extract; records file hashes, vintage
identifiers, the observed-versus-forecast rule and the last observed year used.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "normalize"))
import ameco  # noqa: E402

OUT = ROOT / "data" / "interim" / "ameco_2026_spring_snapshot.json"
SEASON = "spring"
SAMPLE_START_PROVISIONAL = 1995


def main() -> None:
    """Build and write the snapshot summary."""
    manifest = [
        json.loads(line)
        for line in (ameco.AMECO_DIR / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    capb = ameco.read_sdmx_csv(ameco.AMECO_DIR / "sdmx" / "AMECO_CHAPTER17-01_UBLGBP.csv")
    eu = capb[capb["REF_AREA"].isin(ameco.EU27_AMECO)]
    max_year = int(capb["TIME_PERIOD"].max())
    last_obs = ameco.last_observed_year(max_year, SEASON)
    window = eu[eu["TIME_PERIOD"].between(SAMPLE_START_PROVISIONAL, last_obs)]
    first_year = eu.dropna(subset=["OBS_VALUE"]).groupby("REF_AREA")["TIME_PERIOD"].min()
    summary = {
        "series": ameco.CAPB_ITEM,
        "label": ameco.CAPB_LABEL,
        "denominator_text": ameco.POTENTIAL_GDP_TEXT,
        "sign_convention": "surplus positive",
        "vintage": {
            "season": SEASON,
            "sdmx_last_update_values": sorted(capb["LAST UPDATE"].unique().tolist()),
            "zip_server_last_modified": next(r["last_modified"] for r in manifest if r["id"] == "A01"),
        },
        "obs_status_values": sorted(capb["OBS_STATUS"].unique().tolist()),
        "obs_status_informative": False,
        "max_year_in_vintage": max_year,
        "forecast_rule": "last 2 years of a Spring vintage are forecasts (AMECO Reference Metadata)",
        "forecast_years": list(range(last_obs + 1, max_year + 1)),
        "last_observed_year_used": last_obs,
        "eu27_cells_observed_1995_to_last_observed": int(window["OBS_VALUE"].notna().sum()),
        "eu27_cells_possible": 27 * (last_obs - SAMPLE_START_PROVISIONAL + 1),
        "eu27_first_observed_year_by_area": {k: int(v) for k, v in first_year.items()},
        "files": {r["id"]: {"sha256": r["sha256"], "size_bytes": r["size_bytes"], "retrieved_utc": r["retrieved_utc"]} for r in manifest},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: last observed {last_obs}, "
          f"{summary['eu27_cells_observed_1995_to_last_observed']}/{summary['eu27_cells_possible']} EU-27 cells")


if __name__ == "__main__":
    main()
