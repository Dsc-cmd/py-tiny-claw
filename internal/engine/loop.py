# internal/engine/loop.py
# 对应 Go 版: internal/engine/loop.go
# 第 3 章：引入"慢思考"(Thinking Phase)：先剥夺工具强制模型规划，再放开工具让它行动。
import logging

from internal.provider.interface import LLMProvider
from internal.schema.message import Message, ROLE_SYSTEM, ROLE_USER
from internal.tools.registry import Registry

log = logging.getLogger(__name__)


class AgentEngine:
    def __init__(self, provider: LLMProvider, registry: Registry, work_dir: str, enable_thinking: bool):
        self.provider = provider
        self.registry = registry
        self.work_dir = work_dir
        self.enable_thinking = enable_thinking

    def run(self, user_prompt: str) -> None:
        log.info("[Engine] 引擎启动，锁定工作区: %s", self.work_dir)
        log.info("[Engine] 慢思考模式 (Thinking Phase): %s", self.enable_thinking)

        context_history: list[Message] = [
            Message(
                role=ROLE_SYSTEM,
                content="You are py-tiny-claw, an expert coding assistant. You have full access to tools in the workspace.",
            ),
            Message(
                role=ROLE_USER,
            content=user_prompt,1
            ),
        ]

        turn_count = 0

        while True:
            turn_count += 1
            log.info("\n========== [Turn %d] 开始 ==========", turn_count)

            available_tools = self.registry.get_available_tools()

            # ================= Phase 1: Thinking =================
            if self.enable_thinking:
                log.info("[Phase 1] 剥夺工具访问权，强制进入慢思考与规划阶段...")
                try:
                    think_resp = self.provider.generate(context_history, None)  # 传 None 剥夺工具
                except Exception as e:
                    raise RuntimeError(f"Thinking 阶段失败: {e}")

                if think_resp.content != "":
                    print(f"[内部思考 Trace]: {think_resp.content}")
                context_history.append(think_resp)

            # ================= Phase 2: Reason =================
            log.info("[Phase 2] 恢复工具挂载，等待模型行动...")
            try:
                action_resp = self.provider.generate(context_history, available_tools)
            except Exception as e:
                raise RuntimeError(f"Action 阶段失败: {e}")

            context_history.append(action_resp)

            if action_resp.content != "":
                print(f"[对外回复]: {action_resp.content}")

            # ================= 执行判断 =================
            if len(action_resp.tool_calls) == 0:
                log.info("模型未请求工具，任务完成。")
                break

            log.info("模型请求调用 %d 个工具...", len(action_resp.tool_calls))

            # ================= Act + Observe =================
            for tool_call in action_resp.tool_calls:
                result = self.registry.execute(tool_call)

                observation_msg = Message(
                    role=ROLE_USER,
                    content=result.output,
                    tool_call_id=tool_call.id,
                )
                context_history.append(observation_msg)