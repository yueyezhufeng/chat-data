"""Staged changes: the single write path. Nothing applies without an approval mark."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Callable

from .types import DiffItem, StagedChange


class ChangeStore:
    """Thread-safe store, JSON-persisted. `apply_fn` executes the real work and is
    called only from the host's approve route — never from a tool the model calls."""

    def __init__(self, path: Path | None = None, apply_fn: Callable[[StagedChange], dict] | None = None):
        self._path = path
        self._apply_fn = apply_fn
        self._lock = threading.Lock()
        self._changes: dict[str, StagedChange] = {}
        if path and path.exists():
            for raw in json.loads(path.read_text(encoding="utf-8")):
                change = self._from_dict(raw)
                self._changes[change.change_id] = change

    def _persist(self) -> None:
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps([c.to_dict() for c in self._changes.values()], ensure_ascii=False, indent=1),
                encoding="utf-8",
            )

    @staticmethod
    def _from_dict(raw: dict) -> StagedChange:
        change = StagedChange(
            kind=raw["kind"], summary=raw["summary"], sql=raw.get("sql", ""),
            items=[DiffItem(**item) for item in raw.get("items", [])],
            impact=raw.get("impact", {}), change_id=raw["change_id"],
            status=raw.get("status", "staged"),
            created_by=raw.get("created_by", "agent"), created_by_kind=raw.get("created_by_kind", "agent"),
            created_at=raw.get("created_at", ""),
        )
        change.applied_at, change.applied_by = raw.get("applied_at"), raw.get("applied_by")
        change.discarded_at, change.discarded_by = raw.get("discarded_at"), raw.get("discarded_by")
        return change

    def stage(self, change: StagedChange, guardrails: Callable[[StagedChange], None] | None = None) -> StagedChange:
        """Guardrails run at stage time; they raise ValueError with an operator-readable reason."""
        if guardrails:
            guardrails(change)
        with self._lock:
            self._changes[change.change_id] = change
            self._persist()
        return change

    def get(self, change_id: str) -> StagedChange | None:
        return self._changes.get(change_id)

    def all(self) -> list[StagedChange]:
        return sorted(self._changes.values(), key=lambda c: c.created_at, reverse=True)

    def pending(self) -> list[StagedChange]:
        return [c for c in self.all() if c.status == "staged"]

    def apply(self, change_id: str, approved_by: str) -> StagedChange:
        """The approval mark comes from the host route, never from chat text or a card."""
        with self._lock:
            change = self._changes.get(change_id)
            if change is None:
                raise ValueError(f"未知变更 {change_id}")
            if change.status != "staged":
                raise ValueError(f"变更 {change_id} 已是 {change.status} 状态，不能重复处理")
            if self._apply_fn is None:
                raise ValueError("该部署没有注册执行器，无法应用变更")
            impact = self._apply_fn(change)   # guardrails run again in the executor; real work happens here
            change.impact.update(impact)
            change.status = "applied"
            change.applied_by = approved_by
            from .types import now_iso
            change.applied_at = now_iso()
            self._persist()
            return change

    def update(self, change: StagedChange) -> None:
        """Persist a mutation made outside stage/apply (e.g. a post-apply measurement)."""
        with self._lock:
            self._changes[change.change_id] = change
            self._persist()

    def discard(self, change_id: str, by: str, by_kind: str = "operator") -> StagedChange:
        with self._lock:
            change = self._changes.get(change_id)
            if change is None:
                raise ValueError(f"未知变更 {change_id}")
            if change.status != "staged":
                raise ValueError(f"变更 {change_id} 已是 {change.status} 状态")
            change.status = "discarded"
            change.discarded_by = by
            change.discarded_by_kind = by_kind
            from .types import now_iso
            change.discarded_at = now_iso()
            self._persist()
            return change
