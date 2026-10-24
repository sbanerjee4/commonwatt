# Requirements Document

## Introduction

This document specifies the requirements for adding SMS as a delivery channel for operator alerts and building manager requests in the CommonWatt demand-response platform. The feature enables:

1. **Building managers** to receive event participation requests via SMS and reply with YES/NO/kW
2. **Operators** to receive alerts when drafts are ready, backfill is needed, or targets are unreachable
3. **Safe, audited communication** with provider abstraction supporting Twilio (live) and simulated (demo/test) providers
4. **Safety enforcement** per safety.md: no "cut", "shut off", "curtail", or "disconnect" language; demo mode restricts outbound to an allowlist

All outbound and inbound SMS interactions are persisted to the database for auditability and backfill logic consumption.

---

## Glossary

- **SMS**: Short Message Service; plain-text message ≤160 characters
- **E.164 Format**: International phone number format (e.g., +12025551234)
- **Provider**: Abstraction for SMS delivery backend (TwilioProvider, SimulatedProvider)
- **TwilioProvider**: Live SMS delivery via Twilio API
- **SimulatedProvider**: Demo/test provider that logs to database instead of calling Twilio
- **Demo Mode**: Configuration that restricts TwilioProvider sending to allowlisted numbers
- **HMAC-SHA1**: Cryptographic signature algorithm used by Twilio for webhook validation
- **X-Twilio-Signature**: HTTP header containing HMAC-SHA1 signature for webhook authentication
- **Template**: Parameterized SMS message (building_ask, operator_draft_ready, operator_backfill, operator_unreachable)
- **building_ask**: SMS template sent to building managers when an event is approved, requesting participation
- **operator_draft_ready**: SMS template sent to operators when a draft event is ready for approval
- **operator_backfill**: SMS template sent to operators when backfill is needed due to declines
- **operator_unreachable**: SMS template sent to operators when target is unreachable under EJ cap
- **outbound_messages**: Database table storing sent SMS records (status, provider_sid, body, audit trail)
- **replies**: Database table storing inbound SMS responses (kind, kw, event_id, building_id)
- **audit_log**: Database table recording all SMS actions (send, skip, receive, opt-out, opt-in)
- **sms_opted_out**: Boolean flag indicating user has replied STOP and disabled SMS delivery
- **Inbound Webhook**: HTTP POST endpoint that receives Twilio-forwarded SMS replies from building managers
- **TwiML**: Twilio Markup Language; XML format for Twilio responses (e.g., SMS reply)

---

## Requirements

### Requirement 1: Building Manager Receives Event Participation Request

**User Story:** As a building manager, I want to receive SMS notifications when my building is called in a demand-response event, so that I can promptly decide whether to participate and what capacity I can offer.

#### Acceptance Criteria

1. WHEN an operator approves a demand-response event that includes a building, THE System SHALL send an SMS to the building manager with the event window, building name, requested kW, enrolled kW, reason for selection, and estimated payment
2. WHEN the SMS body is generated from the building_ask template, THE System SHALL substitute placeholders with values from the event and building (window, building_name, kw_requested, kw_enrolled, reason, payment)
3. WHEN a building manager's user record has no phone number, THE System SHALL NOT send SMS and SHALL log the skip reason in the audit trail
4. WHEN a building manager has set sms_opted_out=true, THE System SHALL NOT send SMS and SHALL log the skip reason in the audit trail
5. WHEN SMS is sent, THE System SHALL create an outbound_messages row with template name, rendered body, provider type, and initial status=pending
6. WHEN the SMS is successfully delivered via Twilio, THE System SHALL update the outbound_messages row with provider_sid and status=sent
7. WHEN the SMS delivery fails (network error, auth error, rate limit), THE System SHALL update the outbound_messages row with error details and status=failed
8. WHEN an SMS is sent or skipped, THE System SHALL write an audit_log entry with user_id, event_id (if applicable), action (sms_sent, sms_skipped, sms_failed), and reason

---

### Requirement 2: Operator Receives Draft-Ready Alert

**User Story:** As a utility operator, I want to receive an SMS alert when the planner has produced a draft event ready for approval, so that I can quickly review and approve it via the dashboard.

#### Acceptance Criteria

