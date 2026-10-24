# Implementation Plan: SMS Notifications with Twilio Integration

## Overview

This plan breaks down the SMS notifications feature into discrete implementation tasks, progressing from schema and provider abstraction through tests and wiring. All tasks use Python with FastAPI and SQLAlchemy, matching the existing CommonWatt stack. The implementation emphasizes incremental validation: schema + provider + core notify logic is complete and tested before wiring approval flows or inbound webhooks.

---

## Tasks

- [ ] 1. Create database schema migrations for SMS support
  - [x] 1.1 Add users.phone and users.sms_opted_out columns
    - Migrate users table: add nullable phone (E.164 format, unique), add sms_opted_out boolean (default False)
    - _Requirements: 18.1, 9.1_
  
  - [x] 1.2 Create outbound_messages table
    - Create outbound_messages table with user_id (FK), event_id (FK, nullable), template, body, provider, status, provider_sid, error, created_at, updated_at
    - _Requirements: 1.5, 12.2_
  
  - [x] 1.3 Add SMS action types to audit_log
    - Document audit_log actions: sms_sent, sms_skipped, sms_received, sms_opted_out, sms_opted_in, sms_webhook_invalid_signature, sms_unregistered_sender, sms_unrecognized_body
    - _Requirements: 1.8, 12.1, 13.1_

- [ ] 2. Implement provider abstraction layer
  - [x] 2.1 Create Provider abstract base class and SMSResult dataclass
    - Define SMSResult(success: bool, provider_sid: Optional[str], error: Optional[str])
    - Define Provider ABC with async send(phone: str, body: str) → SMSResult
    - _Requirements: 14.1, 14.2_
  
  - [x] 2.2 Implement TwilioProvider with Twilio SDK integration
    - Implement TwilioProvider.__init__ (account_sid, auth_token, from_number, demo_mode, demo_allowlist)
    - Implement TwilioProvider.send(): check demo_mode allowlist, call Twilio API, return SMSResult with provider_sid or error
    - Handle HTTP errors (network, auth, rate limit) gracefully
    - _Requirements: 10.2, 10.3, 10.4, 10.5_
  
  - [x]* 2.3 Write property test for demo mode allowlist enforcement
    - **Property 3: Demo Mode Allowlist Enforcement**
    - **Validates: Requirements 10.2, 10.3, 10.5**
  
  - [x] 2.4 Implement SimulatedProvider for testing and demo
    - Implement SimulatedProvider.__init__ (db_session)
    - Implement SimulatedProvider.send(): write to outbound_messages, return SMSResult with generated provider_sid
    - _Requirements: 11.1, 11.2, 11.3_
  
  - [ ]* 2.5 Write unit tests for Provider interface
    - Test TwilioProvider initialization with credentials
    - Test SimulatedProvider logging to DB
    - Test both providers return SMSResult in expected format
    - _Requirements: 14.1, 14.2_

- [ ] 3. Create template system with validation
  - [x] 3.1 Define SMS templates with placeholders
    - Create TEMPLATES dict: building_ask, operator_draft_ready, operator_backfill, operator_unreachable
    - Each template includes placeholders (e.g., {window}, {building_name}) for substitution
    - _Requirements: 5.1_
  
  - [x] 3.2 Implement template validation for forbidden language
    - Implement validate_templates() to check no template contains: "cut", "shut off", "curtail", "disconnect" (case-insensitive)
    - Call validate_templates() at module load (fail-safe)
    - _Requirements: 5.2, 5.3_
  
  - [x] 3.3 Implement template rendering with parameter substitution
    - Implement render_template(template_name: str, params: dict) → str
    - Validate all required placeholders present in params dict
    - Raise KeyError if required param missing
    - _Requirements: 19.1, 19.2, 19.3_
  
  - [x] 3.4 Implement SMS length validation (≤160 characters)
    - Check rendered body length after substitution
    - Raise ValueError if > 160 characters
    - _Requirements: 20.1, 20.2_
  
  - [x]* 3.5 Write property test for forbidden words exclusion
    - **Property 5: Forbidden Words Excluded from Rendered Templates**
    - **Validates: Requirements 5.2, 5.4, 5.5**
  
  - [ ]* 3.6 Write unit tests for template rendering and validation
    - Test successful rendering with valid params
    - Test KeyError on missing params
    - Test length validation
    - Test forbidden word rejection
    - _Requirements: 5.1, 5.2, 19.1, 19.2, 20.1_

