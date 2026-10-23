import React, { useMemo, useState } from 'react';
import {
  Activity,
  ChevronDown,
  ChevronUp,
  Flame,
  Radar,
  RotateCcw,
  Scale,
  SlidersHorizontal,
  Zap,
} from 'lucide-react';
import { generateIntradayForSymbol } from '../data/seedMarket';
import { useMarketStore } from '../store/useMarketStore';
import type { AuctionSignalType } from '../types/market';
import {
  formatAmountCN,
  formatPrice,
  formatSignedPercent,
  getSignedColorClass,
} from '../utils/marketCalc';
import {
  analyzeAuctionVolumeRatio,
  calculateAuctionRadar,
  calculateBoardLadderSummary,
  calculateRegulatoryDeviation,
  calculateVWDVR,
  type AuctionRadarOverride,
} from '../utils/ultraShortQuant';

function getSignalStyle(signal: AuctionSignalType): {
  badge: string;
  border: string;
  accentText: string;
} {
  switch (signal) {
    case 'LOCKED_LIMIT_UP':
      return {
        badge: 'bg-[#F6465D] text-white border-[#F6465D]',
        border: 'border-[#F6465D]/50',
        accentText: 'text-[#F6465D]',
      };
    case 'SUPER_GRAB':
      return {
        badge: 'bg-[#F6465D]/20 text-[#F6465D] border-[#F6465D]/50',
        border: 'border-[#F6465D]/40',
        accentText: 'text-[#F6465D]',
      };
    case 'WEAK_TO_STRONG':
      return {
        badge: 'bg-[#F59E0B]/20 text-[#F59E0B] border-[#F59E0B]/50',
        border: 'border-[#F59E0B]/40',
        accentText: 'text-[#F59E0B]',
      };
    case 'OVERHEAT_DUMP':
      return {
        badge: 'bg-[#a855f7]/20 text-[#c084fc] border-[#a855f7]/50',
        border: 'border-[#a855f7]/40',
        accentText: 'text-[#c084fc]',
      };
    case 'NUCLEAR_BUTTON':
      return {
        badge: 'bg-[#0ECB81]/20 text-[#0ECB81] border-[#0ECB81]/50',
        border: 'border-[#0ECB81]/50',
        accentText: 'text-[#0ECB81]',
      };
    default:
      return {
        badge: 'bg-[#131722] text-[#9ca3af] border-[#2a2e39]',
        border: 'border-[#2a2e39]',
        accentText: 'text-[#d1d4dc]',
      };
  }
}

/**
 * 中央面板顶部专用的【09:25 竞价雷达插件】
 * 包含：
 * 1. 竞价金额占昨比计算 ((09:25竞价成交额 / 昨日全天成交额) * 100%) 及黄金抢筹区间进度条
 * 2. 09:25 竞价量比分析与买一未匹配封单 / 卖一未匹配压单监控
 * 3. 自动识别【超预期抢筹】、【一字巨封顶板】、【分歧弱转强】、【爆量兑现预警】与【竞价核按钮】信号
 * 4. 全市场竞价异动快筛标签与交互式竞价参数推演仿真器
 */
