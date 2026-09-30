# -*- coding: utf-8 -*-
"""sim_llm.py — LLM 消息面推演（2026-09-30 新增 · 消息面→推演 第 ③ 步）

参考 MiroFish 的流水线（种子 → 人格 → 多轮 → 报告），但**不搬它的社交平台仿真**——
A 股次日走势吃的是资金属性与封板博弈，不是"谁发帖谁点赞"。映射：
  · 种子 = 交付① 的当日事件表（data/news/events-YYYY-MM-DD.json）+ 市场微结构事实
  · 人格 = 项目已有九方势力（名称/权重与 stock_dashboard._AGENT_W 完全一致）
  · 多轮 = LLM 逐轮给"势力修正 + 谁在接谁的货 + 次日合力定性"；**数值聚合仍走规则引擎**（LLM 不碰算术）
  · 报告 = 结构化 JSON：冲击矩阵 / 板块优先级 / 风险点 / 三档情景 / 叙事 / 置信度

设计原则：LLM 只输出"判断"，可回溯、可对账（seed 哈希 + 原始输出一起存档），
失败/无密钥一律回落到规则引擎，绝不把页面搞挂。

配置（密钥只放本地，别进聊天、别进 git）：
  1) 环境变量 STOCK_LLM_BASE_URL / STOCK_LLM_API_KEY / STOCK_LLM_MODEL
  2) config/llm.local.json（推荐，模板见 config/llm.local.json.example）
  3) 可选 opt-in：{"fallback_hermes": true} 复用 Hermes .env 里的 DashScope 通道（qwen-plus）

用法：
  python scripts/sim_llm.py                      # 今天 / 3 轮 / Top20 事件
  python scripts/sim_llm.py --dry-run            # 不调 API，用内置样例响应验证链路
  python scripts/sim_llm.py --rounds 1 --top-events 12
  python scripts/sim_llm.py --date 2026-09-30 --json
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import stock_dashboard as sd  # noqa: E402

ROOT = _HERE.parent
DATA_DIR = ROOT / 'data'
NEWS_DIR = DATA_DIR / 'news'
LLM_DIR = DATA_DIR / 'llm'
CFG_PATH = ROOT / 'config' / 'llm.local.json'
CFG_EXAMPLE = ROOT / 'config' / 'llm.local.json.example'

w = sd.w

# 九方势力人格（与 stock_dashboard._AGENT_W 同名同权重；描述是 A 股口径的行为规则）
FORCES = [
    ('国家队', 1.2, '逆周期托底资金：冰点/系统性风险时扫宽基 ETF 护盘，亢奋时降温，基本不做日内博弈'),
    ('机构', 0.9, '配置与基本面盘：重政策与流动性信号，加仓看两融与增量资金，利好后常逢高派发'),
    ('游资', 1.0, '题材情绪打板：追高度与承接，炸板率上升即撤，偏好龙头首板与连板梯队'),
    ('团伙(控盘)', 0.6, '控盘庄股逻辑：做高度与梯队，最怕监管特停/立案核查'),
    ('散户', 0.7, '情绪驱动跟风：追涨杀跌、高位接盘，恐惧与贪婪双向放大'),
    ('北向', 0.8, '外资配置与风险偏好代理：看 A50/汇率/全球风险偏好，政策确定性提高才持续流入'),
    ('量化', 0.7, 'DMA/中性策略：动量与流动性收割，炸板率高时最先撤流动性'),
    ('产业资本', 0.5, '大宗交易/回购/增减持：关注折溢价与产业景气，不追短期情绪'),
    ('大散户', 0.9, '放大版散户且更极端：杠杆盘，亢奋重仓、冰点割肉、退潮死扛'),
]
FORCE_WEIGHT = {n: wt for n, wt, _d in FORCES}
FORCE_DESC = {n: d for n, _wt, d in FORCES}

SYSTEM_PROMPT = (
    '你是 A 股短线博弈推演引擎，服务对象是专业短线交易者。'
    '你只能基于用户给出的事件表与市场事实做判断，**严禁虚构消息**。'
    '只输出 JSON，不要任何解释性前后缀。'
)


# ==================== 配置 ====================
def load_llm_config(quiet=False):
    """配置发现顺序：环境变量 > config/llm.local.json >（可选）Hermes .env 的 DashScope 通道。
    返回 cfg（不含明文打印；只报告来源与是否有密钥）。"""
    cfg, src = {}, 'none'
    if CFG_PATH.exists():
        try:
            cfg = json.loads(CFG_PATH.read_text(encoding='utf-8')) or {}
            src = 'config/llm.local.json'
        except Exception as e:
            w(f'[LLM配置] config/llm.local.json 解析失败: {e}')
    for key, env in (('base_url', 'STOCK_LLM_BASE_URL'), ('api_key', 'STOCK_LLM_API_KEY'),
                     ('model', 'STOCK_LLM_MODEL')):
        v = os.environ.get(env)
        if v:
            cfg[key] = v
            src = 'env'
    if not cfg.get('api_key') and cfg.get('fallback_hermes'):
        p = pathlib.Path(os.environ.get('LOCALAPPDATA', '')) / 'hermes' / '.env'
        kv = {}
        try:
            for line in p.read_text(encoding='utf-8', errors='replace').splitlines():
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, _, v = line.partition('=')
                    kv[k.strip()] = v.strip()
        except Exception:
            kv = {}
        if kv.get('HERMES_CUSTOM_QW_API_KEY'):
            cfg['base_url'] = cfg.get('base_url') or kv.get('DASHSCOPE_BASE_URL') or \
                'https://dashscope.aliyuncs.com/compatible-mode/v1'
            cfg['api_key'] = kv['HERMES_CUSTOM_QW_API_KEY']
            cfg['model'] = cfg.get('model') or 'qwen-plus'
            src = 'hermes .env (DashScope)'
    cfg.setdefault('base_url', 'https://api.deepseek.com/v1')
    cfg.setdefault('model', 'deepseek-chat')
    cfg.setdefault('timeout', 150)
    cfg.setdefault('max_tokens', 2600)
    cfg.setdefault('temperature', 0.3)
    cfg.setdefault('rounds', 3)
    cfg.setdefault('top_events', 20)
    cfg['source'] = src
    cfg['has_key'] = bool(cfg.get('api_key'))
    if not quiet:
        w(f"[LLM配置] 来源={src} | base_url={cfg['base_url']} | model={cfg['model']} | "
          f"密钥={'已就位' if cfg['has_key'] else '缺失'}")
    return cfg


# ==================== 种子 ====================
def build_seed(date_str=None, top_events=20):
    """把交付①的事件表 + 市场微结构压成一段紧凑提示（≈2k 字符）"""
    date_str = date_str or dt.date.today().strftime('%Y-%m-%d')
    ev_path = NEWS_DIR / f'events-{date_str}.json'
    if not ev_path.exists():
        return None, f'缺少当日事件表 {ev_path}，请先运行: python scripts/news_events.py --date {date_str}'
    p = json.loads(ev_path.read_text(encoding='utf-8'))
    lines = []
    for i, e in enumerate(p.get('events', [])[:top_events], 1):
        pol = '+' if e['polarity'] > 0 else ('-' if e['polarity'] < 0 else '·')
        sec = '/'.join(e.get('sectors', [])[:3]) or '-'
        stk = ' '.join(x.get('name', '') for x in (e.get('stocks') or [])[:3])
        lines.append(f"{i}. [{e['strength']}|{e['type']}|{pol}|{e['bucket']}] {e['title'][:64]}"
                     f"（板块:{sec}{'｜个股:' + stk if stk else ''}）")
    board = p.get('sector_board') or {}
    pos = '，'.join(f"{r['name']}({r['count']}条 正{r['pos']}/负{r['neg']})" for r in (board.get('positive') or [])[:8])
    neg = '，'.join(f"{r['name']}({r['count']}条 正{r['pos']}/负{r['neg']})" for r in (board.get('negative') or [])[:8])
    facts = {}
    try:
        fp = pathlib.Path(sd.DATA_DIR) / 'sentiment_history.jsonl'
        if fp.exists():
            recs = [json.loads(l) for l in fp.read_text(encoding='utf-8').splitlines() if l.strip()]
            if recs:
                la = recs[-1]
                facts = {k: la.get(k) for k in ('date', 'score', 'score_v1', 'algo', 'zt', 'zb', 'dt',
                                                'max_lb', 'diverge', 'effect') if k in la}
    except Exception as e:
        w(f'[种子] 情绪存档读取失败: {e}')
    text = '\n'.join([
        f"【日期】{date_str}（推演目标：次一交易日）",
        f"【市场微结构】{json.dumps(facts, ensure_ascii=False)}" if facts else '【市场微结构】缺失',
        f"【当日事件表 Top{len(lines)}（按冲击强度，含类型/极性/时效）】",
        '\n'.join(lines) if lines else '(无事件)',
        f"【消息面板块榜·正面】{pos or '-'}",
        f"【消息面板块榜·负面】{neg or '-'}",
    ])
    seed = {'date': date_str, 'facts': facts, 'events_used': len(lines),
            'deduped_total': p.get('deduped_total'), 'text': text}
    seed['sha'] = hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]
    return seed, None


def _forces_block():
    return '\n'.join(f"- {n}（权重{wt}）：{d}" for n, wt, d in FORCES)


# ==================== LLM 调用 ====================
def call_llm(messages, cfg, json_mode=True):
    """OpenAI 兼容 /chat/completions。返回 (content, usage)。response_format 不被支持时自动重试。"""
    url = cfg['base_url'].rstrip('/') + '/chat/completions'
    body = {'model': cfg['model'], 'messages': messages,
            'temperature': cfg.get('temperature', 0.3), 'max_tokens': cfg.get('max_tokens', 2600)}
    if json_mode:
        body['response_format'] = {'type': 'json_object'}
    last = None
    for attempt, use_json in enumerate((json_mode, False) if json_mode else (False,)):
        if not use_json:
            body.pop('response_format', None)
        try:
            req = urllib.request.Request(
                url, data=json.dumps(body).encode('utf-8'),
                headers={'Content-Type': 'application/json',
                         'Authorization': 'Bearer ' + cfg['api_key']}, method='POST')
            with urllib.request.urlopen(req, timeout=cfg.get('timeout', 150)) as r:
                j = json.loads(r.read().decode('utf-8', 'replace'))
            return j['choices'][0]['message']['content'], (j.get('usage') or {})
        except urllib.error.HTTPError as e:
            last = f'HTTP {e.code} {e.read()[:200].decode("utf-8", "replace") if hasattr(e, "read") else ""}'
            if e.code in (400, 422) and use_json:
                continue
            raise RuntimeError(last)
        except Exception as e:
            last = f'{type(e).__name__}: {e}'
    raise RuntimeError(last or '未知错误')


def _extract_json(text):
    """容错解析：```json 包裹 / 前后缀 / 尾逗号 / 单引号 / 控制字符 都要能救回来。

    实测（2026-09-30）：deepseek-v4.1-flash 偶发尾逗号 → json.loads 抛
    "Expecting ',' delimiter" 直接把整轮推演打回 rule 回落，所以这里必须多级修复。
    """
    s = (text or '').strip()
    if '```' in s:
        parts = s.split('```')
        if len(parts) >= 2:
            s = parts[1]
        s = s[4:] if s.lstrip().lower().startswith('json') else s
    i, j = s.find('{'), s.rfind('}')
    if i < 0 or j <= i:
        raise ValueError('响应里没有 JSON 对象')
    body = s[i:j + 1]
    cands = [body, re.sub(r',\s*([}\]])', r'\1', body)]
    cands.append(re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', cands[-1]))
    last = None
    for c in cands:
        for kwargs in ({}, {'strict': False}):
            try:
                return json.loads(c, **kwargs)
            except Exception as e:
                last = e
    try:                      # 单引号/True/None 之类的 python 字面量兜底
        import ast
        return ast.literal_eval(cands[0])
    except Exception as e:
        last = e
    raise ValueError(f'JSON 解析失败(多级修复后): {last}')


def _call_json(messages, cfg, dry_run=False, retries=1):
    """调用并解析 JSON：失败时把原文回喂要求"只输出合法 JSON"再试一次。

    返回 (data, usage, raw_content)。
    """
    fn = mock_call if dry_run else call_llm
    msgs, last_err, content = list(messages), None, ''
    for attempt in range(retries + 1):
        content, usage = fn(msgs, cfg)
        try:
            return _extract_json(content), usage, content
        except Exception as e:
            last_err = e
            if attempt < retries:
                w(f'[LLM] 第 {attempt + 1} 次返回不是合法 JSON（{e}），回喂修复提示重试…')
                msgs = msgs + [
                    {'role': 'assistant', 'content': (content or '')[:1200]},
                    {'role': 'user', 'content': '上面这段不是合法 JSON。请只输出合法 JSON：不要 markdown 包裹、'
                                                '不要注释、不要尾逗号，字段与要求完全一致。'},
                ]
    raise ValueError(f'JSON 解析失败(已重试 {retries} 次): {last_err}')


MOCK_RESPONSE = {
    'impact': {'国家队': 8, '机构': 12, '游资': 22, '团伙(控盘)': 14, '散户': 18,
               '北向': 6, '量化': 4, '产业资本': 5, '大散户': 15},
    'theme_priority': [
        {'sector': '银行', 'polarity': 1, 'strength': 7, 'reason': '央行连发政策工具+PSL降息扩围，增量资金预期明确'},
        {'sector': '汽车', 'polarity': 1, 'strength': 6, 'reason': '以旧换新销售额1.55万亿+汽车第一城万亿目标'},
        {'sector': '创新药', 'polarity': 1, 'strength': 5, 'reason': '医药工业十五五规划落地，科创板创新药械长期利好'},
    ],
    'risk_points': [
        {'item': '节前最后一个交易日成交缩量', 'reason': '缩量行情下高位股接力易断，长假不确定性压制仓位'},
        {'item': '科技板块高位分歧（科创50走弱）', 'reason': 'AI/半导体消息面强但盘面走弱，兑现压力大'},
    ],
    'scenarios': {
        'optimistic': {'trigger': '节前资金抢筹+政策持续发酵', 'path': '指数稳中偏强，金融/汽车承接，情绪分回到60上方',
                       'sectors': ['银行', '券商', '汽车']},
        'neutral': {'trigger': '存量博弈延续', 'path': '指数窄幅震荡，题材轮动快、持续性弱', 'sectors': ['创新药', '汽车零部件']},
        'pessimistic': {'trigger': '高位科技股补跌+缩量', 'path': '情绪分回落、涨停梯队断层，防守为主', 'sectors': ['高股息', '公用事业']},
    },
    'key_variables': ['节后首个交易日的竞价强度', '政策落地力度（降准/贴息）', '科技板块能否止跌'],
    'narrative': '消息面偏暖但集中在政策与消费，缺乏新增量资金证据；短线资金更可能做低位补涨而非追高位科技。',
    'confidence': 0.62,
}


MOCK_ROUND = {
    'adjust': {'国家队': 2, '机构': -3, '游资': 5, '团伙(控盘)': 4, '散户': 6,
               '北向': 1, '量化': -2, '产业资本': 1, '大散户': 5},
    'cross': '游资与小散接力情绪票，机构借政策利好逢高派发，量能在缩量中撤退。',
    'next_day': '次日合力偏多但强度有限（存量博弈，需竞价确认）。',
    'confidence': 0.58,
}


def mock_call(messages, cfg, json_mode=True):
    """dry-run 专用：按提示词形态返回对应样例（第一轮=冲击矩阵，后续轮=博弈修正）"""
    user = ' '.join(m.get('content', '') for m in messages if m.get('role') == 'user')
    body = MOCK_ROUND if '"adjust"' in user else MOCK_RESPONSE
    return json.dumps(body, ensure_ascii=False), {'prompt_tokens': 1234, 'completion_tokens': 456,
                                                  'total_tokens': 1690, 'mock': True}


# ==================== 推演 ====================
def deduce_impact(seed, cfg, dry_run=False):
    """第 1 次调用：事件表 → 九方冲击矩阵 + 板块优先级 + 风险点 + 三档情景"""
    user = '\n'.join([
        '【今日消息面】（这是唯一事实来源，禁止引入其它消息）',
        seed['text'],
        '',
        '【九方势力（人格与权重，用于判断冲击归属）】',
        _forces_block(),
        '',
        '【任务】基于上述事件，输出严格 JSON：',
        '{',
        '  "impact": {"国家队": 整数[-40,40], "机构": ..., "游资": ..., "团伙(控盘)": ..., "散户": ...,',
        '             "北向": ..., "量化": ..., "产业资本": ..., "大散户": ...},',
        '  "theme_priority": [{"sector": "板块名", "polarity": 1或-1或0, "strength": 0-10, "reason": "≤30字"}],',
        '  "risk_points": [{"item": "≤20字", "reason": "≤30字"}],',
        '  "scenarios": {"optimistic": {"trigger":"","path":"","sectors":[]},',
        '                "neutral": {...}, "pessimistic": {...}},',
        '  "key_variables": ["≤20字"],',
        '  "narrative": "≤60字的次日博弈总结",',
        '  "confidence": 0.0-1.0',
        '}',
        '约束：impact 只填数字（对每方势力的净冲击，正=偏多/加仓，负=偏空/减仓）；',
        '      事件不足以支撑的信息宁可给接近 0 的值；theme_priority 最多 6 项，risk_points 最多 4 项。',
    ])
    return _call_json([{'role': 'system', 'content': SYSTEM_PROMPT},
                       {'role': 'user', 'content': user}], cfg, dry_run=dry_run)


def play_round(rnd, seed, stances, cfg, dry_run=False, prev_note=''):
    """第 2..N 次调用：让 LLM 在"势力博弈"里做修正与相互关系判断（数值仍由规则引擎算）"""
    user = '\n'.join([
        '【今日消息面摘要】', seed['text'][:1200],
        '',
        f'【当前（第 {rnd} 轮）九方势力立场 -100~+100】',
        json.dumps({k: round(v) for k, v in stances.items()}, ensure_ascii=False),
        (f'【上一轮模型判断】{prev_note}' if prev_note else ''),
        '',
        '【任务】判断经过本轮互相影响后，各势力立场应如何**微调**（每个 -15..+15），并说明谁在接谁的货。输出 JSON：',
        '{"adjust": {"国家队": 整数[-15,15], ... 九方},',
        ' "cross": "≤50字：谁在给谁接货/谁在撤退",',
        ' "next_day": "≤40字：次日合力方向与强度定性",',
        ' "confidence": 0.0-1.0}',
    ])
    return _call_json([{'role': 'system', 'content': SYSTEM_PROMPT},
                       {'role': 'user', 'content': user}], cfg, dry_run=dry_run)


def run(date_str=None, rounds=None, top_events=None, dry_run=False, quiet=False):
    """完整推演：种子 → 冲击矩阵 → 多轮修正 → 结构化报告落盘。返回 payload（失败返回 {'ok': False,...}）"""
    cfg = load_llm_config(quiet=quiet)
    rounds = rounds or cfg.get('rounds', 3)
    top_events = top_events or cfg.get('top_events', 20)
    if not cfg['has_key'] and not dry_run:
        return {'ok': False, 'engine': 'rule', 'reason': 'no_api_key',
                'hint': f'把密钥填进 {CFG_PATH}（模板：{CFG_EXAMPLE.name}），或设 STOCK_LLM_API_KEY'}
    seed, err = build_seed(date_str, top_events)
    if err:
        return {'ok': False, 'engine': 'rule', 'reason': 'no_seed', 'hint': err}

    t0 = time.time()
    usages = []
    resp, u0, raw0 = deduce_impact(seed, cfg, dry_run=dry_run)
    usages.append(u0)
    weights = FORCE_WEIGHT
    # 注意: deduce_impact 返回的是整个响应体, 冲击矩阵在 resp['impact']
    impact_map = {str(k): v for k, v in (resp.get('impact') or {}).items()}
    stances = {}
    for n, _wt, _d in FORCES:
        try:
            stances[n] = max(-100.0, min(100.0, float(impact_map.get(n, 0))))
        except (TypeError, ValueError):
            stances[n] = 0.0
    round_rows, prev_note = [], ''
    partial = False
    for rnd in range(2, max(rounds, 1) + 1):
        try:
            data, u, _raw = play_round(rnd, seed, stances, cfg, dry_run=dry_run, prev_note=prev_note)
        except Exception as e:
            # 单轮失败不再把整场推演打回回落：记下错误、保留上一轮立场继续
            partial = True
            round_rows.append({'round': rnd, 'error': f'{type(e).__name__}: {e}',
                               'stances': {k: round(v, 1) for k, v in stances.items()}})
            w(f'[LLM] 第 {rnd} 轮失败，保留上一轮立场继续：{type(e).__name__}: {e}')
            continue
        adj = data.get('adjust') or {}
        for n in stances:
            try:
                a = float(adj.get(n, 0))
            except Exception:
                a = 0.0
            stances[n] = max(-100.0, min(100.0, stances[n] + max(-15.0, min(15.0, a))))
        prev_note = data.get('cross', '')
        round_rows.append({'round': rnd, 'stances': {k: round(v, 1) for k, v in stances.items()},
                           'cross': data.get('cross', ''), 'next_day': data.get('next_day', ''),
                           'confidence': data.get('confidence')})
        usages.append(u)
    net = sum(stances[n] * weights[n] for n in stances)
    wsum = sum(weights[n] for n in stances) or 1.0
    payload = {
        'ok': True, 'engine': 'llm', 'dry_run': bool(dry_run), 'partial': partial,
        'date': seed['date'], 'generated_at': dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'model': cfg['model'], 'llm_source': cfg['source'], 'seed_sha': seed['sha'],
        'seed_stats': {'events_used': seed['events_used'], 'deduped_total': seed['deduped_total'],
                       'facts': seed['facts']},
        'impact': {k: round(float(impact_map.get(k) or 0), 1) for k in weights},
        'theme_priority': resp.get('theme_priority') or [],
        'risk_points': resp.get('risk_points') or [],
        'scenarios': resp.get('scenarios') or {},
        'key_variables': resp.get('key_variables') or [],
        'narrative': resp.get('narrative', ''),
        'confidence': resp.get('confidence'),
        'rounds': round_rows,
        'stances_final': {k: round(v, 1) for k, v in stances.items()},
        'net': round(net, 1), 'net_pct': round(net / wsum, 1),
        'usage': {'calls': len(usages), 'total_tokens': sum(int(u.get('total_tokens') or 0) for u in usages)},
        'elapsed_s': round(time.time() - t0, 1),
    }
    LLM_DIR.mkdir(parents=True, exist_ok=True)
    out = LLM_DIR / f"sim-{seed['date']}.json"
    out.write_text(json.dumps({**payload, 'raw_first_call': raw0[:4000]}, ensure_ascii=False, indent=1),
                   encoding='utf-8')
    payload['saved_to'] = str(out)
    if not quiet:
        print_report(payload)
    return payload


def print_report(p):
    w('')
    w('=' * 78)
    w(f"LLM 消息面推演 · {p['date']}（模型 {p['model']}｜{p['llm_source']}｜"
      f"{'DRY-RUN 样例' if p['dry_run'] else '真实调用'}）")
    w('=' * 78)
    w(f"种子: 事件 {p['seed_stats']['events_used']} 条（当日去重共 {p['seed_stats']['deduped_total']} 条）"
      f" | sha {p['seed_sha']} | 微结构 {json.dumps(p['seed_stats']['facts'], ensure_ascii=False)}")
    w('')
    w('【九方冲击矩阵】LLM 判断（-40~+40）')
    for n, wt, _d in FORCES:
        w(f"  {n:<10} 权重{wt}  {p['impact'][n]:+6.1f}   {FORCE_DESC[n][:26]}")
    w(f"  加权合力: {p['net']:+.1f}（单位刻度 {p['net_pct']:+.1f}）")
    if p['rounds']:
        w('')
        w('【多轮博弈修正】')
        for r in p['rounds']:
            w(f"  R{r['round']}: {r.get('cross', '')}")
            w(f"       次日定性: {r.get('next_day', '')}（置信 {r.get('confidence')}）")
    if p['theme_priority']:
        w('')
        w('【板块/题材优先级】')
        for t in p['theme_priority'][:6]:
            w(f"  {'+' if t.get('polarity', 0) > 0 else ('-' if t.get('polarity', 0) < 0 else '·')} "
              f"{t.get('sector', ''):<10} 强度{t.get('strength')}  {t.get('reason', '')[:36]}")
    if p['risk_points']:
        w('')
        w('【风险点】')
        for r in p['risk_points'][:4]:
            w(f"  ! {r.get('item', '')} —— {r.get('reason', '')[:40]}")
    if p['scenarios']:
        w('')
        w('【三档情景预案】')
        for k, label in (('optimistic', '乐观'), ('neutral', '中性'), ('pessimistic', '悲观')):
            s = p['scenarios'].get(k) or {}
            if s:
                w(f"  {label}: 触发[{s.get('trigger', '')}] → {s.get('path', '')}"
                  f" | 方向 {','.join(s.get('sectors') or [])}")
    w('')
    w(f"【叙事】{p['narrative']}")
    w(f"【关键变量】{' / '.join(p['key_variables'][:5])}")
    w(f"【成本】{p['usage']['calls']} 次调用 / {p['usage']['total_tokens']} tokens / {p['elapsed_s']}s")
    w(f"【归档】{p.get('saved_to')}")


def main():
    ap = argparse.ArgumentParser(description='LLM 消息面推演（事件表 → 九方冲击矩阵 → 多轮博弈 → 预案）')
    ap.add_argument('--date', default=None)
    ap.add_argument('--rounds', type=int, default=None)
    ap.add_argument('--top-events', type=int, default=None)
    ap.add_argument('--dry-run', action='store_true', help='不调 API，用内置样例响应验证链路')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    p = run(date_str=a.date, rounds=a.rounds, top_events=a.top_events, dry_run=a.dry_run)
    if a.json:
        print(json.dumps(p, ensure_ascii=False))
    if not p.get('ok'):
        w(f"[推演未执行] {p.get('reason')} —— {p.get('hint')}")
        raise SystemExit(2)


if __name__ == '__main__':
    main()