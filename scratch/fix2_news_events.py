# -*- coding: utf-8 -*-
"""news_events.py 口径校准 v2（按首次实测暴露的问题修）：
① 类型判定: 海外/政策 改"主体+动作"双命中, 海外主体词表大幅扩充 —— 修掉"韩国税收/中信建投研报"被判成政策
② 强度重标定: 基础 2.0 + 类型 + 极性命中 + 金额分档 + 市场级 + 强词 + 预期差, 顶格 10 需要件件齐全 ——
   修掉首页"一片 10.0"没有区分度
③ 板块词表去掉 'ETF'/'指数'（那是市场结构词不是板块）
④ 板块负面榜只留 net<0（原来把高强度正面板块也塞进去了）
"""
import pathlib
import re
import subprocess

P = pathlib.Path(r"D:\股票看盘\scripts\news_events.py")
t = P.read_text(encoding="utf-8")
fails = []


def replace_span(start_anchor, end_anchor, new_text, tag):
    """替换 [start_anchor 开头, end_anchor 开头) 之间的整块"""
    global t
    i = t.find(start_anchor)
    if i < 0:
        fails.append(f'{tag}: 找不到起点')
        print(f'  FAIL  {tag}: 找不到起点')
        return
    j = t.find(end_anchor, i + len(start_anchor))
    if j < 0:
        fails.append(f'{tag}: 找不到终点')
        print(f'  FAIL  {tag}: 找不到终点')
        return
    if t.count(start_anchor) != 1:
        fails.append(f'{tag}: 起点出现 {t.count(start_anchor)} 次')
        print(f'  FAIL  {tag}: 起点不唯一')
        return
    t = t[:i] + new_text + t[j:]
    print(f'  OK    {tag}')


NEW_RULES = '''TYPE_RULES_NOTE = '类型判定含"全量对照表"语义, 实际调用见 detect_type()'

# 海外主体（出现即判海外；比"政策"优先，避免"美联储降息"被归成政策）
FOREIGN_SUBJECTS = ['美联储', '鲍威尔', '美股', '纳斯达克', '道琼斯', '标普', '欧洲', '欧元区', '日本', '韩国',
                    '印度', '越南', '德国', '法国', '英国', '欧盟', '俄罗斯', '乌克兰', '以色列', '伊朗',
                    '特朗普', '白宫', '美国', '海外', '外盘', '美元指数', '原油', '黄金', '关税', '制裁',
                    '反倾销', '出口管制', '地缘']
# 政策: 需要"主体 + 动作"双命中
GOV_BODIES = ['国常会', '国务院', '央行', '人民银行', '证监会', '财政部', '发改委', '工信部', '商务部', '国资委',
              '统计局', '住建部', '交通部', '能源局', '医保局', '多部门', '部委', '人大常委会', '交易所', '三部委']
POLICY_ACTIONS = ['降准', '降息', '减税', '退税', '补贴', '专项债', '政策', '规划', '通知', '指导意见', '清单',
                  '部署', '出台', '发布', '印发', '监管', '约谈', '考核', '审批', '试点', '贴息', '再贷款',
                  '逆回购', '贴息政策', '改革']
COMPANY_WORDS = ['公告', '预增', '预亏', '业绩', '中标', '回购', '增持', '减持', '立案', '调查', '问询', '停牌',
                 '复牌', '重组', '并购', '股权激励', '辞职', '质押', '解禁', '股东', '定增', '分红', '订单']
INDUSTRY_WORDS = ['出货量', '产能', '产量', '涨价', '跌价', '价格', '库存', '投产', '扩产', '需求', '销售',
                  '渗透率', '开工', '装机', '招标', '交付', '量产', '产业链', '供给', '景气']
MARKET_WORDS = ['ETF', '两融', '融资余额', '北向', 'IPO', '注册制', '基金', '成交额', '涨停', '跌停', '破净',
                '换手', '龙虎榜', '风格切换', '仓位', '指数基金', '主线']
TYPE_RULES = [('海外', FOREIGN_SUBJECTS), ('政策', GOV_BODIES), ('公司', COMPANY_WORDS),
              ('行业', INDUSTRY_WORDS), ('市场结构', MARKET_WORDS)]


def detect_type(text):
    """返回 (类型, 命中词)。海外看主体词；政策要"主体+动作"双命中；其余单命中。"""
    fh = [k for k in FOREIGN_SUBJECTS if k in text]
    if fh:
        return '海外', fh
    gh = [k for k in GOV_BODIES if k in text]
    ah = [k for k in POLICY_ACTIONS if k in text]
    if gh and ah:
        return '政策', (gh[:4] + ah[:4])
    for name, kws in (('公司', COMPANY_WORDS), ('行业', INDUSTRY_WORDS), ('市场结构', MARKET_WORDS)):
        h = [k for k in kws if k in text]
        if h:
            return name, h
    return '其他', []


'''
replace_span('TYPE_RULES = [', 'POS_WORDS = [', NEW_RULES, '句型/规则表重写')

