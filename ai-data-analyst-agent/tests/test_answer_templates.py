from types import SimpleNamespace
from unittest.mock import patch
from app.agent.answer_templates import TEMPLATES, explain_result
from app.analytics.advanced_result import AnalysisResult
from app.agent.graph import run_analysis


def test_template_explanation_gets_raw_evidence_not_mixed_ranking():
    calls=[]
    class Client:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        @property
        def chat(self): return self
        @property
        def completions(self): return self
        def create(self,**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"relevance":"irrelevant","answer":"两项口径不同，不能据此排名或推断因果。","missing":"逐项数据检验结果"}'))])
    result=AnalysisResult.from_query(['section','value'],[{'section':'quality','value':509},{'section':'funnel','value':2378.82}],question='检验和因果判断')
    answer=explain_result(result,'diagnosis',Client,'test',original_question='请检验数据并判断因果')
    assert result.execution_metadata['answer_relevance']=='irrelevant'
    assert '请检验数据并判断因果' in calls[0]['messages'][1]['content']
    assert '尚缺证据' in answer
    assert '不能' in answer
    assert '509' in calls[0]['messages'][1]['content']
    assert '不同单位' in calls[0]['messages'][0]['content']
    assert '最高' not in calls[0]['messages'][1]['content']


def test_template_reaches_planning_and_execution():
    with patch('app.agent.dialogue.plan_turn',return_value={'intent':'query','question':'检查缺失'}) as planner, patch('app.agent.graph.agent_graph') as workflow:
        workflow.invoke.return_value={'analysis':'检查结果'}
        run_analysis('检查数据',answer_template='quality')
    assert '检查字段类型' in planner.call_args.args[0]
    assert workflow.invoke.call_args.args[0]['answer_template']=='quality'


def test_all_templates_and_invalid_selection():
    assert len(TEMPLATES)==5
    assert run_analysis('hello',answer_template='invalid')['error']
