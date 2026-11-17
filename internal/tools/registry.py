# internal/tools/registry.py
# 对应 Go 版: internal/tools/registry.go
# 第 5 章：Registry 从接口升级为真实实现，负责工具的注册、查找与统一执行。
import logging
from abc import ABC, abstractmethod

from internal.schema.message import ToolCall, ToolDefinition, ToolResult

log = logging.getLogger(__name__)


class BaseTool(ABC):
    """所有工具必须实现的基础接口（对应 Go 的 BaseTool interface）

    拆成三个方法是为了"描述"和"执行"分离：
    - name / definition 负责告诉模型"我是谁、参数长什么样"，只用于拼提示词；
    - execute 负责真正干活，参数是模型给的原始 JSON 字符串。
    工具内部出错时直接抛异常，由 Registry 统一转成错误观察，工具自己不用关心兜底。
    """

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
    """工具注册中心接口

    引擎只依赖这个抽象，不认识任何一个具体工具；
    这样加工具只需要实现 BaseTool 再 register，不用改引擎。
    """

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
    """Registry 的默认实现：内部用一个 dict 存储 名称 -> 工具实例 的映射

    用 dict 而不是 list：执行时要按模型给的 name 快速找到工具，
    dict 是 O(1) 查找，list 得逐个比对。
    """

    def __init__(self):
        self.tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        name = tool.name()
        # 同名工具直接覆盖并打警告：热插拔调试时方便，但静默覆盖容易让人困惑。
        if name in self.tools:
            log.info("[Warning] 工具 '%s' 已经被注册，将被覆盖。", name)
        self.tools[name] = tool
        log.info("[Registry] 成功挂载工具: %s", name)

    def get_available_tools(self) -> list[ToolDefinition]:
        # 只返回"定义"（名称/描述/参数 schema），不返回工具实例本身，
        # 因为模型需要的是说明书，不是可执行对象。
        return [tool.definition() for tool in self.tools.values()]

    def execute(self, call: ToolCall) -> ToolResult:
        tool = self.tools.get(call.name)
        # 模型可能"幻觉"出不存在的工具名，这里给一条人类可读的错误观察，
        # 让它自己改成正确名字重试，而不是让引擎崩掉。
        if tool is None:
            err_msg = f"Error: 系统中不存在名为 '{call.name}' 的工具。"
            return ToolResult(
                tool_call_id=call.id,
                output=err_msg,
                is_error=True,
            )

        # 统一的异常兜底：工具内部抛出的任何异常都转换为 is_error 的观察结果，
        # 反馈给模型让它自行纠错，而不是让整个引擎崩溃。
        # 这也是"出错不崩溃"这条要求真正落地的地方：工具只管抛，Registry 负责收。
        try:
            output = tool.execute(call.arguments)
        except Exception as e:
            return ToolResult(
                tool_call_id=call.id,
                output=f"Error executing {call.name}: {e}",
                is_error=True,
            )

        return ToolResult(
            tool_call_id=call.id,
            output=output,
            is_error=False,
        )


def new_registry() -> Registry:
    """对应 Go 版的 NewRegistry 构造函数"""
    return RegistryImpl()
