# internal/tools/write_file.py
# 对应 Go 版: internal/tools/write_file.go
# 第 6 章：write_file 工具 —— 创建或整体覆盖写入文件。
import json
import os

from internal.schema.message import ToolDefinition
from internal.tools.registry import BaseTool


class WriteFileTool(BaseTool):
    # 与 read_file 相同：注入工作区根目录，模型只给相对路径。
    def __init__(self, work_dir: str):
        self.work_dir = work_dir

    def name(self) -> str:
        return "write_file"

    def definition(self) -> ToolDefinition:
        # 明确告诉模型"会覆盖"：write_file 是整体重写，
        # 只想改几行应该用 edit_file，这个差别写在描述里能减少误用。
        return ToolDefinition(
            name=self.name(),
            description="创建或覆盖写入一个文件。如果目录不存在会自动创建。请提供相对于工作区的相对路径。",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要写入的文件路径，如 src/main.py",
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的完整文件内容",
                    },
                },
                "required": ["path", "content"],
            },
        )

    def execute(self, args: str) -> str:
        try:
            input_args = json.loads(args)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"参数解析失败: {e}") from e

        path = input_args.get("path", "")
        content = input_args.get("content", "")

        full_path = os.path.join(self.work_dir, path)

        # 自动创建父目录（对应 Go 的 os.MkdirAll）
        # 模型经常写 logs/xxx.log 这种带子目录的路径，若不建目录会直接失败。
        try:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
        except OSError as e:
            raise RuntimeError(f"创建父目录失败: {e}") from e

        # 用 "w" 模式即整体覆盖，不做追加：这样模型"重写整个文件"的语义
        # 与 write_file 这个名字一致，也避免旧内容残留造成混乱。
        try:
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as e:
            raise RuntimeError(f"写入文件失败: {e}") from e

        return f"成功将内容写入到文件: {path}"
