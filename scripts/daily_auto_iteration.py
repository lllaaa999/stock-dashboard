#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scripts/daily_auto_iteration.py — 每日盘后全自动数据收集、对账、实证校准与自优化迭代中枢

闭环链路：
  1. 交易日门禁探针：基于交易所真实日K判断是否为交易日，非交易日/休市安全跳过
  2. 权威收盘数据收集：计算情绪指数 v2 (含竞价溢价与晋级率)，门禁安全入库
  3. 周期与战略决策中枢：更新周期状态机，生成战略攻防/持仓对撞决策
  4. 消息面清洗与特征提取：抓取 7x24 快讯、跨源去重、实体识别与时效极性分桶
  5. 打脸账本真实对账：消费今日真实盘面事实，自动核验上一交易日 LLM 推演，写入 ledger
  6. 阈值实证自校准与样本积累：动态重算分位数，跟踪准确率指标，记录校准快照
  7. 次日推演与自优化生成：依据历史对账反馈动态修正提示词权重，输出次日多角色博弈推演
  8. 输出结构化运行报告：写入 data/stock_data/daily_pipeline_report.json
"""
import os
import sys
import json
import time
import datetime as dt
import pathlib
import traceback

_HERE = pathlib.Path(__file__).resolve().parent
ROOT = _HERE.parent
sys.path.insert(0, str(_HERE))

import stock_dashboard as sd
import strategic_decision as sd_engine
import news_events
import sim_score
import sim_llm
import threshold_evidence

DATA_DIR = pathlib.Path(sd.DATA_DIR)
REPORT_PATH = DATA_DIR / 'daily_pipeline_report.json'
CALIBRATION_PATH = DATA_DIR / 'evidence_calibration.json'


def log(msg, level='INFO'):
    now_str = dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{now_str}] [{level}] {msg}", flush=True)


def check_is_trading_day(target_ymd):
    """通过上证指数真实日K判断是否为交易日"""
    try:
        kl = sd.kline_tx('sh000001', 60)
        dates = [str(r[0])[:10].replace('-', '') for r in kl]
        is_traded = target_ymd in dates
        latest_date = dates[-1] if dates else '未知'
        return is_traded, latest_date
    except Exception as e:
        log(f"获取日K失败: {e}", level='WARN')
        return False, 'error'


def step_market_and_emotion(target_ymd, force=False):
    """步骤 1: 情绪指标 v2 收集、门禁归档与周期阶段更新"""
    log("--> [步骤 1/5] 正在收集盘后权威行情并运行情绪指标 v2...")
    res = {}
    emo = None
    try:
        # 执行情绪计算与入库（内部带 _archive_eligible 门禁）
        emo = sd.emotion(target_ymd)
        res['emotion'] = emo
        log(f"情绪分计算完成: 日期={emo.get('date')} 得分={emo.get('score')} 分区={emo.get('band')} 背离={emo.get('diverge')}")
    except Exception as e:
        log(f"情绪指标计算异常: {e}", level='ERROR')
        res['emotion_error'] = str(e)

    try:
        # 更新周期状态机
        stage_name = sd.cycle_position()
        res['cycle_stage'] = stage_name
        log(f"周期状态机已更新: 阶段=【{stage_name}】")
    except Exception as e:
        log(f"周期状态机更新异常: {e}", level='ERROR')
        res['cycle_error'] = str(e)

    try:
        # 运行战略决策引擎并记录 (复用已取到的 emo，避免重复发网络请求)
        sec = sd.sector_flow()
        idxs = sd.tx_realtime(sd.IDX_CODES)
        dec = sd_engine.analyze_strategic_decision(emo=emo, sec=sec, idxs=idxs)
        phase = dec.get('phase', {})
        tactics = dec.get('tactics', {})
        res['decision'] = {
            'phase_key': phase.get('key'),
            'phase_title': phase.get('title'),
            'posture': phase.get('posture'),
            'pos_pct': phase.get('pos_pct'),
            'fire_command': tactics.get('rule_2_fire_command', {}).get('command')
        }
        log(f"战略决策生成完成: 阶段={res['decision']['phase_title']} 仓位建议={res['decision']['pos_pct']}% 开火指令={res['decision']['fire_command']}")
    except Exception as e:
        log(f"战略决策分析异常: {e}", level='ERROR')
        res['decision_error'] = str(e)

    return res


def step_news_events(target_date_str):
    """步骤 2: 7x24 消息面抓取、实体关联与极性特征提取"""
    log(f"--> [步骤 2/5] 正在处理消息面快讯 ({target_date_str})...")
    try:
        events_file = ROOT / 'data' / 'news' / f'events-{target_date_str}.json'
        already_has = events_file.exists()
        # 若已有今日归档，直接载入加速；若没有，联网抓取并生成
        payload = news_events.run(date_str=target_date_str, no_fetch=already_has, quiet=True)
        count = len(payload.get('events', []))
        log(f"消息面处理完成: 归档事件 {count} 条 (来源模式={'已有归档' if already_has else '实时爬取去重'})")
        return {'status': 'ok', 'count': count, 'path': str(events_file)}
    except Exception as e:
        log(f"消息面处理异常: {e}", level='WARN')
        return {'status': 'error', 'error': str(e)}


def step_ledger_audit():
    """步骤 3: 次日打脸账本自动对账 (用今日实际盘面事实核验历史推演)"""
    log("--> [步骤 3/5] 正在运行次日打脸账本对账 (sim_score --all)...")
    try:
        scored = sim_score.run(all_=True, quiet=True)
        stats = sim_score.ledger_stats()
        log(f"对账完成: 本次处理 {len(scored)} 笔，累计有效对账样本={stats.get('samples')} 笔")
        if stats.get('samples'):
            log(f"打脸账本指标: 方向命中率={stats.get('direction_hit_pct')}% 强度命中率={stats.get('strength_hit_pct')}% 板块平均命中={stats.get('sector_avg_hit_pct')}%")
        return {'status': 'ok', 'processed': len(scored), 'stats': stats}
    except Exception as e:
        log(f"打脸账本对账异常: {e}", level='WARN')
        return {'status': 'error', 'error': str(e)}


def step_threshold_calibration():
    """步骤 4: 阈值实证自校准与样本积累 (坚决杜绝假实证)"""
    log("--> [步骤 4/5] 正在进行阈值历史分位数真实实证校准...")
    try:
        sent_path = DATA_DIR / 'sentiment_history.jsonl'
        if not sent_path.exists():
            return {'status': 'skip', 'reason': '无历史数据'}

        raw_lines = [json.loads(l) for l in sent_path.read_text(encoding='utf-8').splitlines() if l.strip()]
        recs_by_date = {}
        for r in raw_lines:
            d = str(r.get('date', ''))
            if d:
                recs_by_date[d] = r
        recs = [recs_by_date[d] for d in sorted(recs_by_date.keys())]
        n_total = len(recs)

        all_scores = [float(r['score']) for r in recs if r.get('score') is not None]
        v2_scores = [float(r['score']) for r in recs if r.get('algo') == 'v2' and r.get('score') is not None]

        zb_rates = []
        for r in recs:
            zt, zb = float(r.get('zt') or 0), float(r.get('zb') or 0)
            if (zt + zb) > 0:
                zb_rates.append(round(zb / (zt + zb) * 100, 1))

        calib = {
            'timestamp': dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'sample_count': n_total,
            'v1_samples': len(recs) - len(v2_scores),
            'v2_samples': len(v2_scores),
            'emotion_percentiles': {
                'p25': round(threshold_evidence.percentile(all_scores, 25), 1),
                'p50': round(threshold_evidence.percentile(all_scores, 50), 1),
                'p75': round(threshold_evidence.percentile(all_scores, 75), 1),
            },
            'zb_rate_percentiles': {
                'p25': round(threshold_evidence.percentile(zb_rates, 25), 1),
                'p50': round(threshold_evidence.percentile(zb_rates, 50), 1),
                'p75': round(threshold_evidence.percentile(zb_rates, 75), 1),
            },
            'calibration_status': 'v2积累阶段' if len(v2_scores) < 30 else 'v2已成熟，可切换独立阈值',
            'honest_rule_reminder': '严禁在v2样本未达30前假造实证结论，当前阈值严格承袭历史经验分位'
        }
        CALIBRATION_PATH.write_text(json.dumps(calib, ensure_ascii=False, indent=2), encoding='utf-8')
        log(f"校准快照已更新: 样本总数={n_total} (v2={len(v2_scores)}) | 情绪P25/P50/P75={calib['emotion_percentiles']} | 炸板P25/P50/P75={calib['zb_rate_percentiles']}")
        return {'status': 'ok', 'calibration': calib}
    except Exception as e:
        log(f"阈值校准异常: {e}", level='WARN')
        return {'status': 'error', 'error': str(e)}


def step_next_day_simulation(target_date_str):
    """步骤 5: 次日博弈推演 (结合跨期衰减与自优化反馈生成)"""
    log(f"--> [步骤 5/5] 正在生成面向次日的多角色博弈推演 ({target_date_str})...")
    try:
        cfg = sim_llm.load_llm_config()
        has_key = cfg.get('has_key', False)
        # 触发推演 (若无 key 会自动安全回退 dry-run / fallback)
        res = sim_llm.run(date_str=target_date_str, rounds=3, top_events=20, dry_run=not has_key, quiet=True)
        if res.get('ok'):
            log(f"推演完成: 模式={'真实LLM' if not res.get('dry_run') else '规则/Dry-run'} 目标次日={res.get('target_date')} 跨期衰减={res.get('time_decay')} 折现合力={res.get('decayed_net')}")
            return {
                'status': 'ok',
                'mode': 'llm' if not res.get('dry_run') else 'dry_run',
                'target_date': res.get('target_date'),
                'time_decay': res.get('time_decay'),
                'decayed_net': res.get('decayed_net')
            }
        else:
            log(f"推演返回未成功: {res.get('error')}", level='WARN')
            return {'status': 'warning', 'reason': res.get('error')}
    except Exception as e:
        log(f"次日推演异常: {e}", level='WARN')
        return {'status': 'error', 'error': str(e)}


def run_daily_pipeline(target_date=None, force=False):
    """
    全自动主控流程
    """
    start_time = time.time()
    now_dt = dt.datetime.now()
    if target_date:
        ymd = target_date.replace('-', '')
        date_str = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"
    else:
        ymd = now_dt.strftime('%Y%m%d')
        date_str = now_dt.strftime('%Y-%m-%d')

    log(f"========================================================================")
    log(f"🚀 启动每日看盘与自我优化自迭代流水线: 目标日期={ymd} ({date_str})")
    log(f"========================================================================")

    # 1. 交易日门禁探针
    is_traded, latest_k = check_is_trading_day(ymd)
    if not is_traded and not force:
        log(f"门禁判定: {ymd} 不在交易所已收盘日K中 (最近交易日: {latest_k}) → 判定为非交易日或休市，安全退出。")
        report = {
            'timestamp': now_dt.strftime('%Y-%m-%d %H:%M:%S'),
            'date': ymd,
            'is_trading_day': False,
            'status': 'skipped_holiday',
            'latest_trading_day': latest_k,
            'duration_sec': round(time.time() - start_time, 2)
        }
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        return report

    log(f"门禁核验通过: {ymd} 为真实有效交易日。开始全流程闭环...")

    pipeline_results = {
        'timestamp': now_dt.strftime('%Y-%m-%d %H:%M:%S'),
        'date': ymd,
        'is_trading_day': True,
        'steps': {}
    }

    # 执行步骤
    pipeline_results['steps']['market_and_emotion'] = step_market_and_emotion(ymd, force=force)
    pipeline_results['steps']['news_events'] = step_news_events(date_str)
    pipeline_results['steps']['ledger_audit'] = step_ledger_audit()
    pipeline_results['steps']['threshold_calibration'] = step_threshold_calibration()
    pipeline_results['steps']['next_day_simulation'] = step_next_day_simulation(date_str)

    duration = round(time.time() - start_time, 2)
    pipeline_results['duration_sec'] = duration
    pipeline_results['status'] = 'success'

    # 落盘每日运行总报告
    REPORT_PATH.write_text(json.dumps(pipeline_results, ensure_ascii=False, indent=2), encoding='utf-8')

    log(f"========================================================================")
    log(f"🎉 每日自迭代流水线全部圆满完成！总耗时: {duration}s")
    log(f"📄 运行报告已写入: {REPORT_PATH}")
    log(f"========================================================================")
    return pipeline_results


if __name__ == '__main__':
    force_run = '--force' in sys.argv
    date_arg = None
    if '--date' in sys.argv:
        idx = sys.argv.index('--date')
        if idx + 1 < len(sys.argv):
            date_arg = sys.argv[idx + 1]
    run_daily_pipeline(target_date=date_arg, force=force_run)
