# cmd/claw/main.py
# 对应 Go 版: cmd/claw/main.go
# 第 8 章 ：
#   任务一：终端对话模式（每输入一句话运行一次智能体，输入 exit 退出）
#   任务二：两阶段 ReAct（Phase 1 慢思考规划 -> Phase 2 思考/行动/观察循环）
# 运行方式（在 py-tiny-claw 目录下）: python -m cmd.claw.main
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from internal.engine.loop import AgentEngine
from internal.provider.interface import LLMProvider
from internal.provider.openai import new_deepseek_provider
from internal.tools.bash import BashTool
from internal.tools.edit_file import EditFileTool
from internal.tools.read_file import ReadFileTool
from internal.tools.registry import new_registry
from internal.tools.write_file import WriteFileTool

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(message)s",
                    datefmt="%Y/%m/%d %H:%M:%S",
                    stream=sys.stdout)

# 测试 1：三个互相独立的读操作 -> 应当并发
PROMPT_READ = """
我当前目录下有 a.txt、b.txt、c.txt 三个文件。
为了节省时间，请你在同一轮中一次性调用工具读取这三个文件，
并将它们的内容综合起来告诉我。
"""

# 测试 2：同一轮里混入写操作 -> 应当退回串行
PROMPT_MIX = """
请在同一轮中同时完成两件事：
1. 用 write_file 创建 d.txt，内容为"这是文件D"
2. 用 read_file 读取 a.txt
完成后告诉我 a.txt 的内容。
"""

EXIT_WORDS = {"exit", "quit", "q", "退出"}


def load_dotenv_file(path: Path) -> None:
    """极简 .env 加载器：逐行读取 KEY=VALUE 写入环境变量（已存在的变量不覆盖）。

    这样把 DEEPSEEK_API_KEY 写进项目根目录的 .env 就能直接用，
    同时避免为了读一个配置文件再引入 python-dotenv 依赖。

    只支持最朴素的三件事：KEY=VALUE、整行 # 注释、空行。
    不支持 export 前缀（会连 "export KEY" 一起当键名），
    也不支持行尾注释（整行右侧都会被当成值的一部分）。
    "已存在的不覆盖"是为了让系统级环境变量优先，避免 .env 悄悄盖掉 CI 的配置。
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def prepare_files(work_dir: Path):
    """准备测试文件（等价于教材中的 3 条 echo 命令）

    每次启动都重写一遍：保证 a/b/c.txt 内容可预期，
    演示时不会被上一次跑剩下的内容干扰（代价是手动改过的示例文件会被覆盖）。
    """
    files = {
        "a.txt": "这是文件A，里面记录了前端的报错日志。",
        "b.txt": "这是文件B，里面记录了后端的接口响应时间。",
        "c.txt": "这是文件C，里面写着今天的日期是周五。",
    }
    for name, text in files.items():
        (work_dir / name).write_text(text + "\n", encoding="utf-8")


def build_provider() -> LLMProvider:
    # 模型名可被 CLAW_MODEL 覆盖，方便在同一个密钥下切换模型；
    # 改成 ZHIPU / Claude 只需要把下面这行换成对应的构造函数。
    model = os.getenv("CLAW_MODEL", "deepseek-chat")
    return new_deepseek_provider(model)


def build_engine(work_dir: str, provider: LLMProvider,
                 enable_thinking: bool) -> AgentEngine:
    """把四个工具挂到 Registry 上，再交给引擎统一调度。"""
    # 这里是"工具注册"的组装点：每个工具构造时都注入同一个 work_dir，
    # 模型给的相对路径才会被限制在这个目录里。
    # 引擎拿到的只是 Registry 抽象，所以它不知道也不关心具体挂了哪几个工具。
    registry = new_registry()
    registry.register(ReadFileTool(work_dir))
    registry.register(WriteFileTool(work_dir))
    registry.register(BashTool(work_dir))
    registry.register(EditFileTool(work_dir))
    return AgentEngine(provider, registry, work_dir, enable_thinking)


def repl(engine: AgentEngine) -> None:
    """终端对话模式：一次输入 = 一次完整的智能体运行，exit 退出。

    这是"任务一"的实现主体：外层只负责读一行、跑一次、再读下一行，
    真正的多轮工具循环全部在 engine.run() 里，两者职责不混。
    """
    print("💻 终端模式已启动，输入你的问题（输入 exit 退出）")
    while True:
        try:
            user_input = input("\n👤 你 : ")
        except (EOFError, KeyboardInterrupt):
            # Ctrl+C / Ctrl+D 在交互里很常见，当成"退出"处理，
            # 不必让用户看到一串 KeyboardInterrupt 堆栈。
            print("\n👋 已退出终端模式。")
            break

        user_input = user_input.strip()
        if not user_input:
            # 空行直接跳过，不触发一次空任务的模型调用（省钱也省时间）。
            continue
        if user_input.lower() in EXIT_WORDS:
            print("👋 已退出终端模式。")
            break

        # 单轮失败不能拖垮整个终端：捕获后打印错误，继续等下一句输入
        # （例如 key 临时失效、网络抖动，用户改完可以立刻重试，不用重启进程）
        try:
            engine.run(user_input)
        except Exception as e:
            log = logging.getLogger("claw")
            log.error("[CLI] 本轮运行失败，已返回终端等待下一次输入: %s", e)


def main():
    # 先加载 .env 再做校验：这样用户可以只写 .env 而不设系统环境变量。
    load_dotenv_file(PROJECT_ROOT / ".env")

    if not os.getenv("DEEPSEEK_API_KEY"):
        sys.exit("请先配置 DEEPSEEK_API_KEY 环境变量（或写入项目根目录的 .env）")

    work_dir = PROJECT_ROOT / "workspace"
    work_dir.mkdir(exist_ok=True)
    prepare_files(work_dir)

    # 默认开启慢思考（两阶段 ReAct）；设 CLAW_THINKING=0 可退回单阶段
    # 默认值取 1 而不是 0，是因为作业要求展示"先规划再行动"的效果。
    enable_thinking = os.getenv("CLAW_THINKING", "1") != "0"

    llm_provider = build_provider()
    eng = build_engine(str(work_dir), llm_provider, enable_thinking)
    repl(eng)


if __name__ == "__main__":
    main()
