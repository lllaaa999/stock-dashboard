# -*- coding: utf-8 -*-
"""news_events.py — 当日消息面「采集 + 整理」（2026-09-30 新增，消息面→推演 第 ① ② 步）

① 采集：东财 7x24(column=350，翻页跨零点) + 东财快讯(fastNewsList，单次上限 200) + 新浪 7x24(翻页)
        标题归一化 + 字符 shingle Jaccard 去重，保留全部来源与链接
② 整理：每条消息 → 结构化事件（类型 / 极性 / 强度 0~10 / 作用板块 / 作用个股 / 时效分桶 / 命中词）

词表都是「可解释」的：类型与极性走关键词词典；作用个股对照 data/stock_names.json（只取 6 位 A 股，
2 字名需邻近市场语境词，降低"海南"这类地名误判）；板块词表来自当日涨停/跌停池 hybk + 板块资金名单
+ 题材小词表，无需手工维护。

输出（幂等，可重跑）：
  data/news/YYYY-MM-DD.jsonl         当日去重后的原始消息（与已有文件做并集，不会丢数据）
  data/news/events-YYYY-MM-DD.json   事件表 + 板块消息面榜（供推演/回测消费）

用法：
  python scripts/news_events.py                       # 今天（窗口=昨日18:00→现在）
  python scripts/news_events.py --date 2026-09-30 --top 20
  python scripts/news_events.py --no-fetch            # 不联网，只用已归档 jsonl 重新整理（改词典后重跑）
  python scripts/news_events.py --json                # 额外打印结构化 JSON（给上游程序消费）
"""
import argparse
import datetime as dt
import json
import pathlib
import re
import sys

_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import stock_dashboard as sd  # noqa: E402

ROOT = _HERE.parent
DATA_DIR = ROOT / 'data'
NEWS_DIR = DATA_DIR / 'news'
NAMES_PATH = DATA_DIR / 'stock_names.json'
SECTOR_FLOW_PATH = DATA_DIR / 'stock_data' / 'sector_flow.json'

w = sd.w

# ==================== 词典（可解释，改这里就能调口径） ====================
TYPE_RULES_NOTE = '类型判定含"全量对照表"语义, 实际调用见 detect_type()'

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


POS_WORDS = ['利好', '增长', '超预期', '上涨', '涨停', '突破', '中标', '获批', '落地', '提振', '回升', '扩产',
             '创新高', '放量', '大增', '上调', '增持', '回购', '支持', '刺激', '减税', '降准', '降息', '签约',
             '开工', '投产', '扭亏', '新高', '大涨', '飙升', '涨停潮', '抢筹', '加仓', '看好']
NEG_WORDS = ['利空', '下滑', '不及预期', '低于预期', '下跌', '跌停', '亏损', '预亏', '减持', '立案', '处罚',
             '违规', '退市', '风险警示', '暴跌', '下调', '爆雷', '停产', '终止', '解除', '调查', '打折',
             '抛售', '承压', '萎缩', '砸盘', '踩踏', '大面', '跌停潮', '特停', '核查']
EXPECT_WORDS = ['超预期', '不及预期', '低于预期', '首次', '落地', '传闻', '据悉', '或将', '有望', '拟', '计划', '预期']
STRONG_WORDS = ['重磅', '史诗', '万亿', '千亿', '全面', '超预期', '创纪录', '历史性', '首次', '突发', '紧急']
CONCEPT_WORDS = ['算力', '人工智能', 'AI', '机器人', '人形机器人', '固态电池', '半导体', '芯片', '军工', '低空经济',
                 '光模块', 'CPO', '液冷', '数据中心', '核电', '风电', '光伏', '储能', '创新药', '中药', '白酒',
                 '消费电子', '稀土', '有色', '黄金', '石油', '天然气', '煤炭', '券商', '保险', '银行', '房地产',
                 '汽车', '智能驾驶', '数据要素', '信创', '数字货币', '卫星', '商业航天', '量子', '生物医药',
                 '疫苗', '华为', '鸿蒙', '昇腾', '苹果', '英伟达', '特斯拉', '中字头', '央企改革', '并购重组',
                 '高股息']
