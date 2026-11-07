import React, { useMemo, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { useMarketStore } from '../store/useMarketStore';
import { useRealIntradayRadar } from '../hooks/useRealQuantData';
import type {
  IntradayRadarBasis,
  SynergyLevel,
} from '../types/market';
import {
  formatAmountCN,
  formatPrice,
  formatVolumeHands,
  getDirectionColorClass,
  getPriceDirection,
} from '../utils/marketCalc';

interface TradeTicksAndMetricsPanelProps {
  forcedTab?: 'trades' | 'fundamentals' | 'radar';
}

const formatSignedFlow = (amount: number | null | undefined): string => {
  if (amount === null || amount === undefined || !Number.isFinite(amount)) return '--';
  if (Math.abs(amount) < 1) return '0';
  const formatted = formatAmountCN(Math.abs(amount));
  return amount > 0 ? `+${formatted}` : `-${formatted}`;
};

const formatSignedPercent = (val: number | null | undefined): string => {
  if (val === null || val === undefined || !Number.isFinite(val)) return '--';
  const sign = val > 0 ? '+' : '';
  return `${sign}${val.toFixed(2)}%`;
};

const getSynergyBadge = (level: SynergyLevel) => {
  switch (level) {
    case 'STRONG_RESONANCE':
      return {
        label: '强共振抢筹',
        className: 'bg-rose-500/20 text-[#F6465D] border border-rose-500/40 font-bold',
      };
    case 'MILD_RESONANCE':
      return {
        label: '温和配合',
        className: 'bg-amber-500/15 text-amber-300 border border-amber-500/30 font-medium',
      };
    case 'DIVERGENCE_WARNING':
      return {
        label: '量价背离预警',
        className: 'bg-yellow-500/15 text-yellow-400 border border-yellow-500/30 font-medium',
      };
    case 'BEARISH_DUMP':
      return {
        label: '资金派发预警',
        className: 'bg-emerald-500/15 text-[#0ECB81] border border-emerald-500/30 font-medium',
      };
    default:
      return {
        label: '中性观察',
        className: 'bg-slate-500/15 text-slate-300 border border-slate-500/30 font-medium',
      };
  }
};

const getBasisBadge = (basis?: IntradayRadarBasis, customLabel?: string) => {
  switch (basis) {
    case 'live_eastmoney':
      return {
        label: customLabel || '东财实时异动',
        className: 'bg-[#0ECB81]/15 text-[#0ECB81] border border-[#0ECB81]/30',
      };
    case 'intraday_trend_mined':
      return {
        label: customLabel || '真实分时挖掘',
        className: 'bg-sky-500/15 text-sky-400 border border-sky-500/30',
      };
    case 'snapshot_fallback':
    default:
      return {
        label: customLabel || 'L1盘口快照',
        className: 'bg-slate-500/15 text-slate-300 border border-slate-500/30',
      };
  }
};

const getTemperamentBadge = (temp?: string) => {
  switch (temp) {
    case 'BULLISH_ATTACK':
      return { label: '多头进攻', className: 'text-[#F6465D] bg-rose-500/10 border-rose-500/20' };
    case 'BEARISH_DEFENSE':
      return { label: '防守承压', className: 'text-[#0ECB81] bg-emerald-500/10 border-emerald-500/20' };
    case 'BALANCED_ROTATION':
    default:
      return { label: '均衡轮动', className: 'text-amber-400 bg-amber-500/10 border-amber-500/20' };
  }
};

export const TradeTicksAndMetricsPanel: React.FC<TradeTicksAndMetricsPanelProps> = ({
  forcedTab,
}) => {
  const [activeSubTab, setActiveSubTab] = useState<'trades' | 'radar' | 'fundamentals'>('trades');
  const currentTab = forcedTab ?? activeSubTab;

  // 雷达内部胶囊切换与过滤器状态
  const [radarSubView, setRadarSubView] = useState<'anomalies' | 'topInflow'>('anomalies');
  const [anomalyFilter, setAnomalyFilter] = useState<'ALL' | 'BULLISH' | 'BEARISH'>('ALL');

  // Zustand 状态订阅
  const selectedSymbol = useMarketStore((s) => s.selectedSymbol);
  const setSelectedSymbol = useMarketStore((s) => s.setSelectedSymbol);
  const quote = useMarketStore((s) => s.quotes[s.selectedSymbol]);

  // 盘中异动与资金流向监控 Hook
  const { radar, loading: radarLoading, refresh: refreshRadar } = useRealIntradayRadar(
    selectedSymbol,
    50
  );

  const basisBadge = getBasisBadge(radar?.basis, radar?.basisLabel);
  const temperamentBadge = getTemperamentBadge(radar?.summary.marketTemperament);
  const flow = radar?.symbolCapitalFlow;
  const synergyBadge = getSynergyBadge(flow?.synergyLevel ?? 'MILD_RESONANCE');

  const bullishCount = radar?.summary?.bullishCount ?? 0;
  const bearishCount = radar?.summary?.bearishCount ?? 0;
  const totalAnomalies = bullishCount + bearishCount;
  const bullPercent = totalAnomalies > 0 ? Math.round((bullishCount / totalAnomalies) * 100) : 50;

  const anomalies = useMemo(() => radar?.anomalies || [], [radar?.anomalies]);
  const filteredAnomalies = useMemo(() => {
    if (anomalyFilter === 'BULLISH') return anomalies.filter((a) => a.polarity === 'BULLISH');
    if (anomalyFilter === 'BEARISH') return anomalies.filter((a) => a.polarity === 'BEARISH');
    return anomalies;
  }, [anomalies, anomalyFilter]);

  if (!quote && currentTab !== 'radar') {
    return (
      <div className="flex-1 flex items-center justify-center bg-[#1e222d] text-xs text-[#787b86]">
        暂无标的数据
      </div>
    );
  }

  return (
    <section
      aria-label="实时成交明细与核心盘面指标"
      className="flex flex-col flex-1 min-h-0 bg-[#1e222d]"
    >
      {/* 当未由移动端强制指定 Tab 时，显示内部切换栏 */}
      {!forcedTab && (
        <div className="flex items-center justify-between px-3 py-1.5 border-b border-[#2a2e39] bg-[#131722]/40 shrink-0">
          <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar">
            <button
              type="button"
              onClick={() => setActiveSubTab('trades')}
              className={`px-2 py-0.5 text-xs font-medium rounded transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
                currentTab === 'trades'
                  ? 'bg-[#2a2e39] text-white'
                  : 'text-[#787b86] hover:text-[#d1d4dc]'
              }`}
            >
              实时成交简表
            </button>
            <button
              type="button"
              onClick={() => setActiveSubTab('radar')}
              className={`px-2 py-0.5 text-xs font-medium rounded transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
                currentTab === 'radar'
                  ? 'bg-[#2a2e39] text-white'
                  : 'text-[#787b86] hover:text-[#d1d4dc]'
              }`}
            >
              盘口异动与资金
            </button>
            <button
              type="button"
              onClick={() => setActiveSubTab('fundamentals')}
              className={`px-2 py-0.5 text-xs font-medium rounded transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
                currentTab === 'fundamentals'
                  ? 'bg-[#2a2e39] text-white'
                  : 'text-[#787b86] hover:text-[#d1d4dc]'
              }`}
            >
              换手与基本面
            </button>
          </div>
          <span className="text-[11px] text-[#787b86] font-mono tabular-nums shrink-0 ml-2">
            {currentTab === 'radar'
              ? (radar?.summary ? `异动 ${radar.summary.totalCount} 笔` : '')
              : `换手 ${typeof quote?.turnoverRate === 'number' ? `${quote.turnoverRate.toFixed(2)}%` : '--'}`}
          </span>
        </div>
      )}

      {currentTab === 'trades' && quote ? (
        <div className="flex flex-col flex-1 min-h-0">
          {/* 内外盘主动买卖对比简条 */}
          <div className="grid grid-cols-2 gap-2 px-3 py-1.5 bg-[#131722]/40 border-b border-[#2a2e39] text-[11px] shrink-0">
            <div className="flex items-center justify-between">
              <span className="text-[#787b86]">外盘(主动买)</span>
              <span className="font-mono tabular-nums text-[#F6465D] font-medium">
                {formatVolumeHands(quote.outerVolume ?? 0)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[#787b86]">内盘(主动卖)</span>
              <span className="font-mono tabular-nums text-[#0ECB81] font-medium">
                {formatVolumeHands(quote.innerVolume ?? 0)}
              </span>
            </div>
          </div>

          {/* 成交简表表头 */}
          <div className="flex items-center justify-between px-3 py-1 text-[11px] text-[#787b86] border-b border-[#2a2e39]/60 shrink-0">
            <span className="w-16">时间</span>
            <span className="w-20 text-right">成交价</span>
            <span className="w-16 text-right">现手</span>
            <span className="w-8 text-right">方向</span>
          </div>

          {/* 滚动分笔成交列表 */}
          <div className="flex-1 overflow-y-auto divide-y divide-[#2a2e39]/30">
            {(quote.recentTrades || []).map((trade) => {
              const dir = getPriceDirection(trade.price, quote.prevClose);
              const priceColor = getDirectionColorClass(dir);
              const sideColor =
                trade.side === 'BUY'
                  ? 'text-[#F6465D]'
                  : trade.side === 'SELL'
                  ? 'text-[#0ECB81]'
                  : 'text-[#787b86]';
              const sideLabel =
                trade.side === 'BUY' ? 'B' : trade.side === 'SELL' ? 'S' : '-';

              return (
                <div
                  key={trade.id}
                  className="flex items-center justify-between px-3 h-[24px] text-xs hover:bg-[#2a2e39]/40 transition-colors"
                >
                  <span className="w-16 font-mono tabular-nums text-[#9ca3af] text-[11px]">
                    {trade.time}
                  </span>
                  <span
                    className={`w-20 text-right font-mono tabular-nums font-medium ${priceColor}`}
                  >
                    {formatPrice(trade.price)}
                  </span>
                  <span className="w-16 text-right font-mono tabular-nums text-[#d1d4dc]">
                    {trade.volume}
                  </span>
                  <span
                    className={`w-8 text-right font-mono tabular-nums font-bold ${sideColor}`}
                  >
                    {sideLabel}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      ) : currentTab === 'radar' ? (
        /* 盘中异动与资金流向监控面板 */
        <div className="flex flex-col flex-1 min-h-0 overflow-y-auto divide-y divide-[#2a2e39]/60">
          {/* 区块一：顶部状态与多空温度条 */}
          <div className="p-2.5 bg-[#131722]/60 space-y-2 shrink-0">
            <div className="flex items-center justify-between gap-1 text-[11px]">
              <div className="flex items-center gap-1.5 min-w-0">
                <span
                  className={`px-1.5 py-0.5 rounded text-[10px] font-mono shrink-0 ${basisBadge.className}`}
                  title="异动数据计算底座"
                >
                  {basisBadge.label}
                </span>
                {radar?.summary?.dominantSignal && (
                  <span className="text-[11px] text-[#d1d4dc] truncate" title="全市场主导信号">
                    主导: <strong className="text-amber-400 font-semibold">{radar.summary.dominantSignal}</strong>
                  </span>
                )}
              </div>

              <div className="flex items-center gap-1 shrink-0">
                {radar?.summary?.marketTemperament && (
                  <span
                    className={`px-1.5 py-0.5 rounded text-[10px] font-medium border ${temperamentBadge.className}`}
                  >
                    {temperamentBadge.label}
                  </span>
                )}
                <button
                  type="button"
                  onClick={refreshRadar}
                  disabled={radarLoading}
                  title="刷新盘中异动与资金流向"
                  className="p-1 rounded text-[#787b86] hover:text-white hover:bg-[#2a2e39] transition-colors cursor-pointer disabled:opacity-50"
                >
                  <RefreshCw className={`w-3 h-3 ${radarLoading ? 'animate-spin text-sky-400' : ''}`} />
                </button>
              </div>
            </div>

            {/* 多空异动温度对比条 */}
            <div>
              <div className="flex items-center justify-between text-[10px] font-mono tabular-nums mb-1">
                <span className="text-[#F6465D] font-medium">
                  多头 {bullishCount} 笔 ({bullPercent}%)
                </span>
                <span className="text-[#787b86] text-[10px]">全市场盘口多空博弈</span>
                <span className="text-[#0ECB81] font-medium">
                  空头 {bearishCount} 笔 ({100 - bullPercent}%)
                </span>
              </div>
              <div className="h-1.5 w-full bg-[#1e222d] rounded-full overflow-hidden flex border border-[#2a2e39]">
                <div
                  style={{ width: `${bullPercent}%` }}
                  className="bg-[#F6465D] h-full transition-all duration-300"
                />
                <div
                  style={{ width: `${100 - bullPercent}%` }}
                  className="bg-[#0ECB81] h-full transition-all duration-300"
                />
              </div>
            </div>
          </div>

          {/* 区块二：当前选中个股五档资金流与异动协同诊断卡 */}
          <div className="p-2.5 bg-[#1e222d] space-y-2 shrink-0">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 min-w-0">
                <span className="text-xs font-semibold text-white truncate">
                  {flow ? flow.name : (quote?.name || selectedSymbol)}
                </span>
                <span className="text-[10px] font-mono text-[#787b86]">
                  {flow ? flow.code : (quote?.code || selectedSymbol)}
                </span>
              </div>

              {flow && (
                <div className="flex items-center gap-1 shrink-0">
                  <span className={`px-1.5 py-0.5 rounded text-[10px] border ${synergyBadge.className}`}>
                    {synergyBadge.label}
                  </span>
                  <span
                    className={`text-[10px] font-mono font-bold px-1 py-0.5 rounded bg-[#131722] border border-[#2a2e39] ${
                      flow.synergyScore > 0
                        ? 'text-[#F6465D]'
                        : flow.synergyScore < 0
                        ? 'text-[#0ECB81]'
                        : 'text-[#787b86]'
                    }`}
                    title="协同度评分 [-100, +100]"
                  >
                    {flow.synergyScore > 0 ? `+${flow.synergyScore}` : flow.synergyScore}
                  </span>
                </div>
              )}
            </div>

            {flow ? (
              <>
                {/* 协同诊断文案 */}
                {flow.synergyVerdict && (
                  <div className="text-[11px] text-[#d1d4dc] bg-[#131722]/80 px-2 py-1 rounded border border-[#2a2e39]/60 leading-tight">
                    {flow.synergyVerdict}
                  </div>
                )}

                {/* 主力净流入总额与主力净占比 */}
                <div className="grid grid-cols-2 gap-2 p-1.5 rounded bg-[#131722]/50 border border-[#2a2e39]/60 text-[11px]">
                  <div>
                    <span className="text-[#787b86] text-[10px]">主力净流入</span>
                    <div
                      className={`font-mono tabular-nums font-semibold mt-0.5 text-xs ${
                        flow.mainNetInflow >= 0 ? 'text-[#F6465D]' : 'text-[#0ECB81]'
                      }`}
                    >
                      {formatSignedFlow(flow.mainNetInflow)}
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="text-[#787b86] text-[10px]">主力净占比</span>
                    <div
                      className={`font-mono tabular-nums font-semibold mt-0.5 text-xs ${
                        flow.mainNetRatio >= 0 ? 'text-[#F6465D]' : 'text-[#0ECB81]'
                      }`}
                    >
                      {flow.mainNetRatio >= 0 ? '+' : ''}
                      {flow.mainNetRatio.toFixed(1)}%
                    </div>
                  </div>
                </div>

                {/* 超大单 / 大单 / 中单 / 小单 四档资金流双向进度条 */}
                <div className="space-y-1 pt-0.5">
                  {[
                    { label: '超大单', val: flow.superLargeNetInflow },
                    { label: '大单', val: flow.largeNetInflow },
                    { label: '中单', val: flow.mediumNetInflow },
                    { label: '小单', val: flow.smallNetInflow },
                  ].map((tier) => {
                    const maxVal = Math.max(
                      Math.abs(flow.superLargeNetInflow || 0),
                      Math.abs(flow.largeNetInflow || 0),
                      Math.abs(flow.mediumNetInflow || 0),
                      Math.abs(flow.smallNetInflow || 0),
                      1
                    );
                    const ratio = Math.min(100, Math.round((Math.abs(tier.val || 0) / maxVal) * 100));
                    const isPos = (tier.val || 0) >= 0;

                    return (
                      <div key={tier.label} className="flex items-center text-[10px]">
                        <span className="w-10 text-[#787b86] shrink-0 font-medium">{tier.label}</span>
                        {/* 双向条形图 */}
                        <div className="flex-1 flex items-center h-2 bg-[#131722] rounded overflow-hidden mx-1.5 border border-[#2a2e39]/60">
                          {/* 左半区：流出 */}
                          <div className="w-1/2 h-full flex justify-end">
                            {!isPos && (
                              <div
                                style={{ width: `${ratio}%` }}
                                className="bg-[#0ECB81] h-full transition-all duration-200"
                              />
                            )}
                          </div>
                          {/* 中间基准线 */}
                          <div className="w-[1px] h-full bg-[#2a2e39]" />
                          {/* 右半区：流入 */}
                          <div className="w-1/2 h-full flex justify-start">
                            {isPos && (
                              <div
                                style={{ width: `${ratio}%` }}
                                className="bg-[#F6465D] h-full transition-all duration-200"
                              />
                            )}
                          </div>
                        </div>
                        {/* 数值 */}
                        <span
                          className={`w-14 text-right font-mono tabular-nums shrink-0 font-medium ${
                            tier.val >= 0 ? 'text-[#F6465D]' : 'text-[#0ECB81]'
                          }`}
                        >
                          {formatSignedFlow(tier.val)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </>
            ) : (
              <div className="py-3 text-center text-xs text-[#787b86] bg-[#131722]/40 rounded border border-[#2a2e39]/40">
                {radarLoading ? '资金流分析加载中…' : '当前标的暂无主力资金流向数据'}
              </div>
            )}
          </div>

          {/* 区块三：全市场盘口异动流 / 主力净流入 Top 榜 */}
          <div className="flex flex-col flex-1 min-h-[220px]">
            <div className="flex items-center justify-between px-2.5 py-1.5 bg-[#131722]/80 border-b border-[#2a2e39] shrink-0">
              <div className="flex items-center gap-1 bg-[#1e222d] p-0.5 rounded border border-[#2a2e39]">
                <button
                  type="button"
                  onClick={() => setRadarSubView('anomalies')}
                  className={`px-2 py-0.5 text-[11px] font-medium rounded transition-colors cursor-pointer ${
                    radarSubView === 'anomalies'
                      ? 'bg-[#2a2e39] text-white shadow-xs'
                      : 'text-[#787b86] hover:text-[#d1d4dc]'
                  }`}
                >
                  异动雷达流 ({radar?.anomalies?.length ?? 0})
                </button>
                <button
                  type="button"
                  onClick={() => setRadarSubView('topInflow')}
                  className={`px-2 py-0.5 text-[11px] font-medium rounded transition-colors cursor-pointer ${
                    radarSubView === 'topInflow'
                      ? 'bg-[#2a2e39] text-white shadow-xs'
                      : 'text-[#787b86] hover:text-[#d1d4dc]'
                  }`}
                >
                  主力抢筹榜 ({radar?.topInflowStocks?.length ?? 0})
                </button>
              </div>

              {radarSubView === 'anomalies' && (
                <div className="flex items-center gap-0.5 text-[10px]">
                  {(['ALL', 'BULLISH', 'BEARISH'] as const).map((filter) => {
                    const label = filter === 'ALL' ? '全部' : filter === 'BULLISH' ? '多头' : '空头';
                    const isActive = anomalyFilter === filter;
                    return (
                      <button
                        key={filter}
                        type="button"
                        onClick={() => setAnomalyFilter(filter)}
                        className={`px-1.5 py-0.5 rounded transition-colors cursor-pointer ${
                          isActive
                            ? filter === 'BULLISH'
                              ? 'bg-rose-500/20 text-[#F6465D] font-semibold'
                              : filter === 'BEARISH'
                              ? 'bg-emerald-500/20 text-[#0ECB81] font-semibold'
                              : 'bg-[#2a2e39] text-white font-semibold'
                            : 'text-[#787b86] hover:text-[#d1d4dc]'
                        }`}
                      >
                        {label}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            {/* 列表内容区 */}
            {radarSubView === 'anomalies' ? (
              <div className="divide-y divide-[#2a2e39]/30">
                {filteredAnomalies.length === 0 ? (
                  <div className="py-8 text-center text-xs text-[#787b86]">
                    {radarLoading ? '正在扫描盘中异动…' : '暂无符合筛选的盘口异动'}
                  </div>
                ) : (
                  filteredAnomalies.map((item) => {
                    const isSelected = item.symbol === selectedSymbol;
                    const isBull = item.polarity === 'BULLISH';
                    const isBear = item.polarity === 'BEARISH';
                    const badgeClass = isBull
                      ? 'bg-[#F6465D]/15 text-[#F6465D] border-[#F6465D]/30'
                      : isBear
                      ? 'bg-[#0ECB81]/15 text-[#0ECB81] border-[#0ECB81]/30'
                      : 'bg-slate-500/15 text-slate-300 border-slate-500/30';

                    return (
                      <div
                        key={item.id}
                        onClick={() => setSelectedSymbol(item.symbol)}
                        title={`点击切换到 ${item.name} (${item.code})`}
                        className={`px-2.5 py-1.5 text-xs hover:bg-[#2a2e39]/60 transition-colors cursor-pointer ${
                          isSelected ? 'bg-[#2a2e39]/40 border-l-2 border-[#F6465D]' : ''
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-1.5 min-w-0">
                            <span className="font-mono text-[10px] text-[#9ca3af] tabular-nums shrink-0">
                              {item.time}
                            </span>
                            <span className="font-medium text-white truncate max-w-[80px]">
                              {item.name}
                            </span>
                            <span className="font-mono text-[10px] text-[#787b86] shrink-0">
                              {item.code}
                            </span>
                          </div>

                          <div className="flex items-center gap-1.5 shrink-0">
                            <span
                              className={`px-1.5 py-0.2 rounded text-[10px] font-medium border ${badgeClass}`}
                            >
                              {item.typeName}
                            </span>
                            <span
                              className={`font-mono tabular-nums text-xs font-semibold ${
                                item.changePercent >= 0 ? 'text-[#F6465D]' : 'text-[#0ECB81]'
                              }`}
                            >
                              {formatSignedPercent(item.changePercent)}
                            </span>
                          </div>
                        </div>

                        {/* 第二行：强度条与明细描述 */}
                        <div className="flex items-center justify-between gap-2 mt-1 text-[10px] text-[#787b86]">
                          <div className="flex items-center gap-1 shrink-0">
                            <span>强度</span>
                            <div className="w-10 h-1 bg-[#131722] rounded-full overflow-hidden border border-[#2a2e39]/60">
                              <div
                                style={{ width: `${Math.min(100, Math.max(8, item.anomalyStrength))}%` }}
                                className={`h-full ${isBear ? 'bg-[#0ECB81]' : 'bg-[#F6465D]'}`}
                              />
                            </div>
                            <span className="font-mono tabular-nums">{item.anomalyStrength}</span>
                          </div>

                          <div className="truncate text-right font-mono text-[10px] text-[#9ca3af]">
                            {item.detailText || (item.volumeHands > 0 ? `${formatVolumeHands(item.volumeHands)}手` : '')}
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            ) : (
              /* 主力抢筹榜 */
              <div>
                <div className="flex items-center justify-between px-2.5 py-1 text-[10px] text-[#787b86] border-b border-[#2a2e39]/60 shrink-0 bg-[#131722]/30">
                  <span className="w-24">标的 / 涨跌</span>
                  <span className="w-24 text-right">主力净流入 / 占比</span>
                  <span className="w-20 text-right">异动 / 协同</span>
                </div>

                <div className="divide-y divide-[#2a2e39]/30">
                  {(!radar?.topInflowStocks || radar.topInflowStocks.length === 0) ? (
                    <div className="py-8 text-center text-xs text-[#787b86]">
                      {radarLoading ? '正在分析主力抢筹资金…' : '暂无主力流入上榜个股'}
                    </div>
                  ) : (
                    radar.topInflowStocks.map((stock) => {
                      const isSelected = stock.symbol === selectedSymbol;
                      return (
                        <div
                          key={stock.symbol}
                          onClick={() => setSelectedSymbol(stock.symbol)}
                          title={`点击切换到 ${stock.name} (${stock.code})`}
                          className={`flex items-center justify-between px-2.5 py-1.5 text-xs hover:bg-[#2a2e39]/60 transition-colors cursor-pointer ${
                            isSelected ? 'bg-[#2a2e39]/40 border-l-2 border-[#F6465D]' : ''
                          }`}
                        >
                          {/* 标的与涨跌 */}
                          <div className="w-24 min-w-0">
                            <div className="font-medium text-white truncate text-xs">{stock.name}</div>
                            <div className="flex items-center gap-1 font-mono text-[10px] tabular-nums">
                              <span className="text-[#787b86]">{stock.code}</span>
                              <span
                                className={`font-semibold ${
                                  stock.changePercent >= 0 ? 'text-[#F6465D]' : 'text-[#0ECB81]'
                                }`}
                              >
                                {formatSignedPercent(stock.changePercent)}
                              </span>
                            </div>
                          </div>

                          {/* 主力净流入与占比 */}
                          <div className="w-24 text-right">
                            <div
                              className={`font-mono tabular-nums text-xs font-semibold ${
                                stock.mainNetInflow >= 0 ? 'text-[#F6465D]' : 'text-[#0ECB81]'
                              }`}
                            >
                              {formatSignedFlow(stock.mainNetInflow)}
                            </div>
                            <div className="font-mono tabular-nums text-[10px] text-[#787b86]">
                              占比 {stock.mainNetRatio >= 0 ? '+' : ''}
                              {stock.mainNetRatio.toFixed(1)}%
                            </div>
                          </div>

                          {/* 异动与协同分 */}
                          <div className="w-20 text-right flex flex-col items-end gap-0.5">
                            {stock.latestAnomalyType ? (
                              <span className="px-1 py-0.2 rounded text-[9px] bg-rose-500/15 text-[#F6465D] border border-rose-500/30 truncate max-w-[70px]">
                                {stock.latestAnomalyType}
                              </span>
                            ) : (
                              <span className="text-[10px] text-[#787b86]">--</span>
                            )}
                            <span
                              className={`font-mono text-[10px] tabular-nums font-semibold ${
                                stock.synergyScore > 0
                                  ? 'text-amber-400'
                                  : stock.synergyScore < 0
                                  ? 'text-[#0ECB81]'
                                  : 'text-[#787b86]'
                              }`}
                            >
                              协同 {stock.synergyScore > 0 ? `+${stock.synergyScore}` : stock.synergyScore}
                            </span>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      ) : (
        /* 换手率、量比、涨跌停与基本面指标网格 */
        quote && (
          <div className="flex-1 overflow-y-auto p-3">
            <div className="grid grid-cols-2 gap-2.5 text-xs">
              <div className="p-2.5 rounded bg-[#131722] border border-[#2a2e39]">
                <div className="text-[#787b86] text-[11px]">换手率</div>
                <div className="mt-0.5 font-mono tabular-nums text-sm font-semibold text-[#F59E0B]">
                  {typeof quote.turnoverRate === 'number' ? `${quote.turnoverRate.toFixed(2)}%` : '--'}
                </div>
              </div>
              <div className="p-2.5 rounded bg-[#131722] border border-[#2a2e39]">
                <div className="text-[#787b86] text-[11px]">量比</div>
                <div className="mt-0.5 font-mono tabular-nums text-sm font-semibold text-[#38BDF8]">
                  {typeof quote.volumeRatio === 'number' ? quote.volumeRatio.toFixed(2) : '--'}
                </div>
              </div>
              <div className="p-2.5 rounded bg-[#131722] border border-[#2a2e39]">
                <div className="text-[#787b86] text-[11px]">涨停价</div>
                <div className="mt-0.5 font-mono tabular-nums text-sm font-semibold text-[#F6465D]">
                  {formatPrice(quote.limitUpPrice)}
                </div>
              </div>
              <div className="p-2.5 rounded bg-[#131722] border border-[#2a2e39]">
                <div className="text-[#787b86] text-[11px]">跌停价</div>
                <div className="mt-0.5 font-mono tabular-nums text-sm font-semibold text-[#0ECB81]">
                  {formatPrice(quote.limitDownPrice)}
                </div>
              </div>
              <div className="p-2.5 rounded bg-[#131722] border border-[#2a2e39]">
                <div className="text-[#787b86] text-[11px]">振幅</div>
                <div className="mt-0.5 font-mono tabular-nums text-sm font-semibold text-[#d1d4dc]">
                  {typeof quote.amplitude === 'number' ? `${quote.amplitude.toFixed(2)}%` : '--'}
                </div>
              </div>
              <div className="p-2.5 rounded bg-[#131722] border border-[#2a2e39]">
                <div className="text-[#787b86] text-[11px]">总成交额</div>
                <div className="mt-0.5 font-mono tabular-nums text-sm font-semibold text-[#d1d4dc]">
                  {formatAmountCN(quote.amount)}
                </div>
              </div>
              <div className="p-2.5 rounded bg-[#131722] border border-[#2a2e39]">
                <div className="text-[#787b86] text-[11px]">市盈率 (TTM)</div>
                <div className="mt-0.5 font-mono tabular-nums text-sm font-semibold text-[#d1d4dc]">
                  {typeof quote.peTtm === 'number' ? quote.peTtm.toFixed(2) : '--'}
                </div>
              </div>
              <div className="p-2.5 rounded bg-[#131722] border border-[#2a2e39]">
                <div className="text-[#787b86] text-[11px]">市净率 (PB)</div>
                <div className="mt-0.5 font-mono tabular-nums text-sm font-semibold text-[#d1d4dc]">
                  {typeof quote.pb === 'number' ? quote.pb.toFixed(2) : '--'}
                </div>
              </div>
              <div className="p-2.5 rounded bg-[#131722] border border-[#2a2e39]">
                <div className="text-[#787b86] text-[11px]">总市值</div>
                <div className="mt-0.5 font-mono tabular-nums text-sm font-semibold text-[#d1d4dc]">
                  {typeof quote.marketCap === 'number' && quote.marketCap > 0 ? `${quote.marketCap.toLocaleString('en-US')}亿` : '--'}
                </div>
              </div>
              <div className="p-2.5 rounded bg-[#131722] border border-[#2a2e39]">
                <div className="text-[#787b86] text-[11px]">流通市值</div>
                <div className="mt-0.5 font-mono tabular-nums text-sm font-semibold text-[#d1d4dc]">
                  {typeof quote.floatMarketCap === 'number' && quote.floatMarketCap > 0 ? `${quote.floatMarketCap.toLocaleString('en-US')}亿` : '--'}
                </div>
              </div>
            </div>
          </div>
        )
      )}
    </section>
  );
};
