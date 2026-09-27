"""Skill loader - discovers and parses skills from markdown repositories."""

import re
import yaml
from pathlib import Path
from typing import Optional
from datetime import datetime

from agent_intelligence.core.config import get_settings
from agent_intelligence.skills.schema import (
    Skill, SkillInput, SkillOutput, AcceptanceCheck,
    HandoffSpec, StarterCommand, Department
)


class SkillLoader:
    """Loads skills from markdown files in the skills repository."""

    def __init__(self, skills_path: Optional[Path] = None):
        self.settings = get_settings()
        self.skills_path = skills_path or self.settings.skills.path
        self._skill_cache: dict[str, Skill] = {}
        self._last_loaded: Optional[datetime] = None

    def load_all_skills(self, force_reload: bool = False) -> dict[str, Skill]:
        """Load all skills from the repository."""
        if not force_reload and self._skill_cache and self.settings.skills.auto_reload:
            return self._skill_cache

        self._skill_cache = {}
        departments = self.settings.skills.departments

        for dept in departments:
            dept_path = self.skills_path / "departments" / dept / "skills"
            if dept_path.exists():
                for skill_file in dept_path.glob("*.md"):
                    try:
                        skill = self._parse_skill_file(skill_file, dept)
                        if skill:
                            self._skill_cache[skill.id] = skill
                    except Exception as e:
                        print(f"Warning: Failed to load {skill_file}: {e}")

        self._last_loaded = datetime.utcnow()
        return self._skill_cache

    def get_skill(self, skill_id: str) -> Optional[Skill]:
        """Get a specific skill by ID."""
        if not self._skill_cache:
            self.load_all_skills()
        return self._skill_cache.get(skill_id)

    def get_skills_by_department(self, department: str) -> list[Skill]:
        """Get all skills in a department."""
        if not self._skill_cache:
            self.load_all_skills()
        return [s for s in self._skill_cache.values() if s.department == department]

    def get_skills_by_tag(self, tag: str) -> list[Skill]:
        """Get all skills with a specific tag."""
        if not self._skill_cache:
            self.load_all_skills()
        return [s for s in self._skill_cache.values() if tag in s.tags]

    def search_skills(self, query: str) -> list[Skill]:
        """Search skills by name, description, or tags."""
        if not self._skill_cache:
            self.load_all_skills()
        query_lower = query.lower()
        return [
            s for s in self._skill_cache.values()
            if query_lower in s.name.lower()
            or query_lower in s.description.lower()
            or any(query_lower in t.lower() for t in s.tags)
        ]

    def _parse_skill_file(self, file_path: Path, department: str) -> Optional[Skill]:
        """Parse a single skill markdown file."""
        content = file_path.read_text(encoding="utf-8")

        # Extract frontmatter
        frontmatter_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if not frontmatter_match:
            return None

        frontmatter = yaml.safe_load(frontmatter_match.group(1))
        if not frontmatter:
            return None

        # Extract prompt (content after frontmatter)
        prompt = content[frontmatter_match.end():].strip()

        # Parse sections from prompt
        inputs = self._extract_inputs(prompt)
        outputs = self._extract_outputs(prompt)
        acceptance = self._extract_acceptance(prompt)
        handoff = self._extract_handoff(prompt)
        starters = self._extract_starters(prompt)

        # Generate skill ID from filename
        skill_id = file_path.stem.lower().replace("_", "-")

        return Skill(
            id=skill_id,
            name=frontmatter.get("name", skill_id),
            department=department,
            file_path=str(file_path),
            description=frontmatter.get("description", ""),
            install_url=frontmatter.get("install_url", ""),
            tags=frontmatter.get("tags", []),
            verified=frontmatter.get("verified", True),
            added_date=frontmatter.get("added_date", ""),
            prompt=prompt,
            inputs=inputs,
            outputs=outputs,
            acceptance_check=acceptance,
            handoff=handoff,
            starter_commands=starters,
            source=f"Loaded from {file_path}",
            source_repo="growth-architect-store",
        )

    def _extract_inputs(self, content: str) -> list[SkillInput]:
        """Extract inputs from prompt content."""
        inputs = []
        # Look for "Inputs:" or "## Inputs" section
        patterns = [
            r"(?:##?\s*)?Inputs?:?\n(.*?)(?:\n##|\n\w+:|\Z)",
            r"(?:##?\s*)?Required Inputs?:?\n(.*?)(?:\n##|\n\w+:|\Z)",
        ]
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
            if match:
                lines = match.group(1).strip().split("\n")
                for line in lines:
                    line = line.strip("- •*").strip()
                    if line and ":" in line:
                        name, desc = line.split(":", 1)
                        inputs.append(SkillInput(
                            name=name.strip(),
                            description=desc.strip(),
                            required=True,
                        ))
                break
        return inputs

    def _extract_outputs(self, content: str) -> list[SkillOutput]:
        """Extract outputs from prompt content."""
        outputs = []
        patterns = [
            r"(?:##?\s*)?Outputs?:?\n(.*?)(?:\n##|\n\w+:|\Z)",
            r"(?:##?\s*)?Returns?:?\n(.*?)(?:\n##|\n\w+:|\Z)",
            r"(?:##?\s*)?Deliverables?:?\n(.*?)(?:\n##|\n\w+:|\Z)",
        ]
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
            if match:
                lines = match.group(1).strip().split("\n")
                for line in lines:
                    line = line.strip("- •*").strip()
                    if line:
                        outputs.append(SkillOutput(
                            name="output",
                            description=line,
                            type="string",
                        ))
                break
        return outputs

    def _extract_acceptance(self, content: str) -> Optional[AcceptanceCheck]:
        """Extract acceptance criteria from prompt."""
        patterns = [
            r"(?:##?\s*)?Acceptance\s*Check:?\n(.*?)(?:\n##|\n\w+:|\Z)",
            r"(?:##?\s*)?Acceptance\s*Criteria:?\n(.*?)(?:\n##|\n\w+:|\Z)",
        ]
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
            if match:
                lines = match.group(1).strip().split("\n")
                criteria = [line.strip("- •*").strip() for line in lines if line.strip()]
                if criteria:
                    return AcceptanceCheck(criteria=criteria)
        return None

    def _extract_handoff(self, content: str) -> Optional[HandoffSpec]:
        """Extract handoff specification from prompt."""
        patterns = [
            r"(?:##?\s*)?Handoff:?\n(.*?)(?:\n##|\n\w+:|\Z)",
            r"(?:##?\s*)?Next\s*Steps?:?\n(.*?)(?:\n##|\n\w+:|\Z)",
        ]
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
            if match:
                lines = match.group(1).strip().split("\n")
                next_roles = []
                for line in lines:
                    line = line.strip("- •*").strip()
                    # Look for role references like S01, M02, etc.
                    role_matches = re.findall(r'\b([A-Z]\d{1,2})\b', line)
                    next_roles.extend(role_matches)
                if next_roles:
                    return HandoffSpec(next_roles=list(set(next_roles)))
        return None

    def _extract_starters(self, content: str) -> list[StarterCommand]:
        """Extract starter commands from prompt."""
        starters = []
        patterns = [
            r"(?:##?\s*)?Starter\s*Commands?:?\n(.*?)(?:\n##|\n\w+:|\Z)",
            r"(?:##?\s*)?Quick\s*Start:?\n(.*?)(?:\n##|\n\w+:|\Z)",
        ]
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
            if match:
                lines = match.group(1).strip().split("\n")
                for line in lines:
                    line = line.strip("- •*").strip()
                    if line:
                        starters.append(StarterCommand(command=line))
                break
        return starters


# Convenience function
def load_skills(skills_path: Optional[Path] = None) -> dict[str, Skill]:
    """Load all skills from the repository."""
    loader = SkillLoader(skills_path)
    return loader.load_all_skills()