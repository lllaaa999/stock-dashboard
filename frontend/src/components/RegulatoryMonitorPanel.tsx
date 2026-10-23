import React, { useMemo, useState } from 'react';
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  HelpCircle,
  Scale,
  ShieldAlert,
  X,
} from 'lucide-react';
import type {
  RegulatoryAlertLight,
  RegulatoryDeviationResult,
  RegulatoryMonitorOverview,
} from '../types/market';
import {
  formatPrice,
  formatSignedPercent,
  getSignedColorClass,
} from '../utils/marketCalc';

interface RegulatoryMonitorPanelProps {
  overview: RegulatoryMonitorOverview;
  activeRegDeviation: RegulatoryDeviationResult;
  selectedSymbol: string;
  onSelectSymbol: (symbol: string) => void;
  simulatedIndexPct: number | null;
  defaultIndexPct: number;
  onChangeSimulatedIndexPct: (val: number | null) => void;
}

function getAlertLightStyles(light: RegulatoryAlertLight) {
  switch (light) {
    case 'RED':
      return {
        dotClass: 'bg-[#F6465D] shadow-[0_0_8px_#F6465D]',
        badgeClass: 'bg-[#F6465D]/20 text-[#F6465D] border-[#F6465D]/60',
        cardBorderClass: 'border-[#F6465D]/60 bg-[#F6465D]/10',
        barColor: '#F6465D',
        textColor: 'text-[#F6465D]',
        shortLabel: '红灯高危',
      };
    case 'YELLOW':
      return {
        dotClass: 'bg-[#F59E0B] shadow-[0_0_8px_#F59E0B]',
        badgeClass: 'bg-[#F59E0B]/20 text-[#F59E0B] border-[#F59E0B]/60',
        cardBorderClass: 'border-[#F59E0B]/50 bg-[#F59E0B]/10',
        barColor: '#F59E0B',
        textColor: 'text-[#F59E0B]',
        shortLabel: '黄灯压线',
      };
    case 'GREEN':
      return {
        dotClass: 'bg-[#0ECB81] shadow-[0_0_6px_#0ECB81]',
        badgeClass: 'bg-[#0ECB81]/15 text-[#0ECB81] border-[#0ECB81]/45',
        cardBorderClass: 'border-[#2a2e39] bg-[#1e222d]',
        barColor: '#0ECB81',
        textColor: 'text-[#0ECB81]',
        shortLabel: '绿灯安全',
      };
  }
}

