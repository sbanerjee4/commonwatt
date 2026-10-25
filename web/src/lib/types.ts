// Response shapes returned by the Commonwatt API (app/routes/portfolio.py).
// Every numeric field that the UI renders carries a source_id (provenance).

export type SourcedNumber = { value: number; source_id: string }

export type ZipAggregate = {
  zip: string
  buildingCount: number
  curtailableLoadKw: SourcedNumber | null
  ejStatus: 'ej' | 'non_ej' | 'unknown'
  medianIncome?: number | null
  affluenceTier?: 'low' | 'middle' | 'high' | 'unknown'
  incomeSourceId?: string | null
  cumulativeCalls: number
  hasGeometry: boolean
}

export type ZipsResponse = {
  zips: ZipAggregate[]
  source_id: string
}

export type BuildingMarkerLoad = {
  value: number
  source_id: string
  basis: 'metered' | 'estimated_from_type' | 'unknown'
}

export type BuildingMarker = {
  buildingId: string
  address: string
  zip: string | null
  lngLat: [number, number] | null
  propertyType: string | null
  grossAreaSf: number | null
  curtailableLoadKw: BuildingMarkerLoad | null
  affluenceTier?: 'low' | 'middle' | 'high' | 'unknown'
  medianIncome?: number | null
  canAbsorb?: boolean
  shouldProtect?: boolean
}

export type ZipBuildingsResponse = {
  zip: string
  buildings: BuildingMarker[]
}

export type SavingsCounter = {
  key: string
  value_label: string
  estimated: boolean
  assumptions: string
  source_id: string
  value_usd?: number
  value_mt?: number
}

export type SavingsResponse = {
  shed_mw: number
  event_duration_hours: number
  counters: SavingsCounter[]
}

export type RecruitmentCandidate = {
  building_id: string
  address: string
  zip: string | null
  property_type: string | null
  curtailable_load_kw: number | null
  load_basis: 'metered' | 'estimated_from_type' | 'unknown'
  is_ej: boolean
  median_income: number | null
  affluence_tier: 'low' | 'middle' | 'high' | 'unknown'
  is_commercial: boolean
  socioeconomic_priority: number
  income_source_id: string | null
}

export type RecruitmentResponse = {
  simulated_enrollment: boolean
  ej_zip_count: number
  total_ej_buildings: number
  top_candidates: RecruitmentCandidate[]
  source_id: string
}

// POST /event/draft — planner/critic result
export type TraceStep = {
  ts: string
  kind: 'forecast' | 'plan' | 'constraint_check' | 'self_correct'
  summary: string
  planVersion?: number | null
  toolName?: string | null
  rejectedBy?: string | null
}

export type EventPlan = {
  version: number
  targetMw: number
  achievedMw: number
  buildingCount: number
  ejSharePct: number
  ejCapPct: number
  reachable: boolean
  tradeoff?: string | null
  portfolio: Array<Record<string, unknown>>
  source_id: string
}

export type EventDraftResponse = {
  approved: boolean
  iterations: number
  criticReason?: string | null
  plan: EventPlan | null
  trace: TraceStep[]
}

// GET /portfolio/buildings — all buildings as map markers
export type MapBuilding = {
  buildingId: string
  address: string
  zip: string | null
  lngLat: [number, number] | null
  propertyType: string | null
  grossAreaSf: number | null
  curtailableLoadKw: BuildingMarkerLoad | null
  affluenceTier: 'low' | 'middle' | 'high' | 'unknown'
  medianIncome: number | null
  isEj: boolean
  canAbsorb: boolean
  shouldProtect: boolean
}

export type AllBuildingsResponse = {
  buildings: MapBuilding[]
  placed: number
  total: number
  geocode_source_id: string
}
