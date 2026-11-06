# Unified workspace, stronger charts and business interpretation

Implemented at the user's request on 2026-11-03. This extends the working V3 implementation rather than replacing its UI, database, Agent or provider configuration.

## User-visible changes

The main page now switches between **业务分析 / 数据探索** (Business analysis / Explore data). Both share the existing settings, language and data source. Data exploration, quality, correlations, SQL and exports are accessible from this main page. The old page URL is retained for compatibility, renamed Data analysis, and links back to the main workspace; it is no longer promoted as an independent "Advanced" product.

Answers lead with business interpretation. Statistical details are folded under "查看统计依据"; raw query rows, SQL and exports are available on demand. Each answer has one chart with a selector for different measures and chart views. Stable message/widget keys preserve the selection across reruns.

Chart presentation now supports sorted horizontal comparison bars with value labels, annotated trend peaks, a time range slider for longer date series, readable correlation values and donut composition. Titles and axes use business-friendly labels; theme matches the main page. Revenue is prioritized over incidental numeric column order, identifiers are excluded from recommended measures, and rates/prices use explicitly unweighted group means instead of being summed. Users can still configure all seven chart types, grouping and aggregation manually. Existing chart-engine interfaces were not changed.

## Business interpretation

`app/analytics/business_insights.py` computes typed facts and renders clear text:

- Observed endpoint change and highest observed period.
- Latest adjacent-month change, with a period-completeness caveat.
- Group leader, gap to the lowest group and share of the returned groups when mathematically appropriate.
- Revenue per delivered order when both required fields exist.
- Pair count and correlation interpretation, without causal claims.
- Distribution and data-quality investigation suggestions.
- Categorical record composition, explicitly distinguished from revenue contribution.

Growth percentages are omitted for zero/negative bases. Missing months do not become a false month-over-month comparison. Shares are not calculated from averages, mixed negative/positive group values or an unseen population. Suggestions are investigation paths, not invented explanations of why the metric changed.

Each `BusinessInsight` exposes `id`, `kind`, `title`, `text`, `evidence` and `next_step`. The same snapshot drives these facts, the graph's report, chart recommendations and JSON exports. Existing AI reporting can prioritize known business evidence IDs as well as statistical IDs; unvalidated model prose remains excluded. Deterministic business interpretation remains available without an API call.

Real sample-database verification produced these observations: 2025-12 revenue was 15,306.96 versus 29,417.68 in the preceding returned month, a 48.0% decrease; Clothing contributed 150,071.83, approximately 22.0% of the returned category revenue total. The application cautions against assuming causality or full-population coverage.

## Verification

Baseline before edits: **93 passed in 12.53s**.

Final command:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

Actual final result: **114 passed in 114.03s; exit code 0**. All previous tests remain unchanged. Twenty-one added cases cover business calculations and their boundaries, all seven enhanced Plotly presentation modes, unified-page data exploration, SQL rejection and chart selection across chat reruns. Original Streamlit and compatibility-page tests also pass.

SHA-256 comparisons confirmed `.env`, the existing SQLite database and all nine prior test files are unchanged. Live Streamlit health at `http://127.0.0.1:8513/_stcore/health` returned **200**. UI verification used Streamlit AppTest and real Plotly construction/serialization; no new browser visual-verification claim is made. Live model-provider connectivity was not exercised; its configuration was preserved.

Backups: `.backups/unified_20261103_204850/`. The directory has no `.git`, so the original-file review used byte comparisons with these backups.

## Files

New:

- `app/analytics/business_insights.py`
- `app/ui/analysis_workspace.py`
- `tests/test_business_workspace.py`
- `docs/WORKSPACE_UPDATE.md`

Modified code:

- `app/analytics/advanced_result.py`
- `app/analytics/advanced_report.py`
- `app/analytics/advanced_visualization.py`
- `app/ui/streamlit_app.py`
- `app/ui/advanced_components.py`
- `app/ui/pages/2_Advanced_Analytics.py`

Updated documentation: README, architecture, technical guide, analytics guide, testing guide and the historical V3 verification record.

The existing SQL safety implementation, Agent graph, chart engine, original profile, database, `.env`, dependency files and previous tests were not modified in this update. Loaded-row scope limits, absence of query timeouts/authentication, and conservative date inference remain as documented in the V3 architecture.
