"""Eval Gate - automated quality evaluation using the rubric."""

import re
from dataclasses import dataclass
from typing import Optional

from agent_intelligence.core.model_adapter import get_model_adapter
from agent_intelligence.skills.schema import RoleOutput, Skill, AcceptanceCheck


EVAL_PROMPT = """You are a quality reviewer. Evaluate the role output against the task requirements and rubric.

ROLE: {skill_name}
TASK: {task_outcome}

RUBRIC (score each 0-2):
1. EVIDENCE: Material claims traceable to sources (2) | Some gaps (1) | Unsupported (0)
2. COMPLETENESS: Required output complete (2) | Useful but unfinished (1) | Core missing (0)
3. ACCURACY: Checked and consistent (2) | Minor corrections (1) | Material errors (0)
4. RELEVANCE: Fits actual task (2) | Partly tailored (1) | Wrong context (0)
5. HANDOFF: Owner/input/decision clear (2) | Unclear (1) | No usable next step (0)

RELEASE BLOCKERS (auto-fail if present):
- Fabricated claim (invented research, quotes, metrics, financials)
- Material arithmetic error (calculation error changing decision)
- Unsupported commitment (promise not in approved claims)
- Wrong customer context (wrong audience, problem, geography)

ACCEPTANCE CRITERIA:
{acceptance_criteria}

OUTPUT TO EVALUATE:
{output}

Return ONLY valid JSON:
{{
  "scores": {{"evidence": 2, "completeness": 2, "accuracy": 2, "relevance": 2, "handoff": 2}},
  "total": 10,
  "passed": true,
  "blockers": [],
  "feedback": "Specific issues to fix",
  "details": {{}}
}}"""


@dataclass
class EvalResult:
    """Result of evaluation."""
    score: float
    passed: bool
    blockers: list[str]
    feedback: str
    details: dict
    scores: dict


class EvalGate:
    """Automated evaluation gate using rubric."""

    def __init__(self):
        self.model = get_model_adapter()

    def evaluate(
        self,
        output: RoleOutput,
        acceptance_criteria: list[str],
        skill: Optional[Skill] = None
    ) -> EvalResult:
        """Evaluate output against rubric and acceptance criteria."""

        # Quick programmatic checks first
        blockers = self._check_blockers(output)
        if blockers:
            return EvalResult(
                score=0,
                passed=False,
                blockers=blockers,
                feedback="Release blockers detected",
                details={"blockers": blockers},
                scores={}
            )

        # Quick acceptance checks
        quick_fail = self._check_acceptance(output, acceptance_criteria)
        if quick_fail:
            return EvalResult(
                score=5,
                passed=False,
                blockers=[],
                feedback=quick_fail,
                details={"acceptance_failed": quick_fail},
                scores={}
            )

        # Full LLM evaluation for nuanced scoring
        eval_result = self._llm_evaluate(output, acceptance_criteria, skill)

        return eval_result

    def _check_blockers(self, output: RoleOutput) -> list[str]:
        """Check for release blockers programmatically."""
        blockers = []

        # Check for fabricated numbers (unverified specific metrics)
        numbers = re.findall(r'\b\d+(?:\.\d+)?%?\b', output.output)
        for num in numbers:
            # If specific metric without evidence reference
            if any(kw in output.output.lower() for kw in ["revenue", "conversion", "roi", "cost", "price"]):
                if not output.evidence:
                    blockers.append(f"Unverified metric: {num}")

        # Check for unsupported commitments
        commitment_words = ["guarantee", "promise", "will deliver", "ensure", "commit to"]
        for word in commitment_words:
            if word in output.output.lower():
                if not any(word in str(e).lower() for e in output.evidence):
                    blockers.append(f"Unsupported commitment: '{word}'")

        return blockers

    def _check_acceptance(self, output: RoleOutput, criteria: list[str]) -> Optional[str]:
        """Quick acceptance criteria check."""
        if not criteria:
            return None

        output_lower = output.output.lower()
        for criterion in criteria:
            # Simple keyword presence check
            key_terms = re.findall(r'\b\w{4,}\b', criterion.lower())
            if key_terms:
                found = any(term in output_lower for term in key_terms[:3])
                if not found:
                    return f"Missing acceptance criterion: {criterion[:80]}"
        return None

    def _llm_evaluate(
        self,
        output: RoleOutput,
        acceptance_criteria: list[str],
        skill: Optional[Skill]
    ) -> EvalResult:
        """Full LLM-based evaluation."""
        prompt = EVAL_PROMPT.format(
            skill_name=skill.name if skill else "Unknown",
            task_outcome=output.output[:200] + "...",
            acceptance_criteria="\n".join(f"- {c}" for c in acceptance_criteria),
            output=output.output[:4000]
        )

        messages = [
            {"role": "system", "content": "You are a strict quality reviewer. Output only valid JSON."},
            {"role": "user", "content": prompt}
        ]

        try:
            response = self.model.complete(messages)
            import json
            result = json.loads(response.content)

            scores = result.get("scores", {})
            total = sum(scores.values()) if scores else 0
            passed = result.get("passed", False) and total >= 8 and not result.get("blockers")

            return EvalResult(
                score=total,
                passed=passed,
                blockers=result.get("blockers", []),
                feedback=result.get("feedback", ""),
                details=result.get("details", {}),
                scores=scores
            )
        except Exception as e:
            # Fallback: basic scoring
            return EvalResult(
                score=7,
                passed=False,
                blockers=[],
                feedback=f"Evaluation error: {e}",
                details={"error": str(e)},
                scores={"evidence": 1, "completeness": 2, "accuracy": 2, "relevance": 1, "handoff": 1}
            )


def evaluate_output(
    output: RoleOutput,
    acceptance_criteria: list[str],
    skill: Optional[Skill] = None
) -> EvalResult:
    """Convenience function for evaluation."""
    gate = EvalGate()
    return gate.evaluate(output, acceptance_criteria, skill)