"""Lead agent — two modes:

1. `plan_stage1(idea)` — produces the Stage 1 wave plan via a schema-validated
   tool call. Used by the wave engine.
2. `chat(history, user_message, persona)` — conversational mode used by the
   right-panel chat UI. Switches system prompt based on project phase:
   shaper (pre-run), narrator (during), refiner (post).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from backend.agents.base import BaseAgent
from backend.agents.prompts.chat import PROMPTS as CHAT_PROMPTS
from backend.agents.prompts.stage1 import PROMPTS as STAGE1_PROMPTS
from backend.models.project import AgentRole, ChatMessage, ChatRole, WavePlan

PLAN_WAVES_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "waves": {
            "type": "array",
            "description": "Ordered list of waves. Each wave is a list of role names to run in parallel.",
            "items": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": [
                        r.value
                        for r in AgentRole
                        if r not in (AgentRole.LEAD, AgentRole.REVIEWER)
                    ],
                },
            },
        }
    },
    "required": ["waves"],
    "additionalProperties": False,
}


ChatPersona = Literal["shaper", "narrator", "refiner"]


# Markers the Lead emits to signal orchestrator actions. Parsed out of the
# reply so they don't get shown to the user verbatim.
_MARKERS = {
    # BRIEF:\n<body>\nBRIEF_READY — body is captured as the project idea
    "brief_block": re.compile(
        r"^BRIEF:\s*\n(?P<body>.*?)\n^BRIEF_READY\s*$",
        re.MULTILINE | re.DOTALL,
    ),
    "note_queued": re.compile(r"^NOTE_QUEUED:\s*(.+?)$", re.MULTILINE),
    "revision_request": re.compile(r"^REVISION_REQUEST:\s*(.+?)$", re.MULTILINE),
}


@dataclass
class ChatReply:
    """Lead's reply after parsing orchestrator markers out of the raw text."""
    display_text: str                   # what to show the user (markers stripped)
    brief_ready: bool = False           # shaper: user has approved the brief
    brief_text: str | None = None       # shaper: the brief body to save as project idea
    note_queued: str | None = None      # narrator: note to queue
    revision_request: str | None = None # refiner: revision to schedule
    cost_usd: float = 0.0               # equivalent cost this call


class LeadAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(
            name="Lead",
            role=AgentRole.LEAD.value,
            system_prompt=STAGE1_PROMPTS[AgentRole.LEAD],
        )

    # ------------------------------------------------------------------ planning

    async def plan_stage1(self, idea: str) -> WavePlan:
        result = await self.tool_call(
            user_message=f"Project idea:\n\n{idea}\n\nProduce the Stage 1 wave plan now.",
            tool_name="plan_waves",
            tool_description="Emit the Stage 1 doc-generation wave plan.",
            tool_schema=PLAN_WAVES_TOOL_SCHEMA,
        )
        waves = [[AgentRole(r) for r in wave] for wave in result["waves"]]
        return WavePlan(waves=waves)

    # --------------------------------------------------------------------- chat

    async def chat(
        self,
        history: list[ChatMessage],
        user_message: str,
        persona: ChatPersona,
    ) -> ChatReply:
        """Run one turn of the Lead chat.

        The CLI is stateless per invocation, so we render the history inline
        in the user message. The system prompt is swapped per persona.
        """
        system = CHAT_PROMPTS[persona]
        rendered = _render_history(history, user_message)
        raw, cost = await self.complete_with_usage(rendered, system_override=system)
        return _parse_reply(raw, cost)


def _render_history(history: list[ChatMessage], new_user_message: str) -> str:
    """Produce a single string containing prior turns + the new user message.

    Shape intentionally resembles a transcript so the CLI's default template
    (which expects a user message) reads it as "here is the conversation so
    far, now respond to the latest user turn."
    """
    lines: list[str] = []
    if history:
        lines.append("# Conversation so far")
        for m in history:
            speaker = "User" if m.role == ChatRole.USER else "You"
            lines.append(f"\n## {speaker}\n{m.content.strip()}")
        lines.append("")  # blank separator
    lines.append("# Latest user message")
    lines.append(new_user_message.strip())
    lines.append("")
    lines.append("Respond now as the Lead. Remember the formatting rules from your system prompt (markers go on their own line at the end, only when appropriate).")
    return "\n".join(lines)


def _parse_reply(raw: str, cost: float) -> ChatReply:
    """Strip orchestrator markers from raw reply and extract their payloads."""
    display = raw
    reply = ChatReply(display_text=display, cost_usd=cost)

    m = _MARKERS["brief_block"].search(display)
    if m:
        reply.brief_ready = True
        reply.brief_text = m.group("body").strip()
        # Replace the whole BRIEF:…BRIEF_READY block with a friendlier sign-off
        # so the user-visible chat reads well instead of showing the raw marker.
        display = _MARKERS["brief_block"].sub(
            "Brief locked in. Launching Stage 1 now.", display
        )

    m = _MARKERS["note_queued"].search(display)
    if m:
        reply.note_queued = m.group(1).strip()
        display = _MARKERS["note_queued"].sub("", display)

    m = _MARKERS["revision_request"].search(display)
    if m:
        reply.revision_request = m.group(1).strip()
        display = _MARKERS["revision_request"].sub("", display)

    reply.display_text = display.strip()
    return reply
