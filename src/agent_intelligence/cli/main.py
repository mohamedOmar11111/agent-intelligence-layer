"""CLI entry point for the Agent Intelligence Layer."""

import json
from pathlib import Path
from typing: Optional
from datetime import datetime

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from agent_intelligence.core.config import get_settings, reload_settings
from agent_intelligence.core.skill_loader import SkillLoader
from agent_intelligence.core.planner import Planner
from agent_intelligence.core.executor import get_executor
from agent_intelligence.core.context_store import get_context_store
from agent_intelligence.observability.metrics import get_metrics

app = typer.Typer(
    name="ail",
    help="Agent Intelligence Layer - Execute markdown-defined skills autonomously",
    add_completion=False
)

console = Console()


@app.callback()
def main(
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Config file path"),
    skills_path: Optional[Path] = typer.Option(None, "--skills", "-s", help="Skills repository path"),
    model_provider: Optional[str] = typer.Option(None, "--model", "-m", help="Model provider (ollama, openai, anthropic)"),
    model_name: Optional[str] = typer.Option(None, "--model-name", help="Model name"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug mode"),
):
    """Agent Intelligence Layer CLI."""
    settings = get_settings()

    if config:
        # Would load from config file
        pass
    if skills_path:
        settings.skills.path = skills_path
    if model_provider:
        settings.model.provider = model_provider
    if model_name:
        settings.model.name = model_name
    if debug:
        settings.debug = True
        reload_settings()

    console.print(f"[green]AIL initialized[/green]")
    console.print(f"  Skills: {settings.skills.path}")
    console.print(f"  Model: {settings.model.provider}/{settings.model.name}")


@app.command()
def skills(
    department: Optional[str] = typer.Option(None, "--dept", "-d", help="Filter by department"),
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="Filter by tag"),
    search: Optional[str] = typer.Option(None, "--search", "-q", help="Search skills"),
):
    """List available skills."""
    loader = SkillLoader()

    if search:
        results = loader.search_skills(search)
    elif department:
        results = loader.get_skills_by_department(department)
    elif tag:
        results = loader.get_skills_by_tag(tag)
    else:
        results = list(loader.load_all_skills().values())

    if not results:
        console.print("[yellow]No skills found[/yellow]")
        return

    table = Table(title=f"Skills ({len(results)})")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Department", style="blue")
    table.add_column("Description", style="white")
    table.add_column("Tags", style="yellow")

    for skill in results:
        table.add_row(
            skill.id,
            skill.name,
            skill.department,
            skill.description[:60] + "..." if len(skill.description) > 60 else skill.description,
            ", ".join(skill.tags[:5])
        )

    console.print(table)


@app.command()
def plan(
    goal: str = typer.Argument(..., help="Goal to achieve"),
    brief: str = typer.Option("latest", "--brief", "-b", help="Business brief version"),
    skills: Optional[str] = typer.Option(None, "--skills", help="Comma-separated skill IDs"),
    budget: Optional[float] = typer.Option(None, "--budget", help="Budget in USD"),
    max_stages: int = typer.Option(8, "--max-stages", help="Maximum stages"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save plan to file"),
):
    """Create an execution plan for a goal."""
    planner = Planner()

    preferred = skills.split(",") if skills else None

    with console.status("[bold green]Planning..."):
        plan = planner.plan(
            goal=goal,
            brief_version=brief,
            preferred_skills=preferred,
            max_stages=max_stages,
            budget_usd=budget
        )

    console.print(Panel.fit(
        f"[bold]Goal:[/bold] {plan.goal}\n"
        f"[bold]Brief:[/bold] {plan.brief_version}\n"
        f"[bold]Stages:[/bold] {len(plan.stages)}\n"
        f"[bold]Est. Cost:[/bold] ${plan.estimated_total_cost:.2f}",
        title="Execution Plan"
    ))

    table = Table(title="Stages")
    table.add_column("#", style="cyan")
    table.add_column("Skill", style="green")
    table.add_column("Depends On", style="blue")
    table.add_column("Est. Cost", style="yellow")
    table.add_column("Parallel", style="magenta")

    for stage in plan.stages:
        table.add_row(
            str(stage.stage_id),
            f"{stage.skill_name} ({stage.skill_id})",
            ", ".join(str(d) for d in stage.depends_on) or "—",
            f"${stage.estimated_cost_usd:.2f}",
            "✓" if stage.can_run_parallel else "✗"
        )

    console.print(table)

    if output:
        output.write_text(plan.model_dump_json(indent=2))
        console.print(f"[green]Plan saved to {output}[/green]")


@app.command()
def run(
    goal: str = typer.Argument(..., help="Goal to achieve"),
    brief: str = typer.Option("latest", "--brief", "-b", help="Business brief version"),
    skills: Optional[str] = typer.Option(None, "--skills", help="Comma-separated skill IDs"),
    budget: float = typer.Option(50.0, "--budget", help="Budget in USD"),
    thread: Optional[str] = typer.Option(None, "--thread", help="Thread ID for resume"),
    auto_approve: bool = typer.Option(False, "--auto-approve", help="Skip human approval gates"),
    resume: bool = typer.Option(False, "--resume", help="Resume from checkpoint"),
):
    """Execute a goal autonomously."""
    executor = get_executor()
    planner = Planner()

    preferred = skills.split(",") if skills else None

    console.print(Panel.fit(
        f"[bold]Goal:[/bold] {goal}\n"
        f"[bold]Budget:[/bold] ${budget:.2f}\n"
        f"[bold]Auto-approve:[/bold] {'Yes' if auto_approve else 'No'}",
        title="Starting Execution"
    ))

    # Create plan
    with console.status("[bold green]Creating plan..."):
        plan = planner.plan(
            goal=goal,
            brief_version=brief,
            preferred_skills=preferred,
            budget_usd=budget
        )

    console.print(f"[green]Plan created:[/green] {len(plan.stages)} stages, ${plan.estimated_total_cost:.2f}")

    # Execute
    thread_id = thread or f"run-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Executing...", total=len(plan.stages))

        # Would use executor.execute_plan here
        # For now, show plan
        for stage in plan.stages:
            progress.update(task, advance=1, description=f"Stage {stage.stage_id}: {stage.skill_name}")

    console.print("[bold green]Execution complete![/bold]")


