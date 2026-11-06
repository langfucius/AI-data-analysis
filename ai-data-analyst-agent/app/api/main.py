"""FastAPI interface for the AI Data Analyst Agent."""
from __future__ import annotations

from typing import Any
from fastapi import FastAPI, HTTPException, Depends, Header
import os
import secrets
from pydantic import BaseModel, Field

from app.agent.graph import run_analysis
from app.core.config import is_llm_enabled
from app.database.db import ensure_database, get_schema


app = FastAPI(
    title="AI Data Analyst Agent API",
    description="Natural-language analytics over a read-only sample SQLite database.",
    version="1.0.0",
)


def authorize(authorization: str = Header(default="")):
    token = os.getenv("INSIGHTAI_API_TOKEN", "").strip()
    if token and not secrets.compare_digest(authorization, "Bearer " + token):
        raise HTTPException(status_code=401, detail="Invalid API token")


class AnalyzeRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class AnalyzeResponse(BaseModel):
    question: str
    sql: str | None = None
    analysis: str | None = None
    columns: list[str] = []
    rows: list[dict[str, Any]] = []
    mode: str | None = None
    error: str | None = None
    truncated: bool = False
    retry_count: int = 0
    analysis_result: dict[str, Any] | None = None
    chart_recommendations: list[dict[str, Any]] = []


@app.get("/health")
def health() -> dict[str, str]:
    ensure_database()
    return {"status": "ok", "llm_mode": "openai" if is_llm_enabled() else "demo"}


@app.get("/schema", dependencies=[Depends(authorize)])
def schema() -> dict[str, str]:
    return {"schema": get_schema(ensure_database())}


@app.post("/analyze", response_model=AnalyzeResponse, dependencies=[Depends(authorize)])
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    result = run_analysis(request.question)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return AnalyzeResponse(
        question=request.question,
        sql=result.get("sql"),
        analysis=result.get("analysis"),
        columns=result.get("columns", []),
        rows=result.get("rows", []),
        mode=result.get("mode"),
        error=result.get("error"),
        truncated=result.get("truncated", False),
        retry_count=result.get("retry_count", 0),
        analysis_result=result.get("analysis_result"),
        chart_recommendations=result.get("chart_recommendations", []),
    )

