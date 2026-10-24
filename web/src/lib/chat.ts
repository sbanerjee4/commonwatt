// Typed client for the operator "Facility conversations" chat, backed by the
// FastAPI inbox endpoints (app/routes/chat.py). Identity is resolved entirely
// from the HttpOnly `cw_session` cookie (app/deps.py) — apiGet/apiPost already
// send `credentials: 'include'`, so we deliberately send NO X-Role/X-User-Id
// headers from here. The logged-in utility user is authorized for any
// building's thread.

import { apiGet, apiPost } from './api'

export type ChatSenderRole = 'system' | 'agent' | 'building_manager' | 'operator'

export type ChatMessage = {
  id: number
  event_id: number | null
  sender_role: ChatSenderRole
  sender_user_id: number | null
  body: string
  created_at: string | null
}

// Shape of GET /inbox/{building_id}.
export type ChatThread = {
  building_id: string
  event_id: number | null
  handoff_mode: 'auto' | 'human'
  needs_human: boolean
  messages: ChatMessage[]
}

// Shape of GET /inbox/{building_id}/unread?since={id}.
export type UnreadResponse = {
  building_id: string
  since: number
  unread: number
}

export function getThread(buildingId: string): Promise<ChatThread> {
  return apiGet<ChatThread>(`/inbox/${buildingId}`)
}

export function getUnread(buildingId: string, since: number): Promise<UnreadResponse> {
  return apiGet<UnreadResponse>(`/inbox/${buildingId}/unread?since=${since}`)
}

export function sendOperatorMessage(buildingId: string, body: string): Promise<{ ok: boolean }> {
  return apiPost<{ ok: boolean }>(`/inbox/${buildingId}/operator-message`, { body })
}

export function closeThread(
  buildingId: string,
): Promise<{ ok: boolean; event_id: number | null; closed: boolean }> {
  return apiPost<{ ok: boolean; event_id: number | null; closed: boolean }>(
    `/inbox/${buildingId}/close`,
  )
}
