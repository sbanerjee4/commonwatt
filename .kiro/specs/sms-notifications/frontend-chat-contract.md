# Front-end API contract: event chat + notifications

For whoever builds the chat page on the front-end branch. This is the backend
contract on `sanchali-text-alert`; build against it without reading the Python.
All endpoints are JSON. The BFF sets identity headers from the session; in this
branch they are passed directly:

- `X-User-Id`: the signed-in user's id (integer).
- `X-Role`: `building_manager` or `operator`.

Access rule: a `building_manager` may only read/post to their OWN building; an
`operator` may act on any building's thread for the utility.

---

## Thread

### GET `/inbox/{building_id}`
The whole thread for a building, oldest first. Poll this every few seconds.

**200**
```json
{
  "building_id": 7,
  "messages": [
    {
      "id": 1,
      "event_id": 3,
      "sender_role": "system",
      "sender_user_id": null,
      "body": "CommonWatt: event Tue 2-6PM. Elm St: reduce 20 of 100 kW...",
      "created_at": "2026-10-24T19:00:00+00:00"
    },
    {
      "id": 2,
      "event_id": 3,
      "sender_role": "building_manager",
      "sender_user_id": 42,
      "body": "YES",
      "created_at": "2026-10-24T19:01:10+00:00"
    }
  ]
}
```
`sender_role` ∈ `system` | `building_manager` | `operator` — use it to align
bubbles left/right and label the sender. **403** if the caller is not allowed
this building.

### GET `/inbox/{building_id}/unread?since={message_id}`
Count of messages with `id` greater than `since`. Track the highest `id` you
have rendered, pass it as `since`, show the result as the badge.

**200** `{ "building_id": 7, "since": 2, "unread": 1 }`

---

## Posting

### POST `/inbox/{building_id}/reply`  (building manager)
Body: `{ "body": "YES" }` — or `NO`, a number of kW (`"40"` / `"40 kW"`), or
free text. Always appended to the thread; a parsed YES/NO/kW ALSO records a
structured reply for the planner.

**200**
```json
{ "ok": true, "parsed_reply": { "kind": "yes", "kw": null } }
```
`parsed_reply` is `null` for free text, `{"kind":"counter","kw":40}` for a
number. **409** if there is no open event for the building. **400** empty body.

### POST `/inbox/{building_id}/operator-message`  (operator)
Free text, no template, no length cap. Body: `{ "body": "Hi, operator here…" }`.

**200** `{ "ok": true }`. **403** if not an operator. **422** if the text
contains a forbidden word (`cut`, `shut off`, `curtail`, `disconnect`).
Posting also fires a browser push to the building manager when they have one.

### POST `/inbox/{building_id}/close`  (operator)
Closes the building's open event thread; replies after this get **409**.

**200** `{ "ok": true, "event_id": 3, "closed": true }`.

---

## Browser push (free notification, optional)

### GET `/push/public-key`
**200** `{ "public_key": "<VAPID public key>" }`. Empty string means push is
not configured — hide the "enable notifications" button.

### POST `/push/subscribe`
Send the browser's `PushSubscription` JSON (`{endpoint, keys:{p256dh, auth}}`)
with header `X-User-Id`. **200** `{ "ok": true }`. **400** invalid,
**401** missing `X-User-Id`.

Service worker + the subscribe handshake are front-end work; the backend only
stores the subscription and sends on an operator message.

---

## Polling model
Poll `GET /inbox/{id}` (and optionally `/unread`) every 3–5s while the thread
is open. No websockets/SSE for the demo. Render by appending any message whose
`id` is higher than the last one shown.
