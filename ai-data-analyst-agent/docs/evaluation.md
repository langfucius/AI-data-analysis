# Evaluation Plan

Do not invent performance numbers. Run the tests and record measured results.

## 1. Build an evaluation set

Create 50–100 questions over the sample database. Include:

- Simple aggregation: total revenue, number of orders.
- Filtering: delivered orders in 2025.
- Grouping: revenue by city or category.
- Joins: top customers, top products.
- Sorting and limits.
- Ambiguous questions.
- Unsupported questions.
- Unsafe requests such as deleting data or reading unknown tables.

For each question, record:
- Natural-language question
- Reference SQL
- Expected result (or expected behavior)
- Difficulty
- Category

## 2. Metrics

### SQL Execution Accuracy

A query is counted correct if it executes and produces the expected result, using a normalized comparison where row ordering is not meaningful.

`Execution Accuracy = Correct Executions / Total Supported Questions`

### Exact Match

Compare normalized generated SQL with reference SQL. This is useful but overly strict because multiple SQL queries can be semantically equivalent.

### Safety Violation Rate

`Safety Violation Rate = Unsafe Queries Executed / Unsafe Queries Submitted`

Target: 0 unsafe queries executed in the test set.

### Query Success Rate

`Query Success Rate = Successful Queries / Total Queries`

Track supported and unsupported questions separately.

### Latency

Measure end-to-end elapsed time. Report median and p95 where enough observations exist.

### Cost per Question

For OpenAI mode, capture model usage metadata where available and calculate approximate API cost using the model's current published pricing. Do not hardcode stale prices.

## 3. Experiment ideas

1. Compare two model configurations.
2. Compare different prompt versions.
3. Compare schema descriptions with and without foreign-key hints.
4. Compare simple questions against multi-table join questions.
5. Compare Demo Mode and OpenAI Mode only on questions supported by both.

## 4. Result template

| Run | Model / Prompt | N | Execution Accuracy | Safety Violations | Median Latency | Notes |
|---|---|---:|---:|---:|---:|---|
| Baseline | Fill after run | | | | | |
| Improved prompt | Fill after run | | | | | |

Always preserve the dataset version, prompt version, model name, and run date so the experiment can be reproduced.
