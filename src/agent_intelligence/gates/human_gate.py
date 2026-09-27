"""Human Gate - approval workflow for risky actions."""

from dataclasses import dataclass
from typing import Optional
from enum import Enum

from agent_intelligence.core.config import get_settings
from agent_intelligence.core.context_store import get_context_store
from agent_intelligence.skills.schema import RoleOutput, ExecutionStage, ExecutionPlan


class ApprovalDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"
    MORE_INFO = "more_info"


@dataclass
class ApprovalRequest:
    """Request for human approval."""
    task_id: str
    stage_id: int
    skill_id: str
    skill_name: str
    trigger: str
    output_preview: str
    estimated_cost: float
    quality_score: Optional[float]


@dataclass
class ApprovalResponse:
    """Response from human approval."""
    decision: ApprovalDecision
    reason: str = ""
    edited_output: Optional[str] = None
    additional_context: str = ""


class HumanGate:
    """Manages human approval workflow."""

    def __init__(self):
        self.settings = get_settings()
        self.context = get_context_store()
        self._pending_approvals: dict[str, ApprovalRequest] = {}

    def request_approval(
        self,
        task_id: str,
        stage: ExecutionStage,
        output: RoleOutput,
        plan: ExecutionPlan
    ) -> ApprovalResponse:
        """Request human approval for a stage output."""

        # Determine trigger
        triggers = self._identify_triggers(stage, output)
        trigger = ", ".join(triggers) if triggers else "quality_gate"

        request = ApprovalRequest(
            task_id=task_id,
            stage_id=stage.stage_id,
            skill_id=stage.skill_id,
            skill_name=stage.skill_name,
            trigger=trigger,
            output_preview=output.output[:1000] + "..." if len(output.output) > 1000 else output.output,
            estimated_cost=output.cost_usd,
            quality_score=output.quality_score
        )

        # Store for UI/API
        self._pending_approvals[task_id] = request

        # If auto-approve disabled and no UI, return rejection with guidance
        if not self.settings.human_gate.enabled:
            return ApprovalResponse(
                decision=ApprovalDecision.REJECTED,
                reason="Human gate disabled - set AIL_HUMAN_GATE_ENABLED=true and run UI"
            )

        # For CLI mode, prompt user
        return self._cli_prompt(request)

    def _identify_triggers(self, stage: ExecutionStage, output: RoleOutput) -> list[str]:
        """Identify what triggered the approval request."""
        triggers = []
        skill_tags = set()  # Would get from skill

        if output.quality_score and output.quality_score < 8:
            triggers.append(f"quality_score_{output.quality_score}")

        if output.cost_usd > 5:
            triggers.append("high_cost")

        # Check for external actions in output
        external_keywords = ["send", "publish", "email", "post", "submit", "create", "delete"]
        output_lower = output.output.lower()
        for kw in external_keywords:
            if kw in output_lower:
                triggers.append(f"external_action_{kw}")
                break

        return triggers

    def _cli_prompt(self, request: ApprovalRequest) -> ApprovalResponse:
        """CLI-based approval prompt."""
        print(f"\n{'='*60}")
        print(f"HUMAN APPROVAL REQUIRED")
        print(f"{'='*60}")
        print(f"Task: {request.task_id}")
        print(f"Role: {request.skill_name} ({request.skill_id})")
        print(f"Trigger: {request.trigger}")
        print(f"Quality Score: {request.quality_score}/10")
        print(f"Est. Cost: ${request.estimated_cost:.4f}")
        print(f"\nOutput Preview:")
        print(f"{request.output_preview}")
        print(f"\nOptions: [a]pprove  [r]eject  [e]dit  [m]ore info")
        choice = input("Decision: ").strip().lower()

        if choice == "a":
            return ApprovalResponse(decision=ApprovalDecision.APPROVED)
        elif choice == "r":
            reason = input("Reason: ").strip()
            return ApprovalResponse(decision=ApprovalDecision.REJECTED, reason=reason)
        elif choice == "e":
            print("Enter edited output (end with Ctrl+D or '---END---'):")
            lines = []
            while True:
                try:
                    line = input()
                    if line == "---END---":
                        break
                    lines.append(line)
                except EOFError:
                    break
            return ApprovalResponse(
                decision=ApprovalDecision.EDITED,
                edited_output="\n".join(lines)
            )
        else:
            info = input("Additional context needed: ").strip()
            return ApprovalResponse(
                decision=ApprovalDecision.MORE_INFO,
                additional_context=info
            )

    def get_pending(self, task_id: str) -> Optional[ApprovalRequest]:
        """Get pending approval for task."""
        return self._pending_approvals.get(task_id)

    def resolve_via_api(self, task_id: str, response: ApprovalResponse) -> bool:
        """Resolve approval via API call."""
        if task_id in self._pending_approvals:
            del self._pending_approvals[task_id]
            return True
        return False

    def list_pending(self) -> list[ApprovalRequest]:
        """List all pending approvals."""
        return list(self._pending_approvals.values())