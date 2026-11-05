# -*- coding: utf-8 -*-
import os
import sys
import json
import tempfile
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
sys.path.insert(0, os.path.join(ROOT, 'web'))

import market_gateway as mg
import quant_data_service as qds
import auction_radar as ar


class TestP0P1Fixes(unittest.TestCase):
    def test_fallback_quotes_mapping(self):
        fake_feed = {
            '000530': {
                'name': '冰山冷热',
                'price': 6.60,
                'pre_close': 6.00,
                'open': 6.10,
                'high': 6.60,
                'low': 6.05,
                'pct': 10.0,
                'volume': 125000,
                'amount': 82500000.0,
                'turnover': 4.8,
                'vol_ratio': 2.3,
                'pe': 25.0,
                'pb': 1.8,
                'total_mv': 55.6,
                'circ_mv': 42.1,
            }
        }
        with patch.object(mg.df_feed, 'get_realtime_quotes', return_value=fake_feed):
            res = mg._fetch_quotes_via_fallback(['000530.SZ'])
            self.assertIn('000530.SZ', res)
            q = res['000530.SZ']
            self.assertEqual(q['price'], 6.60)
            self.assertEqual(q['phase'], 'LIMIT_UP')
            self.assertEqual(q['limitUpPrice'], 6.60)
            self.assertEqual(len(q['orderBook']['bids']), 5)

    def test_dragon_tiger_cross_day_guard_and_ledger_stats(self):
        fake_b = [
            {
                'OPERATEDEPT_NAME': '国泰君安证券股份有限公司南京太平南路证券营业部',
                'BUY': 55000000.0,
                'SELL': 500000.0,
                'ACCUM_AMOUNT': 450000000.0,
                'CLOSE_PRICE': 15.20,
                'CHANGE_RATE': 4.15,  # 非涨停趋势股
                'SECURITY_NAME_ABBR': '测试科技',
                'EXPLANATION': '日振幅值达15%的前五只证券',
            }
        ]
        fake_s = [
            {
                'OPERATEDEPT_NAME': '东方财富证券股份有限公司拉萨团结路第二证券营业部',
                'BUY': 2000000.0,
                'SELL': 18000000.0,
                'ACCUM_AMOUNT': 450000000.0,
                'CLOSE_PRICE': 15.20,
                'CHANGE_RATE': 4.15,
            }
        ]
        today_str = qds.dt.date.today().strftime('%Y-%m-%d')
        def fake_lhb(code, ds, side):
            if ds != today_str:
                return fake_b if side == 'B' else fake_s
            return []

        with patch.object(qds, 'get_today_lhb_list', return_value=[]), \
             patch.object(qds.sd, '_lhb_detail', side_effect=fake_lhb), \
             patch.object(qds, '_ultra_pool_index', return_value={'ymd': '20991231'}):
            out = qds.get_real_dragon_tiger('000530.SZ')
            self.assertEqual(out['status'], 'ok')
            self.assertTrue(out['hasLhb'])
            analysis = out['analysis']
            # 历史榜单不应混用当日分时 DVR，必须保持 historical_board_neutral
            self.assertEqual(analysis['microDimensions']['vwDvrSource'], 'historical_board_neutral')
            self.assertFalse(analysis['microDimensions']['isCurrentDayBoard'])
            self.assertIn('vetoTags', analysis)
            # 席位应挂载真实账本信誉字段
            b0 = analysis['buySeats'][0]
            self.assertIn('reputationGamma', b0)
            self.assertIn('ledgerAppearances', b0)
            self.assertGreaterEqual(b0['ledgerAppearances'], 1)

    def test_full_market_scan_frozen_after_0930(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rec_dir = os.path.join(tmpdir, 'auction_records')
            os.makedirs(rec_dir, exist_ok=True)
            today_ymd = ar.dt.datetime.now().strftime('%Y%m%d')
            snap_file = os.path.join(rec_dir, f'full_market_scan_{today_ymd}.json')
            frozen_payload = {
                'status': 'ok',
                'basis': 'auction',
                'scan_items': [
                    {
                        'code': '000530',
                        'name': '冰山冷热',
                        'price': 6.30,
                        'open_price': 6.30,
                        'open_pct': 5.0,
                        'pct': 5.0,
                        'vol_ratio': 4.2,
                        'amount': 35000000.0,
                        'high': 6.30,
                        'low': 6.30,
                        'prev_close': 6.00,
                        'seal_amount': 0.0,
                        'signal': 'SUPER_GRAB',
                        'signalLabel': '超预期抢筹',
                    }
                ],
                'grabCount': 1,
                'nuclearCount': 0,
                'fakeHighCount': 0,
                'lockedCount': 0,
                'total_scanned': 5000,
                'updated_at': '2026-11-05 09:25:10',
            }
            with open(snap_file, 'w', encoding='utf-8') as f:
                json.dump(frozen_payload, f, ensure_ascii=False)

            fake_eastmoney = json.dumps({
                'data': {
                    'diff': [
                        {
                            'f12': '000530',
                            'f14': '冰山冷热',
                            'f2': 6.60,   # 盘中涨停最新价
                            'f3': 10.0,   # 盘中最新涨幅
                            'f10': 0.8,   # 盘中量比回落，不应覆盖 09:25 竞价量比 4.2
                            'f6': 250000000.0,
                            'f18': 6.00,
                            'f15': 6.60,
                            'f16': 6.25,
                            'f17': 6.30,
                            'f31': 6.60,
                            'f32': 0,
                            'f34': 50000,
                        }
                    ]
                }
            })
            with patch.object(ar, '_in_call_auction', return_value=False), \
                 patch.object(ar.sd, 'DATA_DIR', tmpdir), \
                 patch.object(ar.sd, 'http', return_value=fake_eastmoney):
                res = ar.get_full_market_auction_scan()
                self.assertEqual(res['status'], 'ok')
                self.assertEqual(res['basis'], 'auction_frozen')
                item = res['scan_items'][0]
                # 09:25 竞价信号与量比被严格保护，同时现价与现涨幅已更新
                self.assertEqual(item['signal'], 'SUPER_GRAB')
                self.assertEqual(item['vol_ratio'], 4.2)
                self.assertEqual(item['price'], 6.60)
                self.assertEqual(item['pct'], 10.0)


if __name__ == '__main__':
    unittest.main()
