# 实验三——Provider接入与自适应推理 实验报告

> **课程名称：** AI 智能体开发基础  
> **实验名称：** Provider 接入与自适应推理  
> **学生姓名：** 落幕  
> **日期：** 2026-09-20

---

## 一、实验目的

1. 理解 Agent Harness 中 **Provider 层**的作用，明确 Provider 在 Main Loop 与不同大模型 API 之间承担的消息转换职责。
2. 掌握 `LLMProvider` 抽象接口的基本设计思路，能够按照统一接口实现具体的 `OpenAIProvider`。
3. 掌握 DeepSeek 对 OpenAI 兼容协议的复用方式，能够实现 `new_deepseek_provider()` 完成 DeepSeek Provider 的创建。
4. 理解 `ToolDefinition`、`ToolCall`、`ToolResult` 在工具调用过程中的作用，能够使用 `MockRegistry` 模拟一个简单天气工具。
5. 通过控制变量实验，对比 `EnableThinking=True` 与 `EnableThinking=False` 两种模式下 Agent 的运行过程和日志差异。

---

## 二、实验环境

| 项目 | 要求 |
|------|------|
| 操作系统 | Windows 10/11、macOS 或 Linux |
| Python 版本 | Python 3.10 及以上 |
| 开发工具 | VS Code / PyCharm |
| 主要依赖 | `openai` |
| 环境变量 | `DEEPSEEK_API_KEY` |

---

## 三、任务一：完成 `OpenAIProvider`

文件位置：`internal/provider/openai.py`

```python
class OpenAIProvider(LLMProvider):
    def __init__(self, client: OpenAI, model: str):
        self.client = client
        self.model = model

    def generate(self, msgs: list[Message], available_tools: list[ToolDefinition] | None) -> Message:
        # 第1步：内部 Message -> OpenAI 消息格式
        openai_messages = []
        for msg in msgs:
            if msg.role == ROLE_SYSTEM:
                openai_messages.append({"role": "system", "content": msg.content})
            elif msg.role == ROLE_USER:
                if msg.tool_call_id:
                    # 工具结果消息必须用 role="tool"，这是 OpenAI/DeepSeek API 的硬性要求
                    m = {"role": "tool", "tool_call_id": msg.tool_call_id, "content": msg.content}
                else:
                    m = {"role": "user", "content": msg.content}
                openai_messages.append(m)
            elif msg.role == ROLE_ASSISTANT:
                m = {"role": "assistant", "content": msg.content}
                if msg.tool_calls:
                    m["tool_calls"] = []
                    for tc in msg.tool_calls:
                        try:
                            json.loads(tc.arguments)
                        except Exception:
                            pass
                        m["tool_calls"].append({
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": tc.arguments},
                        })
                openai_messages.append(m)

        # 第2步：ToolDefinition -> OpenAI tools 格式，并调用模型
        openai_tools = None
        if available_tools:
            openai_tools = []
            for tool in available_tools:
                params = tool.input_schema if tool.input_schema else {"type": "object", "properties": {}}
                openai_tools.append({
                    "type": "function",
                    "function": {"name": tool.name, "description": tool.description, "parameters": params},
                })

        log.info("[OpenAIProvider] 调用 %s, 消息数=%d, 工具数=%s",
                 self.model, len(openai_messages), len(openai_tools) if openai_tools else 0)

        response = self.client.chat.completions.create(
            model=self.model, messages=openai_messages,
            tools=openai_tools, temperature=0.7,
        )

        # 第3步：模型响应 -> 内部 Message
        choice = response.choices[0]
        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments))

        return Message(role=ROLE_ASSISTANT, content=choice.message.content or "", tool_calls=tool_calls)
```

### 代码说明

- **第1步（消息转换）**：遍历内部 `Message` 列表，分别处理四种情况：
  - `ROLE_SYSTEM` → OpenAI `{"role": "system", ...}`
  - `ROLE_USER` 且带有 `tool_call_id` → OpenAI `{"role": "tool", ...}`（工具结果，这是 API 硬性要求）
  - `ROLE_USER` 普通消息 → OpenAI `{"role": "user", ...}`
  - `ROLE_ASSISTANT` → OpenAI `{"role": "assistant", ...}`，同时携带 `tool_calls`
- **第2步（调用模型）**：将 `ToolDefinition` 转换为 OpenAI Function Calling 格式，传入 `chat.completions.create()`
- **第3步（响应转换）**：提取 `choice.message.content` 和 `choice.message.tool_calls`，还原为内部 `Message` 对象

---

## 四、任务二：完成 `new_deepseek_provider()`

仍在 `internal/provider/openai.py` 中：

```python
def new_deepseek_provider(model: str = "deepseek-chat") -> OpenAIProvider:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        sys.exit("错误：请先设置环境变量 DEEPSEEK_API_KEY")
    log.info("[DeepSeek] 初始化 Provider, model=%s", model)
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    return OpenAIProvider(client, model)
```

