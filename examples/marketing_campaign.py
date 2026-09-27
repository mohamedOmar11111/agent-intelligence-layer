#!/usr/bin/env python
"""
Marketing Campaign Vertical - End-to-end example.

Runs: M01 → M02 → M03 → M04 → M05 → M06 → M07 → M11
Goal: Build a complete marketing campaign for a B2B SaaS product
"""

import asyncio
from pathlib import Path

from agent_intelligence.core.config import get_settings
from agent_intelligence.core.skill_loader import SkillLoader
from agent_intelligence.core.planner import Planner
from agent_intelligence.core.executor import get_executor
from agent_intelligence.core.context_store import get_context_store
from agent_intelligence.observability.metrics import get_metrics


# Sample business brief for a B2B SaaS company
SAMPLE_BRIEF = """
Business and website: Acme Analytics - acmeanalytics.io
What we sell: B2B SaaS analytics platform, $299/mo per seat, annual billing, 14-day trial
Who we serve: Product managers at B2B SaaS companies (50-500 employees), North America, Europe
Customer problem: PMs waste 10+ hours/week manually pulling data from Mixpanel, Amplitude, GA4 to build reports. They want automated insights.
Why buyers choose us: One-click integration with 12 analytics tools, AI-generated insights, Slack/Email delivery, SOC2 Type II
Current objective: Launch Q4 campaign targeting 500 qualified signups by Dec 31, 2026
Baseline: 50 signups/month from organic, 20 from paid, 30% trial-to-paid
Capacity: 1 marketer (20 hrs/week), 1 designer (10 hrs/week), $5k/mo budget
Budget: $15k total for Q4 campaign
Brand voice: Direct, data-driven, helpful. Avoid: hype, vague promises, jargon
Approved claims: "10+ hours saved/week", "12 integrations", "SOC2 Type II", "30% faster reporting"
Systems and data: HubSpot CRM, Google Analytics, Mixpanel, Customer.io, Notion
Permissions: Read CRM/analytics, draft content, publish to blog/social, send emails (with approval)
Financial context: US entity, USD, accrual accounting
Working conventions: EST, ISO 8601 dates, English
Decision owner: Sarah Chen, Head of Marketing
Material constraints: No customer data in prompts, legal review for claims, GDPR compliance
Brief version and date: v1.0, 2026-09-27
"""


async def run_marketing_campaign():
    """Run the complete marketing campaign vertical."""

    print("=" * 60)
    print("MARKETING CAMPAIGN VERTICAL")
    print("=" * 60)

    # Initialize
    settings = get_settings()
    context = get_context_store()

    # Save brief
    brief_version = "marketing-q4-2026"
    context.save_brief(brief_version, SAMPLE_BRIEF)
    print(f"✓ Business brief saved: {brief_version}")

    # Load skills
    loader = SkillLoader()
    skills = loader.load_all_skills()
    marketing_skills = {k: v for k, v in skills.items() if v.department == "marketing"}
    print(f"✓ Loaded {len(marketing_skills)} marketing skills")

    # Define the vertical sequence
    vertical_skills = [
        "m01-head-of-marketing",      # Strategy & priorities
        "m02-customer-researcher",    # Voice of customer
        "m03-positioning-strategist", # Positioning
        "m04-offer-designer",         # Offer packaging
        "m05-campaign-manager",       # Campaign coordination
        "m06-content-strategist",     # Content plan
        "m07-marketing-copywriter",   # Copywriting
        "m11-landing-page-writer",    # Landing page
    ]

    # Verify all skills exist
    for sid in vertical_skills:
        if sid not in skills:
            print(f"⚠ Skill not found: {sid}")
        else:
            print(f"  • {skills[sid].name}")

    # Create planner
    planner = Planner()

    # Goal
    goal = "Build and launch Q4 marketing campaign for Acme Analytics targeting 500 qualified signups"

    # Create plan
    print("\n📋 Creating execution plan...")
    plan = planner.plan(
        goal=goal,
        brief_version=brief_version,
        preferred_skills=vertical_skills,
        budget_usd=15000
    )

    print(f"Plan created: {len(plan.stages)} stages, ${plan.estimated_total_cost:.2f}")
    for stage in plan.stages:
        print(f"  {stage.stage_id}: {stage.skill_name} (${stage.estimated_cost_usd:.2f})")

    # Execute (showing what would happen)
    print("\n🚀 Executing campaign vertical...")
    print("-" * 40)

    executor = get_executor()

    # For demo, we'll show the sequence without actual LLM calls
    # In production, this would call executor.execute_plan(plan)

    stage_outputs = {}

    for stage in plan.stages:
        skill = skills.get(stage.skill_id)
        if not skill:
            print(f"  ⚠ Skipping {stage.skill_id} - not found")
            continue

        print(f"\n  Stage {stage.stage_id}: {skill.name}")
        print(f"    Inputs: {list(stage.inputs.keys())}")
        print(f"    Depends on: {stage.depends_on}")
        print(f"    Acceptance: {stage.acceptance_criteria[:2]}...")

        # Simulate execution
        task_brief = planner.create_task_brief(plan, stage, stage_outputs)

        # In real execution:
        # response = model.complete(messages, skill=skill)
        # output = RoleOutput(...)
        # eval_result = eval_gate.evaluate(output, stage.acceptance_criteria, skill)
        # if human_gate_needed: approval = human_gate.request_approval(...)

        # Simulate output for next stage
        stage_outputs[stage.skill_id] = f"[OUTPUT from {skill.name}]"

    print("\n" + "=" * 60)
    print("CAMPAIGN VERTICAL COMPLETE")
    print("=" * 60)
    print("\nDeliverables produced:")
    print("  1. Marketing Plan (M01) - Priorities, budget allocation, measurement framework")
    print("  2. Customer Research (M02) - Themes table with verbatim quotes")
    print("  3. Positioning (M03) - Message hierarchy, competitive comparison")
    print("  4. Offer Spec (M04) - Outcome, deliverables, pricing, economics model")
    print("  5. Campaign Brief (M05) - Tracker, risk register, measurement plan")
    print("  6. Content Calendar (M06) - Topic-to-journey map, production briefs")
    print("  7. Campaign Copy (M07) - Drafts with claim check table")
    print("  8. Landing Page (M11) - Page draft, build brief, tracking requirements")

    # Show metrics
    metrics = get_metrics()
    # Would show actual metrics after execution

    return plan


def main():
    """Main entry point."""
    asyncio.run(run_marketing_campaign())


if __name__ == "__main__":
    main()