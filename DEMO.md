# 真实模型演示说明

## 1. 使用 DeepSeek live 模式启动

Key 只通过当前 shell 的环境变量注入，不写入仓库：

```bash
export LLM_BASE_URL=https://api.deepseek.com
export LLM_API_KEY='替换成你自己的新Key'
export LLM_MODEL=deepseek-flash

cd starter
make rebuild
make run
```

打开：<http://127.0.0.1:8000/>

先确认服务确实使用真实模型：

```bash
curl -sS http://127.0.0.1:8000/api/health
```

响应中应包含：

```json
{"status":"ok","llm_mode":"live"}
```

## 2. 演示混合问题

在“运营助手”中输入：

```text
618 当天 S02 的牛肉poke 卖了多少份？达到目标了吗？
```

预期展示：

- DeepSeek 先通过工具查询数据库实际销量。
- DeepSeek 再调用知识库检索活动目标。
- 代码根据工具结果和 KB-023 生成已达标/未达标结论。
- `data_evidence` 展示真实数据库查询和结果。
- `citations` 展示 KB-023 的逐字引用。

也可以直接调用 API：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/chat \
  -H 'content-type: application/json' \
  -d '{"session_id":"demo-live","question":"618 当天 S02 的牛肉poke 卖了多少份？达到目标了吗？"}'
```

响应至少包含：

```json
{
  "answer_type": "hybrid",
  "citations": [{"doc_id": "KB-023", "quote": "...目标销量 120 份..."}],
  "data_evidence": [{"tool": "query_metrics", "params": {"store_id": "S02"}, "result": {"qty": 125}}],
  "trace_id": "t-..."
}
```

具体数字以当前数据和当次模型调用结果为准。

### 完整示例

提问：

```text
618 当天 S02 的牛肉poke 卖了多少份？达到目标了吗？
```

系统先执行数据库工具：

```json
{
  "tool": "query_metrics",
  "params": {
    "start": "2026-06-18",
    "end": "2026-06-18",
    "store_id": "S02",
    "product_id": "P06"
  },
  "result": {
    "qty": 125,
    "net_revenue": 3625.0,
    "orders": 53
  }
}
```

然后检索活动方案 `KB-023`，取得目标：

```json
{
  "doc_id": "KB-023",
  "quote": "当天牛肉poke 目标销量 120 份。"
}
```

最终回答示例：

```text
618 当天 S02 的牛肉poke 售出 125 份，活动目标是 120 份，已达标，超出 5 份。
```

接口响应中的 `answer_type` 为 `hybrid`，同时包含上面的 `data_evidence` 和 `citations`。回答里的 125 来自数据库，120 来自 KB-023，5 由代码计算得出。

## 3. 查看真实模型调用过程

回答完成后，页面会自动读取 `/api/trace/{trace_id}`，展示真实 live 请求的：

- Planner 结果。
- 初始检索和精炼检索。
- 每轮 DeepSeek 工具调用及参数。
- 每个工具结果。
- `reasoning_content` 是否存在（不会展示给最终用户）。
- 脱敏后的完整模型请求和原始输出。
- 每一步耗时。
- 错误和 fallback。

点击“新建会话”可以验证不同 `session_id` 不会串线；在同一会话中输入“那 7 月呢？”可以验证追问继承。

## 4. 不使用真实模型时

删除三个 `LLM_*` 环境变量后重启，服务会进入 mock 模式。mock 模式用于离线开发和回归；本演示的目标是展示配置 Key 后的 live 模式。
