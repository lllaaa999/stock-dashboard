# -*- coding: utf-8 -*-
"""单元测试：统一数据层 (data_layer)
覆盖：批量实时行情规范输出、标准日K线结构、TDX多周期分钟K线、09:15-09:25竞价分笔切片"""
import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))
import data_layer

class TestDataLayer(unittest.TestCase):
    def test_clean_code(self):
        m, c = data_layer._clean_code('sh.600519')
        self.assertEqual(m, 1)
        self.assertEqual(c, '600519')

        m, c = data_layer._clean_code('sz000001')
        self.assertEqual(m, 0)
        self.assertEqual(c, '000001')

    def test_realtime_quotes(self):
        quotes = data_layer.realtime_quotes(['600519', '000001'])
        self.assertIsInstance(quotes, list)
        self.assertGreaterEqual(len(quotes), 1)
        q = quotes[0]
        for key in ['code', 'name', 'price', 'pct', 'amount', 'vol', 'open', 'high', 'low', 'last_close']:
            self.assertIn(key, q)
        self.assertGreater(q['price'], 0)

    def test_kline_format(self):
        kl = data_layer.kline('600519', days=5)
        self.assertIsNotNone(kl)
        self.assertGreaterEqual(len(kl), 1)
        row = kl[-1]
        self.assertEqual(len(row), 6)  # [date, open, close, high, low, vol]
        self.assertIsInstance(row[0], str)
        self.assertGreater(row[2], 0)   # close > 0

    def test_min_kline_format(self):
        k5 = data_layer.min_kline('600519', n=3, freq='5m')
        if k5:  # TDX 可用时应返回标准结构
            self.assertGreaterEqual(len(k5), 1)
            row = k5[-1]
            self.assertEqual(len(row), 7)  # [datetime, open, close, high, low, vol, amount]
            self.assertGreater(row[2], 0)

    def test_auction_ticks_format(self):
        auc = data_layer.auction_ticks('600519')
        self.assertIsInstance(auc, list)
        if auc:
            first = auc[0]
            self.assertIn('time', first)
            self.assertIn('price', first)
            self.assertIn('buyorsell', first)
            self.assertLessEqual(first['time'], '09:25')

if __name__ == '__main__':
    unittest.main()
