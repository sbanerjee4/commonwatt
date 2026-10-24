import { useEffect, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../lib/api'
import type { AllBuildingsResponse, MapBuilding } from '../lib/types'

type GroupBy = 'equity' | 'ej' | 'load'

const BOSTON_CENTER: [number, number] = [-71.057, 42.335]

// Colorblind-safe palette. Equity: low income = protect (teal), high = ask-first (amber).
function colorFor(b: MapBuilding, group: GroupBy): string {
  if (group === 'ej') return b.isEj ? '#2a9d8f' : '#9aa0a6'
  if (group === 'load') {
    const kw = b.curtailableLoadKw?.value ?? 0
    return kw > 2000 ? '#e76f51' : kw > 500 ? '#e9c46a' : '#8ab4c4'
  }
  // equity by affluence tier
  switch (b.affluenceTier) {
    case 'low': return '#2a9d8f'    // protect
    case 'middle': return '#8ab4c4'
    case 'high': return '#e9a23b'   // ask first
    default: return '#9aa0a6'
  }
}

export function BuildingMap() {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const [group, setGroup] = useState<GroupBy>('equity')
  const [ready, setReady] = useState(false)

  const query = useQuery({
    queryKey: ['all-buildings'],
    queryFn: () => apiGet<AllBuildingsResponse>('/portfolio/buildings'),
  })

  // init map once
  useEffect(() => {
    if (mapRef.current || !containerRef.current) return
    const map = new maplibregl.Map({
      container: containerRef.current,
      // Keyless raster basemap (OSM tiles via the demo style). No token needed.
      style: {
        version: 8,
        sources: {
          osm: {
            type: 'raster',
            tiles: ['https://a.tile.openstreetmap.org/{z}/{x}/{y}.png'],
            tileSize: 256,
            attribution: '© OpenStreetMap contributors',
          },
        },
        layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
      },
      center: BOSTON_CENTER,
      zoom: 11,
    })
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    map.on('load', () => setReady(true))
    mapRef.current = map
    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  // (re)build the GeoJSON source + layer when data or grouping changes
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready || !query.data) return

    const features = query.data.buildings
      .filter((b) => b.lngLat)
      .map((b) => ({
        type: 'Feature' as const,
        geometry: { type: 'Point' as const, coordinates: b.lngLat as [number, number] },
        properties: {
          color: colorFor(b, group),
          address: b.address,
          tier: b.affluenceTier,
          income: b.medianIncome ?? 0,
          ej: b.isEj ? 'yes' : 'no',
          kw: b.curtailableLoadKw?.value ?? 0,
          type: b.propertyType ?? '',
        },
      }))

    const data = { type: 'FeatureCollection' as const, features }
    const existing = map.getSource('buildings') as maplibregl.GeoJSONSource | undefined
    if (existing) {
      existing.setData(data)
      return
    }

    map.addSource('buildings', { type: 'geojson', data })
    map.addLayer({
      id: 'building-pins',
      type: 'circle',
      source: 'buildings',
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['get', 'kw'], 0, 3, 2000, 9],
        'circle-color': ['get', 'color'],
        'circle-opacity': 0.82,
        'circle-stroke-width': 0.5,
        'circle-stroke-color': '#1a1a1a',
      },
    })

    const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: true })
    map.on('click', 'building-pins', (e: maplibregl.MapLayerMouseEvent) => {
      const f = e.features?.[0]
      if (!f) return
      const p = f.properties as Record<string, string>
      const income = Number(p.income) ? `$${(Number(p.income) / 1000).toFixed(0)}k median income` : 'income n/a'
      const kw = Number(p.kw) ? `${Number(p.kw).toLocaleString()} kW curtailable` : 'load unknown'
      popup
        .setLngLat((f.geometry as { coordinates: [number, number] }).coordinates)
        .setHTML(
          `<strong>${p.address}</strong><br/>${p.type}<br/>${income} · ${p.tier}` +
            `<br/>${kw}${p.ej === 'yes' ? '<br/><em>EJ zip — protected</em>' : ''}`,
        )
        .addTo(map)
    })
    map.on('mouseenter', 'building-pins', () => (map.getCanvas().style.cursor = 'pointer'))
    map.on('mouseleave', 'building-pins', () => (map.getCanvas().style.cursor = ''))
  }, [ready, query.data, group])

  const placed = query.data?.placed ?? 0
  const total = query.data?.total ?? 0

  return (
    <div className="building-map">
      <div className="map-controls">
        <label>
          Group by
          <select value={group} onChange={(e) => setGroup(e.target.value as GroupBy)}>
            <option value="equity">Equity (income)</option>
            <option value="ej">EJ status</option>
            <option value="load">Available load</option>
          </select>
        </label>
        <span className="map-meta">
          {query.isLoading ? 'Loading buildings…' : `${placed.toLocaleString()} of ${total.toLocaleString()} placed`}
        </span>
      </div>

      <div ref={containerRef} className="map-canvas" />

      <div className="legend map-legend">
        {group === 'equity' && (
          <>
            <strong>Median income — who we lean on vs protect</strong>
            <span><i style={{ background: '#e9a23b' }} /> Higher income — ask first</span>
            <span><i style={{ background: '#8ab4c4' }} /> Middle income</span>
            <span><i style={{ background: '#2a9d8f' }} /> Lower income — protect</span>
          </>
        )}
        {group === 'ej' && (
          <>
            <strong>Environmental Justice status</strong>
            <span><i style={{ background: '#2a9d8f' }} /> EJ zip — protect</span>
            <span><i style={{ background: '#9aa0a6' }} /> Non-EJ</span>
          </>
        )}
        {group === 'load' && (
          <>
            <strong>Available load (pin size = kW)</strong>
            <span><i style={{ background: '#e76f51' }} /> High</span>
            <span><i style={{ background: '#e9c46a' }} /> Medium</span>
            <span><i style={{ background: '#8ab4c4' }} /> Low</span>
          </>
        )}
      </div>
    </div>
  )
}