_MKT_CTX = re.compile(r'(涨|跌|停|公告|公司|股|盘|板|净额|业绩|行业|板块|概念|龙头|中标|资金)')
_AMOUNT_RE = re.compile(r'(万亿|\d{3,}\.\d+亿|\d{3,}亿|\d+\.\d+万亿)')
_MARKET_RE = re.compile(r'(上证|沪深|创业板|科创|大盘|两市|A股|全球|全市场|指数)')


def _now_str():
    return dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# ==================== ① 采集 ====================
def fetch_em_724(win_start, max_pages=12):
    """东财 7x24 要闻流：page_index 翻页，跨零点后再翻 1 页就停"""
    out = []
    for pi in range(1, max_pages + 1):
        u = ('https://np-listapi.eastmoney.com/comm/web/getNewsByColumns?client=web&biz=web_724'
             '&column=350&order=1&needInteractData=0&page_index=%d&page_size=100'
             '&req_trace=%s' % (pi, dt.datetime.now().strftime('%Y%m%d%H%M%S%f')[:-3]))
        try:
            L = json.loads(sd.http(u, retries=2, timeout=10))['data']['list']
        except Exception as e:
            w(f'  [东财7x24] 第 {pi} 页失败: {type(e).__name__} {e}')
            break
        if not L:
            break
        for it in L:
            out.append({
                'time': (it.get('showTime') or '')[:19],
                'title': (it.get('title') or '').strip(),
                'summary': (it.get('summary') or '').strip(),
                'url': it.get('uniqueUrl') or it.get('url') or '',
                'source': '东财7x24',
            })
        if min(x['time'] for x in out) <= win_start:
            break
    return out


def fetch_em_fast():
    """东财 7x24 快讯流（单次上限实测 200 条，覆盖约 5 小时）"""
    u = ('https://np-listapi.eastmoney.com/comm/web/getFastNewsList?client=web&biz=web_724'
         '&fastColumn=102&sortEnd=&pageSize=200&req_trace=%s' % dt.datetime.now().strftime('%Y%m%d%H%M%S'))
    try:
        L = json.loads(sd.http(u, retries=2, timeout=10))['data']['fastNewsList']
    except Exception as e:
        w(f'  [东财快讯] 失败: {type(e).__name__} {e}')
        return []
    out = []
    for x in L:
        codes = []
        for s in (x.get('stockList') or []):
            if isinstance(s, dict) and s.get('code'):
                codes.append(str(s['code']))
        out.append({
            'time': (x.get('showTime') or '')[:19],
            'title': (x.get('title') or '').strip(),
            'summary': (x.get('summary') or '').strip(),
            'codes': ','.join(codes),
            'url': '',
            'source': '东财快讯',
        })
    return out


def fetch_sina(win_start, max_pages=40):
    """新浪财经 7x24（正文最全；页大小实测固定 100，约 35 分钟/页，翻页快：10 页约 4s）"""
    out = []
    hit_win = False
    for pg in range(1, max_pages + 1):
        u = f'https://zhibo.sina.com.cn/api/zhibo/feed?page={pg}&page_size=100&zhibo_id=152&tag_id=0'
        try:
            L = json.loads(sd.http(u, retries=2, timeout=10))['result']['data']['feed']['list']
        except Exception as e:
            w(f'  [新浪7x24] 第 {pg} 页失败: {type(e).__name__} {e}')
            break
        if not L:
            break
        for x in L:
            body = re.sub(r'<[^>]+>', '', x.get('rich_text') or '')
            body = re.sub(r'\s+', ' ', body).strip()
            m = re.match(r'^【(.+?)】\s*(.*)$', body)
            if m:
                title = m.group(1).strip()
            else:
                first = re.split(r'[。！？!?；;]', body)[0] or body
                title = first[:36]
            out.append({
                'time': (x.get('create_time') or '')[:19],
                'title': title,
                'summary': body,
                'url': x.get('docurl') or '',
                'source': '新浪7x24',
            })
        if min(y['time'] for y in out) <= win_start:
            break
    return out


def _norm_title(t):
    t = re.sub(r'^【|】$', '', (t or '').strip())
    return re.sub(r'[^\w\u4e00-\u9fa5]', '', t).lower()


