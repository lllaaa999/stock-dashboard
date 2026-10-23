import React, { useCallback } from 'react';
import { useMarketStore } from '../store/useMarketStore';
import {
  formatPrice,
  formatSignedChange,
  formatSignedPercent,
  getSignedColorClass,
} from '../utils/marketCalc';

const INDEX_SYMBOLS = [
  '000001.SH',
  '399001.SZ',
  '399006.SZ',
  '000688.SH',
  '000300.SH',
];

const IndexTickerItem: React.FC<{ symbol: string }> = React.memo(({ symbol }) => {
  const indexQuote = useMarketStore(useCallback((s) => s.indices[symbol], [symbol]));
  if (!indexQuote) return null;

  const colorClass = getSignedColorClass(indexQuote.change);

  return (
    <div className="flex items-center gap-2.5 px-3 py-1 border-r border-[#2a2e39] whitespace-nowrap shrink-0">
      <span className="text-xs font-medium text-[#d1d4dc]">
        {indexQuote.name}
      </span>
      <span className={`text-xs font-mono tabular-nums font-semibold ${colorClass}`}>
        {formatPrice(indexQuote.price)}
      </span>
      <span className={`text-[11px] font-mono tabular-nums ${colorClass}`}>
        {formatSignedChange(indexQuote.change)} ({formatSignedPercent(indexQuote.changePercent)})
      </span>
      <span className="hidden lg:inline text-[11px] font-mono tabular-nums text-[#787b86]">
        {indexQuote.amount.toFixed(0)}亿
      </span>
    </div>
  );
});
IndexTickerItem.displayName = 'IndexTickerItem';

export const IndexTickerBar: React.FC = () => {
  return (
    <div
      aria-label="核心大盘指数实时监控条"
      className="flex items-center overflow-x-auto bg-[#131722] border-b border-[#2a2e39] h-8 select-none shrink-0"
    >
      {INDEX_SYMBOLS.map((sym) => (
        <IndexTickerItem key={sym} symbol={sym} />
      ))}
    </div>
  );
};
