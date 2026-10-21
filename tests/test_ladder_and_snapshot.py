#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
tests/test_ladder_and_snapshot.py — 梯队断层结构诊断与盘后不可变快照单测集
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

import stock_dashboard as sd


class TestLadderAndSnapshot(unittest.TestCase):
    def test_ladder_fault_healthy(self):
        """梯队完整层层递进: 1板5只, 2板3只, 3板2只, 4板1只 -> 无断层 healthy"""
        first_boards = [{'c': '000001'}, {'c': '000002'}, {'c': '000003'}, {'c': '000004'}, {'c': '000005'}]
        ladder_grouped = {
            2: [{'c': '000006'}, {'c': '000007'}, {'c': '000008'}],
            3: [{'c': '000009'}, {'c': '000010'}],
            4: [{'c': '000011'}],
        }
        res = sd.analyze_ladder_faults(ladder_grouped, first_boards, max_lb=4)
        self.assertEqual(res['max_height'], 4)
        self.assertFalse(res['has_fault'])
        self.assertEqual(res['status'], 'healthy')
        self.assertEqual(res['tag'], '梯队完整')
        self.assertEqual(res['fault_levels'], [])

    def test_ladder_fault_high_gap(self):
        """高位断层: 最高5板, 但4板空缺(0只), 3板2只, 2板3只 -> high_gap"""
        first_boards = [{'c': '000001'}] * 10
        ladder_grouped = {
            2: [{'c': '000002'}] * 4,
            3: [{'c': '000003'}] * 2,
            5: [{'c': '000005'}],
        }
        res = sd.analyze_ladder_faults(ladder_grouped, first_boards, max_lb=5)
        self.assertEqual(res['max_height'], 5)
        self.assertTrue(res['has_fault'])
        self.assertIn(4, res['fault_levels'])
        self.assertEqual(res['status'], 'high_gap')
        self.assertEqual(res['tag'], '高位断层')

    def test_ladder_fault_seed_gap(self):
        """接力断层: 1进2全军覆没(2板=0只), 但有3板/4板残留标杆 -> seed_gap"""
        first_boards = [{'c': '000001'}] * 8
        ladder_grouped = {
            3: [{'c': '000003'}],
            4: [{'c': '000004'}],
        }
        res = sd.analyze_ladder_faults(ladder_grouped, first_boards, max_lb=4)
        self.assertTrue(res['has_fault'])
        self.assertIn(2, res['fault_levels'])
        self.assertEqual(res['tag'], '接力断层')

    def test_ladder_low_suppression(self):
        """空间受限: 全市场最高仅2板 -> low_suppression"""
        first_boards = [{'c': '000001'}] * 3
        ladder_grouped = {
            2: [{'c': '000002'}]
        }
        res = sd.analyze_ladder_faults(ladder_grouped, first_boards, max_lb=2)
        self.assertFalse(res['has_fault'])
        self.assertEqual(res['status'], 'low_suppression')
        self.assertEqual(res['tag'], '空间受限')

    def test_immutable_snapshot_lifecycle(self):
        """不可变快照生命周期验证"""
        tmp_dir = tempfile.mkdtemp(prefix='snap_test_')
        old_snap_dir = sd.SNAPSHOT_DIR
        sd.SNAPSHOT_DIR = tmp_dir
        try:
            fake_data = {
                'score': 72.5,
                'band': '强势区',
                'zt': 58,
                'zb': 12,
                'dt': 1,
                'max_lb': 4,
                'ladder_analysis': {'tag': '梯队完整', 'status': 'healthy'},
            }
            test_date = '20261019'
            # 1. 成功归档
            ok, msg = sd.archive_daily_snapshot(test_date, fake_data, force=True)
            self.assertTrue(ok)
            snap_file = os.path.join(tmp_dir, f'snapshot_{test_date}.json')
            self.assertTrue(os.path.exists(snap_file))

            # 2. 读取快照
            loaded = sd.get_daily_snapshot(test_date)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded['score'], 72.5)
            self.assertTrue(loaded['immutable'])

            # 3. 不可变性测试：非 force 再次归档不能随意篡改数据
            modified_data = dict(fake_data, score=99.9)
            ok2, msg2 = sd.archive_daily_snapshot(test_date, modified_data, force=False)
            self.assertTrue(ok2)
            self.assertIn('不可变快照已存在', msg2)
            loaded2 = sd.get_daily_snapshot(test_date)
            self.assertEqual(loaded2['score'], 72.5)  # 保持原值不变
        finally:
            sd.SNAPSHOT_DIR = old_snap_dir
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
