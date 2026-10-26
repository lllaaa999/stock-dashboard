# -*- coding: utf-8 -*-
"""情绪存档写入幂等性回归测试。

背景：20261022 在 sentiment_history.jsonl 里出现了两条记录（一条 stage_meta=adjacent/conf2、
一条 stay/conf3），原因是旧的「先判断日期、再 open('a') 追加」在两个进程并发时会各写一行。
重复行会让 MA3/MA7 把同一天算两遍、cycle_position 样本数虚高。
本测试锁定 _hist_upsert 的三个契约：①同日期覆盖不追加 ②保持日期有序 ③不丢其他日期。
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(_PROJECT_ROOT), str(_PROJECT_ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import stock_dashboard as sd


def _read(fp):
    with open(fp, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


class TestHistoryUpsert(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fp = os.path.join(self.tmp.name, "sentiment_history.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_same_date_is_overwritten_not_appended(self):
        sd._hist_upsert(self.fp, dict(date="20261022", score=27.89, stage="冰点"))
        sd._hist_upsert(self.fp, dict(date="20261022", score=27.89, stage="冰点",
                                      stage_meta={"trans": "stay", "conf": 3}))
        rows = _read(self.fp)
        self.assertEqual(len(rows), 1, "同日期必须覆盖，不能出现两行")
        self.assertEqual(rows[0]["stage_meta"]["conf"], 3, "后写入的版本应生效")

    def test_keeps_other_dates_and_sorted(self):
        sd._hist_upsert(self.fp, dict(date="20261023", score=65.02))
        sd._hist_upsert(self.fp, dict(date="20261016", score=48.99))
        sd._hist_upsert(self.fp, dict(date="20261022", score=27.89))
        dates = [r["date"] for r in _read(self.fp)]
        self.assertEqual(dates, ["20261016", "20261022", "20261023"], "写入后必须按日期有序")
        self.assertEqual(len(dates), 3)

    def test_no_tmp_file_left_behind(self):
        sd._hist_upsert(self.fp, dict(date="20261022", score=27.89))
        self.assertFalse(os.path.exists(self.fp + ".tmp"), "原子重写不应残留 .tmp")


if __name__ == "__main__":
    unittest.main()
