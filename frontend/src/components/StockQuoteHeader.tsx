import React, { useEffect, useRef, useState } from 'react';
import { Star, ListFilter, BellRing } from 'lucide-react';
import { useMarketStore } from '../store/useMarketStore';
import type { MarketScenario } from '../types/market';
import {
  formatAmountCN,
  formatPrice,
  formatSignedChange,
  formatSignedPercent,
  formatVolumeHands,
  getDirectionColorClass,
  getPriceDirection,
  getSignedColorClass,
} from '../utils/marketCalc';

export const StockQuoteHeader: React.FC = () => {
  const selectedSymbol = useMarketStore((s) => s.selectedSymbol);
  const quote = useMarketStore((s) => s.quotes[s.selectedSymbol]);
  const watchlist = useMarketStore((s) => s.watchlist);
  const alertRules = useMarketStore((s) => s.alertRules);
  const toggleWatchlist = useMarketStore((s) => s.toggleWatchlist);
  const triggerScenario = useMarketStore((s) => s.triggerScenario);
  const setMobileWatchlistOpen = useMarketStore((s) => s.setMobileWatchlistOpen);
  const setAlertModalOpen = useMarketStore((s) => s.setAlertModalOpen);

  const prevPriceRef = useRef<number | null>(quote?.price ?? null);
  const [priceFlash, setPriceFlash] = useState<string>('');

  useEffect(() => {
    if (!quote) return;
    if (prevPriceRef.current !== null && prevPriceRef.current !== quote.price) {
      const isUp = quote.price > prevPriceRef.current;
      setPriceFlash(isUp ? 'bg-[#F6465D]/20' : 'bg-[#0ECB81]/20');
      const timer = setTimeout(() => {
        setPriceFlash('');
      }, 220);
      prevPriceRef.current = quote.price;
      return () => clearTimeout(timer);
    }
    prevPriceRef.current = quote.price;
  }, [quote?.price, quote]);

  if (!quote) {
    return (
      <div className="bg-[#1e222d] border-b border-[#2a2e39] px-3 py-2 select-none flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-base font-bold text-white tracking-tight font-mono">{selectedSymbol}</span>
          <span className="text-xs text-[#2962ff] animate-pulse">正在穿透网关加载 Level-1 权威盘口与实时分时...</span>
        </div>
      </div>
    );
  }

  const isStarred = watchlist.includes(quote.symbol);
  const stockAlerts = alertRules.filter((r) => r.symbol === quote.symbol);
  const activeAlertCount = stockAlerts.filter((r) => r.enabled && !r.triggered).length;
  const triggeredAlertCount = stockAlerts.filter((r) => r.triggered).length;

  const priceColor = getSignedColorClass(quote.change);
  const openColor = getDirectionColorClass(getPriceDirection(quote.open, quote.prevClose));
  const highColor = getDirectionColorClass(getPriceDirection(quote.high, quote.prevClose));
  const lowColor = getDirectionColorClass(getPriceDirection(quote.low, quote.prevClose));

  const currentScenario: MarketScenario =
    quote.phase === 'LIMIT_UP'
      ? 'limit_up'
      : quote.phase === 'LIMIT_DOWN'
      ? 'limit_down'
      : quote.phase === 'CALL_AUCTION'
      ? 'call_auction'
      : 'normal';

  return (
    <div className="bg-[#1e222d] border-b border-[#2a2e39] px-3 py-2 select-none">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* 左侧：股票名称、代码与实时大字报价 */}
        <div className="flex items-center gap-4 min-w-0">
          {/* 移动端打开自选股抽屉按钮 */}
          <button
            type="button"
            aria-label="打开自选股切换列表"
            onClick={() => setMobileWatchlistOpen(true)}
            className="md:hidden flex items-center justify-center min-w-[40px] min-h-[40px] rounded bg-[#131722] border border-[#2a2e39] text-[#d1d4dc] hover:text-white cursor-pointer"
          >
            <ListFilter className="w-4 h-4" />
          </button>

          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <h1 className="text-base sm:text-lg font-bold text-white tracking-tight truncate">
                {quote.name}
              </h1>
              <button
                type="button"
                aria-label={isStarred ? '从自选股移除' : '加入自选股'}
                onClick={() => toggleWatchlist(quote.symbol)}
                className="p-1 rounded text-[#787b86] hover:text-[#F59E0B] transition-colors cursor-pointer"
              >
                <Star
                  className={`w-4 h-4 ${
                    isStarred ? 'fill-[#F59E0B] text-[#F59E0B]' : ''
                  }`}
                />
              </button>
              <button
                type="button"
                aria-label="设置价格预警"
                onClick={() => setAlertModalOpen(true)}
                className={`flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium border transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
                  triggeredAlertCount > 0
                    ? 'bg-[#F59E0B]/20 border-[#F59E0B] text-[#F59E0B]'
                    : activeAlertCount > 0
                    ? 'bg-[#131722] border-[#2a2e39] text-[#F59E0B] hover:border-[#F59E0B]'
                    : 'bg-[#131722] border-[#2a2e39] text-[#9ca3af] hover:text-white'
                }`}
              >
                <BellRing className="w-3 h-3" />
                <span>价格预警</span>
                {(activeAlertCount > 0 || triggeredAlertCount > 0) && (
                  <span className="font-mono tabular-nums">
                    ({activeAlertCount})
                  </span>
                )}
              </button>
            </div>
            <div className="flex items-center gap-1.5 text-xs text-[#787b86] font-mono tabular-nums">
              <span>{quote.symbol}</span>
              <span aria-hidden="true">·</span>
              <span className="font-sans">{quote.sector}</span>
            </div>
          </div>

          {/* 核心现价与涨跌幅（带 220ms 硬件加速微闪烁） */}
          <div
            className={`flex items-baseline gap-2.5 px-2.5 py-1 rounded transition-colors duration-200 ${priceFlash}`}
          >
            <span
              data-testid="active-stock-price"
              className={`text-xl sm:text-2xl font-bold font-mono tabular-nums tracking-tight ${priceColor}`}
            >
              {formatPrice(quote.price)}
            </span>
            <div className={`flex flex-col text-xs font-mono tabular-nums font-semibold ${priceColor}`}>
              <span>{formatSignedChange(quote.change)}</span>
              <span>{formatSignedPercent(quote.changePercent)}</span>
            </div>
          </div>
        </div>

        {/* 中部：核心盘面六维行情数据 (3列x2行，标签与数值左右对齐，彻底杜绝窄列挤压重叠) */}
        <div className="grid grid-cols-3 gap-x-5 gap-y-1 text-xs shrink-0 min-w-[290px] sm:min-w-[340px]">
          <div className="flex items-center justify-between gap-2 whitespace-nowrap">
            <span className="text-[#787b86] text-[11px]">今开</span>
            <span className={`font-mono tabular-nums font-medium ${openColor}`}>
              {formatPrice(quote.open)}
            </span>
          </div>
          <div className="flex items-center justify-between gap-2 whitespace-nowrap">
            <span className="text-[#787b86] text-[11px]">最高</span>
            <span className={`font-mono tabular-nums font-medium ${highColor}`}>
              {formatPrice(quote.high)}
            </span>
          </div>
          <div className="flex items-center justify-between gap-2 whitespace-nowrap">
            <span className="text-[#787b86] text-[11px]">换手</span>
            <span className="font-mono tabular-nums font-medium text-[#d1d4dc]">
              {typeof quote.turnoverRate === 'number' ? `${quote.turnoverRate.toFixed(2)}%` : '--'}
            </span>
          </div>
          <div className="flex items-center justify-between gap-2 whitespace-nowrap">
            <span className="text-[#787b86] text-[11px]">最低</span>
            <span className={`font-mono tabular-nums font-medium ${lowColor}`}>
              {formatPrice(quote.low)}
            </span>
          </div>
          <div className="flex items-center justify-between gap-2 whitespace-nowrap">
            <span className="text-[#787b86] text-[11px]">总手</span>
            <span className="font-mono tabular-nums font-medium text-[#d1d4dc]">
              {formatVolumeHands(quote.volume)}
            </span>
          </div>
          <div className="flex items-center justify-between gap-2 whitespace-nowrap">
            <span className="text-[#787b86] text-[11px]">总额</span>
            <span className="font-mono tabular-nums font-medium text-[#d1d4dc]">
              {formatAmountCN(quote.amount)}
            </span>
          </div>
        </div>

        {/* 右侧：Level-1 极端盘口空档保护验证切换器 (正常 / 涨停封板 / 跌停封板 / 集合竞价) */}
        <div className="hidden xl:flex items-center gap-1 bg-[#131722] p-1 rounded border border-[#2a2e39] shrink-0">
          <span className="text-[11px] text-[#787b86] px-1.5 whitespace-nowrap">
            盘口仿真:
          </span>
          {(
            [
              { id: 'normal', label: '连续竞价' },
              { id: 'limit_up', label: '涨停空卖档' },
              { id: 'limit_down', label: '跌停空买档' },
              { id: 'call_auction', label: '集合竞价' },
            ] as { id: MarketScenario; label: string }[]
          ).map((item) => {
            const active = currentScenario === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => triggerScenario(quote.symbol, item.id)}
                className={`px-2 py-0.5 text-[11px] font-medium rounded transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
                  active
                    ? item.id === 'limit_up'
                      ? 'bg-[#F6465D] text-white'
                      : item.id === 'limit_down'
                      ? 'bg-[#0ECB81] text-[#0d0e12]'
                      : 'bg-[#2962ff] text-white'
                    : 'text-[#9ca3af] hover:text-white hover:bg-[#2a2e39]'
                }`}
              >
                {item.label}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
};
