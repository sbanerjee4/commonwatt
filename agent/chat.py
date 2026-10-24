"""
Building chat agent — facility manager interface.

A facility manager can ask natural-language questions about their building:
  - "How much could we reduce?"
  - "What is my building's energy use?"
  - "What are we being asked to do today?"
  - "How much will we get paid?"

The agent has read access to building_info and estimate_savings via MCP tools.
It never produces a number without calling a tool first.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from anthropic import AnthropicBedrock
from agent.llm import get_client, get_model_id

from server.tools import building_info, estimate_savings
from agent.prompts import BUILDING_CHAT_SYSTEM

CHAT_TOOLS = [
    {
        "name": "building_info",
        "description": (
            "Return the full profile for one building: address, type, area, EUI, "
            "estimated curtailable load (kW), GHG emissions, and whether it is in an EJ zip."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "building_id": {"type": "string"},
            },
            "required": ["building_id"],
        },
    },
    {
        "name": "estimate_savings",
        "description": (
            "Estimate payments and savings for a given shed_mw and duration. "
            "Returns three counters: paid_to_buildings, avoided_system_cost, co2_avoided. "
            "All estimated — always show source_id and assumptions to the user."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "shed_mw": {"type": "number"},
                "event_duration_hours": {"type": "number", "default": 3.0},
            },
            "required": ["shed_mw"],
        },
    },
]

TOOL_FN_MAP: dict[str, Any] = {
    "building_info": building_info,
    "estimate_savings": estimate_savings,
}


@dataclass
class ChatMessage:
    role: str  # "user" | "assistant"
    content: str


@dataclass
class ChatSession:
    """
    Stateful chat session for one facility manager.
    Holds conversation history so multi-turn context works.
    """
    building_id: str
    event_context: dict | None = None  # set when a live event is asking this building
    _history: list[dict] = field(default_factory=list)
    _client: AnthropicBedrock = field(init=False)

    def __post_init__(self) -> None:
        self._client = get_client()

    def _system_prompt(self) -> str:
        base = BUILDING_CHAT_SYSTEM
        if self.event_context:
            base += (
                f"\n\n--- LIVE EVENT CONTEXT ---\n"
                f"Building {self.building_id} is being asked to participate in an event:\n"
                f"Window: {self.event_context.get('window_label', 'today')}\n"
                f"kW requested: {self.event_context.get('requested_kw', 'unknown')}\n"
                f"Reason selected: {self.event_context.get('reason', 'high afternoon load')}\n"
                f"Estimated payment: {self.event_context.get('estimated_payment_label', 'see estimate_savings tool')}\n"
                f"Enrollment capacity: {self.event_context.get('enrolled_capacity_kw', 'unknown')} kW\n"
                f"Note: Participation is voluntary. Reply YES, NO, or offer a counter kW amount.\n"
                f"This is SIMULATED data for the demo — label it as such.\n"
            )
        return base

    def chat(self, user_message: str) -> str:
        """
        Send a message and return the assistant's reply.
        Handles tool calls transparently.
        """
        self._history.append({"role": "user", "content": user_message})

        messages = list(self._history)

        while True:
            response = self._client.messages.create(
                model=get_model_id(),
                max_tokens=2048,
                system=self._system_prompt(),
                tools=CHAT_TOOLS,
                messages=messages,
            )

            if response.stop_reason == "tool_use":
                tool_results = []
                assistant_content = response.content

                for block in assistant_content:
                    if block.type == "tool_use":
                        fn = TOOL_FN_MAP.get(block.name)
                        if fn:
                            result = fn(**block.input)
                        else:
                            result = {"error": f"unknown tool {block.name!r}"}
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        })

                messages.append({"role": "assistant", "content": assistant_content})
                messages.append({"role": "user", "content": tool_results})

            else:
                # end_turn — extract text reply
                reply = "".join(
                    block.text for block in response.content if hasattr(block, "text")
                )
                self._history.append({"role": "assistant", "content": reply})
                return reply

    def reset(self) -> None:
        """Clear conversation history (new session)."""
        self._history = []


def make_session(
    building_id: str,
    event_context: dict | None = None,
) -> ChatSession:
    """
    Factory to create a chat session for a facility manager.

    Args:
        building_id: the BERDO building id
        event_context: optional dict describing a live event asking this building.
            Keys: window_label, requested_kw, reason, estimated_payment_label,
                  enrolled_capacity_kw
    """
    return ChatSession(building_id=building_id, event_context=event_context)


# ---------------------------------------------------------------------------
# CLI entry point for testing the chat agent interactively
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    building_id = sys.argv[1] if len(sys.argv) > 1 else "129860"
    print(f"Starting chat session for building {building_id}")
    print("Type 'quit' to exit, 'reset' to clear history.\n")

    session = make_session(building_id)

    while True:
        try:
            msg = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not msg:
            continue
        if msg.lower() == "quit":
            break
        if msg.lower() == "reset":
            session.reset()
            print("(session reset)\n")
            continue
        reply = session.chat(msg)
        print(f"\nAssistant: {reply}\n")