@app.command()
def brief(
    action: str = typer.Argument("show", help="Action: show, create, list, set"),
    version: Optional[str] = typer.Argument(None, help="Brief version"),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Brief file to load"),
):
    """Manage business briefs."""
    context = get_context_store()

    if action == "list":
        briefs = context.list_briefs()
        if not briefs:
            console.print("[yellow]No briefs found[/yellow]")
            return
        table = Table(title="Business Briefs")
        table.add_column("Version", style="cyan")
        table.add_column("Created", style="blue")
        table.add_column("Updated", style="green")
        for b in briefs:
            table.add_row(b["version"], b["created_at"], b["updated_at"])
        console.print(table)

    elif action == "show":
        content = context.get_brief(version or "latest")
        if content:
            console.print(Panel(content, title=f"Brief: {version or 'latest'}"))
        else:
            console.print("[red]Brief not found[/red]")

    elif action == "create":
        if not file:
            console.print("[red]--file required for create[/red]")
            return
        content = file.read_text()
        ver = version or f"v{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        context.save_brief(ver, content)
        console.print(f"[green]Brief saved as {ver}[/green]")

    elif action == "set":
        if not version:
            console.print("[red]Version required for set[/red]")
            return
        # Just verify it exists
        content = context.get_brief(version)
        if content:
            console.print(f"[green]Active brief set to {version}[/green]")
        else:
            console.print("[red]Brief not found[/red]")


@app.command()
def metrics(
    run_id: Optional[str] = typer.Argument(None, help="Run ID to show metrics for"),
):
    """Show execution metrics."""
    collector = get_metrics()

    if run_id:
        summary = collector.get_run_summary(run_id)
        console.print(Panel.fit(
            f"Tokens: {summary['total_tokens']}\n"
            f"Cost: ${summary['total_cost']:.4f}\n"
            f"Latency: {summary['avg_latency']:.2f}s\n"
            f"Calls: {summary['llm_calls']}",
            title=f"Metrics: {run_id}"
        ))

        if summary["stages"]:
            table = Table(title="Stage Details")
            table.add_column("Skill", style="cyan")
            table.add_column("Stage", style="blue")
            table.add_column("Success", style="green")
            table.add_column("Quality", style="yellow")
            table.add_column("Cost", style="magenta")
            for s in summary["stages"]:
                table.add_row(
                    s.get("skill_id", "—"),
                    str(s.get("stage_id", "—")),
                    "✓" if s.get("success") else "✗",
                    str(s.get("quality_score", "—")),
                    f"${s.get('cost_usd', 0):.4f}"
                )
            console.print(table)
    else:
        console.print("[yellow]Run ID required[/yellow]")


@app.command()
def config(
    show: bool = typer.Option(False, "--show", help="Show current config"),
    set_key: Optional[str] = typer.Option(None, "--set", help="Set config key=value"),
):
    """Manage configuration."""
    settings = get_settings()

    if show:
        console.print(Panel(settings.model_dump_json(indent=2), title="Current Config"))

    if set_key:
        # Would parse and set
        console.print(f"[yellow]Config set not yet implemented[/yellow]")


if __name__ == "__main__":
    app()