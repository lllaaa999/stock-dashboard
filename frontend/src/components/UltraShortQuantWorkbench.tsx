import React, { useMemo, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  Building2,
  Flame,
  Layers,
  Radar,
  Scale,
  ShieldAlert,
  Zap,
} from 'lucide-react';
import { generateIntradayForSymbol } from '../data/seedMarket';
import { useMarketStore } from '../store/useMarketStore';
import type {
  AuctionSignalType,
  DragonTigerPresetMode,
  DragonTigerSeatNature,
  ThemeResonanceScenarioPreset,
} from '../types/market';
import {
  formatAmountCN,
  formatPrice,
  formatSignedPercent,
  getSignedColorClass,
} from '../utils/marketCalc';
import {
  analyzeMarketRegulatoryOverview,
  analyzeMarketThemeResonance,
  analyzeStockDragonTigerList,
  calculateAuctionRadar,
  calculateBoardLadderSummary,
  calculateRegulatoryDeviation,
  calculateThemeResonance,
  calculateVWDVR,
  getDragonRoleLabel,
  type LadderScenarioPreset,
} from '../utils/ultraShortQuant';
import { DragonTigerNetworkGraph } from './DragonTigerNetworkGraph';
import { RegulatoryMonitorPanel } from './RegulatoryMonitorPanel';
import { ThemeResonanceMonitorPanel } from './ThemeResonanceMonitorPanel';

function getAuctionSignalBadgeClass(signal: AuctionSignalType): string {
  switch (signal) {
    case 'LOCKED_LIMIT_UP':
      return 'bg-[#F6465D]/20 text-[#F6465D] border-[#F6465D]/50';
    case 'SUPER_GRAB':
      return 'bg-[#F6465D]/15 text-[#ff6b81] border-[#F6465D]/40';
    case 'WEAK_TO_STRONG':
      return 'bg-[#F59E0B]/15 text-[#F59E0B] border-[#F59E0B]/40';
    case 'OVERHEAT_DUMP':
      return 'bg-[#a855f7]/15 text-[#c084fc] border-[#a855f7]/40';
    case 'NUCLEAR_BUTTON':
      return 'bg-[#0ECB81]/20 text-[#0ECB81] border-[#0ECB81]/50';
    default:
      return 'bg-[#131722] text-[#9ca3af] border-[#2a2e39]';
  }
}

function getSeatNatureBadgeClass(nature: DragonTigerSeatNature): string {
  switch (nature) {
    case 'HOT_MONEY':
      return 'bg-[#F6465D]/20 text-[#F6465D] border-[#F6465D]/50';
    case 'INSTITUTION':
      return 'bg-[#F59E0B]/20 text-[#F59E0B] border-[#F59E0B]/50';
    case 'QUANT_CAMP':
      return 'bg-[#a855f7]/20 text-[#c084fc] border-[#a855f7]/50';
    case 'RETAIL_CAMP':
      return 'bg-[#38bdf8]/20 text-[#38bdf8] border-[#38bdf8]/50';
  }
}

/**
 * 顶部单股超短游资五维实时诊断条 (常驻于 K 线/分时主图上方)
 * 让交易员在看盘同时一眼掌握：09:25竞价占昨比、连板身位与断层、题材点面共振、k∈{2,3}异动安全上限价、VW-DVR承接算子
 */
