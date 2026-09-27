"""Observability - metrics, logging, and tracing."""

import json
import time
import sqlite3
from pathlib import Path
from datetime import datetime
from typing: Optional
from contextlib: contextmanager
from dataclasses import dataclass, asdict
from functools import wraps

from agent_intelligence.core.config import get_settings


@dataclass
class MetricEvent:
    """Single metric event."""
    timestamp: str
    event_type: str
    run_id: str
    skill_id: Optional[str]
    stage_id: Optional[int]
    data: dict


class MetricsCollector:
    """Collects and stores metrics."""

    def __init__(self):
        self.settings = get_settings()
        self.db_path = self.settings.memory.sqlite_path.parent / "metrics.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._buffer: list[MetricEvent] = []
        self._flush_interval = 10  # flush every N events

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    skill_id TEXT,
                    stage_id INTEGER,
                    data_json TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_run ON metrics(run_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_skill ON metrics(skill_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_time ON metrics(timestamp)")

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def record(self, event: MetricEvent):
        """Record a metric event."""
        self._buffer.append(event)
        if len(self._buffer) >= self._flush_interval:
            self.flush()

    def flush(self):
        """Flush buffer to database."""
        if not self._buffer:
            return
        with self._conn() as conn:
            for event in self._buffer:
                conn.execute("""
                    INSERT INTO metrics (timestamp, event_type, run_id, skill_id, stage_id, data_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    event.timestamp, event.event_type, event.run_id,
                    event.skill_id, event.stage_id, json.dumps(event.data)
                ))
        self._buffer.clear()

    def record_llm_call(self, run_id: str, skill_id: str, stage_id: int,
                        model: str, tokens: int, cost: float, latency: float):
        """Record LLM call metrics."""
        self.record(MetricEvent(
            timestamp=datetime.utcnow().isoformat(),
            event_type="llm_call",
            run_id=run_id,
            skill_id=skill_id,
            stage_id=stage_id,
            data={"model": model, "tokens": tokens, "cost_usd": cost, "latency_seconds": latency}
        ))

    def record_stage_start(self, run_id: str, skill_id: str, stage_id: int):
        self.record(MetricEvent(
            timestamp=datetime.utcnow().isoformat(),
            event_type="stage_start",
            run_id=run_id,
            skill_id=skill_id,
            stage_id=stage_id,
            data={}
        ))

    def record_stage_complete(self, run_id: str, skill_id: str, stage_id: int,
                               success: bool, quality_score: float, cost: float):
        self.record(MetricEvent(
            timestamp=datetime.utcnow().isoformat(),
            event_type="stage_complete",
            run_id=run_id,
            skill_id=skill_id,
            stage_id=stage_id,
            data={"success": success, "quality_score": quality_score, "cost_usd": cost}
        ))

    def record_eval(self, run_id: str, skill_id: str, stage_id: int,
                     passed: bool, score: float, blockers: list):
        self.record(MetricEvent(
            timestamp=datetime.utcnow().isoformat(),
            event_type="eval_gate",
            run_id=run_id,
            skill_id=skill_id,
            stage_id=stage_id,
            data={"passed": passed, "score": score, "blockers": blockers}
        ))

    def record_human_gate(self, run_id: str, skill_id: str, stage_id: int,
                           decision: str, reason: str):
        self.record(MetricEvent(
            timestamp=datetime.utcnow().isoformat(),
            event_type="human_gate",
            run_id=run_id,
            skill_id=skill_id,
            stage_id=stage_id,
            data={"decision": decision, "reason": reason}
        ))

    def get_run_summary(self, run_id: str) -> dict:
        """Get metrics summary for a run."""
        with self._conn() as conn:
            # LLM calls
            llm = conn.execute("""
                SELECT SUM(tokens) as total_tokens, SUM(cost_usd) as total_cost,
                       AVG(latency_seconds) as avg_latency, COUNT(*) as calls
                FROM metrics WHERE run_id = ? AND event_type = 'llm_call'
            """, (run_id,)).fetchone()

            # Stages
            stages = conn.execute("""
                SELECT skill_id, stage_id, data_json
                FROM metrics WHERE run_id = ? AND event_type = 'stage_complete'
                ORDER BY stage_id
            """, (run_id,)).fetchall()

            stage_data = []
            for row in stages:
                import json
                data = json.loads(row["data_json"])
                stage_data.append({
                    "skill_id": row["skill_id"],
                    "stage_id": row["stage_id"],
                    **data
                })

            return {
                "run_id": run_id,
                "total_tokens": llm["total_tokens"] or 0,
                "total_cost": llm["total_cost"] or 0.0,
                "avg_latency": llm["avg_latency"] or 0.0,
                "llm_calls": llm["calls"] or 0,
                "stages": stage_data
            }


# Decorator for automatic metric recording
def track_metrics(event_type: str, run_id_key: str = "run_id", skill_id_key: str = "skill_id"):
    """Decorator to automatically track function metrics."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            collector = MetricsCollector()
            run_id = kwargs.get(run_id_key, "unknown")
            skill_id = kwargs.get(skill_id_key)

            try:
                result = func(*args, **kwargs)
                latency = time.perf_counter() - start
                collector.record(MetricEvent(
                    timestamp=datetime.utcnow().isoformat(),
                    event_type=event_type,
                    run_id=run_id,
                    skill_id=skill_id,
                    stage_id=kwargs.get("stage_id"),
                    data={"success": True, "latency_seconds": latency}
                ))
                return result
            except Exception as e:
                latency = time.perf_counter() - start
                collector.record(MetricEvent(
                    timestamp=datetime.utcnow().isoformat(),
                    event_type=event_type,
                    run_id=run_id,
                    skill_id=skill_id,
                    stage_id=kwargs.get("stage_id"),
                    data={"success": False, "error": str(e), "latency_seconds": latency}
                ))
                raise
        return wrapper
    return decorator


# Global instance
_metrics: Optional[MetricsCollector] = None


def get_metrics() -> MetricsCollector:
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics