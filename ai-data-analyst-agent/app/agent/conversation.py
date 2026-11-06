"""Route explanations away from database execution."""
from app.core.config import get_openai_api_key, get_openai_model


def direct_answer(question):
    q=question.strip().lower()
    # A request to calculate actual metrics must retain the SQL evidence path.
    calculate=any(w in q for w in ('计算','统计','查询','calculate','compute','查询一下'))
    definition=any(w in q for w in ('区别','是什么','什么意思','如何理解','解释','difference','what is','explain'))
    if definition and not calculate and any(w in q for w in ('同比','环比','year-over-year','month-over-month')):
        return ('**同比**是与上一年同期比较，例如 2025 年 12 月与 2024 年 12 月比较。\n\n'
                '**环比**是与紧邻的上一期比较，例如 2025 年 12 月与 2025 年 11 月比较。\n\n'
                '增长率 =（本期值 − 对比期值）÷ 对比期值 × 100%。对比期为零时不能直接计算增长率；负基期需另行解释。\n\n'
                '同比适合观察相同季节下的年度变化，环比适合观察近期变化。任意两个时间点的首尾比较不一定是同比或环比。')
    if any(w in q for w in ('怎么上传','如何上传','怎么导入','如何导入','how to upload','how to import')):
        return '在左侧“导入数据”选择 CSV 或 .xlsx 文件，预览后点击“确认导入并使用”。Excel 可选择工作表。支持最大 20 MB、10 万行、200 列；自由提问分析需要配置模型 API。'
    if q.rstrip('！!。.？? ') in ('你好','您好','hello','hi','你能做什么','你是谁'):
        return '你好！我是 InsightAI，可以分析上传的数据、查询统计结果、展示图表，也可以解释数据分析概念。你可以上传 CSV / Excel，或直接提问。'
    data=any(w in q for w in ('销售','收入','订单','客户','产品','数据','走势','高点','趋势','统计','查询','预览','行数','多少行','revenue','sales','order','customer','product','trend','count','rows','data','region','quantity','amount'))
    if calculate or data:
        return None
    if not get_openai_api_key():
        return '当前为 Demo 模式，此问题没有匹配可用的数据查询模板。请说明要分析的指标，或配置模型 API 后继续提问。'
    from app.agent.llm import _get_client
    with _get_client() as client:
        response=client.chat.completions.create(
            model=get_openai_model(),
            messages=[{'role':'system','content':'你是 InsightAI。简洁回答用户的知识、概念或日常问题。你在此分支没有访问数据库，不得声称查询过数据或编造当前数据中的数字。如果用户需要具体数据分析，说明需要明确指标与范围。'},
                      {'role':'user','content':question}])
    return response.choices[0].message.content or '模型未返回文本，请重新提问。'