- [ ] 4. Implement validation module (signatures and reply parsing)
  - [x] 4.1 Implement Twilio signature validation
    - Implement validate_signature(body: bytes, signature: str, auth_token: str, url: str) → bool
    - Compute HMAC-SHA1(auth_token, url + body_params_sorted_by_key)
    - Use constant-time comparison to prevent timing attacks
    - _Requirements: 6.2, 6.3_
  
  - [ ]* 4.2 Write property test for signature validation non-bypassable
    - **Property 6: Signature Validation Non-Bypassable**
    - **Validates: Requirements 6.2, 6.3**
  
  - [x] 4.3 Implement reply body parser
    - Implement parse_reply_body(body: str) → Union[str, int, None]
    - Handle YES/NO (case-insensitive, strip whitespace) → return "yes"/"no"
    - Handle STOP/START (case-insensitive) → return "STOP"/"START"
    - Handle positive integers or "N kw" pattern → return int N (N > 0)
    - Return None for unrecognized input
    - _Requirements: 7.4, 7.5, 7.6, 7.7, 7.9_
  
  - [x]* 4.4 Write property test for parser correctness and totality
    - **Property 4: Parser Totality and Correctness**
    - **Validates: Requirements 7.4, 7.5, 7.6, 7.7, 7.9**
  
  - [ ]* 4.5 Write unit tests for validation module
    - Test signature validation with valid and invalid signatures
    - Test reply parser with all input categories (YES, NO, kW, STOP, START, unrecognized)
    - Test case-insensitivity and whitespace tolerance
    - _Requirements: 6.2, 7.4, 7.5, 7.6, 7.7, 7.9_

- [ ] 5. Implement core send_sms function with access control
  - [x] 5.1 Implement send_sms core logic with pre-checks
    - Implement send_sms(user_id, template, params, event_id=None, db_session=None, provider=None) → dict
    - Query user by user_id; check phone (not null) and sms_opted_out flag
    - Check building_ask template requires event_id for building-event authorization
    - Query event to verify user.building_id in event.buildings
    - _Requirements: 16.1, 16.2, 16.3, 17.1, 17.2, 17.3_
  
  - [x]* 5.2 Write property test for access control (never send outside event)
    - **Property 1: Access Control — Never Send Building Ask for Unauthorized Building**
    - **Validates: Requirements 17.1, 17.2, 17.3**
  
  - [x] 5.3 Implement send_sms template rendering and provider call
    - Call render_template(template, params)
    - Create outbound_messages row (status=pending)
    - Call provider.send(phone, body)
    - Update outbound_messages row with provider_sid and final status
    - _Requirements: 1.5, 1.6, 1.7_
  
  - [x] 5.4 Implement send_sms skip logic with audit trail
    - Return {"sent": false, "reason_skipped": "..."} for no phone, opted out, event not found, building not in event
    - Write audit_log entry with action and reason
    - Never call provider.send() if skipped
    - _Requirements: 1.3, 1.4, 1.8_
  
  - [x]* 5.5 Write property test for opt-out enforcement
    - **Property 2: Opt-Out Respected — Never Send to Opted-Out User**
    - **Validates: Requirements 1.4, 2.4, 3.4, 4.4, 9.3**
  
  - [x] 5.6 Implement error handling for invalid inputs
    - Raise ValueError for unknown template
    - Raise ValueError for missing event_id when required
    - Raise ValueError for missing provider
    - _Requirements: 16.5, 16.6, 16.7_
  
  - [x]* 5.7 Write unit tests for send_sms function
    - Test successful send for eligible user
    - Test skip for no phone number
    - Test skip for opted-out user
    - Test skip for building not in event
    - Test error cases (missing params, unknown template)
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 1.7, 16.1, 16.2, 17.1_

