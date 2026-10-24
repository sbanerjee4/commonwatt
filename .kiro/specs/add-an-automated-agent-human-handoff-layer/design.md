# Design Document

Automated-Agent + Human-Handoff Layer for the In-App Event Chat

## 1. Approach

The existing in-app chat (`app/routes/chat.py`) and its provider path
(`notify/provider.py:InAppProvider`, `notify/models.py:send_sms`) post the
system "ask" into a thread and let a building manager reply. This design adds
two things on top of that thread:

1. an **automated agent** that answers the manager in `auto` mode, reusing
   `agent/chat.py:ChatSession` + `agent/llm.py` (Bedrock), and
2. a **human-handoff** flip (`auto -> human`) that silences the agent and hands
   the thread to a `utility` operator.

A single new column — `handoff_mode` on the thread — is the switch. The agent
posts only while the thread is `auto`; the operator posts only free text, in
either mode, and a request-human action flips the mode and alerts the operator.

**Schema reconciliation is part of this work (AC-27/AC-28).** The current chat
code imports models that do not exist in `db/models.py` (`Message`,
`EventBuilding`, `OutboundMessage`, `PushSubscription`), uses integer building
ids, and references `AuditLog.reason`/`provider`, `Reply.event_id`/`kw`/
`"counter"`, `Event.closed_at`/`building_ids`, and a `"operator"` role. None of
those exist on main. This design defines the chat storage against main's real
schema and rewires the route, the provider, and the tests onto it.

### Decision — storage shape (`message-storage-shape`, accepted default)

Add a `Thread` table and a `Message` table against main's real schema, keyed by
String(64) building ids with FKs to `events` and `buildings`. `handoff_mode`
lives on `Thread`. This is preferred over resurrecting the old int-based
stand-in models, which would mean migrating main's advanced schema *backwards*.

### Decision — agent-failure fallback (`agent-failure-fallback`, accepted default)

On a Bedrock error, or when an agent reply trips the banned-word check, the
system persists the manager's message, posts one fixed agent message ("A
Commonwatt representative will follow up with you shortly."), and flags the
thread for operator attention — rather than auto-flipping to `human`. The mode
stays `auto`, so a later, healthy manager message can still get an agent reply;
the operator sees the flag and can take over or the manager can press
"Contact a human rep".

## 2. Data model (new, against `db/models.py`)

Both tables use the project's `Base` / `NAMING_CONVENTION`, String(64) building
ids, timezone-aware `server_default=func.now()` timestamps, and named FKs with
`ondelete`.

### 2.1 `threads`

