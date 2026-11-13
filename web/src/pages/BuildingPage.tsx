import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AppHeader, Heading, Panel, Tag } from '../components/ui'
import { apiGet, apiPost, ApiError } from '../lib/api'
import { plainText } from '../lib/chat'
import { siteTypeFor } from '../lib/grouping'
import { getIdentity } from '../lib/session'

type BuildingProfile = {
  building_id?: string
  address?: string
  zip?: string
  property_type?: string | null
  curtailable_load_kw?: number | null
  load_basis?: string
  is_ej?: boolean
  affluence_tier?: string
  is_commercial?: boolean
  source_id?: string
}

type Decision = { kind: 'yes' | 'no' | 'counter' | 'offer'; kw: number | null }

type InboxMessage = {
  id: number
  sender_role: 'operator' | 'agent' | 'building_manager' | 'system'
  body: string
}

type InboxResponse = {
  event_id: number | null
  window_label: string | null
  requested_kw: number | null
  est_payment_usd: number | null
  capacity_kw: number | null
  decision: Decision | null
  confirmed: boolean
  handoff_mode: 'auto' | 'human'
  needs_human: boolean
  messages: InboxMessage[]
}

const kw = (n: number) => `${Math.round(n).toLocaleString()} kW`
const usd = (n: number) => `$${Math.round(n).toLocaleString()}`

// Typical measures by site type. Shown as guidance, not a prescription — the
// facility's own engineer decides how to deliver the reduction.
const MEASURES: Record<string, string> = {
  Office: 'Raise cooling setpoints 2–3°F, dim non-essential lighting, pause EV charging.',
  Retail: 'Raise cooling setpoint ~2°F, dim back-of-house and display lighting.',
  Warehouse: 'Shift charging and non-urgent equipment out of the window.',
  'Industrial / Plant': 'Shift non-urgent process loads out of the window.',
  Residential: 'Pre-cool common areas beforehand, dim common-area lighting. No changes inside units.',
  Education: 'Defer non-critical loads only; occupied spaces stay comfortable.',
  Healthcare: 'Defer non-critical loads only; clinical systems are never touched.',
  Lab: 'Defer non-critical loads only; lab safety systems are never touched.',
  Other: 'Raise cooling setpoints slightly and dim non-essential lighting.',
}

function whyThisBuilding(p: BuildingProfile | undefined): string {
  if (!p) return 'Your building has flexible capacity for this window.'
  const parts: string[] = []
  if (p.is_commercial) parts.push('a commercial site, so a reduction lands on operations, not residents')
  if (p.affluence_tier === 'high') parts.push('in a higher-income area')
  if (p.is_ej === false) parts.push('outside an Environmental Justice zip')
  if (parts.length === 0) return 'Your building has flexible capacity, and this event stays within the neighborhood equity cap.'
  return `Your building is ${parts.join(', ')}. The utility asks sites like yours first so lower-income neighborhoods are spared.`
}

function decisionLabel(d: Decision): string {
  if (d.kind === 'no') return 'You declined this event.'
  if (d.kind === 'yes') return `You accepted ${kw(d.kw ?? 0)}.`
  return `You offered ${kw(d.kw ?? 0)}.`
}

