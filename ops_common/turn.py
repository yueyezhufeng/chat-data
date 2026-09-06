"""The turn loop over any Anthropic-compatible endpoint (first-party or a gateway).

Rules that hold on every call:
  - the static system block and the tools array are byte-identical across turns, so the
    prefix caches; per-request data rides in a second system block after the breakpoint
  - tool exceptions never end the turn; they come back as an error tool_result
  - a tool that a gate blocks returns a normal result with status=blocked and the gate name
"""

from __future__ import annotations

import json
import time
from typing import AsyncIterator, Callable

import anthropic

from .config import AgentConfig
from .skills import SkillRegistry
from .tools import ToolOutcome, ToolSpec, tool_schemas
from .types import AgentEvent, Session


def _short_label(tool_input: dict, limit: int = 70) -> str:
    for key in ("keyword", "name", "table", "sql", "rationale", "product_id", "user_id"):
        if tool_input.get(key):
            text = str(tool_input[key]).replace("\n", " ")
            return text[:limit] + ("…" if len(text) > limit else "")
    return (json.dumps(tool_input, ensure_ascii=False)[:limit]) if tool_input else ""


class Agent:
    def __init__(
        self,
        *,
        config: AgentConfig,
        system_static: str,
        tools: list[ToolSpec],
        dynamic_context: Callable[[Session], str] | None = None,
        client: anthropic.AsyncAnthropic | None = None,
    ):
        self.config = config
        self.system_static = system_static
        self.tools = {t.name: t for t in tools}
        self.dynamic_context = dynamic_context
        self.client = client or anthropic.AsyncAnthropic(
            timeout=config.request_timeout_s, max_retries=4
        )

    def _system(self, session: Session) -> list[dict]:
        blocks = [{"type": "text", "text": self.system_static, "cache_control": {"type": "ephemeral"}}]
        if self.dynamic_context:
            blocks.append({"type": "text", "text": self.dynamic_context(session)})
        return blocks

    async def stream_turn(self, session: Session, user_message: str) -> AsyncIterator[AgentEvent]:
        started = time.time()
        session.messages.append({"role": "user", "content": user_message})
        schemas = tool_schemas(list(self.tools.values()))

        try:
            for round_no in range(1, self.config.max_tool_iterations + 1):
                async with self.client.messages.stream(
                    model=self.config.model,
                    max_tokens=self.config.max_tokens,
                    system=self._system(session),
                    tools=schemas,
                    messages=session.messages,
                ) as stream:
                    async for event in stream:
                        if event.type == "content_block_delta" and getattr(event.delta, "type", "") == "text_delta":
                            yield AgentEvent.text(event.delta.text)
                    message = await stream.get_final_message()

                session.messages.append({"role": "assistant", "content": message.model_dump(mode="json")["content"]})

                if message.stop_reason != "tool_use":
                    yield AgentEvent("turn_complete", {
                        "usage": {
                            "input_tokens": message.usage.input_tokens,
                            "output_tokens": message.usage.output_tokens,
                            "cache_read": getattr(message.usage, "cache_read_input_tokens", 0) or 0,
                        },
                        "elapsed_ms": int((time.time() - started) * 1000),
                        "rounds": round_no,
                    })
                    return

                results = []
                for block in message.content:
                    if block.type != "tool_use":
                        continue
                    tool_input = dict(block.input or {})
                    yield AgentEvent.tool_call(block.name, _short_label(tool_input))

                    spec = self.tools.get(block.name)
                    if spec is None:
                        outcome = ToolOutcome(content=f"工具 {block.name} 不在本次部署的工具面内。", status="error")
                    else:
                        try:
                            outcome = await spec.handler(tool_input, session)
                        except Exception as error:  # a tool exception never ends the turn
                            outcome = ToolOutcome(content=f"工具执行失败：{error}", status="error")

                    yield AgentEvent.tool_result(block.name, outcome.status, outcome.short())
                    if outcome.ui:
                        yield AgentEvent.ui(outcome.ui["component"], outcome.ui["payload"])
                    if outcome.change:
                        yield AgentEvent.change_update(outcome.change)

                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": [{"type": "text", "text": outcome.content or "（空结果）"}],
                    })
                session.messages.append({"role": "user", "content": results})

            yield AgentEvent.error("已达到单轮工具调用次数上限，请拆小问题或开新会话。")
        except anthropic.AuthenticationError:
            yield AgentEvent.error(
                "模型 API 认证失败（401）。请检查 .env 里的 ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL 后重启服务。"
            )
        except anthropic.APIConnectionError as error:
            yield AgentEvent.error(f"无法连接模型 API：{error.__class__.__name__}。请检查网络后重试。")
        except Exception as error:
            yield AgentEvent.error(f"本轮对话出错：{error}. 请重试。")


def build_system(role_text: str, skills: SkillRegistry | None) -> str:
    """Static system prompt: role rules first, then the skill index (a load_skill away)."""
    parts = [role_text]
    if skills and skills.loaded():
        parts.append(
            "\n## 技能（流程手册）\n"
            "处理对应类别的请求前，先调用 load_skill 加载完整流程，再按流程执行：\n"
            + skills.index_lines()
        )
    return "\n".join(parts)
