# TODO project name

## Track

TODO

## One-line description

TODO

## Setup

TODO

Run `make setup`.

## Run the demo

TODO

Run `make demo`.

## Demo URL

TODO

## Video

TODO

## Team and Representative

TODO

---

## SMS Notifications (Twilio)

Outbound asks to building managers and alerts to operators, plus an inbound
reply webhook. Two providers behind one interface: **simulated** (default — no
network, used by tests and `make demo`) and **twilio** (real send).

### Setup

```bash
make setup     # venv + deps
make test      # runs with the simulated provider; no SMS sent
```

### Configuration

Copy `.env.example` to `.env` (git-ignored) and fill it in. Never commit `.env`.

| Variable | Meaning |
|---|---|
| `SMS_PROVIDER` | `simulated` (default) or `twilio` |
| `SMS_DEMO_MODE` | `true` → real sends go ONLY to `SMS_DEMO_ALLOWLIST` |
| `SMS_DEMO_ALLOWLIST` | Comma-separated E.164 numbers (e.g. `+15551234567`) |
| `TWILIO_ACCOUNT_SID` | Twilio Account SID (`AC...`) |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token |
| `TWILIO_FROM_NUMBER` | Your Twilio number, E.164 |
| `SMS_WEBHOOK_URL` | Public URL of `/sms/inbound`, for signature validation |

Keep `SMS_DEMO_MODE=true` until you trust the flow: real Twilio sends, but a
bug cannot text anyone outside the allowlist.

### Templates

Four plain-text templates (`notify/templates.py`), each ≤160 chars and checked
at import for forbidden language:

- `building_ask` — asks a building manager to reduce load for an event
- `operator_draft_ready` — a draft event is ready to approve
- `operator_backfill` — declines dropped capacity, backfill proposed
- `operator_unreachable` — target not reachable under the EJ cap

**Safety:** no template or rendered body may contain `cut`, `shut off`,
`curtail`, or `disconnect`. Enforced by `validate_templates()` and re-checked
after substitution; the import fails fast if violated.

### Sending

`notify.send_sms(user_id, template, params, event_id=None)` is the one choke
point. It skips (with an audit row, never calling the provider) when the user
has no phone, has opted out, or — for `building_ask` — is not in the event.

### Inbound webhook

`POST /sms/inbound` (`app/routes/sms.py`) validates the `X-Twilio-Signature`
(rejects with 403 on mismatch), looks up the sender by phone, then:

- `STOP` / `START` → toggles `sms_opted_out`
- `YES` / `NO` / a number of kW → records a reply against the building's open
  approved event
- unknown sender / unknown body / no active event → a safe reply, always 200

Every branch writes an `audit_log` row. Run the app with
`uvicorn app.main:app`.

