# Implementation Plan

Automated-Agent + Human-Handoff Layer for the In-App Event Chat

Ordered bottom-up: models and migration first, then the lookup helpers and the
agent wrapper, then the routes, then the reconciled tests, then demo wiring.
Each task names the files it touches and the acceptance criteria it satisfies.
Every task ends able to run `pytest` green. ACs are defined in
`requirements.md`; the technical shapes are fixed in `design.md`.

## 1. Data model

- [ ] **1.1 Add `Thread` and `Message` models** to `db/models.py`
  - `Thread`: `id`, `event_id` FK `events.id` CASCADE, `building_id`
    `String(64)` FK `buildings.id` RESTRICT, `handoff_mode` `String(16)`
    default `"auto"` + CHECK `handoff_mode_allowed in (auto, human)`,
    `needs_human` `Boolean` default False `server_default="0"`, `closed_at`
    nullable `DateTime(timezone=True)`, `created_at` `server_default=func.now()`,
    unique `(event_id, building_id)`.
  - `Message`: `id`, `thread_id` FK `threads.id` CASCADE, `event_id` FK
    `events.id` CASCADE, `building_id` `String(64)` FK `buildings.id` RESTRICT,
    `sender_role` `String(32)` + CHECK `sender_role_allowed in (system, agent,
    building_manager, operator)`, `sender_user_id` `Integer` FK `users.id`
    `SET NULL` nullable, `body` `Text`, `created_at` `server_default=func.now()`.
  - Add both to `__all__`. Use `Base` / `NAMING_CONVENTION`.
  - _AC-2, AC-5, AC-27_

- [ ] **1.2 Extend `AUDIT_ACTIONS`** in `db/models.py` with the new values:
  `chat_thread_opened`, `chat_agent_reply`, `chat_handoff_requested`,
  `chat_operator_message`, `chat_building_reply`, `chat_thread_closed`
  (append only; remove nothing).
  - _AC-26_

- [ ] **1.3 Alembic migration** in `db/migrations/versions/`
  - `create_table("threads", ...)` and `create_table("messages", ...)` with the
    CHECK, unique, and FK constraints under the naming convention.
  - Rebuild the `audit_log` action CHECK to include the new values: SQLite via
    `op.batch_alter_table`, Postgres via drop/add of the named CHECK.
  - Verify `alembic upgrade head` runs on a fresh SQLite file and
    `Base.metadata.create_all` still matches.
  - _AC-28_

## 2. Lookup helpers and reconciliation

- [ ] **2.1 `open_event_for_building(db, building_id: str) -> Event | None`**
  in `app/routes/chat.py` (or a small `app/routes/_chat_helpers.py`): approved
  events newest-first whose `current_version` `plan_buildings` includes the
  building and whose thread is not closed. Add `current_plan_building(db, event,
  building_id)` returning the `PlanBuilding` (for `kw_requested`, `reason`), and
  `get_or_create_thread(db, event_id, building_id)`.
  - _AC-1, AC-25_

- [ ] **2.2 Rewire `InAppProvider`** in `notify/provider.py`: `building_id` is
  `str`; `send` resolves/creates the `Thread` for `(event_id, building_id)` and
  inserts `Message(thread_id=..., event_id=..., building_id=...,
  sender_role="system", body=body)`; `provider_sid=f"INAPP{msg.id}"`.
  - _AC-1, AC-5_

- [ ] **2.3 Fix `send_sms` in-app membership check** in `notify/models.py`:
  replace the `event.building_ids` reference on the in-app path with a
  `plan_buildings` membership check (reuse the 2.1 helper). Leave the SMS path
  untouched.
  - _AC-27_

## 3. Agent wrapper (auto mode)

- [ ] **3.1 `build_event_context(db, event, building_id)`** in a new
  `app/routes/_chat_agent.py`: assemble `{window_label, requested_kw, reason,
  estimated_payment_label, enrolled_capacity_kw}` from the event,
  `current_plan_building`, and the `Building` row — no invented numbers; missing
  values pass through as `None` / the tool-deferral label.
  - _AC-6, AC-12_

- [ ] **3.2 `agent_reply_or_fallback(db, thread, ctx, body) -> (str, bool)`** in
  `app/routes/_chat_agent.py`: call `make_session(thread.building_id,
  ctx).chat(body)` inside try/except; on exception return `(FALLBACK, True)`;
  if `notify.templates._contains_forbidden(reply)` hits, return
  `(FALLBACK, True)`; else `(reply, False)`. `FALLBACK = "A Commonwatt
  representative will follow up with you shortly."` The boolean is "fell back".
  - _AC-10, AC-16_

## 4. Routes

- [ ] **4.1 Rewrite `GET /inbox/{building_id}`** (`building_id: str`): resolve
  the open event + thread, return `building_id`, `event_id`, `handoff_mode`,
  `needs_human`, and ordered `messages`. Keep `/unread` counting
  `messages.id > since` for the building's thread.
  - _AC-22, AC-23_

- [ ] **4.2 Rewrite `POST /inbox/{building_id}/reply`**: access check (own or
  `utility`, else 403); `open_event_for_building` else 409; create thread if
  needed; insert `building_manager` message; parse via `parse_reply_body` and,
  on a structured decision, write `Reply(call_id=<event's call_history row for
  the building>, building_id, kind in {yes,no,offer}, offer_kw=int|None)`; if
  `handoff_mode=="auto"` run `agent_reply_or_fallback` and insert an `agent`
  message, setting `needs_human=True` when it fell back; one
  `chat_building_reply` audit row and a `chat_agent_reply` row when an agent
  message posts. Return `{ok, parsed_reply, agent_replied, handoff_mode}`.
  - _AC-3, AC-6, AC-7, AC-8, AC-9, AC-10, AC-16, AC-23, AC-25, AC-26_

- [ ] **4.3 Add `POST /inbox/{building_id}/request-human`**: owning
  `building_manager` only (`utility` → 403); `open_event_for_building` else 409;
  if thread already `human`, idempotent success; else set
  `handoff_mode="human"`, post a `system` message, write
  `chat_handoff_requested`, and `notify.push.notify_user` the utility user(s)
  best-effort. Return `{ok, handoff_mode:"human"}`.
  - _AC-17, AC-18, AC-19, AC-20, AC-23, AC-25_

- [ ] **4.4 Rewrite `POST /inbox/{building_id}/operator-message`**: `utility`
  only (else 403); `_contains_forbidden` → 422 before storing;
  `open_event_for_building` else 409; insert `operator` message; never trigger
  an agent reply; clear `needs_human`; `chat_operator_message` audit row;
  best-effort push to the manager.
  - _AC-4, AC-15, AC-21, AC-24, AC-25, AC-26_

- [ ] **4.5 Rewrite `POST /inbox/{building_id}/close`**: `utility` only; set
  `threads.closed_at`; write `chat_thread_closed`; after close
  `open_event_for_building` returns None.
  - _AC-24, AC-25, AC-26_

## 5. Tests (reconciled onto the real schema)

- [ ] **5.1 Rework the chat fixture** in `tests/integration/test_chat.py` and
  `test_chat_extras.py`: seed `Utility`, `Zip`, `Building` (String(64) id),
  `User` manager + `role="utility"` operator, an approved `Event`, a
  `PlanBuilding` row for the current version, and a `CallHistory` row so parsed
  replies have a `call_id`. SQLite in-memory + `Base.metadata.create_all`.
  Monkeypatch `make_session` to a fake `ChatSession` returning a fixed sourced
  string (no Bedrock, no network).
  - _AC-27_

- [ ] **5.2 Auto reply + structured decision tests**: manager message in `auto`
  yields an `agent` message (AC-6/7/9); `"YES"` writes one `Reply(kind="yes",
  call_id set)` **and** an agent message (AC-8); `"40 kW"` →
  `Reply(kind="offer", offer_kw=40)` (AC-8).
  - _AC-6, AC-7, AC-8, AC-9_

- [ ] **5.3 Handoff + silence tests**: request-human flips to `human`, posts a
  system message, writes the audit row (AC-18); second call idempotent (AC-20);
  a manager message after the flip produces **no** agent message (AC-4).
  - _AC-4, AC-18, AC-20_

- [ ] **5.4 Operator + banned-word + fallback tests**: operator free text stored
  as `operator`, no agent reply, `needs_human` cleared (AC-21); operator banned
  word → 422, nothing stored (AC-15); stub `make_session` returning a forbidden
  word → agent reply suppressed, fallback posted, `needs_human=True` (AC-16);
  stub `make_session` raising → fallback posted, manager message still
  persisted, `needs_human=True` (AC-10).
  - _AC-10, AC-15, AC-16, AC-21_

- [ ] **5.5 Access + provenance tests**: other-building read 403 (AC-23);
  request-human by `utility` 403 (AC-23); operator-message by manager 403
  (AC-24); reply with no open event 409 (AC-25); a unit test asserting
  `agent.chat.CHAT_TOOLS` names only `building_info` + `estimate_savings`
  (AC-11).
  - _AC-11, AC-23, AC-24, AC-25_

## 6. Demo wiring and verification

- [ ] **6.1 Confirm router registration** in `app/main.py` includes the chat
  router (it does) and that `make demo` seeds at least one approved event with a
  `plan_buildings` row and a `CallHistory` row for a demo building, so a live
  thread exists to exercise the agent. Update `db/seed.py` only if that seed is
  missing.
  - _AC-1_

- [ ] **6.2 Run the gates**: `pytest` green; `scripts/presubmit.sh` (banned-word
  + constants-citation hooks) clean; confirm no remaining import of a phantom
  model (`Message`/`EventBuilding`/`OutboundMessage`/`PushSubscription` only
  where now defined) via a repo grep.
  - _AC-15, AC-16, AC-27_
