# internal/schema/message.py
# 对应 Go 版: internal/schema/message.go
# 定义引擎内部流转的统一消息格式（与具体模型厂商解耦）。

# 为什么要有这一层：OpenAI 用 "tool" 角色承放工具结果，Anthropic 用
# tool_result block 包在 user 消息里。如果引擎直接拼厂商格式，
# 换一个模型就要改一遍引擎；所以这里定义自己的 Message，让 Provider 去翻译。
from dataclasses import dataclass, field

# Go 版中的 type Role string + 常量定义。
# Python 里直接用字符串常量表达角色。
ROLE_SYSTEM = "system"
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"


@dataclass
class ToolCall:
    """模型发起的一次工具调用请求。arguments 保持为原始 JSON 字符串（对应 Go 的 json.RawMessage），由各工具自行解析。"""
    # 保持字符串而不在这里解析成 dict：不同厂商返回的 arguments 形态不同
    # （有的直接给字符串、有的给对象），统一成字符串能让引擎完全不必关心。
    id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass
class Message:
    """一条上下文消息。tool_calls 仅在 assistant 消息中出现；tool_call_id 仅在承载工具执行结果的 user 消息中出现。"""
    # 用"role + tool_call_id"这一个结构同时表达四种消息（system / user /
    # assistant / 工具结果），引擎就只需要维护一个 list，回写观察也只是 append。
    role: str = ""
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str = ""


@dataclass
class ToolResult:
    """一次工具执行的结果。"""
    tool_call_id: str = ""
    output: str = ""
    is_error: bool = False


@dataclass
class ToolDefinition:
    """暴露给模型的工具定义（名称 + 描述 + JSON Schema 入参约束）。"""
    name: str = ""
    description: str = ""
    input_schema: dict | None = None
