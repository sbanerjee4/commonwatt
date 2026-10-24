import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Tag } from './ui'
import { ApiError } from '../lib/api'
import {
  getThread,
  sendReply,
  requestHuman,
  sendOperatorMessage,
  closeThread,
  type ChatMessage,
  type SenderRole,
} from '../lib/chat'

// Reusable thread view for both sides of the conversation. A thread only
// exists while the building is in an OPEN APPROVED event, so POSTs can 409 and
// GET can return empty messages — both are rendered as states, never thrown.
type ChatThreadProps = {
  buildingId: string
  mode: 'operator' | 'facility'
  title?: string
}

const ROLE_LABELS: Record<SenderRole, string> = {
  system: 'System',
  agent: 'Agent',
  building_manager: 'Facility',
  operator: 'Operator',
}

// building_manager sits on one side; everyone else (operator/agent/system) on
// the other. `.chat-message.user` is the right-aligned bubble.
function isUserSide(sender: SenderRole, mode: 'operator' | 'facility'): boolean {
  return mode === 'facility' ? sender === 'building_manager' : sender !== 'building_manager'
}

function errorDetail(err: unknown): string {
  if (err instanceof ApiError) return err.message
  if (err instanceof Error) return err.message
  return 'Something went wrong.'
}

export function ChatThread({ buildingId, mode, title }: ChatThreadProps) {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState('')

  const thread = useQuery({
    queryKey: ['thread', buildingId],
    queryFn: () => getThread(buildingId),
    refetchInterval: 4000,
  })

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ['thread', buildingId] })
  }

  const send = useMutation({
    mutationFn: (body: string) =>
      mode === 'facility' ? sendReply(buildingId, body) : sendOperatorMessage(buildingId, body),
    onSuccess: () => {
      setDraft('')
      invalidate()
    },
  })

  const human = useMutation({
    mutationFn: () => requestHuman(buildingId),
    onSuccess: invalidate,
  })

  const close = useMutation({
    mutationFn: () => closeThread(buildingId),
    onSuccess: invalidate,
  })

  function onSend() {
    const body = draft.trim()
    if (!body) return
    send.mutate(body)
  }

  const data = thread.data
  const messages: ChatMessage[] = data?.messages ?? []
  const noThread =
    thread.isError && thread.error instanceof ApiError && thread.error.status === 409
  const showHandoffBanner = data ? data.handoff_mode === 'human' || data.needs_human : false
  const actionError = send.error ?? human.error ?? close.error
  const busy = send.isPending || human.isPending || close.isPending

  return (
    <div className="chat-panel">
      {title && (
        <div className="chat-panel-head">
          <strong>{title}</strong>
          {data?.handoff_mode === 'human' && <Tag tone="attention">Human handoff</Tag>}
        </div>
      )}

      {showHandoffBanner && (
        <div className="chat-banner" role="status">
          A human operator is handling this conversation.
        </div>
      )}

      <div className="chat-thread">
        {thread.isLoading && <p className="caption">Loading conversation…</p>}

        {noThread && (
          <p className="caption">
            No active conversation for this facility. A thread opens once the building is part of an
            approved event.
          </p>
        )}

        {!thread.isLoading && !noThread && messages.length === 0 && (
          <p className="caption">No messages yet.</p>
        )}

        {messages.map((m) => (
          <div
            key={m.id}
            className={isUserSide(m.sender_role, mode) ? 'chat-message user' : 'chat-message'}
          >
            <span>{ROLE_LABELS[m.sender_role]}</span>
            <p>{m.body}</p>
          </div>
        ))}
      </div>

      {actionError && (
        <div className="inline-error" role="alert">
          <span>{errorDetail(actionError)}</span>
        </div>
      )}

      <div className="chat-composer">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={mode === 'facility' ? 'Reply to the operator…' : 'Message the facility…'}
          rows={2}
          disabled={busy}
        />
        <button type="button" className="ui-button primary" onClick={onSend} disabled={busy || !draft.trim()}>
          Send
        </button>
      </div>

      <div className="chat-actions">
        {mode === 'facility' && (
          <button
            type="button"
            className="ui-button secondary"
            onClick={() => human.mutate()}
            disabled={busy}
          >
            Contact a human
          </button>
        )}
        {mode === 'operator' && (
          <button
            type="button"
            className="ui-button ghost"
            onClick={() => close.mutate()}
            disabled={busy}
          >
            Close thread
          </button>
        )}
      </div>
    </div>
  )
}