1. WHEN the agent produces a draft demand-response event, THE System SHALL identify all users with role=utility for the associated utility_id
2. WHEN draft production completes, THE System SHALL send an SMS to each operator using the operator_draft_ready template, with substitutions for window, target_mw, building_count, and ej_share
3. WHEN the SMS body is generated from the operator_draft_ready template, THE System SHALL render the template with event window, target MW, count of buildings in the event, and EJ percentage share
4. WHEN an operator has no phone or has opted out, THE System SHALL skip sending and log the skip reason in the audit trail
5. WHEN SMS is sent to operators, THE System SHALL update outbound_messages rows with provider_sid and status=sent (or failed if Twilio returns error)
6. WHEN an SMS send or skip occurs for an operator alert, THE System SHALL write an audit_log entry with user_id, action, and reason

---

### Requirement 3: Operator Receives Backfill Alert

**User Story:** As a utility operator, I want to receive an SMS alert when building declines have created a capacity shortfall and backfill is proposed, so that I can prioritize approval.

#### Acceptance Criteria

1. WHEN the backfill logic detects that declines have reduced available capacity below the target, THE System SHALL identify all operators for the utility
2. WHEN backfill is proposed, THE System SHALL send an SMS to each operator using the operator_backfill template, with substitutions for decline count and shortfall MW
3. WHEN the SMS body is generated from the operator_backfill template, THE System SHALL render the template with the number of declines and the shortfall in MW
4. WHEN an operator has no phone or has opted out, THE System SHALL skip sending and log the skip reason
5. WHEN SMS is sent or skipped, THE System SHALL create or update outbound_messages and audit_log entries with provider_sid and status

---

### Requirement 4: Operator Receives Unreachable Alert

**User Story:** As a utility operator, I want to receive an SMS alert when the event target is unreachable under the EJ cap constraint, so that I can decide to raise the cap or accept a lower target.

#### Acceptance Criteria

1. WHEN the dispatch logic determines the target is unreachable under the configured EJ cap, THE System SHALL identify all operators for the utility
2. WHEN unreachable detection occurs, THE System SHALL send an SMS to each operator using the operator_unreachable template, with substitutions for the EJ cap percentage and achievable MW
3. WHEN the SMS body is generated from the operator_unreachable template, THE System SHALL render the template with the current EJ cap and the maximum achievable MW
4. WHEN an operator has no phone or has opted out, THE System SHALL skip sending and log the skip reason
5. WHEN SMS is sent or skipped, THE System SHALL create or update outbound_messages and audit_log entries with provider_sid and status

---

### Requirement 5: SMS Templates Exclude Forbidden Language

**User Story:** As a CommonWatt administrator, I want to ensure all SMS messages comply with safety.md guidelines, so that participant messaging is always compliant with demand-response best practices.

#### Acceptance Criteria

1. THE System SHALL maintain four SMS templates: building_ask, operator_draft_ready, operator_backfill, operator_unreachable
2. WHEN any template is loaded into memory, THE System SHALL validate that it contains none of the forbidden substrings: "cut", "shut off", "curtail", "disconnect"
3. IF a template contains forbidden language, THE System SHALL raise an error at module initialization (fail-safe)
4. WHEN a template is rendered with substituted parameters, THE System SHALL NOT inject forbidden language via parameters (templates only use controlled placeholders)
5. WHEN building_ask is rendered, it SHALL use "asked to reduce" or "event participation" language instead of forbidden terms

---

### Requirement 6: Inbound SMS Reply Signature Validation

**User Story:** As a CommonWatt security administrator, I want all inbound SMS webhooks to be validated against Twilio signatures, so that I can trust only authentic replies from Twilio.

#### Acceptance Criteria

1. WHEN the inbound SMS webhook POST /sms/inbound is received, THE System SHALL extract the X-Twilio-Signature header
2. WHEN X-Twilio-Signature is present, THE System SHALL validate it using HMAC-SHA1(auth_token, url + body_params_sorted)
3. IF the signature does not match, THE System SHALL reject the webhook (HTTP 403) and log the rejection to audit_log
4. IF the signature is valid, THE System SHALL process the webhook and parse the SMS reply
5. IF the signature validation is invalid, THE System SHALL NOT modify any database state (replies, users, audit_log)

---

### Requirement 7: Building Manager Replies to Event Request via SMS

**User Story:** As a building manager, I want to reply to an event participation request via SMS with YES, NO, or a kW counter-offer, so that the backfill logic can process my response.

#### Acceptance Criteria

