"""Model adapter - unified interface for any LLM via LiteLLM (100+ providers)."""

import os
import time
from typing import Optional
from dataclasses import dataclass

import litellm
from litellm import completion, acompletion

from agent_intelligence.core.config import get_settings
from agent_intelligence.skills.schema import Skill


@dataclass
class ModelResponse:
    """Standardized model response."""
    content: str
    tokens_used: int
    cost_usd: float
    latency_seconds: float
    model: str
    provider: str


class ModelAdapter:
    """Unified model interface via LiteLLM — supports 100+ providers."""

    def __init__(self):
        self.settings = get_settings()
        self._configure_litellm()

    def _configure_litellm(self):
        """Configure LiteLLM with settings for all supported providers."""
        litellm.drop_params = True
        litellm.set_verbose = self.settings.debug

        model_config = self.settings.model

        # Provider-specific environment setup
        if model_config.provider == "ollama":
            os.environ["OLLAMA_API_BASE"] = model_config.base_url or "http://localhost:11434"
            if model_config.api_key:
                os.environ["OLLAMA_API_KEY"] = model_config.api_key

        elif model_config.provider == "openai":
            if model_config.api_key:
                os.environ["OPENAI_API_KEY"] = model_config.api_key
            if model_config.base_url:
                os.environ["OPENAI_API_BASE"] = model_config.base_url

        elif model_config.provider == "anthropic":
            if model_config.api_key:
                os.environ["ANTHROPIC_API_KEY"] = model_config.api_key

        elif model_config.provider == "gemini":
            if model_config.api_key:
                os.environ["GEMINI_API_KEY"] = model_config.api_key
            if model_config.base_url:
                os.environ["GEMINI_API_BASE"] = model_config.base_url

        elif model_config.provider == "azure":
            if model_config.api_key:
                os.environ["AZURE_API_KEY"] = model_config.api_key
            if model_config.base_url:
                os.environ["AZURE_API_BASE"] = model_config.base_url
            if hasattr(model_config, 'api_version') and model_config.api_version:
                os.environ["AZURE_API_VERSION"] = model_config.api_version

        elif model_config.provider == "bedrock":
            # Uses AWS credentials from ~/.aws/credentials or env vars
            # AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION
            pass

        elif model_config.provider == "vertex_ai":
            # Uses GCP credentials from gcloud auth or GOOGLE_APPLICATION_CREDENTIALS
            if hasattr(model_config, 'project') and model_config.project:
                os.environ["VERTEXAI_PROJECT"] = model_config.project
            if hasattr(model_config, 'location') and model_config.location:
                os.environ["VERTEXAI_LOCATION"] = model_config.location

        elif model_config.provider == "litellm":
            if model_config.api_key:
                os.environ["LITELLM_API_KEY"] = model_config.api_key
            if model_config.base_url:
                os.environ["LITELLM_API_BASE"] = model_config.base_url

        elif model_config.provider in ("local", "lmstudio", "vllm", "localai"):
            # Local OpenAI-compatible servers
            if model_config.base_url:
                os.environ["OPENAI_API_BASE"] = model_config.base_url
            if model_config.api_key:
                os.environ["OPENAI_API_KEY"] = model_config.api_key

    def _build_model_string(self, skill: Optional[Skill] = None) -> str:
        """Build LiteLLM model string for any provider."""
        model_config = self.settings.model

        # Skill can override model preference
        if skill and skill.model_preference:
            return skill.model_preference

        provider = model_config.provider
        name = model_config.name

        # LiteLLM provider prefixes
        provider_prefixes = {
            "ollama": "ollama/",
            "openai": "",
            "anthropic": "anthropic/",
            "gemini": "gemini/",
            "azure": "azure/",
            "bedrock": "bedrock/",
            "vertex_ai": "vertex_ai/",
            "litellm": "",
            "local": "",
            "lmstudio": "",
            "vllm": "",
            "localai": "",
        }

        prefix = provider_prefixes.get(provider, f"{provider}/")
        return f"{prefix}{name}"

    def _build_params(self, skill: Optional[Skill] = None) -> dict:
        """Build completion parameters."""
        model_config = self.settings.model
        params = {
            "temperature": model_config.temperature,
            "max_tokens": model_config.max_tokens,
        }

        if model_config.reasoning_effort:
            params["reasoning_effort"] = model_config.reasoning_effort

        # Skill-specific overrides
        if skill:
            if skill.estimated_cost_usd > 0:
                params["max_budget"] = skill.estimated_cost_usd

        return params

    def complete(
        self,
        messages: list[dict],
        skill: Optional[Skill] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> ModelResponse:
        """Synchronous completion via LiteLLM."""
        start = time.perf_counter()

        model_str = model or self._build_model_string(skill)
        params = self._build_params(skill)
        params.update(kwargs)

        try:
            response = completion(
                model=model_str,
                messages=messages,
                **params
            )

            latency = time.perf_counter() - start

            usage = response.usage if hasattr(response, 'usage') else None
            tokens = usage.total_tokens if usage else 0

            cost = 0.0
            try:
                cost = litellm.completion_cost(completion_response=response)
            except Exception:
                pass

            return ModelResponse(
                content=response.choices[0].message.content or "",
                tokens_used=tokens,
                cost_usd=cost,
                latency_seconds=latency,
                model=model_str,
                provider=self.settings.model.provider
            )

        except Exception as e:
            # Fallback with minimal params
            try:
                response = completion(
                    model=model_str,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=2048
                )
                latency = time.perf_counter() - start
                return ModelResponse(
                    content=response.choices[0].message.content or "",
                    tokens_used=0,
                    cost_usd=0.0,
                    latency_seconds=latency,
                    model=model_str,
                    provider=self.settings.model.provider
                )
            except Exception as e2:
                raise RuntimeError(f"Model completion failed: {e2}")

    async def acomplete(
        self,
        messages: list[dict],
        skill: Optional[Skill] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> ModelResponse:
        """Asynchronous completion via LiteLLM."""
        start = time.perf_counter()

        model_str = model or self._build_model_string(skill)
        params = self._build_params(skill)
        params.update(kwargs)

        response = await acompletion(
            model=model_str,
            messages=messages,
            **params
        )

        latency = time.perf_counter() - start
        usage = response.usage if hasattr(response, 'usage') else None
        tokens = usage.total_tokens if usage else 0

        cost = 0.0
        try:
            cost = litellm.completion_cost(completion_response=response)
        except Exception:
            pass

        return ModelResponse(
            content=response.choices[0].message.content or "",
            tokens_used=tokens,
            cost_usd=cost,
            latency_seconds=latency,
            model=model_str,
            provider=self.settings.model.provider
        )

    def estimate_cost(self, messages: list[dict], skill: Optional[Skill] = None) -> float:
        """Estimate cost for a completion via LiteLLM."""
        model_str = self._build_model_string(skill)
        try:
            input_text = " ".join(m.get("content", "") for m in messages)
            input_tokens = len(input_text) / 4
            return litellm.completion_cost(
                model=model_str,
                prompt_tokens=int(input_tokens),
                completion_tokens=500
            )
        except Exception:
            return 0.0


# Global instance
_model_adapter: Optional[ModelAdapter] = None


def get_model_adapter() -> ModelAdapter:
    """Get global model adapter instance."""
    global _model_adapter
    if _model_adapter is None:
        _model_adapter = ModelAdapter()
    return _model_adapter