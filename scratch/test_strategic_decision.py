import sys
sys.path.insert(0, 'scripts')
import strategic_decision as sd

def test_strategic_engine():
    # 场景 1: 防御期 (炸板高、跌停多、接力弱)
    emo_defense = {
        'score': 35,
        'zb_rate': 42.0,
        'dt_count': 15,
        'zt_count': 30,
        'zb_count': 22,
        'rate_1to2': 8.0,
        'premium_next_open': 0.1,
        'max_lb': 7,
        'themes': [{'name': '公用事业', 'count': 4}]
    }
    sec_defense = {'inflow': [{'name': '公用事业', 'flow': 10.5}], 'outflow': []}
    idx_defense = [{'name': '上证指数', 'pct': 0.8}] # 指数红，但底层差 => 实事求是背离报警
    
    r1 = sd.analyze_strategic_decision(emo=emo_defense, sec=sec_defense, idxs=idx_defense)
    assert r1['phase']['key'] == 'defense', f"Expected defense, got {r1['phase']['key']}"
    assert r1['reality_check']['status'] == 'danger'
    assert '公用事业' in r1['contradiction']['primary_theme']
    print("PASS: Defense Scenario & Reality Check")

    # 场景 2: 反攻期 (情绪高涨、炸板低、接力强)
    emo_counter = {
        'score': 82,
        'zb_rate': 12.0,
        'dt_count': 0,
        'zt_count': 85,
        'zb_count': 10,
        'rate_1to2': 35.0,
        'premium_next_open': 3.5,
        'max_lb': 9,
        'themes': [{'name': '半导体', 'count': 25}, {'name': '人工智能', 'count': 18}]
    }
    sec_counter = {'inflow': [{'name': '半导体', 'flow': 85.0}], 'outflow': []}
    idx_counter = [{'name': '创业板指', 'pct': 3.2}]

    r2 = sd.analyze_strategic_decision(emo=emo_counter, sec=sec_counter, idxs=idx_counter)
    assert r2['phase']['key'] == 'counter', f"Expected counter, got {r2['phase']['key']}"
    assert r2['phase']['pos_pct'] == 80
    assert '半导体' in r2['contradiction']['primary_theme']
    print("PASS: Counter-offensive Scenario & Tactics")

    print("\nALL STRATEGIC DECISION UNIT TESTS PASSED!")

if __name__ == '__main__':
    test_strategic_engine()
