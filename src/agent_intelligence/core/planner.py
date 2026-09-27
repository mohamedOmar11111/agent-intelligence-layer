"""Planner - converts goals into execution plans using coordinator logic."""

import json
from typing import Optional
from datetime import datetime

from agent_intelligence.core.config import get_settings
from agent_intelligence.core.context_store import get_context_store
from agent_intelligence.core.skill_loader import SkillLoader, load_skills
from agent_intelligence.core.model_adapter import get_model_adapter
from agent_intelligence.skills.schema import Skill, ExecutionPlan, ExecutionStage, TaskBrief


COORDINATOR_PROMPT = """You are the Coordinator for a business team. Given a goal, business brief, and available skills, create an execution plan.

BUSINESS BRIEF:
{brief}

AVAILABLE SKILLS:
{skills}

GOAL: {goal}

Create a minimal sequence of roles to achieve this goal. For each stage, specify:
1. skill_id - the role to execute
2. inputs - what data/artifacts it needs (from brief or previous stages)
3. depends_on - stage numbers this depends on (0-indexed)
4. acceptance_criteria - what must be true for this stage to pass
5. required_tools - any tools needed (web_search, crm, email, etc.)
6. can_run_parallel - whether this can run alongside other stages

Return ONLY valid JSON:
{{
  "stages": [
    {{
      "skill_id": "m02-customer-researcher",
      "inputs": {{"research_question": "What criteria do B2B SaaS buyers use?"}},
      "depends_on": [],
      "acceptance_criteria": ["Themes table with verbatim quotes", "Every quote traced to source"],
      "required_tools": ["web_search"],
      "can_run_parallel": false
    }}
  ],
  "estimated_total_cost": 5.0
}}"""


class Planner:
    """Plans execution sequences from goals."""

    def __init__(self):
        self.settings = get_settings()
        self.skill_loader = SkillLoader()
        self.model = get_model_adapter()
        self.context = get_context_store()

    def plan(
        self,
        goal: str,
        brief_version: str = "latest",
        preferred_skills: Optional[list[str]] = None,
        max_stages: int = 8,
        budget_usd: Optional[float] = None
    ) -> ExecutionPlan:
        """Create an execution plan for a goal."""

        # Load brief
        brief = self.context.get_brief(brief_version)
        if not brief:
            raise ValueError(f"No business brief found for version: {brief_version}")

        # Load available skills
        all_skills = self.skill_loader.load_all_skills()

        # Filter skills
        if preferred_skills:
            skills = {k: v for k, v in all_skills.items() if k in preferred_skills}
        else:
            skills = all_skills

        # Build skills summary for prompt
        skills_summary = self._build_skills_summary(skills)

        # Call coordinator model
        prompt = COORDINATOR_PROMPT.format(
            brief=brief[:8000],  # Limit brief size
            skills=skills_summary,
            goal=goal
        )

        messages = [
            {"role": "system", "content": "You are an expert business coordinator. Output only valid JSON."},
            {"role": "user", "content": prompt}
        ]

        response = self.model.complete(messages)

        # Parse plan
        plan_data = self._parse_plan_response(response.content)

        # Build ExecutionPlan
        stages = []
        for i, stage_data in enumerate(plan_data.get("stages", [])[:max_stages]):
            skill_id = stage_data.get("skill_id")
            skill = skills.get(skill_id)
            if not skill:
                continue

            stage = ExecutionStage(
                stage_id=i,
                skill_id=skill_id,
                skill_name=skill.name,
                inputs=stage_data.get("inputs", {}),
                depends_on=stage_data.get("depends_on", []),
                acceptance_criteria=stage_data.get("acceptance_criteria", skill.acceptance_check.criteria if skill.acceptance_check else []),
                required_tools=stage_data.get("required_tools", skill.tool_requirements),
                estimated_cost_usd=skill.estimated_cost_usd or 0.5,
                timeout_seconds=skill.timeout_seconds,
                can_run_parallel=stage_data.get("can_run_parallel", False)
            )
            stages.append(stage)

        total_cost = sum(s.estimated_cost_usd for s in stages)
        if budget_usd and total_cost > budget_usd:
            # Trim stages to fit budget
            stages = self._trim_to_budget(stages, budget_usd)
            total_cost = sum(s.estimated_cost_usd for s in stages)

        return ExecutionPlan(
            goal=goal,
            brief_version=brief_version,
            stages=stages,
            estimated_total_cost=total_cost,
            required_approvals=self._identify_approvals(stages)
        )

    def _build_skills_summary(self, skills: dict[str, Skill]) -> str:
        """Build compact skills summary for planner."""
        lines = []
        for skill in skills.values():
            lines.append(f"- {skill.id} ({skill.name}): {skill.description[:100]}")
            if skill.acceptance_check:
                lines.append(f"  Acceptance: {'; '.join(skill.acceptance_check.criteria[:2])}")
        return "\n".join(lines)

    def _parse_plan_response(self, content: str) -> dict:
        """Parse JSON from model response."""
        # Try to extract JSON
        import re
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        # Fallback: try full content
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"stages": []}

    def _trim_to_budget(self, stages: list[ExecutionStage], budget: float) -> list[ExecutionStage]:
        """Trim stages to fit budget."""
        trimmed = []
        total = 0.0
        for stage in stages:
            if total + stage.estimated_cost_usd <= budget:
                trimmed.append(stage)
                total += stage.estimated_cost_usd
            else:
                break
        return trimmed

    def _identify_approvals(self, stages: list[ExecutionStage]) -> list[str]:
        """Identify which stages need human approval."""
        approvals = []
        for stage in stages:
            skill = self.skill_loader.get_skill(stage.skill_id)
            if skill and any(t in ["email", "send", "publish", "spend", "external"] for t in skill.tags):
                approvals.append(f"stage_{stage.stage_id}_{stage.skill_id}")
        return approvals

    def create_task_brief(
        self,
        plan: ExecutionPlan,
        stage: ExecutionStage,
        previous_outputs: dict[str, any]
    ) -> TaskBrief:
        """Create a task brief for a specific stage."""
        task_id = f"task-{plan.goal[:20]}-{stage.stage_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        # Build inputs from plan + previous outputs
        inputs = dict(stage.inputs)
        for dep_id in stage.depends_on:
            dep_stage = plan.stages[dep_id]
            dep_output = previous_outputs.get(dep_stage.skill_id)
            if dep_output:
                inputs[f"{dep_stage.skill_id}_output"] = dep_output

        return TaskBrief(
            task_id=task_id,
            role=stage.skill_id,
            decision_or_outcome=f"Complete {stage.skill_name} for: {plan.goal}",
            inputs=inputs,
            scope={"goal": plan.goal},
            required_output={"format": "markdown", "complete": True},
            success_criteria=stage.acceptance_criteria,
            constraints={"budget_usd": stage.estimated_cost_usd, "timeout_seconds": stage.timeout_seconds},
            decision_owner="user",
            next_recipient=plan.stages[stage.stage_id + 1].skill_id if stage.stage_id + 1 < len(plan.stages) else "complete",
            business_brief_version=plan.brief_version
        )