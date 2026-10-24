import { useEffect, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../lib/api'
import type { AllBuildingsResponse, MapBuilding } from '../lib/types'

type GroupBy = 'equity' | 'ej' | 'load'

const BOSTON_CENTER: [number, number] = [-71.057, 42.335]

function colorFor(b: MapBuilding, group: GroupBy): string {
  if (group === 'ej') return b.isEj ? '#17a398' : '#2563eb'
  if (group === 'load') {
    const kw = b.curtailableLoadKw?.value ?? 0
    return kw > 2000 ? '#e63946' : kw > 500 ? '#f4a261' : '#2563eb'
  }
  switch (b.affluenceTier) {
    case 'low': return '#17a398'
    case 'middle': return '#2563eb'
    case 'high': return '#f59e0b'
    default: return '#64748b'
  }
}

export function BuildingMap() {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const markersRef = useRef<maplibregl.Marker[]>([])
  const loadedRef = useRef(false)
  const [group, setGroup] = useState<GroupBy>('equity')
  const [tick, setTick] = useState(0)

  const query = useQuery({
    queryKey: ['all-buildings'],
    queryFn: () => apiGet<AllBuildingsResponse>('/portfolio/buildings'),
  })

  // init map once
  useEffect(() => {
    if (mapRef.current || !containerRef.current) return
    const map = new maplibregl.Map({
      container: containerRef.current,
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
    const done = () => { loadedRef.current = true; setTick((t) => t + 1) }
    if (map.loaded()) done()
    else map.on('load', done)
    mapRef.current = map
    return () => { map.remove(); mapRef.current = null; loadedRef.current = false }
  }, [])

  // (re)place HTML markers whenever data / grouping changes
  useEffect(() => {
    const map = mapRef.current
    if (!map || !loadedRef.current || !query.data) return

    // clear old markers
    for (const m of markersRef.current) m.remove()
    markersRef.current = []

    const buildings = query.data.buildings.filter((b) => b.lngLat)
    // eslint-disable-next-line no-console
    console.log('[BuildingMap] placing', buildings.length, 'HTML markers')

    const bounds = new maplibregl.LngLatBounds()

    for (const b of buildings) {
      const [lng, lat] = b.lngLat as [number, number]
      const kw = b.curtailableLoadKw?.value ?? 0
      const size = Math.max(14, Math.min(46, 14 + Math.sqrt(kw) * 0.7))

      const el = document.createElement('div')
      el.className = 'bldg-dot'
      el.style.width = `${size}px`
      el.style.height = `${size}px`
      el.style.background = colorFor(b, group)

      const income = b.medianIncome ? `$${(b.medianIncome / 1000).toFixed(0)}k median income` : 'income n/a'
      const kwLabel = kw ? `${kw.toLocaleString()} kW curtailable` : 'load unknown'
      const html =
        `<div class="bldg-popup">` +
        `<strong>${b.address}</strong>` +
        `<div>${b.propertyType ?? 'Building'}${b.zip ? ' · ' + b.zip : ''}</div>` +
        `<div>${income} · <b>${b.affluenceTier}</b> income</div>` +
        `<div>${kwLabel}</div>` +
        (b.isEj ? `<div class="bldg-popup-ej">EJ zip — protected</div>` : '') +
        `</div>`

      // Attaching the popup to the marker makes the whole dot clickable
      // reliably (MapLibre forwards the marker click to its popup).
      const popup = new maplibregl.Popup({ closeButton: true, offset: 16 }).setHTML(html)
      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([lng, lat])
        .setPopup(popup)
        .addTo(map)
      markersRef.current.push(marker)
      bounds.extend([lng, lat])
    }

    if (buildings.length > 0) {
      map.fitBounds(bounds, { padding: 40, maxZoom: 13, duration: 0 })
    }
  }, [query.data, group, tick])

  const shown = query.data?.buildings.filter((b) => b.lngLat).length ?? 0

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
          {query.isLoading ? 'Loading buildings…' : query.isError ? 'Could not reach the API' : `${shown.toLocaleString()} buildings shown`}
        </span>
      </div>

      <div ref={containerRef} className="map-canvas" />

      <div className="legend map-legend">
        {group === 'equity' && (
          <>
            <strong>Median income — who we lean on vs protect</strong>
            <span><i style={{ background: '#f59e0b' }} /> Higher income — ask first</span>
            <span><i style={{ background: '#2563eb' }} /> Middle income</span>
            <span><i style={{ background: '#17a398' }} /> Lower income — protect</span>
          </>
        )}
        {group === 'ej' && (
          <>
            <strong>Environmental Justice status</strong>
            <span><i style={{ background: '#17a398' }} /> EJ zip — protect</span>
            <span><i style={{ background: '#2563eb' }} /> Non-EJ</span>
          </>
        )}
        {group === 'load' && (
          <>
            <strong>Available load (circle size = kW)</strong>
            <span><i style={{ background: '#e63946' }} /> High</span>
            <span><i style={{ background: '#f4a261' }} /> Medium</span>
            <span><i style={{ background: '#2563eb' }} /> Low</span>
          </>
        )}
      </div>
    </div>
  )
}
