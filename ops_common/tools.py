"""ToolSpec/ToolOutcome live beside the events so verticals and the loop agree."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .types import Session


@dataclass
class ToolOutcome:
    content: str = ""
    status: str = "ok"           # ok | blocked | error
    ui: dict | None = None       # {"component": ..., "payload": ...}
    change: dict | None = None   # a staged/updated change to broadcast

    def short(self, limit: int = 80) -> str:
        text = " ".join(self.content.split())
        return text[:limit] + ("…" if len(text) > limit else "")


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict
    handler: Callable[[dict, Session], Awaitable[ToolOutcome]]


def tool_schemas(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {"name": t.name, "description": t.description, "input_schema": t.input_schema}
        for t in tools
    ]
