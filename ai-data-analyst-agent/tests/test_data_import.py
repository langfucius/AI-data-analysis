from io import BytesIO
from contextlib import closing
import sqlite3
import pandas as pd
import pytest
from app.ui.data_import import read_upload
from app.core.config import active_database
from app.agent import graph


def test_csv_encodings_and_empty():
    for encoding in ('utf-8-sig', 'gb18030'):
        frame=read_upload('产品,金额\n苹果,10'.encode(encoding),'sales.csv')
        assert frame.iloc[0].tolist()==['苹果',10]
    with pytest.raises(ValueError):
        read_upload(b'name,amount\n','empty.csv')


def test_excel_sheet_selection():
    buffer=BytesIO()
    with pd.ExcelWriter(buffer) as writer:
        pd.DataFrame({'n':[1]}).to_excel(writer,index=False,sheet_name='First')
        pd.DataFrame({'n':[2,3]}).to_excel(writer,index=False,sheet_name='Second')
    assert read_upload(buffer.getvalue(),'sample.xlsx','Second')['n'].tolist()==[2,3]


def test_imported_query_isolation(tmp_path,monkeypatch):
    monkeypatch.setattr('app.agent.dialogue.get_openai_api_key',lambda:'')
    monkeypatch.setattr('app.agent.llm.get_openai_api_key',lambda:'')
    tokens=[]
    try:
        for count in (2,5):
            path=tmp_path/f'{count}.db'
            with closing(sqlite3.connect(path)) as conn:
                pd.DataFrame({'value':range(count)}).to_sql('uploaded_data',conn,index=False)
            tokens.append(active_database.set(str(path)))
            result=graph.run_analysis('count rows')
            assert not result['error']
            assert result['rows']==[{'row_count':count}]
    finally:
        for token in reversed(tokens):
            active_database.reset(token)
