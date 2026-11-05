import React, { useEffect, useState } from 'react';

interface PulseState {
  emotion?: { score?: number; band?: string; zt?: number; dt?: number; max_lb?: number } | null;
  strategic_decision?: { phase?: { posture?: string; pos_pct?: number; title?: string } } | null;
  sectors?: { inflow?: { name?: string; pct?: number }[] } | null;
  margin?: { net_3d?: number | null } | null;
  news?: { title?: string }[] | null;
  updated?: string;
}

/**
 * 大盘情绪、战略仓位、行业资金、两融与快讯。数据来自 /api/market。
 */
export const MarketPulseStrip: React.FC = () => {
  const [data, setData] = useState<PulseState | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () => {
      fetch('/api/market')
        .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
        .then((json) => {
          if (!alive) return;
          setData(json);
          setError(null);
        })
        .catch(() => {
          if (alive) setError('大盘接口暂不可用');
        });
    };
    load();
    const timer = window.setInterval(load, 60_000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  const emo = data?.emotion;
  const sector = data?.sectors?.inflow?.[0];
  const newsTitle = Array.isArray(data?.news) ? data?.news?.[0]?.title : undefined;
  const phase = data?.strategic_decision?.phase;
  const advice = phase
    ? `${phase.title || ''}${phase.posture ? ` · ${phase.posture}` : ''}${
        typeof phase.pos_pct === 'number' ? ` ${phase.pos_pct}%` : ''
      }`
    : '';

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-1.5 bg-[#131722] border-b border-[#2a2e39] text-[11px] text-[#9ca3af] shrink-0 overflow-x-auto">
      <span className="text-[#787b86]">大盘</span>
      {error && !data ? (
        <span>{error}</span>
      ) : (
        <>
          <span>
            情绪{' '}
            <strong className="text-white">
              {emo?.band || '—'}
              {typeof emo?.score === 'number' ? ` ${emo.score.toFixed(1)}` : ''}
            </strong>
            {emo?.zt != null && (
              <span className="ml-1 font-mono">
                涨停{emo.zt} 跌停{emo.dt ?? '—'} 最高{emo.max_lb ?? '—'}板
              </span>
            )}
          </span>
          <span>
            仓位 <strong className="text-[#F59E0B]">{advice || '—'}</strong>
          </span>
          <span>
            行业{' '}
            <strong className="text-white">
              {sector?.name || '—'}
              {typeof sector?.pct === 'number' ? ` ${sector.pct.toFixed(2)}%` : ''}
            </strong>
          </span>
          <span>
            两融3日{' '}
            <strong className="font-mono text-white">
              {typeof data?.margin?.net_3d === 'number' ? `${data.margin.net_3d > 0 ? '+' : ''}${data.margin.net_3d}亿` : '—'}
            </strong>
          </span>
          {newsTitle && <span className="truncate max-w-[280px]">{newsTitle}</span>}
        </>
      )}
    </div>
  );
};
