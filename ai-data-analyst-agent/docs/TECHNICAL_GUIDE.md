# InsightAI V3 技术学习指南

## 从“查数据”到“解释数据”

新增 `business_insights.py` 是当前最值得先读的模块。它没有再查询数据库，也不依赖模型猜测，而是读取 `AnalysisResult` 的同一份结果，计算有业务含义的比较：

- 首尾变化率：`(last - first) / first × 100`，只有起点为正数时才输出。
- 最近月份变化：仅在最后两个观测月份相邻时计算，并提示核对月份是否完整。
- 分组差距：领先组数值减去最低组数值。
- 分组占比：仅对非负、可加总的指标，用已返回分组之和作为分母。平均值或转化率不计算这种份额。
- 每单收入：返回结果同时有收入和已交付订单数，且订单数为正时计算。
- 变量关系：报告成对有效样本数、Pearson 系数，并明确不能据此推断因果。

每条 `BusinessInsight` 包含 `id/kind/title/text/evidence/next_step`。先计算数字，再由模板生成解读与核查建议。`evidence` 适合测试和 API 使用，`text` 适合人阅读。这比让模型先写故事再寻找数字更容易验证。

界面由 `analysis_workspace.py` 负责整合：业务解读在前，统计依据与 SQL 按需展开；图表下拉框切换指标，始终读取同一快照。回答使用稳定的消息编号作为 widget key，所以切换图表触发 Streamlit rerun 后，不会跳回默认视角。

## 建议阅读顺序

1. `app/database/db.py`：连接、查询、返回 tuple，以及 SQLite authorizer。
2. `app/agent/sql_safety.py`：SQLGlot AST、异常类型、表白名单、LIMIT。
3. `app/analytics/advanced_result.py`：dataclass、classmethod、property、数据所有权。
4. `app/analytics/advanced_profile.py`：Pandas 统计、缺失值、分位数、相关系数。
5. `app/analytics/advanced_visualization.py`：配置对象、配置校验、groupby、Plotly。
6. `app/agent/graph.py`：TypedDict、节点、条件边、有界重试。
7. `app/analytics/advanced_report.py`：如何约束模型的输出空间。
8. `app/ui/pages/2_Advanced_Analytics.py` 和 `app/ui/advanced_components.py`：页面与可重用视图。
9. 新增 tests：从具体输入和断言理解模块契约。

## 从 SQL 到数据快照

```python
from app.analytics.advanced_service import analyze_sql
from app.analytics.advanced_visualization import AdvancedChartSpec, create_advanced_chart

result = analyze_sql(
    "SELECT status, SUM(total_amount) AS revenue FROM orders GROUP BY status",
    question="Compare revenue by order status",
)
print(result.summary())
figure = create_advanced_chart(result, AdvancedChartSpec("bar", "status", "revenue", "sum"))
```

`analyze_sql` 不接收任意数据库路径或写连接。它调用现有数据库配置，验证 SQL，然后只执行一次。表名来自数据库接口。`AnalysisResult` 根据该次结果建立 DataFrame，统计和可视化不会重新执行 SQL。

## 为什么复制 DataFrame

Pandas 对象是可变对象。若图表把日期字符串原地转换，后续导出可能与 SQL 原结果不同。`dataframe`、`rows`、`profile` 属性返回副本，图表在副本上清洗。dataclass 的 frozen 仅禁止重新赋值，不能自动冻结内部 DataFrame；因此 `_frame` 与 `_profile` 是约定私有字段，调用方必须使用公开属性。

`snapshot_id` 是列名与行值的 SHA-256，写在图表 metadata 和 JSON 中，方便核对数据来源。它不是数据库版本号，也不是权限控制。

## 聚合与统计范围

`groupby("status")["revenue"].sum()` 得到分组之和；`size()` 得到每组行数；两者含义不同。查询已经聚合时，再按相同类别求和通常保留指标，但用户仍需理解 SQL 粒度。系统不从列名臆测“客户数”等业务定义。

SQL LIMIT 限制返回行数，而统计描述加载的结果。例如，查询返回每月收入时 mean 是月收入均值，不能叫平均订单金额。报告使用原列别名和统计名称，避免偷换含义。

## 错误和测试

语法错误可进入有上限的模型修复；安全错误必须终止。修复后再次验证，不能让模型成为权限边界。执行时数据库只读模式与 authorizer 提供第二层保护。

可从测试中学习依赖替换：`monkeypatch` 用本地假函数替换网络调用，验证发生哪些调用、未发生哪些调用。UI 使用 Streamlit 自带 AppTest 执行实际页面，检查异常、表单和 session_state；这不等于真实浏览器视觉验证，两者各有用途。

## 练习方向

先运行完整测试，再尝试新增一个稳定的业务统计字段，为其添加手工可算的测试。下一步可做查询耗时预算和取消、统计样本量展示、更多 Demo 问题。任何新增模型功能都应首先明确可接受输出与验证方法。