export const UltraShortStockDiagnosticStrip: React.FC = () => {
  const quotes = useMarketStore((s) => s.quotes);
  const selectedSymbol = useMarketStore((s) => s.selectedSymbol);
  const workspaceMode = useMarketStore((s) => s.workspaceMode);
  const openQuantModule = useMarketStore((s) => s.openQuantModule);
  const setWorkspaceMode = useMarketStore((s) => s.setWorkspaceMode);

  const activeQuote = quotes[selectedSymbol];

  const diagnostic = useMemo(() => {
    if (!activeQuote) return null;
    const allQuotes = Object.values(quotes);
    const auction = calculateAuctionRadar(activeQuote);
    const ladder = calculateBoardLadderSummary(allQuotes);
    const themes = calculateThemeResonance(allQuotes);
    const currentTheme = themes.find((t) => t.sectorName === activeQuote.sector) ?? themes[0];
    const reg = calculateRegulatoryDeviation(activeQuote);
    const intraday = generateIntradayForSymbol(activeQuote);
    const dvr = calculateVWDVR(activeQuote, intraday);

    return {
      auction,
      ladder,
      currentTheme,
      reg,
      dvr,
    };
  }, [activeQuote, quotes]);

  if (!activeQuote || !diagnostic) return null;

  const { auction, ladder, currentTheme, reg, dvr } = diagnostic;
  const boards = activeQuote.ultraShort?.consecutiveBoards ?? 0;
  const roleLabel = getDragonRoleLabel(activeQuote.ultraShort?.dragonRole ?? 'FOLLOWER');

  return (
    <div
      data-testid="ultrashort-diagnostic-strip"
      className="bg-[#131722] border-b border-[#2a2e39] px-3 py-1.5 select-none shrink-0"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        {/* 五大超短游资实时算子速览卡片 */}
        <div className="flex flex-wrap items-center gap-2 min-w-0">
          {/* 1. 09:25 竞价雷达 */}
          <button
            type="button"
            onClick={() => openQuantModule('auction')}
            className="flex items-center gap-1.5 px-2 py-1 rounded bg-[#1e222d] hover:bg-[#262b38] border border-[#2a2e39] text-[11px] transition-colors cursor-pointer whitespace-nowrap shrink-0"
          >
            <Radar className="w-3.5 h-3.5 text-[#F59E0B]" />
            <span className="text-[#787b86]">09:25竞价:</span>
            <span
              className={`px-1.5 py-0.2 rounded border text-[10px] font-semibold ${getAuctionSignalBadgeClass(
                auction.signal
              )}`}
            >
              {auction.signalLabel}
            </span>
            <span className="font-mono tabular-nums text-[#d1d4dc]">
              占昨 <strong className="text-white">{auction.amountToYesterdayRatio.toFixed(1)}%</strong>
            </span>
          </button>

          {/* 2. 连板身位与断层监测 */}
          <button
            type="button"
            onClick={() => openQuantModule('ladder')}
            className="flex items-center gap-1.5 px-2 py-1 rounded bg-[#1e222d] hover:bg-[#262b38] border border-[#2a2e39] text-[11px] transition-colors cursor-pointer whitespace-nowrap shrink-0"
          >
            <Flame className="w-3.5 h-3.5 text-[#F6465D]" />
            <span className="text-[#787b86]">梯队身位:</span>
            <span className="font-mono tabular-nums font-semibold text-[#F6465D]">
              {boards >= 1 ? `${boards}连板` : '趋势/首板备选'} · {roleLabel}
            </span>
            <span className="text-[#787b86]">|</span>
            <span className="font-mono tabular-nums text-[#9ca3af]">
              最高标 <strong className="text-white">{ladder.maxBoardHeight}板</strong>
              {ladder.hasLadderFault && (
                <span className="ml-1 text-[#F59E0B]">
                  (断层缺{ladder.missingBoards.join('/')}板)
                </span>
              )}
            </span>
          </button>

          {/* 3. 题材点面共振 */}
          {currentTheme && (
            <button
              type="button"
              onClick={() => openQuantModule('resonance')}
              className="hidden sm:flex items-center gap-1.5 px-2 py-1 rounded bg-[#1e222d] hover:bg-[#262b38] border border-[#2a2e39] text-[11px] transition-colors cursor-pointer whitespace-nowrap shrink-0"
            >
              <Layers className="w-3.5 h-3.5 text-[#38bdf8]" />
              <span className="text-[#787b86]">点面共振:</span>
              <span className="text-white font-medium">{currentTheme.sectorName}</span>
              <span className="font-mono tabular-nums text-[#38bdf8] font-semibold">
                {currentTheme.resonanceScore}分
              </span>
              <span className="text-[10px] text-[#9ca3af]">({currentTheme.resonanceStatus})</span>
            </button>
          )}

          {/* 4. 监管异动监测 (k ∈ {2, 3} 异动窗口与红黄灯预警) */}
          <button
            type="button"
            onClick={() => openQuantModule('regulatory')}
            className={`flex items-center gap-1.5 px-2 py-1 rounded border text-[11px] transition-colors cursor-pointer whitespace-nowrap shrink-0 ${
              reg.alertLight === 'RED'
                ? 'bg-[#F6465D]/15 border-[#F6465D]/50 text-[#F6465D]'
                : reg.alertLight === 'YELLOW'
                ? 'bg-[#F59E0B]/15 border-[#F59E0B]/50 text-[#F59E0B]'
                : 'bg-[#1e222d] hover:bg-[#262b38] border-[#2a2e39] text-[#d1d4dc]'
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full ${
                reg.alertLight === 'RED'
                  ? 'bg-[#F6465D] shadow-[0_0_6px_#F6465D]'
                  : reg.alertLight === 'YELLOW'
                  ? 'bg-[#F59E0B] shadow-[0_0_6px_#F59E0B]'
                  : 'bg-[#0ECB81]'
              }`}
            />
            <span className="text-[#787b86]">监管异动监测:</span>
            <span className="font-mono tabular-nums font-semibold">
              {formatPrice(reg.effectiveTriggerPrice)}元 (
              {formatSignedPercent(reg.effectiveMaxSafeChangePercent)})
            </span>
            {reg.severeSuspensionLockWarning && (
              <span className="px-1 rounded bg-[#F6465D] text-white text-[10px] font-bold">
                红灯·10日{reg.cumDeviation10dPercent}%
              </span>
            )}
          </button>

          {/* 5. 真实成交量加权承接算子 (VW-DVR) */}
          <button
            type="button"
            onClick={() => openQuantModule('vwdvr')}
            className="hidden lg:flex items-center gap-1.5 px-2 py-1 rounded bg-[#1e222d] hover:bg-[#262b38] border border-[#2a2e39] text-[11px] transition-colors cursor-pointer whitespace-nowrap shrink-0"
          >
            <Activity className="w-3.5 h-3.5 text-[#0ECB81]" />
            <span className="text-[#787b86]">VW-DVR承接:</span>
            <span
              className={`font-mono tabular-nums font-bold ${
                dvr.vwDvrScore >= 74
                  ? 'text-[#F6465D]'
                  : dvr.vwDvrScore >= 48
                  ? 'text-[#F59E0B]'
                  : 'text-[#0ECB81]'
              }`}
            >
              {dvr.vwDvrScore}分
            </span>
            <span className="text-[10px] text-[#9ca3af]">({dvr.signalLabel})</span>
          </button>
        </div>

        {/* 右侧：切换全景超短量化作战室按钮 */}
        <button
          type="button"
          data-testid="toggle-quant-workbench-btn"
          onClick={() =>
            setWorkspaceMode(workspaceMode === 'quant' ? 'chart' : 'quant')
          }
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-semibold transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
            workspaceMode === 'quant'
              ? 'bg-[#2962ff] text-white'
              : 'bg-[#F6465D]/15 text-[#F6465D] border border-[#F6465D]/40 hover:bg-[#F6465D] hover:text-white'
          }`}
        >
          <Zap className="w-3.5 h-3.5" />
          <span>{workspaceMode === 'quant' ? '返回K线看盘主图' : '超短游资量化作战室'}</span>
        </button>
      </div>
    </div>
  );
};

/**
 * 超短游资量化作战室主面板 (包含 5 大核心实战引擎)
 * 1. 09:25 竞价雷达（金额占昨比、量比、竞价核按钮/超预期抢筹识别）
 * 2. 涨跌停连板梯队（高度板、首板晋级率、断层监测）
 * 3. 题材点面共振与先锋龙身位识别
 * 4. 现行注册制法定复利异动监管逆推（k∈{2,3} 法定异动窗口与特停锁死预警）
 * 5. 真实成交量加权承接算子（VW-DVR）
 */
export const UltraShortQuantWorkbench: React.FC<{ compact?: boolean }> = ({
  compact = false,
}) => {
  const quotes = useMarketStore((s) => s.quotes);
  const symbolOrder = useMarketStore((s) => s.symbolOrder);
  const selectedSymbol = useMarketStore((s) => s.selectedSymbol);
  const quantModuleTab = useMarketStore((s) => s.quantModuleTab);
  const setQuantModuleTab = useMarketStore((s) => s.setQuantModuleTab);
  const setSelectedSymbol = useMarketStore((s) => s.setSelectedSymbol);
  const setWorkspaceMode = useMarketStore((s) => s.setWorkspaceMode);

  // 竞价雷达信号过滤器
  const [auctionFilter, setAuctionFilter] = useState<'ALL' | AuctionSignalType>('ALL');
  // 连板梯队断层监测：实盘分布 vs 极端退潮断层 vs 完整梯队推演切换
  const [ladderScenario, setLadderScenario] = useState<LadderScenarioPreset>('live');
  // 龙虎榜席位分析：实盘席位 vs 游资+机构共振 vs 量化扎堆 vs 拉萨接盘推演
  const [dragonTigerPreset, setDragonTigerPreset] =
    useState<DragonTigerPresetMode>('live');
  // 板块/题材共振监测：实盘题材共振 vs AI+算力双主线爆发 vs 高低切轮动分化
  const [themeScenario, setThemeScenario] =
    useState<ThemeResonanceScenarioPreset>('live');
  // 注册制异动逆推：基准指数今日实时涨幅模拟滑块 (%)
  const [simulatedIndexPct, setSimulatedIndexPct] = useState<number | null>(null);

  const allQuotes = useMemo(
    () => symbolOrder.map((sym) => quotes[sym]).filter(Boolean),
    [quotes, symbolOrder]
  );

  const activeQuote = quotes[selectedSymbol] ?? allQuotes[0];

  // 1. 09:25 竞价雷达全量计算
  const auctionList = useMemo(() => {
    const list = allQuotes.map((q) => calculateAuctionRadar(q));
    return list.sort((a, b) => b.amountToYesterdayRatio - a.amountToYesterdayRatio);
  }, [allQuotes]);

  const filteredAuctionList = useMemo(() => {
    if (auctionFilter === 'ALL') return auctionList;
    return auctionList.filter((item) => item.signal === auctionFilter);
  }, [auctionList, auctionFilter]);

  // 2. 连板梯队与断层监测（自动对比今日涨停分布与昨日连板基数，识别晋级断层与退潮风险）
  const ladderSummary = useMemo(
    () => calculateBoardLadderSummary(allQuotes, ladderScenario),
    [allQuotes, ladderScenario]
  );

  // 3. 板块/题材共振监测与主流资金进攻方向分析
  const themeResonanceOverview = useMemo(
    () => analyzeMarketThemeResonance(allQuotes, themeScenario),
    [allQuotes, themeScenario]
  );

  // 4. 监管异动监测 (2/3日涨跌幅实时监控、k ∈ {2, 3} 法定异动窗口与红黄灯特停预警)
  const activeRegDeviation = useMemo(
    () =>
      activeQuote
        ? calculateRegulatoryDeviation(
            activeQuote,
            simulatedIndexPct !== null ? simulatedIndexPct : undefined
          )
        : null,
    [activeQuote, simulatedIndexPct]
  );

  const regulatoryOverview = useMemo(
    () =>
      analyzeMarketRegulatoryOverview(
        allQuotes,
        simulatedIndexPct !== null ? simulatedIndexPct : undefined
      ),
    [allQuotes, simulatedIndexPct]
  );

  // 5. VW-DVR 真实成交量加权承接算子
  const activeVWDVR = useMemo(() => {
    if (!activeQuote) return null;
    const pts = generateIntradayForSymbol(activeQuote);
    return calculateVWDVR(activeQuote, pts);
  }, [activeQuote]);

  const allVWDVRList = useMemo(() => {
    return allQuotes
      .map((q) => calculateVWDVR(q, generateIntradayForSymbol(q)))
      .sort((a, b) => b.vwDvrScore - a.vwDvrScore);
  }, [allQuotes]);

  // 6. 龙虎榜席位性质分析 (自动解析选定股票前五买席/前五卖席及游资/机构/量化/散户阵营)
  const activeDragonTiger = useMemo(() => {
    if (!activeQuote) return null;
    return analyzeStockDragonTigerList(activeQuote, dragonTigerPreset);
  }, [activeQuote, dragonTigerPreset]);

  const tabs: {
    id: typeof quantModuleTab;
    label: string;
    shortLabel: string;
  }[] = [
    { id: 'overview', label: '六维实战总览', shortLabel: '总览' },
    { id: 'auction', label: '09:25 竞价雷达', shortLabel: '09:25竞价' },
    { id: 'ladder', label: '连板梯队与断层', shortLabel: '连板梯队' },
    { id: 'dragon_tiger', label: '龙虎榜席位分析', shortLabel: '龙虎榜' },
    { id: 'resonance', label: '板块/题材共振监测', shortLabel: '题材共振' },
    { id: 'regulatory', label: '监管异动监测', shortLabel: '监管监测' },
    { id: 'vwdvr', label: 'VW-DVR 承接算子', shortLabel: 'VW-DVR' },
  ];

  return (
    <div
      data-testid="ultrashort-quant-workbench"
      className="flex flex-col flex-1 min-h-0 bg-[#0d0e12] text-[#d1d4dc] overflow-hidden select-none"
    >
      {/* 顶部子模块导航栏 */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 bg-[#131722] border-b border-[#2a2e39] shrink-0">
        <div className="flex items-center gap-1 overflow-x-auto">
          {tabs.map((tab) => {
            const active = quantModuleTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                data-testid={`quant-tab-${tab.id}`}
                onClick={() => setQuantModuleTab(tab.id)}
                className={`px-2.5 py-1 text-xs font-medium rounded transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
                  active
                    ? 'bg-[#2962ff] text-white font-semibold'
                    : 'text-[#9ca3af] hover:text-white hover:bg-[#1e222d]'
                }`}
              >
                {compact ? tab.shortLabel : tab.label}
              </button>
            );
          })}
        </div>

        {!compact && (
          <div className="hidden xl:flex items-center gap-2 shrink-0">
            <span className="text-[11px] text-[#787b86] font-mono tabular-nums">
              纯 Level-1 衍生算子 · 零 L2 虚构依赖
            </span>
          </div>
        )}
      </div>

      {/* 主体内容滚动区 */}
      <div className="flex-1 min-h-0 overflow-y-auto p-3 space-y-3">
        {/* ==================== 模块一：09:25 集合竞价雷达 ==================== */}
        {(quantModuleTab === 'overview' || quantModuleTab === 'auction') && (
          <section
            aria-label="09:25 集合竞价雷达"
            className="bg-[#1e222d] border border-[#2a2e39] rounded-md overflow-hidden"
          >
            <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 bg-[#131722] border-b border-[#2a2e39]">
              <div className="flex items-center gap-2">
                <Radar className="w-4 h-4 text-[#F59E0B]" />
                <h2 className="text-xs sm:text-sm font-bold text-white">
                  09:25 集合竞价雷达 (竞价金额占昨比 / 竞价量比 / 核按钮与抢筹识别)
                </h2>
              </div>
              <div className="flex items-center gap-1 flex-wrap">
                {(
                  [
                    { id: 'ALL', label: '全部标的' },
                    { id: 'SUPER_GRAB', label: '超预期抢筹' },
                    { id: 'LOCKED_LIMIT_UP', label: '一字巨封' },
                    { id: 'WEAK_TO_STRONG', label: '分歧弱转强' },
                    { id: 'OVERHEAT_DUMP', label: '爆量兑现' },
                    { id: 'NUCLEAR_BUTTON', label: '竞价核按钮' },
                  ] as { id: 'ALL' | AuctionSignalType; label: string }[]
                ).map((btn) => (
                  <button
                    key={btn.id}
                    type="button"
                    onClick={() => setAuctionFilter(btn.id)}
                    className={`px-2 py-0.5 rounded text-[11px] transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
                      auctionFilter === btn.id
                        ? 'bg-[#2962ff] text-white font-semibold'
                        : 'bg-[#1e222d] text-[#9ca3af] hover:text-white'
                    }`}
                  >
                    {btn.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="border-b border-[#2a2e39] text-[#787b86] bg-[#161a24] text-[11px]">
                    <th className="py-2 px-2.5 whitespace-nowrap">代码/名称</th>
                    <th className="py-2 px-2 text-right whitespace-nowrap">09:25撮合 / 涨幅</th>
                    <th className="py-2 px-2 text-right whitespace-nowrap">竞价额</th>
                    <th className="py-2 px-2.5 whitespace-nowrap">
                      竞价占昨比 (黄金线 6%~16%)
                    </th>
                    <th className="py-2 px-2 text-right whitespace-nowrap">竞价量比</th>
                    <th className="py-2 px-2 text-right whitespace-nowrap">未匹配封单/压单</th>
                    <th className="py-2 px-2 whitespace-nowrap">定性信号</th>
                    <th className="py-2 px-2.5 whitespace-nowrap">游资盘口诊断</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#2a2e39]/60">
                  {filteredAuctionList.map((item) => {
                    const isSelected = item.symbol === selectedSymbol;
                    const pctColor = getSignedColorClass(item.auctionChangePercent);
                    const barWidth = Math.min(100, Math.round(item.amountToYesterdayRatio * 4));
                    return (
                      <tr
                        key={item.symbol}
                        onClick={() => setSelectedSymbol(item.symbol)}
                        className={`cursor-pointer transition-colors ${
                          isSelected
                            ? 'bg-[#2962ff]/15 hover:bg-[#2962ff]/20'
                            : 'hover:bg-[#262b38]'
                        }`}
                      >
                        <td className="py-2 px-2.5 whitespace-nowrap">
                          <div className="font-semibold text-white">{item.name}</div>
                          <div className="text-[10px] font-mono tabular-nums text-[#787b86]">
                            {item.symbol} · {item.sector}
                          </div>
                        </td>
                        <td
                          className={`py-2 px-2 text-right font-mono tabular-nums font-semibold whitespace-nowrap ${pctColor}`}
                        >
                          <div>{formatPrice(item.auctionPrice)}</div>
                          <div className="text-[11px]">
                            {formatSignedPercent(item.auctionChangePercent)}
                          </div>
                        </td>
                        <td className="py-2 px-2 text-right font-mono tabular-nums text-[#d1d4dc] whitespace-nowrap">
                          {formatAmountCN(item.auctionAmount)}
                        </td>
                        <td className="py-2 px-2.5 whitespace-nowrap min-w-[140px]">
                          <div className="flex items-center justify-between font-mono tabular-nums text-xs mb-1">
                            <span
                              className={
                                item.amountToYesterdayRatio >= 20
                                  ? 'text-[#c084fc] font-bold'
                                  : item.amountToYesterdayRatio >= 6.5
                                  ? 'text-[#F6465D] font-bold'
                                  : 'text-[#d1d4dc]'
                              }
                            >
                              {item.amountToYesterdayRatio.toFixed(2)}%
                            </span>
                            <span className="text-[10px] text-[#787b86]">
                              昨 {formatAmountCN(item.yesterdayAmount)}
                            </span>
                          </div>
                          <div className="w-full h-1.5 bg-[#131722] rounded overflow-hidden">
                            <div
                              className={`h-full ${
                                item.amountToYesterdayRatio >= 20
                                  ? 'bg-[#a855f7]'
                                  : item.amountToYesterdayRatio >= 6.5
                                  ? 'bg-[#F6465D]'
                                  : 'bg-[#2962ff]'
                              }`}
                              style={{ width: `${barWidth}%` }}
                            />
                          </div>
                        </td>
                        <td className="py-2 px-2 text-right font-mono tabular-nums text-[#F59E0B] font-semibold whitespace-nowrap">
                          {item.auctionVolumeRatio.toFixed(2)}x
                        </td>
                        <td
                          className={`py-2 px-2 text-right font-mono tabular-nums font-semibold whitespace-nowrap ${
                            item.unmatchedHands >= 0 ? 'text-[#F6465D]' : 'text-[#0ECB81]'
                          }`}
                        >
                          {item.unmatchedHands >= 0
                            ? `买封 +${item.unmatchedHands.toLocaleString('en-US')}手`
                            : `卖压 ${item.unmatchedHands.toLocaleString('en-US')}手`}
                        </td>
                        <td className="py-2 px-2 whitespace-nowrap">
                          <span
                            className={`inline-block px-1.5 py-0.5 rounded border text-[11px] font-semibold whitespace-nowrap ${getAuctionSignalBadgeClass(
                              item.signal
                            )}`}
                          >
                            {item.signalLabel}
                          </span>
                        </td>
                        <td className="py-2 px-2.5 text-[11px] text-[#9ca3af] max-w-[190px] truncate">
                          {item.signalReason}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* ==================== 模块二：涨跌停连板梯队与断层监测 ==================== */}
        {(quantModuleTab === 'overview' || quantModuleTab === 'ladder') && (
          <section
            aria-label="涨跌停连板梯队与断层监测"
            data-testid="ladder-fault-monitor-section"
            className="bg-[#1e222d] border border-[#2a2e39] rounded-md overflow-hidden"
          >
            {/* 顶部标题栏 + 梯队断层场景沙盘切换 */}
            <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 bg-[#131722] border-b border-[#2a2e39]">
              <div className="flex items-center gap-2">
                <Flame className="w-4 h-4 text-[#F6465D]" />
                <h2 className="text-xs sm:text-sm font-bold text-white">
                  连板梯队断层监测引擎 (今日涨停板分布对比 / 晋级空间断层识别 / 退潮风险预警)
                </h2>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {/* 断层推演切换按钮组 */}
                <div
                  role="group"
                  aria-label="连板梯队分布监测模式"
                  className="flex items-center bg-[#1e222d] p-0.5 rounded border border-[#2a2e39] text-[11px]"
                >
                  <button
                    type="button"
                    data-testid="ladder-scenario-live"
                    onClick={() => setLadderScenario('live')}
                    className={`px-2 py-0.5 rounded transition-colors cursor-pointer whitespace-nowrap ${
                      ladderScenario === 'live'
                        ? 'bg-[#2962ff] text-white font-semibold'
                        : 'text-[#9ca3af] hover:text-white'
                    }`}
                  >
                    实盘监测 (缺5/4板)
                  </button>
                  <button
                    type="button"
                    data-testid="ladder-scenario-severe"
                    onClick={() => setLadderScenario('severe_ebb')}
                    className={`px-2 py-0.5 rounded transition-colors cursor-pointer whitespace-nowrap ${
                      ladderScenario === 'severe_ebb'
                        ? 'bg-[#F6465D] text-white font-semibold'
                        : 'text-[#9ca3af] hover:text-white'
                    }`}
                  >
                    推演高危退潮 (缺5/4/3板)
                  </button>
                  <button
                    type="button"
                    data-testid="ladder-scenario-healthy"
                    onClick={() => setLadderScenario('healthy_full')}
                    className={`px-2 py-0.5 rounded transition-colors cursor-pointer whitespace-nowrap ${
                      ladderScenario === 'healthy_full'
                        ? 'bg-[#0ECB81] text-[#0d0e12] font-semibold'
                        : 'text-[#9ca3af] hover:text-white'
                    }`}
                  >
                    推演完整梯队 (无断层)
                  </button>
                </div>

                <div className="flex items-center gap-2.5 text-xs font-mono tabular-nums">
                  <span className="text-[#9ca3af]">
                    情绪周期:{' '}
                    <strong
                      className={`font-sans ${
                        ladderSummary.ebbTideRiskLevel === 'HIGH_EBB_RISK'
                          ? 'text-[#F6465D]'
                          : ladderSummary.ebbTideRiskLevel === 'MEDIUM_FAULT_RISK'
                          ? 'text-[#F59E0B]'
                          : 'text-[#0ECB81]'
                      }`}
                    >
                      {ladderSummary.sentimentPhase}
                    </strong>
                  </span>
                  <span className="text-[#9ca3af]">
                    最高标:{' '}
                    <strong className="text-white">
                      {ladderSummary.maxBoardHeight}连板 ({ladderSummary.spaceDragonName})
                    </strong>
                  </span>
                </div>
              </div>
            </div>

            {/* 核心晋级率与空间断层五维仪表栏 */}
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 p-3 bg-[#161a24] border-b border-[#2a2e39]">
              <div className="p-2.5 rounded bg-[#1e222d] border border-[#2a2e39]">
                <div className="text-[11px] text-[#787b86] whitespace-nowrap">
                  最高空间板 vs 次高板
                </div>
                <div className="mt-1 flex items-baseline justify-between gap-1 font-mono tabular-nums whitespace-nowrap">
                  <span className="text-base font-bold text-[#F6465D]">
                    {ladderSummary.maxBoardHeight}板 / {ladderSummary.secondMaxBoardHeight}板
                  </span>
                  <span className="text-xs text-white font-sans truncate">
                    {ladderSummary.spaceDragonName}
                  </span>
                </div>
              </div>

              <div className="p-2.5 rounded bg-[#1e222d] border border-[#2a2e39]">
                <div className="text-[11px] text-[#787b86] whitespace-nowrap">
                  晋级空间断层跨度
                </div>
                <div className="mt-1 flex items-baseline justify-between gap-1 font-mono tabular-nums whitespace-nowrap">
                  <span
                    className={`text-base font-bold ${
                      ladderSummary.hasLadderFault ? 'text-[#F59E0B]' : 'text-[#0ECB81]'
                    }`}
                  >
                    {ladderSummary.hasLadderFault
                      ? `缺${ladderSummary.missingBoards.join('/')}板`
                      : '0 断层'}
                  </span>
                  <span className="text-[11px] text-[#9ca3af]">
                    {ladderSummary.maxFaultSpan > 0
                      ? `连缺${ladderSummary.maxFaultSpan}层`
                      : '阶梯完整'}
                  </span>
                </div>
              </div>

              <div className="p-2.5 rounded bg-[#1e222d] border border-[#2a2e39]">
                <div className="text-[11px] text-[#787b86] whitespace-nowrap">
                  首板晋级率 (1进2)
                </div>
                <div className="mt-1 flex items-baseline justify-between gap-1 font-mono tabular-nums whitespace-nowrap">
                  <span className="text-base font-bold text-[#F59E0B]">
                    {ladderSummary.firstToSecondRate.toFixed(1)}%
                  </span>
                  <span className="text-[11px] text-[#9ca3af]">
                    2进3 {ladderSummary.secondToThirdRate.toFixed(1)}%
                  </span>
                </div>
              </div>

              <div className="p-2.5 rounded bg-[#1e222d] border border-[#2a2e39]">
                <div className="text-[11px] text-[#787b86] whitespace-nowrap">
                  今日封板率 / 炸板
                </div>
                <div className="mt-1 flex items-baseline justify-between gap-1 font-mono tabular-nums whitespace-nowrap">
                  <span className="text-base font-bold text-[#F6465D]">
                    {ladderSummary.sealSuccessRate.toFixed(1)}%
                  </span>
                  <span className="text-[11px] text-[#0ECB81]">
                    炸板 {ladderSummary.brokenBoardCount}家
                  </span>
                </div>
              </div>

              <div className="p-2.5 rounded bg-[#1e222d] border border-[#2a2e39]">
                <div className="text-[11px] text-[#787b86] whitespace-nowrap">
                  退潮风险指数 / 跌停
                </div>
                <div className="mt-1 flex items-baseline justify-between gap-1 font-mono tabular-nums whitespace-nowrap">
                  <span
                    className={`text-base font-bold ${
                      ladderSummary.ebbTideRiskScore >= 68
                        ? 'text-[#F6465D]'
                        : ladderSummary.ebbTideRiskScore >= 40
                        ? 'text-[#F59E0B]'
                        : 'text-[#0ECB81]'
                    }`}
                  >
                    {ladderSummary.ebbTideRiskScore} / 100
                  </span>
                  <span className="text-[11px] text-[#0ECB81]">
                    跌停 {ladderSummary.limitDownCount}家
                  </span>
                </div>
              </div>
            </div>

            {/* 连板梯队断层监测 & 潜在退潮风险深度预警面板 */}
            <div
              data-testid="ladder-ebb-risk-panel"
              className={`p-3 border-b ${
                ladderSummary.ebbTideRiskLevel === 'HIGH_EBB_RISK'
                  ? 'bg-[#F6465D]/10 border-[#F6465D]/35'
                  : ladderSummary.ebbTideRiskLevel === 'MEDIUM_FAULT_RISK'
                  ? 'bg-[#F59E0B]/10 border-[#F59E0B]/35'
                  : 'bg-[#0ECB81]/10 border-[#0ECB81]/30'
              }`}
            >
              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-2 pb-2.5 border-b border-[#2a2e39]/80">
                <div className="flex items-start sm:items-center gap-2">
                  <AlertTriangle
                    className={`w-4 h-4 shrink-0 mt-0.5 sm:mt-0 ${
                      ladderSummary.ebbTideRiskLevel === 'HIGH_EBB_RISK'
                        ? 'text-[#F6465D]'
                        : ladderSummary.ebbTideRiskLevel === 'MEDIUM_FAULT_RISK'
                        ? 'text-[#F59E0B]'
                        : 'text-[#0ECB81]'
                    }`}
                  />
                  <span
                    data-testid="ladder-fault-warning"
                    className="text-xs sm:text-sm font-bold text-white leading-snug"
                  >
                    {ladderSummary.ebbTideWarningTitle}
                  </span>
                </div>

                {/* 断层区间徽章与退潮风险进度条 */}
                <div className="flex flex-wrap items-center gap-2 shrink-0">
                  {ladderSummary.faultZones.length > 0 ? (
                    ladderSummary.faultZones.map((zone) => (
                      <span
                        key={`${zone.fromBoard}-${zone.toBoard}`}
                        data-testid="ladder-fault-zone-badge"
                        className="px-2 py-0.5 rounded bg-[#F59E0B]/20 border border-[#F59E0B]/50 font-mono tabular-nums text-[11px] font-semibold text-[#F59E0B]"
                      >
                        断层带: {zone.label}
                      </span>
                    ))
                  ) : (
                    <span className="px-2 py-0.5 rounded bg-[#0ECB81]/20 border border-[#0ECB81]/40 font-mono tabular-nums text-[11px] font-semibold text-[#0ECB81]">
                      1~{ladderSummary.maxBoardHeight}板梯队连续无断层
                    </span>
                  )}

                  <div className="flex items-center gap-1.5 bg-[#131722] px-2.5 py-1 rounded border border-[#2a2e39]">
                    <span className="text-[11px] text-[#9ca3af]">退潮风险值</span>
                    <div className="w-20 h-2 bg-[#1e222d] rounded-full overflow-hidden">
                      <div
                        className={`h-full transition-all duration-200 ${
                          ladderSummary.ebbTideRiskScore >= 68
                            ? 'bg-[#F6465D]'
                            : ladderSummary.ebbTideRiskScore >= 40
                            ? 'bg-[#F59E0B]'
                            : 'bg-[#0ECB81]'
                        }`}
                        style={{ width: `${ladderSummary.ebbTideRiskScore}%` }}
                      />
                    </div>
                    <span className="font-mono tabular-nums text-xs font-bold text-white">
                      {ladderSummary.ebbTideRiskScore}分
                    </span>
                  </div>
                </div>
              </div>

              {/* 三维自动对比诊断明细 (空间断层扫描 / 晋级对比诊断 / 退潮传导推演) */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5 mt-2.5 text-xs">
                {ladderSummary.ebbTideRiskReasons.map((reason, idx) => (
                  <div
                    key={idx}
                    className="p-2 rounded bg-[#131722]/90 border border-[#2a2e39] text-[#d1d4dc] leading-relaxed"
                  >
                    {reason}
                  </div>
                ))}
              </div>

              {/* 游资退潮防守与操作预案 */}
              <div className="mt-2 flex flex-wrap items-center justify-between gap-2 px-2.5 py-1.5 rounded bg-[#131722] border border-[#2a2e39] text-xs">
                <div className="flex items-center gap-2">
                  <span className="px-1.5 py-0.5 rounded bg-[#2962ff]/20 border border-[#2962ff]/40 text-[10px] font-bold text-[#38bdf8] whitespace-nowrap">
                    游资应对铁律
                  </span>
                  <span className="text-[#d1d4dc]">{ladderSummary.tacticalPlaybook}</span>
                </div>
                <span className="font-mono tabular-nums text-[11px] text-[#9ca3af]">
                  高位晋级率(≥3进4):{' '}
                  <strong
                    className={
                      ladderSummary.highBoardPromotionRate < 25
                        ? 'text-[#0ECB81]'
                        : 'text-[#F6465D]'
                    }
                  >
                    {ladderSummary.highBoardPromotionRate.toFixed(1)}%
                  </strong>
                </span>
              </div>
            </div>

            {/* 今日涨停板分布 vs 昨日连板基数对比阶梯表 */}
            <div className="overflow-x-auto" data-testid="ladder-distribution-table">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="border-b border-[#2a2e39] text-[#787b86] bg-[#161a24] text-[11px]">
                    <th className="py-2 px-3 whitespace-nowrap">连板身位层级</th>
                    <th className="py-2 px-2.5 whitespace-nowrap">梯队接力状态</th>
                    <th className="py-2 px-2.5 text-right whitespace-nowrap">
                      昨日(N-1)板基数
                    </th>
                    <th className="py-2 px-2.5 text-right whitespace-nowrap">
                      今日封板家数
                    </th>
                    <th className="py-2 px-2.5 text-right whitespace-nowrap">
                      层间晋级率 / 淘汰数
                    </th>
                    <th className="py-2 px-3 whitespace-nowrap">
                      今日涨停 vs 昨日基数对比条
                    </th>
                    <th className="py-2 px-3 whitespace-nowrap">
                      在板核心标的 / 晋级空间断层诊断
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#2a2e39]">
                  {ladderSummary.distributionComparison.map((row) => {
                    const maxRefCount = Math.max(
                      row.yesterdayCandidateCount ?? 1,
                      row.todaySealedCount,
                      6
                    );
                    const yesterdayBarPct =
                      row.yesterdayCandidateCount !== null
                        ? Math.min(100, Math.round((row.yesterdayCandidateCount / maxRefCount) * 100))
                        : 0;
                    const todayBarPct = Math.min(
                      100,
                      Math.round((row.todaySealedCount / maxRefCount) * 100)
                    );

                    return (
                      <tr
                        key={`dist-row-${row.boardCount}`}
                        data-testid={`ladder-tier-row-${row.boardCount}`}
                        className={
                          row.isFaultLevel
                            ? 'bg-[#F59E0B]/[0.06] hover:bg-[#F59E0B]/10 transition-colors'
                            : 'hover:bg-[#262b38]/50 transition-colors'
                        }
                      >
                        {/* 1. 连板身位层级 */}
                        <td className="py-2.5 px-3 font-mono tabular-nums font-bold whitespace-nowrap">
                          <span
                            className={
                              row.isFaultLevel
                                ? 'text-[#F59E0B]'
                                : row.boardCount === ladderSummary.maxBoardHeight
                                ? 'text-[#F6465D]'
                                : 'text-white'
                            }
                          >
                            {row.label}
                          </span>
                        </td>

                        {/* 2. 梯队接力状态 */}
                        <td className="py-2.5 px-2.5 whitespace-nowrap">
                          {row.isFaultLevel ? (
                            <span className="px-2 py-0.5 rounded bg-[#F59E0B]/20 border border-[#F59E0B]/50 text-[11px] font-semibold text-[#F59E0B]">
                              晋级空间断层
                            </span>
                          ) : row.boardCount === ladderSummary.maxBoardHeight &&
                            ladderSummary.topDragonIsolation ? (
                            <span className="px-2 py-0.5 rounded bg-[#F6465D]/20 border border-[#F6465D]/50 text-[11px] font-semibold text-[#F6465D]">
                              断层之上独苗
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded bg-[#0ECB81]/15 border border-[#0ECB81]/30 text-[11px] font-medium text-[#0ECB81]">
                              梯队传导正常
                            </span>
                          )}
                        </td>

                        {/* 3. 昨日(N-1)板候选基数 */}
                        <td className="py-2.5 px-2.5 text-right font-mono tabular-nums text-[#9ca3af] whitespace-nowrap">
                          {row.yesterdayCandidateCount !== null
                            ? `昨${row.boardCount - 1}板: ${row.yesterdayCandidateCount}家`
                            : '全市场首板池'}
                        </td>

                        {/* 4. 今日封板家数 */}
                        <td className="py-2.5 px-2.5 text-right font-mono tabular-nums font-bold whitespace-nowrap">
                          <span
                            className={
                              row.isFaultLevel ? 'text-[#F59E0B]' : 'text-[#F6465D]'
                            }
                          >
                            {row.todaySealedCount} 家
                          </span>
                        </td>

                        {/* 5. 层间晋级率 / 淘汰数 */}
                        <td className="py-2.5 px-2.5 text-right font-mono tabular-nums whitespace-nowrap">
                          {row.promotionRate !== null ? (
                            <div>
                              <span
                                className={`font-bold ${
                                  row.promotionRate === 0
                                    ? 'text-[#F59E0B]'
                                    : row.promotionRate >= 30
                                    ? 'text-[#F6465D]'
                                    : 'text-white'
                                }`}
                              >
                                {row.promotionRate.toFixed(1)}%
                              </span>
                              <span className="ml-1.5 text-[10px] text-[#787b86]">
                                (淘汰{row.eliminatedCount}家)
                              </span>
                            </div>
                          ) : (
                            <span className="text-[11px] text-[#9ca3af]">首板试错发酵</span>
                          )}
                        </td>

                        {/* 6. 今日涨停 vs 昨日基数对比条 */}
                        <td className="py-2.5 px-2.5 w-28 whitespace-nowrap">
                          <div className="space-y-1 w-24">
                            {row.yesterdayCandidateCount !== null && (
                              <div className="flex items-center gap-1">
                                <span className="text-[10px] font-mono tabular-nums text-[#787b86] w-7">
                                  昨基
                                </span>
                                <div className="flex-1 h-1.5 bg-[#131722] rounded overflow-hidden">
                                  <div
                                    className="h-full bg-[#787b86]/60"
                                    style={{ width: `${yesterdayBarPct}%` }}
                                  />
                                </div>
                              </div>
                            )}
                            <div className="flex items-center gap-1">
                              <span className="text-[10px] font-mono tabular-nums text-[#9ca3af] w-7">
                                今封
                              </span>
                              <div className="flex-1 h-1.5 bg-[#131722] rounded overflow-hidden">
                                <div
                                  className={`h-full ${
                                    row.isFaultLevel ? 'bg-[#F59E0B]' : 'bg-[#F6465D]'
                                  }`}
                                  style={{
                                    width: `${row.isFaultLevel ? 0 : Math.max(todayBarPct, 8)}%`,
                                  }}
                                />
                              </div>
                            </div>
                          </div>
                        </td>

                        {/* 7. 在板核心标的 / 晋级空间断层诊断 */}
                        <td className="py-2.5 px-3 min-w-[280px]">
                          {row.isFaultLevel ? (
                            <div className="flex items-center gap-2 text-xs text-[#F59E0B] whitespace-nowrap">
                              <span className="font-semibold">
                                断层真空区：昨 {row.yesterdayCandidateCount ?? 0} 家{' '}
                                {row.boardCount - 1}板今日晋级 {row.boardCount}板 全部失败
                              </span>
                              <span className="text-[11px] text-[#9ca3af]">
                                (警惕高位补跌退潮)
                              </span>
                            </div>
                          ) : (
                            <div className="flex flex-wrap items-center gap-1.5">
                              {row.stocks.map((st) => (
                                <button
                                  key={st.symbol}
                                  type="button"
                                  onClick={() => setSelectedSymbol(st.symbol)}
                                  className="flex items-center gap-1.5 px-2 py-1 rounded bg-[#131722] hover:bg-[#2962ff]/20 border border-[#2a2e39] text-xs transition-colors cursor-pointer whitespace-nowrap"
                                >
                                  <span className="font-bold text-white">{st.name}</span>
                                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-[#F6465D]/15 text-[#F6465D] font-medium">
                                    {st.sector}
                                  </span>
                                  <span className="font-mono tabular-nums text-[11px] text-[#9ca3af]">
                                    封板 {st.firstSealTime}
                                  </span>
                                  <span className="font-mono tabular-nums text-[11px] text-[#F59E0B]">
                                    封单 {formatAmountCN(st.sealOrderAmount)}
                                  </span>
                                </button>
                              ))}
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* ==================== 模块三：板块/题材共振监测与主流资金进攻方向雷达 ==================== */}
        {(quantModuleTab === 'overview' || quantModuleTab === 'resonance') && (
          <ThemeResonanceMonitorPanel
            overview={themeResonanceOverview}
            scenario={themeScenario}
            onChangeScenario={setThemeScenario}
            selectedSymbol={selectedSymbol}
            onSelectSymbol={setSelectedSymbol}
            compact={compact}
          />
        )}

        {/* ==================== 模块四：监管异动监测 (2/3日涨跌幅实时监控、法定异动窗口与红黄灯特停预警) ==================== */}
        {(quantModuleTab === 'overview' || quantModuleTab === 'regulatory') &&
          activeRegDeviation && (
            <RegulatoryMonitorPanel
              overview={regulatoryOverview}
              activeRegDeviation={activeRegDeviation}
              selectedSymbol={selectedSymbol}
              onSelectSymbol={setSelectedSymbol}
              simulatedIndexPct={simulatedIndexPct}
              defaultIndexPct={activeQuote?.ultraShort?.indexReturnToday ?? 1.05}
              onChangeSimulatedIndexPct={setSimulatedIndexPct}
            />
          )}

        {/* ==================== 模块五：真实成交量加权承接算子 (VW-DVR) ==================== */}
        {(quantModuleTab === 'overview' || quantModuleTab === 'vwdvr') &&
          activeVWDVR && (
            <section
              aria-label="真实成交量加权承接算子 VW-DVR"
              className="bg-[#1e222d] border border-[#2a2e39] rounded-md overflow-hidden"
            >
              <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 bg-[#131722] border-b border-[#2a2e39]">
                <div className="flex items-center gap-2">
                  <Activity className="w-4 h-4 text-[#0ECB81]" />
                  <h2 className="text-xs sm:text-sm font-bold text-white">
                    真实成交量加权承接算子 (VW-DVR = 0.42·η_vwap + 0.35·α_dip + 0.23·β_shadow)
                  </h2>
                </div>
                <span className="text-[11px] font-mono tabular-nums text-[#9ca3af]">
                  当前选中：{activeVWDVR.name} ({activeVWDVR.symbol}) · VW-DVR 得分{' '}
                  <strong className="text-white">{activeVWDVR.vwDvrScore}</strong>
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-2.5 p-3 bg-[#161a24] border-b border-[#2a2e39] text-xs">
                <div className="p-2.5 rounded bg-[#1e222d] border border-[#2a2e39]">
                  <div className="text-[11px] text-[#787b86]">
                    水上筹码锚定率 (η_vwap · 权重42%)
                  </div>
                  <div className="mt-1 flex items-baseline justify-between font-mono tabular-nums">
                    <span className="text-lg font-bold text-[#F6465D]">
                      {activeVWDVR.aboveVwapVolumeRatio.toFixed(1)}%
                    </span>
                    <span className="text-[11px] text-[#9ca3af]">
                      VWAP {formatPrice(activeVWDVR.vwap)}
                    </span>
                  </div>
                </div>

                <div className="p-2.5 rounded bg-[#1e222d] border border-[#2a2e39]">
                  <div className="text-[11px] text-[#787b86]">
                    分时回撤买盘吸收率 (α_dip · 权重35%)
                  </div>
                  <div className="mt-1 flex items-baseline justify-between font-mono tabular-nums">
                    <span className="text-lg font-bold text-[#F59E0B]">
                      {activeVWDVR.dipBuyAbsorptionRatio.toFixed(1)}%
                    </span>
                    <span className="text-[11px] text-[#9ca3af]">回踩外盘吞噬度</span>
                  </div>
                </div>

                <div className="p-2.5 rounded bg-[#1e222d] border border-[#2a2e39]">
                  <div className="text-[11px] text-[#787b86]">
                    下影线探底韧性 (β_shadow · 权重23%)
                  </div>
                  <div className="mt-1 flex items-baseline justify-between font-mono tabular-nums">
                    <span className="text-lg font-bold text-[#38bdf8]">
                      {activeVWDVR.lowerShadowResilience.toFixed(1)}%
                    </span>
                    <span className="text-[11px] text-[#9ca3af]">
                      均价乖离 {formatSignedPercent(activeVWDVR.priceToVwapDiffPercent)}
                    </span>
                  </div>
                </div>

                <div className="p-2.5 rounded bg-[#1e222d] border border-[#2a2e39]">
                  <div className="text-[11px] text-[#787b86]">VW-DVR 综合承接定性</div>
                  <div className="mt-1 flex items-baseline justify-between">
                    <span
                      className={`font-mono tabular-nums text-lg font-bold ${
                        activeVWDVR.vwDvrScore >= 74
                          ? 'text-[#F6465D]'
                          : activeVWDVR.vwDvrScore >= 48
                          ? 'text-[#F59E0B]'
                          : 'text-[#0ECB81]'
                      }`}
                    >
                      {activeVWDVR.vwDvrScore}分
                    </span>
                    <span className="text-xs font-semibold text-white">
                      {activeVWDVR.signalLabel}
                    </span>
                  </div>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="border-b border-[#2a2e39] text-[#787b86] bg-[#161a24] text-[11px]">
                      <th className="py-2 px-3 whitespace-nowrap">股票标的</th>
                      <th className="py-2 px-2.5 text-right whitespace-nowrap">日内均价 (VWAP)</th>
                      <th className="py-2 px-2.5 text-right whitespace-nowrap">VWAP乖离率</th>
                      <th className="py-2 px-2.5 text-right whitespace-nowrap">
                        水上筹码比 η_vwap
                      </th>
                      <th className="py-2 px-2.5 text-right whitespace-nowrap">
                        回撤买盘吸收 α_dip
                      </th>
                      <th className="py-2 px-2.5 text-right whitespace-nowrap">
                        下影线韧性 β_shadow
                      </th>
                      <th className="py-2 px-2.5 text-right whitespace-nowrap">VW-DVR 得分</th>
                      <th className="py-2 px-2.5 whitespace-nowrap">承接状态定性</th>
                      <th className="py-2 px-3 whitespace-nowrap">超短分时应对策略</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#2a2e39]/60">
                    {allVWDVRList.map((item) => (
                      <tr
                        key={item.symbol}
                        onClick={() => setSelectedSymbol(item.symbol)}
                        className={`cursor-pointer transition-colors ${
                          item.symbol === selectedSymbol
                            ? 'bg-[#2962ff]/15'
                            : 'hover:bg-[#262b38]'
                        }`}
                      >
                        <td className="py-2 px-3 whitespace-nowrap">
                          <span className="font-semibold text-white">{item.name}</span>
                          <span className="ml-1.5 font-mono tabular-nums text-[10px] text-[#787b86]">
                            {item.symbol}
                          </span>
                        </td>
                        <td className="py-2 px-2.5 text-right font-mono tabular-nums text-[#F59E0B] whitespace-nowrap">
                          {formatPrice(item.vwap)}
                        </td>
                        <td
                          className={`py-2 px-2.5 text-right font-mono tabular-nums font-semibold whitespace-nowrap ${getSignedColorClass(
                            item.priceToVwapDiffPercent
                          )}`}
                        >
                          {formatSignedPercent(item.priceToVwapDiffPercent)}
                        </td>
                        <td className="py-2 px-2.5 text-right font-mono tabular-nums text-white whitespace-nowrap">
                          {item.aboveVwapVolumeRatio.toFixed(1)}%
                        </td>
                        <td className="py-2 px-2.5 text-right font-mono tabular-nums text-white whitespace-nowrap">
                          {item.dipBuyAbsorptionRatio.toFixed(1)}%
                        </td>
                        <td className="py-2 px-2.5 text-right font-mono tabular-nums text-white whitespace-nowrap">
                          {item.lowerShadowResilience.toFixed(1)}%
                        </td>
                        <td className="py-2 px-2.5 text-right font-mono tabular-nums font-bold text-[#F6465D] whitespace-nowrap">
                          {item.vwDvrScore.toFixed(1)}
                        </td>
                        <td className="py-2 px-2.5 whitespace-nowrap">
                          <span
                            className={`px-2 py-0.5 rounded text-[11px] font-semibold ${
                              item.signal === 'STRONG_ABSORPTION'
                                ? 'bg-[#F6465D]/20 text-[#F6465D]'
                                : item.signal === 'HEALTHY_TURNOVER'
                                ? 'bg-[#F59E0B]/20 text-[#F59E0B]'
                                : 'bg-[#0ECB81]/20 text-[#0ECB81]'
                            }`}
                          >
                            {item.signalLabel}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-[11px] text-[#9ca3af] max-w-xs truncate">
                          {item.actionAdvice}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

        {/* ==================== 模块六：龙虎榜席位性质分析 (游资常用席位 / 机构专用 / 量化大本营) ==================== */}
        {(quantModuleTab === 'overview' || quantModuleTab === 'dragon_tiger') &&
          activeDragonTiger && (
            <section
              aria-label="龙虎榜席位性质分析"
              data-testid="dragon-tiger-section"
              className="bg-[#1e222d] border border-[#2a2e39] rounded-md overflow-hidden"
            >
              {/* 顶部标题栏 + 席位结构沙盘推演切换 */}
              <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 bg-[#131722] border-b border-[#2a2e39]">
                <div className="flex items-center gap-2">
                  <Building2 className="w-4 h-4 text-[#F6465D]" />
                  <h2 className="text-xs sm:text-sm font-bold text-white">
                    龙虎榜席位性质解析引擎 (自动识别游资常用席位 / 机构专用 / 量化大本营 / 散户合力)
                  </h2>
                  <span className="px-1.5 py-0.5 rounded bg-[#F6465D]/15 border border-[#F6465D]/40 font-mono tabular-nums text-[10px] font-bold text-[#F6465D]">
                    {activeDragonTiger.boardType === '3D' ? '连续3日榜' : '当日龙虎榜'}
                  </span>
                </div>

                {/* 席位结构沙盘推演切换按钮组 */}
                <div
                  role="group"
                  aria-label="龙虎榜席位结构推演模式"
                  className="flex items-center bg-[#1e222d] p-0.5 rounded border border-[#2a2e39] text-[11px]"
                >
                  <button
                    type="button"
                    data-testid="dt-preset-live"
                    onClick={() => setDragonTigerPreset('live')}
                    className={`px-2 py-0.5 rounded transition-colors cursor-pointer whitespace-nowrap ${
                      dragonTigerPreset === 'live'
                        ? 'bg-[#2962ff] text-white font-semibold'
                        : 'text-[#9ca3af] hover:text-white'
                    }`}
                  >
                    实盘龙虎榜解析
                  </button>
                  <button
                    type="button"
                    data-testid="dt-preset-resonance"
                    onClick={() => setDragonTigerPreset('hot_inst_resonance')}
                    className={`px-2 py-0.5 rounded transition-colors cursor-pointer whitespace-nowrap ${
                      dragonTigerPreset === 'hot_inst_resonance'
                        ? 'bg-[#F6465D] text-white font-semibold'
                        : 'text-[#9ca3af] hover:text-white'
                    }`}
                  >
                    游资+机构共振
                  </button>
                  <button
                    type="button"
                    data-testid="dt-preset-quant"
                    onClick={() => setDragonTigerPreset('quant_crowded')}
                    className={`px-2 py-0.5 rounded transition-colors cursor-pointer whitespace-nowrap ${
                      dragonTigerPreset === 'quant_crowded'
                        ? 'bg-[#a855f7] text-white font-semibold'
                        : 'text-[#9ca3af] hover:text-white'
                    }`}
                  >
                    量化大本营扎堆
                  </button>
                  <button
                    type="button"
                    data-testid="dt-preset-retail"
                    onClick={() => setDragonTigerPreset('retail_takeover')}
                    className={`px-2 py-0.5 rounded transition-colors cursor-pointer whitespace-nowrap ${
                      dragonTigerPreset === 'retail_takeover'
                        ? 'bg-[#F59E0B] text-[#0d0e12] font-semibold'
                        : 'text-[#9ca3af] hover:text-white'
                    }`}
                  >
                    拉萨散户接盘
                  </button>
                </div>
              </div>

              {/* 快捷焦点上榜个股切换条 + 当前标的上榜原因 */}
              <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 bg-[#161a24] border-b border-[#2a2e39] text-xs">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[11px] text-[#787b86] mr-1">焦点龙虎榜标的:</span>
                  {['601360.SH', '002230.SZ', '300059.SZ', '688981.SH', '000651.SZ', '300750.SZ'].map(
                    (sym) => {
                      const q = quotes[sym];
                      if (!q) return null;
                      const isCurrent = selectedSymbol === sym;
                      return (
                        <button
                          key={sym}
                          type="button"
                          data-testid={`dt-stock-pill-${q.code}`}
                          onClick={() => setSelectedSymbol(sym)}
                          className={`flex items-center gap-1 px-2 py-0.5 rounded border text-[11px] transition-colors cursor-pointer whitespace-nowrap ${
                            isCurrent
                              ? 'bg-[#2962ff]/25 border-[#2962ff] text-white font-bold'
                              : 'bg-[#131722] border-[#2a2e39] text-[#9ca3af] hover:text-white'
                          }`}
                        >
                          <span>{q.name}</span>
                          <span
                            className={`font-mono tabular-nums ${getSignedColorClass(
                              q.changePercent
                            )}`}
                          >
                            {formatSignedPercent(q.changePercent)}
                          </span>
                        </button>
                      );
                    }
                  )}
                </div>

                <div className="flex items-center gap-2 font-mono tabular-nums text-[11px] text-[#9ca3af]">
                  <span>
                    当前解析:{' '}
                    <strong className="text-white font-sans">
                      {activeDragonTiger.name} ({activeDragonTiger.symbol})
                    </strong>
                  </span>
                  <span className="text-[#2a2e39]">|</span>
                  <span className="text-[#F59E0B] font-sans">
                    上榜原因: {activeDragonTiger.listingReason}
                  </span>
                </div>
              </div>

              {/* D3.js 游资大佬营业部关联网络图 & 点击节点席位活跃度画像 */}
              <DragonTigerNetworkGraph
                analysis={activeDragonTiger}
                onSelectSymbol={setSelectedSymbol}
              />

              {/* 四大席位性质（游资常用席位 / 机构专用 / 量化大本营 / 散户大本营）资金力量汇总卡片 */}
              <div
                data-testid="dragon-tiger-nature-summary"
                className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5 p-3 bg-[#161a24] border-b border-[#2a2e39]"
              >
                {activeDragonTiger.campBreakdown.map((camp) => {
                  const netColor =
                    camp.netAmount > 0
                      ? 'text-[#F6465D]'
                      : camp.netAmount < 0
                      ? 'text-[#0ECB81]'
                      : 'text-[#9ca3af]';
                  return (
                    <div
                      key={camp.nature}
                      data-testid={`dt-camp-card-${camp.nature}`}
                      className="p-2.5 rounded bg-[#1e222d] border border-[#2a2e39] flex flex-col justify-between min-w-0"
                    >
                      <div className="flex items-center justify-between gap-1">
                        <span
                          className={`px-1.5 py-0.5 rounded border text-[11px] font-bold whitespace-nowrap ${getSeatNatureBadgeClass(
                            camp.nature
                          )}`}
                        >
                          {camp.label}
                        </span>
                        <span className="font-mono tabular-nums text-[10px] text-[#9ca3af] whitespace-nowrap">
                          <strong className="text-white">{camp.seatCount}</strong>席 · 买占
                          <strong className="text-white">{camp.buySharePercent}%</strong>
                        </span>
                      </div>

                      <div className="mt-2 flex items-baseline justify-between font-mono tabular-nums whitespace-nowrap">
                        <span className="text-[11px] text-[#787b86]">阵营净额:</span>
                        <span className={`text-base font-bold ${netColor}`}>
                          {camp.netAmount > 0 ? '+' : camp.netAmount < 0 ? '-' : ''}
                          {formatAmountCN(Math.abs(camp.netAmount))}
                        </span>
                      </div>

                      <div className="mt-1 flex items-center justify-between text-[11px] font-mono tabular-nums text-[#9ca3af] whitespace-nowrap">
                        <span>
                          买: <strong className="text-[#F6465D]">{formatAmountCN(camp.buyAmount)}</strong>
                        </span>
                        <span>
                          卖: <strong className="text-[#0ECB81]">{formatAmountCN(camp.sellAmount)}</strong>
                        </span>
                      </div>

                      <div className="mt-1.5 pt-1.5 border-t border-[#2a2e39]/70 text-[11px] text-[#787b86] truncate">
                        {camp.representativeTags.length > 0
                          ? `代表: ${camp.representativeTags.join(' / ')}`
                          : '当日无该性质席位上榜'}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* 席位协同定性与次日竞价博弈结论横幅 */}
              <div
                data-testid="dragon-tiger-verdict-banner"
                className="p-3 bg-[#131722] border-b border-[#2a2e39] flex flex-col lg:flex-row lg:items-center justify-between gap-3"
              >
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      data-testid="dragon-tiger-synergy-label"
                      className={`px-2 py-0.5 rounded text-xs font-bold border ${
                        activeDragonTiger.synergyVerdict === 'HOT_INST_RESONANCE' ||
                        activeDragonTiger.synergyVerdict === 'TOP_HOT_LOCK'
                          ? 'bg-[#F6465D]/20 text-[#F6465D] border-[#F6465D]/50'
                          : activeDragonTiger.synergyVerdict === 'QUANT_CROWDED_RISK'
                          ? 'bg-[#a855f7]/20 text-[#c084fc] border-[#a855f7]/50'
                          : 'bg-[#0ECB81]/20 text-[#0ECB81] border-[#0ECB81]/50'
                      }`}
                    >
                      {activeDragonTiger.synergyLabel}
                    </span>
                    <span className="text-xs font-mono tabular-nums text-[#d1d4dc]">
                      前五买合计:{' '}
                      <strong className="text-[#F6465D]">
                        {formatAmountCN(activeDragonTiger.totalBuyAmount)}
                      </strong>{' '}
                      ({activeDragonTiger.buyTurnoverRatioPercent}%)
                    </span>
                    <span className="text-[#2a2e39]">|</span>
                    <span className="text-xs font-mono tabular-nums text-[#d1d4dc]">
                      前五卖合计:{' '}
                      <strong className="text-[#0ECB81]">
                        {formatAmountCN(activeDragonTiger.totalSellAmount)}
                      </strong>{' '}
                      ({activeDragonTiger.sellTurnoverRatioPercent}%)
                    </span>
                    <span className="text-[#2a2e39]">|</span>
                    <span className="text-xs font-mono tabular-nums">
                      龙虎榜净额:{' '}
                      <strong
                        className={
                          activeDragonTiger.totalNetAmount >= 0
                            ? 'text-[#F6465D]'
                            : 'text-[#0ECB81]'
                        }
                      >
                        {activeDragonTiger.totalNetAmount >= 0 ? '+' : '-'}
                        {formatAmountCN(Math.abs(activeDragonTiger.totalNetAmount))} (
                        {formatSignedPercent(activeDragonTiger.netTurnoverRatioPercent)})
                      </strong>
                    </span>
                  </div>
                  <p className="text-xs text-[#9ca3af] leading-relaxed">
                    <strong className="text-[#38bdf8]">次日博弈预案：</strong>
                    {activeDragonTiger.actionablePlaybook}
                  </p>
                </div>

                <div className="flex items-center gap-2 bg-[#1e222d] px-3 py-2 rounded border border-[#2a2e39] shrink-0">
                  <div className="text-right">
                    <div className="text-[10px] text-[#787b86]">次日溢价预期指数</div>
                    <div
                      className={`font-mono tabular-nums text-base font-bold ${
                        activeDragonTiger.nextDayPremiumScore >= 75
                          ? 'text-[#F6465D]'
                          : activeDragonTiger.nextDayPremiumScore >= 45
                          ? 'text-[#F59E0B]'
                          : 'text-[#0ECB81]'
                      }`}
                    >
                      {activeDragonTiger.nextDayPremiumScore} / 100
                    </div>
                  </div>
                </div>
              </div>

              {/* 买入前五营业部 vs 卖出前五营业部 全宽深度解析表 */}
              <div className="grid grid-cols-1 divide-y divide-[#2a2e39]">
                {/* 上表：买入金额前五名营业部 */}
                <div data-testid="dragon-tiger-buy-table" className="overflow-x-auto">
                  <div className="px-3 py-2 bg-[#F6465D]/10 border-b border-[#2a2e39] flex items-center justify-between text-xs">
                    <span className="font-bold text-[#F6465D]">
                      买入金额最大的前 5 名营业部 (主封与锁仓力量)
                    </span>
                    <span className="font-mono tabular-nums text-[11px] text-[#9ca3af]">
                      前五买合计 {formatAmountCN(activeDragonTiger.totalBuyAmount)} · 占总成交{' '}
                      {activeDragonTiger.buyTurnoverRatioPercent}%
                    </span>
                  </div>
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="border-b border-[#2a2e39] text-[#787b86] bg-[#161a24] text-[11px]">
                        <th className="py-2 px-3 whitespace-nowrap">席位</th>
                        <th className="py-2 px-3 whitespace-nowrap">营业部名称 & 游资/机构操盘特征</th>
                        <th className="py-2 px-2.5 whitespace-nowrap">席位性质识别</th>
                        <th className="py-2 px-2.5 text-right whitespace-nowrap">买入金额</th>
                        <th className="py-2 px-2.5 text-right whitespace-nowrap">卖出金额</th>
                        <th className="py-2 px-3 text-right whitespace-nowrap">席位净额 / 占总成交比</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#2a2e39]/60">
                      {activeDragonTiger.buySeats.map((seat) => (
                        <tr key={`buy-${seat.rank}`} className="hover:bg-[#262b38]/60">
                          <td className="py-2 px-3 font-mono tabular-nums font-bold text-[#F6465D] whitespace-nowrap">
                            买{seat.rank}
                          </td>
                          <td className="py-2 px-3">
                            <div className="font-semibold text-white">{seat.branchName}</div>
                            <div className="text-[11px] text-[#9ca3af] mt-0.5">
                              <span className="text-[#F59E0B] font-medium">{seat.seatTag}</span> ·{' '}
                              <span>{seat.operatingStyle}</span>
                            </div>
                          </td>
                          <td className="py-2 px-2.5 whitespace-nowrap">
                            <span
                              className={`px-2 py-0.5 rounded border text-[11px] font-semibold ${getSeatNatureBadgeClass(
                                seat.nature
                              )}`}
                            >
                              {seat.natureLabel}
                            </span>
                          </td>
                          <td className="py-2 px-2.5 text-right font-mono tabular-nums font-semibold text-[#F6465D] whitespace-nowrap">
                            {formatAmountCN(seat.buyAmount)}
                          </td>
                          <td className="py-2 px-2.5 text-right font-mono tabular-nums text-[#0ECB81] whitespace-nowrap">
                            {formatAmountCN(seat.sellAmount)}
                          </td>
                          <td className="py-2 px-3 text-right font-mono tabular-nums whitespace-nowrap">
                            <span className="font-bold text-[#F6465D]">
                              +{formatAmountCN(seat.netAmount)}
                            </span>
                            <span className="ml-1.5 text-[11px] text-[#787b86]">
                              ({seat.turnoverSharePercent}%)
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* 下表：卖出金额前五名营业部 */}
                <div data-testid="dragon-tiger-sell-table" className="overflow-x-auto">
                  <div className="px-3 py-2 bg-[#0ECB81]/10 border-b border-[#2a2e39] flex items-center justify-between text-xs">
                    <span className="font-bold text-[#0ECB81]">
                      卖出金额最大的前 5 名营业部 (兑现与抛压来源)
                    </span>
                    <span className="font-mono tabular-nums text-[11px] text-[#9ca3af]">
                      前五卖合计 {formatAmountCN(activeDragonTiger.totalSellAmount)} · 占总成交{' '}
                      {activeDragonTiger.sellTurnoverRatioPercent}%
                    </span>
                  </div>
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="border-b border-[#2a2e39] text-[#787b86] bg-[#161a24] text-[11px]">
                        <th className="py-2 px-3 whitespace-nowrap">席位</th>
                        <th className="py-2 px-3 whitespace-nowrap">营业部名称 & 游资/机构操盘特征</th>
                        <th className="py-2 px-2.5 whitespace-nowrap">席位性质识别</th>
                        <th className="py-2 px-2.5 text-right whitespace-nowrap">买入金额</th>
                        <th className="py-2 px-2.5 text-right whitespace-nowrap">卖出金额</th>
                        <th className="py-2 px-3 text-right whitespace-nowrap">席位净额 / 占总成交比</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#2a2e39]/60">
                      {activeDragonTiger.sellSeats.map((seat) => (
                        <tr key={`sell-${seat.rank}`} className="hover:bg-[#262b38]/60">
                          <td className="py-2 px-3 font-mono tabular-nums font-bold text-[#0ECB81] whitespace-nowrap">
                            卖{seat.rank}
                          </td>
                          <td className="py-2 px-3">
                            <div className="font-semibold text-white">{seat.branchName}</div>
                            <div className="text-[11px] text-[#9ca3af] mt-0.5">
                              <span className="text-[#38bdf8] font-medium">{seat.seatTag}</span> ·{' '}
                              <span>{seat.operatingStyle}</span>
                            </div>
                          </td>
                          <td className="py-2 px-2.5 whitespace-nowrap">
                            <span
                              className={`px-2 py-0.5 rounded border text-[11px] font-semibold ${getSeatNatureBadgeClass(
                                seat.nature
                              )}`}
                            >
                              {seat.natureLabel}
                            </span>
                          </td>
                          <td className="py-2 px-2.5 text-right font-mono tabular-nums text-[#F6465D] whitespace-nowrap">
                            {formatAmountCN(seat.buyAmount)}
                          </td>
                          <td className="py-2 px-2.5 text-right font-mono tabular-nums font-semibold text-[#0ECB81] whitespace-nowrap">
                            {formatAmountCN(seat.sellAmount)}
                          </td>
                          <td className="py-2 px-3 text-right font-mono tabular-nums whitespace-nowrap">
                            <span className="font-bold text-[#0ECB81]">
                              -{formatAmountCN(Math.abs(seat.netAmount))}
                            </span>
                            <span className="ml-1.5 text-[11px] text-[#787b86]">
                              ({seat.turnoverSharePercent}%)
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>
          )}
      </div>
    </div>
  );
};
