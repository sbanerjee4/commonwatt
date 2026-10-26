import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { AppHeader, Heading, Panel, Tag } from '../components/ui'
import { apiGet, apiPost } from '../lib/api'
import { getIdentity } from '../lib/session'

type BuildingProfile = {
  building_id?: string
  address?: string
  zip?: string
  property_type?: string
  gross_area_sf?: number
  curtailable_load_kw?: number | null
  load_basis?: string
  source_id?: string
  [key: string]: unknown
}

type InboxMessage = {
  id: number
  event_id: number | null
  sender_role: 'operator' | 'agent' | 'building_manager' | 'system'
  sender_user_id: number | null
  body: string
  created_at: string | null
}

type InboxResponse = {
  building_id: string
  event_id: number | null
  handoff_mode: 'auto' | 'human'
  needs_human: boolean
  messages: InboxMessage[]
}

const SENDER_LABEL: Record<InboxMessage['sender_role'], string> = {
  operator: 'Utility operator',
  agent: 'Utility operator',
  building_manager: 'You',
  system: 'Utility operator',
}

// Single unified conversation between the building manager and the utility.
// By default an automated agent answers (posted as sender_role 'agent') but the
// manager sees ONE voice — "Utility operator" — for the agent, the human
// operator, and system notices, so the AI appears to speak on the operator's
// behalf. "Talk to a human" flips the thread to human mode (request-human); the
// operator then picks up (operator-message) and the agent stays silent. Polls
// GET /inbox/{id} every 4s so operator/agent messages appear without a reload.
function EventInbox({ buildingId }: { buildingId: string }) {
  const [input, setInput] = useState('')

  const inbox = useQuery({
    queryKey: ['inbox', buildingId],
    queryFn: () => apiGet<InboxResponse>(`/inbox/${buildingId}`),
    refetchInterval: 4000,
    refetchIntervalInBackground: true,
  })

  const reply = useMutation({
    mutationFn: (body: string) =>
      apiPost<{ ok: boolean }>(`/inbox/${buildingId}/reply`, { body }),
    onSuccess: () => {
      setInput('')
      inbox.refetch()
    },
  })

  const requestHuman = useMutation({
    mutationFn: () => apiPost<{ ok: boolean }>(`/inbox/${buildingId}/request-human`, {}),
    onSuccess: () => inbox.refetch(),
  })

  const send = () => {
    const body = input.trim()
    if (!body || reply.isPending) return
    reply.mutate(body)
  }

  const messages = inbox.data?.messages ?? []
  const noEvent = inbox.data && inbox.data.event_id === null
  const humanMode = inbox.data?.handoff_mode === 'human' || inbox.data?.needs_human

  const suggestions = [
    'What is my building and how much could we reduce?',
    'Why was I asked today?',
    'How is my payment estimated?',
  ]

  return (
    <Panel
      title="Conversation with the utility"
      tools={
        <Tag tone={humanMode ? 'attention' : ''}>
          {noEvent ? 'No event' : humanMode ? 'A representative has joined' : 'Assisted'}
        </Tag>
      }
    >
      <p className="request-explainer">
        Message the utility about today’s event. You’ll get an immediate answer; ask for a person any
        time and a representative takes over. Answers are grounded in your building’s real data.
      </p>

      <div className="chat-thread" aria-live="polite">
        {inbox.isError && (
          <p className="caption">Could not load messages. Make sure you are signed in.</p>
        )}
        {!inbox.isError && noEvent && (
          <p className="caption">No active event for your building right now.</p>
        )}
        {!inbox.isError && !noEvent && messages.length === 0 && (
          <div className="chat-suggestions">
            {suggestions.map((s) => (
              <button type="button" key={s} className="ui-button ghost" onClick={() => setInput(s)}>
                {s}
              </button>
            ))}
          </div>
        )}
        {messages.map((m) => (
          <div
            key={m.id}
            className={`chat-message ${m.sender_role === 'building_manager' ? 'user' : 'assistant'}`}
          >
            <span>{SENDER_LABEL[m.sender_role]}</span>
            <p>{m.body}</p>
          </div>
        ))}
        {reply.isPending && (
          <div className="chat-message assistant"><span>Utility operator</span><p>Typing…</p></div>
        )}
      </div>

      {!noEvent && !humanMode && (
        <button
          type="button"
          className="ui-button ghost"
          onClick={() => requestHuman.mutate()}
          disabled={requestHuman.isPending}
          style={{ alignSelf: 'flex-start', marginBottom: 'var(--space-2)' }}
        >
          {requestHuman.isPending ? 'Requesting…' : 'Talk to a human representative'}
        </button>
      )}

      <div className="chat-composer">
        <input
          type="text"
          value={input}
          placeholder={noEvent ? 'No active event' : 'Type a message…'}
          disabled={!!noEvent}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') send() }}
        />
        <button className="ui-button primary" onClick={send} disabled={reply.isPending || !!noEvent}>
          Send
        </button>
      </div>
      {reply.isError && <p className="caption">Could not send. Please try again.</p>}
    </Panel>
  )
}

