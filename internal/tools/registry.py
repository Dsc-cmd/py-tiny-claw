# internal/tools/registry.py
# 对应 Go 版: internal/tools/registry.go
# 第 5 章：Registry 从接口升级为真实实现，负责工具的注册、查找与统一执行。
import logging
from abc import ABC, abstractmethod

from internal.schema.message import ToolCall, ToolDefinition, ToolResult

log = logging.getLogger(__name__)


class BaseTool(ABC):
    """所有工具必须实现的基础接口（对应 Go 的 BaseTool interface）"""

    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def definition(self) -> ToolDefinition:
        ...

    @abstractmethod
    def execute(self, args: str) -> str:
        """args 为原始 JSON 字符串，由工具自行解析；执行失败时抛出异常（对应 Go 的返回 error）"""
        ...


class Registry(ABC):
    """工具注册中心接口"""

    @abstractmethod
    def register(self, tool: BaseTool):
        ...

    @abstractmethod
    def get_available_tools(self) -> list[ToolDefinition]:
        ...

    @abstractmethod
    def execute(self, call: ToolCall) -> ToolResult:
        ...


class RegistryImpl(Registry):
    """Registry 的默认实现：内部用一个 dict 存储 名称 -> 工具实例 的映射"""

    def __init__(self):
        self.tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        # ==================================================
        # 职责 1：动态挂载（Register）
        # 1. 通过 tool.name() 获取工具名称
        # 2. 如果名称已存在，打印警告："[Warning] 工具 'xxx' 已经被注册，将被覆盖。"
        # 3. 将工具存入 self.tools
        # 4. 打印日志："[Registry] 成功挂载工具: xxx"
        # ==================================================
        tool_name = tool.name()
        if tool_name in self.tools:
            print(f"[Warning] 工具 '{tool_name}' 已经被注册，将被覆盖。")
        self.tools[tool_name] = tool
        print(f"[Registry] 成功挂载工具: {tool_name}")

    def get_available_tools(self) -> list[ToolDefinition]:
        # ==================================================
        # 职责 2：描述暴露（Expose Schema）
        # 返回所有已挂载工具的 definition() 组成的列表
        # ==================================================
        return [tool.definition() for tool in self.tools.values()]

    def execute(self, call: ToolCall) -> ToolResult:
        # ==================================================
        # 职责 3：路由分发与执行（Dispatch & Execute）
        # 1. 根据 call.name 查找工具；找不到时返回 is_error=True 的 ToolResult
        # 2. 调用 tool.execute(call.arguments)
        # 3. 用 try/except 兜底：工具抛出的任何异常都转换为 is_error=True 的 ToolResult
        # 4. 执行成功时返回 is_error=False 的 ToolResult
        # 5. 所有 ToolResult 都必须带上正确的 tool_call_id
        # ==================================================
        if call.name not in self.tools:
            return ToolResult(
                tool_call_id=call.id,
                output=f"Error: 系统中不存在名为 '{call.name}' 的工具。",
                is_error=True,
            )
        try:
            output = self.tools[call.name].execute(call.arguments)
            return ToolResult(tool_call_id=call.id, output=output, is_error=False)
        except Exception as e:
            return ToolResult(
                tool_call_id=call.id,
                output=f"Error executing {call.name}: {e}",
                is_error=True,
            )


def new_registry() -> Registry:
    """对应 Go 版的 NewRegistry 构造函数"""
    return RegistryImpl()
