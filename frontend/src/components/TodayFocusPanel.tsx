import { AlertTriangle, RefreshCw, Sparkles } from 'lucide-react';
import { useMarketStore } from '../store/useMarketStore';
import { useRealFocus } from '../hooks/useRealQuantData';
import type { FocusItem } from '../types/market';
import { formatFocusFact, isFocusEmpty, levelLabel, sortFocusItems } from '../utils/focusUtils';

// 级别色：风险红使用深红 + 橙红描边，避免与 A 股上涨红 #F6465D 混淆
const LEVEL_STYLE: Record<FocusItem['level'], { bar: string; chip: string }> = {
  RED: { bar: 'bg-[#b91c1c]', chip: 'bg-[#7f1d1d] text-[#fecaca] border border-[#ef4444]' },
  YELLOW: { bar: 'bg-[#F59E0B]', chip: 'bg-[#422006] text-[#fcd34d] border border-[#F59E0B]/60' },
  GREEN: { bar: 'bg-[#38bdf8]', chip: 'bg-[#0c2a3a] text-[#7dd3fc] border border-[#38bdf8]/60' },
  INFO: { bar: 'bg-[#4b5563]', chip: 'bg-[#1f2937] text-[#9ca3af] border border-[#4b5563]' },
};

function FocusCard({ item }: { item: FocusItem }) {
  const setSelectedSymbol = useMarketStore((s) => s.setSelectedSymbol);
  const clickable = item.symbols.length > 0;
  const style = LEVEL_STYLE[item.level] ?? LEVEL_STYLE.INFO;
  const isRisk = item.level === 'RED';

  return (
    <div
      data-testid={`focus-card-${item.id}`}
      role={clickable ? 'button' : undefined}
      tabIndex={clickable ? 0 : undefined}
      onClick={clickable ? () => setSelectedSymbol(item.symbols[0]) : undefined}
      onKeyDown={
        clickable
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                setSelectedSymbol(item.symbols[0]);
              }
            }
          : undefined
      }
      className={`flex overflow-hidden rounded-md bg-[#1e222d] border ${
        isRisk ? 'border-[#ef4444]/50' : 'border-[#2a2e39]'
      } ${clickable ? 'cursor-pointer hover:bg-[#262b38]' : ''}`}
    >
      <div className={`w-1.5 shrink-0 ${style.bar}`} />
      <div className="flex-1 min-w-0 p-3 space-y-2">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold shrink-0 ${style.chip}`}>
              {levelLabel(item.level)}
            </span>
            <h3 className="text-sm font-semibold text-white truncate">{item.title}</h3>
          </div>
          <span
            className={`px-1.5 py-0.5 rounded text-[10px] font-mono shrink-0 ${
              item.narrativeSource === 'llm'
                ? 'bg-[#2962ff]/20 text-[#7aa2ff] border border-[#2962ff]/50'
                : 'bg-[#2a2e39] text-[#9ca3af] border border-[#363a45]'
            }`}
          >
            {item.narrativeSource === 'llm' ? 'AI' : '规则'}
          </span>
        </div>

        {item.facts.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {item.facts.map((f, i) => (
              <span
                key={`${f.label}-${i}`}
                className="px-1.5 py-0.5 rounded bg-[#131722] border border-[#2a2e39] text-[11px] text-[#d1d4dc] font-mono tabular-nums"
              >
                {formatFocusFact(f)}
              </span>
            ))}
          </div>
        )}

        {item.narrative && (
          <p className="text-xs leading-relaxed text-[#9ca3af]">{item.narrative}</p>
        )}

        {clickable && (
          <div className="text-[10px] text-[#787b86] font-mono">
            {item.symbols.slice(0, 4).join(' · ')}
            {item.symbols.length > 4 ? ` 等${item.symbols.length}只` : ''}
          </div>
        )}
      </div>
    </div>
  );
}

function Section({
  title,
  items,
  accent,
}: {
  title: string;
  items: FocusItem[];
  accent?: string;
}) {
  const sorted = sortFocusItems(items);
  return (
    <section aria-label={title} className="space-y-2">
      <h2 className={`text-xs font-bold tracking-wide ${accent ?? 'text-[#d1d4dc]'}`}>
        {title} <span className="text-[#787b86] font-mono">({sorted.length})</span>
      </h2>
      {sorted.length === 0 ? (
        <div className="text-xs text-[#787b86] px-3 py-2 rounded bg-[#131722] border border-dashed border-[#2a2e39]">
          暂无
        </div>
      ) : (
        <div className="grid gap-2 grid-cols-1 xl:grid-cols-2">
          {sorted.map((it) => (
            <FocusCard key={it.id} item={it} />
          ))}
        </div>
      )}
    </section>
  );
}

export function TodayFocusPanel() {
  const { focus, loading, error, refresh } = useRealFocus();
  const empty = isFocusEmpty(focus);
  const disclaimer = focus?.disclaimer || '仅供研究，不构成投资建议';

  return (
    <div data-testid="today-focus-panel" className="flex flex-col gap-3 text-[#d1d4dc]">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-[#F59E0B]" />
          <h1 className="text-sm font-bold text-white">今日关注</h1>
        </div>
        <button
          type="button"
          onClick={refresh}
          disabled={loading}
          className="flex items-center gap-1 px-2 py-1 text-[11px] rounded text-[#9ca3af] hover:text-white hover:bg-[#1e222d] cursor-pointer disabled:opacity-50"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
          刷新
        </button>
      </div>

      {error && (
        <div
          role="alert"
          className="flex items-center gap-2 px-3 py-2 rounded text-xs bg-[#2a1a1a] border border-[#ef4444]/40 text-[#fecaca]"
        >
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          {focus ? '今日关注刷新失败，当前显示的是上一次数据。' : '今日关注数据加载失败，请稍后重试。'}
        </div>
      )}

      {loading && !focus && (
        <div className="px-3 py-8 text-center text-xs text-[#787b86] bg-[#131722] border border-[#2a2e39] rounded">
          正在汇总今日关注…
        </div>
      )}

      {focus && (
        <>
          <div
            data-testid="focus-market-tone"
            className="flex overflow-hidden rounded-md bg-[#131722] border border-[#2a2e39]"
          >
            <div className={`w-1.5 shrink-0 ${(LEVEL_STYLE[focus.marketTone?.level] ?? LEVEL_STYLE.INFO).bar}`} />
            <div className="p-3 space-y-1">
              <div className="text-[11px] text-[#787b86]">市场定调</div>
              <div className="text-sm font-bold text-white">{focus.marketTone?.phase || '--'}</div>
              {focus.marketTone?.text && (
                <p className="text-xs leading-relaxed text-[#9ca3af]">{focus.marketTone.text}</p>
              )}
            </div>
          </div>

          {focus.narrativeMode === 'template' && (
            <div className="px-3 py-1.5 rounded text-[11px] bg-[#1e222d] border border-[#2a2e39] text-[#9ca3af]">
              当前为规则模式（未配置 AI Key）
            </div>
          )}

          {empty ? (
            <div className="px-3 py-8 text-center text-xs text-[#787b86] bg-[#131722] border border-[#2a2e39] rounded">
              今日暂无需要特别关注的事项
            </div>
          ) : (
            <>
              <Section title="风险" items={focus.risks} accent="text-[#fca5a5]" />
              <Section title="主线题材" items={focus.themes} />
              <Section title="异动" items={focus.anomalies} />
              <Section title="新闻" items={focus.news} />
            </>
          )}
        </>
      )}

      <p className="text-[11px] text-[#787b86] pt-2 border-t border-[#2a2e39]">⚠ {disclaimer}</p>
    </div>
  );
}