def _shingles(s, k=2):
    return {s[i:i + k] for i in range(max(len(s) - k + 1, 1))}


def _jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


def _srcs_of(it):
    """兼容两种输入形态：采集态(有 source 字段) 与归档态(有 sources 列表)"""
    s = it.get('source')
    if s:
        return {s}
    v = it.get('sources')
    if isinstance(v, list):
        return set(v)
    if isinstance(v, str) and v:
        return set(x for x in v.split(',') if x)
    return {'归档'}


def _overlap_coef(a, b):
    """重叠系数 = 交集 / 较短集合 —— 处理'一条标题比另一条多几个修饰词'的情形"""
    if not a or not b:
        return 0.0
    return len(a & b) / float(min(len(a), len(b)))


def _containment(a, b):
    """一条归一化标题包含另一条(≥8 字) —— 快讯常换标题重发同一件事"""
    if len(a) < 8 or len(b) < 8:
        return False
    return a in b or b in a


def dedupe(items, thresh=0.72):
    """标题归一化 + shingle 倒排索引去重（跨源/跨轮次重复推送极多）

    候选用 shingle 倒排表找(而非前缀分桶 —— 前缀分桶会漏掉"央行宣布降准" vs "央行降准"这类),
    再加"短标题被长标题包含"的直接判重。
    """
    groups, idx_sh = [], {}
    for it in items:
        n = _norm_title(it.get('title'))
        if len(n) < 4:
            continue
        srcs = _srcs_of(it)
        sh = _shingles(n)
        cands = {}
        for sg in sh:
            for gi in idx_sh.get(sg, ()):
                cands[gi] = cands.get(gi, 0) + 1
        need = max(3, int(len(sh) * 0.4))
        hit = None
        for gi, ov in cands.items():
            if ov < need:
                continue
            g = groups[gi]
            if (_jaccard(sh, g['_sh']) >= thresh or _overlap_coef(sh, g['_sh']) >= 0.8
                    or _containment(n, g['_norm'])):
                hit = g
                break
        if hit is not None:
            hit['sources'] |= srcs
            if not hit.get('codes') and it.get('codes'):
                hit['codes'] = it['codes']
            if len(n) < len(hit['_norm']):
                hit['_norm'] = n            # 留更短更干净的标题做后续包含判断
            continue
        g = {'time': it['time'], 'title': it['title'], 'summary': it.get('summary', ''),
             'url': it.get('url', ''), 'codes': it.get('codes', ''), 'sources': set(srcs),
             '_sh': sh, '_norm': n}
        groups.append(g)
        for sg in sh:
            idx_sh.setdefault(sg, set()).add(len(groups) - 1)
    out = []
    for g in groups:
        d = {k: v for k, v in g.items() if not k.startswith('_')}
        d['sources'] = sorted(d.get('sources') or [])
        out.append(d)
    return out


# ==================== ② 整理 ====================
def load_sector_vocab(date_str=None):
    """板块/题材词表：板块资金名单 + 当日涨跌停池行业 + 题材小词表"""
    vocab = set(CONCEPT_WORDS)
    try:
        j = json.loads(SECTOR_FLOW_PATH.read_text(encoding='utf-8'))
        for k in ('inflow', 'outflow'):
            for it in (j.get(k) or []):
                if it.get('name'):
                    vocab.add(str(it['name']))
    except Exception as e:
        w(f'  [板块词表] 板块资金读取失败: {e}')
    ymd = (date_str or dt.date.today().strftime('%Y-%m-%d')).replace('-', '')
    pool_names = set()
    for kind in ('ZT', 'DT'):
        try:
            for x in (sd._pool(kind, ymd) or []):
                if x.get('hybk'):
                    pool_names.add(str(x['hybk']))
        except Exception as e:
            w(f'  [板块词表] {kind} 池行业读取失败: {e}')
    # 东财 hybk 会截断成 4 字(如 '房地产服'), 若已有更长名包含它就让位给长名, 避免榜上出现半截词
    vocab |= {n for n in pool_names
              if not any(o != n and len(o) > len(n) and o.startswith(n) for o in (vocab | pool_names))}
    return {v for v in vocab if v and len(v) >= 2}


