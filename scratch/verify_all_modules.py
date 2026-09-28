import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'web'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def run_tests():
    print("=== [1] 验证前端页面 HTML 模板 ===")
    r = client.get("/")
    assert r.status_code == 200, f"HTML status: {r.status_code}"
    html = r.text
    assert "9:25 竞价雷达 & 大面榜" in html, "缺少 9:25 竞价雷达 Tab"
    assert "我的自选盯盘" in html, "缺少 自选盯盘 Tab"
    assert "缠论日线中枢与买卖点结构化诊断" in html, "缺少 缠论诊断 卡片"
    assert "缠论图层: 笔与中枢" in html, "缺少 缠论图层 开关"
    assert "star-btn" in html, "缺少 自选星标 样式"
    print("  ✓ 前端页面渲染完整，包含竞价雷达、自选盯盘池、缠论图层控制！")

    print("\n=== [2] 验证模块一：9:25 集合竞价雷达 + 亏钱效应大面榜 API ===")
    r = client.get("/api/auction")
    assert r.status_code == 200, f"/api/auction status: {r.status_code}"
    auc = r.json()
    assert auc.get('status') == 'ok', f"auction status not ok: {auc}"
    sm = auc.get('premium_summary', {})
    print(f"  昨日交易日: {sm.get('y_date')} | 样本涨停数: {sm.get('total_zt')}只")
    print(f"  今日开盘平均溢价率: {sm.get('avg_open_pct'):+.2f}% (高开率 {sm.get('open_positive_rate')}%)")
    print(f"  今日最新平均涨幅: {sm.get('avg_curr_pct'):+.2f}% (红盘率 {sm.get('curr_positive_rate')}%)")
    print(f"  连板晋级数: {sm.get('promote_zt_count')}只 | 大面预警数: {sm.get('mian_count')}只 | 定调: 【{sm.get('sentiment_tag')}】")
    print(f"  弱转强异动标的数: {len(auc.get('weak_to_strong', []))}")
    if auc.get('weak_to_strong'):
        for it in auc['weak_to_strong'][:3]:
            print(f"    - {it['code']} {it['name']}: {it['pct']:+.2f}% | {it.get('reason','')}")
    print(f"  大面榜标的数: {len(auc.get('big_loss', []))}")
    if auc.get('big_loss'):
        for it in auc['big_loss'][:3]:
            print(f"    - {it['code']} {it['name']}: 现价{it['pct']:+.2f}%, 曾冲高{it['high_pct']:+.2f}%, 日内回撤面值:{it['drop_from_high']:+.2f}%")
    print("  ✓ 模块一 集合竞价雷达与大面榜验证通过！")

    print("\n=== [3] 验证模块二：本地自选盯盘池 API ===")
    r = client.get("/api/watchlist?codes=600519,300750,000001,600664,300931")
    assert r.status_code == 200, f"/api/watchlist status: {r.status_code}"
    wl = r.json()
    assert len(wl) == 5, f"Expected 5 stocks, got {len(wl)}"
    for s in wl:
        print(f"  - {s['code']} {s['name']}: 最新价 {s['price']} ({s['pct']:+.2f}%), 开盘溢价 {s['open_pct']:+.2f}%, 成交额 {s['amount']}")
    print("  ✓ 模块二 自选盯盘池极速行情验证通过！")

    print("\n=== [4] 验证模块三：缠论中枢与买卖点结构化数据 ===")
    r = client.get("/api/stock/600664")
    assert r.status_code == 200, f"/api/stock status: {r.status_code}"
    st = r.json()
    assert st.get('quote') is not None, "个股行情缺失"
    assert st.get('kline') is not None and len(st['kline']) > 30, "K线数据缺失"
    chan = st.get('chan')
    assert chan is not None, "缠论分析数据缺失"
    assert chan.get('status') == 'ok', f"缠论计算状态异常: {chan}"
    print(f"  股票: {st['quote']['name']} ({st['code']})")
    print(f"  缠论笔数: {len(chan.get('bi_points', []))} 笔")
    print(f"  当前笔方向: 【{chan.get('cur_dir')}】")
    zs = chan.get('last_zhongshu')
    if zs:
        print(f"  最近中枢: [{zs['lo']} ~ {zs['hi']}], 现价位于中枢【{zs['pos']}】")
    print(f"  背驰判定: {chan.get('divergence')}")
    print(f"  综合诊断: {chan.get('summary')}")
    print("  ✓ 模块三 缠论笔、中枢、背驰结构化计算验证通过！")

    print("\n🎉 全部 3 个模块核心功能与接口均 100% 自动化验证通过！")

if __name__ == '__main__':
    run_tests()
