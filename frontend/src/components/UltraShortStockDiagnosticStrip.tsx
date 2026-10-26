import React, { useEffect, useMemo } from 'react';
import { Activity, Flame, Layers, Radar, Zap } from 'lucide-react';
import { useMarketStore } from '../store/useMarketStore';
import { useRealLadder, useRealRegulatory } from '../hooks/useRealQuantData';
import { formatNullable, formatPrice, formatSignedPercent } from '../utils/marketCalc';
import {
  calculateAuctionRadar,
  calculateBoardLadderSummary,
  calculateRegulatoryDeviation,
  calculateThemeResonance,
  calculateVWDVR,
  getDragonRoleLabel,
} from '../utils/ultraShortQuant';
import { getAuctionSignalBadgeClass } from '../utils/workbenchHelpers';

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
  const intradayPointsMap = useMarketStore((s) => s.intradayPointsMap);
  const realThemeData = useMarketStore((s) => s.realThemeData);
  const fetchThemeResonance = useMarketStore((s) => s.fetchThemeResonance);

  useEffect(() => {
    fetchThemeResonance();
  }, [fetchThemeResonance]);

  const activeQuote = quotes[selectedSymbol];

  // 全市场真实梯队 + 该标的真实监管口径（模块级缓存，和作战室共用同一份请求）
  const realLadder = useRealLadder();
  const realReg = useRealRegulatory(selectedSymbol);

  const diagnostic = useMemo(() => {
    if (!activeQuote) return null;
    const allQuotes = Object.values(quotes);
    const auction = calculateAuctionRadar(activeQuote);
    // 只扫自选股会得到 0 板（自选里通常没有涨停股），必须优先用全市场真实梯队
    const ladder = realLadder ?? calculateBoardLadderSummary(allQuotes);
    const themes = realThemeData?.themes ?? calculateThemeResonance(allQuotes);
    const currentTheme = themes.find((t: any) => t.sectorName === activeQuote.sector) ?? themes[0];
    const reg = calculateRegulatoryDeviation(activeQuote, undefined, realReg.history ?? undefined);
    const intraday = intradayPointsMap[activeQuote.symbol];
    const dvr = calculateVWDVR(activeQuote, intraday);

    return {
      auction,
      ladder,
      currentTheme,
      reg,
      dvr,
    };
  }, [activeQuote, quotes, intradayPointsMap, realThemeData, realLadder, realReg.history]);

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
                红灯·10日{formatNullable(reg.cumDeviation10dPercent, 1, '%')}
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
