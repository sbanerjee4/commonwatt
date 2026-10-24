import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AppHeader, Heading, Panel, Tag } from '../components/ui'
import { ChatThread } from '../components/ChatThread'
import { apiGet } from '../lib/api'
import { getUnread, type ChatThread as ChatThreadData } from '../lib/chat'
import { getSession } from '../lib/session'

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

// Managed-facilities portfolio. STATIC: there is no multi-facility or
// per-facility-earnings endpoint, so these mirror the design mock. The selected
// facility's status card below reads the real /portfolio/buildings/{id}.
const FACILITIES = [
  { name: 'Franklin Street Center', town: 'Boston', status: 'Request today', tone: 'attention', capacityKw: 420, earnings: '$3,214', selected: true },
  { name: 'North Point Offices', town: 'Cambridge', status: 'Available', tone: '', capacityKw: 310, earnings: '$2,408', selected: false },
  { name: 'Harbor Exchange', town: 'Boston', status: 'Available', tone: '', capacityKw: 275, earnings: '$1,692', selected: false },
  { name: 'Riverside Works', town: 'Somerville', status: 'Not asked', tone: '', capacityKw: 190, earnings: '$1,146', selected: false },
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

  // Scope to the signed-in facility's building (AC-27, audit #4) instead of a
  // hardcoded id. Falls back to the first seeded building when absent.
  const buildingId = getSession()?.buildingId ?? 'PH-BLDG-1'

  const building = useQuery({
    queryKey: ['building', buildingId],
    queryFn: () => apiGet<BuildingProfile>(`/portfolio/buildings/${buildingId}`),
  })

  // Chat sidebar: poll unread since the highest message id the facility has
  // seen. `chatOpen` tracks the manual toggle. Unread>0 auto-opens the
  // sidebar and shows a badge; opening the sidebar advances the seen marker
  // to the newest message in the thread so the badge clears.
  const queryClient = useQueryClient()
  const [chatOpen, setChatOpen] = useState(false)
  const [lastSeenId, setLastSeenId] = useState(0)
  const chatOpenRef = useRef(chatOpen)
  chatOpenRef.current = chatOpen

  const unread = useQuery({
    queryKey: ['unread', buildingId, lastSeenId],
    queryFn: () => getUnread(buildingId, lastSeenId),
    refetchInterval: 4000,
    // A thread may not exist yet (409); treat that as "no unread" rather than
    // retrying into an error state.
    retry: false,
  })

  const unreadCount = unread.data?.unread ?? 0

  useEffect(() => {
    if (unreadCount > 0 && !chatOpenRef.current) {
      setChatOpen(true)
    }
  }, [unreadCount])

  // While the sidebar is open, advance the seen marker to the highest message
  // id currently in the cached thread so unread resets to zero.
  useEffect(() => {
    if (!chatOpen) return
    const cached = queryClient.getQueryData<ChatThreadData>(['thread', buildingId])
    const maxId = cached?.messages.reduce((hi, m) => (m.id > hi ? m.id : hi), 0) ?? 0
    if (maxId > lastSeenId) setLastSeenId(maxId)
  }, [chatOpen, unreadCount, buildingId, lastSeenId, queryClient])

  const profile = building.data
  const selectedName = 'Franklin Street Center'
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
          <div className="chat-toggle-wrap">
            <button
              type="button"
              className="ui-button secondary chat-toggle"
              onClick={() => setChatOpen((open) => !open)}
              aria-expanded={chatOpen}
            >
              {chatOpen ? 'Close messages' : 'Messages'}
              {unreadCount > 0 && <span className="chat-sidebar-badge">{unreadCount}</span>}
            </button>
            <Tag>Simulated data</Tag>
          </div>
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
                {FACILITIES.map((f) => (
                  <tr key={f.name} className={f.selected ? 'selected-row' : ''}>
                    <td>
                      <strong>{f.name}</strong>
                      <small>{f.selected ? `Selected · ${f.town}` : f.town}</small>
                    </td>
                    <td>
                      <Tag tone={f.tone}>{f.status}</Tag>
                    </td>
                    <td className="mono">{f.capacityKw} kW</td>
                    <td className="mono">{f.earnings}</td>
                  </tr>
                ))}
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
        </div>
      </main>
      {chatOpen && (
        <aside className="chat-sidebar" aria-label="Facility messages">
          <div className="chat-sidebar-head">
            <strong>Messages</strong>
            <button type="button" className="text-link" onClick={() => setChatOpen(false)}>
              Close
            </button>
          </div>
          <ChatThread buildingId={buildingId} mode="facility" title="Utility conversation" />
        </aside>
      )}
    </div>
  )
}
