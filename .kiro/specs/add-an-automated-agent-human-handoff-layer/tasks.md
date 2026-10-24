# Implementation Plan

Automated-Agent + Human-Handoff Layer for the In-App Event Chat

Ordered bottom-up: models and migration first, then SMS removal, then the
lookup helpers and the agent wrapper, then the routes, then the reconciled
tests, then demo wiring. Each task names the files it touches and the
acceptance criteria it satisfies. Every task ends able to run `pytest` green.
ACs are defined in `requirements.md`; the technical shapes are fixed in
`design.md`.

**Context after the merge:** the merged `sanchali-text-alert` branch committed
an SMS + chat subsystem against a never-merged schema, so the branch does not
import or collect. SMS is being removed, so these tasks DELETE the SMS code and
reconcile only the surviving in-app + browser-push surface onto main's schema.

## 1. Data model

- [x] **1.1 Add `Thread` and `Message` models** to `db/models.py`
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

- [x] **1.2 Extend `AUDIT_ACTIONS`** in `db/models.py` with the new values:
  `chat_agent_reply`, `chat_handoff_requested`, `chat_operator_message`,
  `chat_building_reply`, `chat_thread_closed` (append only; remove nothing).
  Thread creation writes no audit row (`audit_log.user_id` is NOT NULL and the
  system ask has no acting user).
  - _AC-26_

- [x] **1.3 Alembic migration** in `db/migrations/versions/`
  - `create_table("threads", ...)` and `create_table("messages", ...)` with the
    CHECK, unique, and FK constraints under the naming convention.
  - Rebuild the `audit_log` action CHECK to include the new values: SQLite via
    `op.batch_alter_table`, Postgres via drop/add of the named CHECK.
  - Verify `alembic upgrade head` runs on a fresh SQLite file and
    `Base.metadata.create_all` still matches.
  - _AC-28_

- [x] **1.4 Add `PushSubscription` model + migration table** so browser push
  works against the real schema: `id`, `user_id` FK `users.id` CASCADE indexed,
  `endpoint` `String(512)` unique, `p256dh` `String(255)`, `auth` `String(255)`,
  `created_at`. Add to `__all__` and `create_table("push_subscriptions", ...)`
  in revision `0002`.
  - _AC-31_

## 2. SMS removal

- [x] **2.1 Delete the SMS code paths**
  - Remove `app/routes/sms.py` and its `include_router` in `app/main.py`.
  - Remove `notify/models.py` (`send_sms` / `OutboundMessage`); the in-app ask
    moves to `post_system_ask` (task 3.2).
  - In `notify/provider.py` remove `TwilioProvider`, `SimulatedProvider`, and
    the SMS branches of `resolve_provider`; keep only the in-app post path.
  - In `notify/validation.py` remove `validate_signature` (keep
    `parse_reply_body`).
  - In `notify/templates.py` drop the operator_* SMS templates and the
    160-char limit; keep `FORBIDDEN_WORDS` + `_contains_forbidden`; repurpose
    the `building_ask` text as the in-app ask string.
  - Remove `twilio_auth_token` / `webhook_url` from `app/config.py` and delete
    `scripts/send_test_sms.py`.
  - _AC-29_

- [x] **2.2 Remove SMS-only `User` fields**: delete `User.phone` and
  `User.sms_opted_out` wherever they appear (they were never on main), and
  confirm nothing references them.
  - _AC-30_

## 3. Lookup helpers, agent wrapper, and the in-app ask

- [x] **3.1 Chat helpers** in `app/routes/_chat_helpers.py`:
  `open_event_for_building(db, building_id: str)` (approved events newest-first
  whose current-version `plan_buildings` includes the building and whose thread
  is not closed), `current_plan_building`, `get_or_create_thread`,
  `call_history_for`, and `post_message`.
  - _AC-1, AC-25_

- [x] **3.2 `post_system_ask(db, event, building_id, body)`** (in
  `_chat_helpers.py` or the provider): resolve/create the `Thread` and insert a
  `system` `Message`; `building_id` is `str`; membership via `plan_buildings`.
  This replaces the deleted `send_sms` in-app entry point.
  - _AC-1, AC-5_

- [x] **3.3 `build_event_context(db, event, building_id)`** in a new
  `app/routes/_chat_agent.py`: assemble `{window_label, requested_kw, reason,
  estimated_payment_label, enrolled_capacity_kw}` from the event,
  `current_plan_building`, and the `Building` row — no invented numbers; missing
  values pass through as `None` / the tool-deferral label.
  - _AC-6, AC-12_

- [x] **3.4 `agent_reply_or_fallback(db, thread, ctx, body) -> (str, bool)`** in
  `app/routes/_chat_agent.py`: call `make_session(thread.building_id,
  ctx).chat(body)` inside try/except; on exception return `(FALLBACK, True)`;
  if `notify.templates._contains_forbidden(reply)` hits, return
  `(FALLBACK, True)`; else `(reply, False)`. `FALLBACK = "A Commonwatt
  representative will follow up with you shortly."` The boolean is "fell back".
  - _AC-10, AC-16_

## 4. Routes

- [x] **4.1 Rewrite `GET /inbox/{building_id}`** (`building_id: str`): resolve
  the open event + thread, return `building_id`, `event_id`, `handoff_mode`,
  `needs_human`, and ordered `messages`. Keep `/unread` counting
  `messages.id > since` for the building's thread.
  - _AC-22, AC-23_

