# Testing InsightAI V3

The unified-workspace update adds `tests/test_business_workspace.py`. It checks hand-calculated endpoint/adjacent-month changes, missing-month boundaries, nonpositive bases, correct share denominators, rates using means, derived order value, correlation caveats, categorical counts, all seven presentation modes, main-page data exploration, SQL rejection and chart selection surviving reruns. All previously existing tests remain unchanged; hashes were compared with the pre-edit backup.

The original-page and compatibility-page UI tests still execute their real Streamlit scripts. The primary UI is now the main entry's **Business analysis / Explore data** switch, with narrative first and one selected chart per answer.

Always use the project environment:

```powershell
.\.venv\Scripts\python.exe -m pytest --collect-only -vv
.\.venv\Scripts\python.exe -m pytest -v
```

The initial V3 baseline was 28 passing original tests. No original tests were rewritten. New coverage is additive:

- `tests/test_advanced_analytics.py`: hand-calculated statistics, missing values, duplicates, IQR, date inference, correlation/ties/constants, seven real Plotly traces, aggregations, null/non-finite values, invalid configurations, recommendation determinism, snapshot copies, strict JSON, actual SQL and safety boundaries.
- `tests/test_v3_agent.py`: successful and empty snapshots, truncation, generation/report failures, retry limit, repaired-query revalidation, execution repair classification, evidence-only model reporting, Demo Mode and FastAPI integration.
- `tests/test_v3_ui.py`: runs both actual Streamlit scripts through AppTest; checks original Demo charts are not duplicated across reruns; verifies new page, failed SQL retaining the old snapshot and Demo AI analysis.

No tests make external model calls. Model configuration is preserved; monkeypatches apply only inside tests. Passing mocked model tests proves local contracts, not availability of a remote provider or its quota.

## Manual exploration

Start the original entry point and use its generated multipage navigation to open Advanced Analytics. Query a source table, select a recommended chart, try custom aggregation, inspect all three correlation methods, export CSV/JSON, then ask a Demo question. Attempt `DELETE FROM orders` and verify immediate rejection.

For startup checking, run Streamlit headless on an unused port and request `/_stcore/health`. Health only proves the web server started; AppTest additionally executes the page scripts and interactions. Browser inspection checks navigation and actual rendered charts when available.

## Preservation

Original files were backed up under `.backups/v3_20261103_142204/` before edits. The backup includes SHA-256 hashes of `.env` and the existing database; compare hashes after validation without printing configuration contents. This workspace has no `.git` metadata, so a Git diff is unavailable; file comparisons against the backup serve as the change review.

See the final verification report in `docs/V3_VERIFICATION.md` for the executed results and limitations.
