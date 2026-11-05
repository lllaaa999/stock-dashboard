import React, { useEffect, useState } from 'react';

interface Hologram {
  today_flow?: { main_net?: number; source?: string };
  announcements?: { date?: string; title?: string }[];
  ultrashort?: {
    dvr?: { label?: string; dvr?: number };
    headroom?: { safe_price?: number; action_advice?: string; normal_triggers_in_prev_9d?: number };
  };
  chan?: { status?: string } | null;
}

/**
 * 个股全息：主力净流入、公告、下行方差与异动安全价。数据来自 /api/stock/{code}。
 */
export const StockHologramBar: React.FC<{ symbol: string }> = ({ symbol }) => {
  const [data, setData] = useState<Hologram | null>(null);

  useEffect(() => {
    const code = (symbol || '').replace(/\.(SH|SZ|BJ|SS)$/i, '');
    if (!/^\d{6}$/.test(code)) {
      setData(null);
      return;
    }
    let alive = true;
    fetch(`/api/stock/${code}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((json) => {
        if (alive) setData(json);
      })
      .catch(() => {
        if (alive) setData(null);
      });
    return () => {
      alive = false;
    };
  }, [symbol]);

  const flow = data?.today_flow;
  const dvr = data?.ultrashort?.dvr;
  const head = data?.ultrashort?.headroom;
  const anns = (data?.announcements || []).slice(0, 2);

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-1.5 border-t border-[#2a2e39] bg-[#161a24] text-[11px] text-[#9ca3af] shrink-0">
      <span>
        主力净流入{' '}
        <strong className="font-mono text-white">
          {typeof flow?.main_net === 'number' ? `${flow.main_net > 0 ? '+' : ''}${flow.main_net}亿` : '—'}
        </strong>
      </span>
      <span>
        承接{' '}
        <strong className="text-white">
          {dvr?.label || '—'}
          {typeof dvr?.dvr === 'number' ? ` ${dvr.dvr.toFixed(2)}` : ''}
        </strong>
      </span>
      <span>
        安全价{' '}
        <strong className="font-mono text-[#F59E0B]">
          {typeof head?.safe_price === 'number' ? head.safe_price.toFixed(2) : '—'}
        </strong>
        {typeof head?.normal_triggers_in_prev_9d === 'number' && (
          <span className="ml-1">近9日异动{head.normal_triggers_in_prev_9d}次</span>
        )}
      </span>
      {anns.map((a, i) => (
        <span key={`${a.date}-${i}`} className="truncate max-w-[320px]">
          {a.date ? `${a.date} ` : ''}
          {a.title}
        </span>
      ))}
    </div>
  );
};
