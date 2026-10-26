import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { AppHeader, Heading, Panel, Tag } from '../components/ui'
import { BuildingMap } from '../components/BuildingMap'
import { ChatThread } from '../components/ChatThread'
import { apiGet, apiPost } from '../lib/api'
import { getUnread } from '../lib/chat'
import { regionForZip, siteTypeFor } from '../lib/grouping'
import type {
SavingsResponse, RecruitmentResponse, RecruitmentCandidate,
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
