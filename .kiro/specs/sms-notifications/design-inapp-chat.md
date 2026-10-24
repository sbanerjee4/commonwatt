# Design note: in-app chat channel (addendum to the SMS spec)

**Status:** implemented on `sanchali-text-alert`.
**Why:** the Twilio free trial allows only predefined templates for every
message form, so custom-text SMS needs a paid upgrade. For the demo we add a
free in-app chat channel alongside SMS. SMS stays in the codebase and works
after upgrade — this changes the delivery channel, not the core.

## What is reused unchanged

- `notify.send_sms` — the one send choke point, with eligibility, access
  control, and audit. The in-app channel is just another `Provider`.
- `notify.validation.parse_reply_body` — a chat reply that parses to YES/NO/kW
  still writes a structured `replies` row, so backfill logic is unchanged.
- `notify.templates` — the `building_ask` wording and the forbidden-word check.
  Operator free text is checked with the same forbidden-word guard.
- The role boundary — a building session sees only its own building; an
  operator may act on any thread for the utility.

## What is new

- `db.models.Message` — one row per message in an (event, building) thread,
  with `sender_role` ∈ {system, building_manager, operator} and
  `sender_user_id`. The thread is the conversation; `replies` remains the
  structured answer feed.
- `notify.provider.InAppProvider` — posts the rendered body as a `system`
  message into the thread instead of texting. Needs no phone and no credential.
- Routes (`app/routes/chat.py`):
  - `GET /inbox/{building_id}` — the thread, polled by the SPA every few seconds.
  - `POST /inbox/{building_id}/reply` — building manager reply; always a
    message, plus a `replies` row when it parses.
  - `POST /inbox/{building_id}/operator-message` — operator FREE TEXT takeover
    (no template, no length cap, forbidden-word checked).

## Flow

1. Event approved → `send_sms(..., provider=InAppProvider)` posts a `system`
   `building_ask` into the (event, building) thread.
2. The building manager opens their page; the SPA polls `GET /inbox/{id}` and
   shows the thread. They reply YES / NO / a kW number, or free text.
3. A parsed reply also lands in `replies` for the backfill planner.
4. An operator can post free text into the same thread to take over.

## Notifications

Update nudges are a separate, free concern (browser push or email), not SMS —
SMS nudges hit the same trial/upgrade wall. Not yet built.

## Open / later

- SPA chat page (React) — belongs with the front-end spec work.
- Live updates use polling for the demo; server-sent events are a later option.
- Free update notification (browser push or email).
