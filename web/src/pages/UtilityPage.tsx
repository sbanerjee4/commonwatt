import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AppHeader, Heading, Panel, Tag } from '../components/ui'
import { apiGet } from '../lib/api'
import type { ZipsResponse, ZipBuildingsResponse, SavingsResponse, RecruitmentResponse } from '../lib/types'

// --- Agent trace (static sample; POST /event/draft wiring is a follow-up pass) ---
const trace: Array<[string, string, string, string]> = [
  ['14:02:11', 'Forecast', 'Peak risk detected for 5–7 PM.', 'grid.forecast'],
  ['14:02:14', 'Plan v1', 'Proposed 40 MW across 126 buildings.', 'plan.compose'],
  ['14:02:16', 'Portfolio check', 'Repeated requests detected for two building groups.', 'portfolio.check'],
  ['14:02:18', 'Self-correct', 'Rebalanced 18 buildings to broaden participation.', 'plan.revise'],
  ['14:02:21', 'Plan v2', '40 MW target met across 108 available buildings.', 'plan.compose'],
]

function MapPanel() {
  const zips = useQuery({ queryKey: ['zips'], queryFn: () => apiGet<ZipsResponse>('/zips') })
  const [selectedZip, setSelectedZip] = useState<string | null>(null)

  const drill = useQuery({
    queryKey: ['zip-buildings', selectedZip],
    queryFn: () => apiGet<ZipBuildingsResponse>(`/zips/${selectedZip}/buildings`),
    enabled: selectedZip !== null,
  })

  // Buildings whose load couldn't be geocoded/placed go to the orphan list,
  // never silently dropped (AC-12b). Markers lack lngLat today (BFF returns
  // null), so the drill-in shows the building list rather than map pins.
  const markers = drill.data?.buildings ?? []
  const orphanCount = markers.filter((b) => b.lngLat === null).length

  return (
    <Panel
      title="Portfolio grid"
      className="map-panel"
      tools={
        <div className="segmented">
          <span className="active">Available load</span>
          <span>Building type</span>
          <span>Previous requests</span>
        </div>
      }
    >
      <div className="map-placeholder grid-view">
        {zips.isLoading && <p className="caption">Loading zip aggregates…</p>}
        {zips.isError && (
          <p className="caption">
            Could not reach the API. Locally, run `make serve` (port 8000). On a deployed site, set
            VITE_API_BASE_URL to the backend URL.
          </p>
        )}
        {zips.data && (
          <div className="grid-map" aria-label="Zip aggregates from the portfolio">
            {zips.data.zips.slice(0, 12).map((z, index) => (
              <button
                type="button"
                key={z.zip ?? index}
                className={`grid-cell state-${index % 3}${selectedZip === z.zip ? ' selected' : ''}`}
                onClick={() => setSelectedZip(z.zip)}
              >
                <span>{z.zip || '—'}</span>
                <b>
                  {z.curtailableLoadKw ? `${z.curtailableLoadKw.value.toLocaleString()} kW` : 'Load unknown'}
                </b>
                <small>{z.ejStatus === 'ej' ? 'EJ zip' : 'Non-EJ'} · {z.buildingCount} bldgs</small>
              </button>
            ))}
          </div>
        )}
        <div className="legend">
          <strong>Portfolio status</strong>
          <span>
            <i className="pattern-a" /> Available
          </span>
          <span>
            <i className="pattern-b" /> Previously asked
          </span>
          <span>
            <i className="pattern-c" /> Not enrolled
          </span>
        </div>
        {selectedZip && (
          <article className="map-popover">
            <div>
              <strong>Zip {selectedZip}</strong>
              <Tag>Selected</Tag>
            </div>
            {drill.isLoading && <p>Loading buildings…</p>}
            {drill.data && <p>{drill.data.buildings.length} buildings in this zip</p>}
            {drill.data?.buildings[0] && (
              <div>
                <span>{drill.data.buildings[0].address}</span>
                <b>
                  {drill.data.buildings[0].curtailableLoadKw
                    ? `${drill.data.buildings[0].curtailableLoadKw.value} kW`
                    : 'Load unknown'}
                </b>
              </div>
            )}
          </article>
        )}
      </div>
      <div className="orphan-list">
        <strong>Ungrouped facilities</strong>
        <span>{orphanCount} buildings not yet placed on the map</span>
        <span>Geocoding pending</span>
      </div>
    </Panel>
  )
}