def load_stock_index():
    """个股名 → 代码（只留 6 位 A 股，排除指数/ST 带星等易误判项）"""
    d = json.loads(NAMES_PATH.read_text(encoding='utf-8'))
    idx, code2name = {}, {}
    for code, name in d.items():
        code = str(code)
        name = (name or '').strip()
        if not re.fullmatch(r'(00|30|60|68|8[38]|43)\d{4}', code):
            continue
        if not name or name.startswith('*') or len(name) < 2:
            continue
        idx.setdefault(name, code)
        code2name.setdefault(code, name)
    return idx, code2name


def match_sectors(text, vocab):
    hits = []
    for v in vocab:
        if re.fullmatch(r'[A-Za-z]{2,4}', v):
            if re.search(r'(?<![A-Za-z])' + re.escape(v) + r'(?![A-Za-z])', text):
                hits.append(v)
        elif v in text:
            hits.append(v)
    return hits


def match_stocks(text, idx, code2name, max_hits=8):
    """滑窗匹配个股名（2/3/4 字），2 字名需邻近市场语境词；再兜底匹配 6 位代码"""
    hits, seen = [], set()
    L = len(text)
    for ln in (4, 3, 2):
        for i in range(max(L - ln + 1, 0)):
            cand = text[i:i + ln]
            code = idx.get(cand)
            if not code or cand in seen:
                continue
            if ln == 2 and not _MKT_CTX.search(text[max(0, i - 6): i + ln + 6]):
                continue
            seen.add(cand)
            hits.append({'code': code, 'name': cand})
            if len(hits) >= max_hits:
                return hits
    for m in re.finditer(r'(?<!\d)(\d{6})(?!\d)', text):
        c = m.group(1)
        if c in code2name and code2name[c] not in seen:
            seen.add(code2name[c])
            hits.append({'code': c, 'name': code2name[c]})
    return hits[:max_hits]


def time_bucket(tstr):
    """时效分桶：隔夜(前一日18:00~09:15) / 盘前(09:15~09:30) / 盘中(09:30~15:00) / 盘后(15:00~18:00) / 深夜"""
    try:
        hh, mm = int(tstr[11:13]), int(tstr[14:16])
    except Exception:
        return '未知'
    m = hh * 60 + mm
    if 9 * 60 + 15 <= m < 9 * 60 + 30:
        return '盘前'
    if 9 * 60 + 30 <= m < 15 * 60:
        return '盘中'
    if 15 * 60 <= m < 18 * 60:
        return '盘后'
    return '隔夜' if m >= 18 * 60 or m < 9 * 60 + 15 else '深夜'


def classify(text):
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
    if typ == '政策' and ('万亿' in text or any(k in text for k in ('降准', '降息', '印花税', '全面'))):
        strength += 1.0      # 全局性政策工具(降准/降息/万亿级)属市场级事件
    strength += min(len(pos) if polarity > 0 else len(neg), 4) * 0.4
    if '万亿' in text:
        strength += 2.5
    elif re.search(r'(千亿|\d{4,}亿)', text):
        strength += 2.0
    elif re.search(r'\d{3,}亿', text):
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


def build_events(raw_items, vocab, idx, code2name):
    events = []
    for it in raw_items:
        title = it.get('title') or ''
        summary = it.get('summary') or ''
        text = title + ' ' + summary
        # 打分以【标题】为准（摘要里常出现与事件无关的大数字, 会把强度抬到顶格）; 标题无信号才回退看摘要
        cl = classify(title)
        if cl['type'] == '其他' and cl['polarity'] == 0:
            alt = classify(text[:400])
            if alt['type'] != '其他' or alt['polarity'] != 0:
                cl = alt
        ev = {
            'time': it['time'], 'bucket': time_bucket(it['time']),
            'type': cl['type'], 'polarity': cl['polarity'], 'strength': cl['strength'],
            'sectors': match_sectors(text, vocab),
            'stocks': match_stocks(text, idx, code2name),
            'title': it['title'], 'summary': (it.get('summary') or '')[:200],
            'sources': it.get('sources'), 'url': it.get('url', ''),
            'hits': {'type': cl['type_hits'], 'pos': cl['pos_hits'], 'neg': cl['neg_hits']},
        }
        if it.get('codes'):
            ev['codes'] = it['codes']
        events.append(ev)
    events.sort(key=lambda e: (-e['strength'], e['time'][::-1]))  # 同分近端优先
    return events


