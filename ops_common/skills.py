"""SKILL.md registries: a flow per directory, rendered into the prompt index."""

from __future__ import annotations

import re
from pathlib import Path

from .fencing import fence

_FRONT = re.compile(r"^---\s*\n(?P<meta>.*?)\n---\s*\n?", re.S)


class Skill:
    def __init__(self, name: str, description: str, body: str):
        self.name = name
        self.description = description
        self.body = body


class SkillRegistry:
    def __init__(self, skills_dir: Path | str | None):
        self.skills: dict[str, Skill] = {}
        if skills_dir is None:
            return
        for path in sorted(Path(skills_dir).glob("*/SKILL.md")):
            raw = path.read_text(encoding="utf-8")
            match = _FRONT.match(raw)
            meta = {}
            if match:
                for line in match.group("meta").splitlines():
                    key, _, value = line.partition(":")
                    if key and value:
                        meta[key.strip()] = value.strip()
                raw = raw[match.end():]
            name = meta.get("name", path.parent.name)
            self.skills[name] = Skill(name, meta.get("description", ""), raw.strip())

    def loaded(self) -> bool:
        return bool(self.skills)

    def index_lines(self) -> str:
        return "\n".join(f"  - {s.name}：{s.description}" for s in self.skills.values())

    def get(self, name: str) -> Skill | None:
        return self.skills.get(name)

    def load(self, name: str) -> str:
        skill = self.skills.get(name)
        if skill is None:
            return f"未找到技能 {name}。可用技能：{', '.join(self.skills) or '无'}"
        return fence(f"技能 {name}", skill.body, max_chars=8000)

    def tool_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "enum": sorted(self.skills), "description": "要加载的技能名"}
            },
            "required": ["name"],
        }
