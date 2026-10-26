import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  ArrowUpRight,
  BarChart2,
  Flame,
  Radar,
  RotateCcw,
  Scale,
  SlidersHorizontal,
  Zap,
} from 'lucide-react';
import { useMarketStore } from '../store/useMarketStore';
import type { AuctionSignalType, BoardLadderSummary, FullMarketScanItem, FullScanSignalType } from '../types/market';
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

function getFullScanSignalStyle(signal: FullScanSignalType): {
  badge: string;
  label: string;
  color: string;
} {
  switch (signal) {
    case 'SUPER_GRAB':
      return {
        badge: 'bg-[#F6465D]/20 text-[#F6465D] border-[#F6465D]/50',
        label: '超预期抢筹',
        color: '#F6465D',
      };
    case 'NUCLEAR_BUTTON':
      return {
        badge: 'bg-[#0ECB81]/20 text-[#0ECB81] border-[#0ECB81]/50',
        label: '竞价核按钮',
        color: '#0ECB81',
      };
    case 'LOCKED_LIMIT_UP':
      return {
        badge: 'bg-[#F6465D] text-white border-[#F6465D]',
        label: '一字封单',
        color: '#C0392B',
      };
    case 'FAKE_HIGH':
      return {
        badge: 'bg-[#a855f7]/20 text-[#c084fc] border-[#a855f7]/50',
        label: '缩量假高开',
        color: '#a855f7',
      };
  }
}

/**
 * 100% 满屏独立视图：【09:25 集合竞价雷达】
 * 彻底解耦原上下硬拼堆叠，纵向 100% 占满主工作区：
 * 1. 顶部信号过滤与焦点异动标的一键联动条
 * 2. 当前焦点标的 09:25 竞价三维深度归因卡片 + 交互式信号推演沙盘
 * 3. 下半屏自适应撑满：全市场 09:25 竞价异动高密度矩阵（支持点击任意股票秒切回主图或联动盘口）
 */
