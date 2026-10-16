# internal/tools/write_file.py
# 对应 Go 版: internal/tools/write_file.go
# 第 6 章：write_file 工具 —— 创建或整体覆盖写入文件。
import json
import os

from internal.schema.message import ToolDefinition
from internal.tools.registry import BaseTool


class WriteFileTool(BaseTool):
    def __init__(self, work_dir: str):
        self.work_dir = work_dir

    def name(self) -> str:
        return "write_file"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name(),
            description="创建或覆盖写入一个文件。如果目录不存在会自动创建。请提供相对于工作区的相对路径。",
            # TODO：请补全 input_schema
            # 要求：type 为 object，包含两个 string 类型的参数 path 和 content，二者都必填
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要写入的文件路径（相对于工作区的相对路径）",
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入文件的完整内容",
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

        # ==================================================
        # 要求：
        # 1. 从 input_args 中取出 path 和 content
        # 2. 用 os.path.join 将 path 拼接到 self.work_dir 下
        # 3. 自动创建父目录（提示：os.makedirs(..., exist_ok=True)）
        # 4. 以 utf-8 编码写入文件，失败时抛出 RuntimeError
        # 5. 返回 "成功将内容写入到文件: xxx"
        # ==================================================
        file_path = input_args.get("path", "")
        content = input_args.get("content", "")
        full_path = os.path.join(self.work_dir, file_path)

        try:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as e:
            raise RuntimeError(f"写入文件失败: {e}") from e

        return f"成功将内容写入到文件: {file_path}"