1. WHEN a building manager sends an SMS reply to the Twilio inbound number, THE System SHALL receive it via POST /sms/inbound with From, Body, MessageSid, and X-Twilio-Signature
2. WHEN the inbound webhook validates the signature successfully, THE System SHALL parse the From field (E.164 phone number) and match it to a user in the users table
3. IF the phone number is not registered, THE System SHALL send an SMS reply "This number isn't registered with CommonWatt." and log the action
4. WHEN the From number matches a registered user, THE System SHALL parse the Body field to extract the reply kind (YES, NO, or kW counter)
5. WHEN Body is "YES" (case-insensitive), THE System SHALL interpret it as acceptance and write replies row with kind=yes
6. WHEN Body is "NO" (case-insensitive), THE System SHALL interpret it as decline and write replies row with kind=no
7. WHEN Body is a positive integer or "N kW" (case-insensitive), THE System SHALL interpret it as a kW counter-offer and write replies row with kw=N
8. WHEN Body is "STOP" or "START", THE System SHALL handle opt-out/opt-in (see Requirement 9)
9. WHEN Body doesn't match YES, NO, integer, or kW pattern, THE System SHALL send an SMS "Didn't catch that. Reply YES, NO, or a number of kW." and log the unrecognized reply

---

### Requirement 8: Building Manager Reply Persisted to Database

**User Story:** As a backfill planner, I want building manager replies to be written to the replies table, so that the backfill logic can consume them.

#### Acceptance Criteria

1. WHEN a valid YES/NO/kW reply is received and parsed, THE System SHALL query the user's associated building_id from the users table
2. WHEN the user's building_id is known, THE System SHALL query the events table for the most recent event with status=approved and closed_at IS NULL that includes the building
3. IF an open approved event is found, THE System SHALL write a replies row with: building_id, event_id, kind (yes/no), kw (if counter), timestamp, and source=sms
4. WHEN the replies row is written, THE System SHALL write an audit_log entry with action=sms_received, user_id, event_id, and reply kind
5. IF no open approved event exists for the building, THE System SHALL send an SMS "No active event for your building." and log the action
6. WHEN the replies row is committed, THE System SHALL send an SMS confirmation "Got it. Your response has been recorded."

---

### Requirement 9: Building Manager SMS Opt-Out / Opt-In

**User Story:** As a building manager, I want to control whether I receive SMS notifications by replying STOP or START, so that I can manage my communication preferences.

#### Acceptance Criteria

1. WHEN a building manager sends "STOP" via SMS reply, THE System SHALL set user.sms_opted_out=true and send an SMS confirmation "You've opted out of SMS updates. Reply START to re-enable."
2. WHEN a building manager sends "START" via SMS reply, THE System SHALL set user.sms_opted_out=false and send an SMS confirmation "You're opted in to SMS updates."
3. WHEN a user has sms_opted_out=true, THE System SHALL NOT send any SMS messages (building_ask, alerts) to that user, regardless of reason
4. WHEN a user opts out or in, THE System SHALL write an audit_log entry with action=sms_opted_out or sms_opted_in and user_id
5. WHEN user.sms_opted_out is set (either to true or false), THE System SHALL commit the update atomically in the same transaction

---

### Requirement 10: Demo Mode Allowlist Enforcement

**User Story:** As a developer testing with Twilio credentials in a demo environment, I want SMS sends to be restricted to allowlisted phone numbers, so that I don't accidentally contact real users during development.

#### Acceptance Criteria

1. WHEN the application is started with SMS_DEMO_MODE=true, THE TwilioProvider SHALL check the SMS_DEMO_ALLOWLIST configuration
2. WHEN TwilioProvider is called to send SMS and demo_mode=true, THE System SHALL verify the recipient phone number is in the allowlist before calling Twilio API
3. IF the phone number is not in the allowlist, THE System SHALL return SMSResult(success=false, error="Demo mode: number not in allowlist") and NOT call Twilio
4. IF the phone number is in the allowlist, THE System SHALL proceed with Twilio API call as normal
5. WHEN an SMS send is blocked by demo mode, THE System SHALL log to audit_log with action=sms_skipped and reason=demo_mode_allowlist

---

### Requirement 11: SimulatedProvider for Testing

**User Story:** As a developer, I want to test SMS workflows without calling Twilio in unit and integration tests, so that tests run quickly and deterministically.

#### Acceptance Criteria

