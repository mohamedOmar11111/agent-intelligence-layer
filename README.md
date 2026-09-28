# Agent Intelligence Layer

> **Model-agnostic agent operating system** that loads skills from markdown repositories and executes them with planning, memory, eval gates, and human approval.

## Overview

The Agent Intelligence Layer (AIL) sits **above any LLM** and turns your markdown-defined skills into an autonomous, observable, and controllable agent team.

```
┌─────────────────────────────────────────────────────────────┐
│  YOUR SKILLS REPO (growth-architect-store)                  │
│  → 52+ role definitions (prompts + I/O schemas + acceptance)│
└─────────────────────────┬───────────────────────────────────┘
                          │ loads skills
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  AGENT INTELLIGENCE LAYER (this repo)                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐     │
│  │ Skill    │ │ Planner  │ │ Executor │ │ Context    │     │
│  │ Loader   │ │(Coordinator)│ │(LangGraph)│ │ Store      │     │
│  └──────────┘ └──────────┘ └──────────┘ └────────────┘     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐     │
│  │ Eval     │ │ Human    │ │ Cost     │ │ Metrics/   │     │
│  │ Gates    │ │ Gate     │ │ Gate     │ │ Logging    │     │
│  └──────────┘ └──────────┘ └──────────┘ └────────────┘     │
└─────────────────────────┬───────────────────────────────────┘
                          │ model-agnostic
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  ANY LLM BACKEND                                             │
│  Ollama (local) │ OpenAI │ Anthropic │ Azure │ Bedrock     │
└─────────────────────────────────────────────────────────────┘
```

## Features

- **📂 Skill Loader** — Discovers and parses skills from markdown files with frontmatter
- **🧠 Planner** — Uses coordinator logic to convert goals into minimal execution plans
- **⚡ Executor** — LangGraph runtime with checkpointing, retries, and parallel execution
- **💾 Context Store** — SQLite + ChromaDB for briefs, outputs, handoffs, and semantic search
- **✅ Eval Gates** — Automated rubric evaluation (evidence, completeness, accuracy, relevance, handoff)
- **👤 Human Gates** — Approval workflow for spend, external actions, quality thresholds
- **💰 Cost Gates** — Per-run and per-role budget enforcement
- **📊 Observability** — Structured logging, metrics, cost tracking, quality scores
- **🔌 MCP Ready** — Tool registry for stdio MCP servers
- **🔄 Model Agnostic** — Swap Ollama ↔ OpenAI ↔ Anthropic via config

## Quick Start

```bash
# 1. Install
pip install -e ".[ui]"

# 2. Configure your LLM (any provider via LiteLLM)
# Ollama (local, free):    ail config set model.provider ollama && ail config set model.name qwen2.5:7b
# OpenAI:                  ail config set model.provider openai && ail config set model.name gpt-4o
# Anthropic:               ail config set model.provider anthropic && ail config set model.name claude-3-5-sonnet
# Azure/OpenAI-compatible: ail config set model.provider litellm && ail config set model.name <your-model>

# 3. Point to your skills repo
ail config set skills.path ../growth-architect-store

# 4. Create a business brief
ail brief create --file briefs/my-business.yaml --version v1.0

# 5. Run a goal
ail run "Build Q4 outbound campaign for ICP: B2B SaaS" --budget 50 --brief v1.0
```

> **Use any LLM backend** — Configure once, works with any coding agent (Cursor, Windsurf, VS Code, CLI, etc.)

## CLI Commands

| Command | Description |
|---------|-------------|
| `ail skills` | List/search skills |
| `ail plan` | Create execution plan |
| `ail run` | Execute goal autonomously |
| `ail brief` | Manage business briefs |
| `ail metrics` | View execution metrics |
| `ail config` | View/modify configuration |

## Architecture