export const CallAuctionRadarPlugin: React.FC = () => {
  const quotes = useMarketStore((s) => s.quotes);
  const symbolOrder = useMarketStore((s) => s.symbolOrder);
  const selectedSymbol = useMarketStore((s) => s.selectedSymbol);
  const workspaceMode = useMarketStore((s) => s.workspaceMode);
  const setSelectedSymbol = useMarketStore((s) => s.setSelectedSymbol);
  const openQuantModule = useMarketStore((s) => s.openQuantModule);
  const setWorkspaceMode = useMarketStore((s) => s.setWorkspaceMode);

  // 控制展开/收起交互式仿真器与全市场竞价榜抽屉
  const [isSimOpen, setIsSimOpen] = useState(false);
  const [isMatrixExpanded, setIsMatrixExpanded] = useState(false);
  const [overrideMap, setOverrideMap] = useState<Record<string, AuctionRadarOverride>>({});

  const activeQuote = quotes[selectedSymbol];
  const currentOverride = overrideMap[selectedSymbol];

  const allQuotes = useMemo(
    () => symbolOrder.map((sym) => quotes[sym]).filter(Boolean),
    [quotes, symbolOrder]
  );

  // 全市场 09:25 竞价雷达扫描结果
  const allRadarMetrics = useMemo(() => {
    return allQuotes
      .map((q) => calculateAuctionRadar(q, overrideMap[q.symbol]))
      .sort((a, b) => b.amountToYesterdayRatio - a.amountToYesterdayRatio);
  }, [allQuotes, overrideMap]);

  // 统计全市场竞价信号分布与异动焦点股
  const radarSummary = useMemo(() => {
    let grabCount = 0;
    let nuclearCount = 0;
    let weakToStrongCount = 0;
    let dumpCount = 0;

    for (const m of allRadarMetrics) {
      if (m.signal === 'SUPER_GRAB' || m.signal === 'LOCKED_LIMIT_UP') grabCount++;
      else if (m.signal === 'NUCLEAR_BUTTON') nuclearCount++;
      else if (m.signal === 'WEAK_TO_STRONG') weakToStrongCount++;
      else if (m.signal === 'OVERHEAT_DUMP') dumpCount++;
    }

    // 提取典型异动标的供顶部一键切换
    const highlightStocks = allRadarMetrics.filter((m) => m.signal !== 'NORMAL').slice(0, 6);

    return {
      grabCount,
      nuclearCount,
      weakToStrongCount,
      dumpCount,
      highlightStocks,
    };
  }, [allRadarMetrics]);

  // 当前选中股票的 09:25 竞价雷达指标 + 量比耦合分析 + 超短辅助指标
  const activeAnalysis = useMemo(() => {
    if (!activeQuote) return null;
    const radar = calculateAuctionRadar(activeQuote, currentOverride);
    const volAnalysis = analyzeAuctionVolumeRatio(
      radar.auctionVolumeRatio,
      radar.amountToYesterdayRatio,
      radar.auctionChangePercent
    );
    const ladder = calculateBoardLadderSummary(allQuotes);
    const reg = calculateRegulatoryDeviation(activeQuote);
    const dvr = calculateVWDVR(activeQuote, generateIntradayForSymbol(activeQuote));

    return {
      radar,
      volAnalysis,
      ladder,
      reg,
      dvr,
    };
  }, [activeQuote, currentOverride, allQuotes]);

  if (!activeQuote || !activeAnalysis) return null;

  const { radar, volAnalysis, ladder, reg, dvr } = activeAnalysis;
  const sigStyle = getSignalStyle(radar.signal);

  const handleApplyPreset = (preset: 'grab' | 'nuclear' | 'dump' | 'reset') => {
    if (preset === 'reset') {
      setOverrideMap((prev) => {
        const next = { ...prev };
        delete next[selectedSymbol];
        return next;
      });
      return;
    }

    const yestAmt = radar.yesterdayAmount;
    if (preset === 'grab') {
      setOverrideMap((prev) => ({
        ...prev,
        [selectedSymbol]: {
          auctionChangePercent: 5.68,
          auctionAmount: Math.round(yestAmt * 0.125), // 12.50% 黄金抢筹占比
          auctionVolumeRatio: 5.85,
          unmatchedHands: 18600,
        },
      }));
    } else if (preset === 'nuclear') {
      setOverrideMap((prev) => ({
        ...prev,
        [selectedSymbol]: {
          auctionChangePercent: -8.85,
          auctionAmount: Math.round(yestAmt * 0.092),
          auctionVolumeRatio: 4.35,
          unmatchedHands: -68000,
        },
      }));
    } else if (preset === 'dump') {
      setOverrideMap((prev) => ({
        ...prev,
        [selectedSymbol]: {
          auctionChangePercent: 2.45,
          auctionAmount: Math.round(yestAmt * 0.242), // 24.20% 天量爆量兑现
          auctionVolumeRatio: 8.2,
          unmatchedHands: -4200,
        },
      }));
    }
  };

  // 竞价占昨比进度条宽度 (0% ~ 25% 映射到 0% ~ 100%)
  const ratioBarWidth = Math.min(100, Math.max(4, (radar.amountToYesterdayRatio / 25) * 100));

  return (
    <section
      aria-label="09:25 竞价雷达插件"
      data-testid="call-auction-radar-plugin"
      className="bg-[#131722] border-b border-[#2a2e39] px-3 py-2 select-none shrink-0"
    >
      {/* 第一行：插件标题栏 + 全市场信号计数 + 异动标的快切胶囊 + 仿真/展开控制 */}
      <div className="flex flex-wrap items-center justify-between gap-2 pb-1.5 border-b border-[#2a2e39]/80">
        <div className="flex flex-wrap items-center gap-2 min-w-0">
          <div className="flex items-center gap-1.5 shrink-0">
            <Radar className="w-4 h-4 text-[#F59E0B] shrink-0" />
            <span className="text-xs font-bold text-white tracking-tight whitespace-nowrap">
              09:25 竞价雷达
            </span>
          </div>

          {/* 全市场信号实时统计 */}
          <div className="hidden sm:flex items-center gap-1 text-[11px] font-mono tabular-nums shrink-0">
            <span className="px-1.5 py-0.5 rounded bg-[#F6465D]/15 text-[#F6465D] border border-[#F6465D]/30 whitespace-nowrap">
              抢筹/巨封 {radarSummary.grabCount}
            </span>
            <span className="px-1.5 py-0.5 rounded bg-[#F59E0B]/15 text-[#F59E0B] border border-[#F59E0B]/30 whitespace-nowrap">
              弱转强 {radarSummary.weakToStrongCount}
            </span>
            <span className="px-1.5 py-0.5 rounded bg-[#0ECB81]/15 text-[#0ECB81] border border-[#0ECB81]/30 whitespace-nowrap">
              核按钮 {radarSummary.nuclearCount}
            </span>
          </div>

          {/* 异动焦点股一键切换按钮 */}
          <div className="hidden lg:flex items-center gap-1 flex-wrap">
            {radarSummary.highlightStocks.slice(0, 4).map((item) => {
              const isCurrent = item.symbol === selectedSymbol;
              const isGrab =
                item.signal === 'SUPER_GRAB' ||
                item.signal === 'LOCKED_LIMIT_UP' ||
                item.signal === 'WEAK_TO_STRONG';
              return (
                <button
                  key={item.symbol}
                  type="button"
                  data-testid={`radar-quick-stock-${item.code}`}
                  onClick={() => setSelectedSymbol(item.symbol)}
                  className={`flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] border transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
                    isCurrent
                      ? 'bg-[#2962ff]/25 border-[#2962ff] text-white font-semibold'
                      : 'bg-[#1e222d] hover:bg-[#262b38] border-[#2a2e39] text-[#d1d4dc]'
                  }`}
                >
                  <span
                    className={
                      item.signal === 'NUCLEAR_BUTTON'
                        ? 'text-[#0ECB81] font-semibold'
                        : isGrab
                        ? 'text-[#F6465D] font-semibold'
                        : 'text-[#c084fc] font-semibold'
                    }
                  >
                    [{item.signalLabel}]
                  </span>
                  <span>{item.name}</span>
                  <span className="font-mono tabular-nums text-[10px] text-[#9ca3af]">
                    {item.amountToYesterdayRatio.toFixed(1)}%
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* 右侧：竞价仿真推演、展开全市场雷达矩阵、进入超短作战室 */}
        <div className="flex items-center gap-1.5 shrink-0">
          <button
            type="button"
            data-testid="toggle-auction-sim-btn"
            onClick={() => setIsSimOpen((v) => !v)}
            className={`flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium border transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
              isSimOpen || currentOverride
                ? 'bg-[#F59E0B]/20 border-[#F59E0B] text-[#F59E0B]'
                : 'bg-[#1e222d] hover:bg-[#262b38] border-[#2a2e39] text-[#9ca3af] hover:text-white'
            }`}
          >
            <SlidersHorizontal className="w-3 h-3" />
            <span>信号推演</span>
          </button>

          <button
            type="button"
            data-testid="toggle-auction-matrix-btn"
            onClick={() => setIsMatrixExpanded((v) => !v)}
            className="flex items-center gap-1 px-2 py-0.5 rounded bg-[#1e222d] hover:bg-[#262b38] border border-[#2a2e39] text-[11px] font-medium text-[#d1d4dc] hover:text-white transition-colors whitespace-nowrap shrink-0 cursor-pointer"
          >
            <span>{isMatrixExpanded ? '收起雷达榜' : '全市场竞价榜'}</span>
            {isMatrixExpanded ? (
              <ChevronUp className="w-3 h-3" />
            ) : (
              <ChevronDown className="w-3 h-3" />
            )}
          </button>

          <button
            type="button"
            data-testid="toggle-quant-workbench-btn"
            onClick={() =>
              setWorkspaceMode(workspaceMode === 'quant' ? 'chart' : 'quant')
            }
            className={`flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
              workspaceMode === 'quant'
                ? 'bg-[#2962ff] text-white'
                : 'bg-[#F6465D]/15 text-[#F6465D] border border-[#F6465D]/40 hover:bg-[#F6465D] hover:text-white'
            }`}
          >
            <Zap className="w-3 h-3" />
            <span>{workspaceMode === 'quant' ? '返回K线主图' : '超短游资作战室'}</span>
          </button>
        </div>
      </div>

      {/* 第二行：当前选中标的 09:25 竞价三维核心算子面板 (信号识别 + 金额占比计算 + 量比与封单分析) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5 pt-2">
        {/* 卡片 1：09:25 竞价信号识别（核按钮 / 超预期抢筹 / 一字巨封 / 弱转强） */}
        <div
          className={`flex flex-col justify-between p-2.5 rounded bg-[#1e222d] border overflow-hidden ${sigStyle.border}`}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] text-[#9ca3af] font-medium truncate">
              09:25 信号识别 · {radar.name}
            </span>
            <span
              data-testid="active-auction-signal-badge"
              className={`px-2 py-0.5 rounded border text-[11px] font-bold whitespace-nowrap shrink-0 ${sigStyle.badge}`}
            >
              {radar.signalLabel}
            </span>
          </div>
          <div className="mt-1.5 flex items-baseline justify-between gap-2 font-mono tabular-nums">
            <div className="whitespace-nowrap">
              <span className="text-[11px] text-[#787b86] mr-1 font-sans">撮合价:</span>
              <span
                className={`text-sm font-bold ${getSignedColorClass(
                  radar.auctionChangePercent
                )}`}
              >
                {formatPrice(radar.auctionPrice)} (
                {formatSignedPercent(radar.auctionChangePercent)})
              </span>
            </div>
            <span className="text-[11px] text-[#d1d4dc] font-sans truncate">
              {activeQuote.ultraShort?.yesterdayPerformanceNote ?? '昨常态收盘'}
            </span>
          </div>
          <div
            data-testid="active-auction-signal-reason"
            className="mt-1 text-[11px] text-[#9ca3af] truncate"
            title={radar.signalReason}
          >
            {radar.signalReason}
          </div>
        </div>

        {/* 卡片 2：竞价金额占昨比计算 ((09:25竞价成交额 / 昨全天成交额) * 100%) */}
        <div className="flex flex-col justify-between p-2.5 rounded bg-[#1e222d] border border-[#2a2e39] overflow-hidden">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] text-[#9ca3af] font-medium whitespace-nowrap">
              竞价金额占昨比 (黄金线 6%~16%)
            </span>
            <span
              data-testid="active-auction-amount-ratio"
              className={`font-mono tabular-nums text-sm font-bold whitespace-nowrap shrink-0 ${
                radar.amountToYesterdayRatio >= 20
                  ? 'text-[#c084fc]'
                  : radar.amountToYesterdayRatio >= 6.0
                  ? 'text-[#F6465D]'
                  : 'text-[#d1d4dc]'
              }`}
            >
              {radar.amountToYesterdayRatio.toFixed(2)}%
            </span>
          </div>

          {/* 占昨比可视化阈值进度条 */}
          <div className="my-1.5">
            <div className="relative w-full h-2 bg-[#131722] rounded overflow-hidden">
              {/* 6%~16% 黄金抢筹区间底色标记 */}
              <div
                className="absolute top-0 bottom-0 bg-[#F59E0B]/20 border-x border-[#F59E0B]/40"
                style={{ left: '24%', width: '40%' }}
                title="黄金抢筹区间: 6% ~ 16%"
              />
              <div
                className={`h-full transition-all duration-200 ${
                  radar.amountToYesterdayRatio >= 20
                    ? 'bg-[#a855f7]'
                    : radar.amountToYesterdayRatio >= 6.0
                    ? 'bg-[#F6465D]'
                    : 'bg-[#2962ff]'
                }`}
                style={{ width: `${ratioBarWidth}%` }}
              />
            </div>
          </div>

          <div className="flex items-center justify-between gap-2 text-[11px] font-mono tabular-nums text-[#9ca3af] whitespace-nowrap">
            <span>
              09:25竞价额 <strong className="text-white">{formatAmountCN(radar.auctionAmount)}</strong>
            </span>
            <span>
              昨全天额 <strong className="text-[#d1d4dc]">{formatAmountCN(radar.yesterdayAmount)}</strong>
            </span>
          </div>
        </div>

        {/* 卡片 3：09:25 竞价量比分析与未匹配封单/压单 */}
        <div className="flex flex-col justify-between p-2.5 rounded bg-[#1e222d] border border-[#2a2e39] overflow-hidden">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] text-[#9ca3af] font-medium whitespace-nowrap">
              09:25 量比分析与未匹配单
            </span>
            <span className="px-1.5 py-0.5 rounded bg-[#131722] border border-[#2a2e39] text-[10px] font-semibold text-[#F59E0B] whitespace-nowrap shrink-0">
              {volAnalysis.levelLabel} · {volAnalysis.intensityScore}分
            </span>
          </div>

          <div className="mt-1.5 flex items-baseline justify-between gap-2 font-mono tabular-nums whitespace-nowrap">
            <div>
              <span className="text-[11px] text-[#787b86] mr-1 font-sans">竞价量比:</span>
              <span
                data-testid="active-auction-vol-ratio"
                className="text-sm font-bold text-[#F59E0B]"
              >
                {radar.auctionVolumeRatio.toFixed(2)}x
              </span>
            </div>
            <div>
              <span className="text-[11px] text-[#787b86] mr-1 font-sans">未匹配:</span>
              <span
                data-testid="active-auction-unmatched"
                className={`text-xs font-bold ${
                  radar.unmatchedHands >= 0 ? 'text-[#F6465D]' : 'text-[#0ECB81]'
                }`}
              >
                {radar.unmatchedHands >= 0
                  ? `买封 +${radar.unmatchedHands.toLocaleString('en-US')}手`
                  : `卖压 ${radar.unmatchedHands.toLocaleString('en-US')}手`}
              </span>
            </div>
          </div>

          <div
            className="mt-1 text-[11px] text-[#9ca3af] truncate"
            title={volAnalysis.description}
          >
            {volAnalysis.description}
          </div>
        </div>
      </div>

      {/* 第三行：超短游资规则快速联动条 (连板梯队断层 + k∈{2,3}法定异动压线价 + VW-DVR承接得分) */}
      <div className="flex flex-wrap items-center justify-between gap-2 pt-1.5 mt-1.5 border-t border-[#2a2e39]/60 text-[11px]">
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => openQuantModule('ladder')}
            className="flex items-center gap-1 text-[#9ca3af] hover:text-white cursor-pointer whitespace-nowrap"
          >
            <Flame className="w-3.5 h-3.5 text-[#F6465D]" />
            <span>
              连板梯队: 最高 <strong className="font-mono text-[#F6465D]">{ladder.maxBoardHeight}连板</strong>
              {ladder.hasLadderFault && (
                <span className="text-[#F59E0B] ml-1">
                  (断层缺失 {ladder.missingBoards.join('/')} 板)
                </span>
              )}
            </span>
          </button>

          <span className="text-[#2a2e39]">|</span>

          <button
            type="button"
            onClick={() => openQuantModule('regulatory')}
            className="flex items-center gap-1 text-[#9ca3af] hover:text-white cursor-pointer whitespace-nowrap"
          >
            <Scale className="w-3.5 h-3.5 text-[#F59E0B]" />
            <span>
              k∈&#123;2,3&#125;法定异动压线价:{' '}
              <strong className="font-mono tabular-nums text-[#F59E0B]">
                {formatPrice(reg.effectiveTriggerPrice)}元 ({formatSignedPercent(reg.effectiveMaxSafeChangePercent)})
              </strong>
            </span>
          </button>

          <span className="hidden sm:inline text-[#2a2e39]">|</span>

          <button
            type="button"
            onClick={() => openQuantModule('vwdvr')}
            className="hidden sm:flex items-center gap-1 text-[#9ca3af] hover:text-white cursor-pointer whitespace-nowrap"
          >
            <Activity className="w-3.5 h-3.5 text-[#0ECB81]" />
            <span>
              VW-DVR承接算子:{' '}
              <strong className="font-mono tabular-nums text-white">{dvr.vwDvrScore}分</strong> ({dvr.signalLabel})
            </span>
          </button>
        </div>

        <button
          type="button"
          onClick={() => openQuantModule('auction')}
          className="text-[#38bdf8] hover:underline font-medium whitespace-nowrap cursor-pointer"
        >
          查看全市场 09:25 竞价深度归因 &rarr;
        </button>
      </div>

      {/* 可选展开区 1：交互式 09:25 竞价信号推演仿真器 */}
      {isSimOpen && (
        <div
          data-testid="auction-simulator-panel"
          className="mt-2 p-2.5 rounded bg-[#1e222d] border border-[#F59E0B]/40 text-xs"
        >
          <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-[#2a2e39]">
            <div className="flex items-center gap-2">
              <span className="font-bold text-[#F59E0B]">
                09:25 竞价信号实时推演仿真 ({radar.name})
              </span>
              <span className="text-[11px] text-[#9ca3af]">
                调节下方竞价参数或点击典型场景，实时验证【超预期抢筹】与【竞价核按钮】判定阈值
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                data-testid="sim-preset-grab"
                onClick={() => handleApplyPreset('grab')}
                className="px-2 py-0.5 rounded bg-[#F6465D]/20 hover:bg-[#F6465D]/30 border border-[#F6465D]/40 text-[#F6465D] text-[11px] font-semibold cursor-pointer"
              >
                模拟超预期抢筹
              </button>
              <button
                type="button"
                data-testid="sim-preset-nuclear"
                onClick={() => handleApplyPreset('nuclear')}
                className="px-2 py-0.5 rounded bg-[#0ECB81]/20 hover:bg-[#0ECB81]/30 border border-[#0ECB81]/40 text-[#0ECB81] text-[11px] font-semibold cursor-pointer"
              >
                模拟竞价核按钮
              </button>
              <button
                type="button"
                data-testid="sim-preset-dump"
                onClick={() => handleApplyPreset('dump')}
                className="px-2 py-0.5 rounded bg-[#a855f7]/20 hover:bg-[#a855f7]/30 border border-[#a855f7]/40 text-[#c084fc] text-[11px] font-semibold cursor-pointer"
              >
                模拟爆量兑现
              </button>
              <button
                type="button"
                data-testid="sim-preset-reset"
                onClick={() => handleApplyPreset('reset')}
                className="flex items-center gap-1 px-2 py-0.5 rounded bg-[#131722] hover:bg-[#2a2e39] border border-[#2a2e39] text-[#9ca3af] hover:text-white text-[11px] cursor-pointer"
              >
                <RotateCcw className="w-3 h-3" />
                <span>重置实盘</span>
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[#9ca3af] whitespace-nowrap">09:25 竞价涨幅:</span>
              <input
                type="range"
                aria-label="09:25竞价涨跌幅推演"
                min={-10}
                max={10}
                step={0.2}
                value={radar.auctionChangePercent}
                onChange={(e) =>
                  setOverrideMap((prev) => ({
                    ...prev,
                    [selectedSymbol]: {
                      ...prev[selectedSymbol],
                      auctionChangePercent: Number(e.target.value),
                    },
                  }))
                }
                className="w-28 accent-[#F6465D] cursor-pointer"
              />
              <span className="font-mono tabular-nums font-bold text-white w-14 text-right">
                {formatSignedPercent(radar.auctionChangePercent)}
              </span>
            </div>

            <div className="flex items-center justify-between gap-2">
              <span className="text-[#9ca3af] whitespace-nowrap">竞价金额占昨比:</span>
              <input
                type="range"
                aria-label="09:25竞价金额占昨比推演"
                min={1}
                max={30}
                step={0.5}
                value={radar.amountToYesterdayRatio}
                onChange={(e) => {
                  const pct = Number(e.target.value);
                  setOverrideMap((prev) => ({
                    ...prev,
                    [selectedSymbol]: {
                      ...prev[selectedSymbol],
                      auctionAmount: Math.round(radar.yesterdayAmount * (pct / 100)),
                    },
                  }));
                }}
                className="w-28 accent-[#F59E0B] cursor-pointer"
              />
              <span className="font-mono tabular-nums font-bold text-[#F59E0B] w-14 text-right">
                {radar.amountToYesterdayRatio.toFixed(1)}%
              </span>
            </div>

            <div className="flex items-center justify-between gap-2">
              <span className="text-[#9ca3af] whitespace-nowrap">未匹配封单/压单:</span>
              <input
                type="range"
                aria-label="09:25未匹配手数推演"
                min={-80000}
                max={80000}
                step={2000}
                value={radar.unmatchedHands}
                onChange={(e) =>
                  setOverrideMap((prev) => ({
                    ...prev,
                    [selectedSymbol]: {
                      ...prev[selectedSymbol],
                      unmatchedHands: Number(e.target.value),
                    },
                  }))
                }
                className="w-28 accent-[#2962ff] cursor-pointer"
              />
              <span className="font-mono tabular-nums font-bold text-white w-20 text-right">
                {radar.unmatchedHands >= 0
                  ? `+${(radar.unmatchedHands / 10000).toFixed(1)}万手`
                  : `${(radar.unmatchedHands / 10000).toFixed(1)}万手`}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* 可选展开区 2：全市场 09:25 竞价雷达速查表 */}
      {isMatrixExpanded && (
        <div
          data-testid="expanded-auction-matrix"
          className="mt-2 rounded bg-[#1e222d] border border-[#2a2e39] overflow-hidden max-h-52 overflow-y-auto"
        >
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-[#2a2e39] bg-[#161a24] text-[#787b86] text-[11px] sticky top-0">
                <th className="py-1.5 px-2.5 whitespace-nowrap">标的</th>
                <th className="py-1.5 px-2 text-right whitespace-nowrap">09:25撮合 / 涨幅</th>
                <th className="py-1.5 px-2 text-right whitespace-nowrap">竞价成交额</th>
                <th className="py-1.5 px-2 text-right whitespace-nowrap">金额占昨比</th>
                <th className="py-1.5 px-2 text-right whitespace-nowrap">竞价量比</th>
                <th className="py-1.5 px-2 text-right whitespace-nowrap">未匹配手数</th>
                <th className="py-1.5 px-2 whitespace-nowrap">信号识别</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#2a2e39]/60">
              {allRadarMetrics.map((item) => {
                const st = getSignalStyle(item.signal);
                return (
                  <tr
                    key={item.symbol}
                    onClick={() => setSelectedSymbol(item.symbol)}
                    className={`cursor-pointer transition-colors ${
                      item.symbol === selectedSymbol
                        ? 'bg-[#2962ff]/20'
                        : 'hover:bg-[#262b38]'
                    }`}
                  >
                    <td className="py-1.5 px-2.5 whitespace-nowrap">
                      <span className="font-semibold text-white">{item.name}</span>
                      <span className="ml-1 font-mono tabular-nums text-[10px] text-[#787b86]">
                        {item.code}
                      </span>
                    </td>
                    <td
                      className={`py-1.5 px-2 text-right font-mono tabular-nums font-semibold whitespace-nowrap ${getSignedColorClass(
                        item.auctionChangePercent
                      )}`}
                    >
                      {formatPrice(item.auctionPrice)} (
                      {formatSignedPercent(item.auctionChangePercent)})
                    </td>
                    <td className="py-1.5 px-2 text-right font-mono tabular-nums text-[#d1d4dc] whitespace-nowrap">
                      {formatAmountCN(item.auctionAmount)}
                    </td>
                    <td className="py-1.5 px-2 text-right font-mono tabular-nums font-bold text-[#F59E0B] whitespace-nowrap">
                      {item.amountToYesterdayRatio.toFixed(2)}%
                    </td>
                    <td className="py-1.5 px-2 text-right font-mono tabular-nums text-white whitespace-nowrap">
                      {item.auctionVolumeRatio.toFixed(2)}x
                    </td>
                    <td
                      className={`py-1.5 px-2 text-right font-mono tabular-nums font-semibold whitespace-nowrap ${
                        item.unmatchedHands >= 0 ? 'text-[#F6465D]' : 'text-[#0ECB81]'
                      }`}
                    >
                      {item.unmatchedHands >= 0
                        ? `买封 +${item.unmatchedHands.toLocaleString('en-US')}手`
                        : `卖压 ${item.unmatchedHands.toLocaleString('en-US')}手`}
                    </td>
                    <td className="py-1.5 px-2 whitespace-nowrap">
                      <span
                        className={`inline-block px-1.5 py-0.2 rounded border text-[10px] font-semibold ${st.badge}`}
                      >
                        {item.signalLabel}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
};
