# -*- coding: utf-8 -*-
"""验证 news_events.py：分类/时效/去重/个股与板块匹配 的离线断言 + 归档数据的实时体检"""
import json
import pathlib
import sys

ROOT = pathlib.Path(r"D:\股票看盘")
sys.path.insert(0, str(ROOT / "scripts"))
import news_events as ne  # noqa: E402

fails = []


def check(name, cond, extra=''):
    print(('PASS  ' if cond else 'FAIL  ') + name + (('   ' + str(extra)) if extra else ''))
    if not cond:
        fails.append(name)


print("== 1. 分类 classify()（词典可解释）==")
c1 = ne.classify('央行宣布全面降准50个基点，释放长期资金约1万亿元')
check("降准+万亿 → 政策 / 正 / 强度≥8", c1['type'] == '政策' and c1['polarity'] == 1 and c1['strength'] >= 8, c1)
c2 = ne.classify('某高位连板妖股盘后遭监管特停核查涉嫌操纵')
check("特停核查 → 负极性", c2['polarity'] == -1, c2)
c3 = ne.classify('公司公告：上半年净利润同比下滑30%，股东拟减持不超过2%股份')
check("公告+下滑+减持 → 公司 / 负", c3['type'] == '公司' and c3['polarity'] == -1, c3)
c4 = ne.classify('美联储宣布降息25BP，美股三大指数集体收涨')
check("美联储+美股 → 海外（不被误判成政策）", c4['type'] == '海外', c4)
c5 = ne.classify('硅料硅片板块走高，弘元绿能涨停，通威股份、大全能源跟涨')
check("板块走高+涨停 → 正极性", c5['polarity'] == 1, c5)
c6 = ne.classify('今日无重要消息')
check("无信号 → 其他 / 中性 / 基础强度 2.0", c6['type'] == '其他' and c6['polarity'] == 0 and c6['strength'] == 2.0, c6)

print()
print("== 2. 时效分桶 time_bucket() ==")
for t, want in [('2026-09-30 09:20:00', '盘前'), ('2026-09-30 11:00:00', '盘中'),
                ('2026-09-30 15:30:00', '盘后'), ('2026-09-30 20:00:00', '隔夜'),
                ('2026-09-30 02:00:00', '隔夜'), ('2026-09-30 09:31:00', '盘中')]:
    got = ne.time_bucket(t)
    check(f"  {t[11:16]} → {want}", got == want, got)

print()
print("== 3. 去重 dedupe()（跨源 + 归档态兼容）==")
raw = [
    {'time': '2026-09-30 10:00:00', 'title': '央行宣布降准50个基点', 'summary': 'A', 'source': '东财7x24'},
    {'time': '2026-09-30 10:00:30', 'title': '【央行宣布降准50个基点】', 'summary': 'B', 'source': '新浪7x24'},
    {'time': '2026-09-30 10:01:00', 'title': '央行宣布降准50个基点，释放万亿资金', 'summary': 'C', 'source': '新浪7x24'},
    {'time': '2026-09-30 10:05:00', 'title': '某公司中标5亿元项目', 'summary': 'D', 'source': '东财快讯'},
]
d = ne.dedupe(raw)
check("4 条输入 → 2 条(3 条降准合并 + 1 条中标)", len(d) == 2, [x['title'][:20] for x in d])
merged = [x for x in d if '降准' in x['title']][0]
check("合并后保留多来源标记", sorted(merged['sources']) == ['东财7x24', '新浪7x24'], merged['sources'])
archived = [{'time': '2026-09-30 10:00:00', 'title': '央行宣布降准50个基点', 'sources': ['东财7x24'], 'summary': ''},
            {'time': '2026-09-30 10:00:10', 'title': '【央行降准50个基点】', 'sources': ['新浪7x24'], 'summary': ''}]
try:
    d2 = ne.dedupe(archived)
    check("归档态输入(有 sources 列表) 不再抛 KeyError", len(d2) == 1, d2)
