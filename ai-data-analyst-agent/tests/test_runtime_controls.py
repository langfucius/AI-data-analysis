import sqlite3
import pytest
from fastapi.testclient import TestClient
from app.database.db import execute_readonly_query
from app.api.main import app


def test_execution_budget(tmp_path):
    path = tmp_path / 'budget.db'
    sqlite3.connect(path).close()
    with pytest.raises(TimeoutError):
        execute_readonly_query('WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<100000000) SELECT sum(x) FROM n', path, timeout_seconds=0.001)


def test_api_token(monkeypatch):
    monkeypatch.setenv('INSIGHTAI_API_TOKEN', 'test-secret')
    client = TestClient(app)
    assert client.get('/schema').status_code == 401
    assert client.get('/schema', headers={'Authorization': 'Bearer test-secret'}).status_code == 200
    assert client.get('/health').status_code == 200
