"""Executor - runs execution plans with eval gates and human approval."""

import asyncio
import time
from typing import Optional
from datetime import datetime
from uuid import uuid4

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

from agent_intelligence.core.config import get_settings
from agent_intelligence.core.context_store import get_context_store
from agent_intelligence.core.skill_loader import SkillLoader
from agent_intelligence.core.model_adapter import get_model_adapter, ModelResponse
from agent_intelligence.core.planner import Planner
from agent_intelligence.gates.eval_gate import EvalGate
from agent_intelligence.gates.human_gate import HumanGate
from agent_intelligence.gates.cost_gate import CostGate
from agent_intelligence.skills.schema import (
    Skill, ExecutionPlan, ExecutionStage, TaskBrief, RoleOutput, HandoffRecord
)


class AgentState(dict):
    """LangGraph state for execution."""
    pass


class Executor:
    """Executes plans with quality gates and human approval."""

    def __init__(self):
        self.settings = get_settings()
        self.context = get_context_store()
        self.skill_loader = SkillLoader()
        self.model = get_model_adapter()
        self.planner = Planner()
        self.eval_gate = EvalGate()
        self.human_gate = HumanGate()
        self.cost_gate = CostGate()
        self._checkpointer = None

    def _get_checkpointer(self):
        """Get or create SQLite checkpointer."""
        if self._checkpointer is None:
            db_path = self.settings.memory.sqlite_path
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._checkpointer = SqliteSaver(str(db_path))
        return self._checkpointer

    def execute_plan(
        self,
        plan: ExecutionPlan,
        thread_id: Optional[str] = None,
        auto_approve: bool = False
    ) -> dict:
        """Execute a full plan."""
        thread_id = thread_id or f"run-{uuid4().hex[:8]}"

        # Build the graph
        graph = self._build_execution_graph(plan)

        # Initial state
        initial_state = {
            "plan": plan.model_dump(),
            "current_stage": 0,
            "stage_outputs": {},
            "approvals_needed": plan.required_approvals,
            "auto_approve": auto_approve,
            "total_cost": 0.0,
            "total_tokens": 0,
            "errors": [],
            "status": "running"
        }

        # Compile and run
        app = graph.compile(checkpointer=self._get_checkpointer())
        config = {"configurable": {"thread_id": thread_id}}

        result = app.invoke(initial_state, config=config)

        return {
            "run_id": thread_id,
            "status": result.get("status", "unknown"),
            "outputs": result.get("stage_outputs", {}),
            "total_cost": result.get("total_cost", 0),
            "total_tokens": result.get("total_tokens", 0),
            "errors": result.get("errors", [])
        }

    def _build_execution_graph(self, plan: ExecutionPlan) -> StateGraph:
        """Build LangGraph for plan execution."""

        def execute_stage(state: AgentState) -> AgentState:
            stage_idx = state["current_stage"]
            plan_obj = ExecutionPlan(**state["plan"])
            stage = plan_obj.stages[stage_idx]

            skill = self.skill_loader.get_skill(stage.skill_id)
            if not skill:
                state["errors"].append(f"Skill not found: {stage.skill_id}")
                state["status"] = "error"
                return state

            # Create task brief
            task_brief = self.planner.create_task_brief(
                plan_obj, stage, state["stage_outputs"]
            )

            # Check cost gate
            if not self.cost_gate.check(stage.estimated_cost_usd, state["total_cost"]):
                state["errors"].append(f"Budget exceeded at stage {stage_idx}")
                state["status"] = "budget_exceeded"
                return state

            # Build messages for role
            messages = self._build_role_messages(skill, task_brief, state["stage_outputs"])

            # Execute role
            response = self.model.complete(messages, skill=skill)

            # Create output
            output = RoleOutput(
                task_id=task_brief.task_id,
                skill_id=stage.skill_id,
                skill_name=stage.skill_name,
                output=response.content,
                tokens_used=response.tokens_used,
                cost_usd=response.cost_usd,
                latency_seconds=response.latency_seconds,
                brief_version=plan_obj.brief_version
            )

            # Run eval gate
            eval_result = self.eval_gate.evaluate(output, stage.acceptance_criteria, skill)
            output.quality_score = eval_result.score
            output.quality_details = eval_result.details

            if not eval_result.passed:
                if eval_result.blockers:
                    state["errors"].append(f"Eval blocked: {eval_result.blockers}")
                    state["status"] = "eval_failed"
                    return state
                # Retry once with feedback
                retry_messages = messages + [
                    {"role": "assistant", "content": response.content},
                    {"role": "user", "content": f"Please fix: {eval_result.feedback}"}
                ]
                retry_response = self.model.complete(retry_messages, skill=skill)
                output.output = retry_response.content
                output.tokens_used += retry_response.tokens_used
                output.cost_usd += retry_response.cost_usd

                # Re-evaluate
                eval_result = self.eval_gate.evaluate(output, stage.acceptance_criteria, skill)
                output.quality_score = eval_result.score
                output.quality_details = eval_result.details

                if not eval_result.passed:
                    state["errors"].append(f"Eval failed after retry: {eval_result.feedback}")
                    state["status"] = "eval_failed"
                    return state

            # Save output
            self.context.save_output(output)
            state["stage_outputs"][stage.skill_id] = output.output
            state["total_cost"] += output.cost_usd
            state["total_tokens"] += output.tokens_used

            # Check human gate
            if not auto_approve and self._needs_human_approval(stage, output):
                approval = self.human_gate.request_approval(
                    task_id=task_brief.task_id,
                    stage=stage,
                    output=output,
                    plan=plan_obj
                )
                if not approval.approved:
                    state["errors"].append(f"Human rejected: {approval.reason}")
                    state["status"] = "rejected"
                    return state
                if approval.edited_output:
                    output.output = approval.edited_output

            # Create handoff if next stage exists
            if stage_idx + 1 < len(plan_obj.stages):
                next_stage = plan_obj.stages[stage_idx + 1]
                handoff = self._create_handoff(output, stage, next_stage)
                self.context.save_handoff(handoff)

            return state

        def should_continue(state: AgentState) -> str:
            if state.get("status") in ("error", "budget_exceeded", "eval_failed", "rejected", "complete"):
                return "end"
            if state["current_stage"] >= len(ExecutionPlan(**state["plan"]).stages) - 1:
                state["status"] = "complete"
                return "end"
            return "continue"

        def increment_stage(state: AgentState) -> AgentState:
            state["current_stage"] += 1
            return state

        # Build graph
        workflow = StateGraph(AgentState)
        workflow.add_node("execute", execute_stage)
        workflow.add_node("increment", increment_stage)
        workflow.set_entry_point("execute")
        workflow.add_conditional_edges(
            "execute",
            should_continue,
            {"continue": "increment", "end": END}
        )
        workflow.add_edge("increment", "execute")

        return workflow

    def _build_role_messages(
        self,
        skill: Skill,
        task_brief: TaskBrief,
        previous_outputs: dict
    ) -> list[dict]:
        """Build messages for role execution."""
        brief = self.context.get_brief(task_brief.business_brief_version) or ""

        messages = [
            {"role": "system", "content": skill.prompt},
            {"role": "user", "content": f"""
BUSINESS BRIEF:
{brief}

TASK BRIEF:
{task_brief.model_dump_json(indent=2)}

PREVIOUS OUTPUTS:
{self._format_previous_outputs(previous_outputs, task_brief.inputs)}

Execute this task and produce the required output.
"""}
        ]
        return messages

    def _format_previous_outputs(self, outputs: dict, inputs: dict) -> str:
        """Format previous outputs for context."""
        parts = []
        for key, value in inputs.items():
            if key in outputs:
                parts.append(f"--- {key} ---\n{outputs[key][:2000]}")
        return "\n\n".join(parts) if parts else "None"

    def _needs_human_approval(self, stage: ExecutionStage, output: RoleOutput) -> bool:
        """Check if stage needs human approval."""
        skill = self.skill_loader.get_skill(stage.skill_id)
        if not skill:
            return False

        # Check tags for approval triggers
        approval_tags = {"email", "send", "publish", "spend", "external", "contract", "legal"}
        if any(tag in approval_tags for tag in skill.tags):
            return True

        # Check quality score
        if output.quality_score and output.quality_score < 8:
            return True

        return False

    def _create_handoff(
        self,
        output: RoleOutput,
        from_stage: ExecutionStage,
        to_stage: ExecutionStage
    ) -> HandoffRecord:
        """Create handoff record between stages."""
        return HandoffRecord(
            task_id=output.task_id,
            from_role=from_stage.skill_id,
            to_role=to_stage.skill_id,
            approved_output=output.output,
            output_version="1.0",
            source_references=[],  # Could extract from evidence
            reliable_facts=[],     # Could extract from evidence
            assumptions=output.assumptions,
            unresolved_items=output.gaps,
            decision_required=f"Review {to_stage.skill_name} input",
            decision_owner="user",
            next_action=f"Execute {to_stage.skill_name}",
            brief_version=output.brief_version
        )


# Global instance
_executor: Optional[Executor] = None


def get_executor() -> Executor:
    """Get global executor instance."""
    global _executor
    if _executor is None:
        _executor = Executor()
    return _executor