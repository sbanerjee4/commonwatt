import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { AppHeader, Heading, Panel, Tag } from '../components/ui'
import { BuildingMap } from '../components/BuildingMap'
import { ChatThread } from '../components/ChatThread'
import { apiGet, apiPost } from '../lib/api'
import { getUnread } from '../lib/chat'
import { regionForZip, siteTypeFor } from '../lib/grouping'
import type {
SavingsResponse, RecruitmentResponse,
  EventDraftResponse,
  AllBuildingsResponse,
  MapBuilding,
} from '../lib/types'


// One or two sentences describing what the proposal changes, built from the
// live plan + trace — no invented numbers.
function buildProposalSummary(data: EventDraftResponse): string {
  const p = data.plan
  if (!p) return ''
  const lead =
    `This proposal asks ${p.buildingCount} buildings to reduce ` +
    `${p.achievedMw.toFixed(1)} MW (target ${p.targetMw} MW), with ` +
    `${p.ejSharePct.toFixed(1)}% of load from equity-priority zips (cap ${p.ejCapPct.toFixed(0)}%).`
  const correction = data.trace.find((s) => s.kind === 'self_correct')
  return correction ? `${lead} ${correction.summary}` : lead
}

function MapPanel() {
  return (
    <Panel title="Portfolio map" className="map-panel">
      <BuildingMap />
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
      <p className="caption panel-caption panel-caption-below">
        Buildings ranked by how much peak load they could reduce — the agent's suggested recruits
        for an upcoming event. Curtailable load is estimated from building type; enrollment is simulated.
      </p>
    </Panel>
  )
}

