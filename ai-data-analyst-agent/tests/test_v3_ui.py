"""Run real Streamlit scripts with its headless application test runner."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

from app.agent import llm


ROOT = Path(__file__).resolve().parents[1]


def test_original_ui_starts_and_demo_renders_once(monkeypatch):
    monkeypatch.setattr(llm, "get_openai_api_key", lambda: "")
    app = AppTest.from_file(str(ROOT / "app/ui/streamlit_app.py"), default_timeout=45).run()
    assert not app.exception
    app.session_state.pending_question = "Show monthly revenue trends."
    app.run()
    assert not app.exception
    assert len(app.get("plotly_chart")) == 1
    assert app.session_state.messages[-1]["result"]["mode"] == "demo"
    # History should show the same single chart on a later rerun.
    app.run()
    assert not app.exception and len(app.get("plotly_chart")) == 1


def test_advanced_page_starts_query_safety_and_agent(monkeypatch):
    monkeypatch.setattr(llm, "get_openai_api_key", lambda: "")
    page = ROOT / "app/ui/pages/2_Advanced_Analytics.py"
    assert page.exists()
    app = AppTest.from_file(str(page), default_timeout=45).run()
    assert not app.exception
    assert app.session_state.advanced_snapshot.loaded_row_count > 0
    original = app.session_state.advanced_snapshot.snapshot_id
    app.text_area[0].set_value("DELETE FROM orders")
    app.button[0].click().run()
    assert not app.exception and len(app.error) == 1
    assert app.session_state.advanced_snapshot.snapshot_id == original
    app.button[1].click().run()
    assert not app.exception
    assert app.session_state.advanced_agent_result["mode"] == "demo"
    assert app.session_state.advanced_agent_result["analysis_result"]["loaded_row_count"] > 0
