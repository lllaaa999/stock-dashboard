import sys, os, time, json
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, 'web')
sys.path.insert(0, 'scripts')
from starlette.testclient import TestClient
from main import app

client = TestClient(app)

report = []

def check(name, fn):
    t0 = time.time()
    try:
        fn()
        elapsed = round((time.time() - t0) * 1000, 1)
        report.append({"name": name, "status": "PASS", "ms": elapsed, "detail": "OK"})
        print(f"[PASS] {name} ({elapsed}ms)")
    except Exception as e:
        elapsed = round((time.time() - t0) * 1000, 1)
        report.append({"name": name, "status": "FAIL", "ms": elapsed, "detail": str(e)})
        print(f"[FAIL] {name} ({elapsed}ms): {e}")

print("==================== 开始全功能深度自检 ====================")

# 1. 基础页面加载
def test_home():
    r = client.get('/')
    assert r.status_code == 200
    html = r.text
    # 核心选项卡
    assert 'tab-radar' in html, "tab-radar 缺失"
    assert 'tab-auction' in html, "tab-auction 缺失"
    assert 'tab-watchlist' in html, "tab-watchlist 缺失"
    assert 'tab-portfolio' in html, "tab-portfolio 缺失"
    assert 'tab-screener' in html, "tab-screener 缺失"
    assert 'tab-sim' in html, "tab-sim 缺失"
    # 弹窗结构与样式必须默认隐藏
    assert 'display: none;' in html, "modal display: none 缺失"
    assert 'id="holdingModal"' in html, "holdingModal 缺失"
    assert 'id="batchHoldingModal"' in html, "batchHoldingModal 缺失"
    assert 'style="display:none;"' in html, "行内隐藏样式缺失"
check("1.1 首页 HTML 与 6 大核心选项卡渲染", test_home)

# 2. 大盘全景雷达
def test_market():
    r = client.get('/api/market?refresh=1')
    assert r.status_code == 200
    d = r.json()
    assert len(d.get('indices', [])) >= 4, "指数数量不足"
    assert len(d.get('globals', [])) >= 4, "隔夜外盘数量不足"
    assert d.get('emotion') is not None, "情绪数据缺失"
    assert len(d.get('sectors', {}).get('inflow', [])) > 0, "行业资金流入缺失"
    assert d.get('news') is not None, "快讯数据缺失"
check("2.1 大盘全景雷达 API (/api/market)", test_market)

def test_emotion_history():
    r = client.get('/api/emotion/history')
    assert r.status_code == 200
    hist = r.json()
    assert len(hist) >= 20, f"历史情绪记录仅 {len(hist)} 条，不足20条"
    assert hist[-1].get('date') is not None
    assert hist[-1].get('score') is not None
check("2.2 情绪周期历史走势 API (/api/emotion/history)", test_emotion_history)

# 3. 9:25 竞价雷达与梯队晋级
def test_auction():
    r = client.get('/api/auction?refresh=1')
    assert r.status_code == 200
    d = r.json()
    assert d.get('status') == 'ok'
    pm = d.get('promotion_metrics', {})
    assert pm.get('seal_rate') is not None, "封板率缺失"
    assert pm.get('broken_rate') is not None, "炸板率缺失"
    assert pm.get('max_lbc') is not None, "连板高度缺失"
    assert pm.get('promote_1_to_2_rate') is not None, "首板晋级率缺失"
    assert pm.get('promote_2_to_3_rate') is not None, "二板晋级率缺失"
    assert pm.get('high_tier_promote_rate') is not None, "高标晋级率缺失"
    assert d.get('premium_summary') is not None, "昨涨停溢价汇总缺失"
check("3.1 9:25 集合竞价雷达 & 晋级率指标 (/api/auction)", test_auction)

# 4. 自选股与持仓批量行情通道
def test_watchlist():
    r = client.get('/api/watchlist?codes=600519,300750,000001')
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 3, f"批量行情数量不匹配: {len(items)}"
    for it in items:
        assert it.get('price') is not None and it['price'] > 0
        assert it.get('name') is not None
check("4.1 自选/持仓极速批量行情 API (/api/watchlist)", test_watchlist)

