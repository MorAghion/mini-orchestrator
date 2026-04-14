"""Lead agent — produces the Stage 1 wave plan via a single tool call."""

from __future__ import annotations

from backend.agents.base import BaseAgent
from backend.agents.prompts.stage1 import PROMPTS
from backend.models.project import AgentRole, WavePlan


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


class LeadAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(
            name="Lead",
            role=AgentRole.LEAD.value,
            system_prompt=PROMPTS[AgentRole.LEAD],
        )

    async def plan_stage1(self, idea: str) -> WavePlan:
        result = await self.tool_call(
            user_message=f"Project idea:\n\n{idea}\n\nProduce the Stage 1 wave plan now.",
            tool_name="plan_waves",
            tool_description="Emit the Stage 1 doc-generation wave plan.",
            tool_schema=PLAN_WAVES_TOOL_SCHEMA,
        )
        waves = [[AgentRole(r) for r in wave] for wave in result["waves"]]
        return WavePlan(waves=waves)
