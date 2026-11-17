## DeepSeek返回的消息格式

- 字段含义
```
resp.id                              请求 ID
resp.object                         "chat.completion"
resp.created                        Unix 时间戳
resp.model                          实际使用的模型
resp.system_fingerprint             后端配置指纹

resp.choices[0].index               选择项索引
resp.choices[0].message.role        assistant
resp.choices[0].message.content     最终回答
resp.choices[0].message.reasoning_content
                                    思考模式下的推理内容
resp.choices[0].message.tool_calls  工具调用数组

resp.choices[0].logprobs            概率信息，通常是 null
resp.choices[0].finish_reason       stop / length / tool_calls 等

resp.usage.completion_tokens
resp.usage.prompt_tokens
resp.usage.prompt_cache_hit_tokens
resp.usage.prompt_cache_miss_tokens
resp.usage.total_tokens
resp.usage.completion_tokens_details.reasoning_tokens
```

- 返回的Json消息
```json
{
  "id": "chatcmpl-xxxxxxxx",
  "object": "chat.completion",
  "created": 1718345013,
  "model": "deepseek-v4-flash",
  "system_fingerprint": "fp_xxxxx",

  "choices": [
    {
      "index": 0,

      "message": {
        "role": "assistant",
        "content": "最终回答内容",

        "reasoning_content": "思考模式下的推理内容",

        "tool_calls": [
          {
            "id": "call_xxxxx",
            "type": "function",
            "function": {
              "name": "get_weather",
              "arguments": "{\"city\":\"上海\"}"
            }
          }
        ]
      },

      "logprobs": null,

      "finish_reason": "stop"
    }
  ],

  "usage": {
    "completion_tokens": 100,
    "prompt_tokens": 200,
    "prompt_cache_hit_tokens": 0,
    "prompt_cache_miss_tokens": 200,
    "total_tokens": 300,

    "completion_tokens_details": {
      "reasoning_tokens": 80
    }
  }
}
```


- provider处理后，保留的形式
```python
Message(
    role=ROLE_ASSISTANT,
    content=choice.content or "",
    tool_calls=[
        ToolCall(
            id=tc.id,
            name=tc.function.name,
            arguments=tc.function.arguments,
        )
    ],
)
```