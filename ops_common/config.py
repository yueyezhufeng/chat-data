"""Agent configuration. Demo values; a deployment re-tunes them."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _model_default() -> str:
    return os.environ.get("OPS_MODEL", "deepseek-v4-flash")


@dataclass
class AgentConfig:
    name: str
    model: str = field(default_factory=_model_default)
    max_tokens: int = 2200
    max_tool_iterations: int = 12
    # The compat endpoint takes `thinking: disabled` but not adaptive-thinking effort fields.
    request_timeout_s: float = 120.0
