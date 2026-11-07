import React, { useCallback, useMemo, useState } from 'react';
import { Globe } from 'lucide-react';
import { useMarketStore } from '../store/useMarketStore';
import { useRealGlobalRadar } from '../hooks/useRealQuantData';
import type { GlobalAssetQuote } from '../types/market';
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

const DEFAULT_GLOBAL_ANCHORS: GlobalAssetQuote[] = [
  { symbol: 'CN50', name: '富时A50', category: 'ASIA_CORE', price: 13245.0, change: 48.0, changePercent: 0.36 },
  { symbol: 'HSTECH', name: '恒生科技', category: 'ASIA_CORE', price: 4482.1, change: 56.2, changePercent: 1.27 },
  { symbol: 'IXIC', name: '纳斯达克', category: 'US_EU_INDICES', price: 18983.5, change: 142.3, changePercent: 0.75 },
  { symbol: 'NVDA', name: '英伟达', category: 'TECH_GIANTS', price: 138.25, change: 3.75, changePercent: 2.78 },
  { symbol: 'TSLA', name: '特斯拉', category: 'TECH_GIANTS', price: 262.10, change: 10.65, changePercent: 4.23 },
  { symbol: 'GC', name: 'COMEX黄金', category: 'COMMODITIES', price: 2742.6, change: 14.8, changePercent: 0.54 },
  { symbol: 'CL', name: 'WTI原油', category: 'COMMODITIES', price: 71.45, change: -0.62, changePercent: -0.86 },
  { symbol: 'USDCNH', name: '离岸人民币', category: 'FOREX', price: 7.2415, change: -0.0125, changePercent: -0.17 },
];

