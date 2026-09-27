"""Cost Gate - budget enforcement and tracking."""

from dataclasses import dataclass
from typing import Optional

from agent_intelligence.core.config import get_settings
from agent_intelligence.core.context_store import get_context_store


@dataclass
class CostCheckResult:
    """Result of cost check."""
    allowed: bool
    current_spend: float
    projected_spend: float
    budget_limit: float
    remaining: float
    reason: str = ""


class CostGate:
    """Enforces budget limits per run and per role."""

    def __init__(self):
        self.settings = get_settings()
        self.context = get_context_store()
        self._run_budgets: dict[str, float] = {}

    def set_budget(self, run_id: str, budget_usd: float):
        """Set budget for a run."""
        self._run_budgets[run_id] = budget_usd

    def check(self, estimated_cost: float, current_spend: float, run_id: Optional[str] = None) -> CostCheckResult:
        """Check if estimated cost fits within budget."""
        budget = self.settings.default_budget_usd

        if run_id and run_id in self._run_budgets:
            budget = self._run_budgets[run_id]

        projected = current_spend + estimated_cost
        remaining = budget - projected

        if projected > budget:
            return CostCheckResult(
                allowed=False,
                current_spend=current_spend,
                projected_spend=projected,
                budget_limit=budget,
                remaining=remaining,
                reason=f"Projected spend ${projected:.2f} exceeds budget ${budget:.2f}"
            )

        # Warn at 80%
        if projected > budget * 0.8:
            return CostCheckResult(
                allowed=True,
                current_spend=current_spend,
                projected_spend=projected,
                budget_limit=budget,
                remaining=remaining,
                reason=f"Warning: {projected/budget*100:.0f}% of budget used"
            )

        return CostCheckResult(
            allowed=True,
            current_spend=current_spend,
            projected_spend=projected,
            budget_limit=budget,
            remaining=remaining
        )

    def check_role_budget(self, skill_id: str, estimated_cost: float) -> CostCheckResult:
        """Check if a single role's cost is reasonable."""
        # Default per-role limits
        role_limits = {
            "research": 2.0,
            "analysis": 1.5,
            "writing": 1.0,
            "planning": 1.5,
            "default": 3.0
        }

        # Determine role type from skill_id
        role_type = "default"
        for key in role_limits:
            if key in skill_id:
                role_type = key
                break

        limit = role_limits[role_type]
        if estimated_cost > limit:
            return CostCheckResult(
                allowed=False,
                current_spend=0,
                projected_spend=estimated_cost,
                budget_limit=limit,
                remaining=limit - estimated_cost,
                reason=f"Role {skill_id} estimated ${estimated_cost:.2f} exceeds {role_type} limit ${limit:.2f}"
            )

        return CostCheckResult(
            allowed=True,
            current_spend=0,
            projected_spend=estimated_cost,
            budget_limit=limit,
            remaining=limit - estimated_cost
        )

    def get_run_summary(self, run_id: str) -> dict:
        """Get cost summary for a run."""
        # Would query context store for actual costs
        return {
            "run_id": run_id,
            "budget": self._run_budgets.get(run_id, self.settings.default_budget_usd),
            "spent": 0.0,  # Would aggregate from role_outputs
            "remaining": self._run_budgets.get(run_id, self.settings.default_budget_usd)
        }