// The main screen for a facility manager: one request, one decision.
function DecisionCard({ buildingId, profile }: { buildingId: string; profile?: BuildingProfile }) {
  const qc = useQueryClient()
  const [mode, setMode] = useState<'choose' | 'counter'>('choose')
  const [counterKw, setCounterKw] = useState('')
  const [editing, setEditing] = useState(false)

  const inbox = useQuery({
    queryKey: ['inbox', buildingId],
    queryFn: () => apiGet<InboxResponse>(`/inbox/${buildingId}`),
    refetchInterval: 4000,
    retry: false,
  })

  const decide = useMutation({
    mutationFn: (body: { decision: 'accept' | 'decline' | 'counter'; kw?: number }) =>
      apiPost<{ ok: boolean }>(`/inbox/${buildingId}/decision`, body),
    onSuccess: () => {
      setMode('choose')
      setEditing(false)
      qc.invalidateQueries({ queryKey: ['inbox', buildingId] })
    },
  })

  const data = inbox.data
  if (inbox.isError) {
    return (
      <Panel title="Today’s request">
        <p className="decision-empty">Could not load your request. Make sure you are signed in.</p>
      </Panel>
    )
  }
  if (!data) {
    return (
      <Panel title="Today’s request">
        <p className="decision-empty">Loading…</p>
      </Panel>
    )
  }
  if (data.event_id === null || data.requested_kw == null) {
    return (
      <Panel title="Today’s request" tools={<Tag>No request</Tag>}>
        <p className="decision-empty">
          No request right now. When the utility needs a reduction and your building is a good fit,
          the request, your estimated earnings, and your options appear here.
        </p>
      </Panel>
    )
  }

  const requested = data.requested_kw
  const capacity = data.capacity_kw ?? requested
  const ceiling = Math.min(requested, capacity)
  const ratePerKw = data.est_payment_usd != null ? data.est_payment_usd / requested : null
  const earn = (k: number) => (ratePerKw != null ? usd(ratePerKw * k) : '—')
  // Simulated typical peak: curtailable capacity is ~15% of peak load.
  const typicalPeak = profile?.curtailable_load_kw ? profile.curtailable_load_kw / 0.15 : null
  const share = (k: number) => (typicalPeak ? Math.round((100 * k) / typicalPeak) : null)
  const measures = MEASURES[siteTypeFor(profile?.property_type ?? null)] ?? MEASURES.Other

  const counterNum = Number(counterKw)
  const counterError =
    counterKw === ''
      ? null
      : !Number.isFinite(counterNum) || counterNum <= 0
        ? 'Enter an amount above 0 kW.'
        : counterNum >= ceiling
          ? `Must be below ${kw(ceiling)}, the amount asked. To commit the full amount, accept instead.`
          : null
  const serverError = decide.error instanceof ApiError ? decide.error.message : null

  const decided = data.decision && !editing
  // Tiles follow the amount in play: the sent offer, the offer being typed, or the full ask.
  const offered = decided && data.decision?.kind === 'counter' ? data.decision.kw : null
  const shown = offered ?? (mode === 'counter' && counterKw !== '' && !counterError ? counterNum : requested)
  const pct = share(shown)

  return (
    <Panel
      title="Today’s request"
      className="decision-card"
      tools={
        data.confirmed ? <Tag>Confirmed by utility</Tag>
          : decided ? <Tag>Awaiting utility confirmation</Tag>
          : <Tag tone="attention">Reply needed</Tag>
      }
    >
      <div className="decision-ask">
        <span>The utility asks you to reduce</span>
        <strong>{kw(requested)}</strong>
        <small>{data.window_label} · voluntary and paid</small>
      </div>

      <div className="decision-facts">
        <div>
          <span>You’d earn <Tag>Estimated</Tag></span>
          <b>{earn(shown)}</b>
          <small>Program rate × kW delivered; finalized after meter verification.</small>
        </div>
        <div>
          <span>What it takes</span>
          <b>{pct != null ? `≈${pct}% of typical peak` : kw(shown)}</b>
          <small>{measures}</small>
        </div>
        <div>
          <span>Why you</span>
          <small>{whyThisBuilding(profile)}</small>
        </div>
      </div>

      <p className="decision-capacity">
        Your enrolled capacity is <b>{kw(capacity)}</b>.{' '}
        {requested < capacity
          ? `The utility only needs ${kw(requested)} from you to reach its target.`
          : 'This request uses your full enrolled capacity.'}{' '}
        You can’t commit more than you’re able to deliver.
      </p>

      {decided && data.decision ? (
        <div className={`decision-result ${data.confirmed ? 'confirmed' : ''}`}>
          <b>{decisionLabel(data.decision)}</b>
          <span>
            {data.confirmed
              ? data.decision.kind === 'no'
                ? 'The utility confirmed the event without your building.'
                : 'The utility confirmed the event. Thank you.'
              : 'The utility will confirm the event once enough buildings have replied.'}
          </span>
          {!data.confirmed && (
            <button type="button" className="ui-button ghost" onClick={() => setEditing(true)}>
              Change reply
            </button>
          )}
        </div>
      ) : (
        <div className="decision-actions">
          {mode === 'choose' ? (
            <>
              <button className="ui-button primary" disabled={decide.isPending}
                onClick={() => decide.mutate({ decision: 'accept' })}>
                Accept {kw(requested)}
              </button>
              <button className="ui-button secondary" onClick={() => setMode('counter')}>
                Offer less
              </button>
              <button className="ui-button ghost" disabled={decide.isPending}
                onClick={() => decide.mutate({ decision: 'decline' })}>
                Decline
              </button>
            </>
          ) : (
            <div className="counter-form">
              <label>
                I can reduce (kW)
                <input
                  type="number"
                  min={1}
                  max={Math.max(1, Math.floor(ceiling) - 1)}
                  value={counterKw}
                  placeholder={`Up to ${Math.max(1, Math.floor(ceiling) - 1).toLocaleString()}`}
                  onChange={(e) => setCounterKw(e.target.value)}
                  aria-invalid={!!counterError}
                />
              </label>
              {counterError && <p className="field-error">{counterError}</p>}
              <div className="counter-buttons">
                <button
                  className="ui-button primary"
                  disabled={decide.isPending || counterKw === '' || !!counterError}
                  onClick={() => decide.mutate({ decision: 'counter', kw: counterNum })}
                >
                  Send offer{counterKw && !counterError ? ` · ${earn(counterNum)}` : ''}
                </button>
                <button className="ui-button ghost" onClick={() => { setMode('choose'); setCounterKw('') }}>
                  Back
                </button>
              </div>
            </div>
          )}
          {serverError && <p className="field-error">{serverError}</p>}
        </div>
      )}
    </Panel>
  )
}

