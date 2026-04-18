"""Shared Claude Code CLI loop used by all Stage 1 agents.

All agents consume the user's Claude subscription (Max plan) by shelling out
to the `claude` CLI in print mode — no Anthropic API key required.

Responsibilities:
- Spawn `claude -p ...` subprocesses asynchronously.
- Capture the JSON envelope and extract `result` (text) or `structured_output` (JSON-schema-validated).
- Disable all built-in tools (`--tools ""`) so agents only produce text / structured JSON.
- Skip session persistence and CLAUDE.md auto-discovery so each call is self-contained.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from backend.config import AGENT_MODEL


class CLIError(RuntimeError):
    """Raised when the `claude` CLI exits non-zero or returns an error envelope."""


class BaseAgent:
    """Subclasses provide role + system prompt and call self.complete() / self.structured()."""

    def __init__(
        self,
        name: str,
        role: str,
        system_prompt: str,
        model: str = AGENT_MODEL,
        max_tokens: int = 16000,  # advisory; CLI honors its own model limits
    ):
        self.name = name
        self.role = role
        self.system_prompt = system_prompt
        self.model = model
        self.max_tokens = max_tokens

    def _base_cmd(self, user_message: str) -> list[str]:
        """Common argv. System prompt replaces the default (not appended)."""
        return [
            "claude",
            "-p",
            user_message,
            "--system-prompt",
            self.system_prompt,
            "--model",
            self.model,
            "--tools",
            "",  # disable all tools — agents produce text/JSON only
            "--output-format",
            "json",
            "--no-session-persistence",
        ]

    async def _run(self, cmd: list[str]) -> dict[str, Any]:
        # Strip ANTHROPIC_API_KEY so the CLI always uses the Max subscription.
        # If a key is set in the shell profile or .env it would make the CLI
        # try API auth instead of the logged-in Max account and fail.
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,  # prevent any interactive prompts
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            out_head = stdout.decode(errors="replace")[:300]
            err_head = stderr.decode(errors="replace")[:300]
            raise CLIError(
                f"{self.name}: claude exited {proc.returncode}\n"
                f"  stderr: {err_head or '(empty)'}\n"
                f"  stdout: {out_head or '(empty)'}"
            )
        try:
            envelope = json.loads(stdout.decode())
        except json.JSONDecodeError as e:
            raise CLIError(
                f"{self.name}: could not parse CLI envelope: {e}\n"
                f"stdout head: {stdout[:500]!r}"
            ) from e
        if envelope.get("is_error"):
            raise CLIError(
                f"{self.name}: CLI reported error: {envelope.get('result', '')[:500]}"
            )
        return envelope

    async def complete(self, user_message: str) -> str:
        """Single-turn text completion; returns the assistant's `result` text."""
        envelope = await self._run(self._base_cmd(user_message))
        return str(envelope.get("result", "")).strip()

    async def complete_with_usage(
        self, user_message: str, system_override: str | None = None
    ) -> tuple[str, float]:
        """Same as complete() but also returns the CLI's reported cost_usd.

        `system_override` — if given, replaces the agent's system prompt for
        this one call. Used by chat-capable agents to switch personas
        without constructing a new instance.
        """
        cmd = self._base_cmd(user_message)
        if system_override is not None:
            # --system-prompt value sits right after the flag in _base_cmd
            i = cmd.index("--system-prompt") + 1
            cmd[i] = system_override
        envelope = await self._run(cmd)
        text = str(envelope.get("result", "")).strip()
        cost = float(envelope.get("total_cost_usd") or 0.0)
        return text, cost

    async def structured(
        self,
        user_message: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Request schema-validated JSON via the CLI's `--json-schema` flag.

        The CLI enforces the schema server-side and places the parsed object on
        `envelope.structured_output`.
        """
        cmd = self._base_cmd(user_message) + ["--json-schema", json.dumps(schema)]
        envelope = await self._run(cmd)
        structured = envelope.get("structured_output")
        if not isinstance(structured, dict):
            raise CLIError(
                f"{self.name}: envelope lacks structured_output; "
                f"result head: {str(envelope.get('result', ''))[:300]}"
            )
        return structured

    async def tool_call(
        self,
        user_message: str,
        tool_name: str,
        tool_description: str,
        tool_schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Compatibility shim for the previous API-based interface.

        The CLI path does not have forced tool calls the way the API does; the
        equivalent is schema-validated structured output. `tool_name` and
        `tool_description` are unused here — the schema alone constrains the shape.
        """
        del tool_name, tool_description  # unused
        return await self.structured(user_message, tool_schema)