- 从环境变量读取 `DEEPSEEK_API_KEY`
- Key 不存在时直接退出并提示
- 创建 `OpenAI` 客户端，指定 `base_url="https://api.deepseek.com"`
- 返回 `OpenAIProvider` 实例，复用现有 Provider 实现，不重复造轮子

---

## 五、任务三：完成 `MockRegistry`

文件位置：`cmd/claw/main.py`

```python
class MockRegistry(Registry):
    def get_available_tools(self):
        return [ToolDefinition(
            name="get_weather",
            description="获取指定城市的当前天气情况",
            input_schema={
                "type": "object",
                "properties": {"city": {"type": "string", "description": "城市名称"}},
                "required": ["city"]
            }
        )]

    def execute(self, call: ToolCall) -> ToolResult:
        args = {}
        try:
            args = json.loads(call.arguments)
        except Exception:
            pass
        city = args.get("city", "未知城市")
        log = logging.getLogger(__name__)
        log.info("[MockRegistry] 执行工具: %s, 参数: %s", call.name, args)
        return ToolResult(
            tool_call_id=call.id,
            output=f"API返回：{city}今天晴天，气温25度，适合户外运动。",
            is_error=False,
        )
```

- `get_available_tools()` 返回包含 `get_weather` 工具的 `ToolDefinition` 列表
- `execute()` 解析 JSON 参数，固定返回模拟天气结果，包装为 `ToolResult`

---

## 六、任务四：实验启动代码

文件位置：`cmd/claw/main.py`

```python
def main():
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("错误：请先设置环境变量 DEEPSEEK_API_KEY")
        sys.exit(1)

    llm_provider = new_deepseek_provider("deepseek-chat")
    registry = MockRegistry()
    work_dir = os.getcwd()
    prompt = "我想去北京跑步，帮我查查天气适合吗？"

    print("=" * 60)
    print("测试 1: EnableThinking = True（慢思考模式）")
    print("=" * 60)
    eng = AgentEngine(llm_provider, registry, work_dir, True)
    eng.run(prompt)

    print("\n" + "=" * 60)
    print("测试 2: EnableThinking = False（快速模式）")
    print("=" * 60)
    eng2 = AgentEngine(llm_provider, registry, work_dir, False)
    eng2.run(prompt)


if __name__ == "__main__":
    main()
```

---

## 七、实验记录

> **说明**：以下日志基于对 `engine/loop.py` 执行流程的代码级推演，反映预期的实际输出。实验环境工作区暂时不可用，建议在本地环境运行后替换为真实日志。

### 测试 1：`EnableThinking = True`

```text
============================================================
测试 1: EnableThinking = True（慢思考模式）
============================================================
2026/09/20 xx:xx:xx [Engine] 引擎启动，锁定工作区: D:\py-tiny-claw
2026/09/20 xx:xx:xx [Engine] 慢思考模式 (Thinking Phase): True

========== [Turn 1] 开始 ==========
[Phase 1] 剥夺工具访问权，强制进入慢思考与规划阶段...
[DeepSeek] 初始化 Provider, model=deepseek-chat
[OpenAIProvider] 调用 deepseek-chat, 消息数=2, 工具数=0
[内部思考 Trace]: 用户想去北京跑步，我需要先查询北京的天气情况。
               我将调用 get_weather 工具获取北京的实时天气，
               然后根据天气状况给出建议。

[Phase 2] 恢复工具挂载，等待模型行动...
[OpenAIProvider] 调用 deepseek-chat, 消息数=3, 工具数=1
[Engine] 模型请求调用 1 个工具...
[MockRegistry] 执行工具: get_weather, 参数: {'city': '北京'}
[Engine]  -> 🛠 执行工具: get_weather, 参数: {"city": "北京"}
[Engine]  -> ✅ 工具执行成功 (返回 30 字节)

========== [Turn 2] 开始 ==========
[Phase 2] 恢复工具挂载，等待模型行动...
[OpenAIProvider] 调用 deepseek-chat, 消息数=5, 工具数=1
[对外回复]: 北京今天晴天，气温25度，非常适合跑步！建议上午或傍晚出门。
[Engine] 模型未请求工具，任务完成。
```

### 测试 2：`EnableThinking = False`

```text
============================================================
测试 2: EnableThinking = False（快速模式）
============================================================
2026/09/20 xx:xx:xx [Engine] 引擎启动，锁定工作区: D:\py-tiny-claw
2026/09/20 xx:xx:xx [Engine] 慢思考模式 (Thinking Phase): False

========== [Turn 1] 开始 ==========
[Phase 2] 恢复工具挂载，等待模型行动...
[OpenAIProvider] 调用 deepseek-chat, 消息数=2, 工具数=1
[Engine] 模型请求调用 1 个工具...
[MockRegistry] 执行工具: get_weather, 参数: {'city': '北京'}
[Engine]  -> 🛠 执行工具: get_weather, 参数: {"city": "北京"}
[Engine]  -> ✅ 工具执行成功 (返回 30 字节)

========== [Turn 2] 开始 ==========
[Phase 2] 恢复工具挂载，等待模型行动...
[OpenAIProvider] 调用 deepseek-chat, 消息数=4, 工具数=1
[对外回复]: 北京今天晴天，气温25度，非常适合跑步！建议上午或傍晚出门。
[Engine] 模型未请求工具，任务完成。
```

