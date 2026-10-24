# Requirements Document

Commonwatt: Automated-Agent + Human-Handoff Layer for the In-App Event Chat

## Overview

Commonwatt already has an in-app event chat (`app/routes/chat.py`): when an
approved event asks a building to reduce load, a thread keyed by
`(event, building)` carries the conversation, the building manager replies on
their own page, and a utility operator can post free text to take over. Today
that takeover is fully manual — a human operator must watch every thread and
type every reply.

This feature adds an **automated utilities agent** that carries the
conversation by default, plus a **clean human-handoff path**. When an event is
approved, the automated agent (reusing the existing `agent/chat.py`
`ChatSession` and `agent/llm.py` Bedrock pipeline) answers the building
manager's questions from tool-grounded data. The building manager has a
**"Contact a human rep"** control; using it flips the thread to human mode,
notifies the operator, and from that point only the operator's free-text
replies are posted — the agent goes silent for that thread.

The agent is bound by the project's existing safety and provenance rules: it
**never invents a number** (every figure comes from an MCP tool result with a
`source_id`) and **never uses banned words** (`cut`, `shut off`, `curtail`,
`disconnect`).

**Channel decision — SMS is removed.** The project has fully switched off paid
SMS / Twilio; the only participant channels are the **in-app event chat** and
**browser (Web Push) notifications**. This feature therefore also *removes* the
SMS pathway rather than reconciling it: the Twilio webhook, the SMS send
orchestration, the Twilio provider, SMS-only user fields, and the SMS-only
tests are deleted, and the in-app "ask" that formerly rode on `send_sms` is
posted directly into the thread. Browser push (`notify/push.py`,
`app/routes/push.py`) is kept and is the sole out-of-band nudge.

### Grounding note — schema reconciliation (read before Design)

The spec is planned against **main's real schema** in `db/models.py`:

- building ids are `String(64)` (BERDO ids), not integers;
- user roles are `utility` and `building_manager` (there is no `operator`
  role value — the operator is a `utility` user);
- `Reply` has `call_id` (FK to `call_history`), `kind` ∈ {`yes`, `no`,
  `offer`}, and `offer_kw`; it does **not** have `event_id`, a `counter` kind,
  or a `kw` column;
- `AuditLog` has `action` (from a fixed allow-list) and `detail`; it does
  **not** have `reason` or `provider`;
- `Event` has `status` ∈ {`draft`, `approved`, `rejected`} and
  `current_version`; it does **not** have `closed_at` or a `building_ids`
  attribute;
- event membership lives in `plan_buildings` (composite key
  `event_id, plan_version, building_id`);
- there is no `Message` or `Thread` model yet, and `User` has no `phone` /
  `sms_opted_out`.

The merged `sanchali-text-alert` branch committed an SMS + in-app chat
subsystem (`app/routes/{chat,sms,push}.py`, `notify/{models,provider,push,
templates,validation}.py`, and the `tests/` SMS suite) that was written against
a different, never-merged schema: it imports `Message`, `OutboundMessage`,
`PushSubscription`, `EventBuilding`, and `notify.schema`, uses integer building
ids and a `"operator"` role, and references `AuditLog.reason`/`provider`,
`Reply.event_id`/`kw`/`"counter"`, `Event.closed_at`/`building_ids`, and
`User.phone`/`sms_opted_out`. As committed, the branch does **not** import,
`app.main` does **not** boot, and the test suite does **not** collect.

Because SMS is now removed, this feature does not reconcile the SMS code — it
**deletes** it (see the SMS-removal acceptance criteria below) and reconciles
only the surviving in-app + push surface onto main's real schema. The exact
new tables and the delete list are fixed in `design.md`; this document states
the user-visible behaviour and the acceptance criteria.

## Users and goals

| User | Role (`users.role`) | Surface | Goal |
| --- | --- | --- | --- |
| Building manager | `building_manager` | Building account chat thread | Ask about the building's ask, reply YES / NO / counter kW, and reach a human when the agent cannot help |
| Utility operator | `utility` | Operator thread view | Monitor threads, be alerted when a manager requests a human, and take over with free text |
| Automated agent | — (system) | Posts into the thread | Answer the manager from tool-grounded data while the thread is in auto mode |

## User Stories

### Automated agent carries the conversation

