"""Configuration management for the Agent Intelligence Layer."""

from pathlib import Path
from typing import Literal, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelConfig(BaseSettings):
    """Model provider configuration — supports 100+ providers via LiteLLM."""
    provider: Literal[
        "ollama", "openai", "anthropic", "gemini",
        "azure", "bedrock", "vertex_ai", "litellm",
        "local", "lmstudio", "vllm", "localai"
    ] = "ollama"
    name: str = "qwen2.5:7b"
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    temperature: float = 0.1
    max_tokens: int = 4096
    reasoning_effort: Optional[Literal["low", "medium", "high"]] = None

    # Azure-specific
    api_version: Optional[str] = None

    # Vertex AI-specific
    project: Optional[str] = None
    location: Optional[str] = None

    model_config = SettingsConfigDict(env_prefix="AIL_MODEL_", extra="ignore")


class MemoryConfig(BaseSettings):
    """Memory/storage configuration."""
    sqlite_path: Path = Path("./data/agent_intelligence.db")
    chroma_path: Path = Path("./data/chroma")
    chroma_collection: str = "agent_outputs"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    model_config = SettingsConfigDict(env_prefix="AIL_MEMORY_")


class SkillsConfig(BaseSettings):
    """Skills repository configuration."""
    path: Path = Path("../growth-architect-store")
    departments: list[str] = [
        "developers", "designers", "marketing", "social-media",
        "finance", "small-business", "legal", "gpt6-astra-business-team"
    ]
    auto_reload: bool = True

    model_config = SettingsConfigDict(env_prefix="AIL_SKILLS_")


class MCPConfig(BaseSettings):
    """MCP server configuration."""
    enabled: bool = True
    servers_dir: Path = Path("./mcp/servers")
    config_file: Path = Path("./mcp/mcp_config.yaml")
    timeout_seconds: int = 30

    model_config = SettingsConfigDict(env_prefix="AIL_MCP_")


class HumanGateConfig(BaseSettings):
    """Human approval gate configuration."""
    enabled: bool = True
    api_port: int = 8080
    ui_port: int = 8501
    require_approval_for: list[str] = [
        "spend>10",
        "external_send",
        "data_export",
        "contract_change",
        "eval_score<8",
        "blocker"
    ]
    notification_channels: list[Literal["api", "streamlit", "slack"]] = ["api", "streamlit"]

    model_config = SettingsConfigDict(env_prefix="AIL_HUMAN_GATE_")


class ObservabilityConfig(BaseSettings):
    """Observability configuration."""
    enabled: bool = True
    log_level: str = "INFO"
    log_file: Path = Path("./logs/agent_intelligence.log")
    langfuse_enabled: bool = False
    langfuse_host: str = "http://localhost:3000"
    langfuse_public_key: Optional[str] = None
    langfuse_secret_key: Optional[str] = None
    metrics_retention_days: int = 30

    model_config = SettingsConfigDict(env_prefix="AIL_OBS_")


class Settings(BaseSettings):
    """Main application settings."""
    model: ModelConfig = Field(default_factory=ModelConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    human_gate: HumanGateConfig = Field(default_factory=HumanGateConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)

    # Runtime
    debug: bool = False
    max_concurrent_roles: int = 3
    default_budget_usd: float = 50.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get the global settings instance."""
    return settings


def reload_settings() -> Settings:
    """Reload settings from environment."""
    global settings
    settings = Settings()
    return settings