1. WHEN SimulatedProvider is configured, THE System SHALL accept send(phone, body) calls without calling Twilio API
2. WHEN SimulatedProvider.send() is called, THE System SHALL write to the outbound_messages table with provider=simulated and a generated provider_sid
3. WHEN SimulatedProvider.send() is called, THE System SHALL return SMSResult(success=true, provider_sid=generated_id, error=None)
4. WHEN SimulatedProvider is used in demo mode, THE System SHALL optionally schedule scripted reply messages to be returned via the inbound webhook in subsequent tests
5. WHEN SimulatedProvider logs an outbound message, THE System SHALL record it identically to TwilioProvider (same outbound_messages schema, same audit_log format)

---

### Requirement 12: Outbound Messages Audit Trail

**User Story:** As a compliance officer, I want a complete audit trail of all outbound SMS sends and refusals, so that I can investigate delivery issues and verify operator compliance.

#### Acceptance Criteria

1. WHEN send_sms() completes (sent, failed, or skipped), THE System SHALL write one audit_log row with: user_id, event_id (if applicable), action (sms_sent, sms_failed, sms_skipped), timestamp, and reason (if skipped)
2. WHEN a message is sent via TwilioProvider, THE System SHALL record in outbound_messages: user_id, event_id, template name, rendered body, provider=twilio, status=sent, provider_sid, timestamps
3. WHEN a message send fails, THE System SHALL record in outbound_messages: user_id, event_id, template name, rendered body, provider=twilio, status=failed, error details, timestamps
4. WHEN a message is skipped (no phone, opted out, event not found), THE System SHALL record in outbound_messages: user_id, event_id (if applicable), template name, reason, status=skipped, timestamps
5. WHEN querying the audit trail, a compliance officer SHALL be able to retrieve all SMS actions for a given user, event, or date range

---

### Requirement 13: Inbound Webhook Audit Trail

**User Story:** As a compliance officer, I want a complete audit trail of all inbound SMS replies, so that I can verify message authenticity and investigate disputes.

#### Acceptance Criteria

1. WHEN an inbound SMS webhook is received at POST /sms/inbound, THE System SHALL write an audit_log entry after processing with: action (sms_received, sms_unregistered_sender, sms_unrecognized_body, sms_webhook_invalid_signature), user_id (if registered), timestamp, and details (From number, Body, reason if rejected)
2. WHEN a reply is successfully parsed and written to the replies table, THE System SHALL record the action=sms_received, user_id, event_id, reply kind, and kw (if counter)
3. WHEN a webhook signature fails validation, THE System SHALL record action=sms_webhook_invalid_signature without modifying state
4. WHEN an unregistered phone sends a reply, THE System SHALL record action=sms_unregistered_sender with From number
5. WHEN a reply body cannot be parsed, THE System SHALL record action=sms_unrecognized_body with the raw Body text

---

### Requirement 14: Provider Interface Abstraction

**User Story:** As a developer, I want the SMS provider to be abstracted behind an interface, so that I can swap implementations (Twilio, SimulatedProvider, future providers) without changing caller code.

#### Acceptance Criteria

1. THE System SHALL define a Provider abstract base class with method: send(phone: str, body: str) → SMSResult
2. WHEN send_sms() calls the provider, THE System SHALL use the abstract interface, not provider-specific logic
3. WHEN a provider is resolved (from config or dependency injection), THE System SHALL instantiate either TwilioProvider or SimulatedProvider
4. WHEN TwilioProvider is instantiated, THE System SHALL accept account_sid, auth_token, from_number, demo_mode, and demo_allowlist parameters
5. WHEN SimulatedProvider is instantiated, THE System SHALL accept a db_session parameter for writing to outbound_messages

---

### Requirement 15: SMS Response Format (TwiML)

**User Story:** As a system operator, I want all inbound webhook responses to be properly formatted TwiML, so that Twilio can relay SMS replies back to building managers.

#### Acceptance Criteria

1. WHEN the inbound webhook (POST /sms/inbound) processes a request, THE System SHALL return an HTTP response with valid TwiML XML
2. WHEN a reply is successfully parsed and persisted, THE System SHALL return TwiML with an SMS body: "Got it. Your response has been recorded."
3. WHEN a reply is unrecognized, THE System SHALL return TwiML with an SMS body: "Didn't catch that. Reply YES, NO, or a number of kW."
4. WHEN a user is not registered, THE System SHALL return TwiML with an SMS body: "This number isn't registered with CommonWatt."
5. WHEN a user has no active event, THE System SHALL return TwiML with an SMS body: "No active event for your building."
6. WHEN a user opts out (STOP), THE System SHALL return TwiML with an SMS body: "You've opted out of SMS updates. Reply START to re-enable."
7. WHEN a user opts in (START), THE System SHALL return TwiML with an SMS body: "You're opted in to SMS updates."
8. WHEN the webhook signature is invalid, THE System SHALL return HTTP 403 with a simple error message (no TwiML required)

