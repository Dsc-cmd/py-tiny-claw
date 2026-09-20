# internal/schema/message.py
# 对应 Go 版: internal/schema/message.go
from dataclasses import dataclass, field

ROLE_SYSTEM = "system"
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"


@dataclass
class ToolCall:
    id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass
class Message:
    role: str = ""
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str = ""


@dataclass
class ToolResult:
    tool_call_id: str = ""
    output: str = ""
    is_error: bool = False


@dataclass
class ToolDefinition:
    name: str = ""
    description: str = ""
    input_schema: dict | None = None