```
src/agent_intelligence/
├── core/
│   ├── config.py          # Pydantic settings
│   ├── skill_loader.py    # Markdown skill parser
│   ├── context_store.py   # SQLite + ChromaDB
│   ├── model_adapter.py   # LiteLLM unified interface
│   ├── planner.py         # Coordinator → execution plan
│   └── executor.py        # LangGraph runtime
├── gates/
│   ├── eval_gate.py       # Rubric evaluation
│   ├── human_gate.py      # Approval workflow
│   └── cost_gate.py       # Budget enforcement
├── observability/
│   ├── metrics.py         # SQLite metrics collector
│   └── logging.py         # Structured logging
├── cli/
│   └── main.py            # Typer CLI
├── skills/
│   └── schema.py          # Pydantic skill schemas
└── examples/
    └── marketing_campaign.py  # M01→M11 vertical
```

## Skills Repository Structure

AIL reads skills from a repository with this structure:

```
skills-repo/
├── departments/
│   ├── marketing/
│   │   ├── skills/
│   │   │   ├── m01-head-of-marketing.md
│   │   │   └── ...
│   │   └── README.md
│   └── ...
└── templates/
    ├── skill-template.md
    └── department-readme-template.md
```

Each skill markdown file has frontmatter:

```markdown
---
name: "M01 Head of Marketing"
department: "marketing"
description: "Priorities connected to commercial goals"
install_url: "https://github.com/..."
tags: ["strategy", "planning", "priorities"]
verified: true
added_date: "2026-09-27"
---

# M01 Head of Marketing

**Speciality:** Priorities connected to commercial goals.

**Inputs:**
- Business goal
- ICP
- Offer
- Funnel baseline
- Channel history
- Budget
- Capacity
- Sales feedback

**Prompt:** Act as our Head of Marketing...

**Acceptance Check:**
- Priorities address diagnosed constraint
- Fit budget and capacity

**Handoff:**
- Send plan to M05 and M20
- Send financial inputs to F07
```

## Configuration

Create `.env` file:

```env
# Model (choose one)
# Ollama (local)
AIL_MODEL_PROVIDER=ollama
AIL_MODEL_NAME=qwen2.5:7b
# OpenAI
# AIL_MODEL_PROVIDER=openai
# AIL_MODEL_NAME=gpt-4o
# AIL_MODEL_API_KEY=sk-...
# Anthropic
# AIL_MODEL_PROVIDER=anthropic
# AIL_MODEL_NAME=claude-3-5-sonnet-20241022
# AIL_MODEL_API_KEY=sk-ant-...
# Any OpenAI-compatible (vLLM, LM Studio, etc.)
# AIL_MODEL_PROVIDER=litellm
# AIL_MODEL_NAME=your-model
# AIL_MODEL_BASE_URL=http://localhost:8000/v1

AIL_MODEL_TEMPERATURE=0.1

# Skills
AIL_SKILLS_PATH=../growth-architect-store

# Memory
AIL_MEMORY_SQLITE_PATH=./data/agent_intelligence.db
AIL_MEMORY_CHROMA_PATH=./data/chroma

# Human Gate
AIL_HUMAN_GATE_ENABLED=true
AIL_HUMAN_GATE_API_PORT=8080
AIL_HUMAN_GATE_UI_PORT=8501

# Observability
AIL_OBS_LOG_LEVEL=INFO
AIL_OBS_LANGFUSE_ENABLED=false
```

**Works with any coding agent** — Cursor, Windsurf, VS Code, Zed, CLI, or custom scripts

## Running the Marketing Vertical

```bash
# Run the example
python examples/marketing_campaign.py

# Or via CLI
ail run "Build Q4 marketing campaign for B2B SaaS targeting 500 signups" \
  --brief marketing-q4-2026 \
  --budget 15000 \
  --skills m01-head-of-marketing,m02-customer-researcher,m03-positioning-strategist,m04-offer-designer,m05-campaign-manager,m06-content-strategist,m07-marketing-copywriter,m11-landing-page-writer
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check .
mypy src/

# Works with any coding agent — Cursor, Windsurf, VS Code, Zed, CLI
```

## License

MIT