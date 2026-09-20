# internal/provider/openai.py
# 对应 Go 版: internal/provider/openai.go
# 第 4 章：接入真实的 OpenAI 兼容协议 Provider（DeepSeek）
import json
import logging
import os
import sys
from openai import OpenAI

from .interface import LLMProvider
from ..schema.message import Message, ROLE_SYSTEM, ROLE_USER, ROLE_ASSISTANT, ToolCall, ToolDefinition

log = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    """OpenAI 兼容协议的 Provider 实现"""

    def __init__(self, client: OpenAI, model: str):
        self.client = client
        self.model = model

    def generate(self, msgs: list[Message], available_tools: list[ToolDefinition] | None) -> Message:
        """
        核心生成逻辑，三步走：
        1. 内部 Message -> OpenAI 消息格式
        2. 调用模型 API
        3. OpenAI 响应 -> 内部 Message
        """

        # ==================================================
        # 第 1 步：内部 Message -> OpenAI 消息格式
        # ==================================================
        openai_messages = []
        for msg in msgs:
            if msg.role == ROLE_SYSTEM:
                openai_messages.append({
                    "role": "system",
                    "content": msg.content,
                })
            elif msg.role == ROLE_USER:
                # 工具结果消息需要携带 tool_call_id
                openai_msg = {"role": "user", "content": msg.content}
                if msg.tool_call_id:
                    openai_msg["tool_call_id"] = msg.tool_call_id
                openai_messages.append(openai_msg)
            elif msg.role == ROLE_ASSISTANT:
                openai_msg = {"role": "assistant", "content": msg.content}
                # 处理 tool_calls
                if msg.tool_calls:
                    openai_msg["tool_calls"] = []
                    for tc in msg.tool_calls:
                        openai_msg["tool_calls"].append({
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": tc.arguments,
                            }
                        })
                openai_messages.append(openai_msg)

        # ==================================================
        # 第 2 步：ToolDefinition -> OpenAI tools 格式并调用模型
        # ==================================================
        openai_tools = None
        if available_tools:
            openai_tools = []
            for tool in available_tools:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema or {
                            "type": "object",
                            "properties": {},
                        },
                    }
                })

        log.info("[OpenAIProvider] 调用模型: %s", self.model)
        log.info("[OpenAIProvider] 消息数量: %d", len(openai_messages))
        if openai_tools:
            log.info("[OpenAIProvider] 可用工具: %d 个", len(openai_tools))

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                tools=openai_tools,
                temperature=0.7,
            )
        except Exception as e:
            log.error("[OpenAIProvider] API 调用失败: %s", e)
            raise

        # ==================================================
        # 第 3 步：模型响应 -> 内部 Message
        # ==================================================
        choice = response.choices[0]
        message_obj = choice.message

        # 提取 content
        content = message_obj.content or ""

        # 提取 tool_calls
        tool_calls = []
        if message_obj.tool_calls:
            for tc in message_obj.tool_calls:
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=tc.function.arguments,
                ))

        result_msg = Message(
            role=ROLE_ASSISTANT,
            content=content,
            tool_calls=tool_calls,
        )

        log.info("[OpenAIProvider] 响应内容: %s", content[:100] if content else "(无内容)")
        if tool_calls:
            log.info("[OpenAIProvider] 工具调用: %d 个", len(tool_calls))

        return result_msg


def new_deepseek_provider(model: str = "deepseek-chat") -> OpenAIProvider:
    """
    构造 DeepSeek Provider。
    DeepSeek 兼容 OpenAI 协议，复用 OpenAIProvider。
    """
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        sys.exit("错误：请先设置环境变量 DEEPSEEK_API_KEY")

    log.info("[DeepSeek] 初始化 Provider, model=%s", model)
    log.info("[DeepSeek] API Base: https://api.deepseek.com")

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
    )

    return OpenAIProvider(client, model)
