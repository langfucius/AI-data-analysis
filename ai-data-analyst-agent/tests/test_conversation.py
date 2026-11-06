from unittest.mock import patch
import pytest
from app.agent.graph import run_analysis
from app.agent.demo_mode import demo_sql
from app.agent.conversation import direct_answer


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr('app.agent.dialogue.get_openai_api_key',lambda:'')


@pytest.mark.parametrize('question',['同比与环比的区别','解释一下同比是什么意思','怎么导入 Excel','你好'])
def test_conversation_does_not_query(question):
    with patch('app.agent.graph.agent_graph') as workflow:
        result=run_analysis(question)
        workflow.invoke.assert_not_called()
    assert result['mode']=='conversation' and result['analysis']
    assert 'analysis_result' not in result


@pytest.mark.parametrize('question',['走势与高点','计算每月收入同比','查询销售额','count rows'])
def test_data_request_keeps_query_path(question):
    assert direct_answer(question) is None


def test_unknown_demo_has_no_silent_fallback():
    with pytest.raises(ValueError,match='Demo'):
        demo_sql('arbitrary unsupported request')
