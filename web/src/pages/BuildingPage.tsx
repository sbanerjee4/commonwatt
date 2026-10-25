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

type ChatTurn = { role: 'you' | 'assistant'; text: string }

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
  operator: 'Operator',
  agent: 'Assistant',
  building_manager: 'You',
  system: 'System',
}

// Live event inbox: polls GET /inbox/{buildingId} every few seconds so an
// operator message sent from another machine appears here within seconds
// without a page reload (the backend is built for this — see app/routes/chat.py).
// The manager replies via POST /inbox/{buildingId}/reply.
function EventInbox({ buildingId }: { buildingId: string }) {
  const [input, setInput] = useState('')

  const inbox = useQuery({
    queryKey: ['inbox', buildingId],
    queryFn: () => apiGet<InboxResponse>(`/inbox/${buildingId}`),
    refetchInterval: 4000, // poll every 4s for new operator/agent messages
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

  const send = () => {
    const body = input.trim()
    if (!body || reply.isPending) return
    reply.mutate(body)
  }

  const messages = inbox.data?.messages ?? []
  const noEvent = inbox.data && inbox.data.event_id === null

  return (
    <Panel
      title="Event messages"
      tools={<Tag tone={messages.length ? 'attention' : ''}>{messages.length ? 'Live' : 'No event'}</Tag>}
    >
      <p className="request-explainer">
        Messages from your utility operator about today’s event appear here live. Replies are
        recorded against the event.
      </p>

      <div className="chat-thread" aria-live="polite">
        {inbox.isError && (
          <p className="caption">Could not load messages. Make sure you are signed in.</p>
        )}
        {!inbox.isError && noEvent && (
          <p className="caption">No active event for your building right now.</p>
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
      </div>

      <div className="chat-composer">
        <input
          type="text"
          value={input}
          placeholder={noEvent ? 'No active event' : 'Reply to the operator…'}
          disabled={!!noEvent}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') send() }}
        />
        <button className="ui-button primary" onClick={send} disabled={reply.isPending || !!noEvent}>
          Send
        </button>
      </div>
    </Panel>
  )
}

function BuildingChat({ buildingId }: { buildingId: string }) {
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [input, setInput] = useState('')

  const ask = useMutation({
    mutationFn: (message: string) =>
      apiPost<{ buildingId: string; reply: string }>(
        `/portfolio/building/${buildingId}/chat`,
        { message },
        { 'X-Role': 'building_manager' },
      ),
    onSuccess: (data) => {
      setTurns((t) => [...t, { role: 'assistant', text: data.reply }])
    },
  })

  const send = () => {
    const msg = input.trim()
    if (!msg || ask.isPending) return
    setTurns((t) => [...t, { role: 'you', text: msg }])
    setInput('')
    ask.mutate(msg)
  }

  const suggestions = [
    'What is my building and how much could we reduce?',
    'Why was I asked today?',
    'How is my payment estimated?',
  ]

  return (
    <Panel title="Ask the Commonwatt assistant">
      <p className="request-explainer">
        Ask about your building, your energy use, or today’s request. The assistant reads your
        building’s real data and never invents numbers.
      </p>

      <div className="chat-thread" aria-live="polite">
        {turns.length === 0 && (
          <div className="chat-suggestions">
            {suggestions.map((s) => (
              <button type="button" key={s} className="ui-button ghost" onClick={() => { setInput(s) }}>
                {s}
              </button>
            ))}
          </div>
        )}
        {turns.map((t, i) => (
          <div key={i} className={`chat-message ${t.role === 'you' ? 'user' : 'assistant'}`}>
            <span>{t.role === 'you' ? 'You' : 'Assistant'}</span>
            <p>{t.text}</p>
          </div>
        ))}
        {ask.isPending && <div className="chat-message assistant"><span>Assistant</span><p>Thinking…</p></div>}
        {ask.isError && <p className="caption">Could not reach the assistant. Is `make serve` running with a Bedrock key?</p>}
      </div>

      <div className="chat-composer">
        <input
          type="text"
          value={input}
          placeholder="Type a question…"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') send() }}
        />
        <button className="ui-button primary" onClick={send} disabled={ask.isPending}>
          Send
        </button>
      </div>
    </Panel>
  )
}

// Managed-facilities portfolio. STATIC: there is no multi-facility or
// per-facility-earnings endpoint, so these mirror the design mock. The selected
// facility's status card below reads the real /portfolio/buildings/{id}.
const FACILITIES = [
  { name: 'Franklin Street Center', town: 'Boston', status: 'Request today', tone: 'attention', capacityKw: 420, earnings: '$3,214' },
  { name: 'North Point Offices', town: 'Cambridge', status: 'Available', tone: '', capacityKw: 310, earnings: '$2,408' },
  { name: 'Harbor Exchange', town: 'Boston', status: 'Available', tone: '', capacityKw: 275, earnings: '$1,692' },
  { name: 'Riverside Works', town: 'Somerville', status: 'Not asked', tone: '', capacityKw: 190, earnings: '$1,146' },
] as const

const EARNINGS_LEGEND = [
  { key: 'one', name: 'Franklin Street Center', pct: '38%' },
  { key: 'two', name: 'North Point Offices', pct: '28%' },
  { key: 'three', name: 'Harbor Exchange', pct: '20%' },
  { key: 'four', name: 'Riverside Works', pct: '14%' },
] as const

export function BuildingPage() {
  const [reply, setReply] = useState<'yes' | 'no' | 'offer'>('yes')
  const [submitted, setSubmitted] = useState(false)
  const [selectedName, setSelectedName] = useState<string>(FACILITIES[0].name)

  // Scope to the signed-in facility's building (AC-27, audit #4) instead of a
  // hardcoded id. Falls back to the first seeded building when absent.
  const buildingId = getIdentity()?.buildingId ?? 'PH-BLDG-1'

  const building = useQuery({
    queryKey: ['building', buildingId],
    queryFn: () => apiGet<BuildingProfile>(`/portfolio/buildings/${buildingId}`),
  })

  const profile = building.data
  const load =
    profile?.curtailable_load_kw != null ? `${profile.curtailable_load_kw.toLocaleString()} kW` : '420 kW'

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
          <Panel title="Managed facilities" tools={<Tag>4 facilities</Tag>}>
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
                  const isSelected = f.name === selectedName
                  return (
                    <tr
                      key={f.name}
                      className={`facility-row ${isSelected ? 'selected-row' : ''}`.trim()}
                      onClick={() => setSelectedName(f.name)}
                      tabIndex={0}
                      aria-selected={isSelected}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          setSelectedName(f.name)
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
                aria-label="Franklin Street Center 38 percent, North Point Offices 28 percent, Harbor Exchange 20 percent, Riverside Works 14 percent"
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
            <strong>1,284 kW</strong>
            <small>SRC-MTR-220</small>
          </div>
          <div className="ask-status yes">
            <span className="status-symbol">!</span>
            <span>
              <b>Asked to reduce today</b>
              <small>5–7 PM · Reply by 3:30 PM</small>
            </span>
          </div>
        </section>

        <div className="account-grid">
          <Panel title="Current event request">
            <div className="request-explainer">
              The utility is asking whether your building can voluntarily use less electricity from
              5–7 PM. You choose whether to participate.
            </div>
            <div className="live-number">
              <span>Asked to reduce by</span>
              <strong>320 kW</strong>
              <small>Estimate from Event plan #2048</small>
            </div>
            <p className="why">
              <strong>Why this building?</strong>
              Your building has available capacity, and this event stays within the neighborhood equity cap.
            </p>
            <div className="payment">
              <span>Expected event earnings</span>
              <strong>$1,120</strong>
              <small>320 kW × event rate; finalized after meter verification</small>
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
          <BuildingChat buildingId={buildingId} />
        </div>
      </main>
    </div>
  )
}
