# internal/tools/bash.py
# 对应 Go 版: internal/tools/bash.go
# 第 6 章：bash 工具 —— Agent 最强大的"万能手"，可以执行任意 shell 命令。
import json
import subprocess

from internal.schema.message import ToolDefinition
from internal.tools.registry import BaseTool


class BashTool(BaseTool):
    # 注意：bash 是唯一能执行任意命令的工具，它可能改文件、装依赖、起进程，
    # 所以在引擎里被归为"写"操作，永远不会和别的工具并发执行。
    def __init__(self, work_dir: str):
        self.work_dir = work_dir

    def name(self) -> str:
        return "bash"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name(),
            description="在当前工作区执行任意的 bash 命令。支持链式命令(如 &&)。返回标准输出(stdout)和标准错误(stderr)。",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 bash 命令",
                    },
                },
                "required": ["command"],
            },
        )

    def execute(self, args: str) -> str:
        try:
            input_args = json.loads(args)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"参数解析失败: {e}") from e

        # 30 秒超时保护，防止模型执行的命令把引擎挂死（对应 Go 的 context.WithTimeout）
        # 不加超时的话，一句 sleep 9999 就能让整个智能体永远卡在这里。
        # 用 ["bash", "-c", cmd] 而不是 shell=True：命令以单参数传入，
        # 避免 Windows/POSIX 的引号解析差异，也便于将来换成别的 shell。
        try:
            proc = subprocess.run(
                ["bash", "-c", input_args.get("command", "")],
                cwd=self.work_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError as e:
            # Windows 上若没有把 Git Bash 加入 PATH，会走到这里
            # 转成中文提示而不是抛原始堆栈：模型看得懂"环境问题"，才不会一直重试同一条命令。
            raise RuntimeError(
                "找不到 bash 可执行文件，请安装 Git Bash 并将其加入 PATH"
            ) from e
        except subprocess.TimeoutExpired as e:
            # stdout/stderr 合并输出（对应 Go 的 CombinedOutput）
            # 超时不抛异常而是"返回带警告的输出"：把已经跑出来的部分日志
            # 交给模型，它就能判断是命令写错还是确实太慢。
            partial = (e.stdout or "") + (e.stderr or "")
            if isinstance(partial, bytes):
                partial = partial.decode("utf-8", errors="replace")
            return partial + "\n[警告: 命令执行超时(30s)，已被系统强制终止。]"

        output_str = proc.stdout + proc.stderr

        # 非 0 退出码也用"正常返回"而不是抛异常：
        # 命令失败是常见现象（比如 grep 没匹配到），让模型读到 stderr 自己决定下一步，
        # 比把它变成异常、走 Registry 的兜底路径更有信息量。
        if proc.returncode != 0:
            return f"执行报错: exit status {proc.returncode}\n输出:\n{output_str}"

        if output_str == "":
            return "命令执行成功，无终端输出。"

        # 与 read_file 同理：终端输出可能极长（比如 cat 一个大日志），
        # 截断是为了不让一次工具结果就把上下文窗口占满。
        MAX_LEN = 8000
        if len(output_str) > MAX_LEN:
            return f"{output_str[:MAX_LEN]}\n\n...[终端输出过长，已截断至前 {MAX_LEN} 字节]..."

        return output_str
