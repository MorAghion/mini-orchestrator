"""Reviewer agent — checks Stage 1 docs for cross-document consistency and returns a ReviewReport."""

from __future__ import annotations

from backend.agents.base import BaseAgent
from backend.agents.prompts.stage1 import FILENAMES, PROMPTS
from backend.models.project import AgentRole, ReviewReport


REVIEW_REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "overall_verdict": {"type": "string", "enum": ["approved", "needs_rework"]},
        "summary": {"type": "string"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                    "category": {"type": "string"},
                    "affected_artifacts": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "description": {"type": "string"},
                    "suggested_fix": {"type": "string"},
                },
                "required": [
                    "severity",
                    "category",
                    "affected_artifacts",
                    "description",
                    "suggested_fix",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["overall_verdict", "summary", "issues"],
    "additionalProperties": False,
}


class ReviewerAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(
            name="Reviewer",
            role=AgentRole.REVIEWER.value,
            system_prompt=PROMPTS[AgentRole.REVIEWER],
        )

    async def review(
        self,
        idea: str,
        artifacts: dict[AgentRole, str],
    ) -> ReviewReport:
        sections: list[str] = [f"## Project idea\n\n{idea}"]
        for role, content in artifacts.items():
            fname = FILENAMES.get(role, role.value + ".md")
            sections.append(f"## {fname}\n\n{content}")
        user_message = (
            "\n\n".join(sections)
            + "\n\nReview these artifacts for cross-document consistency. Emit a ReviewReport."
        )
        raw = await self.structured(user_message, REVIEW_REPORT_SCHEMA)
        return ReviewReport(**raw)