- [ ] 6. Implement inbound webhook (POST /sms/inbound)
  - [x] 6.1 Create FastAPI route for webhook POST /sms/inbound
    - Create route handler: async def inbound_webhook(request: Request, db_session)
    - Extract From, Body, MessageSid, X-Twilio-Signature from request
    - Validate signature; reject (403) if invalid
    - _Requirements: 6.1, 6.2, 6.3_
  
  - [x] 6.2 Implement inbound phone lookup and registration check
    - Normalize From field to E.164
    - Query user by phone; if not found, send "not registered" SMS and log audit_log
    - _Requirements: 7.2, 7.3_
  
  - [x] 6.3 Implement reply parsing and kW counter extraction
    - Call parse_reply_body(Body)
    - Extract kind (yes/no) or kW counter value
    - _Requirements: 7.4, 7.5, 7.6, 7.7, 7.9_
  
  - [x] 6.4 Implement STOP/START opt-out/opt-in handling
    - If STOP: set user.sms_opted_out = true, send confirmation SMS, write audit_log
    - If START: set user.sms_opted_out = false, send confirmation SMS, write audit_log
    - Update and audit in single transaction
    - _Requirements: 9.1, 9.2, 9.4, 9.5_
  
  - [x] 6.5 Implement replies persistence for YES/NO/kW responses
    - Query user.building_id
    - Query events where building_id in event.buildings, status=approved, closed_at IS NULL
    - If event found: write replies row (building_id, event_id, kind, kw), write audit_log, send "Got it" SMS
    - If no event found: send "No active event" SMS and log audit_log
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_
  
  - [x] 6.6 Implement unrecognized body handling
    - If Body doesn't match any recognized pattern: send "Didn't catch that..." SMS and log audit_log
    - _Requirements: 7.9_
  
  - [x] 6.7 Implement TwiML response generation
    - Generate valid TwiML XML responses for all reply types
    - Return HTTP 200 with TwiML body (never raise; Twilio retries on non-2xx)
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7, 15.8_
  
  - [x]* 6.8 Write integration tests for inbound webhook
    - Test valid signature, registered user, YES reply → writes replies row
    - Test invalid signature → 403 rejection
    - Test unregistered phone → "not registered" SMS
    - Test STOP reply → user.sms_opted_out set to true
    - Test START reply → user.sms_opted_out set to false
    - Test no active event → "no active event" SMS
    - Test unrecognized body → "Didn't catch that" SMS
    - _Requirements: 6.2, 7.2, 7.3, 8.1, 8.2, 8.5, 9.1, 9.2_

- [ ] 7. Create MCP tool wrapper for send_sms with authorization
  - [ ] 7.1 Implement notify MCP tool in commonwatt_mcp module
    - Wrap send_sms function in MCP tool
    - Tool accepts: user_id, template, params, event_id
    - _Requirements: 16.1, 16.2_
  
  - [ ] 7.2 Implement access control in MCP tool
    - For building_ask template: enforce that event_id contains user.building_id
    - For operator alerts: allow all operators for the utility
    - Return permission error if unauthorized
    - _Requirements: 17.1, 17.2, 17.3_
  
  - [ ]* 7.3 Write integration tests for MCP tool authorization
    - Test building_ask sent only to buildings in event
    - Test permission denied for building not in event
    - Test operator alerts sent to all operators (no per-building check)
    - _Requirements: 17.1, 17.2, 17.3_

- [ ] 8. Wire event approval to send building asks
  - [ ] 8.1 Integrate send_sms into event approval route
    - Modify app/routes/events.py POST /utility/events/{event_id}/approve
    - After event.status = "approved", query event.buildings
    - For each building: call send_sms(building_manager_user_id, "building_ask", params, event_id) via MCP tool
    - _Requirements: 1.1, 1.2_
  
  - [ ] 8.2 Collect parameters for building_ask template
    - Extract event.window_label, event.reason_text, event.estimated_payment
    - Extract building.name, building.kw_requested, building.kw_enrolled
    - Pass as params dict to send_sms
    - _Requirements: 1.1, 1.2_
  
  - [ ] 8.3 Handle SMS sending errors gracefully
    - Log errors from send_sms; do not block event approval
    - Operator can retry send via API or dashboard (future task)
    - _Requirements: 1.6, 1.7_
  
  - [ ]* 8.4 Write integration tests for approval workflow
    - Test: approve event → send_sms called for each building → outbound_messages rows created
    - Test: approve event with opted-out building manager → skipped with audit log
    - Test: approve event → SMS body contains correct window, building name, kW, payment
    - _Requirements: 1.1, 1.2, 1.5, 1.6, 1.8_

