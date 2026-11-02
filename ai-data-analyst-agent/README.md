# AI Data Analyst Agent

一个面向 AI Engineer / AI Agent Engineer 求职 Portfolio 的端到端项目。

用户通过自然语言提问，Agent 读取数据库 Schema、生成 SQL、验证查询安全性、执行只读查询，并总结结果、展示表格和图表。

## Features

- Natural Language to SQL (OpenAI mode)
- Deterministic Demo Mode (无需 API Key)
- LangGraph workflow orchestration
- SQL parsing and table allow-list validation
- Read-only SQLite execution and row limits
- Pandas / Plotly result visualization
- Streamlit chat interface
- FastAPI endpoints
- Pytest unit and integration tests
- Synthetic retail sales database

## Architecture

```text
User
 |
 v
Streamlit UI / FastAPI
 |
 v
LangGraph Workflow
 |-- Inspect database schema
 |-- Generate SQL (OpenAI or Demo templates)
 |-- Validate SQL (SQLGlot + table allow-list)
 |-- Execute read-only query (SQLite authorizer)
 |-- Analyze result (LLM or local summary)
 |
 v
SQLite sample database
```

## 1. Requirements

- Windows 11
- Python 3.10 or newer (Python 3.11 recommended)
- VS Code
- Internet connection for installing packages
- Optional: OpenAI API key for open-ended natural-language SQL generation

## 2. Setup on Windows 11 (PowerShell)

Open the project folder in VS Code, then open **Terminal → New Terminal**.

```powershell
# Create virtual environment
py -m venv .venv

# Activate it
.\.venv\Scripts\Activate.ps1

# If PowerShell blocks activation, run this for the current terminal only:
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1

# Upgrade pip and install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

# Create the local environment file
Copy-Item .env.example .env

# Create / refresh the sample database
python scripts/init_db.py
```

If `py` is not recognized, try `python -m venv .venv`.

## 3. Run the Streamlit app

```powershell
python -m streamlit run app/ui/streamlit_app.py
```

Streamlit will print a local URL, usually `http://localhost:8501`.

## 4. Demo Mode vs OpenAI Mode

### Demo Mode

No API key is required. The app uses deterministic SQL templates for example intents such as:

- What is the total revenue?
- Show the top 5 best-selling products.
- Show monthly revenue trends.
- Compare sales by category.
- Who are the top customers?
- What is the order status distribution?

Demo Mode is intentionally limited; it is a predictable local learning path, not a general-purpose language model.

### OpenAI Mode

1. Open `.env`.
2. Add your API key:

```env
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4o-mini
```

3. Stop and restart Streamlit.

Never commit `.env` or expose your API key in screenshots, GitHub, or frontend code.

## 5. Run the FastAPI backend

In a second terminal (with the virtual environment activated):

```powershell
python -m uvicorn app.api.main:app --reload
```

Useful endpoints:

- `GET http://127.0.0.1:8000/health`
- `GET http://127.0.0.1:8000/schema`
- `POST http://127.0.0.1:8000/analyze`

Example request body:

```json
{
  "question": "Show the top 5 best-selling products."
}
```

Interactive API docs: `http://127.0.0.1:8000/docs`.

## 6. Run tests

```powershell
python -m pytest
```

The tests cover SQL safety, database creation, read-only query execution, and Demo Mode SQL templates.

## 7. Suggested questions

| Question | Expected analysis |
|---|---|
| What is the total revenue? | Delivered-order revenue |
| Show the top 5 best-selling products. | Products ranked by revenue |
| Show monthly revenue trends. | Monthly delivered revenue |
| Compare sales by category. | Revenue by product category |
| Who are the top customers? | Customers ranked by spending |
| What is the order status distribution? | Count by order status |

## 8. Project structure

```text
ai-data-analyst-agent/
├── app/
│   ├── agent/          # LangGraph, LLM, SQL safety, Demo Mode
│   ├── api/            # FastAPI
│   ├── core/           # Configuration
│   ├── database/       # SQLite helpers and synthetic data
│   └── ui/             # Streamlit app
├── data/               # Sample database
├── docs/               # Architecture, learning guide, evaluation
├── scripts/            # Database initialization
├── tests/              # Automated tests
├── .env.example
├── requirements.txt
└── README.md
```

## 9. Important design and safety notes

- Generated SQL is parsed before execution.
- Only a single SELECT / UNION query is accepted.
- Referenced tables must be in the database allow-list.
- Queries run through a read-only SQLite connection.
- A SQLite authorizer blocks write operations and selected dangerous functions.
- Results are capped by `MAX_ROWS`.
- Demo data is synthetic and contains no real customer information.

This is a learning Portfolio project, not a production security boundary. Before connecting a real database, use a dedicated read-only database account, restrict accessible schemas and columns, add authentication, rate limits, audit logs, and stronger isolation.

## 10. Suggested next improvements

- Add PostgreSQL support.
- Add query result caching.
- Add conversation-level follow-up context.
- Add schema relationship retrieval.
- Add a benchmark dataset with 50–100 natural-language questions.
- Compare SQL generation across models.
- Add Docker Compose and CI with GitHub Actions.

## Resume positioning

**AI Data Analyst Agent | Python, LangGraph, OpenAI API, FastAPI, SQLite, Pandas, Plotly**

- Developed an AI-powered data analyst agent that translates natural-language questions into SQL queries using a LangGraph-orchestrated workflow.
- Implemented SQL parsing, table allow-list validation, read-only execution, and result visualization to improve query safety and usability.
- Built automated tests for SQL safety and query execution, and evaluated the system across a curated set of analytics questions.

Only add measured performance numbers after running a reproducible evaluation.