except Exception as e:
    check("归档态输入(有 sources 列表) 不再抛 KeyError", False, f'{type(e).__name__}: {e}')
check("去重结果可直接 JSON 序列化", isinstance(json.dumps(d, ensure_ascii=False), str))

print()
print("== 4. 个股匹配 match_stocks()（含误判防护）==")
idx = {'弘元绿能': '688185', '通威股份': '600438', '大全能源': '688303', '海南': '600999'}
c2n = {'688185': '弘元绿能', '600438': '通威股份', '688303': '大全能源', '600999': '海南'}
hits = ne.match_stocks('硅料硅片板块走高，弘元绿能涨停，通威股份、大全能源跟涨', idx, c2n)
codes = {h['code'] for h in hits}
check("3 只个股名全部命中", {'688185', '600438', '688303'} <= codes, hits)
h2 = ne.match_stocks('海南旅游旺季来临，三亚酒店预订量上升', idx, c2n)
check("2 字名在无市场语境时不误判(海南)", all(h['name'] != '海南' for h in h2), h2)
h3 = ne.match_stocks('海南板块涨停，本地股集体走强', idx, c2n)
check("2 字名有市场语境时命中", any(h['name'] == '海南' for h in h3), h3)

print()
print("== 5. 板块匹配 match_sectors() ==")
vocab = {'光伏设备', '养殖业', 'AI', '证券'}
s1 = ne.match_sectors('光伏设备板块午后拉升', vocab)
check("中文板块名命中", '光伏设备' in s1, s1)
s2 = ne.match_sectors('AI 算力需求爆发', vocab)
check("拉丁缩写按词边界命中", 'AI' in s2, s2)
s3 = ne.match_sectors('A股今日震荡', vocab)
check("拉丁缩写不误伤(A股 里的 A 不算 AI)", 'AI' not in s3, s3)

print()
print("== 6. 归档数据体检 ==")
import datetime as _dt  # noqa: E402
today = _dt.date.today().strftime('%Y-%m-%d')
ev_path = ROOT / 'data' / 'news' / f'events-{today}.json'
raw_path = ROOT / 'data' / 'news' / f'{today}.jsonl'
if not ev_path.exists():
    check(f"事件表存在 {ev_path.name}（先跑一次 news_events.py）", False)
else:
    p = json.loads(ev_path.read_text(encoding='utf-8'))
    evs = p['events']
    check("事件数 > 200", len(evs) > 200, len(evs))
    check("去重后条数 >= 事件数一致", p['deduped_total'] == len(evs), (p['deduped_total'], len(evs)))
    check("强度全部落在 1~10", all(1.0 <= e['strength'] <= 10.0 for e in evs))
    check("强度已降序", all(evs[i]['strength'] >= evs[i + 1]['strength'] for i in range(min(len(evs) - 1, 500))))
    check("时效桶都在枚举内", set(e['bucket'] for e in evs) <= {'隔夜', '盘前', '盘中', '盘后', '深夜', '未知'},
          set(e['bucket'] for e in evs))
    check("类型分布已统计", sum(p['type_counts'].values()) == len(evs), p['type_counts'])
    check("板块榜非空(正/负)", bool(p['sector_board']['positive']) and bool(p['sector_board']['negative']))
    check("原始 jsonl 存在且行数一致", raw_path.exists() and len(
        [l for l in raw_path.read_text(encoding='utf-8').splitlines() if l.strip()]) == p['deduped_total'], p['deduped_total'])
    top = evs[0]
    print(f"   Top1: [{top['strength']}] {top['type']}/{top['bucket']} {top['title'][:50]}")
    sec = p['sector_board']['positive'][0]
    print(f"   板块榜首: {sec['name']} 条数{sec['count']} 正{sec['pos']}/负{sec['neg']} 强度{sec['strength']}")

print()
print("FAILED:", fails if fails else "无 —— 全部通过")
sys.exit(1 if fails else 0)