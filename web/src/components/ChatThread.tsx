import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../lib/api'
import type { ChatMessage } from '../lib/chat'
import { closeThread, getThread, sendOperatorMessage } from '../lib/chat'
import { Tag } from './ui'

const SENDER_LABEL: Record<ChatMessage['sender_role'], string> = {
  operator: 'Operator',
  agent: 'Assistant',
  building_manager: 'Building manager',
  system: 'System',
}

// Live operator view of one building's conversation. Polls GET /inbox/{id}
// every 4s so a reply from the building manager appears without a reload.
// Messages are aligned by sender: building_manager on one side, everyone else
// (operator/agent/system) on the other. Auth is cookie-only — no role headers.
export function ChatThread({ buildingId, title }: { buildingId: string; title?: string }) {
  const queryClient = useQueryClient()
  const [body, setBody] = useState('')

  const thread = useQuery({
    queryKey: ['thread', buildingId],
    queryFn: () => getThread(buildingId),
    refetchInterval: 4000,
    retry: false,
  })

  const send = useMutation({
    mutationFn: (text: string) => sendOperatorMessage(buildingId, text),
    onSuccess: () => {
      setBody('')
      queryClient.invalidateQueries({ queryKey: ['thread', buildingId] })
    },
  })

  const close = useMutation({
    mutationFn: () => closeThread(buildingId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['thread', buildingId] })
    },
  })

  const onSend = () => {
    const text = body.trim()
    if (!text || send.isPending) return
    send.mutate(text)
  }

  const sendErrorMessage = (err: unknown): string => {
    if (err instanceof ApiError) {
      if (err.status === 422) return 'Message rejected: contains a forbidden word'
      if (err.status === 409) return 'No active event for this building yet.'
      return err.message
    }
    return 'Could not send message.'
  }

  const data = thread.data
  const messages = data?.messages ?? []
  const humanRequested = data ? data.handoff_mode === 'human' || data.needs_human : false

  return (
    <div className="conversations-thread">
      <div className="panel-head">
        <strong>{title ?? buildingId}</strong>
        <button
          className="ui-button ghost"
          onClick={() => close.mutate()}
          disabled={close.isPending}
        >
          Close thread
        </button>
      </div>

      {humanRequested && (
        <div className="chat-banner">
          <Tag tone="attention">Building requested a human rep</Tag>
        </div>
      )}

      <div className="chat-thread" aria-live="polite">
        {thread.isError && (
          <p className="caption">Could not load this conversation. Make sure you are signed in.</p>
        )}
        {!thread.isError && messages.length === 0 && (
          <p className="caption">No messages yet.</p>
        )}
        {messages.map((m) => (
          <div
            key={m.id}
            className={`chat-message ${m.sender_role === 'building_manager' ? '' : 'user'}`}
          >
            <span>{SENDER_LABEL[m.sender_role]}</span>
            <p>{m.body}</p>
          </div>
        ))}
      </div>

      <div className="chat-composer">
        <textarea
          value={body}
          placeholder="Message the building manager…"
          onChange={(e) => setBody(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              onSend()
            }
          }}
        />
        <button className="ui-button primary" onClick={onSend} disabled={send.isPending}>
          Send
        </button>
      </div>

      {send.isError && <p className="caption">{sendErrorMessage(send.error)}</p>}
      {close.isError && (
        <p className="caption">
          {close.error instanceof ApiError && close.error.status === 409
            ? 'No active event for this building yet.'
            : 'Could not close the thread.'}
        </p>
      )}
    </div>
  )
}
