import React, { useState } from 'react';
import { useMarketStore } from '../store/useMarketStore';
import {
  formatAmountCN,
  formatPrice,
  formatVolumeHands,
  getDirectionColorClass,
  getPriceDirection,
} from '../utils/marketCalc';

interface TradeTicksAndMetricsPanelProps {
  forcedTab?: 'trades' | 'fundamentals';
}

export const TradeTicksAndMetricsPanel: React.FC<TradeTicksAndMetricsPanelProps> = ({
  forcedTab,
}) => {
  const [activeSubTab, setActiveSubTab] = useState<'trades' | 'fundamentals'>('trades');
  const currentTab = forcedTab ?? activeSubTab;

  // Zustand 精确订阅当前选中股票的成交明细与盘面指标
  const quote = useMarketStore((s) => s.quotes[s.selectedSymbol]);

  if (!quote) {
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
          <div className="flex items-center gap-2">
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
          <span className="text-[11px] text-[#787b86] font-mono tabular-nums">
            换手 {typeof quote.turnoverRate === 'number' ? `${quote.turnoverRate.toFixed(2)}%` : '--'}
          </span>
        </div>
      )}

      {currentTab === 'trades' ? (
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
      ) : (
        /* 换手率、量比、涨跌停与基本面指标网格 */
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
      )}
    </section>
  );
};
