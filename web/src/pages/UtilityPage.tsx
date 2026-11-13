import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AppHeader, Heading, Panel, Tag } from '../components/ui'
import { BuildingMap } from '../components/BuildingMap'
import { ChatThread } from '../components/ChatThread'
import { apiGet, apiPost } from '../lib/api'
import { getUnread, plainText } from '../lib/chat'
import { regionForZip, siteTypeFor } from '../lib/grouping'
import type {
SavingsResponse, RecruitmentResponse, RecruitmentCandidate,
  EventDraftResponse, PlanRequest, CurrentEvent,
  AllBuildingsResponse,
  MapBuilding,
} from '../lib/types'


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
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const recruitment = useQuery({
    queryKey: ['recruitment', 8],
    queryFn: () => apiGet<RecruitmentResponse>('/recruitment?top_n=8'),
  })

  const candidates = recruitment.data?.top_candidates ?? []
  const selected = candidates.find((b) => b.building_id === selectedId) ?? null
  const selectedRank = selected ? candidates.findIndex((b) => b.building_id === selectedId) + 1 : 0

  return (
    <Panel
      title="Recruitment candidates"
      className="table-panel recruitment-panel"
      tools={<Tag>Simulated enrollment</Tag>}
    >
      <div className="recruitment-body">
        <div className="recruitment-table-wrap">
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
              {candidates.map((b) => (
                <tr
                  key={b.building_id}
                  className={`recruitment-row ${selectedId === b.building_id ? 'active' : ''}`.trim()}
                  onClick={() => setSelectedId(b.building_id)}
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      setSelectedId(b.building_id)
                    }
                  }}
                >
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
        </div>

        <aside className="recruitment-detail">
          {!selected ? (
            <p className="caption recruitment-detail-empty">Select a building to see more.</p>
          ) : (
            <RecruitmentDetail candidate={selected} rank={selectedRank} total={candidates.length} />
          )}
        </aside>
      </div>

      <p className="caption panel-caption panel-caption-below">
        Buildings ranked by how much peak load they could reduce — the agent's suggested recruits
        for an upcoming event. Curtailable load is estimated from building type; enrollment is simulated.
      </p>
    </Panel>
  )
}

