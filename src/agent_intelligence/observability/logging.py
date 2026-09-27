"""Structured logging for the agent intelligence layer."""

import logging
import sys
from pathlib import Path
from typing import Optional
from logging.handlers import RotatingFileHandler

from agent_intelligence.core.config import get_settings


def setup_logging(level: Optional[str] = None, log_file: Optional[Path] = None):
    """Configure structured logging."""
    settings = get_settings()

    log_level = level or settings.observability.log_level
    log_path = log_file or settings.observability.log_file

    # Ensure log directory exists
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Create formatters
    console_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S"
    )

    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(log_level)

    # File handler with rotation
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=10_000_000,  # 10MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(log_level)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Suppress noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("litellm").setLevel(logging.WARNING)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)


class StructuredLogger:
    """Logger with structured context."""

    def __init__(self, name: str, run_id: Optional[str] = None, skill_id: Optional[str] = None):
        self.logger = logging.getLogger(name)
        self.run_id = run_id
        self.skill_id = skill_id

    def _format(self, message: str, **kwargs) -> str:
        parts = [message]
        if self.run_id:
            parts.append(f"run={self.run_id}")
        if self.skill_id:
            parts.append(f"skill={self.skill_id}")
        for k, v in kwargs.items():
            parts.append(f"{k}={v}")
        return " | ".join(parts)

    def info(self, message: str, **kwargs):
        self.logger.info(self._format(message, **kwargs))

    def debug(self, message: str, **kwargs):
        self.logger.debug(self._format(message, **kwargs))

    def warning(self, message: str, **kwargs):
        self.logger.warning(self._format(message, **kwargs))

    def error(self, message: str, **kwargs):
        self.logger.error(self._format(message, **kwargs))

    def critical(self, message: str, **kwargs):
        self.logger.critical(self._format(message, **kwargs))

    def bind(self, **kwargs) -> "StructuredLogger":
        """Create a new logger with additional context."""
        new = StructuredLogger(self.logger.name, self.run_id, self.skill_id)
        # Could add extra context here
        return new


# Initialize on import
setup_logging()