- [x] **4.2 Rewrite `POST /inbox/{building_id}/reply`**: access check (own or
  `utility`, else 403); `open_event_for_building` else 409; create thread if
  needed; insert `building_manager` message; parse via `parse_reply_body` and,
  on a structured decision, write `Reply(call_id=<event's call_history row for
  the building>, building_id, kind in {yes,no,offer}, offer_kw=int|None)`; if
  `handoff_mode=="auto"` run `agent_reply_or_fallback` and insert an `agent`
  message, setting `needs_human=True` when it fell back; one
  `chat_building_reply` audit row and a `chat_agent_reply` row when an agent
  message posts. Return `{ok, parsed_reply, agent_replied, handoff_mode}`.
  - _AC-3, AC-6, AC-7, AC-8, AC-9, AC-10, AC-16, AC-23, AC-25, AC-26_

- [x] **4.3 Add `POST /inbox/{building_id}/request-human`**: owning
  `building_manager` only (`utility` → 403); `open_event_for_building` else 409;
  if thread already `human`, idempotent success; else set
  `handoff_mode="human"`, post a `system` message, write
  `chat_handoff_requested`, and `notify.push.notify_user` the utility user(s)
  best-effort. Return `{ok, handoff_mode:"human"}`.
  - _AC-17, AC-18, AC-19, AC-20, AC-23, AC-25_

- [x] **4.4 Rewrite `POST /inbox/{building_id}/operator-message`**: `utility`
  only (else 403); `_contains_forbidden` → 422 before storing;
  `open_event_for_building` else 409; insert `operator` message; never trigger
  an agent reply; clear `needs_human`; `chat_operator_message` audit row;
  best-effort push to the manager.
  - _AC-4, AC-15, AC-21, AC-24, AC-25, AC-26_

- [x] **4.5 Rewrite `POST /inbox/{building_id}/close`**: `utility` only; set
  `threads.closed_at`; write `chat_thread_closed`; after close
  `open_event_for_building` returns None.
  - _AC-24, AC-25, AC-26_

## 5. Tests (reconciled onto the real schema; SMS tests deleted)

- [x] **5.1 Rework fixtures + delete SMS tests**: rewrite `tests/conftest.py`
  (drop `from notify.schema import ...`) and the chat fixtures in
  `tests/integration/test_chat.py` / `test_chat_extras.py` to seed `Utility`,
  `Zip`, `Building` (String(64) id), `User` manager + `role="utility"`
  operator, an approved `Event`, a `PlanBuilding` row for the current version,
  and a `CallHistory` row so parsed replies have a `call_id`. SQLite in-memory
  + `Base.metadata.create_all`. Monkeypatch `make_session` to a fake
  `ChatSession` returning a fixed sourced string. DELETE
  `tests/integration/test_webhook.py`, `tests/unit/test_notify.py`,
  `tests/properties/test_notify_access.py`, and the signature / 160-char cases
  in `tests/properties/test_templates_parser.py`.
  - _AC-27, AC-29, AC-31_

- [x] **5.2 Auto reply + structured decision tests**: manager message in `auto`
  yields an `agent` message (AC-6/7/9); `"YES"` writes one `Reply(kind="yes",
  call_id set)` **and** an agent message (AC-8); `"40 kW"` →
  `Reply(kind="offer", offer_kw=40)` (AC-8).
  - _AC-6, AC-7, AC-8, AC-9_

- [x] **5.3 Handoff + silence tests**: request-human flips to `human`, posts a
  system message, writes the audit row (AC-18); second call idempotent (AC-20);
  a manager message after the flip produces **no** agent message (AC-4).
  - _AC-4, AC-18, AC-20_

- [x] **5.4 Operator + banned-word + fallback tests**: operator free text stored
  as `operator`, no agent reply, `needs_human` cleared (AC-21); operator banned
  word → 422, nothing stored (AC-15); stub `make_session` returning a forbidden
  word → agent reply suppressed, fallback posted, `needs_human=True` (AC-16);
  stub `make_session` raising → fallback posted, manager message still
  persisted, `needs_human=True` (AC-10).
  - _AC-10, AC-15, AC-16, AC-21_

- [x] **5.5 Access + provenance tests**: other-building read 403 (AC-23);
  request-human by `utility` 403 (AC-23); operator-message by manager 403
  (AC-24); reply with no open event 409 (AC-25); a unit test asserting
  `agent.chat.CHAT_TOOLS` names only `building_info` + `estimate_savings`
  (AC-11).
  - _AC-11, AC-23, AC-24, AC-25_

- [x] **5.6 Push kept + SMS gone tests**: keep/adapt `test_chat_extras.py`'s
  push tests (subscribe stores a `PushSubscription`; `notify_user` no-ops
  without VAPID); add an `app.main` import/boot test; a repo-grep assertion
  that `send_sms`/`TwilioProvider`/`OutboundMessage`/`User.phone` and
  `app/routes/sms.py` are gone.
  - _AC-29, AC-30, AC-31_

## 6. Demo wiring and verification

- [x] **6.1 Confirm router registration** in `app/main.py` includes only the
  chat + push routers (SMS router removed) and that `make demo` / `db/seed.py`
  seeds at least one approved event with a `plan_buildings` row and a
  `CallHistory` row for a demo building, so a live thread exists to exercise the
  agent. Update `db/seed.py` only if that seed is missing.
  - _AC-1, AC-31_

- [x] **6.2 Run the gates**: `pytest` green; `scripts/presubmit.sh` (banned-word
  + constants-citation hooks) clean; confirm `app.main` boots and a repo grep
  finds no `send_sms` / `TwilioProvider` / `OutboundMessage` / `validate_signature`
  / `User.phone` reference and no phantom-model import.
  - _AC-15, AC-16, AC-27, AC-29, AC-30, AC-31_