# 5. 情绪周期 12 策略选股库
def test_strategies_auto():
    r = client.get('/api/strategies?mode=auto')
    assert r.status_code == 200
    d = r.json()
    assert d.get('status') == 'ok'
    assert d.get('stage') is not None, "周期定位缺失"
    assert len(d.get('strategies', [])) > 0, "策略列表为空"
    for s in d['strategies']:
        for it in s.get('items', []):
            assert it.get('price') is not None and it['price'] > 0, f"策略标的物价格缺失: {it}"
            assert it.get('pct') is not None, f"策略标的物涨跌幅缺失: {it}"
check("5.1 情绪周期自适应选股 (/api/strategies?mode=auto)", test_strategies_auto)

def test_strategies_all():
    r = client.get('/api/strategies?mode=all')
    assert r.status_code == 200
    d = r.json()
    assert len(d.get('strategies', [])) == 8, f"策略总数预期 8，实际 {len(d.get('strategies', []))}"
check("5.2 策略库全量跑 (/api/strategies?mode=all)", test_strategies_all)

# 6. 经典形态扫描 (测试单形态以保证极速响应)
def test_screen():
    r = client.get('/api/screen?patterns=低吸')
    assert r.status_code == 200
    d = r.json()
    assert d.get('status') == 'ok'
    assert 'summary' in d and 'results' in d
check("6.1 经典形态扫描 API (/api/screen)", test_screen)

# 7. 个股全维体检与缠论诊断
def test_stock_detail():
    r = client.get('/api/stock/600519')
    assert r.status_code == 200
    d = r.json()
    assert d.get('quote') is not None, "盘口数据缺失"
    assert len(d.get('kline', [])) > 30, "K线数据过少"
    # 缠论结构验证
    chan = d.get('chan', {})
    assert chan.get('status') == 'ok', "缠论结构计算失败"
    assert chan.get('cur_dir') in ('向上', '向下'), "缠论当前笔方向异常"
    assert len(chan.get('bi_points', [])) > 0 or len(chan.get('bi_list', [])) > 0, "缠论笔序列为空"
check("7.1 个股体检与缠论中枢可视化 (/api/stock/600519)", test_stock_detail)

# 8. 多主体势力世界模拟
def test_sim():
    r = client.get('/api/sim')
    assert r.status_code == 200
    d = r.json()
    assert d.get('status') == 'ok'
    assert d.get('text') is not None and len(d['text']) > 50
check("8.1 九方势力大盘模拟 (/api/sim)", test_sim)

def test_sim_agent():
    r = client.get('/api/sim?code=600519')
    assert r.status_code == 200
    d = r.json()
    assert d.get('status') == 'ok'
    assert '资金主体' in d.get('text', '') or '合力' in d.get('text', '')
check("8.2 个股多主体博弈推演 (/api/sim?code=600519)", test_sim_agent)

# 9. 数据源健康监控
def test_data_status():
    r = client.get('/api/data_status')
    assert r.status_code == 200
    d = r.json()
    sc = d.get('sources', {})
    assert sc.get('tencent', {}).get('status') == 'healthy', "腾讯通道非健康"
check("9.1 数据源健康状态 API (/api/data_status)", test_data_status)

# 10. 桌面启动脚本验证
def test_bat_scripts():
    desktop_bat = r"C:\Users\28769\Desktop\启动股票看盘.bat"
    root_bat = r"D:\股票看盘\一键启动股票看盘.bat"
    assert os.path.exists(desktop_bat), "桌面启动脚本不存在"
    assert os.path.exists(root_bat), "根目录启动脚本不存在"
    b_desk = open(desktop_bat, 'rb').read()
    b_root = open(root_bat, 'rb').read()
    assert b'\r\n' in b_desk, "桌面脚本未采用 CRLF"
    assert b':8001' in b_desk, "桌面脚本端口缺失"
    assert b'\r\n' in b_root, "根目录脚本未采用 CRLF"
check("10.1 桌面与根目录一键启动批处理完整性", test_bat_scripts)

print("\n==================== 全功能检查汇总 ====================")
all_pass = all(r['status'] == 'PASS' for r in report)
print(f"总检查项: {len(report)} | 通过: {sum(1 for r in report if r['status'] == 'PASS')} | 失败: {sum(1 for r in report if r['status'] == 'FAIL')}")
print(f"最终结果: {'✅ 全部通过 (ALL PASSED)' if all_pass else '❌ 存在异常项'}")
