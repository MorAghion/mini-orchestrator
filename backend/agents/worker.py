"""Stage 1 worker agent — one instance per doc role. Produces markdown text."""

from __future__ import annotations

from backend.agents.base import BaseAgent
from backend.agents.prompts.stage1 import CONTEXT_DEPS, FILENAMES, PROMPTS
from backend.models.project import AgentRole


class DocWorkerAgent(BaseAgent):
    """Single class, configured per role via its AgentRole."""

    def __init__(self, role: AgentRole):
        if role not in PROMPTS or role in (AgentRole.LEAD, AgentRole.REVIEWER):
            raise ValueError(f"DocWorkerAgent cannot be instantiated for role {role}")
        super().__init__(
            name=role.value,
            role=role.value,
            system_prompt=PROMPTS[role],
        )
        self.agent_role = role
        self.filename = FILENAMES[role]

    def context_deps(self) -> list[AgentRole]:
        return CONTEXT_DEPS.get(self.agent_role, [])

    async def produce_doc(
        self,
        idea: str,
        prior_artifacts: dict[AgentRole, str],
        rework_feedback: str | None = None,
    ) -> str:
        """Generate the doc. `prior_artifacts` maps role -> markdown content."""
        sections: list[str] = [f"## Project idea\n\n{idea}"]
        for dep in self.context_deps():
            content = prior_artifacts.get(dep)
            if content is None:
                continue
            sections.append(f"## {FILENAMES[dep]}\n\n{content}")
        if rework_feedback:
            sections.append(
                "## Reviewer feedback (rework cycle — address these issues)\n\n"
                + rework_feedback
            )
        user_message = "\n\n".join(sections) + f"\n\nProduce {self.filename} now."
        return (await self.complete(user_message)).strip()
