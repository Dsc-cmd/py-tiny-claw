# internal/provider/openai.py
# 对应 Go 版: internal/provider/openai.go
# 使用 OpenAI 官方 Python SDK（Chat Completions 协议），Base URL 指向智谱的兼容端点。
import os

import openai

from internal.provider import interface
from internal.provider.interface import LLMProvider
from internal.schema.message import (
    Message,
    ROLE_ASSISTANT,
    ROLE_SYSTEM,
    ROLE_USER,
    ToolCall,
    ToolDefinition,
)


class OpenAIProvider(LLMProvider):
    def __init__(self, client: openai.OpenAI, model: str):
        self.client = client
        self.model = model

    def generate(self, msgs: list[Message], available_tools: list[ToolDefinition] | None) -> Message:
        # 这一层只做"翻译"，不掺任何业务判断：
        # 内部统一 Message -> OpenAI Chat Completions 格式，再把响应翻回来。
        # 1. 把内部统一格式的消息翻译为 OpenAI Chat Completions 的格式
        openai_msgs = []

        for msg in msgs:
            if msg.role == ROLE_SYSTEM:
                openai_msgs.append({"role": "system", "content": msg.content})

            elif msg.role == ROLE_USER:
                if msg.tool_call_id != "":
                    # 工具执行结果在 OpenAI 协议中是独立的 "tool" 角色消息
                    # （Anthropic 则是塞进 user 消息的 tool_result block，差异就在这里被吸收）
                    openai_msgs.append({
                        "role": "tool",
                        "content": msg.content,
                        "tool_call_id": msg.tool_call_id,
                    })
                else:
                    openai_msgs.append({"role": "user", "content": msg.content})

            elif msg.role == ROLE_ASSISTANT:
                ast_param: dict = {"role": "assistant"}

                if msg.content != "":
                    ast_param["content"] = msg.content

                if len(msg.tool_calls) > 0:
                    tool_calls = []
                    for tc in msg.tool_calls:
                        tool_calls.append({
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                # OpenAI 协议中 arguments 本身就是 JSON 字符串
                                "arguments": tc.arguments,
                            },
                        })
                    ast_param["tool_calls"] = tool_calls

                openai_msgs.append(ast_param)

        # 2. 翻译工具定义为 function tool 格式
        openai_tools = []
        for tool_def in available_tools or []:
            params_schema = tool_def.input_schema if isinstance(tool_def.input_schema, dict) else {}

            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool_def.name,
                    "description": tool_def.description,
                    "parameters": params_schema,
                },
            })

        params = {
            "model": self.model,
            "messages": openai_msgs,
        }
        if openai_tools:
            params["tools"] = openai_tools
            # 关键副作用：只有当工具清单非空时才会写入 tools 字段。
            # 因此引擎在慢思考阶段传 None（或空列表）时，这一次请求里
            # 模型根本看不到任何函数定义，只能输出纯文本规划——
            # "剥夺工具访问权"就是靠这一行实现的，而不是靠提示词约束。

       ##########################  调用大模型执行  ###############################
        try:
            resp = self.client.chat.completions.create(**params)
        except Exception as e:
            raise RuntimeError(f"OpenAI/Zhipu API 请求失败: {e}") from e
        if len(resp.choices) == 0:
            raise RuntimeError("API 返回了空的 Choices")

        # 3. 把模型响应翻译回内部统一格式
        choice = resp.choices[0].message
        result_msg = Message(
            role=ROLE_ASSISTANT,
            content=choice.content or "",
        )

        for tc in choice.tool_calls or []:
            if tc.type == "function":
                result_msg.tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=tc.function.arguments,
                ))

        return result_msg


def new_zhipu_openai_provider(model: str) -> OpenAIProvider:
    """对应 Go 版的 NewZhipuOpenAIProvider 构造函数"""
    api_key = os.getenv("ZHIPU_API_KEY")
    if not api_key:
        raise RuntimeError("请设置 ZHIPU_API_KEY 环境变量")
    base_url = "https://open.bigmodel.cn/api/paas/v4/"
    return OpenAIProvider(
        client=openai.OpenAI(api_key=api_key, base_url=base_url),
        model=model,
    )


def new_deepseek_provider(model: str) -> OpenAIProvider:
    """DeepSeek 官方 API。

    DeepSeek 走的同样是 OpenAI Chat Completions 兼容协议，
    所以上面那套消息与工具翻译逻辑可以原样复用，只需换 Base URL 与密钥。
    可用模型：deepseek-v4-flash（快、便宜）、deepseek-v4-pro（更强）。
    """
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError(
            "请设置 DEEPSEEK_API_KEY 环境变量"
            "（也可以写进项目根目录的 .env 文件，会被自动加载）"
        )
    base_url = "https://api.deepseek.com/v1"
    # DeepSeek 走 OpenAI 兼容协议，所以上面那套消息/工具翻译可以原样复用，
    # 只需换 base_url 与 api_key；这也是"引擎与厂商解耦"带来的直接收益。
    return OpenAIProvider(
        client=openai.OpenAI(api_key=api_key, base_url=base_url),
        model=model,
    )


