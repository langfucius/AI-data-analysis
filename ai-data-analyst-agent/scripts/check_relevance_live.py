"""Live regression: unrelated aggregates must not be passed off as task completion."""
import sys
import json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.analytics.advanced_result import AnalysisResult
from app.agent.answer_templates import explain_result
from app.agent.llm import _get_client
from app.core.config import get_openai_model

result=AnalysisResult.from_query(['section','value'],[
    {'section':'C_order_funnel','value':2378.82},
    {'section':'B_data_quality','value':509}],question='各section的value比较',sql='SELECT section,value FROM report')
answer=explain_result(result,'quality',_get_client,get_openai_model(),original_question='给出数据检验和因果判断')
report={'original_question':'给出数据检验和因果判断','rewritten_question':result.question,
        'relevance':result.execution_metadata.get('answer_relevance'),'answer':answer}
Path('reports/relevance_live.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('relevance:',report['relevance'])
assert report['relevance'] == 'irrelevant', report
assert '最高' not in answer and '52.9%' not in answer, answer
print('PASS: unrelated aggregates rejected as complete answer')
