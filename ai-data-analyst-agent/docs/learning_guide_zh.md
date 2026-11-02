# 中文学习指南：从运行到理解 AI Data Analyst Agent

建议每天投入 1–2 小时。先运行，再阅读代码，最后自己修改。

## Day 1：启动项目

目标：在 Windows 11 + VS Code 上运行 Streamlit。

1. 在 VS Code 打开项目文件夹。
2. 打开 PowerShell Terminal。
3. 创建并激活 `.venv`。
4. 安装 `requirements.txt`。
5. 运行 `python scripts/init_db.py`。
6. 运行 `python -m streamlit run app/ui/streamlit_app.py`。
7. 尝试侧边栏中的示例问题。

检查点：你能打开网页，并看到 SQL、结果表格和图表。

## Day 2：理解数据库和 SQL

阅读：

- `app/database/seed.py`
- `app/database/db.py`

理解：

- 什么是 relational database？
- Primary Key 和 Foreign Key 有什么作用？
- 为什么订单和订单商品需要分成不同的表？
- JOIN 如何连接 customers、orders、order_items、products？
- GROUP BY、SUM、COUNT、ORDER BY 分别做什么？

练习：自己写一个 SQL，统计每个城市的订单数量。

## Day 3：理解 LLM 如何生成 SQL

阅读：

- `app/agent/llm.py`
- `app/agent/demo_mode.py`

理解：

- System Prompt 和 User Prompt 的区别。
- Schema 为什么要提供给 LLM？
- 为什么要求模型返回 JSON？
- 为什么模型生成的 SQL 不能直接执行？
- Demo Mode 与 OpenAI Mode 有什么区别？

练习：修改 Prompt，要求模型生成 SQL 时优先使用明确列名而不是 SELECT *。

## Day 4：理解 SQL 安全性

阅读：

- `app/agent/sql_safety.py`
- `app/database/db.py` 中的 authorizer

理解：

- SQL Parsing 是什么？
- 为什么只允许 SELECT？
- Table Allow-list 是什么？
- Read-only connection 为什么重要？
- LIMIT 为什么重要？

练习：在测试中增加一个访问不存在表的案例，并确认它会被拒绝。

## Day 5：理解 LangGraph

阅读：

- `app/agent/graph.py`

理解：

- StateGraph 是什么？
- Node 和 Edge 有什么区别？
- Conditional Edge 如何决定下一步？
- 为什么要把 SQL Validation 和 Query Execution 分开？
- Error Handler 如何工作？

练习：增加一个 `log_question` Node，记录用户问题（不要记录敏感信息）。

## Day 6：理解前后端

阅读：

- `app/ui/streamlit_app.py`
- `app/api/main.py`

理解：

- Streamlit 如何维护聊天状态？
- FastAPI Endpoint 是什么？
- Request Model 和 Response Model 有什么作用？
- API 与 UI 为什么分开？

练习：新增一个 `/version` API Endpoint。

## Day 7：测试和小型实验

阅读：

- `tests/`
- `docs/evaluation.md`

执行：

```powershell
python -m pytest
```

练习：

1. 增加 10 个测试问题。
2. 记录正确执行的数量。
3. 计算 SQL Execution Accuracy。
4. 记录平均响应时间。
5. 写下失败案例和改进方案。

## 面试时你应该能解释

- 从用户输入到 SQL 执行，系统经过哪些步骤？
- 为什么使用 LangGraph？
- 为什么不直接让 LLM 执行 SQL？
- 如何阻止模型执行危险查询？
- 如何评估 Text-to-SQL 的准确率？
- SQL Exact Match 与 Execution Accuracy 有什么区别？
- 如何处理模型返回无效 SQL？
- 如何降低 LLM Token 成本？

## 最重要的学习规则

不要只复制代码。每完成一个模块，尝试不看原代码重新画出流程，并用自己的话解释它的输入、输出和失败情况。