One row per `(event_id, building_id)` conversation.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `Integer` PK autoincrement | |
| `event_id` | `Integer` FK `events.id` `ondelete=CASCADE`, indexed | |
| `building_id` | `String(64)` FK `buildings.id` `ondelete=RESTRICT`, indexed | BERDO id |
| `handoff_mode` | `String(16)` default `"auto"` | CHECK in (`auto`, `human`), name `handoff_mode_allowed` |
| `needs_human` | `Boolean` default `False`, `server_default="0"` | AC-10/AC-16 attention flag |
| `closed_at` | `DateTime(timezone=True)` nullable | operator close (replaces the route's phantom `Event.closed_at`) |
| `created_at` | `DateTime(timezone=True)` `server_default=func.now()` | |

Unique constraint on `(event_id, building_id)` (name
`uq_threads_event_id`), so a thread is created at most once per pair (AC-1).

### 2.2 `messages`

One row per posted message; append-only (AC-5).

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `Integer` PK autoincrement | monotonic ordering + `unread.since` cursor |
| `thread_id` | `Integer` FK `threads.id` `ondelete=CASCADE`, indexed | |
| `event_id` | `Integer` FK `events.id` `ondelete=CASCADE`, indexed | denormalized for convenience |
| `building_id` | `String(64)` FK `buildings.id` `ondelete=RESTRICT`, indexed | |
| `sender_role` | `String(32)` | CHECK in (`system`, `agent`, `building_manager`, `operator`), name `sender_role_allowed` |
| `sender_user_id` | `Integer` FK `users.id` `ondelete=SET NULL` nullable | null for system/agent |
| `body` | `Text` | |
| `created_at` | `DateTime(timezone=True)` `server_default=func.now()` | |

### 2.3 `AuditLog` action values

`AUDIT_ACTIONS` in `db/models.py` is extended (new values only; none removed)
with: `chat_thread_opened`, `chat_agent_reply`, `chat_handoff_requested`,
`chat_operator_message`, `chat_building_reply`, `chat_thread_closed`. The route
writes `AuditLog(user_id=..., event_id=..., building_id=..., action=<one of
those>, detail=<free text>)` — using the real `detail` column, not the
phantom `reason`/`provider` the current code passes (AC-26).

### 2.4 Reconciliation touch-ups

- `notify/provider.py:InAppProvider.send` currently builds `Message(event_id,
  building_id, sender_role="system", ...)`. It is rewired to resolve/create the
  `Thread` for `(event_id, building_id)` and insert a `Message(thread_id=...,
  sender_role="system")`. `building_id` type becomes `str`.
- `notify/models.py:send_sms` references `Event.building_ids`; the in-app path
  resolves membership through `plan_buildings` instead (see §4.1).

No change to `replies`/`call_history`: a structured decision still writes a
`Reply` row the existing way — `Reply(call_id=<the building's call_history row
for this event>, building_id=..., kind=<"yes"|"no"|"offer">, offer_kw=<int|None>)`
(AC-8). There is no `"counter"` kind; a kW counter is `kind="offer"` with
`offer_kw` set.

## 3. Thread membership and the "open event" lookup

`plan_buildings` is the source of truth for which buildings an event asks.
A helper resolves the current open ask for a building:

```python
def open_event_for_building(db, building_id: str) -> Event | None:
    # approved events, newest first, whose current plan version includes this building
    stmt = select(Event).where(Event.status == "approved").order_by(Event.id.desc())
    for ev in db.execute(stmt).scalars():
        exists = db.execute(
            select(PlanBuilding.building_id).where(
                PlanBuilding.event_id == ev.id,
                PlanBuilding.plan_version == ev.current_version,
                PlanBuilding.building_id == building_id,
            )
        ).first()
        if exists and not _thread_closed(db, ev.id, building_id):
            return ev
    return None
```

`_thread_closed` checks the `threads.closed_at` for that pair. "Open" means
the event is approved, the building is in its current plan version, and the
thread (if any) is not closed (AC-25).

## 4. API

All routes stay under the existing `app/routes/chat.py` router and the demo
header-identity scheme (`X-User-Id`, `X-Role`), with `X-Role` ∈
{`building_manager`, `utility`} — the `"operator"` string is replaced by
`utility` to match `users.role` (AC-24). `building_id` path params become `str`.

### 4.1 `GET /inbox/{building_id}` — read thread (AC-22, AC-23)

Returns the thread's messages in id order plus `handoff_mode` and
`needs_human`:

```json
{
  "building_id": "129860",
  "event_id": 42,
  "handoff_mode": "auto",
  "needs_human": false,
  "messages": [
    {"id": 1, "sender_role": "system", "sender_user_id": null,
     "body": "...", "created_at": "..."}
  ]
}
```

`GET /inbox/{building_id}/unread?since=<id>` keeps its current shape, counting
`messages.id > since` for the building's thread.

### 4.2 `POST /inbox/{building_id}/reply` — building manager (AC-6..AC-10, AC-23, AC-25)

Flow:
1. Access check (own building or `utility`); else 403.
2. `open_event_for_building`; if none, 409.
3. Resolve/create the `Thread`; insert a `building_manager` `Message`.
4. Parse with `parse_reply_body`. If `"yes"`/`"no"`/positive int, write a
   `Reply` row tied to the event's `call_history` row for the building
   (`kind="yes"|"no"|"offer"`, `offer_kw=int|None`) (AC-8).
5. If `thread.handoff_mode == "auto"`, generate an agent reply (§5) and insert
   an `agent` `Message` (AC-7). If `"human"`, do **not** (AC-4).
6. One `chat_building_reply` audit row; plus a `chat_agent_reply` row when an
   agent message is posted (AC-26).

Returns `{"ok": true, "parsed_reply": {...}|null, "agent_replied": bool,
"handoff_mode": "..."}`.

### 4.3 `POST /inbox/{building_id}/request-human` — handoff (AC-17..AC-20, AC-23, AC-25)

1. Access check: only the owning `building_manager` (a `utility` user gets 403
   — a utility cannot request a human against itself).
2. `open_event_for_building`; if none, 409.
3. Resolve the `Thread`. If already `human`, idempotent success (AC-20).
4. Set `handoff_mode="human"`, post a `system` message ("A human
   representative has been requested."), write a `chat_handoff_requested`
   audit row (AC-18).
5. Notify the operator via `notify.push.notify_user` for the utility user(s),
   best-effort (AC-19).

Returns `{"ok": true, "handoff_mode": "human"}`.

### 4.4 `POST /inbox/{building_id}/operator-message` — takeover (AC-21, AC-24, AC-15)

1. `X-Role == "utility"` else 403.
2. Banned-word check via `notify.templates._contains_forbidden`; if hit, 422
   before storing (AC-15).
3. `open_event_for_building`; if none, 409.
4. Insert an `operator` `Message`; **never** trigger an agent reply (AC-21).
5. Clear `needs_human` (operator has engaged). Write `chat_operator_message`
   audit row. Best-effort push to the building manager.

### 4.5 `POST /inbox/{building_id}/close` — operator close (AC-24, AC-26)

`utility` only; sets `threads.closed_at`; writes `chat_thread_closed`. After
close, `open_event_for_building` returns `None`, so replies get 409 (AC-25).

## 5. Agent integration (auto mode)

`agent/chat.py` already exposes `make_session(building_id, event_context)` →
`ChatSession.chat(user_message) -> str`, restricted to `building_info` and
`estimate_savings` (both tool-grounded, both return `source_id`). The route
uses it directly; no new Bedrock plumbing.

### 5.1 Seeding event context

Built from the open event + `plan_buildings` + `building_info`, with no
invented numbers:

```python
pb = current_plan_building(db, event, building_id)   # kw_requested, reason
ctx = {
    "window_label": event.window_label,
    "requested_kw": pb.kw_requested,
    "reason": pb.reason or "high afternoon load",
    "estimated_payment_label": "see estimate_savings tool",
    "enrolled_capacity_kw": building.enrolled_capacity_kw,  # may be None
}
session = make_session(building_id, event_context=ctx)
reply = session.chat(body)
```

A fresh `ChatSession` is created per POST (stateless across requests); the
thread's stored `Message` history is the durable record. The prior turns are
not replayed into the model in this iteration — each manager message is
answered from the seeded context + tools, which is sufficient for the
single-ask demo and keeps the path deterministic to test.

### 5.2 Provenance guarantees (AC-11..AC-14)

- `ChatSession` is wired only to `building_info` + `estimate_savings`; there is
  no tool that returns an unsourced number (AC-11).
- `BUILDING_CHAT_SYSTEM` (`agent/prompts.py`) already instructs: never make up
  numbers, always call a tool and cite `source_id`, label estimates, mark
  simulated data, never use banned words. No prompt change is required for
  correctness; the enforcement below is the backstop.

### 5.3 Failure and banned-word enforcement (AC-10, AC-16)

Wrap the agent call:

```python
def agent_reply_or_fallback(db, thread, ctx, body) -> tuple[str, bool]:
    try:
        reply = make_session(thread.building_id, ctx).chat(body)
    except Exception:
        return FALLBACK, True           # Bedrock unavailable/errored (AC-10)
    if _contains_forbidden(reply) is not None:
        return FALLBACK, True           # suppress, do not post the reply (AC-16)
    return reply, False
```

`FALLBACK = "A Commonwatt representative will follow up with you shortly."`
When the fallback fires, set `thread.needs_human = True` and still post the
fallback as an `agent` message. The mode stays `auto`.

## 6. Access control

| Action | `building_manager` (own) | `building_manager` (other) | `utility` |
| --- | --- | --- | --- |
| read thread | ✅ | 403 | ✅ (any) |
| reply | ✅ | 403 | ✅ |
| request-human | ✅ | 403 | 403 |
| operator-message | 403 | 403 | ✅ |
| close | 403 | 403 | ✅ |

Enforced by `_require_building_access(role, user, building_id)` (own-building or
`utility`) plus explicit `utility`-only / owner-only guards. Access is checked
in the route layer only (no DB row-level security), per project convention.

## 7. Migration (AC-28)

One Alembic revision in `db/migrations/versions/`:
- `create_table("threads", ...)` with the CHECK + unique + FKs under
  `NAMING_CONVENTION`.
- `create_table("messages", ...)` with its CHECK + FKs.
- extend the `audit_log` action CHECK: on SQLite via `batch_alter_table` to
  rebuild the constraint; on Postgres drop/add the named CHECK. The
  `AUDIT_ACTIONS` tuple in the model is the source of allowed values.

`Base.metadata.create_all` (used by tests, `app/db.py:init_db`) picks the new
tables up automatically; the migration is for Postgres/`make setup`.

## 8. Testing

Rework `tests/integration/test_chat.py` and `test_chat_extras.py` onto the real
schema (String(64) building ids via a seeded `Building`, `role="utility"` for
the operator, `plan_buildings` for membership, a `CallHistory` row so a parsed
reply has a `call_id`). Add:

- **Auto reply:** manager posts in `auto`; an `agent` message appears
  (Bedrock stubbed via monkeypatching `make_session` to a fake `ChatSession`
  returning a fixed sourced string). (AC-6, AC-7, AC-9)
- **Structured + conversational:** `"YES"` writes one `Reply` (kind `yes`,
  `call_id` set) **and** an `agent` message. (AC-8)
- **kW counter:** `"40 kW"` → `Reply(kind="offer", offer_kw=40)`. (AC-8)
- **Handoff flip:** request-human sets `handoff_mode="human"`, posts a system
  message, writes the audit row; second call is idempotent. (AC-18, AC-20)
- **Agent silent in human mode:** manager posts after flip → no `agent`
  message. (AC-4)
- **Operator takeover:** operator free text stored as `operator`, no agent
  reply, `needs_human` cleared. (AC-21)
- **Banned word (operator):** 422, nothing stored. (AC-15)
- **Banned word (agent):** stub `make_session` to return a forbidden word →
  reply suppressed, fallback posted, `needs_human=True`. (AC-16)
- **Bedrock error:** stub `make_session` to raise → fallback posted, manager
  message still persisted, `needs_human=True`. (AC-10)
- **Access:** other-building read 403; request-human by `utility` 403;
  operator-message by manager 403; reply with no open event 409. (AC-23..AC-25)
- **Provenance unit test:** assert `ChatSession.CHAT_TOOLS` names only
  `building_info` + `estimate_savings`. (AC-11)

All run under SQLite in-memory with `Base.metadata.create_all`, no Bedrock and
no network — the Bedrock pipeline is always stubbed in tests.

## 9. Non-goals (restated from requirements)

No SMS/Twilio changes, no planner/critic changes, no multi-operator routing, no
websocket transport. The thread keeps polling.
