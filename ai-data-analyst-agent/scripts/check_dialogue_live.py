"""Four live intent checks; invokes the configured model API."""
import sys
import json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.agent.dialogue import plan_turn
from app.database.db import get_schema

cases=[
    ('可是如果是我把数据给大模型呢',[{'role':'user','content':'这个项目和普通大模型有什么区别？'},{'role':'assistant','content':'本项目支持连接数据库查询。'}],'answer'),
    ('同比与环比的区别',[],'answer'),
    ('走势与高点',[],'clarify'),
    ('那按产品类别拆分呢',[{'role':'user','content':'查询2025年收入总和'},{'role':'assistant','content':'已查询2025年收入','result':{'sql':"SELECT SUM(total_amount) FROM orders WHERE order_date >= '2025-01-01' AND order_date < '2026-01-01'",'columns':['revenue'],'rows':[{'revenue':100}]}}],'query')]
results=[]
for question,history,expected in cases:
    plan=plan_turn(question,history,get_schema())
    passed=plan['intent']==expected
    results.append({'question':question,'expected':expected,'plan':plan,'passed':passed})
    print(expected,plan['intent'],passed,flush=True)
path=Path('reports/dialogue_live.json')
path.parent.mkdir(exist_ok=True)
path.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
assert all(r['passed'] for r in results),results
