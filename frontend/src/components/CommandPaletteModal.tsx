import React, { useEffect, useMemo, useRef, useState } from 'react';
import { CornerDownLeft, Keyboard, Search, Sparkles, X } from 'lucide-react';
import { useMarketStore } from '../store/useMarketStore';
import {
  formatPrice,
  formatSignedPercent,
  getSignedColorClass,
} from '../utils/marketCalc';

/**
 * 通达信式键盘精灵 / 全市场极速检索浮层 (Keyboard Sprite & Global Search Palette)
 * 特性：
 * 1. 页面任意位置直接敲击数字代码 (如 002724, 600519) 或拼音首字母 (如 gzmt, byd) 自动唤出并追加字符
 * 2. 支持 ↑ / ↓ 键在候选结果列表中导航，Enter 键一键选中标的并立即切回主图看盘
 * 3. 同时合并本地高速缓存标的与后端 /api/market/search 全市场实时穿透结果
 */
export const CommandPaletteModal: React.FC = () => {
  const isOpen = useMarketStore((s) => s.isCommandPaletteOpen);
  const initialQuery = useMarketStore((s) => s.commandPaletteInitialQuery);
  const setCommandPaletteOpen = useMarketStore((s) => s.setCommandPaletteOpen);
  const quotes = useMarketStore((s) => s.quotes);
  const symbolOrder = useMarketStore((s) => s.symbolOrder);
  const selectAndSubscribeStock = useMarketStore((s) => s.selectAndSubscribeStock);
  const setWorkspaceMode = useMarketStore((s) => s.setWorkspaceMode);

  const [query, setQuery] = useState('');
  const [remoteResults, setRemoteResults] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);

  // 当浮层打开时，注入初始敲击字符并自动聚焦输入框
  useEffect(() => {
    if (isOpen) {
      setQuery(initialQuery || '');
      setActiveIndex(0);
      requestAnimationFrame(() => {
        inputRef.current?.focus();
      });
    } else {
      setQuery('');
      setRemoteResults([]);
    }
  }, [isOpen, initialQuery]);

  // 请求后端全市场搜索接口 /api/market/search
  useEffect(() => {
    if (!isOpen) return;
    const q = query.trim();
    if (!q) {
      setRemoteResults([]);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    const timer = setTimeout(() => {
      fetch(`/api/market/search?q=${encodeURIComponent(q)}`)
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          if (data && data.status === 'ok' && Array.isArray(data.results)) {
            setRemoteResults(data.results);
          }
        })
        .catch((e) => {
          console.error('[CommandPaletteModal] 搜索请求失败:', e);
        })
        .finally(() => setIsLoading(false));
    }, 120);

    return () => clearTimeout(timer);
  }, [isOpen, query]);

  // 合并本地行情池匹配项与远端全市场匹配项
  const mergedCandidates = useMemo(() => {
    const q = query.trim().toLowerCase();
    const localList = symbolOrder
      .map((sym) => quotes[sym])
      .filter(Boolean)
      .filter((item) => {
        if (!q) return true;
        return (
          item.code.toLowerCase().includes(q) ||
          item.symbol.toLowerCase().includes(q) ||
          item.name.toLowerCase().includes(q) ||
          item.pinyin.toLowerCase().includes(q)
        );
      });

    const map = new Map<string, any>();
    for (const loc of localList) {
      map.set(loc.symbol, loc);
    }
    for (const rem of remoteResults) {
      if (rem && rem.symbol && !map.has(rem.symbol)) {
        map.set(rem.symbol, rem);
      }
    }
    return Array.from(map.values()).slice(0, 12);
  }, [query, symbolOrder, quotes, remoteResults]);

  useEffect(() => {
    setActiveIndex(0);
  }, [mergedCandidates.length, query]);

  if (!isOpen) return null;

  const handleConfirmSelect = (item: any) => {
    if (!item) return;
    selectAndSubscribeStock({
      symbol: item.symbol,
      code: item.code,
      name: item.name,
      market: item.market || (item.symbol.endsWith('.SH') ? 'SH' : 'SZ'),
      sector: item.sector || item.securityType || 'A股核心',
    });
    setWorkspaceMode('chart');
    setCommandPaletteOpen(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      setCommandPaletteOpen(false);
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (mergedCandidates.length > 0) {
        setActiveIndex((prev) => (prev + 1) % mergedCandidates.length);
      }
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (mergedCandidates.length > 0) {
        setActiveIndex((prev) => (prev - 1 + mergedCandidates.length) % mergedCandidates.length);
      }
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      const target = mergedCandidates[activeIndex] ?? mergedCandidates[0];
      if (target) {
        handleConfirmSelect(target);
      }
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="通达信式全市场键盘精灵检索"
      data-testid="tdx-command-palette-modal"
      className="fixed inset-0 z-50 flex items-start justify-center pt-16 sm:pt-24 bg-black/75 backdrop-blur-[2px] px-4 select-none"
      onClick={() => setCommandPaletteOpen(false)}
    >
      <div
        className="w-full max-w-lg rounded-lg bg-[#161a24] border border-[#2962ff]/70 shadow-[0_20px_60px_rgba(0,0,0,0.85)] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 顶部输入栏 */}
        <div className="flex items-center gap-2.5 px-3.5 py-3 bg-[#131722] border-b border-[#2a2e39]">
          <Keyboard className="w-4 h-4 text-[#2962ff] shrink-0" />
          <input
            ref={inputRef}
            type="text"
            data-testid="tdx-command-palette-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="通达信键盘精灵：输入 6 位代码或拼音首字母 (如 002724 / gzmt)..."
            className="flex-1 bg-transparent text-sm font-mono text-white placeholder-[#787b86] focus:outline-none"
          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery('')}
              className="p-1 text-[#787b86] hover:text-white cursor-pointer"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
          <span className="px-1.5 py-0.5 rounded bg-[#1e222d] border border-[#2a2e39] text-[10px] font-mono text-[#9ca3af]">
            ESC 关闭
          </span>
        </div>

        {/* 候选标的列表 */}
        <div className="max-h-80 overflow-y-auto divide-y divide-[#2a2e39]/50">
          {mergedCandidates.length === 0 ? (
            <div className="py-10 text-center text-xs text-[#787b86]">
              {isLoading
                ? '正在穿透 TDX 全市场网关检索...'
                : `未找到与 "${query}" 匹配的股票代码或拼音`}
            </div>
          ) : (
            mergedCandidates.map((item, idx) => {
              const liveQuote = quotes[item.symbol];
              const price = liveQuote?.price ?? item.price;
              const changePct = liveQuote?.changePercent ?? item.changePercent ?? 0;
              const isFocused = idx === activeIndex;
              const colorClass = getSignedColorClass(changePct);

              return (
                <div
                  key={item.symbol}
                  role="option"
                  aria-selected={isFocused}
                  onMouseEnter={() => setActiveIndex(idx)}
                  onClick={() => handleConfirmSelect(item)}
                  className={`flex items-center justify-between px-3.5 py-2.5 cursor-pointer transition-colors ${
                    isFocused ? 'bg-[#2962ff]/25 text-white' : 'hover:bg-[#1e222d]'
                  }`}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="font-mono tabular-nums text-xs font-bold text-[#38bdf8] w-20 shrink-0">
                      {item.symbol}
                    </span>
                    <span className="text-xs font-semibold text-white truncate">
                      {item.name}
                    </span>
                    {item.sector && (
                      <span className="px-1.5 py-0.5 rounded bg-[#131722] border border-[#2a2e39] text-[10px] text-[#9ca3af] truncate">
                        {item.sector}
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-3 shrink-0 font-mono tabular-nums text-xs">
                    {price && price > 0 ? (
                      <>
                        <span className={`font-semibold ${colorClass}`}>
                          {formatPrice(price)}
                        </span>
                        <span className={`w-16 text-right font-semibold ${colorClass}`}>
                          {formatSignedPercent(changePct)}
                        </span>
                      </>
                    ) : (
                      <span className="text-[11px] text-[#787b86]">全市场穿透</span>
                    )}
                    {isFocused && (
                      <CornerDownLeft className="w-3.5 h-3.5 text-[#38bdf8]" />
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* 底部快捷键操作提示栏 */}
        <div className="flex items-center justify-between px-3.5 py-2 bg-[#0d0e12] border-t border-[#2a2e39] text-[11px] text-[#787b86]">
          <div className="flex items-center gap-3">
            <span>
              <strong className="text-[#d1d4dc] font-mono">↑/↓</strong> 上下选择
            </span>
            <span>
              <strong className="text-[#d1d4dc] font-mono">Enter</strong> 切入主图
            </span>
            <span>
              <strong className="text-[#d1d4dc] font-mono">Space / F5</strong> 分时/日K秒切
            </span>
          </div>
          <span className="font-mono text-[10px] text-[#38bdf8]">
            TDX Keyboard Sprite
          </span>
        </div>
      </div>
    </div>
  );
};