export const CallAuctionRadarPlugin: React.FC = () => {
  const quotes = useMarketStore((s) => s.quotes);
  const symbolOrder = useMarketStore((s) => s.symbolOrder);
  const selectedSymbol = useMarketStore((s) => s.selectedSymbol);
  const selectAndSubscribeStock = useMarketStore((s) => s.selectAndSubscribeStock);
  const openQuantModule = useMarketStore((s) => s.openQuantModule);
  const setWorkspaceMode = useMarketStore((s) => s.setWorkspaceMode);
  const intradayPointsMap = useMarketStore((s) => s.intradayPointsMap);

  const [isSimOpen, setIsSimOpen] = useState(false);
  const [signalFilter, setSignalFilter] = useState<'ALL' | AuctionSignalType>('ALL');
  const [overrideMap, setOverrideMap] = useState<Record<string, AuctionRadarOverride>>({});
  const [serverRadarData, setServerRadarData] = useState<any | null>(null);
  const [realLadder, setRealLadder] = useState<BoardLadderSummary | null>(null);

  // Tab 切换：接力雷达 vs 全市场竞价扫描
  const [activeTab, setActiveTab] = useState<'radar' | 'fullscan'>('radar');

  // 全市场竞价扫描数据
  const fullMarketScanData = useMarketStore((s) => s.fullMarketScanData);
  const fetchFullMarketScan = useMarketStore((s) => s.fetchFullMarketScan);

  // 信号分组折叠状态
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});

  // 全市场扫描 Tab 虚拟滚动状态（独立于接力雷达的滚动状态）
  const FULLSCAN_ROW_HEIGHT = 40;
  const FULLSCAN_BUFFER_ROWS = 6;
  const fullscanScrollRef = useRef<HTMLDivElement>(null);
  const [fullscanScrollTop, setFullscanScrollTop] = useState(0);
  const [fullscanViewportHeight, setFullscanViewportHeight] = useState(400);

  const handleFullscanScroll = useCallback(() => {
    const el = fullscanScrollRef.current;
    if (el) {
      setFullscanScrollTop(el.scrollTop);
      setFullscanViewportHeight(el.clientHeight);
    }
  }, []);

  // 初始化全市场扫描视口高度
  useEffect(() => {
    const el = fullscanScrollRef.current;
    if (el) setFullscanViewportHeight(el.clientHeight);
  }, [activeTab]);

  // 全市场扫描 5 秒轮询（仅在 Tab 激活时发起）
  useEffect(() => {
    if (activeTab !== 'fullscan') return;
    fetchFullMarketScan();
    const interval = setInterval(fetchFullMarketScan, 5000);
    return () => clearInterval(interval);
  }, [activeTab, fetchFullMarketScan]);

  // 虚拟滚动状态
  const ROW_HEIGHT = 44; // 每行估算高度（py-2 16px + 内容约28px）
  const BUFFER_ROWS = 6; // 上下缓冲行数
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(400);

  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current;
    if (el) {
      setScrollTop(el.scrollTop);
      setViewportHeight(el.clientHeight);
    }
  }, []);

  // 初始化视口高度
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (el) setViewportHeight(el.clientHeight);
  }, []);

  // 异步获取后端真实全市场连板梯队 (/api/quant/ladder)
  // 为什么必须取全市场：本地 calculateBoardLadderSummary(allQuotes) 只扫自选股，
  // 自选里没有涨停股时最高连板恒为 0（"连板梯队: 最高 0连板"就是这么来的）。
  useEffect(() => {
    let isMounted = true;
    fetch('/api/quant/ladder')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (isMounted && data && data.status === 'ok') {
          setRealLadder(data as unknown as BoardLadderSummary);
        }
      })
      .catch((e) => {
        console.error('[CallAuctionRadarPlugin] 获取连板梯队数据失败:', e);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  // 异步获取后端真实全市场 09:25 竞价雷达 (/api/quant/auction_radar)
  useEffect(() => {
    let isMounted = true;
    fetch('/api/quant/auction_radar')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (isMounted && data && data.status === 'ok') {
          setServerRadarData(data);
        }
      })
      .catch((e) => {
        console.error('[CallAuctionRadarPlugin] 获取竞价雷达数据失败:', e);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  const activeQuote = quotes[selectedSymbol];
  const currentOverride = overrideMap[selectedSymbol];

  const allQuotes = useMemo(
    () => symbolOrder.map((sym) => quotes[sym]).filter(Boolean),
    [quotes, symbolOrder]
  );

  // 全市场 09:25 竞价雷达扫描结果 (优先真实全市场引擎)
  const allRadarMetrics = useMemo(() => {
    if (
      serverRadarData &&
      Array.isArray(serverRadarData.radar_items) &&
      serverRadarData.radar_items.length > 0
    ) {
      return serverRadarData.radar_items;
    }
    return allQuotes
      .map((q) => calculateAuctionRadar(q, overrideMap[q.symbol]))
      .sort((a, b) => b.amountToYesterdayRatio - a.amountToYesterdayRatio);
  }, [serverRadarData, allQuotes, overrideMap]);

  const filteredRadarMetrics = useMemo(() => {
    if (signalFilter === 'ALL') return allRadarMetrics;
    return allRadarMetrics.filter((item: any) => item.signal === signalFilter);
  }, [allRadarMetrics, signalFilter]);

  // 统计全市场竞价信号分布与异动焦点股
  const radarSummary = useMemo(() => {
    if (serverRadarData && serverRadarData.status === 'ok') {
      return {
        grabCount: serverRadarData.grabCount ?? 0,
        nuclearCount: serverRadarData.nuclearCount ?? 0,
        weakToStrongCount: serverRadarData.weakToStrongCount ?? 0,
        dumpCount: serverRadarData.dumpCount ?? 0,
        highlightStocks: serverRadarData.highlightStocks ?? [],
      };
    }
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

    const highlightStocks = allRadarMetrics.filter((m: any) => m.signal !== 'NORMAL').slice(0, 6);

    return {
      grabCount,
      nuclearCount,
      weakToStrongCount,
      dumpCount,
      highlightStocks,
    };
  }, [serverRadarData, allRadarMetrics]);

  // 当前选中股票的 09:25 竞价雷达指标 + 量比耦合分析 + 超短辅助指标
  const activeAnalysis = useMemo(() => {
    if (!activeQuote) return null;
    const radarFallback = calculateAuctionRadar(activeQuote, currentOverride);
    // 优先用后端真实全市场雷达里这只票的结果：本地 calculateAuctionRadar 拿不到真实
    // 竞价成交额/未匹配手数，只能按"昨日成交额 × 6.5%"这类系数估算，金额与占昨比都不可信。
    // 只有在用户手动做沙盘推演（override）时才退回本地计算。
    const serverItem = currentOverride
      ? null
      : ((serverRadarData?.radar_items as any[] | undefined) || []).find(
          (it) => it.symbol === activeQuote.symbol
        );
    const radar = (serverItem as typeof radarFallback | undefined) ?? radarFallback;
    const volAnalysis = analyzeAuctionVolumeRatio(
      radar.auctionVolumeRatio,
      radar.amountToYesterdayRatio,
      radar.auctionChangePercent
    );
    const ladder = realLadder ?? calculateBoardLadderSummary(allQuotes);
    const reg = calculateRegulatoryDeviation(activeQuote);
    const dvr = calculateVWDVR(activeQuote, intradayPointsMap[selectedSymbol]);

    return {
      radar,
      volAnalysis,
      ladder,
      reg,
      dvr,
    };
  }, [activeQuote, currentOverride, allQuotes, intradayPointsMap, selectedSymbol, realLadder, serverRadarData]);

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
          auctionAmount: Math.round(yestAmt * 0.125),
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
          auctionAmount: Math.round(yestAmt * 0.242),
          auctionVolumeRatio: 8.2,
          unmatchedHands: -4200,
        },
      }));
    }
  };

  const handleSelectStockAndJumpToChart = (item: any, jumpToChart = true) => {
    selectAndSubscribeStock({
      symbol: item.symbol,
      name: item.name,
      code: item.code,
      market: item.symbol.endsWith('.SH') ? 'SH' : 'SZ',
    });
    if (jumpToChart) {
      setWorkspaceMode('chart');
    }
  };

  const ratioBarWidth = Math.min(100, Math.max(4, (radar.amountToYesterdayRatio / 25) * 100));

  return (
    <section
      aria-label="09:25 竞价雷达满屏工作台"
      data-testid="call-auction-radar-plugin"
      className="flex flex-col flex-1 min-h-0 h-full bg-[#0d0e12] text-[#d1d4dc] select-none overflow-hidden"
    >
      {/* 顶部控制条：全市场信号统计 + 异动焦点股胶囊 + 推演沙盘开关 + 返回主图 */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 bg-[#131722] border-b border-[#2a2e39] shrink-0">
        <div className="flex flex-wrap items-center gap-2 min-w-0">
          {/* Tab 切换 */}
          <div className="flex items-center gap-1 shrink-0">
            <button
              type="button"
              onClick={() => setActiveTab('radar')}
              className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs sm:text-sm font-bold tracking-tight whitespace-nowrap transition-colors cursor-pointer ${
                activeTab === 'radar'
                  ? 'bg-[#F59E0B]/20 text-[#F59E0B] border border-[#F59E0B]/50'
                  : 'text-[#9ca3af] hover:text-white border border-transparent'
              }`}
            >
              <Radar className="w-4 h-4 shrink-0" />
              <span>09:25 接力雷达</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('fullscan')}
              className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs sm:text-sm font-bold tracking-tight whitespace-nowrap transition-colors cursor-pointer ${
                activeTab === 'fullscan'
                  ? 'bg-[#2962ff]/20 text-[#38bdf8] border border-[#2962ff]/50'
                  : 'text-[#9ca3af] hover:text-white border border-transparent'
              }`}
            >
              <Zap className="w-4 h-4 shrink-0" />
              <span>全市场竞价扫描</span>
            </button>
          </div>

          {/* 全市场信号实时统计 + 异动焦点股（仅接力雷达 Tab 显示） */}
          {activeTab === 'radar' && (<>
          {/* 全市场信号实时统计 */}
          <div className="hidden sm:flex items-center gap-1.5 text-[11px] font-mono tabular-nums shrink-0">
            <button
              type="button"
              onClick={() =>
                setSignalFilter(signalFilter === 'SUPER_GRAB' ? 'ALL' : 'SUPER_GRAB')
              }
              className={`px-2 py-0.5 rounded border cursor-pointer transition-colors whitespace-nowrap ${
                signalFilter === 'SUPER_GRAB'
                  ? 'bg-[#F6465D] text-white border-[#F6465D]'
                  : 'bg-[#F6465D]/15 text-[#F6465D] border-[#F6465D]/30 hover:bg-[#F6465D]/25'
              }`}
            >
              抢筹/巨封 {radarSummary.grabCount}
            </button>
            <button
              type="button"
              onClick={() =>
                setSignalFilter(
                  signalFilter === 'WEAK_TO_STRONG' ? 'ALL' : 'WEAK_TO_STRONG'
                )
              }
              className={`px-2 py-0.5 rounded border cursor-pointer transition-colors whitespace-nowrap ${
                signalFilter === 'WEAK_TO_STRONG'
                  ? 'bg-[#F59E0B] text-[#0d0e12] font-bold border-[#F59E0B]'
                  : 'bg-[#F59E0B]/15 text-[#F59E0B] border-[#F59E0B]/30 hover:bg-[#F59E0B]/25'
              }`}
            >
              弱转强 {radarSummary.weakToStrongCount}
            </button>
            <button
              type="button"
              onClick={() =>
                setSignalFilter(
                  signalFilter === 'NUCLEAR_BUTTON' ? 'ALL' : 'NUCLEAR_BUTTON'
                )
              }
              className={`px-2 py-0.5 rounded border cursor-pointer transition-colors whitespace-nowrap ${
                signalFilter === 'NUCLEAR_BUTTON'
                  ? 'bg-[#0ECB81] text-[#0d0e12] font-bold border-[#0ECB81]'
                  : 'bg-[#0ECB81]/15 text-[#0ECB81] border-[#0ECB81]/30 hover:bg-[#0ECB81]/25'
              }`}
            >
              核按钮 {radarSummary.nuclearCount}
            </button>
          </div>

          {/* 异动焦点股一键切换按钮 */}
          <div className="hidden xl:flex items-center gap-1 flex-wrap">
            {radarSummary.highlightStocks.slice(0, 4).map((item: any) => {
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
                  onClick={() => handleSelectStockAndJumpToChart(item, false)}
                  className={`flex items-center gap-1 px-2 py-0.5 rounded text-[11px] border transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
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
          </>)}
        </div>

        {/* 右侧：信号推演沙盘、切回分时/K线主图 */}
        <div className="flex items-center gap-2 shrink-0">
          {activeTab === 'radar' && (
          <button
            type="button"
            data-testid="toggle-auction-sim-btn"
            onClick={() => setIsSimOpen((v) => !v)}
            className={`flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium border transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
              isSimOpen || currentOverride
                ? 'bg-[#F59E0B]/20 border-[#F59E0B] text-[#F59E0B]'
                : 'bg-[#1e222d] hover:bg-[#262b38] border-[#2a2e39] text-[#9ca3af] hover:text-white'
            }`}
          >
            <SlidersHorizontal className="w-3.5 h-3.5" />
            <span>竞价推演沙盘</span>
          </button>
          )}

          <button
            type="button"
            data-testid="toggle-quant-workbench-btn"
            onClick={() => setWorkspaceMode('chart')}
            className="flex items-center gap-1 px-2.5 py-1 rounded text-xs font-semibold bg-[#2962ff] hover:bg-[#1e53e5] text-white transition-colors whitespace-nowrap shrink-0 cursor-pointer"
          >
            <BarChart2 className="w-3.5 h-3.5" />
            <span>返回分时/K线主图</span>
          </button>
        </div>
      </div>

      {/* 主体满屏自适应容器 — 接力雷达 Tab */}
      {activeTab === 'radar' && (
      <div className="flex-1 min-h-0 flex flex-col p-3 gap-3 overflow-y-auto">
        {/* 当前选中标的 09:25 竞价三维核心算子面板 */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 shrink-0">
          {/* 卡片 1：09:25 竞价信号识别 */}
          <div
            className={`flex flex-col justify-between p-3 rounded-md bg-[#1e222d] border ${sigStyle.border}`}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs text-[#9ca3af] font-medium truncate">
                09:25 信号定性 · {radar.name} ({radar.code})
              </span>
              <span
                data-testid="active-auction-signal-badge"
                className={`px-2 py-0.5 rounded border text-xs font-bold whitespace-nowrap shrink-0 ${sigStyle.badge}`}
              >
                {radar.signalLabel}
              </span>
            </div>
            <div className="mt-2 flex items-baseline justify-between gap-2 font-mono tabular-nums">
              <div className="whitespace-nowrap">
                <span className="text-xs text-[#787b86] mr-1.5 font-sans">09:25撮合价:</span>
                <span
                  className={`text-base font-bold ${getSignedColorClass(
                    radar.auctionChangePercent
                  )}`}
                >
                  {formatPrice(radar.auctionPrice)} (
                  {formatSignedPercent(radar.auctionChangePercent)})
                </span>
              </div>
              <span className="text-xs text-[#d1d4dc] font-sans truncate">
                {activeQuote.ultraShort?.yesterdayPerformanceNote ?? '昨常态收盘'}
              </span>
            </div>
            <div
              data-testid="active-auction-signal-reason"
              className="mt-1.5 text-xs text-[#9ca3af] leading-snug"
            >
              {radar.signalReason}
            </div>
          </div>

          {/* 卡片 2：竞价金额占昨比计算 */}
          <div className="flex flex-col justify-between p-3 rounded-md bg-[#1e222d] border border-[#2a2e39]">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs text-[#9ca3af] font-medium whitespace-nowrap">
                竞价金额占昨比 (黄金线 6%~16%)
              </span>
              <span
                data-testid="active-auction-amount-ratio"
                className={`font-mono tabular-nums text-base font-bold whitespace-nowrap shrink-0 ${
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

            <div className="my-2">
              <div className="relative w-full h-2.5 bg-[#131722] rounded overflow-hidden">
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

            <div className="flex items-center justify-between gap-2 text-xs font-mono tabular-nums text-[#9ca3af] whitespace-nowrap">
              <span>
                {radar.amountBasis === 'intraday'
                  ? '当日累计成交'
                  : radar.estimated
                  ? '竞价额(估算)'
                  : '09:25竞价额'}{' '}
                <strong className="text-white">{formatAmountCN(radar.auctionAmount)}</strong>
              </span>
              <span>
                昨全天额{' '}
                <strong className="text-[#d1d4dc]">
                  {formatAmountCN(radar.yesterdayAmount)}
                </strong>
              </span>
            </div>
          </div>

          {/* 卡片 3：09:25 竞价量比分析与未匹配封单/压单 */}
          <div className="flex flex-col justify-between p-3 rounded-md bg-[#1e222d] border border-[#2a2e39]">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs text-[#9ca3af] font-medium whitespace-nowrap">
                09:25 量比与未匹配封单/压单
              </span>
              <span className="px-2 py-0.5 rounded bg-[#131722] border border-[#2a2e39] text-[11px] font-semibold text-[#F59E0B] whitespace-nowrap shrink-0">
                {volAnalysis.levelLabel} · {volAnalysis.intensityScore}分
              </span>
            </div>

            <div className="mt-2 flex items-baseline justify-between gap-2 font-mono tabular-nums whitespace-nowrap">
              <div>
                <span className="text-xs text-[#787b86] mr-1 font-sans">竞价量比:</span>
                <span
                  data-testid="active-auction-vol-ratio"
                  className="text-base font-bold text-[#F59E0B]"
                >
                  {radar.auctionVolumeRatio.toFixed(2)}x
                </span>
              </div>
              <div>
                <span className="text-xs text-[#787b86] mr-1 font-sans">未匹配:</span>
                <span
                  data-testid="active-auction-unmatched"
                  className={`text-sm font-bold ${
                    radar.unmatchedHands >= 0 ? 'text-[#F6465D]' : 'text-[#0ECB81]'
                  }`}
                >
                  {radar.unmatchedHands >= 0
                    ? `买封 +${radar.unmatchedHands.toLocaleString('en-US')}手`
                    : `卖压 ${radar.unmatchedHands.toLocaleString('en-US')}手`}
                </span>
              </div>
            </div>

            <div className="mt-1.5 text-xs text-[#9ca3af] leading-snug">
              {volAnalysis.description}
            </div>
          </div>
        </div>

        {/* 可选展开区：交互式 09:25 竞价信号推演仿真器 */}
        {isSimOpen && (
          <div
            data-testid="auction-simulator-panel"
            className="p-3 rounded-md bg-[#1e222d] border border-[#F59E0B]/50 text-xs shrink-0"
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

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2.5">
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

        {/* 全市场 09:25 竞价异动高密度矩阵表（默认 100% 满屏展开，点击直达主图） */}
        <div
          data-testid="expanded-auction-matrix"
          className="flex-1 min-h-[260px] flex flex-col rounded-md bg-[#1e222d] border border-[#2a2e39] overflow-hidden"
        >
          <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 bg-[#131722] border-b border-[#2a2e39] shrink-0">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-white">
                全市场 09:25 竞价异动监控矩阵 ({filteredRadarMetrics.length} 只标的)
              </span>
              <span className="text-[11px] text-[#787b86]">
                点击任意行自动切换选中股票，点击【看主图】秒切回分时/K线
              </span>
            </div>

            <div className="flex items-center gap-1 flex-wrap">
              {(
                [
                  { id: 'ALL', label: '全部信号' },
                  { id: 'SUPER_GRAB', label: '超预期抢筹' },
                  { id: 'LOCKED_LIMIT_UP', label: '一字巨封' },
                  { id: 'WEAK_TO_STRONG', label: '分歧弱转强' },
                  { id: 'OVERHEAT_DUMP', label: '爆量兑现' },
                  { id: 'NUCLEAR_BUTTON', label: '竞价核按钮' },
                ] as { id: 'ALL' | AuctionSignalType; label: string }[]
              ).map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setSignalFilter(tab.id)}
                  className={`px-2 py-0.5 rounded text-[11px] transition-colors cursor-pointer whitespace-nowrap ${
                    signalFilter === tab.id
                      ? 'bg-[#2962ff] text-white font-semibold'
                      : 'bg-[#1e222d] text-[#9ca3af] hover:text-white'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex-1 overflow-auto" ref={scrollContainerRef} onScroll={handleScroll}>
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-[#2a2e39] bg-[#161a24] text-[#787b86] text-[11px] sticky top-0 z-10">
                  <th className="py-2 px-3 whitespace-nowrap">股票标的</th>
                  <th className="py-2 px-2.5 text-right whitespace-nowrap">09:25撮合 / 涨幅</th>
                  <th className="py-2 px-2.5 text-right whitespace-nowrap">竞价成交额</th>
                  <th className="py-2 px-3 whitespace-nowrap">金额占昨比 (黄金线 6%~16%)</th>
                  <th className="py-2 px-2.5 text-right whitespace-nowrap">竞价量比</th>
                  <th className="py-2 px-2.5 text-right whitespace-nowrap">未匹配封单/压单</th>
                  <th className="py-2 px-2.5 whitespace-nowrap">信号定性</th>
                  <th className="py-2 px-3 whitespace-nowrap">游资盘口客观诊断</th>
                  <th className="py-2 px-2.5 text-right whitespace-nowrap">主图联动</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#2a2e39]/60">
                {(() => {
                  const total = filteredRadarMetrics.length;
                  const startIdx = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - BUFFER_ROWS);
                  const endIdx = Math.min(total, startIdx + Math.ceil(viewportHeight / ROW_HEIGHT) + 2 * BUFFER_ROWS);
                  return (
                    <>
                      {startIdx > 0 && (
                        <tr style={{ height: startIdx * ROW_HEIGHT }} aria-hidden="true"><td colSpan={9} /></tr>
                      )}
                      {filteredRadarMetrics.slice(startIdx, endIdx).map((item: any) => {
                  const st = getSignalStyle(item.signal);
                  const isSelected = item.symbol === selectedSymbol;
                  const barW = Math.min(100, Math.max(4, Math.round(item.amountToYesterdayRatio * 4)));
                  return (
                    <tr
                      key={item.symbol}
                      onClick={() => handleSelectStockAndJumpToChart(item, false)}
                      className={`cursor-pointer transition-colors ${
                        isSelected ? 'bg-[#2962ff]/20' : 'hover:bg-[#262b38]'
                      }`}
                    >
                      <td className="py-2 px-3 whitespace-nowrap">
                        <div className="font-semibold text-white">{item.name}</div>
                        <div className="font-mono tabular-nums text-[10px] text-[#787b86]">
                          {item.symbol} · {item.sector || '核心标的'}
                        </div>
                      </td>
                      <td
                        className={`py-2 px-2.5 text-right font-mono tabular-nums font-semibold whitespace-nowrap ${getSignedColorClass(
                          item.auctionChangePercent
                        )}`}
                      >
                        {formatPrice(item.auctionPrice)} (
                        {formatSignedPercent(item.auctionChangePercent)})
                      </td>
                      <td className="py-2 px-2.5 text-right font-mono tabular-nums text-[#d1d4dc] whitespace-nowrap">
                        {formatAmountCN(item.auctionAmount)}
                      </td>
                      <td className="py-2 px-3 whitespace-nowrap min-w-[140px]">
                        <div className="flex items-center justify-between font-mono tabular-nums text-xs mb-1">
                          <span className="font-bold text-[#F59E0B]">
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
                                : item.amountToYesterdayRatio >= 6.0
                                ? 'bg-[#F6465D]'
                                : 'bg-[#2962ff]'
                            }`}
                            style={{ width: `${barW}%` }}
                          />
                        </div>
                      </td>
                      <td className="py-2 px-2.5 text-right font-mono tabular-nums text-white font-semibold whitespace-nowrap">
                        {item.auctionVolumeRatio.toFixed(2)}x
                      </td>
                      <td
                        className={`py-2 px-2.5 text-right font-mono tabular-nums font-semibold whitespace-nowrap ${
                          item.unmatchedHands >= 0 ? 'text-[#F6465D]' : 'text-[#0ECB81]'
                        }`}
                      >
                        {item.unmatchedHands >= 0
                          ? `买封 +${item.unmatchedHands.toLocaleString('en-US')}手`
                          : `卖压 ${item.unmatchedHands.toLocaleString('en-US')}手`}
                      </td>
                      <td className="py-2 px-2.5 whitespace-nowrap">
                        <span
                          className={`inline-block px-2 py-0.5 rounded border text-[11px] font-semibold ${st.badge}`}
                        >
                          {item.signalLabel}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-[11px] text-[#9ca3af] max-w-[220px] truncate">
                        {item.signalReason}
                      </td>
                      <td className="py-2 px-2.5 text-right whitespace-nowrap">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleSelectStockAndJumpToChart(item, true);
                          }}
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-[#131722] hover:bg-[#2962ff] text-[#38bdf8] hover:text-white border border-[#2a2e39] text-[11px] font-medium transition-colors cursor-pointer"
                        >
                          <span>看主图</span>
                          <ArrowUpRight className="w-3 h-3" />
                        </button>
                      </td>
                    </tr>
                  );
                      })}
                      {endIdx < total && (
                        <tr style={{ height: (total - endIdx) * ROW_HEIGHT }} aria-hidden="true"><td colSpan={9} /></tr>
                      )}
                    </>
                  );
                })()}
              </tbody>
            </table>
          </div>
        </div>

        {/* 底部超短游资规则快速联动条 */}
        <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 rounded bg-[#131722] border border-[#2a2e39] text-xs shrink-0">
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => openQuantModule('ladder')}
              className="flex items-center gap-1 text-[#9ca3af] hover:text-white cursor-pointer whitespace-nowrap"
            >
              <Flame className="w-3.5 h-3.5 text-[#F6465D]" />
              <span>
                连板梯队: 最高{' '}
                <strong className="font-mono text-[#F6465D]">{ladder.maxBoardHeight}连板</strong>
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
                  {formatPrice(reg.effectiveTriggerPrice)}元 (
                  {formatSignedPercent(reg.effectiveMaxSafeChangePercent)})
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
                <strong className="font-mono tabular-nums text-white">{dvr.vwDvrScore}分</strong> (
                {dvr.signalLabel})
              </span>
            </button>
          </div>

          <button
            type="button"
            onClick={() => openQuantModule('overview')}
            className="text-[#38bdf8] hover:underline font-medium whitespace-nowrap cursor-pointer"
          >
            进入六维超短量化作战室 &rarr;
          </button>
        </div>
      </div>
      )}

      {/* 全市场竞价扫描 Tab 内容 */}
      {activeTab === 'fullscan' && (
        <div className="flex-1 min-h-0 flex flex-col p-3 gap-3 overflow-hidden">
          {/* 统计卡片 */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2 shrink-0">
            <div className="flex flex-col items-center justify-center p-2 rounded-md bg-[#1e222d] border border-[#2a2e39]">
              <span className="text-[11px] text-[#787b86]">扫描总数</span>
              <span className="text-lg font-bold text-white font-mono tabular-nums">
                {fullMarketScanData?.total_scanned ?? '—'}
              </span>
            </div>
            <div className="flex flex-col items-center justify-center p-2 rounded-md bg-[#1e222d] border border-[#F6465D]/30">
              <span className="text-[11px] text-[#787b86]">超预期抢筹</span>
              <span className="text-lg font-bold text-[#F6465D] font-mono tabular-nums">
                {fullMarketScanData?.grabCount ?? 0}
              </span>
            </div>
            <div className="flex flex-col items-center justify-center p-2 rounded-md bg-[#1e222d] border border-[#0ECB81]/30">
              <span className="text-[11px] text-[#787b86]">竞价核按钮</span>
              <span className="text-lg font-bold text-[#0ECB81] font-mono tabular-nums">
                {fullMarketScanData?.nuclearCount ?? 0}
              </span>
            </div>
            <div className="flex flex-col items-center justify-center p-2 rounded-md bg-[#1e222d] border border-[#a855f7]/30">
              <span className="text-[11px] text-[#787b86]">缩量假高开</span>
              <span className="text-lg font-bold text-[#c084fc] font-mono tabular-nums">
                {fullMarketScanData?.fakeHighCount ?? 0}
              </span>
            </div>
            <div className="flex flex-col items-center justify-center p-2 rounded-md bg-[#1e222d] border border-[#F6465D]/50">
              <span className="text-[11px] text-[#787b86]">一字封单</span>
              <span className="text-lg font-bold text-[#F6465D] font-mono tabular-nums">
                {fullMarketScanData?.lockedCount ?? 0}
              </span>
            </div>
          </div>

          {/* 信号分组列表（虚拟滚动） */}
          <div className="flex-1 min-h-0 overflow-auto" ref={fullscanScrollRef} onScroll={handleFullscanScroll}>
            {fullMarketScanData ? (
              (() => {
                const groups: { signal: FullScanSignalType; label: string; items: FullMarketScanItem[] }[] = [
                  { signal: 'SUPER_GRAB', label: '超预期抢筹', items: fullMarketScanData.scan_items.filter((it: any) => it.signal === 'SUPER_GRAB') },
                  { signal: 'LOCKED_LIMIT_UP', label: '一字封单', items: fullMarketScanData.scan_items.filter((it: any) => it.signal === 'LOCKED_LIMIT_UP') },
                  { signal: 'FAKE_HIGH', label: '缩量假高开', items: fullMarketScanData.scan_items.filter((it: any) => it.signal === 'FAKE_HIGH') },
                  { signal: 'NUCLEAR_BUTTON', label: '竞价核按钮', items: fullMarketScanData.scan_items.filter((it: any) => it.signal === 'NUCLEAR_BUTTON') },
                ];

                type FlatRow =
                  | { type: 'group'; signal: FullScanSignalType; label: string; count: number }
                  | { type: 'item'; item: FullMarketScanItem };
                const flatRows: FlatRow[] = [];
                for (const g of groups) {
                  if (g.items.length === 0) continue;
                  const isCollapsed = collapsedGroups[g.signal] ?? false;
                  flatRows.push({ type: 'group', signal: g.signal, label: g.label, count: g.items.length });
                  if (!isCollapsed) {
                    for (const item of g.items) {
                      flatRows.push({ type: 'item', item });
                    }
                  }
                }

                const GROUP_ROW_HEIGHT = 36;
                const totalHeight = flatRows.reduce((sum, row) => sum + (row.type === 'group' ? GROUP_ROW_HEIGHT : FULLSCAN_ROW_HEIGHT), 0);

                let cursor = 0;
                let startIdx = 0;
                let startOffset = 0;
                for (let i = 0; i < flatRows.length; i++) {
                  const h = flatRows[i].type === 'group' ? GROUP_ROW_HEIGHT : FULLSCAN_ROW_HEIGHT;
                  if (cursor + h > fullscanScrollTop - FULLSCAN_BUFFER_ROWS * FULLSCAN_ROW_HEIGHT) {
                    startIdx = i;
                    startOffset = cursor;
                    break;
                  }
                  cursor += h;
                }

                let endIdx = flatRows.length;
                cursor = startOffset;
                for (let i = startIdx; i < flatRows.length; i++) {
                  const h = flatRows[i].type === 'group' ? GROUP_ROW_HEIGHT : FULLSCAN_ROW_HEIGHT;
                  cursor += h;
                  if (cursor > fullscanScrollTop + fullscanViewportHeight + FULLSCAN_BUFFER_ROWS * FULLSCAN_ROW_HEIGHT) {
                    endIdx = i + 1;
                    break;
                  }
                }

                return (
                  <div style={{ height: totalHeight, position: 'relative' }}>
                    <div style={{ position: 'absolute', top: startOffset, left: 0, right: 0 }}>
                      {flatRows.slice(startIdx, endIdx).map((row) => {
                        if (row.type === 'group') {
                          const isCollapsed = collapsedGroups[row.signal] ?? false;
                          const style = getFullScanSignalStyle(row.signal);
                          return (
                            <div
                              key={`group-${row.signal}`}
                              style={{ height: GROUP_ROW_HEIGHT }}
                              className="flex items-center gap-2 px-3 cursor-pointer hover:bg-[#262b38] border-b border-[#2a2e39]"
                              onClick={() => setCollapsedGroups((prev) => ({ ...prev, [row.signal]: !prev[row.signal] }))}
                            >
                              <span className={`inline-block px-2 py-0.5 rounded border text-xs font-semibold ${style.badge}`}>
                                {row.label}
                              </span>
                              <span className="text-xs text-[#9ca3af]">{row.count} 只</span>
                              <span className="text-xs text-[#787b86]">{isCollapsed ? '▶ 展开查看' : '▼ 点击折叠'}</span>
                            </div>
                          );
                        }
                        const item = row.item;
                        const style = getFullScanSignalStyle(item.signal);
                        const sym = item.code.startsWith('6') ? `${item.code}.SH` : `${item.code}.SZ`;
                        return (
                          <div
                            key={`item-${item.code}`}
                            style={{ height: FULLSCAN_ROW_HEIGHT }}
                            onClick={() => handleSelectStockAndJumpToChart({ symbol: sym, name: item.name, code: item.code }, true)}
                            className="flex items-center gap-2 px-3 cursor-pointer hover:bg-[#262b38] border-b border-[#2a2e39]/60 text-xs"
                          >
                            <span className="font-mono tabular-nums text-[#787b86] w-16 shrink-0">{item.code}</span>
                            <span className="text-white font-medium w-20 truncate shrink-0">{item.name}</span>
                            <span className={`font-mono tabular-nums w-20 text-right shrink-0 ${item.open_pct >= 0 ? 'text-[#F6465D]' : 'text-[#0ECB81]'}`}>
                              {item.price.toFixed(2)}
                            </span>
                            <span className={`font-mono tabular-nums w-20 text-right shrink-0 ${item.open_pct >= 0 ? 'text-[#F6465D]' : 'text-[#0ECB81]'}`}>
                              {item.open_pct >= 0 ? '+' : ''}{item.open_pct.toFixed(2)}%
                            </span>
                            <span className="font-mono tabular-nums w-16 text-right text-[#F59E0B] shrink-0">
                              {item.vol_ratio.toFixed(2)}x
                            </span>
                            <span className="font-mono tabular-nums w-24 text-right text-[#d1d4dc] shrink-0">
                              {formatAmountCN(item.amount)}
                            </span>
                            <span className={`inline-block px-1.5 py-0.5 rounded border text-[10px] font-semibold shrink-0 ${style.badge}`}>
                              {item.signalLabel}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })()
            ) : (
              <div className="flex items-center justify-center h-full text-[#787b86] text-sm">
                正在获取全市场竞价扫描数据...
              </div>
            )}
          </div>

          {fullMarketScanData?.updated_at && (
            <div className="shrink-0 text-[11px] text-[#787b86] text-right px-3 py-1">
              数据更新时间: {fullMarketScanData.updated_at} · 每5秒自动刷新
            </div>
          )}
        </div>
      )}
    </section>
  );
};
