# -*- coding: utf-8 -*-
"""Step1 验证脚本: 数据源健康度阈值(offline 可达) + 降级路径不再编造单笔分层

用法: python scratch/verify_step1.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
import data_feed as df  # noqa: E402

fails = []


def check(name, cond, extra=''):
    print(('PASS  ' if cond else 'FAIL  ') + name + (('   ' + str(extra)) if extra else ''))
    if not cond:
        fails.append(name)


print('== 1. 健康度阈值序列 ==')
seq = []
for i in range(1, 7):
    df._record_status('tencent', False, 0.01)
    seq.append(df.SOURCE_HEALTH['tencent']['status'])
print('   1..6 次连续失败 ->', seq)
check('第3次失败 -> degraded', seq[2] == 'degraded', seq)
check('第5次失败 -> offline (修正前永远不可达)', seq[4] == 'offline', seq)
check('第6次失败仍 offline', seq[5] == 'offline', seq)
df._record_status('tencent', True, 0.02)
check('一次成功后复位 healthy 且 failures=0',
      df.SOURCE_HEALTH['tencent']['status'] == 'healthy' and df.SOURCE_HEALTH['tencent']['failures'] == 0)

print()
print('== 2. 降级路径不造数 (东财被墙 -> 腾讯内外盘兜底) ==')
df.CACHE._cache.clear()


def fake_http(url, gbk=False, timeout=20, retries=3, referer=None, headers=None):
    if 'push2his' in url:
        raise RuntimeError('simulated eastmoney block')
    if 'qt.gtimg.cn' in url:
        parts = [''] * 50
        parts[1] = '哈药股份'
        parts[2] = '600664'
        parts[3] = '5.00'      # 现价
        parts[4] = '4.90'      # 昨收
        parts[5] = '4.95'      # 今开
        parts[7] = '120000'    # 外盘(主动买)
        parts[8] = '80000'     # 内盘(主动卖)
        parts[30] = '20260930150000'
        parts[31] = '0.10'
        parts[32] = '2.04'
        parts[33] = '5.10'
        parts[34] = '4.88'
        parts[36] = '200000'
        parts[37] = '123456'
        return 'v_sh600664="' + '~'.join(parts) + '";'
    raise RuntimeError('unexpected url ' + url)


df.sd.http = fake_http
res = df.get_capital_breakdown('600664')
t = res.get('today') or {}
print('   today =', t)
check('super_net 为 None (不再按比例编造)', t.get('super_net') is None)
check('large_net 为 None', t.get('large_net') is None)
check('med_net / small_net 为 None', t.get('med_net') is None and t.get('small_net') is None)
check('标记 estimated=True', t.get('estimated') is True)
check('标记 source=tencent_inout', t.get('source') == 'tencent_inout')
check('main_net 仍给出(内外盘净额, 0.2亿)', t.get('main_net') == 0.2, t.get('main_net'))
check('history 为空(东财不可用)', res.get('history') == [])

print()
print('FAILED:', fails if fails else '无 —— 全部通过')
sys.exit(1 if fails else 0)