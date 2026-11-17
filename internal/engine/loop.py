# internal/engine/loop.py
# 对应 Go 版: internal/engine/loop.go
# 第 8 章：并发执行工具调用（Fork-Join）。
# Go 版用 goroutine + WaitGroup，
# Python 版用 ThreadPoolExecutor 实现"并发执行、按序聚合"。
# 本课程改进：Fork 之前先判断，只读并发、涉写串行。
import logging
from concurrent.futures import ThreadPoolExecutor

from internal.provider.interface import LLMProvider
from internal.schema.message import (
    Message, ROLE_SYSTEM, ROLE_USER, ToolCall,
)
from internal.tools.registry import Registry

log = logging.getLogger(__name__)

# 只读工具白名单：只有名单里的工具允许并发执行。
# write_file / edit_file / bash 都可能修改文件，一律按"写"处理。
READ_ONLY_TOOLS = {"read_file"}


class AgentEngine:
    """智能体主循环：把"模型决策"和"工具执行"编排在一起。

    一轮（turn）的结构是固定的四段：
      Phase 1 慢思考 -> Phase 2 行动 -> 执行工具 -> 回写观察 -> 判断是否结束。
    把"想"和"做"分成两个阶段，是为了让模型先想清楚再动手：
    直接挂上工具时，模型很容易一上来就乱发调用，把复杂任务拆得七零八落。
    """

    def __init__(self, provider: LLMProvider, registry: Registry,
                 work_dir: str, enable_thinking: bool,
                 max_turns: int = 30):
        # provider / registry 都只依赖抽象接口，引擎本身不认识具体模型和具体工具，
        # 所以换厂商、加工具都不需要改这个文件。
        self.provider = provider
        self.registry = registry
        self.work_dir = work_dir
        # enable_thinking 就是"任务二"的开关：True 时每轮先跑 Phase 1 规划，
        # False 时退化成单阶段 ReAct（只有行动）。
        self.enable_thinking = enable_thinking
        # 防止模型陷入"反复调工具"的死循环，超过上限就强行收尾
        self.max_turns = max_turns

    def run(self, user_prompt: str) -> None:
        log.info("[Engine] 引擎启动，锁定工作区: %s", self.work_dir)
        log.info("[Engine] 慢思考模式 (Thinking Phase): %s",
                 self.enable_thinking)

        # 每次 run 都从一份全新上下文开始，所以两轮用户输入之间不会互相污染。
        # system 提示只在这里注入一次，后续所有轮次与工具观察都追加在它后面。
        context_history: list[Message] = [
            Message(
                role=ROLE_SYSTEM,
                content="You are py-tiny-claw, an expert coding "
                        "assistant. You have full access to tools "
                        "in the workspace.",
            ),
            Message(role=ROLE_USER, content=user_prompt),
        ]

        turn_count = 0

        while True:
            turn_count += 1
            if turn_count > self.max_turns:
                log.warning("[Engine] 已达到最大轮次 %d，强制结束本轮任务。",
                            self.max_turns)
                break
            log.info("\n========== [Turn %d] 开始 ==========",
                     turn_count)

            available_tools = self.registry.get_available_tools()

            # ============ Phase 1: Thinking ============
            # 这一阶段模型"只能想、不能做"：它没有工具可调，只能输出纯文本计划。
            # 好处是它必须先说清楚要分几步走，避免直接甩出一堆调用。
            if self.enable_thinking:
                log.info("[Engine][Phase 1] 剥夺工具访问权，"
                         "强制进入慢思考与规划阶段...")
                try:
                    # 传入 None 剥夺工具
                    # 关键：Provider 只有在工具清单非空时才往请求里写 tools 字段，
                    # 所以这里传 None 等价于"这一次请求里模型看不到任何函数"。
                    think_resp = self.provider.generate(
                        context_history, None)
                except Exception as e:
                    raise RuntimeError(
                        f"Thinking 阶段生成失败: {e}") from e
                if think_resp.content != "":
                    print(f"🧠 [内部思考 Trace]: {think_resp.content}")
                    # 把规划写回上下文而不是用完即弃：Phase 2 请求里模型的
                    # 上一句就是"我自己刚做的计划"，行动自然会沿着计划走。
                    context_history.append(think_resp)

            # ============ Phase 2: Action ============
            # 工具重新挂回去，模型此刻才真正"有手有脚"：
            # 它要么给出 tool_calls（继续干活），要么给出最终回答（结束）。
            log.info("[Engine][Phase 2] 恢复工具挂载，"
                     "等待模型采取行动...")
            try:
                action_resp = self.provider.generate(
                    context_history, available_tools)
            except Exception as e:
                raise RuntimeError(f"Action 阶段生成失败: {e}") from e

            context_history.append(action_resp)

            if action_resp.content != "":
                print(f"🤖 [对外回复]: {action_resp.content}")

            # ============ 执行判断 ============
            # 终止条件是"模型这一轮没有再请求工具"，而不是"跑满固定轮数"。
            # 这样简单任务一轮就能收尾，复杂任务才需要连续多轮读、写、再读。
            tool_calls = action_resp.tool_calls
            if len(tool_calls) == 0:
                log.info("[Engine] 模型未请求调用工具，任务宣告完成。")
                break

            log.info("[Engine] 模型请求调用 %d 个工具...",
                     len(tool_calls))

            # ① 判断本批次能否并发：多于 1 个，且全部是只读工具
            #    判定依据不是"工具快不快"，而是"工具会不会改数据"。
            #    只要混进一个写操作就整批串行，否则可能出现"边写边读"，
            #    后面的读拿到旧内容，汇总结果就直接错了。
            can_parallel = len(tool_calls) > 1 and all(
                call.name in READ_ONLY_TOOLS for call in tool_calls
            )

            # ② 预分配结果列表：第 idx 个工具的结果放进第 idx 格
            #    每个线程只写自己的格子，不需要加锁，顺序也不会乱
            #    为什么不用锁：不同线程写的是列表里不同的元素，
            #    不存在同一个位置被两个线程改的情况；而且最后按列表顺序回写，
            #    模型看到的观察顺序就恒等于它请求的顺序，不会"谁先完成谁在前"。
            observation_msgs: list[Message | None] = (
                [None] * len(tool_calls)
            )

            def run_tool(idx: int, call: ToolCall):
                # 这里不再 try/except：异常已经在 Registry.execute 内部被
                # 兜底成 is_error 的 ToolResult，所以拿到的结果永远有值。
                log.info("  -> [Worker-%d] 🛠️ 开始执行: %s",
                         idx, call.name)

                # 执行底层工具
                result = self.registry.execute(call)

                if result.is_error:
                    log.info("  -> [Worker-%d] ❌ 工具执行报错: %s",
                             idx, result.output)
                else:
                    log.info("  -> [Worker-%d] ✅ 工具执行成功"
                             " (返回 %d 字节)",
                             idx, len(result.output))

                # 写入自己专属的格子
                observation_msgs[idx] = Message(
                    role=ROLE_USER,
                    content=result.output,
                    tool_call_id=call.id,
                )

            # ③ 只读批次 -> Fork-Join 并发；涉写批次 -> 按顺序串行
            #    串行分支保证同一个批次里"写"先落盘，后面的"读"一定读得到新内容。
            if can_parallel:
                log.info("[Engine] ⚡ 本批次全部为只读工具，"
                         "启动并发执行 (Fork)...")
                with ThreadPoolExecutor(
                        max_workers=len(tool_calls)) as executor:
                    # Fork：把每个工具调用分派给一个线程
                    futures = [
                        executor.submit(run_tool, i, call)
                        for i, call in enumerate(tool_calls)
                    ]
                    # Join：逐个等待，并让线程内的异常向上传播
                    for f in futures:
                        f.result()
                log.info("[Engine] 所有并发工具执行完毕 (Join)，"
                         "开始聚合观察结果...")
            else:
                log.info("[Engine] 🔒 本批次包含写操作或只有 1 个"
                         "工具，按顺序串行执行...")
                for i, call in enumerate(tool_calls):
                    run_tool(i, call)

            # ④ 按模型给出的原始顺序，把结果追加回上下文
            #    遍历的是预分配的列表（而不是完成顺序），所以观察顺序 == 请求顺序。
            for obs in observation_msgs:
                if obs is not None:      # 兜底：某个工具彻底失败时跳过该格
                    context_history.append(obs)
