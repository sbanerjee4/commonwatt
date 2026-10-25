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

# Max plausible Site EUI (kBtu/ft2). Above this is a BERDO data error.
MAX_PLAUSIBLE_EUI = 1000.0

INCOME_FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "income.json"
INCOME_SOURCE_ID = "census_acs5_b19013"

GEOCODE_FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "geocoded.json"
GEOCODE_SOURCE_ID = "census_geocoder"


@lru_cache(maxsize=1)
def _lnglat_by_building_id() -> dict:
    """[lng, lat] per building id, from the committed Census geocode fixture."""
    try:
        with open(GEOCODE_FIXTURE_PATH) as f:
            return json.load(f).get("lng_lat_by_building_id", {})
    except FileNotFoundError:
        return {}

# Affluence tiers by median household income (USD). These thresholds split the
# region into who-can-absorb-a-reduction (high) vs who-we-protect (low). The
# planner prefers asking "high" first and spares "low".
# Rough MA context: statewide median ~ $94k; EJ Boston zips run $43k-$65k.
AFFLUENCE_HIGH_MIN = 120_000.0   # >= this -> high (can sacrifice more)
AFFLUENCE_LOW_MAX = 70_000.0     # <= this -> low (protect)


@lru_cache(maxsize=1)
def _income_by_zip() -> dict:
    """Median household income by zip, from the committed ACS fixture."""
    try:
        with open(INCOME_FIXTURE_PATH) as f:
            return json.load(f).get("median_household_income_by_zip", {})
    except FileNotFoundError:
        return {}


def median_income_for_zip(zip_code: str | None) -> int | None:
    if not zip_code:
        return None
    val = _income_by_zip().get(zip_code)
    return int(val) if val else None


def affluence_tier_for_income(income: int | None) -> Literal["low", "middle", "high", "unknown"]:
    if income is None:
        return "unknown"
    if income <= AFFLUENCE_LOW_MAX:
        return "low"
    if income >= AFFLUENCE_HIGH_MIN:
        return "high"
    return "middle"

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
    median_income: int | None = field(init=False)
    affluence_tier: Literal["low", "middle", "high", "unknown"] = field(init=False)
    lng_lat: list | None = field(init=False)

    def __post_init__(self) -> None:
        self.is_ej = self.zip in EJ_ZIPS
        self.curtailable_load_kw, self.load_basis = _estimate_load(self)
        self.median_income = median_income_for_zip(self.zip)
        self.affluence_tier = affluence_tier_for_income(self.median_income)
        self.lng_lat = _lnglat_by_building_id().get(self.building_id)

    @property
    def is_protected(self) -> bool:
        return self.property_type in PROTECTED_PROPERTY_TYPES

    @property
    def is_commercial(self) -> bool:
        """Large commercial / institutional buildings can absorb a reduction
        more easily than homes. Used alongside affluence to prefer who to ask."""
        pt = (self.property_type or "").lower()
        commercial_kw = ("office", "retail", "hotel", "mall", "warehouse",
                         "lab", "financial", "commercial", "industrial",
                         "distribution", "supermarket", "store", "showroom")
        return any(k in pt for k in commercial_kw)

    @property
    def can_absorb(self) -> bool:
        """True if this building is a fair ask-first target: higher-income area
        or a large commercial/institutional building (not a protected facility)."""
        if self.is_protected:
            return False
        return self.affluence_tier == "high" or self.is_commercial

    @property
    def should_protect(self) -> bool:
        """True if we should spare this building where possible: low-income
        area or an EJ zip. These are asked LAST and least."""
        return self.affluence_tier == "low" or self.is_ej

    @property
    def socioeconomic_priority(self) -> float:
        """Ask-first priority from socioeconomic status (higher = ask first).

        Core equity idea: lean on those who can most afford to cut (large
        commercial + higher-income), spare those a reduction would hurt most
        (low-income residential, EJ). A big commercial building in a poor area
        is still a fair ask (it's an institution, not a household), but it is
        ranked below commercial buildings in wealthier areas.

          +2.0  large commercial / institutional building
          +1.5  high-income area
          +0.0  middle-income area
          -1.5  low-income area (protect)
          -1.0  EJ zip (protect; stacks with low-income)
          -10   protected facility (effectively never, handled separately)
        """
        if self.is_protected:
            return -10.0
        score = 0.0
        if self.is_commercial:
            score += 2.0
        if self.affluence_tier == "high":
            score += 1.5
        elif self.affluence_tier == "low":
            score -= 1.5
        if self.is_ej:
            score -= 1.0
        return score

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
            "median_income": self.median_income,
            "affluence_tier": self.affluence_tier,
            "is_commercial": self.is_commercial,
            "can_absorb": self.can_absorb,
            "should_protect": self.should_protect,
            "socioeconomic_priority": round(self.socioeconomic_priority, 2),
            "income_source_id": INCOME_SOURCE_ID if self.median_income else None,
            "lng_lat": self.lng_lat,
            "geocode_source_id": GEOCODE_SOURCE_ID if self.lng_lat else None,
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
    # Guard against BERDO data-entry errors: a plausible Site EUI tops out
    # around 1000 kBtu/ft2 even for energy-intensive buildings. Values above
    # that are garbage (e.g. 50000) and would produce absurd MW estimates, so
    # we ignore the metered path and fall back to type-based estimation.
    eui_plausible = (
        b.site_eui_kbtuft2 is not None and 0 < b.site_eui_kbtuft2 <= MAX_PLAUSIBLE_EUI
    )
    if eui_plausible and b.per_electricity and b.gross_area_sf:
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
    """
    Load and parse all buildings from the fixture. Cached after first call.

    BERDO files some physical campuses (e.g. hospitals) as several records that
    share an address and zip but carry distinct building ids (a base id plus
    `-NNNN` suffixed sub-records). Left in, they show the same building several
    times in the recruitment list AND let the planner double-count one campus's
    load. We collapse rows on (address, zip), keeping the first occurrence so the
    stable base id and ordering are preserved. Records missing an address are
    kept as-is (no safe key to merge them on).
    """
    with open(FIXTURE_PATH) as f:
        data = json.load(f)

    seen: set[tuple[str, str | None]] = set()
    buildings: list[Building] = []
    for r in data["records"]:
        b = Building(**r)
        key = (b.address, b.zip)
        if b.address and key in seen:
            continue  # duplicate physical building — already have it
        if b.address:
            seen.add(key)
        buildings.append(b)
    return buildings


@lru_cache(maxsize=1)
def buildings_by_id() -> dict[str, Building]:
    return {b.building_id: b for b in load_buildings()}


@lru_cache(maxsize=1)
def buildings_by_zip() -> dict[str, list[Building]]:
    result: dict[str, list[Building]] = {}
    for b in load_buildings():
        result.setdefault(b.zip, []).append(b)
    return result
