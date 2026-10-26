import { useEffect, useState } from 'react';
import type {
  BoardLadderSummary,
  RegulatoryEngineResult,
  RegulatoryHistory,
} from '../types/market';

/**
 * 真实量化数据的共享取数钩子。
 *
 * 为什么要有这个：页面里有两处独立计算「连板梯队」和「监管异动」——
 * ① 主图页顶部六维条（UltraShortStockDiagnosticStrip）
 * ② 超短作战室（UltraShortQuantWorkbench）
 * 以前两边各自 `calculateBoardLadderSummary(allQuotes)`（只扫自选股 → 自选没涨停就恒 0 板）
 * 和 `calculateRegulatoryDeviation(quote)`（没有真实 T-1/T-2 → 用 5.2/4.8 占位值）。
 * 现在统一走这里，模块级缓存保证两个组件共用同一份请求结果。
 */

const LADDER_TTL_MS = 60_000;
const REG_TTL_MS = 60_000;

let ladderCache: { data: BoardLadderSummary | null; ts: number } = { data: null, ts: 0 };

export function useRealLadder(): BoardLadderSummary | null {
  const [data, setData] = useState<BoardLadderSummary | null>(ladderCache.data);

  useEffect(() => {
    let alive = true;
    if (ladderCache.data && Date.now() - ladderCache.ts < LADDER_TTL_MS) {
      setData(ladderCache.data);
      return () => {
        alive = false;
      };
    }
    fetch('/api/quant/ladder')
      .then((res) => (res.ok ? res.json() : null))
      .then((json) => {
        if (!alive || !json || json.status !== 'ok') return;
        const summary = json as unknown as BoardLadderSummary;
        ladderCache = { data: summary, ts: Date.now() };
        setData(summary);
      })
      .catch((e) => {
        console.error('[useRealLadder] 获取连板梯队数据失败:', e);
      });
    return () => {
      alive = false;
    };
  }, []);

  return data;
}

export interface RealRegulatoryState {
  regulatory: RegulatoryEngineResult | null;
  history: RegulatoryHistory | null;
  loading: boolean;
}

const regCache = new Map<string, { state: RealRegulatoryState; ts: number }>();
const MAX_REG_CACHE = 30;
function regCacheSet(symbol: string, entry: { state: RealRegulatoryState; ts: number }) {
  regCache.set(symbol, entry);
  if (regCache.size > MAX_REG_CACHE) {
    let oldestKey = '';
    let oldestTs = Infinity;
    for (const [k, v] of regCache) {
      if (v.ts < oldestTs) { oldestTs = v.ts; oldestKey = k; }
    }
    if (oldestKey) regCache.delete(oldestKey);
  }
}

export function useRealRegulatory(symbol?: string | null): RealRegulatoryState {
  const empty: RealRegulatoryState = { regulatory: null, history: null, loading: false };
  const [state, setState] = useState<RealRegulatoryState>(() => {
    if (!symbol) return empty;
    const hit = regCache.get(symbol);
    return hit ? hit.state : { ...empty, loading: true };
  });

  useEffect(() => {
    if (!symbol) {
      setState({ regulatory: null, history: null, loading: false });
      return;
    }
    let alive = true;
    const hit = regCache.get(symbol);
    if (hit && Date.now() - hit.ts < REG_TTL_MS) {
      setState(hit.state);
      return () => {
        alive = false;
      };
    }
    setState({ regulatory: null, history: null, loading: true });
    fetch(`/api/quant/regulatory?symbol=${encodeURIComponent(symbol)}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((json) => {
        if (!alive) return;
        if (!json || json.status !== 'ok') {
          // 取不到就明确置空（UI 显示"—"），绝不拿占位值冒充
          const next = { regulatory: null, history: null, loading: false };
          regCacheSet(symbol, { state: next, ts: Date.now() });
          setState(next);
          return;
        }
        const next: RealRegulatoryState = {
          regulatory: (json.regulatory as RegulatoryEngineResult) ?? null,
          history: (json.history as RegulatoryHistory) ?? null,
          loading: false,
        };
        regCacheSet(symbol, { state: next, ts: Date.now() });
        setState(next);
      })
      .catch((e) => {
        console.error('[useRealRegulatory] 获取监管引擎数据失败:', symbol, e);
        if (alive) setState({ regulatory: null, history: null, loading: false });
      });
    return () => {
      alive = false;
    };
  }, [symbol]);

  return state;
}
