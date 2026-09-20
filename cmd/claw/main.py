# cmd/claw/main.py
# 对应 Go 版: cmd/claw/main.go
# 第 4 章：接入 DeepSeek Provider + MockRegistry（天气工具）
# 运行方式（在 py-tiny-claw 目录下）:
#   export DEEPSEEK_API_KEY=your_key  (macOS/Linux)
#   $env:DEEPSEEK_API_KEY="your_key"  (Windows PowerShell)
#   python -m cmd.claw.main
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from internal.engine.loop import AgentEngine
from internal.provider.openai import new_deepseek_provider
from internal.schema.message import (
    Message,
    ROLE_ASSISTANT,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from internal.tools.registry import Registry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%Y/%m/%d %H:%M:%S")


class MockRegistry(Registry):
    """模拟天气工具注册表"""

    def get_available_tools(self):
        return [ToolDefinition(
            name="get_weather",
            description="获取指定城市的当前天气情况",
            input_schema={
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称，例如：北京、上海"
                    }
                },
                "required": ["city"]
            }
        )]

    def execute(self, call: ToolCall) -> ToolResult:
        import json
        args = json.loads(call.arguments)
        city = args.get("city", "未知城市")
        log = logging.getLogger(__name__)
        log.info("[MockRegistry] 执行工具: %s, 参数: %s", call.name, args)
        return ToolResult(
            tool_call_id=call.id,
            output=f"API返回：{city}今天晴天，气温25度，适合户外运动。",
            is_error=False,
        )


def main():
    work_dir = os.getcwd()

    # 检查 API Key
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("错误：请先设置环境变量 DEEPSEEK_API_KEY")
        print("Windows PowerShell: $env:DEEPSEEK_API_KEY='你的key'")
        print("macOS/Linux: export DEEPSEEK_API_KEY='你的key'")
        sys.exit(1)

    # 创建 Provider（接入 DeepSeek）
    llm_provider = new_deepseek_provider("deepseek-chat")

    # 创建 Mock Registry（天气工具）
    registry = MockRegistry()

    prompt = "我想去北京跑步，帮我查查天气适合吗？"

    print("=" * 60)
    print("测试 1: EnableThinking = True（慢思考模式）")
    print("=" * 60)
    eng = AgentEngine(llm_provider, registry, work_dir, True)
    eng.run(prompt)

    print("\n")
    print("=" * 60)
    print("测试 2: EnableThinking = False（快速模式）")
    print("=" * 60)
    eng2 = AgentEngine(llm_provider, registry, work_dir, False)
    eng2.run(prompt)


if __name__ == "__main__":
    main()