---

### Requirement 16: Send SMS Function Interface

**User Story:** As a developer integrating SMS into event approval and agent workflows, I want a clear send_sms() function interface, so that I can call it consistently across different notification types.

#### Acceptance Criteria

1. THE System SHALL export a function: send_sms(user_id, template, params, event_id=None, db_session=None, provider=None) → dict
2. WHEN send_sms() is called, THE System SHALL accept user_id (int), template (string), and params (dict) as required parameters
3. WHEN send_sms() is called, THE System SHALL accept event_id, db_session, and provider as optional parameters (default to resolved values)
4. WHEN send_sms() returns, THE System SHALL return a dict: {"sent": bool, "reason_skipped": str or None, "provider_sid": str or None}
5. WHEN a required parameter is missing or invalid, THE System SHALL raise ValueError with a descriptive message
6. WHEN template is not a key in TEMPLATES dict, THE System SHALL raise ValueError(f"Unknown template: {template}")
7. WHEN params dict is missing a required placeholder key, THE System SHALL raise KeyError with the missing key name

---

### Requirement 17: Access Control for SMS Sends

**User Story:** As a security administrator, I want to ensure SMS is only sent to buildings authorized for the event, so that building managers don't receive requests they shouldn't.

#### Acceptance Criteria

1. WHEN send_sms(user_id, "building_ask", params, event_id=E) is called, THE System SHALL verify that event_id=E exists in the events table
2. WHEN the event is found, THE System SHALL verify that the user's building_id is included in the event's buildings list
3. IF the user's building_id is not in the event, THE System SHALL return {"sent": false, "reason_skipped": "building_not_in_event"} and audit log the skip
4. IF the event_id does not exist, THE System SHALL raise ValueError(f"Event {event_id} not found")
5. FOR operator alerts (template not "building_ask"), THE System SHALL NOT enforce event-building membership (operator alerts go to all operators for the utility)

---

### Requirement 18: Phone Number Format Validation

**User Story:** As a data quality officer, I want phone numbers to be validated as E.164 format, so that international recipients are correctly identified.

#### Acceptance Criteria

1. WHEN a phone number is stored in users.phone, THE System SHALL enforce E.164 format (e.g., +12025551234)
2. WHEN send_sms() is called, THE System SHALL validate that the user's phone number is in E.164 format before calling the provider
3. IF a phone number is not in E.164 format, THE System SHALL return {"sent": false, "reason_skipped": "invalid_phone_format"} and audit log the skip
4. WHEN parsing an inbound From field, THE System SHALL normalize it to E.164 before matching against users.phone
5. WHEN comparing phone numbers, THE System SHALL use exact string matching (E.164 strings are unique and unambiguous)

---

### Requirement 19: Template Parameter Validation

**User Story:** As a developer, I want the system to validate template parameters before rendering, so that I catch missing or incorrect substitutions early.

#### Acceptance Criteria

1. WHEN send_sms() renders a template with params, THE System SHALL identify all placeholders in the template (e.g., {window}, {building_name})
2. WHEN a placeholder exists in the template, THE System SHALL verify that a corresponding key exists in the params dict
3. IF a required param is missing, THE System SHALL raise KeyError(f"Missing template parameter: {key}")
4. WHEN a template is rendered successfully, THE System SHALL return a plain-text SMS body
5. THE System SHALL NOT allow extra keys in params dict that don't match any placeholder (extra keys are silently ignored for flexibility)

---

### Requirement 20: SMS Length Validation

**User Story:** As a compliance officer, I want to ensure SMS bodies do not exceed the 160-character standard, so that messages are not split or truncated.

#### Acceptance Criteria

1. WHEN an SMS body is rendered from a template, THE System SHALL validate its length
2. IF the rendered body exceeds 160 characters, THE System SHALL raise ValueError(f"SMS body exceeds 160 characters: {len(body)} chars")
3. WHEN templates are validated at module load, THE System SHALL check that all templates (unsubstituted) can accommodate typical parameter values without exceeding 160 characters
4. THE System SHALL treat emoji and international characters as single characters (assume UTF-8 encoding)

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of the system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Access Control — Never Send Building Ask for Unauthorized Building

