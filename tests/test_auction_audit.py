#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
tests/test_auction_audit.py — 竞价推荐池收盘自动对账与打脸账本单测
"""
import os
import sys
import json
import shutil
import tempfile
import unittest
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

import auction_audit as aa


class TestAuctionAudit(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix='auction_audit_test_')
        self.old_dir = aa.AUCTION_RECORD_DIR
        self.old_ledger = aa.LEDGER_FILE
        aa.AUCTION_RECORD_DIR = self.tmp_dir
        aa.LEDGER_FILE = os.path.join(self.tmp_dir, 'auction_audit_ledger.jsonl')

    def tearDown(self):
        aa.AUCTION_RECORD_DIR = self.old_dir
        aa.LEDGER_FILE = self.old_ledger
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_save_and_get_candidates(self):
        """快照保存与读取"""
        sample_radar = {
            'weak_to_strong': [{'code': '000001', 'name': '平安银行', 'open_pct': 2.5, 'vol_ratio': 1.8}],
            'auction_boom': [{'code': '000002', 'name': '万科A', 'open_pct': 1.2, 'vol_ratio': 3.5}],
            'fake_high_opens': [{'code': '600000', 'name': '浦发银行', 'open_pct': 3.0, 'vol_ratio': 0.4}],
        }
        ok, msg = aa.save_auction_candidates_snapshot('20261020', sample_radar)
        self.assertTrue(ok)
        loaded = aa.get_auction_candidates('20261020')
        self.assertIsNotNone(loaded)
        self.assertEqual(len(loaded['weak_to_strong']), 1)
        self.assertEqual(loaded['weak_to_strong'][0]['code'], '000001')

    def test_audit_single_group_metrics(self):
        """组内对账统计指标计算"""
        items = [
            {'code': '000001', 'name': '个股A', 'open_pct': 2.0, 'vol_ratio': 1.5, 'amount_ratio_pct': 6.0},
            {'code': '000002', 'name': '个股B', 'open_pct': 1.0, 'vol_ratio': 2.0, 'amount_ratio_pct': 8.0},
        ]
        zt_codes = {'000001'}  # 000001 封板成功
        zb_codes = {'000002'}  # 000002 炸板
        res = aa._audit_single_group(items, zt_codes, zb_codes, '20261020')
        self.assertEqual(res['count'], 2)
        self.assertEqual(res['zt_count'], 1)
        self.assertEqual(res['zt_rate'], 50.0)
        self.assertEqual(res['zb_count'], 1)
        self.assertEqual(res['zb_rate'], 50.0)
        self.assertEqual(len(res['details']), 2)

    def test_ledger_upsert_and_summary(self):
        """对账打脸总账本持久化与汇总"""
        sample_audit = {
            'audited_at': '2026-10-20 15:35:00',
            'summary': {
                'weak_to_strong': {'count': 4, 'zt_rate': 75.0, 'win_rate': 100.0, 'avg_pnl': 3.5, 'big_loss_rate': 0.0},
                'fake_high_opens_control': {'count': 2, 'zt_rate': 0.0, 'win_rate': 0.0, 'avg_pnl': -4.2, 'big_loss_rate': 50.0},
            }
        }
        aa._upsert_ledger('20261020', sample_audit)
        ledger = aa.get_auction_audit_ledger()
        self.assertEqual(ledger['total_days'], 1)
        self.assertEqual(ledger['total_wts_stocks'], 4)
        self.assertEqual(ledger['cum_zt_rate'], 75.0)
        self.assertEqual(ledger['cum_win_rate'], 100.0)
        self.assertEqual(ledger['cum_avg_pnl'], 3.5)


if __name__ == '__main__':
    unittest.main()


class TestAuditIntegrityGuards(unittest.TestCase):
    """「不能用结果预测结果」的护栏测试。

    背景（2026-10-26 实证）：快照全是收盘后抓的（含后见之明），
    还有一条休市日（周六 20261025）的假对账混进了打脸账本。
    这几条测试把四条护栏锁死：
      ① 非交易日拒绝对账 ② 快照缺失不伪造补录
      ③ 收盘后快照标 synthetic ④ 合成样本不进胜率统计
    """

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix='auction_guard_test_')
        self.old_dir = aa.AUCTION_RECORD_DIR
        self.old_ledger = aa.LEDGER_FILE
        aa.AUCTION_RECORD_DIR = self.tmp_dir
        aa.LEDGER_FILE = os.path.join(self.tmp_dir, 'auction_audit_ledger.jsonl')
        self._orig_trading = aa._is_trading_day

    def tearDown(self):
        aa.AUCTION_RECORD_DIR = self.old_dir
        aa.LEDGER_FILE = self.old_ledger
        aa._is_trading_day = self._orig_trading
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_non_trading_day_rejected_and_no_file(self):
        aa._is_trading_day = lambda ymd: False
        res = aa.audit_auction_for_day('20261025')
        self.assertEqual(res['status'], 'not_trading_day')
        self.assertFalse(os.path.exists(os.path.join(self.tmp_dir, 'auction_audit_20261025.json')),
                         '非交易日不得生成对账档案')

    def test_missing_snapshot_is_not_fabricated(self):
        aa._is_trading_day = lambda ymd: True
        res = aa.audit_auction_for_day('20261021')
        self.assertEqual(res['status'], 'no_candidates')
        self.assertFalse(os.path.exists(os.path.join(self.tmp_dir, 'auction_candidates_20261021.json')),
                         '不得用当前雷达伪造历史快照')

    def test_post_close_snapshot_marked_synthetic(self):
        sample = {'weak_to_strong': [], 'auction_boom': [], 'fake_high_opens': []}
        aa.save_auction_candidates_snapshot('20261020', sample, phase='post_close')
        self.assertTrue(aa.get_auction_candidates('20261020')['synthetic'])
        aa.save_auction_candidates_snapshot('20261022', sample, phase='auction')
        self.assertFalse(aa.get_auction_candidates('20261022')['synthetic'])

    def test_synthetic_rows_excluded_from_hit_rate(self):
        aa._is_trading_day = lambda ymd: True
        res = {
            'audited_at': '2026-10-20 15:30:00',
            'synthetic': True,
            'summary': {
                'weak_to_strong': {'count': 3, 'zt_rate': 100.0, 'win_rate': 100.0,
                                   'avg_pnl': 9.9, 'big_loss_rate': 0.0},
                'fake_high_opens_control': {'count': 0, 'avg_pnl': 0.0, 'big_loss_rate': 0.0},
            },
        }
        aa._upsert_ledger('20261020', res)
        ledger = aa.get_auction_audit_ledger()
        self.assertEqual(ledger['total_days'], 0, '合成样本不能算进有效天数')
        self.assertEqual(ledger['excluded_synthetic_days'], 1)
        self.assertEqual(ledger['cum_win_rate'], 0.0, '合成样本不能影响胜率')
        self.assertEqual(ledger['cum_zt_rate'], 0.0)