- [ ] 9. Wire agent draft/backfill/unreachable alerts to operators
  - [ ] 9.1 Integrate send_sms into agent draft event production
    - Modify agent (planner, critic) to call send_sms for all operators when draft event completes
    - Query operators (role=utility) for the utility_id
    - Call send_sms(operator.id, "operator_draft_ready", params) via MCP tool
    - _Requirements: 2.1, 2.2, 2.3_
  
  - [ ] 9.2 Collect parameters for operator_draft_ready template
    - Extract event.window_label, event.target_mw, building_count, ej_share
    - Pass as params dict to send_sms
    - _Requirements: 2.2, 2.3_
  
  - [ ] 9.3 Integrate send_sms into backfill alert logic
    - Identify when backfill is needed (declines reduce capacity below target)
    - Call send_sms for all operators with "operator_backfill" template
    - Include decline_count and shortfall_mw in params
    - _Requirements: 3.1, 3.2, 3.3_
  
  - [ ] 9.4 Integrate send_sms into unreachable alert logic
    - Identify when target is unreachable under EJ cap
    - Call send_sms for all operators with "operator_unreachable" template
    - Include cap percentage and achievable_mw in params
    - _Requirements: 4.1, 4.2, 4.3_
  
  - [ ]* 9.5 Write integration tests for agent alert workflows
    - Test: draft event produced → send_sms called for all operators → outbound_messages rows created
    - Test: backfill detected → send_sms called for all operators with backfill template
    - Test: unreachable detected → send_sms called for all operators with unreachable template
    - Test: operator has no phone → skipped with audit log
    - _Requirements: 2.1, 2.2, 3.1, 3.2, 4.1, 4.2_

- [ ] 10. Implement comprehensive property-based tests
  - [ ] 10.1 Write remaining property tests for completeness
    - **Property 7: Audit Trail Completeness** — every SMS action has audit_log entry
    - **Property 8: Outbound Messages Persistence** — provider_sid written atomically
    - **Property 9: Replies Persist Only for Registered Users with Active Events** — guard conditions on replies write
    - **Property 10: Template Round-Trip** — render and validate properties hold
    - **Property 11: Opt-Out / Opt-In Atomic Update** — transaction atomicity
    - **Property 12: No SMS Send Without Valid Provider** — provider resolution correctness
    - _Requirements: 1.8, 8.2, 8.3, 8.5, 9.5, 12.1_
  
  - [ ]* 10.2 Run Hypothesis property test suite
    - Execute pytest tests/properties/ with Hypothesis
    - Verify all universal properties hold across generated examples
    - Capture property test results for verification
    - _Requirements: All properties_

- [ ] 11. Implement unit tests for all modules
  - [ ] 11.1 Write unit tests for notify module edge cases
    - Test send_sms with missing optional event_id for operator alerts
    - Test send_sms with null provider resolution
    - Test send_sms with invalid phone format (not E.164)
    - Test all skip reasons: no_phone, opted_out, event_not_found, building_not_in_event, invalid_phone_format
    - _Requirements: 16.1, 16.2, 16.5, 16.6, 16.7, 18.2, 18.3_
  
  - [ ] 11.2 Write unit tests for provider error scenarios
    - Test TwilioProvider with HTTP errors (500, 401, 429, timeout)
    - Test SimulatedProvider with DB write failures (transaction rollback)
    - Test provider error handling and SMSResult error field population
    - _Requirements: 1.7_
  
  - [ ] 11.3 Write unit tests for audit logging
    - Test audit_log entry creation for send_sms success
    - Test audit_log entry creation for all skip reasons
    - Test audit_log entry creation for webhook signature validation failure
    - Test audit_log entry creation for opt-out/opt-in
    - Test audit_log contains user_id, event_id (if applicable), action, reason, timestamp
    - _Requirements: 1.8, 12.1, 12.2, 12.3, 12.4, 12.5, 13.1, 13.2, 13.3, 13.4, 13.5_
  
  - [ ]* 11.4 Run pytest unit test suite
    - Execute pytest tests/unit/ with coverage reporting
    - Target ≥95% coverage for notify/, validation modules
    - Capture unit test results
    - _Requirements: All unit test requirements_

