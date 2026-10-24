"""
In-memory data store loaded from fixtures/berdo.json.
Provides typed building records and zip-level aggregates.
All load values are ESTIMATED unless per_electricity + site_eui are present.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Literal

from server.constants import (
    EJ_CAP_DEFAULT_PCT,
    LOAD_KW_PER_1000_SQFT_BY_TYPE,
    LOAD_TYPE_SOURCE_ID,
    PROTECTED_PROPERTY_TYPES,
)

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "berdo.json"

# Zips classified as Environmental Justice (EJ) in Massachusetts.
# Source: MassGIS EJ block groups crosswalked to zip codes.
# This is the subset of Boston BERDO zips that overlap EJ block groups.
# https://www.mass.gov/info-details/massgis-data-environmental-justice-populations
EJ_ZIPS: frozenset[str] = frozenset({
    "02118",  # South End
    "02119",  # Roxbury
    "02120",  # Roxbury / Mission Hill
    "02121",  # Dorchester (Fields Corner)
    "02122",  # Dorchester (Codman Square)
    "02124",  # Dorchester (Grove Hall)
    "02125",  # Dorchester (lower)
    "02126",  # Mattapan
    "02127",  # South Boston (eastern)
    "02128",  # East Boston
    "02130",  # Jamaica Plain
    "02136",  # Hyde Park
})


@dataclass
class Building:
    building_id: str
    property_name: str | None
    property_type: str | None
    address: str
    zip: str
    reported: str | None
    gross_area_sf: float | None
    site_eui_kbtuft2: float | None
    total_site_energy_kbtu: float | None
    per_electricity: float | None
    ghg_emissions_mtco2e: float | None
    ghg_intensity_kgco2sf: float | None
    year_built: int | None
    energy_star_score: float | None

    # derived
    is_ej: bool = field(init=False)
    curtailable_load_kw: float | None = field(init=False)
    load_basis: Literal["metered", "estimated_from_type", "unknown"] = field(init=False)

    def __post_init__(self) -> None:
        self.is_ej = self.zip in EJ_ZIPS
        self.curtailable_load_kw, self.load_basis = _estimate_load(self)

    @property
    def is_protected(self) -> bool:
        return self.property_type in PROTECTED_PROPERTY_TYPES

    def to_dict(self) -> dict:
        return {
            "building_id": self.building_id,
            "property_name": self.property_name,
            "property_type": self.property_type,
            "address": self.address,
            "zip": self.zip,
            "reported": self.reported,
            "gross_area_sf": self.gross_area_sf,
            "site_eui_kbtuft2": self.site_eui_kbtuft2,
            "total_site_energy_kbtu": self.total_site_energy_kbtu,
            "per_electricity": self.per_electricity,
            "ghg_emissions_mtco2e": self.ghg_emissions_mtco2e,
            "ghg_intensity_kgco2sf": self.ghg_intensity_kgco2sf,
            "year_built": self.year_built,
            "energy_star_score": self.energy_star_score,
            "is_ej": self.is_ej,
            "curtailable_load_kw": self.curtailable_load_kw,
            "load_basis": self.load_basis,
            "is_protected": self.is_protected,
        }


def _estimate_load(b: Building) -> tuple[float | None, Literal["metered", "estimated_from_type", "unknown"]]:
    """
    Estimate curtailable load in kW.

    Priority:
    1. metered: site_eui + per_electricity + gross_area → annual kWh → peak kW
       (assume peak is 3× the average hourly draw, a conservative DR estimate)
    2. estimated_from_type: gross_area × type-based kW/1000sqft factor
    3. unknown: not enough data
    """
    if b.site_eui_kbtuft2 and b.per_electricity and b.gross_area_sf:
        annual_kbtu = b.site_eui_kbtuft2 * b.gross_area_sf
        annual_kwh = annual_kbtu * b.per_electricity / 3.412  # kBTU to kWh
        avg_kw = annual_kwh / 8760
        # Curtailable load estimate: DR programs typically target 10-15% of peak;
        # peak ≈ 3× avg for commercial buildings
        peak_kw = avg_kw * 3.0
        curtailable_kw = round(peak_kw * 0.15, 1)
        return curtailable_kw, "metered"

    if b.gross_area_sf and b.property_type:
        factor = _load_factor(b.property_type)
        curtailable_kw = round(b.gross_area_sf / 1000 * factor * 0.15, 1)
        return curtailable_kw, "estimated_from_type"

    return None, "unknown"


def _load_factor(property_type: str) -> float:
    """Map property type string to kW/1000sqft load factor."""
    pt = property_type.lower()
    if "office" in pt or "admin" in pt:
        return LOAD_KW_PER_1000_SQFT_BY_TYPE["office"]
    if "retail" in pt or "store" in pt or "shop" in pt or "market" in pt:
        return LOAD_KW_PER_1000_SQFT_BY_TYPE["retail"]
    if "hotel" in pt or "motel" in pt or "lodging" in pt:
        return LOAD_KW_PER_1000_SQFT_BY_TYPE["hotel"]
    if "warehouse" in pt or "storage" in pt or "distribution" in pt:
        return LOAD_KW_PER_1000_SQFT_BY_TYPE["warehouse"]
    if "apart" in pt or "multifamily" in pt or "resid" in pt or "condo" in pt or "apt" in pt:
        return LOAD_KW_PER_1000_SQFT_BY_TYPE["multifamily"]
    if "school" in pt or "college" in pt or "university" in pt or "education" in pt or "daycare" in pt:
        return LOAD_KW_PER_1000_SQFT_BY_TYPE["school"]
    if "hospital" in pt or "medical" in pt or "clinic" in pt or "health" in pt or "nursing" in pt:
        return LOAD_KW_PER_1000_SQFT_BY_TYPE["hospital"]
    if "lab" in pt:
        return LOAD_KW_PER_1000_SQFT_BY_TYPE["lab"]
    return LOAD_KW_PER_1000_SQFT_BY_TYPE["default"]


@lru_cache(maxsize=1)
def load_buildings() -> list[Building]:
    """Load and parse all buildings from the fixture. Cached after first call."""
    with open(FIXTURE_PATH) as f:
        data = json.load(f)
    return [Building(**r) for r in data["records"]]


@lru_cache(maxsize=1)
def buildings_by_id() -> dict[str, Building]:
    return {b.building_id: b for b in load_buildings()}


@lru_cache(maxsize=1)
def buildings_by_zip() -> dict[str, list[Building]]:
    result: dict[str, list[Building]] = {}
    for b in load_buildings():
        result.setdefault(b.zip, []).append(b)
    return result
