# AI Engineer Interview Questions for This Project

Use these questions to check whether you understand the project rather than merely knowing its libraries.

1. **Walk me through the architecture.**
   - Explain the UI/API, LangGraph nodes, SQL safety layer, database, and result analysis.

2. **Why did you use LangGraph?**
   - The workflow has explicit state, sequential steps, conditional routing, and error handling.

3. **What is Text-to-SQL?**
   - Translating natural-language questions into executable SQL, grounded in a database schema.

4. **Why provide the database schema to the LLM?**
   - It constrains table and column selection and helps the model understand relationships.

5. **Why not execute generated SQL directly?**
   - LLM output is untrusted. Parse, validate, restrict tables, use read-only credentials, and cap results.

6. **What is the difference between SQL parsing and SQL execution?**
   - Parsing checks syntax/structure; execution runs the query against a database.

7. **What is a table allow-list?**
   - A set of approved tables that generated queries are permitted to reference.

8. **Why use a read-only SQLite connection?**
   - It prevents data modification even if an earlier validation layer has a bug.

9. **What is an SQL authorizer?**
   - A SQLite callback that approves or denies database actions during statement preparation/execution.

10. **What is the difference between Exact Match and Execution Accuracy?**
    - Exact Match compares SQL text; Execution Accuracy compares query outcomes.

11. **How would you improve complex join generation?**
    - Add foreign-key relationship metadata, examples, schema retrieval, query planning, and execution-based repair with strict limits.

12. **How would you handle an invalid SQL query?**
    - Return a structured error; optionally allow a bounded repair attempt, then revalidate before execution.

13. **How would you reduce token usage?**
    - Retrieve only relevant schema, summarize metadata, cache schema, limit result rows, and avoid sending unnecessary records.

14. **How would you support PostgreSQL?**
    - Introduce a database adapter, dialect-aware parsing, connection pooling, least-privilege credentials, and dialect-specific tests.

15. **What are the limitations of the current version?**
    - Demo templates are limited; follow-up context is not persisted; sample data is synthetic; production auth, tenancy, audit, and stronger isolation are not included.