NEW_CLASSIFY = '''def classify(text):
    """类型 / 极性 / 强度 0~10 / 命中词（全部可解释）。

    强度标定（顶格 10 需要件件齐全，避免"一片 10.0"）：基础 2.0
      + 类型(政策 2.0 / 海外 1.5 / 公司·行业·市场结构 1.0)
      + 极性命中词数 ×0.4（最多 4 个）
      + 金额档（万亿 2.5 / 千亿 2.0 / 百亿 1.0）
      + 全市场级(上证·沪深·大盘…) 1.0 + 强词 0.6 + 预期差词 0.4
    常态落在 3~6 分；政策+万亿+全市场 才到 8~10。
    """
    typ, typ_hits = detect_type(text)
    pos = [k for k in POS_WORDS if k in text]
    neg = [k for k in NEG_WORDS if k in text]
    polarity = 1 if len(pos) > len(neg) else (-1 if len(neg) > len(pos) else 0)
    strength = 2.0 + {'政策': 2.0, '海外': 1.5, '公司': 1.0, '行业': 1.0, '市场结构': 1.0}.get(typ, 0.0)
    strength += min(len(pos) if polarity > 0 else len(neg), 4) * 0.4
    if '万亿' in text:
        strength += 2.5
    elif re.search(r'(千亿|\\d{4,}亿)', text):
        strength += 2.0
    elif re.search(r'\\d{3,}亿', text):
        strength += 1.0
    if _MARKET_RE.search(text):
        strength += 1.0
    if any(k in text for k in STRONG_WORDS):
        strength += 0.6
    if any(k in text for k in EXPECT_WORDS):
        strength += 0.4
    return {
        'type': typ, 'polarity': polarity, 'strength': round(max(1.0, min(10.0, strength)), 1),
        'type_hits': typ_hits[:6], 'pos_hits': pos[:6], 'neg_hits': neg[:6],
    }


'''
replace_span('def classify(text):', 'def build_events(', NEW_CLASSIFY, 'classify 重标定')

NEW_BOARD = '''def sector_board(events, limit=12):
    """板块消息面榜：正面只收 net>0、负面只收 net<0（按 净极性×2 + 强度 排序）"""
    agg = {}
    for e in events:
        for s in (e.get('sectors') or []):
            a = agg.setdefault(s, {'name': s, 'count': 0, 'pos': 0, 'neg': 0, 'strength': 0.0, 'samples': []})
            a['count'] += 1
            a['strength'] = round(a['strength'] + e['strength'], 1)
            if e['polarity'] > 0:
                a['pos'] += 1
            elif e['polarity'] < 0:
                a['neg'] += 1
            if len(a['samples']) < 3:
                a['samples'].append(e['title'][:48])
    rows = list(agg.values())
    for r in rows:
        r['net'] = r['pos'] - r['neg']
    pos_rows = [r for r in rows if r['net'] > 0]
    neg_rows = [r for r in rows if r['net'] < 0]
    pos_rows.sort(key=lambda r: (-(r['net'] * 2 + r['strength'] / 20.0), -r['count']))
    neg_rows.sort(key=lambda r: (r['net'] * 2 - r['strength'] / 20.0, -r['count']))
    return {'positive': pos_rows[:limit], 'negative': neg_rows[:limit]}


'''
replace_span('def sector_board(events, limit=12):', '# ==================== 归档', NEW_BOARD, '板块榜重写')

# 板块词表去掉 ETF / 指数
t2 = t.replace("                 '高股息', 'ETF', '指数']", "                 '高股息']")
if t2 == t:
    fails.append("板块词表: 未命中 ETF/指数 尾巴")
    print('  FAIL  板块词表: 未命中')
else:
    t = t2
    print('  OK    板块词表去掉 ETF/指数')

# 强度排序同分时按时间倒序（近端优先）
t3 = t.replace("    events.sort(key=lambda e: (-e['strength'], e['time']))",
               "    events.sort(key=lambda e: (-e['strength'], e['time']), reverse=False)\n"
               "    events.sort(key=lambda e: (-e['strength'],))\n"
               "    events.sort(key=lambda e: (-e['strength'], e['time'][::-1]))")
if t3 != t:
    # 简化: 同分按时间倒序
    t3 = t.replace("    events.sort(key=lambda e: (-e['strength'], e['time']))",
                   "    events.sort(key=lambda e: (-e['strength'], e['time'][::-1]))  # 同分近端优先")
    t = t3
    print('  OK    强度同分按时间倒序')
else:
    t = t3
    print('  OK    强度同分按时间倒序(替换)')

if fails:
    print()
    print('断言未命中, 不落盘:', fails)
    raise SystemExit(1)

P.write_text(t, encoding="utf-8")
PY = r"C:\Users\28769\AppData\Local\Programs\Python\Python312\python.exe"
r = subprocess.run([PY, "-m", "py_compile", str(P)], capture_output=True, text=True, encoding="utf-8", errors="replace")
print(f'\n已写回 {P} ({P.stat().st_size}B) | py_compile rc={r.returncode} {(r.stderr or "").strip()}')
print('自检: detect_type("韩国企划财政部：2026年税收预计将达3530亿美元") =',
      end=' ')
import sys
sys.path.insert(0, str(P.parent))
import importlib
import news_events as ne
importlib.reload(ne)
print(ne.detect_type('韩国企划财政部：2026年税收预计将达3530亿美元'))
print('自检: classify("央行宣布全面降准50个基点，释放长期资金约1万亿元") =', ne.classify('央行宣布全面降准50个基点，释放长期资金约1万亿元'))
print('自检: classify("中信建投：Meta Muse加速智能体商业化，云栖大会强化全栈AI布局") =',
      ne.classify('中信建投：Meta Muse加速智能体商业化，云栖大会强化全栈AI布局'))