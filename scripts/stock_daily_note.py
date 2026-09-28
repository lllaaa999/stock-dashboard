# -*- coding: utf-8 -*-
"""每日看盘笔记 -> Obsidian 记忆库 (D:\hermes-knowledge\股票日记)
复用 stock_dashboard 七层雷达数据；已有当日笔记则追加"更新"段，不覆盖。
数据采集有 60 秒硬上限（守护线程），超时用已获取的部分数据。
"""
import sys, os, datetime, threading
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
import stock_dashboard as sd

VAULT = r'D:\hermes-knowledge'
NOTE_DIR = os.path.join(VAULT, '股票日记')
GATHER_CAP = 60  # 秒


def safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def main():
    os.makedirs(NOTE_DIR, exist_ok=True)
    today = datetime.date.today().strftime('%Y-%m-%d')
    path = os.path.join(NOTE_DIR, today + '.md')
    now = datetime.datetime.now().strftime('%H:%M')
    exists = os.path.exists(path)

    data = {}
    def gather():
        data['idx'] = safe(lambda: sd.tx_realtime(sd.IDX_CODES), [])
        data['emo'] = safe(lambda: sd.emotion(), None)
        data['glo'] = safe(lambda: sd.global_markets(), None)
        data['sec'] = safe(lambda: sd.sector_flow(), None)
        data['mar'] = safe(lambda: sd.margin_total(), None)
        data['nws'] = safe(lambda: sd.news(6), None)
    t = threading.Thread(target=gather, daemon=True)
    t.start()
    t.join(GATHER_CAP)
    finished = not t.is_alive()

    idx = data.get('idx') or []
    emo = data.get('emo')
    glo = data.get('glo')
    sec = data.get('sec')
    mar = data.get('mar')
    nws = data.get('nws')

    L = []
    if not exists:
        L.append('---')
        L.append(f'tags: [股票, 看盘, {today}]')
        L.append(f'created: {today}')
        L.append('---')
        L.append(f'# 每日看盘 {today}')
        L.append('')
    else:
        L.append(f'## 更新 {now}')
        L.append('')
    L.append(f'> 来源：七层雷达仪表盘 (http://127.0.0.1:8001) · 更新 {now}' + ('' if finished else ' · ⚠️ 部分数据超时未取到'))

    L.append('')
    L.append('## 指数')
    if idx:
        for q in idx:
            L.append(f"- {q['name']}（{q['code']}）：{q['price']} ({q['pct']:+.2f}%) 额{q['amount']}")
    else:
        L.append('- 数据获取失败/超时')

    L.append('')
    L.append('## 隔夜外盘')
    if glo:
        L.append(f"- A50期货：{glo['a50']} ({glo['a50_pct']})")
        L.append(f"- 纳指期货：{glo['nq']} ({glo['nq_pct']})")
        L.append(f"- COMEX金：{glo['gold']} | WTI油：{glo['oil']}")
        L.append(f"- USDCNH：{glo['usdcnh']} ({glo['usdcnh_pct']})")
    else:
        L.append('- 数据获取失败/超时')

    L.append('')
    L.append('## 情绪指数')
    if emo:
        br = emo['zb'] / (emo['zt'] + emo['zb']) * 100 if (emo['zt'] + emo['zb']) else 0
        L.append(f"- 情绪：**{emo['score']:.2f}/100 [{emo['band']}]**")
        L.append(f"- 涨停 {emo['zt']} / 炸板 {emo['zb']}（率 {br:.0f}%）/ 跌停 {emo['dt']} / 最高连板 {emo['max_lb']}板")
    else:
        L.append('- 数据获取失败/超时')

    L.append('')
    L.append('## 板块主力资金')
    if sec:
        top_in = ', '.join(f"{r['name']}({r['flow']:+.1f}亿)" for r in (sec.get('inflow') or [])[:5])
        top_out = ', '.join(f"{r['name']}({r['flow']:+.1f}亿)" for r in (sec.get('outflow') or [])[:3])
        L.append(f"- 流入：{top_in}")
        L.append(f"- 流出：{top_out}")
    else:
        L.append('- 数据获取失败/超时')

    L.append('')
    L.append('## 两融余额')
    if mar:
        for r in mar[:4]:
            L.append(f"- {r['date']}：{r['value']:,.0f}亿")
    else:
        L.append('- 数据获取失败/超时')

    L.append('')
    L.append('## 财经快讯')
    if nws:
        for n in nws[:6]:
            L.append(f"- [{n['time']}] {n['title']}")
    else:
        L.append('- 数据获取失败/超时')

    L.append('')
    L.append('---')
    L.append('> 不构成投资建议 · 由 stock_daily_note.py 自动生成')

    with open(path, 'a' if exists else 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')
    print(f'OK: {path} ({"追加更新" if exists else "新建"}) finished={finished}')


if __name__ == '__main__':
    main()
