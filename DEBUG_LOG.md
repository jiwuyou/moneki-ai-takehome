# 第二关调试记录

## 基线

- commit：`357bb72`
- 命令：`python3 eval/run_eval.py --base-url http://127.0.0.1:8000 --questions eval/public_questions.jsonl`
- 初始结果：`43.00 / 100.00`
- `make test`：`20 passed`
- 主要失败：检索 7 题、纯文档 8 题、版本 3 题、混合 5 题、多轮 3 题中的大部分、安全 2 题。

## 缺陷与验证

### 1. 中文问题没有有效分词

- 现象：R01、R04、R05 等问题的检索结果是零分 padding 文档，英文邮件和 HTML FAQ 不在 top-k。
- 假设：BM25 权重或元数据过滤过严。
- 验证：原 tokenizer 把整句中文按空白切成一个 token，例如“发票怎么开”只有一个词；索引中没有同样的整句 token，coverage 为 0。
- 根因：`starter/kbqa/tokenizer.py` 只按空白分词。
- 修复：改为中文二元组与英文/数字词混合分词，并让索引版本失效。
- 回归：`test_retrieval_loads_legacy_html_txt_and_returns_gold_documents`；公开检索题从 8/15 提升到 15/15。

### 2. 检索结果没有应用排除条件且错误覆盖 doc_id

- 现象：已废止文档和无关文档占据结果；命中对象的 `doc_id` 与实际 chunk 不一致。
- 假设：版本排序权重不够。
- 验证：`Retriever.search` 先在所有 chunk 上打分，`allowed` 包含被过滤文档；构造 `Hit` 后又按排序位置覆盖 `hit.doc_id`。
- 根因：`starter/kbqa/retriever.py` 的 `allowed` 和 hit 组装逻辑。
- 修复：先按 doc_id 构造 allowed chunk 集合，保留 chunk 自身 doc_id。
- 回归：公开 R01/R04/R05/R10/R11/R13/R15 全部通过。

### 3. 索引切块丢失文档尾部和 Markdown 表格结构

- 现象：KB-061、KB-040 的答案句和表格内容无法引用；KB-028 的目标数字、KB-022 的赔付金额命中不稳定。
- 假设：引用定位或排序错误。
- 验证：旧 `range(0, len(text) - CHUNK_SIZE, CHUNK_SIZE)` 会丢弃最后不足一个块的正文；表格被普通文本切断。
- 根因：`starter/kbqa/chunker.py`。
- 修复：覆盖完整尾块，表格作为独立 chunk 保存表头和行结构。
- 回归：C02、C04、C05、H03、T02 通过；第二关新增测试覆盖 HTML/TXT/表格。

### 4. 文档问题被“多少/多久/几”错误路由到数据库

- 现象：C01、C06、C08、V02 原本返回全区间经营数字或数据区间拒答。
- 假设：检索没有命中。
- 验证：planner 在分类完成后又无条件把包含“多少/多久/几”的问题改成 `data/summary`。
- 根因：`starter/kbqa/planner.py` 的统一数字路由覆盖了 doc/target/price/anomaly 分类。
- 修复：保留前面的文档意图分类，不再二次覆盖。
- 回归：全部纯文档和版本题通过。

### 5. 文档候选按升序选择低分事实

- 现象：C07 命中 KB-029，但回答选择了较弱的片段，漏掉“毛利率低于 35%”。
- 假设：检索命中错误。
- 验证：`_doc_block` 按 `score` 升序排序，最弱候选先被引用。
- 根因：`starter/kbqa/answerer.py`。
- 修复：按分数降序选择，并在原因问题中合并包含关键原因和阈值的连续原文。
- 回归：C07 通过，全部公开题最终 100/100。

### 6. session 历史没有按 session_id 隔离

- 现象：多轮追问无法继承上一轮上下文，或不同会话可能互相污染。
- 假设：follow-up 规则没有识别“那 7 月呢”。
- 验证：`SessionStore.history/append` 原来使用单一列表，完全忽略 `session_id`；Service 也没有把 history 传给 planner。
- 根因：`starter/kbqa/sessions.py` 和 `starter/kbqa/service.py`。
- 修复：按 session_id 保存最近轮次，planner 接收历史；无上文的追问仍返回 clarify。
- 回归：T01/T02/T03 全部通过，新增 `test_session_followups_are_isolated_and_inherit_context`。

### 7. 知识库提示注入和写操作未在 planner 入口拒绝

- 现象：S02/S03 的破坏性请求会被当作文档检索，返回包含数字的无关引用。
- 假设：sanitize 只需要过滤知识库文本即可。
- 验证：`entities.is_destructive` 与 `is_prompt_probe` 已存在，但 planner 没有调用。
- 根因：planner 没有在规划入口执行安全拒答。
- 修复：在 planner 入口先拒绝删除/修改/SQL 写操作和提示词/表结构探测；知识库指令句在 chunk/unit 层过滤。
- 回归：S01/S02/S03 全部通过，指标基线保持不变。

## 最终验证

- `make test`：`25 passed`（1 个既有的 Starlette/httpx 弃用警告）。
- 公开评测：`100.00 / 100.00`。
- 评测覆盖：指标、检索、文档、版本、混合、多轮、拒答、安全和健康检查。
- 模型 API：未配置，仍在 mock 模式完成第二关。
