import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { AppHeader, Heading, Panel, Tag } from '../components/ui'
import { apiGet, apiPost } from '../lib/api'

// Demo building id (matches the Makefile `chat` default). A real auth session
// would scope this to the signed-in facility manager's building_id (AC-27).
const DEMO_BUILDING_ID = '129860'

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
    <Panel title="Ask the Commonwatt assistant" tools={<Tag>AI · reads your building data</Tag>}>
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

export function BuildingPage() {
  const [reply, setReply] = useState<'yes' | 'no' | 'offer'>('yes')
  const [submitted, setSubmitted] = useState(false)

  const building = useQuery({
    queryKey: ['building', DEMO_BUILDING_ID],
    queryFn: () => apiGet<BuildingProfile>(`/portfolio/buildings/${DEMO_BUILDING_ID}`),
  })

  const profile = building.data
  const address = profile?.address ?? 'Your facility'
  const load =
    profile?.curtailable_load_kw != null ? `${profile.curtailable_load_kw.toLocaleString()} kW` : 'Load unknown'

  return (
    <div className="workspace">
      <AppHeader context={address} />
      <main className="account">
        <div className="dashboard-title">
          <div>
            <p className="kicker">Facility manager account</p>
            <Heading level={1}>{address}</Heading>
            {profile && (
              <p>
                {profile.property_type} · {profile.gross_area_sf?.toLocaleString()} sq ft · zip {profile.zip}
              </p>
            )}
          </div>
          <Tag>Simulated data</Tag>
        </div>

        {building.isError && (
          <p className="caption">
            Could not reach the API. Locally, run `make serve` (port 8000). On a deployed site, set
            VITE_API_BASE_URL to the backend URL.
          </p>
        )}

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
              Curtailable basis <Tag>Simulated</Tag>
            </span>
            <strong>{profile?.load_basis ?? '—'}</strong>
            <small>{profile?.source_id ?? 'SRC-MTR-220'}</small>
          </div>
          <div className="ask-status yes">
            <span className="status-symbol">!</span>
            <span>
              <b>Asked to reduce today</b>
              <small>5–7 PM · Reply requested</small>
            </span>
          </div>
        </section>

        <div className="account-grid">
          <Panel title="Current event request" tools={<Tag tone="attention">Reply by 3:30 PM</Tag>}>
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
          <BuildingChat buildingId={DEMO_BUILDING_ID} />
        </div>
      </main>
    </div>
  )
}