// Pull a sensible default building id out of the drafted plan's portfolio,
// so the operator composer is pre-filled with a building that is in the event.
function OperatorAndAgent() {
  const [targetMw, setTargetMw] = useState(20)
  const [showReasoning, setShowReasoning] = useState(false)

  const draft = useMutation({
    mutationFn: (target: number) =>
      apiPost<EventDraftResponse>(
        '/event/draft',
        { target_mw: target, ej_cap_pct: 0.35, current_temp_f: 88, window_label: '5–7 PM' },
        { 'X-Role': 'operator' },
      ),
    onSuccess: () => approve.reset(),
  })

  const approve = useMutation({
    mutationFn: (target: number) =>
      apiPost<{ ok: boolean; event_id: number; contacted: string[]; building_count: number }>(
        '/event/approve',
        { target_mw: target, ej_cap_pct: 0.35, current_temp_f: 88, window_label: '5–7 PM' },
        { 'X-Role': 'operator' },
      ),
  })

  const data = draft.data
  const plan = data?.plan
  const fmtTime = (ts: string) => {
    try {
      return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    } catch {
      return ts
    }
  }

  return (
    <>
      <Panel
        title="Operator approval"
        className="operator-panel"
        tools={<Tag tone="attention">Agent recommendation</Tag>}
      >
        <p className="agent-origin">
          The planning agent prepares an event proposal from live building data. Nothing is sent to
          facilities until an operator approves it.
        </p>

        <label className="slider-label">
          <span>
            Target <b>{targetMw} MW</b>
          </span>
          <input
            type="range"
            min={5}
            max={40}
            value={targetMw}
            onChange={(e) => setTargetMw(Number(e.target.value))}
          />
        </label>

        <div className="action-row">
          <button
            className="ui-button primary"
            onClick={() => draft.mutate(targetMw)}
            disabled={draft.isPending}
          >
            {draft.isPending ? 'Planning…' : 'Draft proposal'}
          </button>
        </div>

        {draft.isError && (
          <p className="caption">
            Could not reach the planner. Is `make serve` running, and is the Bedrock key set?
          </p>
        )}

        {plan && (
          <>
            {data && <p className="proposal-summary">{buildProposalSummary(data)}</p>}
            <div className="event-facts">
              <div>
                <span>Target</span>
                <b>{plan.targetMw} MW</b>
              </div>
              <div>
                <span>Achieved</span>
                <b>{plan.achievedMw.toFixed(1)} MW</b>
              </div>
              <div>
                <span>Buildings</span>
                <b>{plan.buildingCount}</b>
              </div>
              <div>
                <span>EJ share</span>
                <b>
                  {plan.ejSharePct.toFixed(1)}% / {plan.ejCapPct.toFixed(0)}% cap
                </b>
              </div>
            </div>
            {!plan.reachable && plan.tradeoff && (
              <p className="caption">
                <strong>Unreachable under cap:</strong> {plan.tradeoff}
              </p>
            )}
            <div className="action-row">
              <button
                className="ui-button primary"
                onClick={() => approve.mutate(targetMw)}
                disabled={approve.isPending || !plan.reachable}
              >
                {approve.isPending ? 'Approving…' : 'Approve'}
              </button>
              <button className="ui-button ghost" onClick={() => { draft.reset(); approve.reset() }}>
                Reject
              </button>
              {data && (
                <button
                  className="ui-button secondary"
                  aria-expanded={showReasoning}
                  onClick={() => setShowReasoning(true)}
                >
                  Expand reasoning
                </button>
              )}
            </div>
            {approve.isError && (
              <p className="caption">Could not approve the event. Please try again.</p>
            )}
            {approve.data && (
              <div className="confirmation">
                ✓ Event approved · {plan.achievedMw.toFixed(1)} MW across {approve.data.building_count} buildings
                <span>{approve.data.building_count} building managers contacted automatically · {plan.source_id}</span>
              </div>
            )}
          </>
        )}
      </Panel>

      <Panel
        title="Planning agent"
        className="agent-panel"
        tools={<Tag>{data ? (data.approved ? 'Approved by critic' : 'Needs review') : 'Idle'}</Tag>}
      >
        {!data ? (
          <p className="caption">
            Draft a proposal to run the planning agent. Its reasoning trace (forecast → plan →
            constraint check → self-correct → revised plan) opens from <b>Expand reasoning</b> once a
            proposal exists.
          </p>
        ) : (
          <p className="caption reasoning-collapsed-hint">
            {data.trace.length} steps retained across {data.iterations} iteration(s). Select{' '}
            <b>Expand reasoning</b> on the proposal to inspect the full agent trace.
          </p>
        )}
      </Panel>

      {data && showReasoning && (
        <div className="reasoning-drawer-root" role="dialog" aria-modal="true" aria-label="Agent reasoning trace">
          <div className="reasoning-backdrop" onClick={() => setShowReasoning(false)} />
          <aside className="reasoning-drawer">
            <div className="reasoning-drawer-head">
              <div>
                <strong>Agent reasoning</strong>
                <small>{data.trace.length} steps · {data.iterations} iteration(s)</small>
              </div>
              <button
                type="button"
                className="ui-button ghost"
                onClick={() => setShowReasoning(false)}
              >
                Hide
              </button>
            </div>
            <ol className="trace-list">
              {data.trace.map((step, index) => {
                const isRevision = step.kind === 'self_correct'
                return (
                  <li className={isRevision ? 'revision' : ''} key={`${step.ts}-${index}`}>
                    <time>{fmtTime(step.ts)}</time>
                    <div>
                      <strong>
                        {step.kind === 'plan' && step.planVersion
                          ? `Plan v${step.planVersion}`
                          : step.kind.replace(/_/g, ' ')}
                      </strong>
                      {step.rejectedBy && <Tag tone="attention">Rejected: {step.rejectedBy}</Tag>}
                      <p>{step.summary}</p>
                    </div>
                    {step.toolName && <code>{step.toolName}</code>}
                  </li>
                )
              })}
            </ol>
          </aside>
        </div>
      )}
    </>
  )
}

// Tiny unread indicator for a facility in the conversations list. Polls
// GET /inbox/{buildingId}/unread?since=0 every 4s (cookie auth, no role
// headers) and renders a dot only when there is unread activity.
function UnreadDot({ buildingId }: { buildingId: string }) {
  const unread = useQuery({
    queryKey: ['unread', buildingId],
    queryFn: () => getUnread(buildingId, 0),
    refetchInterval: 4000,
    retry: false,
  })

  if (!unread.data || unread.data.unread <= 0) return null
  return <span className="unread-dot" aria-label={`${unread.data.unread} unread`} />
}

