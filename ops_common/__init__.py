"""ops-common: 两个垂直代理共享的治理层。

模块一览：
    types      事件与暂存变更类型
    config     代理配置（模型、预算、上限）
    fencing    第三方文本净化与围栏
    db         MySQL 连接助手
    skills     SKILL.md 技能注册
    changes    暂存变更存储 + 审批网关
    turn       Anthropic 兼容流式回合循环
"""

from .types import AgentEvent, DiffItem, StagedChange, Session
from .config import AgentConfig
from .fencing import fence, sanitize
from .skills import SkillRegistry
from .changes import ChangeStore
from .turn import Agent

__all__ = [
    "AgentEvent", "DiffItem", "StagedChange", "Session",
    "AgentConfig", "fence", "sanitize", "SkillRegistry", "ChangeStore", "Agent",
]
