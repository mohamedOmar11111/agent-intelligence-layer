"""Context store - persistent memory for briefs, outputs, handoffs, evidence."""

import sqlite3
import json
import uuid
from pathlib import Path
from typing import Optional
from datetime import datetime
from contextlib import contextmanager

import chromadb
from chromadb.config import Settings as ChromaSettings

from agent_intelligence.core.config import get_settings
from agent_intelligence.skills.schema import RoleOutput, HandoffRecord, TaskBrief


class ContextStore:
    """Persistent context store using SQLite + ChromaDB."""

    def __init__(self):
        self.settings = get_settings()
        self.db_path = self.settings.memory.sqlite_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_sqlite()
        self._init_chroma()

    def _init_sqlite(self):
        """Initialize SQLite tables."""
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS business_briefs (
                    id TEXT PRIMARY KEY,
                    version TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS task_briefs (
                    task_id TEXT PRIMARY KEY,
                    role TEXT NOT NULL,
                    brief_json TEXT NOT NULL,
                    brief_version TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS role_outputs (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    skill_id TEXT NOT NULL,
                    skill_name TEXT NOT NULL,
                    output TEXT NOT NULL,
                    evidence_json TEXT,
                    assumptions_json TEXT,
                    gaps_json TEXT,
                    quality_score REAL,
                    quality_details_json TEXT,
                    handoff_json TEXT,
                    tokens_used INTEGER DEFAULT 0,
                    cost_usd REAL DEFAULT 0.0,
                    latency_seconds REAL DEFAULT 0.0,
                    brief_version TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (task_id) REFERENCES task_briefs(task_id)
                );

                CREATE TABLE IF NOT EXISTS handoffs (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    from_role TEXT NOT NULL,
                    to_role TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS execution_runs (
                    run_id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    brief_version TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    status TEXT DEFAULT 'running',
                    total_cost_usd REAL DEFAULT 0.0,
                    total_tokens INTEGER DEFAULT 0,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_outputs_task ON role_outputs(task_id);
                CREATE INDEX IF NOT EXISTS idx_outputs_skill ON role_outputs(skill_id);
                CREATE INDEX IF NOT EXISTS idx_handoffs_task ON handoffs(task_id);
            """)

    def _init_chroma(self):
        """Initialize ChromaDB for vector search."""
        self.chroma_client = chromadb.PersistentClient(
            path=str(self.settings.memory.chroma_path),
            settings=ChromaSettings(anonymized_telemetry=False)
        )
        self.collection = self.chroma_client.get_or_create_collection(
            name=self.settings.memory.chroma_collection,
            metadata={"hnsw:space": "cosine"}
        )

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # Business Briefs
    def save_brief(self, version: str, content: str) -> str:
        """Save or update business brief."""
        brief_id = f"brief-{version}"
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO business_briefs (id, version, content, updated_at)
                VALUES (?, ?, ?, ?)
            """, (brief_id, version, content, datetime.utcnow().isoformat()))
        return brief_id

    def get_brief(self, version: str = "latest") -> Optional[str]:
        """Get business brief by version."""
        with self._conn() as conn:
            if version == "latest":
                row = conn.execute("""
                    SELECT content FROM business_briefs
                    ORDER BY updated_at DESC LIMIT 1
                """).fetchone()
            else:
                row = conn.execute("""
                    SELECT content FROM business_briefs WHERE version = ?
                """, (version,)).fetchone()
            return row["content"] if row else None

    def list_briefs(self) -> list[dict]:
        """List all brief versions."""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT version, created_at, updated_at FROM business_briefs
                ORDER BY updated_at DESC
            """).fetchall()
            return [dict(r) for r in rows]

    # Task Briefs
    def save_task_brief(self, brief: TaskBrief) -> str:
        """Save task brief."""
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO task_briefs (task_id, role, brief_json, brief_version)
                VALUES (?, ?, ?, ?)
            """, (brief.task_id, brief.role, brief.model_dump_json(), brief.business_brief_version))
        return brief.task_id

    def get_task_brief(self, task_id: str) -> Optional[TaskBrief]:
        """Get task brief by ID."""
        with self._conn() as conn:
            row = conn.execute("""
                SELECT brief_json FROM task_briefs WHERE task_id = ?
            """, (task_id,)).fetchone()
            if row:
                return TaskBrief.model_validate_json(row["brief_json"])
        return None

    # Role Outputs
    def save_output(self, output: RoleOutput) -> str:
        """Save role output."""
        output_id = output.task_id or str(uuid.uuid4())
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO role_outputs
                (id, task_id, skill_id, skill_name, output, evidence_json, assumptions_json,
                 gaps_json, quality_score, quality_details_json, handoff_json,
                 tokens_used, cost_usd, latency_seconds, brief_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                output_id, output.task_id, output.skill_id, output.skill_name,
                output.output, json.dumps(output.evidence), json.dumps(output.assumptions),
                json.dumps(output.gaps), output.quality_score,
                json.dumps(output.quality_details), json.dumps(output.handoff) if output.handoff else None,
                output.tokens_used, output.cost_usd, output.latency_seconds, output.brief_version
            ))
        # Index in Chroma for semantic search
        self._index_output(output_id, output)
        return output_id

    def get_output(self, task_id: str, skill_id: str) -> Optional[RoleOutput]:
        """Get role output for a task."""
        with self._conn() as conn:
            row = conn.execute("""
                SELECT * FROM role_outputs WHERE task_id = ? AND skill_id = ?
                ORDER BY created_at DESC LIMIT 1
            """, (task_id, skill_id)).fetchone()
            if row:
                return RoleOutput(
                    task_id=row["task_id"],
                    skill_id=row["skill_id"],
                    skill_name=row["skill_name"],
                    output=row["output"],
                    evidence=json.loads(row["evidence_json"]) if row["evidence_json"] else [],
                    assumptions=json.loads(row["assumptions_json"]) if row["assumptions_json"] else [],
                    gaps=json.loads(row["gaps_json"]) if row["gaps_json"] else [],
                    quality_score=row["quality_score"],
                    quality_details=json.loads(row["quality_details_json"]) if row["quality_details_json"] else {},
                    handoff=json.loads(row["handoff_json"]) if row["handoff_json"] else None,
                    tokens_used=row["tokens_used"],
                    cost_usd=row["cost_usd"],
                    latency_seconds=row["latency_seconds"],
                    brief_version=row["brief_version"],
                )
        return None

    def get_all_outputs_for_task(self, task_id: str) -> list[RoleOutput]:
        """Get all role outputs for a task."""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM role_outputs WHERE task_id = ? ORDER BY created_at
            """, (task_id,)).fetchall()
            return [RoleOutput(
                task_id=r["task_id"], skill_id=r["skill_id"], skill_name=r["skill_name"],
                output=r["output"], evidence=json.loads(r["evidence_json"]) if r["evidence_json"] else [],
                assumptions=json.loads(r["assumptions_json"]) if r["assumptions_json"] else [],
                gaps=json.loads(r["gaps_json"]) if r["gaps_json"] else [],
                quality_score=r["quality_score"],
                quality_details=json.loads(r["quality_details_json"]) if r["quality_details_json"] else {},
                handoff=json.loads(r["handoff_json"]) if r["handoff_json"] else None,
                tokens_used=r["tokens_used"], cost_usd=r["cost_usd"],
                latency_seconds=r["latency_seconds"], brief_version=r["brief_version"],
            ) for r in rows]

    def _index_output(self, output_id: str, output: RoleOutput):
        """Index output in ChromaDB for semantic search."""
        try:
            doc = f"{output.skill_name}: {output.output[:2000]}"
            metadata = {
                "skill_id": output.skill_id,
                "task_id": output.task_id,
                "brief_version": output.brief_version,
                "quality_score": output.quality_score or 0,
                "timestamp": output.timestamp.isoformat() if isinstance(output.timestamp, datetime) else str(output.timestamp),
            }
            self.collection.upsert(
                ids=[output_id],
                documents=[doc],
                metadatas=[metadata]
            )
        except Exception:
            pass  # Chroma indexing is best-effort

    def search_evidence(self, query: str, n_results: int = 5) -> list[dict]:
        """Search evidence across all outputs."""
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results
            )
            return [
                {"id": id, "document": doc, "metadata": meta, "distance": dist}
                for id, doc, meta, dist in zip(
                    results["ids"][0], results["documents"][0],
                    results["metadatas"][0], results["distances"][0]
                )
            ]
        except Exception:
            return []

    # Handoffs
    def save_handoff(self, handoff: HandoffRecord) -> str:
        """Save handoff record."""
        handoff_id = f"handoff-{handoff.task_id}-{handoff.from_role}-{handoff.to_role}"
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO handoffs (id, task_id, from_role, to_role, record_json)
                VALUES (?, ?, ?, ?, ?)
            """, (handoff_id, handoff.task_id, handoff.from_role, handoff.to_role, handoff.model_dump_json()))
        return handoff_id

    def get_handoff(self, task_id: str, from_role: str, to_role: str) -> Optional[HandoffRecord]:
        """Get handoff record."""
        with self._conn() as conn:
            row = conn.execute("""
                SELECT record_json FROM handoffs
                WHERE task_id = ? AND from_role = ? AND to_role = ?
            """, (task_id, from_role, to_role)).fetchone()
            if row:
                return HandoffRecord.model_validate_json(row["record_json"])
        return None

    # Execution Runs
    def start_run(self, run_id: str, goal: str, brief_version: str, plan: dict) -> str:
        """Start an execution run."""
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO execution_runs (run_id, goal, brief_version, plan_json)
                VALUES (?, ?, ?, ?)
            """, (run_id, goal, brief_version, json.dumps(plan)))
        return run_id

    def complete_run(self, run_id: str, status: str, total_cost: float, total_tokens: int):
        """Complete an execution run."""
        with self._conn() as conn:
            conn.execute("""
                UPDATE execution_runs
                SET status = ?, total_cost_usd = ?, total_tokens = ?, completed_at = ?
                WHERE run_id = ?
            """, (status, total_cost, total_tokens, datetime.utcnow().isoformat(), run_id))


# Global instance
_context_store: Optional[ContextStore] = None


def get_context_store() -> ContextStore:
    """Get global context store instance."""
    global _context_store
    if _context_store is None:
        _context_store = ContextStore()
    return _context_store