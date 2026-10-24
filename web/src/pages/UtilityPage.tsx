import { useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { AppHeader, Heading, Panel, Tag } from '../components/ui'
import { BuildingMap } from '../components/BuildingMap'
import { ChatThread } from '../components/ChatThread'
import { apiGet, apiPost } from '../lib/api'
import { getUnread } from '../lib/chat'
import type {
SavingsResponse, RecruitmentResponse,
  EventDraftResponse,
  ZipsResponse,
  ZipBuildingsResponse,
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

// Build a cause→effect reasoning graph from the live agent trace. Signals and
// checks feed decisions; the final plan is the proposal node.
function ReasoningGraph({ data }: { data: EventDraftResponse }) {
  const [active, setActive] = useState<string | null>(null)

  const { nodes, edges } = useMemo(() => {
    const steps = data.trace
    const n: Array<{ id: string; label: string; kind: 'signal' | 'check' | 'decision' | 'proposal'; x: number; y: number; anchor?: 'start' | 'middle' | 'end' }> = []
    const e: Array<{ from: string; to: string; label?: string }> = []
    const kindFor = (k: string): 'signal' | 'check' | 'decision' | 'proposal' =>
      k === 'forecast' ? 'signal' : k.includes('check') ? 'check' : 'decision'
    const cols = Math.max(steps.length - 1, 1)
    steps.forEach((s, i) => {
      const id = `s${i}`
      const last = i === steps.length - 1
      n.push({
        id,
        label:
          s.kind === 'plan' && s.planVersion ? `Plan v${s.planVersion}` : s.kind.replace(/_/g, ' '),
        kind: last ? 'proposal' : kindFor(s.kind),
        x: 6 + (i / cols) * 88,
        y: i % 2 === 0 ? 28 : 64,
        anchor: i === 0 ? 'start' : last ? 'end' : 'middle',
      })
      if (i > 0) e.push({ from: `s${i - 1}`, to: id, label: steps[i].rejectedBy ? 'rejected' : 'leads to' })
    })
    return { nodes: n, edges: e }
  }, [data])

  const node = (id: string) => nodes.find((nn) => nn.id === id)!
  const edgeActive = (ed: { from: string; to: string }) =>
    active !== null && (ed.from === active || ed.to === active)
  const activeNode = active ? node(active) : null

  return (
    <div className="reasoning-graph">
      <svg viewBox="-6 2 112 78" role="img" aria-label="Reasoning knowledge graph" preserveAspectRatio="xMidYMid meet">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="currentColor" />
          </marker>
        </defs>
        {edges.map((ed, i) => {
          const a = node(ed.from)
          const b = node(ed.to)
          return (
            <g key={i} className={`edge ${edgeActive(ed) ? 'edge-active' : ''}`}>
              <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} markerEnd="url(#arrow)" />
              {edgeActive(ed) && ed.label && (
                <text x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 1.5} className="edge-label">
                  {ed.label}
                </text>
              )}
            </g>
          )
        })}
        {nodes.map((nn) => {
          const isActive = active === nn.id
          return (
            <g
              key={nn.id}
              className={`gnode kind-${nn.kind} ${isActive ? 'gnode-active' : ''}`}
              onMouseEnter={() => setActive(nn.id)}
              onMouseLeave={() => setActive(null)}
              onClick={() => setActive((cur) => (cur === nn.id ? null : nn.id))}
              onFocus={() => setActive(nn.id)}
              tabIndex={0}
              role="button"
              aria-pressed={isActive}
            >
              <circle cx={nn.x} cy={nn.y} r={3.4} />
              <text
                x={nn.anchor === 'start' ? nn.x - 3.4 : nn.anchor === 'end' ? nn.x + 3.4 : nn.x}
                y={nn.y + 6.5}
                textAnchor={nn.anchor ?? 'middle'}
                className="gnode-label"
              >
                {nn.label}
              </text>
            </g>
          )
        })}
      </svg>
      <p className="graph-hint">
        {activeNode
          ? `${activeNode.label} — ${activeNode.kind}. Highlighted links show what it fed into.`
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

function MapPanel() {
  return (
    <Panel title="Portfolio map" className="map-panel" tools={<Tag>Building pins · Boston</Tag>}>
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
        tools={
          <div className="agent-tools">
            <Tag>{data ? (data.approved ? 'Approved by critic' : 'Needs review') : 'Idle'}</Tag>
            <button
              type="button"
              className="ui-button ghost reasoning-toggle"
              aria-expanded={showReasoning}
              disabled={!data}
              onClick={() => setShowReasoning((v) => !v)}
            >
              {showReasoning ? 'Hide reasoning' : 'Show reasoning'}
            </button>
          </div>
        }
      >
        {!data && (
          <p className="caption">
            The live agent trace (forecast → plan v1 → constraint check → self-correct → plan v2)
            and an interactive reasoning graph appear here after you draft a proposal.
          </p>
        )}
        {data && !showReasoning && (
          <p className="caption reasoning-collapsed-hint">
            {data.trace.length} steps retained. Select <b>Show reasoning</b> to inspect the trace and
            the reasoning graph behind this proposal.
          </p>
        )}
        {data && showReasoning && (
          <div className="agent-evidence">
            <div className="reasoning-graph-wrap">
              <div className="panel-subhead">
                <span>Reasoning graph</span>
                <small>causes → final proposal</small>
              </div>
              <ReasoningGraph data={data} />
            </div>
            <details open>
              <summary>
                <span>Agent trace</span>
                <small>{data.trace.length} steps · {data.iterations} iteration(s)</small>
              </summary>
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
            </details>
          </div>
        )}
      </Panel>
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

// Operator "Facility conversations" panel: pick a zip, pick a facility from the
// left list, and the right pane shows that building's live conversation thread.
function ConversationsPanel() {
  const [zip, setZip] = useState('')
  const [selected, setSelected] = useState('')

  const zips = useQuery({
    queryKey: ['zips'],
    queryFn: () => apiGet<ZipsResponse>('/zips'),
  })

  const buildings = useQuery({
    queryKey: ['zip-buildings', zip],
    queryFn: () => apiGet<ZipBuildingsResponse>(`/zips/${zip}/buildings`),
    enabled: zip !== '',
  })

  const onPickZip = (next: string) => {
    setZip(next)
    setSelected('')
  }

  return (
    <Panel
      title="Facility conversations"
      className="conversations-panel"
      tools={<Tag>Live inbox</Tag>}
    >
      <div className="conversations-body">
        <div className="conversations-list">
          <select value={zip} onChange={(e) => onPickZip(e.target.value)}>
            <option value="">Select a zip…</option>
            {zips.data?.zips.map((z) => (
              <option key={z.zip} value={z.zip}>
                {z.zip} · {z.buildingCount} buildings
              </option>
            ))}
          </select>

          {buildings.isLoading && zip !== '' && <p className="caption">Loading facilities…</p>}
          {buildings.data?.buildings.map((b) => (
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