- [ ] 12. Run full test suite and validate correctness
  - [ ] 12.1 Configure test environment
    - Set SMS_PROVIDER=simulated
    - Set SMS_DEMO_MODE=true
    - Create test fixtures: users (with/without phone, opted out/in), events, buildings, operators
    - _Requirements: 11.1_
  
  - [ ] 12.2 Checkpoint - Run all tests (unit, properties, integration)
    - Execute make test
    - Verify SMS_PROVIDER=simulated (no Twilio calls)
    - Ensure all tests pass: property tests, unit tests, integration tests
    - Report coverage and test results
    - _Requirements: All_

- [ ] 13. Update README and documentation
  - [x] 13.1 Add SMS configuration section to README
    - Document environment variables: SMS_PROVIDER, SMS_DEMO_MODE, SMS_DEMO_ALLOWLIST, TWILIO_*, SMS_WEBHOOK_URL
    - Document template types: building_ask, operator_draft_ready, operator_backfill, operator_unreachable
    - Document safety rules: forbidden language exclusion, opt-out mechanism
    - _Requirements: Overview_
  
  - [x] 13.2 Document API and MCP tool usage
    - Document send_sms(user_id, template, params, event_id) function interface
    - Document inbound webhook endpoint (POST /sms/inbound, expected headers/body, TwiML response)
    - Document error scenarios and audit trail
    - _Requirements: 16.1, 16.2_

---

## Notes

- **Optional test tasks** marked with `*` can be skipped for faster MVP, but are recommended for production quality.
- **Property-based tests** validate universal properties across randomly generated examples; critical for correctness.
- **All implementation uses Python** with FastAPI, SQLAlchemy ORM, Twilio SDK, and Hypothesis (for PBT).
- **Schema first:** tasks 1–5 establish the data model and core notify logic; all standalone (no wiring).
- **Provider abstraction:** task 2 enables easy testing with SimulatedProvider; TwilioProvider hidden behind interface.
- **Audit trail:** all actions (send, skip, receive, opt-out) logged for compliance.
- **Demo mode:** task 2.2 implements allowlist; safe for development without Twilio credentials.
- **Tests before wiring:** tasks 1–5 complete with ≥95% unit + property coverage before wiring approval (tasks 8–9).
- **Checkpoint at task 12.2:** verify make test passes with SMS_PROVIDER=simulated before proceeding to production Twilio wiring.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "3.1"] },
    { "id": 3, "tasks": ["2.3", "2.4", "2.5", "3.2", "3.3", "3.4", "4.1", "4.3"] },
    { "id": 4, "tasks": ["3.5", "3.6", "4.2", "4.4", "4.5"] },
    { "id": 5, "tasks": ["5.1", "5.3", "5.4", "5.6"] },
    { "id": 6, "tasks": ["5.2", "5.5", "5.7"] },
    { "id": 7, "tasks": ["6.1", "6.2", "6.3", "6.4", "6.5", "6.6", "6.7", "7.1", "7.2"] },
    { "id": 8, "tasks": ["6.8", "7.3"] },
    { "id": 9, "tasks": ["8.1", "8.2", "8.3", "9.1", "9.2", "9.3", "9.4"] },
    { "id": 10, "tasks": ["8.4", "9.5"] },
    { "id": 11, "tasks": ["10.1", "10.2", "11.1", "11.2", "11.3", "11.4"] },
    { "id": 12, "tasks": ["12.1", "12.2"] },
    { "id": 13, "tasks": ["13.1", "13.2"] }
  ]
}
```

---

## Workflow Completion

**This design-first workflow is complete.** You now have:

1. ✓ **Requirements document** (requirements.md) — 20 requirements + 12 correctness properties
2. ✓ **Design document** (design.md) — technical approach, components, interfaces, examples
3. ✓ **Implementation task list** (this file) — 13 epics, 60+ discrete tasks with dependencies

**Next steps:**

- Open `/Users/sanchalibanerjee/Documents/commonwatt/.kiro/specs/sms-notifications/tasks.md`
- Click "Start task" next to task items to begin implementation
- Execute tasks in dependency wave order (0 → 1 → 2, etc.)
- After completing tasks 1–5 and checkpoint 12.2 (make test passes), the core schema and provider layer will be production-ready
- Tasks 6–13 wire the notification flows and polish the feature

The feature is scoped to run on the **sanchali-text-alert** branch and is ready for incremental execution.
