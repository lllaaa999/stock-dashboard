import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Search, Star, ArrowUpDown, X } from 'lucide-react';
import { useMarketStore } from '../store/useMarketStore';
import {
  filterAndSortStocks,
  formatPrice,
  formatSignedPercent,
  getSignedColorClass,
} from '../utils/marketCalc';

interface WatchlistRowProps {
  symbol: string;
  isSelected: boolean;
  isStarred: boolean;
  onSelect: (symbol: string) => void;
  onToggleStar: (symbol: string) => void;
}

/**
 * 单行自选股组件：通过 Zustand 精确 Selector 订阅单只股票，隔离其他股票高频推送
 */
const WatchlistRow: React.FC<WatchlistRowProps> = React.memo(
  ({ symbol, isSelected, isStarred, onSelect, onToggleStar }) => {
    const quote = useMarketStore(useCallback((s) => s.quotes[symbol], [symbol]));
    const prevPriceRef = useRef<number | null>(quote?.price ?? null);
    const [flashBg, setFlashBg] = useState<string>('');

    useEffect(() => {
      if (!quote) return;
      if (prevPriceRef.current !== null && prevPriceRef.current !== quote.price) {
        const isTickUp = quote.price > prevPriceRef.current;
        setFlashBg(isTickUp ? 'bg-[#F6465D]/15' : 'bg-[#0ECB81]/15');
        const timer = setTimeout(() => {
          setFlashBg('');
        }, 220); // 严格 <= 300ms 硬件加速过渡
        prevPriceRef.current = quote.price;
        return () => clearTimeout(timer);
      }
      prevPriceRef.current = quote.price;
    }, [quote?.price, quote]);

    if (!quote) return null;

    const colorClass = getSignedColorClass(quote.change);
    const phaseNote =
      quote.phase === 'LIMIT_UP'
        ? '涨停'
        : quote.phase === 'LIMIT_DOWN'
        ? '跌停'
        : quote.phase === 'CALL_AUCTION'
        ? '竞价'
        : null;

    return (
      <div
        role="row"
        aria-selected={isSelected}
        onClick={() => onSelect(symbol)}
        className={`group flex items-center justify-between px-3 h-[44px] border-b border-[#2a2e39]/60 cursor-pointer select-none transition-colors duration-200 ${
          isSelected
            ? 'bg-[#2962ff]/15'
            : flashBg
            ? flashBg
            : 'hover:bg-[#2a2e39]/40'
        }`}
      >
        {/* 左侧：自选星标 + 股票名称与代码/板块无框元数据 */}
        <div className="flex items-center gap-2 min-w-0">
          <button
            type="button"
            aria-label={isStarred ? `取消自选 ${quote.name}` : `添加自选 ${quote.name}`}
            onClick={(e) => {
              e.stopPropagation();
              onToggleStar(symbol);
            }}
            className="p-1 text-[#787b86] hover:text-[#F59E0B] transition-colors shrink-0 cursor-pointer"
          >
            <Star
              className={`w-3.5 h-3.5 ${
                isStarred ? 'fill-[#F59E0B] text-[#F59E0B]' : ''
              }`}
            />
          </button>

          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-semibold text-[#d1d4dc] truncate">
                {quote.name}
              </span>
              {phaseNote && (
                <span
                  className={`text-[10px] font-medium ${
                    quote.phase === 'LIMIT_UP'
                      ? 'text-[#F6465D]'
                      : quote.phase === 'LIMIT_DOWN'
                      ? 'text-[#0ECB81]'
                      : 'text-[#F59E0B]'
                  }`}
                >
                  · {phaseNote}
                </span>
              )}
            </div>
            <div className="flex items-center gap-1 text-[10px] text-[#787b86] font-mono tabular-nums">
              <span>{quote.code}</span>
              <span aria-hidden="true">·</span>
              <span>{quote.market}</span>
              <span aria-hidden="true">·</span>
              <span className="font-sans truncate">{quote.sector}</span>
            </div>
          </div>
        </div>

        {/* 右侧：最新价与涨跌幅 (严格等宽数字对齐 font-mono tabular-nums) */}
        <div className="flex items-center gap-3 shrink-0">
          <span
            className={`w-16 text-right font-mono tabular-nums text-xs font-semibold ${colorClass}`}
          >
            {formatPrice(quote.price)}
          </span>
          <span
            className={`w-16 text-right font-mono tabular-nums text-xs font-semibold ${colorClass}`}
          >
            {formatSignedPercent(quote.changePercent)}
          </span>
        </div>
      </div>
    );
  }
);
WatchlistRow.displayName = 'WatchlistRow';

export const WatchlistPanel: React.FC = () => {
  const quotes = useMarketStore((s) => s.quotes);
  const symbolOrder = useMarketStore((s) => s.symbolOrder);
  const selectedSymbol = useMarketStore((s) => s.selectedSymbol);
  const watchlist = useMarketStore((s) => s.watchlist);
  const searchQuery = useMarketStore((s) => s.searchQuery);
  const filterCategory = useMarketStore((s) => s.filterCategory);
  const sortBy = useMarketStore((s) => s.sortBy);
  const sortDir = useMarketStore((s) => s.sortDir);

  const setSelectedSymbol = useMarketStore((s) => s.setSelectedSymbol);
  const setSearchQuery = useMarketStore((s) => s.setSearchQuery);
  const setFilterCategory = useMarketStore((s) => s.setFilterCategory);
  const toggleSort = useMarketStore((s) => s.toggleSort);
  const toggleWatchlist = useMarketStore((s) => s.toggleWatchlist);

  // 仅根据过滤/排序条件计算需要渲染的 symbol 列表
  const filteredSymbols = useMemo(() => {
    const allStocks = symbolOrder.map((sym) => quotes[sym]).filter(Boolean);
    const sorted = filterAndSortStocks(
      allStocks,
      searchQuery,
      filterCategory,
      watchlist,
      sortBy,
      sortDir
    );
    return sorted.map((item) => item.symbol);
  }, [quotes, symbolOrder, searchQuery, filterCategory, watchlist, sortBy, sortDir]);

  return (
    <aside
      aria-label="自选股与行情检索列表"
      className="flex flex-col h-full bg-[#1e222d] border-r border-[#2a2e39] select-none"
    >
      {/* 1. 代码 / 拼音首字母快速搜索框 */}
      <div className="p-2.5 border-b border-[#2a2e39] bg-[#131722]/50">
        <div className="relative flex items-center">
          <Search className="w-3.5 h-3.5 text-[#787b86] absolute left-2.5 pointer-events-none" />
          <input
            type="text"
            aria-label="搜索股票代码、名称或拼音首字母"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="代码 / 名称 / 拼音 (如 gzmt, byd)"
            className="w-full pl-8 pr-7 py-1.5 text-xs bg-[#131722] text-[#d1d4dc] placeholder-[#787b86] rounded border border-[#2a2e39] focus:outline-none focus:border-[#2962ff] transition-colors"
          />
          {searchQuery && (
            <button
              type="button"
              aria-label="清空搜索内容"
              onClick={() => setSearchQuery('')}
              className="absolute right-2 p-0.5 text-[#787b86] hover:text-white cursor-pointer"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* 2. 分组筛选按钮 (全部 / 自选 / 涨跌停与竞价) */}
        <div className="flex items-center gap-1 mt-2 p-0.5 bg-[#131722] rounded border border-[#2a2e39]">
          <button
            type="button"
            onClick={() => setFilterCategory('all')}
            className={`flex-1 py-1 text-[11px] font-medium rounded transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
              filterCategory === 'all'
                ? 'bg-[#2a2e39] text-white'
                : 'text-[#787b86] hover:text-[#d1d4dc]'
            }`}
          >
            沪深核心 ({symbolOrder.length})
          </button>
          <button
            type="button"
            onClick={() => setFilterCategory('watchlist')}
            className={`flex-1 py-1 text-[11px] font-medium rounded transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
              filterCategory === 'watchlist'
                ? 'bg-[#2a2e39] text-white'
                : 'text-[#787b86] hover:text-[#d1d4dc]'
            }`}
          >
            我的自选 ({watchlist.length})
          </button>
          <button
            type="button"
            onClick={() => setFilterCategory('special')}
            className={`flex-1 py-1 text-[11px] font-medium rounded transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
              filterCategory === 'special'
                ? 'bg-[#2a2e39] text-[#F59E0B]'
                : 'text-[#787b86] hover:text-[#d1d4dc]'
            }`}
          >
            异动/竞价
          </button>
        </div>
      </div>

      {/* 3. 列头与排序控制 */}
      <div className="flex items-center justify-between px-3 py-1.5 text-[11px] text-[#787b86] border-b border-[#2a2e39] bg-[#131722]/30">
        <span>名称 / 代码</span>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => toggleSort('price')}
            className="w-16 flex items-center justify-end gap-0.5 hover:text-[#d1d4dc] cursor-pointer whitespace-nowrap shrink-0"
          >
            <span>最新价</span>
            <ArrowUpDown className="w-3 h-3" />
          </button>
          <button
            type="button"
            onClick={() => toggleSort('changePercent')}
            className="w-16 flex items-center justify-end gap-0.5 hover:text-[#d1d4dc] cursor-pointer whitespace-nowrap shrink-0"
          >
            <span>涨跌幅</span>
            <ArrowUpDown className="w-3 h-3" />
          </button>
        </div>
      </div>

      {/* 4. 股票高密度滚动列表 */}
      <div className="flex-1 overflow-y-auto" role="rowgroup">
        {filteredSymbols.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-44 px-4 text-center">
            <p className="text-xs text-[#787b86]">
              未找到匹配“{searchQuery || '当前分组'}”的股票标的
            </p>
            <button
              type="button"
              onClick={() => {
                setSearchQuery('');
                setFilterCategory('all');
              }}
              className="mt-2.5 px-3 py-1 text-xs font-medium text-white bg-[#2962ff] rounded hover:bg-[#1e53e5] transition-colors cursor-pointer"
            >
              重置筛选条件
            </button>
          </div>
        ) : (
          filteredSymbols.map((sym) => (
            <WatchlistRow
              key={sym}
              symbol={sym}
              isSelected={sym === selectedSymbol}
              isStarred={watchlist.includes(sym)}
              onSelect={setSelectedSymbol}
              onToggleStar={toggleWatchlist}
            />
          ))
        )}
      </div>
    </aside>
  );
};