// Managed-facilities portfolio. STATIC: there is no multi-facility or
// per-facility-earnings endpoint, so these mirror the design mock. The selected
// facility's status card below reads the real /portfolio/buildings/{id}.
// Facility rows map to REAL seeded building ids so selecting one loads that
// building's real profile/inbox. The first row is the signed-in building (it
// carries the demo event); the others are the other seeded demo buildings.
const FACILITIES = [
  { id: '129860', name: '730 Border St.', town: 'Boston', status: 'Request today', tone: 'attention', capacityKw: 420, earnings: '$3,214' },
  { id: '114120', name: 'North Point Offices', town: 'Cambridge', status: 'Available', tone: '', capacityKw: 310, earnings: '$2,408' },
  { id: '100901', name: '1725 Hyde Park Ave', town: 'Boston', status: 'Available', tone: '', capacityKw: 275, earnings: '$1,692' },
] as const

const EARNINGS_LEGEND = [
  { key: 'one', name: '730 Border St.', pct: '45%' },
  { key: 'two', name: 'North Point Offices', pct: '33%' },
  { key: 'three', name: '1725 Hyde Park Ave', pct: '22%' },
] as const

export function BuildingPage() {
  const [reply, setReply] = useState<'yes' | 'no' | 'offer'>('yes')
  const [submitted, setSubmitted] = useState(false)
  // Selected facility drives which REAL building's data is loaded. Default to
  // the signed-in building when it matches a row, else the first row.
  const signedInId = getIdentity()?.buildingId ?? null
  const defaultFacility = FACILITIES.find((f) => f.id === signedInId) ?? FACILITIES[0]
  const [selectedId, setSelectedId] = useState<string>(defaultFacility.id)
  const selectedFacility = FACILITIES.find((f) => f.id === selectedId) ?? FACILITIES[0]
  const selectedName = selectedFacility.name

  // All building-scoped queries follow the SELECTED facility's real id.
  const buildingId = selectedId

  const building = useQuery({
    queryKey: ['building', buildingId],
    queryFn: () => apiGet<BuildingProfile>(`/portfolio/buildings/${buildingId}`),
  })

  // Does this building actually have an active (approved) event? Drives whether
  // the event-request card + "asked to reduce" banner show at all. event_id ===
  // null means no active event — then we show a calm "no request" state instead
  // of a stale static request card.
  const inbox = useQuery({
    queryKey: ['inbox', buildingId],
    queryFn: () => apiGet<{ event_id: number | null; window_label: string | null; requested_kw: number | null; est_payment_usd: number | null }>(`/inbox/${buildingId}`),
    retry: false,
  })
  const hasActiveEvent = inbox.data ? inbox.data.event_id !== null : false
  const eventWindow = inbox.data?.window_label ?? '5–7 PM'
  const requestedKw = inbox.data?.requested_kw ?? null
  const estPayment = inbox.data?.est_payment_usd ?? null

  const profile = building.data
  const load =
    profile?.curtailable_load_kw != null ? `${profile.curtailable_load_kw.toLocaleString()} kW` : '420 kW'
  // Simulated recent peak load, derived from the real curtailable load
  // (curtailable ≈ 15% of peak), so it varies per building and is labeled.
  const recentLoad =
    profile?.curtailable_load_kw != null
      ? `${Math.round((profile.curtailable_load_kw / 0.15) / 10) * 10} kW`
      : '—'

  return (
    <div className="workspace">
      <AppHeader context={selectedName} />
      <main className="account">
        <div className="dashboard-title">
          <div>
            <p className="kicker">Facility manager account</p>
            <Heading level={1}>Your facility portfolio.</Heading>
            <p>Manage event participation and earnings across four properties.</p>
          </div>
          <Tag>Simulated data</Tag>
        </div>

        {building.isError && (
          <p className="caption">
            Could not reach the API. Locally, run `make serve` (port 8000). On a deployed site, set
            VITE_API_BASE_URL to the backend URL.
          </p>
        )}

        <div className="portfolio-grid">
          <Panel title="Managed facilities" tools={<Tag>3 facilities</Tag>}>
            <table className="facility-table">
              <thead>
                <tr>
                  <th>Facility</th>
                  <th>Status</th>
                  <th>Enrolled capacity</th>
                  <th>Season earnings</th>
                </tr>
              </thead>
              <tbody>
                {FACILITIES.map((f) => {
                  const isSelected = f.id === selectedId
                  return (
                    <tr
                      key={f.id}
                      className={`facility-row ${isSelected ? 'selected-row' : ''}`.trim()}
                      onClick={() => setSelectedId(f.id)}
                      tabIndex={0}
                      aria-selected={isSelected}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          setSelectedId(f.id)
                        }
                      }}
                    >
                      <td>
                        <strong>{f.name}</strong>
                        <small>{isSelected ? `Selected · ${f.town}` : f.town}</small>
                      </td>
                      <td>
                        <Tag tone={f.tone}>{f.status}</Tag>
                      </td>
                      <td className="mono">{f.capacityKw} kW</td>
                      <td className="mono">{f.earnings}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </Panel>

          <Panel
            title="Event earnings by facility"
            tools={<span className="total-paid">Season total <b>$8,460</b></span>}
          >
            <div className="earnings-chart">
              <div
                className="pie-chart"
                role="img"
                aria-label="730 Border St. 45 percent, North Point Offices 33 percent, 1725 Hyde Park Ave 22 percent"
              >
                <span>
                  $8,460
                  <small>total earned</small>
                </span>
              </div>
              <ul className="pie-legend">
                {EARNINGS_LEGEND.map((l) => (
                  <li key={l.key}>
                    <i className={`pie-key ${l.key}`} />
                    <span>{l.name}</span>
                    <b>{l.pct}</b>
                  </li>
                ))}
              </ul>
            </div>
            <p className="caption">Gross event earnings before any facility operating costs.</p>
          </Panel>
        </div>

        <div className="selected-facility">
          <span>Selected facility</span>
          <Heading level={2}>{selectedName}</Heading>
        </div>

        <section className="status-card">
          <div>
            <span>
              Enrolled capacity <Tag>Simulated</Tag>
            </span>
            <strong>{load}</strong>
            <small>{profile?.source_id ?? 'SRC-ENR-108'}</small>
          </div>
          <div>
            <span>
              Recent load <Tag>Simulated</Tag>
            </span>
            <strong>{recentLoad}</strong>
            <small>SRC-MTR-220</small>
          </div>
          <div className="ask-status yes">
            <span className="status-symbol">{hasActiveEvent ? '!' : '✓'}</span>
            <span>
              {hasActiveEvent ? (
                <>
                  <b>Asked to reduce today</b>
                  <small>{eventWindow}{requestedKw != null ? ` · ${requestedKw.toLocaleString()} kW` : ''}</small>
                </>
              ) : (
                <>
                  <b>No active request</b>
                  <small>You'll be notified here when the utility asks.</small>
                </>
              )}
            </span>
          </div>
        </section>

        <div className="account-grid">
          <Panel title="Current event request">
            {!hasActiveEvent ? (
              <p className="caption" style={{ padding: 'var(--space-4)' }}>
                No active event for this facility right now. When the utility approves an event that
                includes this building, the request and your reply options will appear here.
              </p>
            ) : (
            <>
            <div className="request-explainer">
              The utility is asking whether your building can voluntarily use less electricity during
              the {eventWindow} window. You choose whether to participate.
            </div>
            <div className="live-number">
              <span>Asked to reduce by</span>
              <strong>{requestedKw != null ? `${requestedKw.toLocaleString()} kW` : '—'}</strong>
              <small>From the approved event plan</small>
            </div>
            <p className="why">
              <strong>Why this building?</strong>
              Your building has available capacity, and this event stays within the neighborhood equity cap.
            </p>
            <div className="payment">
              <span>Expected event earnings <Tag>Estimated</Tag></span>
              <strong>{estPayment != null ? `$${estPayment.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : '—'}</strong>
              <small>{requestedKw != null ? `${requestedKw.toLocaleString()} kW × program rate` : 'Program rate'}; finalized after meter verification</small>
            </div>
            <fieldset>
              <legend>Your reply</legend>
              <div className="reply-options">
                {(['yes', 'no', 'offer'] as const).map((option) => (
                  <button
                    type="button"
                    key={option}
                    className={reply === option ? 'reply selected' : 'reply'}
                    onClick={() => setReply(option)}
                    aria-pressed={reply === option}
                  >
                    <span className="radio-mark" />
                    {option === 'offer' ? 'Make an offer' : option.toUpperCase()}
                  </button>
                ))}
              </div>
            </fieldset>
            {reply === 'offer' && (
              <label className="offer-field">
                Available amount (kW)
                <input type="number" defaultValue={250} />
              </label>
            )}
            <button className="ui-button primary full" onClick={() => setSubmitted(true)}>
              Submit reply
            </button>
            {submitted && (
              <div className="confirmation">
                ✓ Reply submitted: <strong>{reply === 'offer' ? '250 kW offered' : reply.toUpperCase()}</strong>
                <span>Confirmation REP-841 · Simulated</span>
              </div>
            )}
            </>
            )}
          </Panel>
          <Panel title="Participation history" tools={<span className="total-paid">Total event earnings <b>$8,460</b></span>}>
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Reply</th>
                  <th>Delivered</th>
                  <th>Earnings</th>
                </tr>
              </thead>
              <tbody>
                {(
                  [
                    ['Aug 14', 'Yes', '301 kW', '$1,054'],
                    ['Jul 27', 'Yes', '288 kW', '$1,008'],
                    ['Jul 09', 'No', '—', '$0'],
                    ['Jun 18', '250 kW', '242 kW', '$847'],
                  ] as const
                ).map((row) => (
                  <tr key={row[0]}>
                    {row.map((cell, i) => (
                      <td className={i > 1 ? 'mono' : ''} key={`${row[0]}-${i}`}>
                        {cell}
                        {i === 2 && cell !== '—' && <Tag>Simulated</Tag>}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
          <EventInbox buildingId={buildingId} />
        </div>
      </main>
    </div>
  )
}
