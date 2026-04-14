"""Shared Claude API loop used by all Stage 1 agents.

Responsibilities:
- Construct requests against the Anthropic SDK with prompt caching on the system prompt.
- Support plain text completions, tool-use loops, and structured (JSON-schema) outputs.
- Keep per-agent state (name, role, model) minimal — the blackboard holds state.
"""

from __future__ import annotations

from typing import Any

from anthropic import AsyncAnthropic

from backend.config import AGENT_MODEL, ANTHROPIC_API_KEY


class BaseAgent:
    """Base class — subclasses provide role + system prompt and call self.complete()/self.structured()."""

    def __init__(
        self,
        name: str,
        role: str,
        system_prompt: str,
        model: str = AGENT_MODEL,
        max_tokens: int = 16000,
    ):
        self.name = name
        self.role = role
        self.system_prompt = system_prompt
        self.model = model
        self.max_tokens = max_tokens
        self._client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    def _cached_system(self) -> list[dict[str, Any]]:
        """Render the system prompt as a single cacheable block."""
        return [
            {
                "type": "text",
                "text": self.system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    async def complete(self, user_message: str) -> str:
        """Single-turn completion; returns the assistant's text."""
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self._cached_system(),
            messages=[{"role": "user", "content": user_message}],
        )
        for block in response.content:
            if block.type == "text":
                return block.text
        return ""

    async def structured(
        self,
        user_message: str,
        schema: dict[str, Any],
        tool_name: str = "emit_result",
    ) -> dict[str, Any]:
        """Force a structured response matching `schema`.

        Implemented via a forced tool call — this is the most portable way to get
        validated JSON across SDK versions.
        """
        return await self.tool_call(
            user_message=user_message,
            tool_name=tool_name,
            tool_description="Emit the structured result as typed input.",
            tool_schema=schema,
        )

    async def tool_call(
        self,
        user_message: str,
        tool_name: str,
        tool_description: str,
        tool_schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Force a single tool call and return the parsed input dict. Used by the Lead
        to emit its wave plan as a typed object rather than free-form JSON."""
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self._cached_system(),
            messages=[{"role": "user", "content": user_message}],
            tools=[
                {
                    "name": tool_name,
                    "description": tool_description,
                    "input_schema": tool_schema,
                }
            ],
            tool_choice={"type": "tool", "name": tool_name},
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                return block.input  # already parsed by SDK
        raise RuntimeError(f"{self.name}: expected tool_use for {tool_name}")
