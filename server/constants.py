"""
Energy program rates and emissions factors.
One citation per constant — never inline these in tool logic.
All values labeled ESTIMATED; assumptions shown in ASSUMPTIONS dict.

Sources:
  CONN_SOLUTIONS_RATE_USD_PER_KW:
    Mass Save ConnectedSolutions 2023-2024 program rate.
    https://www.masssave.com/saving/connected-solutions

  ISO_NE_CAPACITY_PRICE_USD_PER_KW_MONTH:
    ISO-NE FCA #17 (2026/27) clearing price, ~$3.50/kW-month estimated.
    https://www.iso-ne.com/markets-operations/markets/forward-capacity-market

  PEAK_LMP_USD_PER_MWH:
    Representative peak-hour LMP, Boston Hub, August 2024.
    https://www.iso-ne.com/isoexpress/

  AVG_LMP_USD_PER_MWH:
    ISO-NE annual average LMP, 2023.
    https://www.iso-ne.com/isoexpress/

  MARGINAL_EMISSIONS_FACTOR_KG_CO2_PER_MWH:
    EPA eGRID 2022 marginal emissions factor for NEWE (New England).
    https://www.epa.gov/egrid

  EJ_CAP_DEFAULT_PCT:
    Default equity constraint: load from EJ zips ≤ 35% per event.
    Per project equity design doc.
"""

# --- Payment rate ---
CONN_SOLUTIONS_RATE_USD_PER_KW: float = 50.0  # $/kW-month, summer peak
CONN_SOLUTIONS_SOURCE_ID: str = "mass_save_connected_solutions_2023"

# --- Avoided cost ---
ISO_NE_CAPACITY_PRICE_USD_PER_KW_MONTH: float = 3.50  # $/kW-month
ISO_NE_PEAK_LMP_USD_PER_MWH: float = 150.0  # $/MWh, peak hour
ISO_NE_AVG_LMP_USD_PER_MWH: float = 45.0    # $/MWh, annual average
ISO_NE_SOURCE_ID: str = "iso_ne_fca17_lmp_2024"

# --- Emissions ---
MARGINAL_EMISSIONS_FACTOR_KG_CO2_PER_MWH: float = 285.0  # kg CO2/MWh, gas peaker
EMISSIONS_SOURCE_ID: str = "epa_egrid_2022_newe"

# --- Equity ---
EJ_CAP_DEFAULT_PCT: float = 0.35  # 35%

# --- Load estimation by property type ---
# kW per 1000 sq ft, estimated from ASHRAE typical peak loads.
# source: ashrae_hvac_applications_2023
LOAD_KW_PER_1000_SQFT_BY_TYPE: dict[str, float] = {
    "office":       3.5,
    "retail":       4.0,
    "hotel":        2.5,
    "warehouse":    1.2,
    "multifamily":  1.8,
    "school":       2.8,
    "hospital":     6.0,
    "lab":          8.0,
    "default":      2.5,
}
LOAD_TYPE_SOURCE_ID: str = "ashrae_hvac_applications_2023"

# --- Protected facility types (excluded when heat threshold exceeded) ---
PROTECTED_PROPERTY_TYPES: set[str] = {
    "K-12 School",
    "SCHOOL",
    "PRIV SCHOOL /COLLEGE",
    "Pre-school/Daycare",
    "Adult Education",
    "NURSING HOME",
    "REHAB/COVALES FACILITY",
    "ELDERLY HOME",
    "Residential Care Facility",
    "Senior Care Community",
    "Senior Living Community",
    "HOSPITAL",
    "Hospital (General Medical & Surgical)",
    "MEDICAL CLINIC",
}

# --- Extreme heat threshold ---
EXTREME_HEAT_TEMP_F: float = 95.0  # °F at Boston buoy 44013

ASSUMPTIONS: dict[str, str] = {
    "paid_to_buildings": (
        f"kW reduced × ${CONN_SOLUTIONS_RATE_USD_PER_KW}/kW-month (Mass Save "
        f"ConnectedSolutions published rate). Assumes full delivery. Labeled estimated."
    ),
    "avoided_system_cost": (
        f"MW shed × ${ISO_NE_CAPACITY_PRICE_USD_PER_KW_MONTH}/kW-month × 12 "
        f"+ MWh shed × (${ISO_NE_PEAK_LMP_USD_PER_MWH} peak LMP − "
        f"${ISO_NE_AVG_LMP_USD_PER_MWH} avg LMP). ISO-NE FCA17 & 2024 LMPs. "
        f"Labeled estimated."
    ),
    "co2_avoided": (
        f"MWh shed × {MARGINAL_EMISSIONS_FACTOR_KG_CO2_PER_MWH} kg CO2/MWh "
        f"(EPA eGRID 2022 NEWE marginal factor). Labeled estimated."
    ),
}

# --- EJ source ---
EJ_SOURCE_ID: str = "massgis_ej_2020"
