# internal/provider/interface.py
# 对应 Go 版: internal/provider/interface.go
from abc import ABC, abstractmethod

from internal.schema.message import Message, ToolDefinition


class LLMProvider(ABC):
    """LLMProvider 定义了与大模型通信的统一接口（对应 Go 的 interface）

    引擎只调用 generate()，完全不知道背后是 DeepSeek、Claude 还是别的厂商。
    各家协议差异（system 放哪、工具结果怎么包）全部收在具体 Provider 里，
    所以"换模型"只需要换一个实现，引擎一行都不用改。
    """

    @abstractmethod
    def generate(self, messages: list[Message], available_tools: list[ToolDefinition] | None) -> Message:
        """generate 接收当前上下文历史和可用工具列表，返回模型响应

        available_tools 传 None 是"剥夺工具"的约定：
        引擎在慢思考阶段用它让模型只能输出纯文本规划，无法发起工具调用。
        """
        ...