type ConvoGroupBy = 'region' | 'site' | 'zip'

// Assign a facility to a group label for the chosen Group-by. All three
// options read existing building fields only (zip, propertyType) via the
// shared grouping helpers — no owner or facility-manager data is involved.
function groupLabelFor(b: MapBuilding, groupBy: ConvoGroupBy): string {
  if (groupBy === 'region') return regionForZip(b.zip)
  if (groupBy === 'site') return siteTypeFor(b.propertyType)
  return b.zip ?? 'Unknown'
}

// Operator "Facility conversations" panel: browse the whole portfolio grouped
// by region / site type / zip, filter by a search box, then pick a facility to
// open its live conversation thread on the right.
function ConversationsPanel() {
  const [groupBy, setGroupBy] = useState<ConvoGroupBy>('region')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState('')
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})

  const buildings = useQuery({
    queryKey: ['all-buildings-convos'],
    queryFn: () => apiGet<AllBuildingsResponse>('/portfolio/buildings'),
  })

  const term = search.trim().toLowerCase()
  const facilities = (buildings.data?.buildings ?? []).filter((b) => {
    if (!term) return true
    const address = b.address.toLowerCase()
    const id = b.buildingId.toLowerCase()
    return address.includes(term) || id.includes(term)
  })

  // Build groups in stable insertion order so the list ordering is predictable.
  const groups = new Map<string, MapBuilding[]>()
  for (const b of facilities) {
    const label = groupLabelFor(b, groupBy)
    const bucket = groups.get(label)
    if (bucket) bucket.push(b)
    else groups.set(label, [b])
  }

  const toggleGroup = (label: string) =>
    setCollapsed((prev) => ({ ...prev, [label]: !(prev[label] ?? true) }))

  return (
    <Panel
      title="Facility conversations"
      className="conversations-panel"
      tools={<Tag>Live inbox</Tag>}
    >
      <div className="conversations-body">
        <div className="conversations-list">
          <div className="convos-controls">
            <label>
              Group by
              <select value={groupBy} onChange={(e) => setGroupBy(e.target.value as ConvoGroupBy)}>
                <option value="region">Region</option>
                <option value="site">Site type</option>
                <option value="zip">Zip</option>
              </select>
            </label>
            <input
              type="search"
              value={search}
              placeholder="Search by address or building id"
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          {buildings.isLoading && <p className="caption">Loading facilities…</p>}
          {buildings.isError && (
            <p className="caption">Could not load facilities. Make sure you are signed in.</p>
          )}
          {!buildings.isLoading && !buildings.isError && groups.size === 0 && (
            <p className="caption">No facilities match this search.</p>
          )}

          {[...groups.entries()].map(([label, items]) => {
            const isCollapsed = collapsed[label] ?? true
            return (
              <div className="convo-group" key={label}>
                <button
                  className="convo-group-heading"
                  aria-expanded={!isCollapsed}
                  onClick={() => toggleGroup(label)}
                >
                  <span>{label}</span>
                  <span className="convo-group-count">{items.length}</span>
                </button>
                {!isCollapsed &&
                  items.map((b) => (
                    <button
                      key={b.buildingId}
                      className={`conversation-item ${selected === b.buildingId ? 'active' : ''}`.trim()}
                      onClick={() => setSelected(b.buildingId)}
                    >
                      <span>{b.address}</span>
                      <UnreadDot buildingId={b.buildingId} />
                    </button>
                  ))}
              </div>
            )
          })}
        </div>

        <div className="conversations-detail">
          {selected ? (
            <ChatThread buildingId={selected} />
          ) : (
            <p className="caption">Select a facility to view its conversation.</p>
          )}
        </div>
      </div>
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
          <OperatorAndAgent />
          <SeasonPanel />
          <RecruitmentPanel />
          <ConversationsPanel />
        </div>
      </main>
    </div>
  )
}