def sector_board(events, limit=12):
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
                if s in (e.get('title') or ''):
                    a['samples'].append(e['title'][:48])
                else:
                    _i = (e.get('summary') or '').find(s)
                    if _i >= 0:
                        a['samples'].append('…' + e['summary'][max(0, _i - 8): _i + 30].strip() + '…')
                    else:
                        a['samples'].append(e['title'][:48])
    rows = list(agg.values())
    for r in rows:
        r['net'] = r['pos'] - r['neg']
    pos_rows = [r for r in rows if r['net'] > 0]
    neg_rows = [r for r in rows if r['net'] < 0]
    pos_rows.sort(key=lambda r: (-(r['net'] * 2 + r['strength'] / 20.0), -r['count']))
    neg_rows.sort(key=lambda r: (r['net'] * 2 - r['strength'] / 20.0, -r['count']))
    return {'positive': pos_rows[:limit], 'negative': neg_rows[:limit]}


# ==================== 归档 ====================
def _day_paths(date_str):
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    return NEWS_DIR / f'{date_str}.jsonl', NEWS_DIR / f'events-{date_str}.json'


def _union_prev(prev, new_items):
    """与已归档的当日消息做并集（按归一化标题精确去重），避免重跑丢数据"""
    out, seen = [], set()
    for it in list(prev) + list(new_items):
        n = _norm_title(it.get('title'))
        if not n or n in seen:
            continue
        seen.add(n)
        out.append(it)
    return out


def save_raw(date_str, items):
    """归档写的 = 模糊去重后的当日消息（保证 jsonl 行数 == 事件表条数）"""
    path, _ = _day_paths(date_str)
    rows = sorted(items, key=lambda x: x.get('time', ''))
    path.write_text('\n'.join(json.dumps(x, ensure_ascii=False) for x in rows) + '\n', encoding='utf-8')
    return len(rows)


def load_raw(date_str):
    path, _ = _day_paths(date_str)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


# ==================== 主流程 ====================
def run(date_str=None, top=15, no_fetch=False, win_start=None, quiet=False):
    date_str = date_str or dt.date.today().strftime('%Y-%m-%d')
    day = dt.date.fromisoformat(date_str)
    win_start = win_start or (day - dt.timedelta(days=1)).strftime('%Y-%m-%d') + ' 18:00:00'
    now_str = _now_str()

    src_counts, fetched = {}, []
    if no_fetch:
        fetched = load_raw(date_str)
        w('[采集] --no-fetch：直接用已归档消息重新整理')
    else:
        w(f'[采集] 窗口 {win_start} → {now_str}')
        parts = [('东财7x24', fetch_em_724(win_start)), ('东财快讯', fetch_em_fast()), ('新浪7x24', fetch_sina(win_start))]
        for name, rows in parts:
            rows = [r for r in rows if win_start <= r['time'] <= now_str and r.get('title')]
            src_counts[name] = len(rows)
            w(f'  {name}: {len(rows)} 条')
            fetched.extend(rows)
    raw_total = len(fetched)
    deduped = dedupe(fetched)
    if not no_fetch:
        prev = load_raw(date_str)
        if prev:
            deduped = _union_prev(prev, deduped)   # 与已归档消息并集（按归一化标题精确合并）
        deduped = dedupe(deduped)                  # 再模糊去重（跨源近似重复）
        save_raw(date_str, deduped)                # 归档 = 去重后的当日消息
    dup_rate = round((1 - len(deduped) / raw_total) * 100, 1) if raw_total else 0.0

    vocab = load_sector_vocab(date_str)
    idx, code2name = load_stock_index()
    events = build_events(deduped, vocab, idx, code2name)
    board = sector_board(events)

    buckets, types, polars = {}, {}, {'正': 0, '中': 0, '负': 0}
    for e in events:
        buckets[e['bucket']] = buckets.get(e['bucket'], 0) + 1
        types[e['type']] = types.get(e['type'], 0) + 1
        polars['正' if e['polarity'] > 0 else ('负' if e['polarity'] < 0 else '中')] += 1

    payload = {
        'date': date_str, 'window': [win_start, now_str], 'generated_at': now_str,
        'source_counts': src_counts, 'raw_total': raw_total, 'deduped_total': len(deduped),
        'dup_rate_pct': dup_rate, 'bucket_counts': buckets, 'type_counts': types, 'polarity_counts': polars,
        'sector_vocab_size': len(vocab), 'stock_index_size': len(idx),
        'events': events, 'sector_board': board,
    }
    _, ev_path = _day_paths(date_str)
    if not no_fetch:
        ev_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')

    if not quiet:
        print_report(payload, top, ev_path)
    return payload


