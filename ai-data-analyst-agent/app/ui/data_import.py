from contextlib import closing
"""Session-isolated CSV and Excel import."""
from io import BytesIO
import sqlite3
import uuid

import pandas as pd
import streamlit as st

from app.core.config import DATA_DIR, active_database


def read_upload(raw, filename, sheet=0):
    if len(raw) > 20 * 1024 * 1024:
        raise ValueError("文件不能超过 20 MB")
    if filename.lower().endswith('.csv'):
        for encoding in ('utf-8-sig', 'gb18030'):
            try:
                frame = pd.read_csv(BytesIO(raw), encoding=encoding, nrows=100001)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError("请使用 UTF-8 或 GB18030 编码的 CSV")
    else:
        frame = pd.read_excel(BytesIO(raw), sheet_name=sheet, nrows=100001)
    if frame.empty or len(frame) > 100000 or len(frame.columns) > 200:
        raise ValueError("请上传 1–100000 行、最多 200 列的非空数据")
    names = [str(c).strip() for c in frame.columns]
    if any(not n for n in names) or len({n.casefold() for n in names}) != len(names):
        raise ValueError("列名不能为空或重复")
    frame.columns = names
    return frame


def render_data_import():
    active_database.set(st.session_state.get('uploaded_database'))
    st.markdown('### 导入数据 / Import data')
    st.caption('支持 CSV、Excel（.xlsx），最大 20 MB、10 万行。每次导入替换当前会话的数据源。')
    upload = st.file_uploader('选择数据文件', type=['csv', 'xlsx'])
    if upload is not None:
        try:
            raw = upload.getvalue()
            sheet = 0
            if upload.name.lower().endswith('.xlsx'):
                if len(raw) > 20 * 1024 * 1024:
                    raise ValueError('文件不能超过 20 MB')
                with pd.ExcelFile(BytesIO(raw)) as book:
                    sheet = st.selectbox('选择工作表', book.sheet_names)
            frame = read_upload(raw, upload.name, sheet)
            st.caption(f'{len(frame):,} 行 · {len(frame.columns)} 列 · 表名 uploaded_data')
            st.dataframe(frame.head(20), use_container_width=True)
            with st.expander('字段类型与缺失值'):
                st.dataframe(pd.DataFrame({'类型': frame.dtypes.astype(str), '缺失值': frame.isna().sum()}))
            if st.button('确认导入并使用', type='primary'):
                directory = DATA_DIR / 'uploads'
                directory.mkdir(parents=True, exist_ok=True)
                path = directory / f'{uuid.uuid4().hex}.db'
                with closing(sqlite3.connect(path)) as connection:
                    frame.to_sql('uploaded_data', connection, index=False)
                st.session_state.uploaded_database = str(path)
                st.session_state.uploaded_filename = upload.name
                st.session_state.messages = []
                for key in ('workspace_snapshot', 'workspace_error', 'workspace_last_source', 'workspace_sql'):
                    st.session_state.pop(key, None)
                st.rerun()
        except Exception as exc:
            st.error(f'无法导入：{exc}')
    if st.session_state.get('uploaded_database'):
        st.success('当前数据源：' + st.session_state.uploaded_filename)
        st.caption('可提问“预览数据”或“多少行”。配置 API 后可自由提问。')
        if st.button('切回示例数据库'):
            st.session_state.pop('uploaded_database', None)
            st.session_state.messages = []
            for key in ('workspace_snapshot', 'workspace_error', 'workspace_last_source', 'workspace_sql'):
                st.session_state.pop(key, None)
            st.rerun()
