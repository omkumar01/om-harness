"""Model routing: pick the right model per task type, with overrides.

Order of precedence for ``select``:
1. explicit override argument (user asked for this model),
2. configured per-task-type models (``routing.task_models``),
3. automatic routing across available providers (cheap models for explore,
   strong models for implement/review),
4. configured ``default_model``,
5. the mock provider (fully offline).
"""

from __future__ import annotations

from om_harness.config.loader import RoutingConfig
from om_harness.models.task import TaskType
from om_harness.providers.base import BY_NAME
from om_harness.providers.registry import ProviderRegistry

# Task types that benefit from stronger (usually costlier) models.
STRONG_TASK_TYPES = {TaskType.implement, TaskType.review}


class ModelRouter:
    def __init__(self, config: RoutingConfig, registry: ProviderRegistry) -> None:
        self.config = config
        self.registry = registry

    def select(self, task_type: TaskType, override: str | None = None) -> str:
        if override:
            self.registry.resolve_model(override)  # validate early
            return override

        if self.config.auto_route and task_type in self.config.task_models:
            configured = self.config.task_models[task_type]
            self.registry.resolve_model(configured)
            return configured

        if self.config.auto_route:
            return self._auto_route(task_type)

        return self.config.default_model

    def _auto_route(self, task_type: TaskType) -> str:
        """Pick from whichever provider has a key; strong/cheap per task type."""
        provider_name = self.registry.first_available()
        spec = BY_NAME[provider_name]
        if task_type in STRONG_TASK_TYPES:
            return spec.strong_model
        return spec.default_model

    def fallback_chain(self, primary: str) -> list[str]:
        """Primary model plus configured fallbacks, all validated."""
        chain = [primary]
        for model_str in self.config.fallbacks:
            self.registry.resolve_model(model_str)
            if model_str not in chain:
                chain.append(model_str)
        return chain