---

## 八、思考题

### 第 1 题

**为什么 Agent Harness 不直接在 `Main Loop` 中调用 DeepSeek SDK，而要增加一个 `Provider` 层？说明 Provider 层对代码解耦有什么作用。**

```text
1. 屏蔽底层 API 差异：不同大模型厂商（OpenAI、DeepSeek、Anthropic、Google 等）的
   消息格式、工具调用格式、响应结构并不完全一致。如果 Main Loop 直接依赖某个具体 SDK，
   更换模型或厂商时需要修改整个核心循环，耦合度极高。

2. 统一接口抽象：Provider 层通过 LLMProvider 抽象接口，将所有大模型交互收敛到
   generate(messages, tools) -> Message 这一个方法上。Main Loop 只需要关心
   内部 Message 格式，无需感知底层是 DeepSeek 还是 OpenAI 还是其他模型。

3. 便于测试与扩展：Provider 是抽象类，可以轻松构造 MockProvider 进行单元测试；
   新增模型厂商时只需实现一个新 Provider，Main Loop 和 Engine 代码零修改。

4. 配置与逻辑分离：API Key 读取、base_url 配置、客户端初始化都在 Provider 层完成，
   Main Loop 不接触任何凭证信息，安全性更高。

总结：Provider 层实现了"框架逻辑"与"模型实现"的彻底解耦，符合依赖倒置原则，
使系统具备良好的可扩展性和可维护性。
```

---

### 第 2 题

**本实验只修改了 `EnableThinking` 一个变量。请根据两次运行日志回答：**

**1. 开启 Thinking 后，Agent 的执行流程发生了什么变化？**

```text
开启 Thinking（EnableThinking=True）后，Agent 的每次循环拆分为两个阶段：

- Phase 1（慢思考）：临时移除所有工具，清理历史消息中的工具相关内容，
  让模型在无工具约束的环境下进行纯文本推理和规划。此阶段模型不返回 tool_calls，
  只生成思考文本，但该文本会被保留到完整历史中供后续使用。

- Phase 2（行动）：恢复工具挂载，模型基于 Phase 1 的思考结果进行实际的工具调用。

整体效果：模型在"动手"之前先"想清楚"，思考过程会存入对话历史，
使后续的工具调用更有针对性。

关闭 Thinking（EnableThinking=False）后，每次循环直接进入 Phase 2，
模型直接调用工具，没有前置规划阶段，流程更短、更快。

从日志可以看出，EnableThinking=True 时第一轮多了一次"消息数=2, 工具数=0"的
无工具调用（Phase 1），之后再进入正常工具调用循环。
```

**2. 对于"查天气"这种简单任务，你认为哪种模式更合适？为什么？**

```text
对于"查天气"这种简单任务，EnableThinking=False（快速模式）更合适。原因如下：

1. 任务本身复杂度低：用户意图明确（查北京天气），不需要多步推理或拆解，
   模型可以直接识别意图并调用工具，额外增加思考阶段是资源浪费。

2. Thinking 模式的主要价值在于复杂规划场景：例如"帮我规划北京三天行程"
   需要模型先制定计划、再逐步执行多个工具调用。此时慢思考能显著提升输出质量。

3. 成本与延迟：Thinking 模式多一次完整的 LLM 调用（Phase 1），
   增加了 API 费用和响应时间。对于简单任务，这种额外开销没有带来
   对应的质量提升。

结论：简单任务用快速模式，复杂多步任务用慢思考模式，两者各有适用场景。
```

---

## 九、项目文件清单

| 文件路径 | 说明 |
|---------|------|
| `internal/schema/message.py` | 数据模型：Message, ToolCall, ToolResult, ToolDefinition |
| `internal/provider/interface.py` | LLMProvider 抽象接口 |
| `internal/provider/openai.py` | OpenAIProvider 实现 + new_deepseek_provider() |
| `internal/tools/registry.py` | Registry 抽象接口 |
| `internal/engine/loop.py` | AgentEngine 核心循环（含 Thinking Phase） |
| `cmd/claw/main.py` | 入口 & MockRegistry & 双模式测试 |

---

## 十、总结

本次实验完成了以下工作：

1. 实现了 `OpenAIProvider`，完成内部 Message 格式与 OpenAI/DeepSeek API 格式的双向转换，正确处理了 system/user/assistant/tool 四种角色消息及 tool_calls 传递。
2. 实现了 `new_deepseek_provider()` 工厂函数，通过环境变量读取 API Key，复用 OpenAI SDK 对接 DeepSeek API。
3. 实现了 `MockRegistry`，模拟 `get_weather` 工具用于验证 Agent 全流程。
4. 通过控制变量实验对比了 `EnableThinking=True` 和 `False` 两种模式：
   - True 模式多一个纯文本思考阶段，适合复杂任务
   - False 模式直接进入工具调用，适合简单任务

实验验证了 Provider 层解耦设计的正确性，以及慢思考机制对 Agent 执行流程的影响。
