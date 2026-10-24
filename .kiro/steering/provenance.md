---
inclusion: always
---

# Provenance rules

- Show a user a number only if its tool result carries a source id and URL.
- Never invent a rate, emissions factor, building value, or enrollment status.
- If a value is unavailable, return "unavailable" with the reason; never estimate silently.
- Keep program rates, capacity prices, LMPs, and emissions factors in one constants file, one citation per constant; never inline them.
- Label every savings figure "estimated" and keep its assumptions retrievable.
- Mark simulated data (replies, meter reads, enrollment) as simulated in code and UI.
