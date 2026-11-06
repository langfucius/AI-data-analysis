from unittest.mock import patch
from app.agent.dialogue import compact_history
from app.agent.graph import run_analysis


def test_product_discussion_never_executes_query():
    with patch('app.agent.dialogue.plan_turn',return_value={'intent':'answer','answer':'有文件分析能力的大模型也能分析数据。'}), patch('app.agent.graph.agent_graph') as workflow:
        result=run_analysis('可是如果我把数据给大模型呢',[{'role':'user','content':'你和普通大模型有什么区别'}])
    workflow.invoke.assert_not_called()
    assert result['mode']=='conversation'


def test_followup_uses_resolved_question_and_history():
    history=[{'role':'user','content':'2025年收入多少'}]
    with patch('app.agent.dialogue.plan_turn',return_value={'intent':'query','question':'按地区统计2025年收入'}) as planner, patch('app.agent.graph.agent_graph') as workflow:
        workflow.invoke.return_value={'sql':'SELECT 1','analysis':'result'}
        result=run_analysis('按地区呢',history)
    assert planner.call_args.args[1]==history
    workflow.invoke.assert_called_once_with({'question':'按地区统计2025年收入','original_question':'按地区呢','conversation_context':compact_history(history)})
    assert result['question']=='按地区呢'
    assert result['resolved_question']=='按地区统计2025年收入'


def test_planner_failure_never_defaults_to_sales_query():
    with patch('app.agent.dialogue.plan_turn',side_effect=ValueError('bad JSON')), patch('app.agent.graph.agent_graph') as workflow:
        result=run_analysis('如果把数据交给模型呢')
    workflow.invoke.assert_not_called()
    assert result['error']


def test_history_is_bounded_and_excludes_unrelated_metadata():
    history=[{'role':'user','content':'x'*3000,'secret':'ignored'}]*20
    context=compact_history(history)
    assert len(context)==10 and len(context[0]['content'])==2500
    assert 'secret' not in context[0]
