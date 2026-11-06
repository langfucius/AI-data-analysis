"""User-selected analysis and explanation structures."""
TEMPLATES = {
    'auto': ('自动分析', '先直接回答问题，再说明关键依据和结论限制。'),
    'quality': ('数据质量检验', '检查字段类型、缺失、重复、取值范围、时间覆盖及可验证的业务一致性。逐项说明已检查项目、发现、影响和建议。未执行的检查必须明确写未检查。'),
    'trend': ('趋势与对比', '说明变化、关键时间点、比较口径和差异；区分同比、环比和首尾比较。检查时间覆盖与指标可比性。'),
    'diagnosis': ('原因排查', '先明确现象，展示已查询的拆分证据，区分事实、可能解释、未验证假设。因果判断需要时间顺序、对照与混杂控制，不得把相关性当因果。'),
    'explain': ('概念与方法解释', '解释定义、区别、例子和适用场景；纯概念无需查库，涉及当前数据的数字必须查询验证。'),
}


def instructions(template):
    return TEMPLATES[template][1]


def explain_result(result, template, client_factory, model, original_question=None, conversation_context=None):
    import json
    import os
    from urllib.parse import urlsplit
    if not client_factory:
        return ('当前未配置模型，无法生成完整的模板解释。以下仅为已加载结果的本地统计，'
                '不代表已完成所有检验或原因验证。\n\n' + result.summary())
    payload={'original_question':original_question or result.question,'resolved_question':result.question,
             'recent_conversation':conversation_context or [],'template':instructions(template),'sql':result.sql,
             'columns':result.columns,'rows':result.rows[:100],
             'loaded_rows':result.loaded_row_count,'provided_rows':min(100,result.loaded_row_count),
             'truncated':result.truncated,'scope':result.scope_notice}
    prompt=('先核对SQL与结果是否回答 original_question，结合对话理解指代。原问题优先于改写和模板；模板不允许替换任务。'
            '返回JSON：{"relevance":"answered|partial|irrelevant","answer":"面向用户的文字回答","missing":"缺少的证据，没有则为空"}。'
            'answered表示结果足以回答，partial表示只能回答部分，irrelevant表示查错方向。'
            'partial必须确实完成原问题的一项子任务；只回答改写后的无关问题不算partial，必须判irrelevant。'
            '不要把偏题的改写内容说成用户原问题的一部分。不同section的value口径不明时禁止计算倍数、差额、排名和占比，即使同时附加免责声明也不允许。'
            'irrelevant时禁止解释无关表格、排名或图表；指出查询未回答什么问题、需要哪些证据。'
            'partial时先说明可回答和未完成部分，不能把检查计划说成已经执行，也不要再次询问是否愿意执行已授权任务。'
            '例如用户要数据检验和因果判断，section/value各模块的最大最小排名不是回答。'
            '根据工具返回的真实结果，用自然语言回答用户，遵循所选模板。必须有实质解释，不能只列标题或让图表代替回答。'
            '先给结论，再给依据、含义与限制。只引用已提供的数字；样本不代表全量，禁止声称执行了未展示的检查。'
            '不同单位或不同指标不能混合求和、排名、计算占比；section/metric/value 等长表须先辨别各行口径，不明则说明。'
            '不要照搬最高最低模板，不要每次机械附加IQR或泛泛建议。解释假设可以提出，但必须标明未验证，不能断言因果。'
            '本结果最多提供100行，超出部分不能假装看过。用用户语言回答。')
    with client_factory() as client:
        response=client.chat.completions.create(model=model,response_format={'type':'json_object'},messages=[{'role':'system','content':prompt},
            {'role':'user','content':json.dumps(payload,ensure_ascii=False,default=str)}],
            **({'extra_body':{'thinking':{'type':'disabled'}}} if urlsplit(os.getenv('OPENAI_BASE_URL','')).hostname=='api.deepseek.com' else {}))
    response_data=json.loads(response.choices[0].message.content or '{}')
    relevance=response_data.get('relevance')
    if relevance not in ('answered','partial','irrelevant'):
        raise ValueError('回答相关性检查未返回有效状态')
    answer=response_data.get('answer')
    if not answer or not answer.strip():
        raise ValueError('模型未返回解释文本')
    result.execution_metadata['answer_relevance']=relevance
    missing=response_data.get('missing','')
    if relevance != 'answered' and missing:
        answer += '\n\n尚缺证据：' + str(missing)
    return answer
