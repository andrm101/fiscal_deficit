"""Single country crosswalk for the EU-27 (as of 2023) used by every Gate 3 module.

The crosswalk lives in ``config/countries.csv`` and maps one row per member state:

* ``eurostat_code``: Eurostat geo code (Greece is ``EL``, not ``GR``);
* ``iso2`` / ``iso3``: ISO 3166-1 alpha-2 / alpha-3 (Romania is ``ROU``);
* ``ameco_code``: ECFIN Redisstat chapter-flow ``REF_AREA`` (ISO-3-like; Greece ``GRC``,
  Romania ``ROM``, as observed in ``AMECO_CHAPTER17-01_UBLGBP.csv`` and tested in
  ``tests/test_ameco_metadata.py``);
* ``name``;
* ``eu_accession_year`` and ``euro_adoption_year`` (empty when the euro has not been adopted by
  2023). These two columns are the public record (accession treaties and Council decisions on euro
  adoption) typed in by the analyst; they are NOT read from a file in this repository and must be
  checked against the ECB / EU treaty pages before use as a control. Neither column feeds the
  election calendar, the exposure variables or the sample selection.

The United Kingdom and every other non-member are deliberately absent: the confirmatory
population is the 27 member states of 2023 (proposal section 4).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COUNTRIES_CSV = PROJECT_ROOT / "config" / "countries.csv"

N_EU27 = 27  # members as of 2023 (proposal section 4)


def load_countries(path: Path = COUNTRIES_CSV) -> pd.DataFrame:
    """Return the crosswalk as a DataFrame with the ``euro_adoption_year`` column as nullable Int64."""
    frame = pd.read_csv(path, dtype={"euro_adoption_year": "Int64", "eu_accession_year": "Int64"})
    return frame


def _mapping(key: str, value: str, path: Path = COUNTRIES_CSV) -> dict[str, str]:
    frame = load_countries(path)
    return dict(zip(frame[key], frame[value], strict=True))


def eurostat_to_ameco(path: Path = COUNTRIES_CSV) -> dict[str, str]:
    """Eurostat geo code -> AMECO ``REF_AREA`` code."""
    return _mapping("eurostat_code", "ameco_code", path)


def ameco_to_eurostat(path: Path = COUNTRIES_CSV) -> dict[str, str]:
    """AMECO ``REF_AREA`` code -> Eurostat geo code."""
    return _mapping("ameco_code", "eurostat_code", path)


def iso3_to_eurostat(path: Path = COUNTRIES_CSV) -> dict[str, str]:
    """ISO 3166-1 alpha-3 code (as used by ETAD and ParlGov) -> Eurostat geo code."""
    return _mapping("iso3", "eurostat_code", path)


def eurostat_to_iso3(path: Path = COUNTRIES_CSV) -> dict[str, str]:
    """Eurostat geo code -> ISO 3166-1 alpha-3 code."""
    return _mapping("eurostat_code", "iso3", path)


def eu27_eurostat_codes(path: Path = COUNTRIES_CSV) -> list[str]:
    """The 27 Eurostat codes in crosswalk order."""
    return load_countries(path)["eurostat_code"].tolist()
