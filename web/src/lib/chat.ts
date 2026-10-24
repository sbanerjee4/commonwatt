// Typed client for the two-sided in-app chat (app/routes/chat.py).
//
// A thread only exists while a building is in an OPEN APPROVED event. Until
// then GET /inbox returns empty messages and the POST actions raise 409. The
// callers (ChatThread, the page sidebars) surface those states; this module
// just mirrors the endpoint shapes and wraps apiGet/apiPost.

import { apiGet, apiPost } from './api'

export type SenderRole = 'system' | 'agent' | 'building_manager' | 'operator'

export type HandoffMode = 'auto' | 'human'

export type ChatMessage = {
  id: number
  event_id: number | null
  sender_role: SenderRole
  sender_user_id: number | null
  body: string
  created_at: string
}

export type ChatThread = {
  building_id: string
  event_id: number | null
  handoff_mode: HandoffMode
  needs_human: boolean
  messages: ChatMessage[]
}

export type UnreadResponse = {
  building_id: string
  since: number
  unread: number
}

export type ReplyResponse = {
  ok: boolean
  parsed_reply: unknown
  agent_replied: boolean
  handoff_mode: HandoffMode
}

export type RequestHumanResponse = {
  ok: boolean
  handoff_mode: HandoffMode
}

export type OperatorMessageResponse = {
  ok: boolean
}

export type CloseThreadResponse = {
  ok: boolean
  event_id: number | null
  closed: boolean
}

/** Full thread for a building (polled). GET /inbox/{building_id}. */
export function getThread(buildingId: string): Promise<ChatThread> {
  return apiGet<ChatThread>(`/inbox/${buildingId}`)
}

/** Unread count after a given message id. GET /inbox/{building_id}/unread?since=. */
export function getUnread(buildingId: string, since: number): Promise<UnreadResponse> {
  return apiGet<UnreadResponse>(`/inbox/${buildingId}/unread?since=${since}`)
}

/** Facility / building_manager reply. POST /inbox/{building_id}/reply. */
export function sendReply(buildingId: string, body: string): Promise<ReplyResponse> {
  return apiPost<ReplyResponse>(`/inbox/${buildingId}/reply`, { body })
}

/** Facility asks for a human operator. POST /inbox/{building_id}/request-human. */
export function requestHuman(buildingId: string): Promise<RequestHumanResponse> {
  return apiPost<RequestHumanResponse>(`/inbox/${buildingId}/request-human`)
}

/** Operator (X-Role utility) message. POST /inbox/{building_id}/operator-message. */
export function sendOperatorMessage(buildingId: string, body: string): Promise<OperatorMessageResponse> {
  return apiPost<OperatorMessageResponse>(`/inbox/${buildingId}/operator-message`, { body })
}

/** Operator closes the thread. POST /inbox/{building_id}/close. */
export function closeThread(buildingId: string): Promise<CloseThreadResponse> {
  return apiPost<CloseThreadResponse>(`/inbox/${buildingId}/close`)
}
