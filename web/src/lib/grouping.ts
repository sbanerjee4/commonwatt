// Presentation-only grouping helpers shared by the map and the conversations
// browser. All functions are pure and operate over existing building data
// (zip, propertyType) — they never invent owner or facility-manager fields.

// Static Boston zip -> region map. The first matching bucket wins, so the
// bucket order below is significant (a zip listed in two buckets is assigned
// to whichever appears first here).
const REGION_BUCKETS: ReadonlyArray<readonly [string, ReadonlyArray<string>]> = [
  ['East Boston', ['02128']],
  ['Charlestown', ['02129']],
  [
    'Downtown / Central',
    ['02108', '02109', '02110', '02111', '02113', '02114', '02116', '02133', '02199', '02203', '02210', '02215'],
  ],
  ['South Boston', ['02127', '02210']],
  ['South End / Roxbury', ['02118', '02119', '02120', '02115']],
  ['Dorchester', ['02121', '02122', '02124', '02125']],
  ['Mattapan / Hyde Park', ['02126', '02136']],
  ['Jamaica Plain / West Roxbury', ['02130', '02131', '02132', '02135', '02134']],
]

export function regionForZip(zip: string | null): string {
  if (!zip) return 'Other'
  for (const [region, zips] of REGION_BUCKETS) {
    if (zips.includes(zip)) return region
  }
  return 'Other'
}

// Normalize a BERDO property_type string into a coarse site-type bucket.
// Keyword matching mirrors server/data.py _load_factor (case-insensitive).
export function siteTypeFor(propertyType: string | null): string {
  const pt = (propertyType ?? '').toLowerCase()
  if (!pt) return 'Other'
  if (pt.includes('office') || pt.includes('admin')) return 'Office'
  if (pt.includes('manufactur') || pt.includes('industrial') || pt.includes('plant')) {
    return 'Industrial / Plant'
  }
  if (pt.includes('warehouse') || pt.includes('storage') || pt.includes('distribution')) {
    return 'Warehouse'
  }
  if (pt.includes('retail') || pt.includes('store') || pt.includes('shop') || pt.includes('market')) {
    return 'Retail'
  }
  if (
    pt.includes('apart') ||
    pt.includes('multifamily') ||
    pt.includes('resid') ||
    pt.includes('condo') ||
    pt.includes('apt')
  ) {
    return 'Residential'
  }
  if (
    pt.includes('school') ||
    pt.includes('college') ||
    pt.includes('university') ||
    pt.includes('education') ||
    pt.includes('daycare')
  ) {
    return 'Education'
  }
  if (
    pt.includes('hospital') ||
    pt.includes('medical') ||
    pt.includes('clinic') ||
    pt.includes('health') ||
    pt.includes('nursing')
  ) {
    return 'Healthcare'
  }
  if (pt.includes('lab')) return 'Lab'
  return 'Other'
}

// Colorblind-safe hex per site-type bucket. Distinct, accessible colors.
const SITE_TYPE_COLORS: Record<string, string> = {
  Office: '#3a7ca5',
  'Industrial / Plant': '#e76f51',
  Warehouse: '#8a6d3b',
  Retail: '#e9a23b',
  Residential: '#2a9d8f',
  Education: '#6a4c93',
  Healthcare: '#c1446a',
  Lab: '#577590',
  Other: '#9aa0a6',
}

export function siteTypeColor(siteType: string): string {
  return SITE_TYPE_COLORS[siteType] ?? SITE_TYPE_COLORS.Other
}