**Statement:** For any randomly generated user U with building_id B, event E not containing building B, and template="building_ask", invoking send_sms(U.id, "building_ask", {...}, event_id=E.id) SHALL either raise ValueError or return {"sent": false, "reason_skipped": "..."}. The provider.send() method SHALL never be called.

**Validates: Requirements 17.1, 17.2, 17.3**

---

### Property 2: Opt-Out Respected — Never Send to Opted-Out User

**Statement:** For any user U with sms_opted_out=true and any template T and params P, invoking send_sms(U.id, T, P, db_session=...) SHALL return {"sent": false, "reason_skipped": "opted_out"}. The provider.send() method SHALL never be called, regardless of whether U.phone is valid or any event exists.

**Validates: Requirements 1.4, 2.4, 3.4, 4.4, 9.3**

---

### Property 3: Demo Mode Allowlist Enforcement

**Statement:** For any TwilioProvider configured with demo_mode=true and SMS_DEMO_ALLOWLIST={"+12025551111", "+12025552222"}, and any phone number P not in the allowlist, invoking provider.send(P, "body") SHALL return SMSResult(success=false, ...) and not make any HTTP request to Twilio.

**Validates: Requirements 10.2, 10.3, 10.5**

---

### Property 4: Parser Totality and Correctness

**Statement:** For any arbitrary string input S, parse_reply_body(S) SHALL return exactly one of: "yes", "no", "STOP", "START", a positive integer, or None. The function is total (always terminates with one result), and the output category is deterministic (same input always produces same output).

**Validates: Requirements 7.4, 7.5, 7.6, 7.7, 7.9**

---

### Property 5: Forbidden Words Excluded from Rendered Templates

**Statement:** For any template T in {building_ask, operator_draft_ready, operator_backfill, operator_unreachable} and any params P where all placeholders are substituted, rendering T with P SHALL produce a string that contains none of the substrings: "cut", "shut off", "curtail", "disconnect" (case-insensitive).

**Validates: Requirements 5.2, 5.4, 5.5**

---

### Property 6: Signature Validation Non-Bypassable

**Statement:** For any POST body B and any signature S that is not HMAC-SHA1(auth_token, url || B_params_in_key_order), validate_signature(B, S, auth_token, url) SHALL return False. No signature other than the correct one SHALL validate.

**Validates: Requirements 6.2, 6.3**

---

### Property 7: Audit Trail Completeness

**Statement:** For any SMS action (send, skip, fail) initiated by send_sms() or the inbound webhook, exactly one audit_log row SHALL be written with: user_id, action, timestamp, and reason (if applicable). No SMS action occurs without a corresponding audit_log entry.

**Validates: Requirements 1.8, 12.1, 13.1**

---

### Property 8: Outbound Messages Persistence

**Statement:** For any successful SMS send via provider.send(), the returned SMSResult.provider_sid SHALL be written to outbound_messages.provider_sid in a single transaction. If the transaction fails, the provider.send() call is rolled back (no side effects with Twilio).

**Validates: Requirements 1.5, 1.6**

---

### Property 9: Replies Persist Only for Registered Users with Active Events

**Statement:** For any inbound webhook reply (YES/NO/kW) parsed from POST /sms/inbound, a replies row SHALL be written to the database if and only if: (1) the From phone is registered to a user, (2) the user has a building_id, and (3) an event exists with status=approved, closed_at IS NULL, and the building in its buildings list. Otherwise, no replies row is written, and an SMS is sent to the user.

**Validates: Requirements 8.2, 8.3, 8.5**

---

### Property 10: Template Round-Trip (Parse → Render)

**Statement:** For any template T and valid params dict P that satisfy all placeholder requirements, rendering T with P SHALL produce a string S such that: (1) S contains all values from P in the expected positions, (2) S is ≤160 characters, (3) S contains no forbidden words.

**Validates: Requirements 5.1, 19.1, 19.2, 20.1, 20.2**

---

### Property 11: Opt-Out / Opt-In Atomic Update

**Statement:** For any STOP or START reply received at POST /sms/inbound, the update to user.sms_opted_out and the corresponding audit_log entry SHALL be committed in a single atomic transaction. If the transaction fails, neither is committed.

**Validates: Requirements 9.5**

---

### Property 12: No SMS Send Without Valid Provider

**Statement:** For any call to send_sms(...) with provider=None, THE System SHALL resolve the provider from configuration and use it consistently throughout the function. If no provider is configured, send_sms SHALL raise a ValueError immediately.

**Validates: Requirements 14.3**

---

