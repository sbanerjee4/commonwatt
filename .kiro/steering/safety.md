---
inclusion: always
---

# Safety and domain rules

- Treat demand response as voluntary and paid; participants can decline any event.
- Never write "cut", "shut off", "curtail", or "disconnect" in user-facing text; use "asked to reduce" or "event participation".
- Never return a plan whose EJ share exceeds the configured cap; return an explicit "unreachable" result instead.
- Never include a building called in the immediately previous event.
- Never include a protected facility (schools in session, cooling centers, nursing homes) when the heat threshold is exceeded.
- Never contact a building or export an event without operator approval; the agent proposes, the operator decides.
- When a constraint makes the target unreachable, present the trade-off explicitly (cap value vs achievable MW) and stop.
- Keep both rejected and accepted plan versions in the trace.