def print_report(p, top, ev_path):
    w('')
    w('=' * 78)
    w(f"当日消息面整理 · {p['date']}  窗口 {p['window'][0]} → {p['window'][1]}")
    w('=' * 78)
    w('源分布: ' + ' | '.join(f'{k} {v} 条' for k, v in p['source_counts'].items()) if p['source_counts']
      else '（--no-fetch：使用归档数据）')
    w(f"原始 {p['raw_total']} 条 → 去重后 {p['deduped_total']} 条（重复率 {p['dup_rate_pct']}%）"
      f" | 板块词表 {p['sector_vocab_size']} 词 | 个股对照 {p['stock_index_size']} 只")
    w('时效: ' + ' '.join(f'{k} {v}' for k, v in sorted(p['bucket_counts'].items())))
    w('类型: ' + ' '.join(f'{k} {v}' for k, v in sorted(p['type_counts'].items(), key=lambda kv: -kv[1])))
    w('极性: ' + ' '.join(f'{k} {v}' for k, v in p['polarity_counts'].items()))
    w('')
    w(f'【强度 Top {top}】')
    w(' 强度 时效 类型   极性 作用板块            标题')
    for e in p['events'][:top]:
        pol = '+' if e['polarity'] > 0 else ('-' if e['polarity'] < 0 else '·')
        sec = ','.join(e['sectors'][:2])[:16] or '-'
        w(f" {e['strength']:>4} {e['bucket']} {e['type']:<4} {pol}  {sec:<18} {e['title'][:40]}")
    w('')
    w('【消息面板块榜 · 正面 Top】')
    w(' 板块                条数 正/负 强度   代表消息')
    for r in p['sector_board']['positive']:
        w(f" {r['name']:<18} {r['count']:>4} {r['pos']}/{r['neg']:<3} {r['strength']:>5} "
          f"{r['samples'][0] if r['samples'] else ''}")
    w('')
    w('【消息面板块榜 · 负面 Top】')
    for r in p['sector_board']['negative']:
        if r['neg'] <= 0:
            continue
        w(f" {r['name']:<18} {r['count']:>4} {r['pos']}/{r['neg']:<3} {r['strength']:>5} "
          f"{r['samples'][0] if r['samples'] else ''}")
    w('')
    w(f'事件表已写入: {ev_path}')


def main():
    ap = argparse.ArgumentParser(description='当日消息面采集 + 整理（结构化事件表）')
    ap.add_argument('--date', default=None, help='目标日期 YYYY-MM-DD（默认今天）')
    ap.add_argument('--top', type=int, default=15, help='打印强度 Top N（默认 15）')
    ap.add_argument('--no-fetch', action='store_true', help='不联网，只用已归档 jsonl 重新整理')
    ap.add_argument('--win-start', default=None, help='采集窗口起点 YYYY-MM-DD HH:MM:SS（默认昨日18:00）')
    ap.add_argument('--json', action='store_true', help='额外输出结构化 JSON')
    a = ap.parse_args()
    p = run(date_str=a.date, top=a.top, no_fetch=a.no_fetch, win_start=a.win_start)
    if a.json:
        print(json.dumps(p, ensure_ascii=False))


if __name__ == '__main__':
    main()