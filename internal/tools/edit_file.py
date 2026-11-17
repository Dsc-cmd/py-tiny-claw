# internal/tools/edit_file.py
# 对应 Go 版: internal/tools/edit_file.go
# 第 6 章：edit_file 工具 —— 局部字符串替换 + 四级模糊匹配兜底策略。
import json
import os

from internal.schema.message import ToolDefinition
from internal.tools.registry import BaseTool


class EditFileTool(BaseTool):
    # 存在的理由：让模型只给"要改的那几行"，而不是把整个文件重写一遍。
    # 好处是省 token、也不会因为模型记错别处内容而顺手改坏无关代码。
    def __init__(self, work_dir: str):
        self.work_dir = work_dir

    def name(self) -> str:
        return "edit_file"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name(),
            description="对现有文件进行局部的字符串替换。这比重写整个文件更安全、更快速。请提供足够的 old_text 上下文以确保匹配的唯一性。",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要修改的文件路径",
                    },
                    "old_text": {
                        "type": "string",
                        "description": "文件中原有的文本。必须包含足够的上下文，以确保在文件中的唯一性。",
                    },
                    "new_text": {
                        "type": "string",
                        "description": "要替换成的新文本",
                    },
                },
                "required": ["path", "old_text", "new_text"],
            },
        )

    def execute(self, args: str) -> str:
        try:
            input_args = json.loads(args)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"参数解析失败: {e}") from e

        path = input_args.get("path", "")
        old_text = input_args.get("old_text", "")
        new_text = input_args.get("new_text", "")

        full_path = os.path.join(self.work_dir, path)

        # 先整份读出来再在内存里替换，最后整体写回：
        # 这样"匹配失败"时文件一个字节都没动，不会留下改到一半的坏文件。
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                original_content = f.read()
        except OSError as e:
            raise RuntimeError(f"读取文件失败，请确认路径是否正确: {e}") from e

        new_content = fuzzy_replace(original_content, old_text, new_text)

        try:
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except OSError as e:
            raise RuntimeError(f"写回文件失败: {e}") from e

        return f"✅ 成功修改文件: {path}"


def fuzzy_replace(original_content: str, old_text: str, new_text: str) -> str:
    """四级降级匹配：精确 -> 换行符归一化 -> 去首尾空白 -> 逐行去缩进

    为什么要分级：old_text 是模型"凭记忆抄"的，它经常把 CRLF 写成 LF、
    或把缩进多写/少写两个空格。如果只做精确匹配，大量本该成功的修改会失败，
    模型就会反复重试同一段文本。逐级放宽能显著提高一次成功率。
    """
    # L1: 精确匹配
    # 唯一匹配才替换；匹配到多处直接报错，是为了避免"改错位置"——
    # 宁可让模型补上下文再来一次，也不能猜它想改哪一处。
    count = original_content.count(old_text)
    if count == 1:
        return original_content.replace(old_text, new_text, 1)
    if count > 1:
        raise RuntimeError(f"old_text 匹配到了 {count} 处，请提供更多的上下文代码以确保唯一性")

    # L2: 换行符归一化
    # Windows 下文件常是 CRLF，模型多半按 LF 抄；不归一化会"看起来一样却匹配不上"。
    normalized_content = original_content.replace("\r\n", "\n")
    normalized_old = old_text.replace("\r\n", "\n")

    count = normalized_content.count(normalized_old)
    if count == 1:
        return normalized_content.replace(normalized_old, new_text, 1)

    # L3: Trim Space 匹配
    trimmed_old = normalized_old.strip()
    if trimmed_old != "":
        count = normalized_content.count(trimmed_old)
        if count == 1:
            return normalized_content.replace(trimmed_old, new_text, 1)

    # L4: 逐行去缩进匹配
    # 最后一级兜底：只比较"去掉首尾空白后"的每一行，
    # 容忍模型整体缩进偏移；仍然要求唯一命中，否则报错让它补上下文。
    return line_by_line_replace(normalized_content, normalized_old, new_text)


def line_by_line_replace(content: str, old_text: str, new_text: str) -> str:
    content_lines = content.split("\n")
    old_lines = old_text.strip().split("\n")

    if len(old_lines) == 0 or len(content_lines) < len(old_lines):
        raise RuntimeError("找不到该代码片段")

    # 每一行都去掉首尾空白后再比较，容忍模型给出的缩进偏差
    old_lines = [line.strip() for line in old_lines]

    match_count = 0
    match_start_index = -1
    match_end_index = -1

    for i in range(len(content_lines) - len(old_lines) + 1):
        is_match = True
        for j in range(len(old_lines)):
            if content_lines[i + j].strip() != old_lines[j]:
                is_match = False
                break

        if is_match:
            match_count += 1
            match_start_index = i
            match_end_index = i + len(old_lines)

    if match_count == 0:
        raise RuntimeError("在文件中未找到 old_text，请检查内容和缩进")
    if match_count > 1:
        raise RuntimeError(f"模糊匹配到了 {match_count} 处代码，请提供更多上下文以定位")

    new_content_lines = (
        content_lines[:match_start_index]
        + [new_text]
        + content_lines[match_end_index:]
    )

    return "\n".join(new_content_lines)
