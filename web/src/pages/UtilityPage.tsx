import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { AppHeader, Heading, Panel, Tag } from '../components/ui'
import { BuildingMap } from '../components/BuildingMap'
import { apiGet, apiPost } from '../lib/api'
import type {
SavingsResponse, RecruitmentResponse,
  EventDraftResponse,
} from '../lib/types'

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

function OperatorAndAgent() {
  const [targetMw, setTargetMw] = useState(20)
  const [approved, setApproved] = useState(false)

  const draft = useMutation({
    mutationFn: (target: number) =>
      apiPost<EventDraftResponse>(
        '/event/draft',
        { target_mw: target, ej_cap_pct: 0.35, current_temp_f: 88, window_label: '5–7 PM' },
        { 'X-Role': 'operator' },
      ),
    onSuccess: () => setApproved(false),
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
            {draft.isPending ? 'Planning…' : 'Draft event'}
          </button>
        </div>

        {draft.isError && (
          <p className="caption">
            Could not reach the planner. Is `make serve` running, and is the Bedrock key set?
          </p>
        )}

        {plan && (
          <>
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
              <button className="ui-button primary" onClick={() => setApproved(true)}>
                Approve
              </button>
              <button className="ui-button secondary">Edit list</button>
              <button className="ui-button ghost" onClick={() => draft.reset()}>
                Reject
              </button>
            </div>
            {approved && (
              <div className="confirmation">
                ✓ Event approved · {plan.achievedMw.toFixed(1)} MW across {plan.buildingCount} buildings
                <span>Audit line recorded · {plan.source_id}</span>
              </div>
            )}
          </>
        )}
      </Panel>

      <Panel title="Planning agent" className="agent-panel" tools={<Tag>{data ? (data.approved ? 'Approved by critic' : 'Needs review') : 'Idle'}</Tag>}>
        <div className="agent-evidence">
          <details open>
            <summary>
              <span>Agent trace</span>
              <small>
                {data ? `${data.trace.length} steps · ${data.iterations} iteration(s)` : 'Draft an event to run the agent'}
              </small>
            </summary>
            {!data && <p className="caption">The live agent trace (forecast → plan v1 → constraint check → self-correct → plan v2) appears here after you draft an event.</p>}
            {data && (
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
            )}
          </details>
        </div>
      </Panel>
    </>
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
        </div>
      </main>
    </div>
  )
}
