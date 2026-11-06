from contextlib import closing
"""Reproducible offline checks; --live explicitly enables paid model calls."""
import argparse
from contextlib import ExitStack
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from time import perf_counter
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from app.core.config import active_database, get_openai_api_key, get_openai_model
from app.agent import graph, llm
from app.ui.data_import import read_upload

CASES = [
    ('How many rows are there?', 'SELECT COUNT(*) FROM uploaded_data'),
    ('多少行？', 'SELECT COUNT(*) FROM uploaded_data'),
    ('What is the total revenue?', 'SELECT SUM(revenue) FROM uploaded_data'),
    ('销售额总和是多少？', 'SELECT SUM(revenue) FROM uploaded_data'),
    ('What is the average revenue?', 'SELECT AVG(revenue) FROM uploaded_data'),
    ('最大销售额是多少？', 'SELECT MAX(revenue) FROM uploaded_data'),
    ('最低销售额是多少？', 'SELECT MIN(revenue) FROM uploaded_data'),
    ('Show total revenue by region ordered by region', 'SELECT region,SUM(revenue) FROM uploaded_data GROUP BY region ORDER BY region'),
    ('按产品统计销售额，按产品排序', 'SELECT product,SUM(revenue) FROM uploaded_data GROUP BY product ORDER BY product'),
    ('Show monthly revenue sorted by month', "SELECT substr(date,1,7),SUM(revenue) FROM uploaded_data GROUP BY substr(date,1,7) ORDER BY 1"),
    ('How many records have missing revenue?', 'SELECT COUNT(*) FROM uploaded_data WHERE revenue IS NULL'),
    ('有多少个不同的产品？', 'SELECT COUNT(DISTINCT product) FROM uploaded_data'),
    ('Total revenue in East region?', "SELECT SUM(revenue) FROM uploaded_data WHERE region='East'"),
    ('Total revenue for product A?', "SELECT SUM(revenue) FROM uploaded_data WHERE product='A'"),
    ('How many records have revenue greater than 100?', 'SELECT COUNT(*) FROM uploaded_data WHERE revenue>100'),
    ('列出销售额大于100的产品和销售额，按销售额降序', 'SELECT product,revenue FROM uploaded_data WHERE revenue>100 ORDER BY revenue DESC'),
    ('How many records are in each region, sorted by region?', 'SELECT region,COUNT(*) FROM uploaded_data GROUP BY region ORDER BY region'),
    ('What is total quantity?', 'SELECT SUM(quantity) FROM uploaded_data'),
    ('按产品计算平均销售额，按产品排序', 'SELECT product,AVG(revenue) FROM uploaded_data GROUP BY product ORDER BY product'),
    ('Total revenue during January 2025?', "SELECT SUM(revenue) FROM uploaded_data WHERE date>='2025-01-01' AND date<'2025-02-01'"),
]
UNSAFE = ['DELETE FROM uploaded_data', 'DROP TABLE uploaded_data',
          'UPDATE uploaded_data SET revenue=0', 'INSERT INTO uploaded_data(revenue) VALUES(1)',
          'SELECT * FROM uploaded_data; DELETE FROM uploaded_data',
          'SELECT * FROM secret', "ATTACH DATABASE 'other.db' AS other", 'PRAGMA table_info(uploaded_data)']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    if args.live and not get_openai_api_key():
        parser.error('No API key configured. Live evaluation was not run.')
    results = []
    def record(name, category, action):
        start = perf_counter()
        try:
            action()
            results.append(dict(name=name, category=category, passed=True, seconds=round(perf_counter()-start,3)))
        except Exception as exc:
            results.append(dict(name=name, category=category, passed=False, detail=str(exc), seconds=round(perf_counter()-start,3)))
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)/'evaluation.db'
        raw = b'date,product,region,revenue,quantity\n2025-01-01,A,East,100,2\n2025-01-15,B,West,200,4\n2025-02-01,A,East,150,3\n2025-02-15,B,West,,1\n'
        frame = read_upload(raw, 'sales.csv')
        with closing(sqlite3.connect(path)) as conn:
            frame.to_sql('uploaded_data', conn, index=False)
        token = active_database.set(str(path))
        try:
            for question, sql in CASES:
                def check(question=question, sql=sql):
                    with ExitStack() as stack:
                        if not args.live:
                            stack.enter_context(patch('app.agent.dialogue.plan_turn',return_value={'intent':'query','question':question}))
                            stack.enter_context(patch.object(graph,'generate_sql',return_value=(sql,'fixture SQL','demo')))
                            stack.enter_context(patch.object(graph,'summarize_results',side_effect=lambda **kw: kw['snapshot'].summary()))
                        state = graph.run_analysis(question)
                    assert not state.get('error'), state.get('error')
                    actual = [tuple(row.values()) for row in state['rows']]
                    with closing(sqlite3.connect(path)) as conn:
                        expected = conn.execute(sql).fetchall()
                    assert actual == expected, f'Expected {expected}; got {actual}; SQL={state.get("sql")}'
                record(question, 'live_query' if args.live else 'fixture_workflow', check)
            for sql in UNSAFE:
                def check(sql=sql):
                    with patch('app.agent.dialogue.plan_turn',return_value={'intent':'query','question':'security test'}), patch.object(graph,'generate_sql',return_value=(sql,'security fixture','demo')):
                        state = graph.run_analysis('security test')
                    assert state.get('safety_violation') and state.get('error'), state
                record(sql,'security_fixture',check)
            def repair():
                with patch('app.agent.dialogue.plan_turn',return_value={'intent':'query','question':'count rows'}), patch.object(graph,'get_openai_api_key',return_value='fixture'), patch.object(graph,'generate_sql',return_value=('SELECT missing FROM uploaded_data','','openai')), patch.object(graph,'repair_sql',return_value=('SELECT COUNT(*) AS n FROM uploaded_data','')), patch.object(graph,'summarize_results',side_effect=lambda **kw: kw['snapshot'].summary()):
                    state=graph.run_analysis('count rows')
                assert not state['error'] and state['retry_count']==1 and state['rows']==[{'n':4}], state
            record('Repair nonexistent column and revalidate','repair_fixture',repair)
            def excel():
                buffer=BytesIO()
                frame.to_excel(buffer,index=False,sheet_name='Sales')
                actual=read_upload(buffer.getvalue(),'sales.xlsx','Sales')
                pd.testing.assert_frame_equal(frame,actual)
            record('Excel round trip','import',excel)
        finally:
            active_database.reset(token)
    report={'mode':'live' if args.live else 'offline', 'model':get_openai_model() if args.live else None,
            'method':'Offline query SQL is injected: this measures workflow correctness, NOT model accuracy. Security and repair use fixtures in both modes. Query comparisons use ordered result values on one small dataset; they do not prove general SQL equivalence.',
            'total':len(results),'passed':sum(r['passed'] for r in results),'cases':results}
    output=Path('reports')/('portfolio_live.json' if args.live else 'portfolio_offline.json')
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f"{report['mode']}: {report['passed']}/{report['total']} passed; {output}")
    raise SystemExit(0 if report['passed']==report['total'] else 1)


if __name__=='__main__':
    main()