- **US-1** As a building manager, when my building is asked to participate in
  an approved event, I want to ask questions in the thread and get immediate,
  accurate answers so that I can decide without waiting for a person.
- **US-2** As a utility operator, I want the agent to handle routine questions
  automatically so that I only step in when a manager actually needs me.
- **US-3** As a building manager, I want every number the agent gives me
  (requested kW, estimated payment, my building's load) to be real and
  sourced so that I can trust the ask.

### Human handoff

- **US-4** As a building manager, I want a clear "Contact a human rep" control
  so that I can reach a person when the agent cannot help or I want to
  negotiate.
- **US-5** As a utility operator, I want to be notified the moment a thread is
  handed to a human so that no request sits unanswered.
- **US-6** As a utility operator, once a thread is in human mode, I want my
  free-text replies to be the only ones posted so that the agent does not talk
  over me.
- **US-7** As a building manager, I want the thread to clearly show when I am
  talking to the automated agent versus a human so that I know who answered.

### Safety and provenance (cross-cutting)

- **US-8** As the utility, I want the agent to be constitutionally unable to
  invent a figure or use prohibited language so that every message is safe and
  defensible.

### Channel

- **US-9** As the utility, I want the product to use only in-app chat and
  browser notifications — no SMS/Twilio — so there is no paid channel, no phone
  numbers to store, and one less thing that can leak or cost money.

## Acceptance Criteria

Format: EARS (Easy Approach to Requirements Syntax). IDs are stable and are
referenced by `design.md` and `tasks.md`.

### Thread mode and lifecycle

- **AC-1** WHEN an event transitions to `approved` and a building is in that
  event's current plan version, THE SYSTEM SHALL ensure a chat thread exists
  for that `(event, building)` pair with `handoff_mode = "auto"`.
- **AC-2** THE SYSTEM SHALL store exactly one `handoff_mode` per thread, whose
  value is one of `auto` or `human`, defaulting to `auto`.
- **AC-3** WHEN a thread is in `auto` mode, THE SYSTEM SHALL allow the
  automated agent to post assistant messages into that thread.
- **AC-4** WHEN a thread is in `human` mode, THE SYSTEM SHALL NOT post any
  agent-generated message into that thread, even if a building-manager message
  arrives.
- **AC-5** THE SYSTEM SHALL keep every message of a thread (system, agent,
  building_manager, operator) in order and never delete one, so the full
  conversation is auditable.

### Automated agent replies (auto mode)

- **AC-6** WHEN a building manager posts a message into an `auto`-mode thread,
  THE SYSTEM SHALL generate an agent reply using the existing `agent/chat.py`
  `ChatSession` seeded with the building id and the event context (window,
  requested kW, reason, estimated payment, enrolled capacity).
- **AC-7** WHEN the agent produces a reply, THE SYSTEM SHALL persist it as a
  message with `sender_role = "agent"` in the same thread.
- **AC-8** IF the manager's message parses to a structured decision
  (YES / NO / a positive kW counter) via `parse_reply_body`, THEN THE SYSTEM
  SHALL additionally record a structured `replies` row (tied to the building's
  `call_history` row for the event) AND still post the agent's conversational
  reply.
- **AC-9** THE SYSTEM SHALL generate the agent reply synchronously within the
  manager's POST so that the thread poll returns the agent message without a
  separate trigger.
- **AC-10** IF the Bedrock pipeline is unavailable or errors, THEN THE SYSTEM
  SHALL persist the manager's message, SHALL NOT fabricate an agent reply, and
  SHALL post a single fixed agent message stating a human will follow up and
  flagging the thread for operator attention.

### Provenance — never invent a number

- **AC-11** THE SYSTEM SHALL restrict the agent to the read-only MCP tools
  (`building_info`, `estimate_savings`) for any figure it states, and SHALL
  provide no tool that returns an unsourced number.
- **AC-12** THE agent SHALL NOT state a rate, payment, load, emissions, or
  enrollment figure that did not come from a tool result; WHEN the data is
  unavailable, THE agent SHALL say so rather than estimate silently.
- **AC-13** WHERE a figure is an estimate (e.g. payment, savings), THE agent
  SHALL label it "estimated" and SHALL keep its assumptions retrievable.
- **AC-14** WHERE data is simulated (replies, meter reads, enrollment), THE
  agent SHALL mark it as simulated in its reply.

### Safety — banned words

- **AC-15** THE SYSTEM SHALL reject (HTTP 422) any operator free-text message
  that contains a forbidden word (`cut`, `shut off`, `curtail`, `disconnect`),
  checked case-insensitively on word boundaries, before it is stored.
- **AC-16** THE SYSTEM SHALL pass every agent-generated reply through the same
  forbidden-word check before persisting it; IF a forbidden word is present,
  THEN THE SYSTEM SHALL suppress that reply and apply the AC-10 fallback
  instead of posting it.

### Human handoff

- **AC-17** THE SYSTEM SHALL expose a request-human action
  (`POST /inbox/{building_id}/request-human`) callable by the building manager
  who owns that building.
- **AC-18** WHEN the owning building manager calls request-human on an
  `auto`-mode thread, THE SYSTEM SHALL set `handoff_mode = "human"`, record an
  audit-log entry, and post a system message into the thread stating a human
  has been requested.
- **AC-19** WHEN a thread flips to `human` mode, THE SYSTEM SHALL notify the
  utility operator via the existing best-effort push channel
  (`notify.push.notify_user`), degrading cleanly to a no-op when push is not
  configured.
- **AC-20** WHEN request-human is called on a thread already in `human` mode,
  THE SYSTEM SHALL treat it as idempotent (no duplicate flip, no duplicate
  system message) and return success.
- **AC-21** WHEN a utility operator posts a free-text message into a
  `human`-mode thread, THE SYSTEM SHALL store it with
  `sender_role = "operator"` and SHALL NOT trigger an agent reply.
- **AC-22** THE SYSTEM SHALL return each thread's current `handoff_mode` in the
  thread-read response so the UI can label who is answering (US-7).

### Access control

- **AC-23** THE SYSTEM SHALL allow a `building_manager` to read, reply to, and
  request-human on only their own building's thread (`users.building_id`
  match), and SHALL return HTTP 403 otherwise.
