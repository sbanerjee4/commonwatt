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

// One or two sentences describing what the proposal changes, for at-a-glance
// explainability. Derived from the trace's self-correction.
const proposalSummary =
  'This proposal asks 108 buildings to reduce 40 MW during the 5–7 PM peak. ' +
  'An initial 126-building plan was rebalanced to broaden participation after two groups were asked too often.'

// --- Reasoning knowledge graph: the causes that led to the final proposal. ---
// Each node is a factor or decision; edges point cause -> effect, ending at the
// final proposal. Positions are on a 0–100 grid (x = left→right flow).
type GraphNode = {
  id: string
  label: string
  kind: 'signal' | 'check' | 'decision' | 'proposal'
  x: number
  y: number
  anchor?: 'start' | 'middle' | 'end'
}
type GraphEdge = { from: string; to: string; label?: string }

const graphNodes: GraphNode[] = [
  { id: 'forecast', label: 'Peak risk 5–7 PM', kind: 'signal', x: 8, y: 20, anchor: 'start' },
  { id: 'target', label: 'Target 40 MW', kind: 'signal', x: 8, y: 70, anchor: 'start' },
  { id: 'v1', label: 'Plan v1 · 126 bldgs', kind: 'decision', x: 36, y: 20 },
  { id: 'check', label: 'Repeated-request check', kind: 'check', x: 36, y: 70 },
  { id: 'rebalance', label: 'Rebalance 18 bldgs', kind: 'decision', x: 58, y: 48, anchor: 'end' },
  { id: 'proposal', label: 'Proposal · 40 MW, 108 bldgs', kind: 'proposal', x: 92, y: 45, anchor: 'end' },
]

const graphEdges: GraphEdge[] = [
  { from: 'forecast', to: 'v1', label: 'drives' },
  { from: 'target', to: 'v1', label: 'sizes' },
  { from: 'v1', to: 'check', label: 'validated by' },
  { from: 'check', to: 'rebalance', label: 'flags fairness' },
  { from: 'v1', to: 'rebalance', label: 'revised' },
  { from: 'rebalance', to: 'proposal', label: 'yields' },
  { from: 'target', to: 'proposal', label: 'met' },
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
        {zips.isError && <p className="caption">Could not reach the BFF. Is `make bff` running on :8000?</p>}
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

function ReasoningGraph() {
  const [active, setActive] = useState<string | null>(null)
  const node = (id: string) => graphNodes.find((n) => n.id === id)!
  const connected = (id: string) =>
    graphEdges.some((e) => (e.from === id || e.to === id) && (e.from === active || e.to === active))
  const edgeActive = (e: GraphEdge) => active !== null && (e.from === active || e.to === active)
  const activeNode = active ? node(active) : null

  return (
    <div className="reasoning-graph">
      <svg viewBox="-6 2 112 92" role="img" aria-label="Reasoning knowledge graph" preserveAspectRatio="xMidYMid meet">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="currentColor" />
          </marker>
        </defs>
        {graphEdges.map((e, i) => {
          const a = node(e.from)
          const b = node(e.to)
          return (
            <g key={i} className={`edge ${edgeActive(e) ? 'edge-active' : ''}`}>
              <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} markerEnd="url(#arrow)" />
              {edgeActive(e) && e.label && (
                <text x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 1.5} className="edge-label">
                  {e.label}
                </text>
              )}
            </g>
          )
        })}
        {graphNodes.map((n) => {
          const isActive = active === n.id
          const dim = active !== null && !isActive && !connected(n.id)
          return (
            <g
              key={n.id}
              className={`gnode kind-${n.kind} ${isActive ? 'gnode-active' : ''} ${dim ? 'gnode-dim' : ''}`}
              onMouseEnter={() => setActive(n.id)}
              onMouseLeave={() => setActive(null)}
              onClick={() => setActive((cur) => (cur === n.id ? null : n.id))}
              tabIndex={0}
              onFocus={() => setActive(n.id)}
              role="button"
              aria-pressed={isActive}
            >
              <circle cx={n.x} cy={n.y} r={3.4} />
              <text
                x={n.anchor === 'start' ? n.x - 3.4 : n.anchor === 'end' ? n.x + 3.4 : n.x}
                y={n.y + 6.5}
                textAnchor={n.anchor ?? 'middle'}
                className="gnode-label"
              >
                {n.label}
              </text>
            </g>
          )
        })}
      </svg>
      <p className="graph-hint">
        {activeNode
          ? `${activeNode.label} — ${activeNode.kind}. Highlighted links show what it influenced.`
          : 'Hover or tap a node to trace how each cause fed into the final proposal.'}
      </p>
      <ul className="graph-legend">
        <li><i className="kind-signal" /> Signal</li>
        <li><i className="kind-check" /> Constraint check</li>
        <li><i className="kind-decision" /> Decision</li>
        <li><i className="kind-proposal" /> Proposal</li>
      </ul>
    </div>
  )
}

export function UtilityPage() {
  const [showReasoning, setShowReasoning] = useState(false)
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
              The planning agent prepared this draft proposal. Nothing is sent to facilities until an
              operator approves it.
            </p>
            <p className="proposal-summary">{proposalSummary}</p>
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
              <button className="ui-button primary">Draft proposal</button>
              <button className="ui-button secondary">Approve</button>
              <button className="ui-button ghost">Reject</button>
            </div>
          </Panel>
          <Panel
            title="Planning agent"
            className="agent-panel"
            tools={
              <button
                type="button"
                className="ui-button ghost reasoning-toggle"
                aria-expanded={showReasoning}
                onClick={() => setShowReasoning((v) => !v)}
              >
                {showReasoning ? 'Hide reasoning' : 'Show reasoning'}
              </button>
            }
          >
            {!showReasoning && (
              <p className="caption reasoning-collapsed-hint">
                The agent retained every step and the causes behind this proposal.
                Select <b>Show reasoning</b> to inspect the trace and the reasoning graph.
              </p>
            )}
            {showReasoning && (
              <div className="agent-evidence">
                <div className="reasoning-graph-wrap">
                  <div className="panel-subhead">
                    <span>Reasoning graph</span>
                    <small>causes → final proposal</small>
                  </div>
                  <ReasoningGraph />
                </div>
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
            )}
          </Panel>
          <SeasonPanel />
          <RecruitmentPanel />
        </div>
      </main>
    </div>
  )
}