function SeasonPanel() {
  // Read the three savings counters from the live BFF. shed_mw=0 yields zeros
  // (AC-24); we request a nominal shed so the panel shows representative values.
  const savings = useQuery({
    queryKey: ['savings', 20, 3],
    queryFn: () => apiGet<SavingsResponse>('/savings?shed_mw=20&hours=3'),
  })

  const series = ['series-one', 'series-two', 'series-three']

  return (
    <Panel
      title="Season outcomes"
      className="report-panel season-expanded"
      tools={
        <div className="segmented">
          <span className="active">May–September</span>
          <span>Export report</span>
        </div>
      }
    >
      <div className="season-totals">
        {savings.isLoading && <p className="caption">Loading savings counters…</p>}
        {savings.data?.counters.map((c, i) => (
          <article key={c.key}>
            <div>
              <i className={series[i]} />
              <span>{c.key.replace(/_/g, ' ')}</span>
              {c.estimated && <Tag>Estimated</Tag>}
            </div>
            <strong>{c.value_label}</strong>
            <small title={c.assumptions}>ⓘ Method and assumptions · {c.source_id}</small>
          </article>
        ))}
      </div>
      <p className="caption">
        Estimated outcomes are calculated from event participation, system-cost assumptions, and
        published emissions factors. Each number carries its source id.
      </p>
    </Panel>
  )
}

function RecruitmentPanel() {
  const recruitment = useQuery({
    queryKey: ['recruitment', 8],
    queryFn: () => apiGet<RecruitmentResponse>('/recruitment?top_n=8'),
  })

  return (
    <Panel
      title="Recruitment candidates"
      className="table-panel"
      tools={<Tag>Simulated enrollment</Tag>}
    >
      <table>
        <thead>
          <tr>
            <th>Address</th>
            <th>Zip</th>
            <th>Type</th>
            <th>Curtailable load</th>
          </tr>
        </thead>
        <tbody>
          {recruitment.isLoading && (
            <tr>
              <td colSpan={4}>Loading candidates…</td>
            </tr>
          )}
          {recruitment.data?.top_candidates.map((b) => (
            <tr key={b.building_id}>
              <td>{b.address}</td>
              <td className="mono">{b.zip}</td>
              <td>{b.property_type}</td>
              <td className="mono">
                {b.curtailable_load_kw !== null ? `${b.curtailable_load_kw.toLocaleString()} kW` : 'Unknown'}
                {b.load_basis === 'estimated_from_type' && <Tag>Estimated</Tag>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  )
}

export function UtilityPage() {
  return (
    <div className="workspace">
      <AppHeader context="Utility operator" />
      <main className="dashboard">
        <div className="dashboard-title">
          <div>
            <p className="kicker">Event planning workspace</p>
            <Heading level={1}>Greater Boston portfolio</Heading>
          </div>
          <Tag>Draft · 14:02 ET</Tag>
        </div>
        <div className="dashboard-grid">
          <MapPanel />
          <Panel title="Operator approval" className="operator-panel" tools={<Tag tone="attention">Agent recommendation</Tag>}>
            <p className="agent-origin">
              The planning agent prepared this event proposal. Nothing is sent to facilities until an
              operator approves it.
            </p>
            <div className="event-facts">
              <div>
                <span>Event window</span>
                <b>5–7 PM</b>
              </div>
              <div>
                <span>Target</span>
                <b>40 MW</b>
              </div>
              <div>
                <span>Buildings</span>
                <b>108</b>
              </div>
              <div>
                <span>Expected response</span>
                <b>92%</b>
              </div>
            </div>
            <label className="slider-label">
              <span>
                Target <b>40 MW</b>
              </span>
              <input type="range" min={20} max={60} defaultValue={40} />
            </label>
            <div className="action-row">
              <button className="ui-button primary">Approve</button>
              <button className="ui-button secondary">Edit list</button>
              <button className="ui-button ghost">Reject</button>
            </div>
          </Panel>
          <Panel title="Planning agent" className="agent-panel" tools={<Tag>Ready for review</Tag>}>
            <div className="agent-evidence">
              <details open>
                <summary>
                  <span>Agent trace</span>
                  <small>5 steps · all versions retained</small>
                </summary>
                <ol className="trace-list">
                  {trace.map(([time, title, copy, tool], index) => (
                    <li className={index === 2 ? 'revision' : ''} key={time}>
                      <time>{time}</time>
                      <div>
                        <strong>{title}</strong>
                        {index === 2 && <Tag tone="attention">Revision trigger</Tag>}
                        <p>{copy}</p>
                      </div>
                      <code>{tool}</code>
                    </li>
                  ))}
                </ol>
              </details>
            </div>
          </Panel>
          <SeasonPanel />
          <RecruitmentPanel />
        </div>
      </main>
    </div>
  )
}
