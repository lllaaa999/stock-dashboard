import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useMarketStore } from '../store/useMarketStore';
import type { FormattedOrderBookRow } from '../types/market';
import {
  calculateOrderBookMetrics,
  formatPrice,
  getDirectionColorClass,
  getSignedColorClass,
} from '../utils/marketCalc';

/**
 * 单档盘口行子组件：包含微闪烁 (<=250ms transition-colors duration-200) 与半透明相对深度条 (Volume Depth Bar)
 */
const OrderBookRowItem: React.FC<{ row: FormattedOrderBookRow }> = React.memo(({ row }) => {
  const prevVolRef = useRef<number | null>(row.rawVolume);
  const [flashClass, setFlashClass] = useState<string>('');

  useEffect(() => {
    if (
      prevVolRef.current !== null &&
      row.rawVolume !== null &&
      prevVolRef.current !== row.rawVolume
    ) {
      const nextFlash =
        row.side === 'bid' ? 'bg-[#F6465D]/15' : 'bg-[#0ECB81]/15';
      setFlashClass(nextFlash);
      const timer = setTimeout(() => {
        setFlashClass('');
      }, 220); // 严格小于 300ms 规范上限
      prevVolRef.current = row.rawVolume;
      return () => clearTimeout(timer);
    }
    prevVolRef.current = row.rawVolume;
  }, [row.rawVolume, row.side]);

  const priceColor = getDirectionColorClass(row.priceDirection);
  const depthBgColor =
    row.side === 'bid'
      ? 'rgba(246, 70, 93, 0.16)'
      : 'rgba(14, 203, 129, 0.16)';

  return (
    <div
      className={`relative flex items-center justify-between h-[21px] md:h-[25px] px-3 text-xs select-none transition-colors duration-200 ${flashClass}`}
    >
      {/* 半透明相对挂单量深度条 (Volume Depth Bar) */}
      {row.depthPercent > 0 && (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute right-0 top-[2px] bottom-[2px] transition-transform duration-150 origin-right"
          style={{
            width: `${row.depthPercent}%`,
            backgroundColor: depthBgColor,
          }}
        />
      )}

      {/* 档位标签 (卖五~卖一 / 买一~买五) */}
      <span className="relative z-10 w-10 text-[#9ca3af] font-medium shrink-0">
        {row.label}
      </span>

      {/* 委托价格 (等宽对齐，空档降级为 --) */}
      <span
        className={`relative z-10 w-20 text-right font-mono tabular-nums font-medium ${priceColor}`}
      >
        {row.priceText}
      </span>

      {/* 委托挂单手数 (等宽对齐，空档降级为 --) */}
      <span className="relative z-10 w-20 text-right font-mono tabular-nums text-[#d1d4dc]">
        {row.volumeText}
      </span>
    </div>
  );
});
OrderBookRowItem.displayName = 'OrderBookRowItem';

export const OrderBook5Panel: React.FC = () => {
  // Zustand 精确订阅当前股票的盘口与基础价格字段
  const symbol = useMarketStore((s) => s.selectedSymbol);
  const orderBook = useMarketStore((s) => s.quotes[s.selectedSymbol]?.orderBook);
  const prevClose = useMarketStore((s) => s.quotes[s.selectedSymbol]?.prevClose ?? 0);
  const latestPrice = useMarketStore((s) => s.quotes[s.selectedSymbol]?.price ?? 0);
  const phase = useMarketStore((s) => s.quotes[s.selectedSymbol]?.phase ?? 'TRADING');

  const metrics = useMemo(
    () => calculateOrderBookMetrics(orderBook, prevClose),
    [orderBook, prevClose]
  );

  const imbalanceColor = getSignedColorClass(metrics.imbalanceRatio);

  const phaseLabel =
    phase === 'LIMIT_UP'
      ? '涨停封板 · 卖盘空档保护'
      : phase === 'LIMIT_DOWN'
      ? '跌停封板 · 买盘空档保护'
      : phase === 'CALL_AUCTION'
      ? '集合竞价 · 3-5档空档保护'
      : '连续竞价 · L1五档';

  return (
    <section
      aria-label="五档盘口与委比委差监控"
      className="flex flex-col bg-[#1e222d] border-b border-[#2a2e39]"
    >
      {/* 顶部标题与当前盘口状态说明 */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-[#2a2e39]">
        <span className="text-xs font-semibold text-[#d1d4dc] tracking-wide">
          五档盘口 ({symbol})
        </span>
        <span className="text-[11px] text-[#787b86] font-mono tabular-nums">
          {phaseLabel}
        </span>
      </div>

      {/* 委比 / 委差实时计算条 */}
      <div className="px-3 py-2 bg-[#131722]/60 border-b border-[#2a2e39]">
        <div className="flex items-center justify-between text-xs mb-1.5">
          <div className="flex items-center gap-1.5">
            <span className="text-[#787b86]">委比</span>
            <span className={`font-mono tabular-nums font-semibold ${imbalanceColor}`}>
              {metrics.imbalanceRatioText}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[#787b86]">委差</span>
            <span className={`font-mono tabular-nums font-semibold ${imbalanceColor}`}>
              {metrics.imbalanceVolumeText}
            </span>
          </div>
        </div>

        {/* 红买绿卖委比力量对比条 */}
        <div className="flex items-center h-1.5 w-full rounded-sm overflow-hidden bg-[#2a2e39]">
          <div
            className="h-full bg-[#F6465D] transition-all duration-200"
            style={{ width: `${metrics.bidPowerPercent}%` }}
          />
          <div
            className="h-full bg-[#0ECB81] transition-all duration-200"
            style={{ width: `${100 - metrics.bidPowerPercent}%` }}
          />
        </div>

        <div className="flex items-center justify-between text-[10px] text-[#787b86] font-mono tabular-nums mt-1">
          <span>买盘总挂: {metrics.totalBidVolume.toLocaleString('en-US')}手</span>
          <span>卖盘总挂: {metrics.totalAskVolume.toLocaleString('en-US')}手</span>
        </div>
      </div>

      {/* 表头列说明 */}
      <div className="flex items-center justify-between px-3 py-1 text-[11px] text-[#787b86] border-b border-[#2a2e39]/60">
        <span className="w-10">档位</span>
        <span className="w-20 text-right">委托价</span>
        <span className="w-20 text-right">挂单量(手)</span>
      </div>

      {/* 卖盘五档：卖五 -> 卖一（由高到低排列） */}
      <div className="py-1" data-testid="orderbook-asks">
        {metrics.asksTopToBottom.map((row) => (
          <OrderBookRowItem key={`ask-${row.level}`} row={row} />
        ))}
      </div>

      {/* 买卖盘中轴最新成交价分割带 */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-[#131722] border-y border-[#2a2e39] text-xs">
        <span className="text-[#787b86] text-[11px]">最新撮合</span>
        <span
          className={`font-mono tabular-nums font-bold text-sm ${getSignedColorClass(
            latestPrice - prevClose
          )}`}
        >
          {formatPrice(latestPrice)}
        </span>
        <span className="text-[11px] text-[#787b86] font-mono tabular-nums">
          昨收 {formatPrice(prevClose)}
        </span>
      </div>

      {/* 买盘五档：买一 -> 买五（由高到低排列） */}
      <div className="py-1" data-testid="orderbook-bids">
        {metrics.bidsTopToBottom.map((row) => (
          <OrderBookRowItem key={`bid-${row.level}`} row={row} />
        ))}
      </div>
    </section>
  );
};
