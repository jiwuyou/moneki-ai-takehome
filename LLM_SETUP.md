# LLM 接入说明

## 1. 用了什么

- 协议：OpenAI 兼容的 Chat Completions。
- 接口：`POST {LLM_BASE_URL}/chat/completions`。
- 默认开发模式：未配置 Key 时使用本地 mock/RAG 路径。
- 评审模型：DeepSeek `deepseek-flash`。
- HTTP 客户端：`httpx`，版本由 `starter/requirements.txt` 管理。
- 工具调用：OpenAI function calling 格式，工具定义来自 `starter/kbqa/toolspec.py`。

## 2. 配置从哪里读

| 变量 | 含义 | 默认值 |
|---|---|---|
| `LLM_BASE_URL` | 模型服务地址，不自动补 `/v1` | 空值 |
| `LLM_API_KEY` | Bearer API Key | 空值 |
| `LLM_MODEL` | 模型名 | 空值 |
| `LLM_TIMEOUT` | 单次模型调用超时 | `120` 秒 |
| `CHAT_BUDGET` | 单次 `/api/chat` 总预算 | `150` 秒 |

Key 只从环境变量读取，不进入仓库、数据库、trace 或普通日志。

## 3. 怎么切换成 DeepSeek

在 `starter/` 目录启动服务前设置：

```bash
export LLM_BASE_URL=https://api.deepseek.com
export LLM_API_KEY='替换成评审方提供的Key'
export LLM_MODEL=deepseek-flash
make run
```

只需要重启服务，不需要重新生成清洗表或知识库索引。

没有配置三个模型变量时，服务进入 `mock` 模式；第一关和第二关的指标、检索、模板问答仍可使用。

## 4. 请求如何发送

客户端只访问：

```text
POST {LLM_BASE_URL}/chat/completions
Authorization: Bearer <LLM_API_KEY>
```

请求包含 `model`、`messages`、`max_tokens`，有工具时包含 `tools` 和 `tool_choice=auto`。不发送 `seed`、`n`、`parallel_tool_calls` 等额外参数。

带工具调用的 assistant 消息会整体追加回下一轮 messages，保留 `reasoning_content`、`content` 和 `tool_calls`。

live 文档/混合问题采用两阶段检索：代码先用当前问题和会话主题做一次初始 Retriever 查询；模型看到初始片段后，最多生成一次精炼 `search_kb` 查询；代码执行精炼检索，再由模型基于最终片段和数据工具结果回答。相同回合不会无限重复 `search_kb`。

## 5. 如何观察完整请求

### 预检假模型

不需要真实 Key：

```bash
python3 eval/llm_gateway.py preflight \
  --service-url http://127.0.0.1:8000 \
  --no-wait
```

预检会注入带路径前缀的假模型地址，检查地址、模型名、认证、工具多轮、思考字段、错误和超时行为。

### 真实请求代理

需要联网和上游 Key 时：

```bash
python3 eval/llm_gateway.py proxy \
  --upstream https://api.deepseek.com \
  --log /tmp/llm_traffic.jsonl
```

再将代理打印的地址设置为 `LLM_BASE_URL`。代理日志会记录请求 messages、工具定义和响应摘要；Key 只记录长度，不记录值。

服务自己的 `/api/trace/{trace_id}` 也会记录脱敏后的完整模型请求、每轮工具调用、工具结果、模型输出和校验结果，不记录 Authorization。每次 trace 同时持久化到 `starter/var/traces/{trace_id}.json`，服务重启后仍可读取；`var/` 已被 Git 忽略。

## 6. 没有 Key 时会怎样

- `/api/health`、`/api/metrics/*`、`/api/retrieve` 正常工作。
- `/api/chat` 使用 mock/RAG 路径，不返回 HTTP 500。
- 配置不完整或模型不可用时，live 路径返回 HTTP 200、`answer_type: "refusal"` 和可追踪的错误。

## 7. 超时、重试和异常

- 单次调用超时取 `min(LLM_TIMEOUT, 剩余预算)`。
- `/api/chat` 总预算不超过 180 秒；默认 `CHAT_BUDGET=150`。
- 429、500、503、网络错误和空正文最多重试一次。
- 401、402、非法工具参数、内容过滤和异常 `finish_reason` 不盲目重试。
- `length`、`content_filter`、`insufficient_system_resource`、`aborted` 都按失败处理。
- 允许的正常 `finish_reason` 只有 `stop` 和 `tool_calls`。
- 工具调用最多 4 轮，连续非法参数超过上限后结构化拒答。

## 8. 安全与证据

- 所有数据工具由服务端白名单控制。
- `run_sql` 只允许单条、带 `FROM` 的 `SELECT`/`WITH` 查询，只能访问清洗后的业务表。
- 模型生成的数字必须能在工具结果、问题或有效引用中找到，否则 fallback 到代码模板或拒答。
- 文档引用由代码从真实检索结果中选句并逐字核对，模型不能伪造 quote。
- 文档内容被视为资料，不当作系统指令执行。

## 9. 接入预检结果

使用仓库内 `eval/llm_gateway.py 2.0.0`，将服务配置为带路径前缀的假模型地址后运行：

```bash
python3 eval/llm_gateway.py preflight \
  --service-url http://127.0.0.1:8000 \
  --port 19001 \
  --no-wait \
  --scenarios normal,slow,http_401,empty_content,content_filter,aborted
```

结果：**14 项检查全部通过**。覆盖地址原样传递、模型名、Bearer Key、参数、`max_tokens`、工具定义、多轮 `reasoning_content` 回传、结构化拒答、超时、live health 状态和保持连接场景。完整报告见 [`preflight_report.md`](preflight_report.md) 和 [`preflight_report.json`](preflight_report.json)。