// Detail + "why this is a good candidate" for one recruitment candidate. Every
// line maps to a real field; income carries its ACS source id (provenance rule).
function RecruitmentDetail({
  candidate,
  rank,
  total,
}: {
  candidate: RecruitmentCandidate
  rank: number
  total: number
}) {
  const loadLabel =
    candidate.curtailable_load_kw !== null
      ? `${candidate.curtailable_load_kw.toLocaleString()} kW`
      : 'Unknown'
  const incomeLabel =
    candidate.median_income !== null ? `$${candidate.median_income.toLocaleString()}` : 'Unavailable'

  // Build the "why" from the ranking signals the backend actually uses:
  // socioeconomic_priority (= ability to absorb) then curtailable load.
  const reasons: string[] = []
  if (rank > 0) reasons.push(`Ranked #${rank} of ${total} candidates by curtailable load.`)
  if (candidate.curtailable_load_kw !== null && candidate.curtailable_load_kw >= 100)
    reasons.push(`High curtailable load (${loadLabel}) — a large, flexible reduction in one site.`)
  if (candidate.is_commercial)
    reasons.push('Commercial building — a reduction lands on operations, not residents.')
  if (candidate.affluence_tier === 'high')
    reasons.push('Higher-income area, so the ask falls where it is least burdensome.')
  if (candidate.affluence_tier === 'low')
    reasons.push('Lower-income area — include only with care; the program spares those a reduction hurts most.')
  if (reasons.length === 0)
    reasons.push('Eligible, unenrolled building with measurable curtailable load.')

  return (
    <div className="recruitment-detail-card">
      <header>
        <strong>{candidate.address}</strong>
        <small>
          {candidate.property_type ?? 'Unknown type'} · zip {candidate.zip ?? '—'}
        </small>
      </header>

      <dl className="recruitment-facts">
        <div>
          <dt>Curtailable load</dt>
          <dd>
            {loadLabel}
            {candidate.load_basis === 'estimated_from_type' && <Tag>Estimated</Tag>}
          </dd>
        </div>
        <div>
          <dt>Median income</dt>
          <dd>
            {incomeLabel}
            {candidate.income_source_id && <small className="src">· {candidate.income_source_id}</small>}
          </dd>
        </div>
        <div>
          <dt>Affluence tier</dt>
          <dd className="cap">{candidate.affluence_tier}</dd>
        </div>
        <div>
          <dt>EJ zip</dt>
          <dd>{candidate.is_ej ? 'Yes' : 'No'}</dd>
        </div>
      </dl>

      <div className="recruitment-why">
        <h4>Why it's a good candidate</h4>
        <ul>
          {reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      </div>
    </div>
  )
}

const DRAFT_INPUTS = { ej_cap_pct: 0.35, current_temp_f: 88, window_label: '5–7 PM' }
const fmtKw = (n: number) => `${Math.round(n).toLocaleString()} kW`

function whyRow(r: PlanRequest): string {
  const site = siteTypeFor(r.propertyType)
  const area = r.isEj ? 'EJ zip, within cap' : r.affluenceTier === 'high' ? 'higher-income area' : 'non-EJ zip'
  return `${site} · ${area}`
}

// Step 1–2: the utility states a need; the planner picks buildings under the
// equity rules; the operator reviews where the burden lands and approves.
function PlanPanel() {
  const qc = useQueryClient()
  const [targetMw, setTargetMw] = useState(5)
  const [showReasoning, setShowReasoning] = useState(false)
  const [showAll, setShowAll] = useState(false)

  const draft = useMutation({
    mutationFn: (target: number) =>
      apiPost<EventDraftResponse>('/event/draft', { target_mw: target, ...DRAFT_INPUTS }),
    onSuccess: () => approve.reset(),
  })
  const approve = useMutation({
    mutationFn: (target: number) =>
      apiPost<{ ok: boolean; event_id: number; building_count: number }>(
        '/event/approve', { target_mw: target, ...DRAFT_INPUTS }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['current-event'] }),
  })

  const data = draft.data
  const plan = data?.plan
  const eq = data?.equity
  const requests = eq?.requests ?? []
  const visible = showAll ? requests : requests.slice(0, 6)
  const capPct = plan?.ejCapPct ?? 35
  const fmtTime = (ts: string) => {
    try {
      return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    } catch {
      return ts
    }
  }

  return (
    <>
      <Panel title="1 · Plan the event" className="plan-panel" tools={<Tag tone="attention">Human approval required</Tag>}>
        <div className="plan-need">
          <label className="slider-label">
            <span>Reduction needed today, {DRAFT_INPUTS.window_label}: <b>{targetMw} MW</b></span>
            <input type="range" min={5} max={40} value={targetMw}
              onChange={(e) => setTargetMw(Number(e.target.value))} />
          </label>
          <button className="ui-button primary" onClick={() => draft.mutate(targetMw)} disabled={draft.isPending}>
            {draft.isPending ? 'Finding buildings…' : 'Find buildings'}
          </button>
        </div>
        <p className="agent-origin">
          Rules applied: at most {capPct.toFixed(0)}% of the load from Environmental Justice zips · buildings that
          carried the last confirmed event sit this one out · schools and care facilities are spared above 95°F ·
          each building is asked only for what the target still needs.
        </p>

        {draft.isError && (
          <p className="caption">Could not reach the planner. Is `make serve` running, and is the Bedrock key set?</p>
        )}

        {plan && eq && (
          <>
            <div className="equity-strip">
              <div>
                <span>Asked</span>
                <b>{eq.requestedMw.toFixed(1)} MW</b>
                <small>target {plan.targetMw} MW · {requests.length} buildings</small>
              </div>
              <div>
                <span>Load from EJ zips</span>
                <b>{eq.requestedEjSharePct.toFixed(0)}%</b>
                <div className="cap-bar" aria-hidden="true">
                  <i style={{ width: `${Math.min(100, eq.requestedEjSharePct)}%` }} />
                  <em style={{ left: `${capPct}%` }} />
                </div>
                <small>
                  cap {capPct.toFixed(0)}%
                  {eq.naiveEjSharePct != null && eq.naiveEjSharePct > eq.requestedEjSharePct
                    ? ` · ranking by load alone: ${eq.naiveEjSharePct.toFixed(0)}% (rejected)`
                    : ''}
                </small>
              </div>
              <div>
                <span>Rotation</span>
                <b>{eq.cooldownExcluded.length}</b>
                <small>
                  {eq.cooldownExcluded.length
                    ? 'buildings rested after carrying the last event'
                    : 'no buildings on cooldown'}
                </small>
              </div>
            </div>

            {!plan.reachable && plan.tradeoff && (
              <p className="tradeoff"><strong>Target not reachable under the cap.</strong> {plan.tradeoff}</p>
            )}

            <div className="plan-tables">
              <table>
                <caption>Where the burden lands</caption>
                <thead><tr><th>Neighborhood</th><th>Asked</th><th>Calls, last 5 events</th></tr></thead>
                <tbody>
                  {eq.neighborhoods.map((n) => (
                    <tr key={n.zip}>
                      <td>{regionForZip(n.zip)} <small className="mono">{n.zip}</small> {n.isEj && <Tag tone="attention">EJ</Tag>}</td>
                      <td className="mono">{fmtKw(n.kwRequested)}</td>
                      <td className="mono">{n.recentCalls}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <table>
                <caption>Buildings asked</caption>
                <thead><tr><th>Building</th><th>Ask / capacity</th></tr></thead>
                <tbody>
                  {visible.map((r) => (
                    <tr key={r.buildingId}>
                      <td>{r.address}<small>{whyRow(r)}</small></td>
                      <td className="mono">
                        {fmtKw(r.kwRequested)}
                        <small>{r.kwRequested < r.capacityKw ? `of ${fmtKw(r.capacityKw)} · tops off target` : 'full capacity'}</small>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {requests.length > 6 && (
                <button className="text-link" onClick={() => setShowAll(!showAll)}>
                  {showAll ? 'Show fewer' : `Show all ${requests.length} buildings`}
                </button>
              )}
            </div>

            <div className="action-row">
              <button className="ui-button primary" onClick={() => approve.mutate(targetMw)}
                disabled={approve.isPending || !plan.reachable || !!approve.data}>
                {approve.isPending ? 'Sending…' : approve.data ? 'Requests sent' : 'Approve & send requests'}
              </button>
              <button className="ui-button ghost" onClick={() => { draft.reset(); approve.reset() }}>
                Discard
              </button>
              <button className="ui-button secondary" aria-expanded={showReasoning} onClick={() => setShowReasoning(true)}>
                Why this plan?
              </button>
            </div>
            {approve.isError && <p className="caption">Could not approve the event. Please try again.</p>}
          </>
        )}
      </Panel>

      {data && showReasoning && (
        <div className="reasoning-drawer-root" role="dialog" aria-modal="true" aria-label="Agent reasoning trace">
          <div className="reasoning-backdrop" onClick={() => setShowReasoning(false)} />
          <aside className="reasoning-drawer">
            <div className="reasoning-drawer-head">
              <div>
                <strong>How the plan was checked</strong>
                <small>{data.trace.length} steps · {data.iterations} iteration(s)</small>
              </div>
              <button type="button" className="ui-button ghost" onClick={() => setShowReasoning(false)}>
                Hide
              </button>
            </div>
            <ol className="trace-list">
              {data.trace.map((step, index) => (
                <li className={step.kind === 'self_correct' ? 'revision' : ''} key={`${step.ts}-${index}`}>
                  <time>{fmtTime(step.ts)}</time>
                  <div>
                    <strong>
                      {step.kind === 'plan' && step.planVersion ? `Plan v${step.planVersion}` : step.kind.replace(/_/g, ' ')}
                    </strong>
                    {step.rejectedBy && <Tag tone="attention">Rejected: {step.rejectedBy}</Tag>}
                    <p>{plainText(step.summary)}</p>
                  </div>
                  {step.toolName && <code>{step.toolName}</code>}
                </li>
              ))}
            </ol>
          </aside>
        </div>
      )}
    </>
  )
}

const DECISION_TEXT = { yes: 'Accepted', no: 'Declined', counter: 'Offered', offer: 'Offered' } as const

// Step 3: buildings answer; the operator confirms what is committed.
function ResponsesPanel() {
  const qc = useQueryClient()
  const current = useQuery({
    queryKey: ['current-event'],
    queryFn: () => apiGet<{ event: CurrentEvent | null }>('/event/current'),
    refetchInterval: 4000,
  })
  const confirm = useMutation({
    mutationFn: (id: number) => apiPost<{ ok: boolean }>(`/event/${id}/confirm`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['current-event'] }),
  })

  const ev = current.data?.event
  if (!ev) {
    return (
      <Panel title="2 · Responses and confirmation" className="responses-panel">
        <p className="decision-empty">Approve a plan to send requests. Building replies appear here as they arrive.</p>
      </Panel>
    )
  }
  const pct = ev.targetMw ? Math.min(100, (100 * ev.committedMw) / ev.targetMw) : 0
  const short = ev.targetMw - ev.committedMw

  return (
    <Panel
      title="2 · Responses and confirmation"
      className="responses-panel"
      tools={ev.confirmed ? <Tag>Confirmed</Tag> : <Tag tone="attention">{ev.responded}/{ev.buildings.length} replied</Tag>}
    >
      <div className="commit-progress">
        <div>
          <b>{ev.committedMw.toFixed(2)} MW</b> committed of {ev.targetMw} MW target · {ev.windowLabel}
        </div>
        <div className="cap-bar" aria-hidden="true"><i style={{ width: `${pct}%` }} /></div>
      </div>
      <table>
        <thead><tr><th>Building</th><th>Asked</th><th>Reply</th></tr></thead>
        <tbody>
          {ev.buildings.map((b) => (
            <tr key={b.buildingId}>
              <td>{b.address} {b.isEj && <Tag tone="attention">EJ</Tag>}</td>
              <td className="mono">{fmtKw(b.kwRequested)}</td>
              <td>
                {b.decision
                  ? `${DECISION_TEXT[b.decision.kind]}${b.decision.kind !== 'no' && b.decision.kw != null ? ` ${fmtKw(b.decision.kw)}` : ''}`
                  : <span className="muted">Waiting</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="action-row single">
        <button className="ui-button primary" disabled={ev.confirmed || ev.committedMw <= 0 || confirm.isPending}
          onClick={() => confirm.mutate(ev.id)}>
          {ev.confirmed ? 'Event confirmed' : `Confirm event · ${ev.committedMw.toFixed(2)} MW`}
        </button>
      </div>
      {!ev.confirmed && short > 0.005 && ev.responded > 0 && (
        <p className="caption">
          {short.toFixed(2)} MW short of target. You can confirm what is committed now; declines and smaller
          offers are expected, and the next event rotates in other buildings.
        </p>
      )}
      {confirm.isError && <p className="caption">Could not confirm the event. Please try again.</p>}
    </Panel>
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
  const [activeOnly, setActiveOnly] = useState(false)

  const buildings = useQuery({
    queryKey: ['all-buildings-convos'],
    queryFn: () => apiGet<AllBuildingsResponse>('/portfolio/buildings'),
  })

  // Which buildings actually have a live (approved-event) conversation.
  const active = useQuery({
    queryKey: ['active-buildings'],
    queryFn: () => apiGet<{ building_ids: string[] }>('/events/active-buildings'),
    refetchInterval: 10000,
  })
  const activeSet = new Set(active.data?.building_ids ?? [])
  const activeCount = activeSet.size

  const term = search.trim().toLowerCase()
  const facilities = (buildings.data?.buildings ?? []).filter((b) => {
    if (activeOnly && !activeSet.has(b.buildingId)) return false
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
            <label className="convos-active-toggle">
              <input
                type="checkbox"
                checked={activeOnly}
                onChange={(e) => setActiveOnly(e.target.checked)}
              />
              Show active conversations only{activeCount ? ` (${activeCount})` : ''}
            </label>
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
            <p className="kicker">Peak event planning</p>
            <Heading level={1}>Who should we ask to reduce today?</Heading>
            <p>Hit the target without leaning on the same neighborhoods twice.</p>
          </div>
        </div>
        <div className="dashboard-grid">
          <PlanPanel />
          <MapPanel />
          <ResponsesPanel />
        </div>
        <details className="more-tools">
          <summary>More tools: facility conversations, season outcomes, recruitment</summary>
          <div className="dashboard-grid">
            <ConversationsPanel />
            <SeasonPanel />
            <RecruitmentPanel />
          </div>
        </details>
      </main>
    </div>
  )
}