- **AC-24** THE SYSTEM SHALL allow a `utility` user to read any thread and to
  post operator messages to any thread for the demo utility, and SHALL return
  HTTP 403 when a non-`utility` user attempts an operator-message or close
  action.
- **AC-25** THE SYSTEM SHALL reject a reply, operator-message, or request-human
  call when there is no open approved event for the building (HTTP 409).

### Audit

- **AC-26** THE SYSTEM SHALL write exactly one `audit_log` row for each of:
  agent reply posted, handoff requested, operator takeover message, and thread
  closed; each using an `action` value drawn from the model's fixed allow-list.

### Compatibility with main

- **AC-27** All new storage (thread/message/mode) SHALL be defined against
  main's real `db/models.py` (String(64) building ids, the
  `replies`/`call_history` model, the existing `users`/`events`/`sessions`
  and `plan_buildings`), and the full test suite SHALL pass against those real
  models — not against the stand-in models the current chat route imports.
- **AC-28** THE schema change SHALL ship as an Alembic migration consistent
  with the project's naming convention, runnable on both SQLite (dev/test) and
  Postgres.

### SMS removal

- **AC-29** THE SYSTEM SHALL NOT contain an SMS/Twilio send or receive path:
  the Twilio inbound webhook (`app/routes/sms.py`), the SMS send orchestration
  (`notify/models.py:send_sms` and `OutboundMessage`), the `TwilioProvider`,
  the Twilio signature validator, the SMS-only templates, and the
  Twilio-related config and scripts SHALL be removed.
- **AC-30** THE `User` model SHALL NOT carry SMS-only fields (`phone`,
  `sms_opted_out`), and no code path SHALL reference them.
- **AC-31** AFTER removal, `app.main` SHALL import and boot, the only
  participant channels SHALL be the in-app thread and browser Web Push
  (`notify/push.py`, `app/routes/push.py`), and the full test suite SHALL
  collect and pass with no SMS tests remaining.

## Out of scope

- **Any SMS / Twilio functionality** — it is removed, not deferred (AC-29).
- Changing the planner/critic dispatch logic or the operator event-approval
  flow.
- Multi-operator routing or operator presence/assignment; any `utility` user
  may take over any thread for the demo utility.
- A websocket/live-push transport for the thread itself; the thread keeps its
  existing few-second polling model. Browser Web Push remains the only
  out-of-band nudge, best-effort and a no-op without VAPID keys.
