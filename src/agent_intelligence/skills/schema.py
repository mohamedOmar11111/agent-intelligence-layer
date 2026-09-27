"""Skill schema definitions - matches the markdown frontmatter in skills repos."""

from typing import Literal, Optional
from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime
from enum import Enum


class Department(str, Enum):
    """Known departments in the skills repository."""
    DEVELOPERS = "developers"
    DESIGNERS = "designers"
    MARKETING = "marketing"
    SOCIAL_MEDIA = "social-media"
    FINANCE = "finance"
    SMALL_BUSINESS = "small-business"
    LEGAL = "legal"
    GPT6_ASTRA_BUSINESS_TEAM = "gpt6-astra-business-team"


class SkillFrontmatter(BaseModel):
    """Frontmatter from skill markdown files."""
    name: str
    department: str
    description: str
    install_url: HttpUrl
    tags: list[str] = []
    verified: bool = True
    added_date: str  # YYYY-MM-DD


class SkillInput(BaseModel):
    """Input specification for a skill."""
    name: str
    description: str
    required: bool = True
    type: str = "string"
    example: Optional[str] = None


class SkillOutput(BaseModel):
    """Output specification for a skill."""
    name: str
    description: str
    type: str = "string"
    format: Optional[str] = None


class AcceptanceCheck(BaseModel):
    """Acceptance criteria for a skill."""
    criteria: list[str]
    blocker_conditions: list[str] = []


class HandoffSpec(BaseModel):
    """Handoff specification to next role."""
    next_roles: list[str] = []
    required_output: list[str] = []
    context_preserved: list[str] = []


class StarterCommand(BaseModel):
    """Starter command for quick testing."""
    command: str
    description: Optional[str] = None


class Skill(BaseModel):
    """Complete skill definition loaded from markdown."""
    # Identity
    id: str  # e.g., "m02-customer-researcher"
    name: str
    department: str
    file_path: str

    # Metadata
    description: str
    install_url: str
    tags: list[str] = []
    verified: bool = True
    added_date: str

    # Execution
    prompt: str
    inputs: list[SkillInput] = []
    outputs: list[SkillOutput] = []
    acceptance_check: Optional[AcceptanceCheck] = None
    handoff: Optional[HandoffSpec] = None
    starter_commands: list[StarterCommand] = []

    # Runtime
    model_preference: Optional[str] = None
    tool_requirements: list[str] = []
    estimated_cost_usd: float = 0.0
    timeout_seconds: int = 120

    # Source
    source: str = ""
    source_repo: str = ""


class ExecutionPlan(BaseModel):
    """Plan for executing a sequence of skills."""
    goal: str
    brief_version: str
    stages: list["ExecutionStage"]
    estimated_total_cost: float = 0.0
    required_approvals: list[str] = []


class ExecutionStage(BaseModel):
    """Single stage in an execution plan."""
    stage_id: int
    skill_id: str
    skill_name: str
    inputs: dict = {}
    depends_on: list[int] = []  # Stage IDs this depends on
    acceptance_criteria: list[str] = []
    required_tools: list[str] = []
    estimated_cost_usd: float = 0.0
    timeout_seconds: int = 120
    can_run_parallel: bool = False


class TaskBrief(BaseModel):
    """Task brief - defines the specific job for a role."""
    task_id: str
    role: str  # skill_id
    decision_or_outcome: str
    inputs: dict = {}
    scope: dict = {}
    required_output: dict = {}
    success_criteria: list[str] = []
    constraints: dict = {}
    decision_owner: str = ""
    next_recipient: str = ""
    business_brief_version: str = ""


class RoleOutput(BaseModel):
    """Output from a role execution."""
    task_id: str
    skill_id: str
    skill_name: str
    output: str
    evidence: list[dict] = []
    assumptions: list[str] = []
    gaps: list[str] = []
    quality_score: Optional[float] = None
    quality_details: dict = {}
    handoff: Optional[dict] = None
    tokens_used: int = 0
    cost_usd: float = 0.0
    latency_seconds: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    brief_version: str = ""


class HandoffRecord(BaseModel):
    """Handoff record between roles."""
    task_id: str
    from_role: str
    to_role: str
    approved_output: str
    output_version: str
    source_references: list[str] = []
    reliable_facts: list[dict] = []
    assumptions: list[str] = []
    unresolved_items: list[str] = []
    decision_required: str = ""
    decision_owner: str = ""
    next_action: str = ""
    deadline: Optional[str] = None
    brief_version: str = ""


# Forward references
ExecutionPlan.model_rebuild()
ExecutionStage.model_rebuild()