// Supporting assistant: collapsed by default, short answers, one voice
// ("Utility operator") for the agent and a human rep.
function AskPanel({ buildingId }: { buildingId: string }) {
  const [open, setOpen] = useState(false)
  const [input, setInput] = useState('')
  const qc = useQueryClient()

  const inbox = useQuery({
    queryKey: ['inbox', buildingId],
    queryFn: () => apiGet<InboxResponse>(`/inbox/${buildingId}`),
    refetchInterval: 4000,
    retry: false,
  })
  const reply = useMutation({
    mutationFn: (body: string) => apiPost<{ ok: boolean }>(`/inbox/${buildingId}/reply`, { body }),
    onSuccess: () => {
      setInput('')
      qc.invalidateQueries({ queryKey: ['inbox', buildingId] })
    },
  })
  const requestHuman = useMutation({
    mutationFn: () => apiPost<{ ok: boolean }>(`/inbox/${buildingId}/request-human`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['inbox', buildingId] }),
  })

  if (!inbox.data || inbox.data.event_id === null) return null
  const messages = inbox.data.messages
  const humanMode = inbox.data.handoff_mode === 'human' || inbox.data.needs_human
  const send = (text: string) => {
    const body = text.trim()
    if (body && !reply.isPending) reply.mutate(body)
  }

  return (
    <section className="ask-panel">
      <button type="button" className="ask-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span>Questions about this request?</span>
        <small>{humanMode ? 'A representative has joined' : 'Ask the utility · instant answers'}</small>
      </button>
      {open && (
        <div className="ask-body">
          <div className="ask-suggestions">
            {['Why was my building asked?', 'How is my payment estimated?', 'What if we deliver less?'].map((s) => (
              <button type="button" key={s} className="ui-button secondary" onClick={() => send(s)}>
                {s}
              </button>
            ))}
          </div>
          {messages.length > 0 && (
            <div className="ask-thread" aria-live="polite">
              {messages.map((m) => (
                <p key={m.id} className={m.sender_role === 'building_manager' ? 'me' : ''}>
                  <span>{m.sender_role === 'building_manager' ? 'You' : 'Utility'}</span>
                  {plainText(m.body)}
                </p>
              ))}
              {reply.isPending && <p><span>Utility</span>Typing…</p>}
            </div>
          )}
          <div className="chat-composer">
            <input
              type="text"
              value={input}
              placeholder="Ask a question…"
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') send(input) }}
            />
            <button className="ui-button primary" onClick={() => send(input)} disabled={reply.isPending}>
              Ask
            </button>
          </div>
          {!humanMode && (
            <button type="button" className="text-link ask-human" onClick={() => requestHuman.mutate()}
              disabled={requestHuman.isPending}>
              Talk to a person instead
            </button>
          )}
        </div>
      )}
    </section>
  )
}

// Portfolio + history: useful context, but secondary to today's decision.
// STATIC demo values (no multi-facility or per-facility earnings endpoint).
const HISTORY = [
  ['Aug 14', 'Accepted', '301 kW', '$1,054'],
  ['Jul 27', 'Accepted', '288 kW', '$1,008'],
  ['Jul 09', 'Declined', '—', '$0'],
  ['Jun 18', 'Offered 250 kW', '242 kW', '$847'],
] as const

function HistorySection() {
  return (
    <details className="history-section">
      <summary>Participation history and season earnings <Tag>Simulated</Tag></summary>
      <table>
        <thead>
          <tr><th>Date</th><th>Reply</th><th>Delivered</th><th>Earnings</th></tr>
        </thead>
        <tbody>
          {HISTORY.map((row) => (
            <tr key={row[0]}>
              {row.map((cell, i) => <td className={i > 1 ? 'mono' : ''} key={i}>{cell}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="caption">Season total $2,909 before facility operating costs.</p>
    </details>
  )
}

export function BuildingPage() {
  const buildingId = getIdentity()?.buildingId ?? ''
  const building = useQuery({
    queryKey: ['building', buildingId],
    queryFn: () => apiGet<BuildingProfile>(`/portfolio/buildings/${buildingId}`),
    enabled: !!buildingId,
  })
  const name = building.data?.address ?? 'Your facility'

  return (
    <div className="workspace">
      <AppHeader context={name} />
      <main className="account decision-page">
        <div className="dashboard-title">
          <div>
            <p className="kicker">Facility manager</p>
            <Heading level={1}>{name}</Heading>
            {building.data?.property_type && <p>{building.data.property_type} · zip {building.data.zip}</p>}
          </div>
          <Tag>Simulated enrollment</Tag>
        </div>

        {building.isError && (
          <p className="caption">
            Could not reach the API. Locally, run `make serve` (port 8000). On a deployed site, set
            VITE_API_BASE_URL to the backend URL.
          </p>
        )}

        {buildingId && <DecisionCard buildingId={buildingId} profile={building.data} />}
        {buildingId && <AskPanel buildingId={buildingId} />}
        <HistorySection />
      </main>
    </div>
  )
}