export const RegulatoryMonitorPanel: React.FC<RegulatoryMonitorPanelProps> = ({
  overview,
  activeRegDeviation,
  selectedSymbol,
  onSelectSymbol,
  simulatedIndexPct,
  defaultIndexPct,
  onChangeSimulatedIndexPct,
}) => {
  // 红黄绿信号灯筛选器
  const [lightFilter, setLightFilter] = useState<'ALL' | RegulatoryAlertLight>('ALL');
  // 『监管规则解读』悬浮框开关状态（支持悬浮或点击固定）
  const [isRulePopoverOpen, setIsRulePopoverOpen] = useState(false);
  const [isRulePopoverPinned, setIsRulePopoverPinned] = useState(false);

  const filteredItems = useMemo(() => {
    if (lightFilter === 'ALL') return overview.items;
    return overview.items.filter((item) => item.alertLight === lightFilter);
  }, [overview.items, lightFilter]);

  const warningStocks = useMemo(
    () => overview.items.filter((item) => item.alertLight !== 'GREEN'),
    [overview.items]
  );

  const activeLightMeta = getAlertLightStyles(activeRegDeviation.alertLight);
  const currentIndexValue = simulatedIndexPct ?? defaultIndexPct;

  return (
    <section
      aria-label="监管异动监测"
      data-testid="regulatory-monitor-panel"
      className="relative bg-[#1e222d] border border-[#2a2e39] rounded-md overflow-visible"
    >
      {/* 顶部标题栏 + 『监管规则解读』悬浮框触发器 + 基准指数推演控制器 */}
      <div className="relative flex flex-wrap items-center justify-between gap-2 px-3 py-2 bg-[#131722] border-b border-[#2a2e39] rounded-t-md">
        <div className="flex flex-wrap items-center gap-2">
          <Scale className="w-4 h-4 text-[#F59E0B]" />
          <h2 className="text-xs sm:text-sm font-bold text-white">
            监管异动监测 (2/3日涨跌幅实时监控 · k ∈ &#123;2, 3&#125; 法定异动窗口 · 特停红黄灯预警)
          </h2>

          {/* 『监管规则解读』悬浮框触发器与浮层容器 */}
          <div
            className="inline-block"
            onMouseEnter={() => setIsRulePopoverOpen(true)}
            onMouseLeave={() => {
              if (!isRulePopoverPinned) {
                setIsRulePopoverOpen(false);
              }
            }}
          >
            <button
              type="button"
              data-testid="regulatory-rules-popover-trigger"
              onClick={() => {
                const nextPinned = !isRulePopoverPinned;
                setIsRulePopoverPinned(nextPinned);
                setIsRulePopoverOpen(nextPinned);
              }}
              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold border transition-colors cursor-pointer ${
                isRulePopoverOpen
                  ? 'bg-[#2962ff] text-white border-[#2962ff]'
                  : 'bg-[#1e222d] text-[#38bdf8] border-[#38bdf8]/40 hover:bg-[#2962ff]/20'
              }`}
            >
              <BookOpen className="w-3.5 h-3.5" />
              <span>监管规则解读</span>
              <HelpCircle className="w-3 h-3 opacity-80" />
            </button>

            {/* 『监管规则解读』悬浮框主体 */}
            {isRulePopoverOpen && (
              <div
                role="dialog"
                aria-label="现行注册制监管异动与特停规则解读"
                data-testid="regulatory-rules-popover"
                className="absolute left-3 top-full mt-1 w-[340px] sm:w-[460px] z-50 rounded-md bg-[#0d0e12] border border-[#38bdf8]/60 shadow-[0_16px_40px_rgba(0,0,0,0.85)] p-3.5 text-xs text-[#d1d4dc] space-y-2.5"
              >
                <div className="flex items-center justify-between border-b border-[#2a2e39] pb-2">
                  <div className="flex items-center gap-1.5 font-bold text-white text-xs sm:text-sm">
                    <Scale className="w-4 h-4 text-[#F59E0B]" />
                    <span>沪深交易所现行注册制异常波动与特停核查规则解读</span>
                  </div>
                  <button
                    type="button"
                    data-testid="close-regulatory-rules-popover"
                    onClick={(e) => {
                      e.stopPropagation();
                      setIsRulePopoverPinned(false);
                      setIsRulePopoverOpen(false);
                    }}
                    className="p-0.5 rounded text-[#9ca3af] hover:text-white hover:bg-[#1e222d] cursor-pointer"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>

                {/* 规则一：2/3日普通异动复利公式 */}
                <div className="p-2.5 rounded bg-[#131722] border border-[#2a2e39] space-y-1">
                  <div className="font-bold text-[#38bdf8] flex items-center justify-between">
                    <span>一、2/3个交易日异常波动法定窗口 (k ∈ &#123;2, 3&#125;)</span>
                    <span className="font-mono tabular-nums text-[10px] text-[#F59E0B]">
                      触发披露龙虎榜
                    </span>
                  </div>
                  <p className="text-[11px] text-[#9ca3af] leading-relaxed">
                    连续 <strong className="text-white">2个</strong> 或{' '}
                    <strong className="text-white">3个</strong>{' '}
                    交易日内日收盘价格涨跌幅偏离值累计达到阈值即触发异常波动：
                    <strong className="text-[#F6465D]"> 沪深主板 ±20%</strong>，
                    <strong className="text-[#38bdf8]"> 创业板 / 科创板 ±30%</strong>。
                  </p>
                  <div className="p-1.5 rounded bg-[#1e222d] font-mono tabular-nums text-[11px] text-[#F59E0B]">
                    复利偏离公式：Dev(k) = [∏(1 + r_个股,i) - 1] - [∏(1 + r_指数,i) - 1]
                  </div>
                  <p className="text-[11px] text-[#9ca3af]">
                    系统自动同时逆推 <span className="font-mono text-white">k=2</span> 与{' '}
                    <span className="font-mono text-white">k=3</span> 的临界价格，取更低者{' '}
                    <span className="font-mono text-[#F59E0B]">
                      min(P_trigger,2, P_trigger,3)
                    </span>{' '}
                    作为今日主约束压线价。
                  </p>
                </div>

                {/* 规则二：严重异常波动与特停核查红线 */}
                <div className="p-2.5 rounded bg-[#131722] border border-[#F6465D]/40 space-y-1">
                  <div className="font-bold text-[#F6465D] flex items-center justify-between">
                    <span>二、严重异常波动与停牌核查（特停）三大法定红线</span>
                    <span className="font-mono tabular-nums text-[10px] px-1.5 py-0.2 rounded bg-[#F6465D]/20 text-[#F6465D]">
                      重点监控 / 特停风险
                    </span>
                  </div>
                  <ul className="space-y-1 text-[11px] text-[#d1d4dc] list-disc list-inside">
                    <li>
                      <strong className="text-white">10日4次同向异动：</strong>
                      连续 10 个交易日内 4 次出现同向 ±20%（或±30%）异常波动；
                    </li>
                    <li>
                      <strong className="text-white">10日 100% 累计偏离：</strong>
                      连续 10 个交易日内日收盘价涨跌幅偏离值累计达到{' '}
                      <strong className="text-[#F6465D]">+100%</strong>（或 -50%）；
                    </li>
                    <li>
                      <strong className="text-white">30日 200% 累计偏离：</strong>
                      连续 30 个交易日内日收盘价涨跌幅偏离值累计达到{' '}
                      <strong className="text-[#F6465D]">+200%</strong>（或 -70%）。
                    </li>
                  </ul>
                </div>

                {/* 规则三：红黄绿灯信号体系与游资压线操盘口诀 */}
                <div className="p-2.5 rounded bg-[#131722] border border-[#2a2e39] space-y-1">
                  <div className="font-bold text-[#0ECB81]">
                    三、红黄绿灯预警分级与游资绕异动实操口诀
                  </div>
                  <div className="grid grid-cols-1 gap-1 text-[11px]">
                    <div className="flex items-start gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-[#F6465D] mt-1 shrink-0" />
                      <span>
                        <strong className="text-[#F6465D]">红灯高危：</strong>
                        10日偏离 ≥86% 或近10日已3次异动（再触发即满4次严重异动），或今日已突破k∈&#123;2,3&#125;异动线；谨防尾盘漏单断板控涨幅。
                      </span>
                    </div>
                    <div className="flex items-start gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-[#F59E0B] mt-1 shrink-0" />
                      <span>
                        <strong className="text-[#F59E0B]">黄灯压线：</strong>
                        距今日异动临界涨幅余量 ≤4.5% 或窗口占用率 ≥75%；主力常采用“压线收盘不封板”精准绕开异动监管。
                      </span>
                    </div>
                    <div className="flex items-start gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-[#0ECB81] mt-1 shrink-0" />
                      <span>
                        <strong className="text-[#0ECB81]">绿灯安全：</strong>
                        2/3日偏离与10日累计偏离空间充裕，无近期监管压线顾虑。
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* 右侧：交互式基准指数今日涨跌幅推演控制器 */}
        <div className="flex items-center gap-2 text-xs">
          <span className="text-[#9ca3af] whitespace-nowrap">
            基准指数今日涨幅推演:
          </span>
          <input
            type="range"
            data-testid="regulatory-index-slider"
            aria-label="基准指数今日涨跌幅推演滑块"
            min={-3.0}
            max={5.0}
            step={0.1}
            value={currentIndexValue}
            onChange={(e) => onChangeSimulatedIndexPct(Number(e.target.value))}
            className="w-24 accent-[#2962ff] cursor-pointer"
          />
          <span
            data-testid="regulatory-index-display"
            className="font-mono tabular-nums font-bold text-[#38bdf8] w-14 text-right"
          >
            {formatSignedPercent(currentIndexValue)}
          </span>
          {simulatedIndexPct !== null && (
            <button
              type="button"
              data-testid="regulatory-index-reset"
              onClick={() => onChangeSimulatedIndexPct(null)}
              className="px-1.5 py-0.5 rounded bg-[#1e222d] border border-[#2a2e39] text-[10px] text-[#9ca3af] hover:text-white cursor-pointer"
            >
              重置实盘
            </button>
          )}
        </div>
      </div>

      {/* 一、全市场红黄绿三色交通信号灯统计与接近特停风险快筛条 */}
      <div
        data-testid="regulatory-traffic-light-banner"
        className="p-3 bg-[#131722] border-b border-[#2a2e39] space-y-2.5"
      >
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
          {/* 全部标的 */}
          <button
            type="button"
            data-testid="reg-filter-ALL"
            onClick={() => setLightFilter('ALL')}
            className={`p-2 rounded border text-left transition-colors cursor-pointer ${
              lightFilter === 'ALL'
                ? 'bg-[#2962ff]/15 border-[#2962ff]'
                : 'bg-[#1e222d] border-[#2a2e39] hover:bg-[#262b38]'
            }`}
          >
            <div className="flex items-center justify-between text-[11px] text-[#9ca3af]">
              <span>全市场监控池</span>
              <span className="font-mono tabular-nums text-[10px] text-[#38bdf8]">
                k∈&#123;2,3&#125; 实时
              </span>
            </div>
            <div className="mt-1 flex items-baseline justify-between gap-1 font-mono tabular-nums">
              <span className="text-base font-bold text-white whitespace-nowrap">
                {overview.items.length} 家
              </span>
              <span className="text-[10px] text-[#787b86] whitespace-nowrap">
                今日触线 {overview.triggeredTodayCount} 家
              </span>
            </div>
          </button>

          {/* 红灯预警 */}
          <button
            type="button"
            data-testid="reg-filter-RED"
            onClick={() => setLightFilter('RED')}
            className={`p-2 rounded border text-left transition-colors cursor-pointer ${
              lightFilter === 'RED'
                ? 'bg-[#F6465D]/20 border-[#F6465D]'
                : 'bg-[#1e222d] border-[#F6465D]/40 hover:bg-[#F6465D]/15'
            }`}
          >
            <div className="flex items-center justify-between text-[11px]">
              <span className="inline-flex items-center gap-1.5 font-semibold text-[#F6465D]">
                <span className="w-2.5 h-2.5 rounded-full bg-[#F6465D] shadow-[0_0_8px_#F6465D] animate-pulse" />
                红灯 · 特停/触线高危
              </span>
            </div>
            <div className="mt-1 flex items-baseline justify-between gap-1 font-mono tabular-nums">
              <span
                data-testid="reg-red-light-count"
                className="text-base font-bold text-[#F6465D] whitespace-nowrap"
              >
                {overview.redLightCount} 家
              </span>
              <span className="text-[10px] text-[#9ca3af] whitespace-nowrap">
                严重异动高危 {overview.suspensionWarningCount} 家
              </span>
            </div>
          </button>

          {/* 黄灯预警 */}
          <button
            type="button"
            data-testid="reg-filter-YELLOW"
            onClick={() => setLightFilter('YELLOW')}
            className={`p-2 rounded border text-left transition-colors cursor-pointer ${
              lightFilter === 'YELLOW'
                ? 'bg-[#F59E0B]/20 border-[#F59E0B]'
                : 'bg-[#1e222d] border-[#F59E0B]/40 hover:bg-[#F59E0B]/15'
            }`}
          >
            <div className="flex items-center justify-between text-[11px]">
              <span className="inline-flex items-center gap-1.5 font-semibold text-[#F59E0B]">
                <span className="w-2.5 h-2.5 rounded-full bg-[#F59E0B] shadow-[0_0_8px_#F59E0B]" />
                黄灯 · 异动压线临界
              </span>
            </div>
            <div className="mt-1 flex items-baseline justify-between gap-1 font-mono tabular-nums">
              <span
                data-testid="reg-yellow-light-count"
                className="text-base font-bold text-[#F59E0B] whitespace-nowrap"
              >
                {overview.yellowLightCount} 家
              </span>
              <span className="text-[10px] text-[#9ca3af] whitespace-nowrap">
                压线临界 (余量≤4.5%)
              </span>
            </div>
          </button>

          {/* 绿灯安全 */}
          <button
            type="button"
            data-testid="reg-filter-GREEN"
            onClick={() => setLightFilter('GREEN')}
            className={`p-2 rounded border text-left transition-colors cursor-pointer ${
              lightFilter === 'GREEN'
                ? 'bg-[#0ECB81]/20 border-[#0ECB81]'
                : 'bg-[#1e222d] border-[#2a2e39] hover:bg-[#262b38]'
            }`}
          >
            <div className="flex items-center justify-between text-[11px]">
              <span className="inline-flex items-center gap-1.5 font-semibold text-[#0ECB81]">
                <span className="w-2.5 h-2.5 rounded-full bg-[#0ECB81] shadow-[0_0_6px_#0ECB81]" />
                绿灯 · 安全运行区间
              </span>
            </div>
            <div className="mt-1 flex items-baseline justify-between gap-1 font-mono tabular-nums">
              <span
                data-testid="reg-green-light-count"
                className="text-base font-bold text-[#0ECB81] whitespace-nowrap"
              >
                {overview.greenLightCount} 家
              </span>
              <span className="text-[10px] text-[#9ca3af] whitespace-nowrap">偏离额度充裕</span>
            </div>
          </button>
        </div>

        {/* 接近特停风险与红黄灯标的快捷雷达条 */}
        {warningStocks.length > 0 && (
          <div
            data-testid="suspension-risk-quick-strip"
            className="flex flex-wrap items-center gap-1.5 pt-1 text-xs"
          >
            <span className="text-[11px] font-semibold text-[#F59E0B] flex items-center gap-1 shrink-0">
              <AlertTriangle className="w-3.5 h-3.5 text-[#F6465D]" />
              红黄灯重点盯防标的：
            </span>
            {warningStocks.map((st) => {
              const stMeta = getAlertLightStyles(st.alertLight);
              const isSelected = st.symbol === selectedSymbol;
              return (
                <button
                  key={st.symbol}
                  type="button"
                  data-testid={`reg-quick-stock-${st.symbol}`}
                  onClick={() => onSelectSymbol(st.symbol)}
                  className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded border text-[11px] transition-colors cursor-pointer ${
                    isSelected
                      ? 'bg-[#2962ff] text-white border-[#2962ff]'
                      : `${stMeta.badgeClass} hover:brightness-110`
                  }`}
                >
                  <span className={`w-2 h-2 rounded-full ${stMeta.dotClass}`} />
                  <span className="font-bold">{st.name}</span>
                  <span className="font-mono tabular-nums text-[10px]">
                    {st.severeSuspensionLockWarning
                      ? `10日${st.cumDeviation10dPercent}%·${st.abnormalCount10d}次异动`
                      : `k=${st.bindingWindowK}偏离${
                          st.bindingWindowK === 2
                            ? st.dev2DayCurrentPercent
                            : st.dev3DayCurrentPercent
                        }%`}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* 二、当前选中个股：2/3日涨跌幅实时监控与法定异动窗口逆推仪表盘 */}
      <div
        data-testid="active-stock-regulatory-dashboard"
        className="p-3 bg-[#161a24] border-b border-[#2a2e39] space-y-2.5"
      >
        {/* 顶部：当前标的信息 + 红黄绿信号灯状态牌 */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-bold text-white">
              当前监测标的：{activeRegDeviation.name} ({activeRegDeviation.symbol})
            </span>
            <span className="px-2 py-0.5 rounded bg-[#2962ff]/20 border border-[#2962ff]/40 text-[11px] font-mono tabular-nums text-[#38bdf8]">
              法定阈值 ±{activeRegDeviation.ruleThresholdPercent}% (
              {activeRegDeviation.boardRuleLabel})
            </span>
            <span
              data-testid="active-stock-alert-light"
              className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded border text-xs font-bold ${activeLightMeta.badgeClass}`}
            >
              <span className={`w-2.5 h-2.5 rounded-full ${activeLightMeta.dotClass}`} />
              {activeRegDeviation.alertLightLabel}
            </span>
          </div>

          <div className="text-xs font-mono tabular-nums text-[#9ca3af]">
            特停风险评分:{' '}
            <strong className={activeLightMeta.textColor}>
              {activeRegDeviation.suspensionRiskScore} / 100
            </strong>
          </div>
        </div>

        {/* 四维核心监控卡片：2/3日涨跌幅明细 | k=2窗口 | k=3窗口 | 压线安全价与10日特停红线 */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 text-xs">
          {/* 1. 个股 2/3 个交易日涨跌幅实时监控 */}
          <div className="p-2.5 rounded bg-[#1e222d] border border-[#2a2e39] space-y-1.5">
            <div className="flex items-center justify-between text-[11px] text-[#787b86] whitespace-nowrap">
              <span>2/3个交易日涨跌幅实时监控</span>
              <span className="font-mono tabular-nums text-[#38bdf8]">复利累计</span>
            </div>

            <div className="grid grid-cols-3 gap-1 pt-0.5 text-center font-mono tabular-nums">
              <div className="p-1 rounded bg-[#131722] border border-[#2a2e39]/70">
                <div className="text-[10px] text-[#787b86]">T-2 涨幅</div>
                <div
                  className={`text-xs font-bold ${getSignedColorClass(
                    activeRegDeviation.stockReturnT2Percent
                  )}`}
                >
                  {formatSignedPercent(activeRegDeviation.stockReturnT2Percent)}
                </div>
              </div>
              <div className="p-1 rounded bg-[#131722] border border-[#2a2e39]/70">
                <div className="text-[10px] text-[#787b86]">T-1 涨幅</div>
                <div
                  className={`text-xs font-bold ${getSignedColorClass(
                    activeRegDeviation.stockReturnT1Percent
                  )}`}
                >
                  {formatSignedPercent(activeRegDeviation.stockReturnT1Percent)}
                </div>
              </div>
              <div className="p-1 rounded bg-[#131722] border border-[#2a2e39]/70">
                <div className="text-[10px] text-[#787b86]">今日实时</div>
                <div
                  className={`text-xs font-bold ${getSignedColorClass(
                    activeRegDeviation.currentChangePercent
                  )}`}
                >
                  {formatSignedPercent(activeRegDeviation.currentChangePercent)}
                </div>
              </div>
            </div>

            <div className="pt-1 border-t border-[#2a2e39]/70 flex items-center justify-between font-mono tabular-nums text-[11px] whitespace-nowrap">
              <span className="text-[#9ca3af]">
                2日累涨:{' '}
                <strong
                  data-testid="active-stock-cum2d-return"
                  className={getSignedColorClass(
                    activeRegDeviation.stockCumReturn2DayPercent
                  )}
                >
                  {formatSignedPercent(activeRegDeviation.stockCumReturn2DayPercent)}
                </strong>
              </span>
              <span className="text-[#9ca3af]">
                3日累涨:{' '}
                <strong
                  data-testid="active-stock-cum3d-return"
                  className={getSignedColorClass(
                    activeRegDeviation.stockCumReturn3DayPercent
                  )}
                >
                  {formatSignedPercent(activeRegDeviation.stockCumReturn3DayPercent)}
                </strong>
              </span>
            </div>
          </div>

          {/* 2. k = 2 (连续2个交易日) 法定异动窗口 */}
          <div
            className={`p-2.5 rounded border space-y-1.5 ${
              activeRegDeviation.bindingWindowK === 2
                ? 'bg-[#1e222d] border-[#F59E0B]/60'
                : 'bg-[#1e222d] border-[#2a2e39]'
            }`}
          >
            <div className="flex items-center justify-between text-[11px] text-[#787b86] whitespace-nowrap">
              <span>k = 2 (2日法定异动窗口)</span>
              {activeRegDeviation.bindingWindowK === 2 ? (
                <span className="px-1.5 py-0.2 rounded bg-[#F59E0B]/20 text-[#F59E0B] font-semibold text-[10px]">
                  [主约束窗口]
                </span>
              ) : (
                <span className="text-[10px] text-[#787b86]">次约束</span>
              )}
            </div>

            <div className="flex items-baseline justify-between font-mono tabular-nums whitespace-nowrap">
              <span className="text-[#9ca3af]">当前2日偏离值:</span>
              <span className="text-sm font-bold text-white">
                {formatSignedPercent(activeRegDeviation.dev2DayCurrentPercent)}{' '}
                <span className="text-[10px] text-[#787b86]">
                  / ±{activeRegDeviation.ruleThresholdPercent}%
                </span>
              </span>
            </div>

            {/* 2日窗口额度占用进度条 */}
            <div className="w-full h-1.5 bg-[#131722] rounded overflow-hidden">
              <div
                className="h-full rounded transition-all"
                style={{
                  width: `${Math.min(100, activeRegDeviation.windowSaturation2DayPercent)}%`,
                  backgroundColor:
                    activeRegDeviation.windowSaturation2DayPercent >= 95
                      ? '#F6465D'
                      : activeRegDeviation.windowSaturation2DayPercent >= 75
                      ? '#F59E0B'
                      : '#38bdf8',
                }}
              />
            </div>

            <div className="flex items-baseline justify-between font-mono tabular-nums text-[11px] whitespace-nowrap">
              <span className="text-[#9ca3af]">k=2 触线临界价:</span>
              <span className="font-bold text-[#F6465D]">
                {formatPrice(activeRegDeviation.triggerPrice2Day)}元 (
                {formatSignedPercent(activeRegDeviation.maxSafeChange2DayPercent)})
              </span>
            </div>
          </div>

          {/* 3. k = 3 (连续3个交易日) 法定异动窗口 */}
          <div
            className={`p-2.5 rounded border space-y-1.5 ${
              activeRegDeviation.bindingWindowK === 3
                ? 'bg-[#1e222d] border-[#F59E0B]/60'
                : 'bg-[#1e222d] border-[#2a2e39]'
            }`}
          >
            <div className="flex items-center justify-between text-[11px] text-[#787b86] whitespace-nowrap">
              <span>k = 3 (3日法定异动窗口)</span>
              {activeRegDeviation.bindingWindowK === 3 ? (
                <span className="px-1.5 py-0.2 rounded bg-[#F59E0B]/20 text-[#F59E0B] font-semibold text-[10px]">
                  [主约束窗口]
                </span>
              ) : (
                <span className="text-[10px] text-[#787b86]">次约束</span>
              )}
            </div>

            <div className="flex items-baseline justify-between font-mono tabular-nums whitespace-nowrap">
              <span className="text-[#9ca3af]">当前3日偏离值:</span>
              <span className="text-sm font-bold text-white">
                {formatSignedPercent(activeRegDeviation.dev3DayCurrentPercent)}{' '}
                <span className="text-[10px] text-[#787b86]">
                  / ±{activeRegDeviation.ruleThresholdPercent}%
                </span>
              </span>
            </div>

            {/* 3日窗口额度占用进度条 */}
            <div className="w-full h-1.5 bg-[#131722] rounded overflow-hidden">
              <div
                className="h-full rounded transition-all"
                style={{
                  width: `${Math.min(100, activeRegDeviation.windowSaturation3DayPercent)}%`,
                  backgroundColor:
                    activeRegDeviation.windowSaturation3DayPercent >= 95
                      ? '#F6465D'
                      : activeRegDeviation.windowSaturation3DayPercent >= 75
                      ? '#F59E0B'
                      : '#38bdf8',
                }}
              />
            </div>

            <div className="flex items-baseline justify-between font-mono tabular-nums text-[11px] whitespace-nowrap">
              <span className="text-[#9ca3af]">k=3 触线临界价:</span>
              <span className="font-bold text-[#F6465D]">
                {formatPrice(activeRegDeviation.triggerPrice3Day)}元 (
                {formatSignedPercent(activeRegDeviation.maxSafeChange3DayPercent)})
              </span>
            </div>
          </div>

          {/* 4. 综合压线上限与 10日100%/4次异动特停锁死监控 */}
          <div className={`p-2.5 rounded border space-y-1.5 ${activeLightMeta.cardBorderClass}`}>
            <div className="flex items-center justify-between text-[11px] whitespace-nowrap">
              <span className="text-[#F59E0B] font-semibold">
                压线安全价 &amp; 10日特停红线
              </span>
              <ShieldAlert className={`w-3.5 h-3.5 ${activeLightMeta.textColor}`} />
            </div>

            <div className="flex items-baseline justify-between font-mono tabular-nums whitespace-nowrap">
              <span className="text-[#9ca3af]">今日压线安全上限:</span>
              <span className="text-sm font-bold text-[#F59E0B]">
                {formatPrice(activeRegDeviation.effectiveTriggerPrice)}元 (
                {formatSignedPercent(activeRegDeviation.effectiveMaxSafeChangePercent)})
              </span>
            </div>

            <div className="flex items-baseline justify-between font-mono tabular-nums text-[11px] whitespace-nowrap">
              <span className="text-[#9ca3af]">10日偏离 (100%特停线):</span>
              <span className="font-bold text-[#F6465D]">
                +{activeRegDeviation.cumDeviation10dPercent.toFixed(2)}% (余
                {activeRegDeviation.remainingTo100Percent.toFixed(1)}%)
              </span>
            </div>

            <div className="flex items-baseline justify-between font-mono tabular-nums text-[11px] whitespace-nowrap">
              <span className="text-[#9ca3af]">近10日已触发异动:</span>
              <span className="font-bold text-white">
                {activeRegDeviation.abnormalCount10d} / 4 次{' '}
                <span className="text-[10px] text-[#9ca3af]">
                  (满4次触发严重异动)
                </span>
              </span>
            </div>
          </div>
        </div>

        {/* 底部：红黄灯定性原因与游资压线绕异动操盘策略 */}
        <div className="p-2.5 rounded bg-[#131722] border border-[#2a2e39] flex flex-col lg:flex-row lg:items-center justify-between gap-2 text-xs">
          <div className="space-y-0.5">
            <div className="text-[#d1d4dc]">
              <strong className={activeLightMeta.textColor}>
                [{activeRegDeviation.alertLightLabel}] 监测诊断：
              </strong>
              {activeRegDeviation.alertLightReason}
            </div>
            <div className="text-[#9ca3af]">
              <strong className="text-[#38bdf8]">游资压线博弈策略：</strong>
              {activeRegDeviation.tacticalPlaybook}
            </div>
          </div>
        </div>
      </div>

      {/* 三、全市场个股 2/3 日涨跌幅与红黄灯异动监测表 */}
      <div data-testid="regulatory-monitor-table" className="overflow-x-auto">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="border-b border-[#2a2e39] text-[#787b86] bg-[#161a24] text-[11px]">
              <th className="py-2 px-2.5 whitespace-nowrap">红黄灯预警</th>
              <th className="py-2 px-2.5 whitespace-nowrap">股票标的</th>
              <th className="py-2 px-2 text-right whitespace-nowrap">现价 / 今日涨幅</th>
              <th className="py-2 px-2 text-right whitespace-nowrap">
                T-2 / T-1 涨幅
              </th>
              <th className="py-2 px-2 text-right whitespace-nowrap">
                2日累涨 / k=2偏离
              </th>
              <th className="py-2 px-2 text-right whitespace-nowrap">
                3日累涨 / k=3偏离
              </th>
              <th className="py-2 px-2 text-right whitespace-nowrap">
                主约束 &amp; 今日压线安全价
              </th>
              <th className="py-2 px-2.5 text-right whitespace-nowrap">
                10日偏离 / 异动次数 (特停风险)
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#2a2e39]/60">
            {filteredItems.map((row) => {
              const lightMeta = getAlertLightStyles(row.alertLight);
              const isSelected = row.symbol === selectedSymbol;

              return (
                <tr
                  key={row.symbol}
                  onClick={() => onSelectSymbol(row.symbol)}
                  className={`cursor-pointer transition-colors ${
                    isSelected ? 'bg-[#2962ff]/15' : 'hover:bg-[#262b38]'
                  }`}
                >
                  {/* 1. 红黄绿信号灯 */}
                  <td className="py-2 px-2.5 whitespace-nowrap">
                    <span
                      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded border text-[11px] font-bold ${lightMeta.badgeClass}`}
                    >
                      <span className={`w-2 h-2 rounded-full ${lightMeta.dotClass}`} />
                      {lightMeta.shortLabel}
                    </span>
                  </td>

                  {/* 2. 股票标的与板块阈值 */}
                  <td className="py-2 px-2.5 whitespace-nowrap">
                    <div className="flex items-center gap-1.5">
                      <span className="font-semibold text-white">{row.name}</span>
                      <span className="font-mono tabular-nums text-[10px] text-[#787b86]">
                        {row.code}
                      </span>
                      <span className="px-1 py-0.2 rounded bg-[#131722] border border-[#2a2e39] font-mono tabular-nums text-[10px] text-[#9ca3af]">
                        ±{row.ruleThresholdPercent}%
                      </span>
                    </div>
                  </td>

                  {/* 3. 现价 / 今日涨幅 */}
                  <td
                    className={`py-2 px-2 text-right font-mono tabular-nums font-semibold whitespace-nowrap ${getSignedColorClass(
                      row.currentChangePercent
                    )}`}
                  >
                    {formatPrice(row.currentPrice)} (
                    {formatSignedPercent(row.currentChangePercent)})
                  </td>

                  {/* 4. T-2 / T-1 历史涨幅 */}
                  <td className="py-2 px-2 text-right font-mono tabular-nums whitespace-nowrap">
                    <span className={getSignedColorClass(row.stockReturnT2Percent)}>
                      {formatSignedPercent(row.stockReturnT2Percent)}
                    </span>
                    <span className="text-[#787b86] mx-1">/</span>
                    <span className={getSignedColorClass(row.stockReturnT1Percent)}>
                      {formatSignedPercent(row.stockReturnT1Percent)}
                    </span>
                  </td>

                  {/* 5. 2日累涨 / k=2偏离 */}
                  <td className="py-2 px-2 text-right font-mono tabular-nums whitespace-nowrap">
                    <span
                      className={`font-semibold ${getSignedColorClass(
                        row.stockCumReturn2DayPercent
                      )}`}
                    >
                      {formatSignedPercent(row.stockCumReturn2DayPercent)}
                    </span>
                    <span className="text-[#787b86] mx-1">/</span>
                    <span className="text-white">
                      偏{formatSignedPercent(row.dev2DayCurrentPercent)}
                    </span>
                  </td>

                  {/* 6. 3日累涨 / k=3偏离 */}
                  <td className="py-2 px-2 text-right font-mono tabular-nums whitespace-nowrap">
                    <span
                      className={`font-semibold ${getSignedColorClass(
                        row.stockCumReturn3DayPercent
                      )}`}
                    >
                      {formatSignedPercent(row.stockCumReturn3DayPercent)}
                    </span>
                    <span className="text-[#787b86] mx-1">/</span>
                    <span className="text-white">
                      偏{formatSignedPercent(row.dev3DayCurrentPercent)}
                    </span>
                  </td>

                  {/* 7. 主约束 & 今日压线安全价 */}
                  <td className="py-2 px-2 text-right font-mono tabular-nums whitespace-nowrap">
                    <span className="px-1 py-0.2 rounded bg-[#131722] text-[#38bdf8] text-[10px] mr-1">
                      k={row.bindingWindowK}
                    </span>
                    <span className="font-bold text-[#F59E0B]">
                      {formatPrice(row.effectiveTriggerPrice)}元 (
                      {formatSignedPercent(row.effectiveMaxSafeChangePercent)})
                    </span>
                  </td>

                  {/* 8. 10日偏离 / 异动次数 (特停风险) */}
                  <td className="py-2 px-2.5 text-right font-mono tabular-nums whitespace-nowrap">
                    <span
                      className={`font-bold ${
                        row.severeSuspensionLockWarning
                          ? 'text-[#F6465D]'
                          : 'text-[#d1d4dc]'
                      }`}
                    >
                      +{row.cumDeviation10dPercent.toFixed(1)}%
                    </span>
                    <span className="ml-1.5 text-[10px] text-[#9ca3af]">
                      ({row.abnormalCount10d}/4次)
                    </span>
                    {row.severeSuspensionLockWarning ? (
                      <span className="ml-1.5 px-1.5 py-0.5 rounded bg-[#F6465D]/20 text-[#F6465D] border border-[#F6465D]/40 text-[10px] font-semibold">
                        特停高危
                      </span>
                    ) : row.isTriggeredToday ? (
                      <span className="ml-1.5 px-1.5 py-0.5 rounded bg-[#F59E0B]/20 text-[#F59E0B] text-[10px] font-semibold">
                        今日触线
                      </span>
                    ) : (
                      <span className="ml-1.5 inline-flex items-center text-[10px] text-[#0ECB81]">
                        <CheckCircle2 className="w-3 h-3 mr-0.5" />
                        余{row.remainingTo100Percent.toFixed(0)}%
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
};