const IndexTickerItem: React.FC<{ symbol: string }> = React.memo(({ symbol }) => {
  const indexQuote = useMarketStore(useCallback((s) => s.indices[symbol], [symbol]));
  if (!indexQuote) return null;

  const colorClass = getSignedColorClass(indexQuote.change);

  return (
    <div className="flex items-center gap-2 px-3 py-1 border-r border-[#2a2e39] whitespace-nowrap shrink-0">
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

const GlobalTickerItem: React.FC<{ asset: GlobalAssetQuote }> = React.memo(({ asset }) => {
  const colorClass = getSignedColorClass(asset.changePercent ?? asset.change);
  const formattedPrice =
    asset.price > 1000
      ? asset.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
      : asset.price.toFixed(asset.price < 10 ? 4 : 2);

  return (
    <div className="flex items-center gap-2 px-3 py-1 border-r border-[#2a2e39] whitespace-nowrap shrink-0 hover:bg-[#1e222d]/60 transition-colors">
      <span className="text-xs font-medium text-[#d1d4dc]">
        {asset.name}
      </span>
      <span className={`text-xs font-mono tabular-nums font-semibold ${colorClass}`}>
        {formattedPrice}
      </span>
      <span className={`text-[11px] font-mono tabular-nums font-medium ${colorClass}`}>
        {formatSignedPercent(asset.changePercent)}
      </span>
    </div>
  );
});
GlobalTickerItem.displayName = 'GlobalTickerItem';

export const IndexTickerBar: React.FC = () => {
  const [tickerMode, setTickerMode] = useState<'A_SHARE' | 'GLOBAL'>('A_SHARE');
  const { radar } = useRealGlobalRadar();

  const globalAnchorAssets = useMemo(() => {
    if (radar?.assets && radar.assets.length > 0) {
      // 优先提取富时A50、恒生科技、纳斯达克、英伟达、特斯拉、黄金、原油、离岸人民币
      const anchorKeys = ['A50', '恒生科技', '纳斯达克', '英伟达', '特斯拉', '黄金', '原油', '人民币', 'USDCNH', 'GC', 'CL', 'NVDA', 'TSLA'];
      const matched = radar.assets.filter((a) =>
        anchorKeys.some((k) => a.symbol.toUpperCase().includes(k.toUpperCase()) || a.name.includes(k))
      );
      if (matched.length >= 4) {
        return matched;
      }
      return radar.assets.slice(0, 10);
    }
    return DEFAULT_GLOBAL_ANCHORS;
  }, [radar?.assets]);

  const handleOpenGlobalWorkbench = useCallback(() => {
    useMarketStore.getState().openQuantModule('global');
  }, []);

  return (
    <div
      aria-label="核心大盘与全球风向标实时监控条"
      className="flex items-center justify-between overflow-hidden bg-[#131722] border-b border-[#2a2e39] h-8 select-none shrink-0 px-1"
    >
      <div className="flex items-center overflow-x-auto scrollbar-none flex-1 min-w-0">
        {/* 胶囊切换按钮 */}
        <div className="flex items-center bg-[#1e222d] p-0.5 rounded border border-[#2a2e39] mx-1 shrink-0 text-xs">
          <button
            type="button"
            onClick={() => setTickerMode('A_SHARE')}
            className={`px-2 py-0.5 text-[11px] rounded transition-colors cursor-pointer ${
              tickerMode === 'A_SHARE'
                ? 'bg-[#2962ff] text-white font-medium shadow-sm'
                : 'text-[#848e9c] hover:text-[#d1d4dc]'
            }`}
          >
            A股核心
          </button>
          <button
            type="button"
            onClick={() => setTickerMode('GLOBAL')}
            className={`px-2 py-0.5 text-[11px] rounded transition-colors cursor-pointer flex items-center gap-1 ${
              tickerMode === 'GLOBAL'
                ? 'bg-[#2962ff] text-white font-medium shadow-sm'
                : 'text-[#848e9c] hover:text-[#d1d4dc]'
            }`}
          >
            <span>🌍 全球风向标</span>
          </button>
        </div>

        {/* 内容展示 */}
        {tickerMode === 'A_SHARE' ? (
          <div className="flex items-center">
            {INDEX_SYMBOLS.map((sym) => (
              <IndexTickerItem key={sym} symbol={sym} />
            ))}
            {/* 宽屏同屏滚发展示核心全球锚点 */}
            <div className="hidden 2xl:flex items-center border-l border-[#2a2e39] ml-1 pl-1">
              <span className="text-[10px] text-[#787b86] px-1 font-mono">全球先行:</span>
              {globalAnchorAssets.slice(0, 4).map((asset) => (
                <GlobalTickerItem key={asset.symbol} asset={asset} />
              ))}
            </div>
          </div>
        ) : (
          <div className="flex items-center">
            {globalAnchorAssets.map((asset) => (
              <GlobalTickerItem key={asset.symbol} asset={asset} />
            ))}
          </div>
        )}
      </div>

      {/* 右侧直达全球传导面板按钮 */}
      <div className="flex items-center pl-2 shrink-0">
        <button
          type="button"
          onClick={handleOpenGlobalWorkbench}
          title="点击打开超短工作台「全球跨市场传导」深度解析面板"
          className="flex items-center gap-1 px-2.5 py-0.5 text-xs font-medium rounded bg-[#2962ff]/15 hover:bg-[#2962ff]/25 text-[#2962ff] hover:text-[#5c8aff] border border-[#2962ff]/30 transition-all cursor-pointer whitespace-nowrap shadow-sm"
        >
          <Globe className="w-3.5 h-3.5" />
          <span>🌍 全球传导</span>
          {radar?.summary?.riskAppetiteLabel && (
            <span
              className={`hidden sm:inline text-[10px] px-1.5 py-0.2 rounded font-normal font-mono ${
                radar.summary.globalRiskAppetite === 'RISK_ON'
                  ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                  : radar.summary.globalRiskAppetite === 'RISK_OFF'
                  ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                  : 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
              }`}
            >
              {radar.summary.riskAppetiteLabel}
            </span>
          )}
        </button>
      </div>
    </div>
  );
};
