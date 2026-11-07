import { useCallback, useEffect, useMemo, useState } from 'react';
import type {
  AuctionRadarMetrics,
  BoardLadderSummary,
  FocusResponse,
  GlobalMarketRadarResponse,
  IntradayRadarResponse,
  RegulatoryEngineResult,
  RegulatoryHistory,
} from '../types/market';

/**
 * 真实量化数据的共享取数钩子。
 *
 * 为什么要有这个：页面里有两处独立计算「连板梯队」、「竞价雷达」和「监管异动」——
 * ① 主图页顶部六维条（UltraShortStockDiagnosticStrip）
 * ② 超短作战室（UltraShortQuantWorkbench）
 * 以前两边各自 `calculateBoardLadderSummary(allQuotes)`（只扫自选股 → 自选没涨停就恒 0 板）
 * 和 `calculateRegulatoryDeviation(quote)`（没有真实 T-1/T-2 → 用 5.2/4.8 占位值）。
 * 现在统一走这里，模块级缓存保证两个组件共用同一份请求结果。
 */

const LADDER_TTL_MS = 60_000;
const REG_TTL_MS = 60_000;
const AUCTION_RADAR_TTL_MS = 15_000;

let auctionRadarCache: { data: AuctionRadarMetrics[] | null; ts: number } = { data: null, ts: 0 };

export function useRealAuctionRadar(): AuctionRadarMetrics[] | null {
  const [data, setData] = useState<AuctionRadarMetrics[] | null>(auctionRadarCache.data);

  useEffect(() => {
    let alive = true;
    if (auctionRadarCache.data && Date.now() - auctionRadarCache.ts < AUCTION_RADAR_TTL_MS) {
      setData(auctionRadarCache.data);
      return () => {
        alive = false;
      };
    }
    fetch('/api/quant/auction_radar')
      .then((res) => (res.ok ? res.json() : null))
      .then((json) => {
        if (!alive || !json || json.status !== 'ok' || !Array.isArray(json.radar_items)) return;
        const items = json.radar_items as AuctionRadarMetrics[];
        auctionRadarCache = { data: items, ts: Date.now() };
        setData(items);
      })
      .catch((e) => {
        console.error('[useRealAuctionRadar] 获取竞价雷达数据失败:', e);
      });
    return () => {
      alive = false;
    };
  }, []);

  return data;
}

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
          history: (() => {
            const hist = (json.history ?? null) as RegulatoryHistory | null;
            const reg = json.regulatory as Record<string, unknown> | null;
            if (!hist || !reg) return hist;
            return {
              ...hist,
              normal_triggers_in_prev_9d:
                typeof reg.normal_triggers_in_prev_9d === 'number'
                  ? reg.normal_triggers_in_prev_9d
                  : hist.normal_triggers_in_prev_9d,
              severe_10d_current_dev:
                typeof reg.severe_10d_current_dev === 'number'
                  ? (reg.severe_10d_current_dev as number) * 100
                  : hist.severe_10d_current_dev,
            };
          })(),
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

/**
 * 批量监管历史（F-13 修复的配套取数）：
 * `/api/quant/regulatory?symbols=A.B,C.D` 一次拿回池内多只票的真实日K口径 T-1/T-2/指数涨幅。
 * 以前只有 selectedSymbol 有真值，池内其它票全部恒 +0.00%，异动判定形同虚设。
 * 后端做了基准指数复用 + 个股并发受限 + 单只失败显式 unknown，这里只负责聚合与缓存。
 */
export interface RealRegulatoryHistoriesState {
  histories: Record<string, RegulatoryHistory>;
  loading: boolean;
}

const histBatchCache = new Map<string, { data: Record<string, RegulatoryHistory>; ts: number }>();
const MAX_HIST_BATCH_CACHE = 12;
const MAX_HIST_BATCH_SYMBOLS = 40;

/** 归一化成后端约定的 key：大写、去重、排序、上限 40 只 */
function normalizeBatchKey(symbols: string[]): string {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of symbols) {
    const s = String(raw || '').trim().toUpperCase();
    if (!s || seen.has(s)) continue;
    seen.add(s);
    out.push(s);
  }
  out.sort();
  return out.slice(0, MAX_HIST_BATCH_SYMBOLS).join(',');
}

export function useRegulatoryHistories(symbols: string[]): RealRegulatoryHistoriesState {
  const rawKey = symbols.join(',');
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const key = useMemo(() => normalizeBatchKey(symbols), [rawKey]);

  const [state, setState] = useState<RealRegulatoryHistoriesState>(() => {
    if (!key) return { histories: {}, loading: false };
    const hit = histBatchCache.get(key);
    return hit ? { histories: hit.data, loading: false } : { histories: {}, loading: true };
  });

  useEffect(() => {
    if (!key) {
      setState({ histories: {}, loading: false });
      return;
    }
    let alive = true;
    const hit = histBatchCache.get(key);
    if (hit && Date.now() - hit.ts < REG_TTL_MS) {
      setState({ histories: hit.data, loading: false });
      return () => {
        alive = false;
      };
    }
    setState((prev) => ({ histories: prev.histories, loading: true }));
    fetch(`/api/quant/regulatory?symbols=${encodeURIComponent(key)}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((json) => {
        if (!alive) return;
        const raw = (json && json.status === 'ok' ? json.histories : null) as
          | Record<string, RegulatoryHistory>
          | null;
        if (!raw) {
          setState({ histories: {}, loading: false });
          return;
        }
        // 统一大写，避免后端 key 与 quote.symbol 大小写不一致导致整池退回估算
        const next: Record<string, RegulatoryHistory> = {};
        for (const [k, v] of Object.entries(raw)) next[String(k).toUpperCase()] = v;
        histBatchCache.set(key, { data: next, ts: Date.now() });
        if (histBatchCache.size > MAX_HIST_BATCH_CACHE) {
          let oldestKey = '';
          let oldestTs = Infinity;
          for (const [k, v] of histBatchCache) {
            if (v.ts < oldestTs) {
              oldestTs = v.ts;
              oldestKey = k;
            }
          }
          if (oldestKey) histBatchCache.delete(oldestKey);
        }
        setState({ histories: next, loading: false });
      })
      .catch((e) => {
        console.error('[useRegulatoryHistories] 获取池内监管历史失败:', e);
        if (alive) setState({ histories: {}, loading: false });
      });
    return () => {
      alive = false;
    };
  }, [key]);

  return state;
}

/**
 * ============================================================
 * 盘中异动与资金流向监控 (Intraday Anomaly & Capital Flow Radar)
 * ============================================================
 */
export interface RealIntradayRadarState {
  radar: IntradayRadarResponse | null;
  loading: boolean;
  refresh: () => void;
}

const INTRADAY_RADAR_TTL_MS = 4_000;
const intradayRadarCache = new Map<string, { data: IntradayRadarResponse; ts: number }>();
const MAX_INTRADAY_RADAR_CACHE = 30;

function setIntradayRadarCache(key: string, data: IntradayRadarResponse) {
  intradayRadarCache.set(key, { data, ts: Date.now() });
  if (intradayRadarCache.size > MAX_INTRADAY_RADAR_CACHE) {
    let oldestKey = '';
    let oldestTs = Infinity;
    for (const [k, v] of intradayRadarCache) {
      if (v.ts < oldestTs) {
        oldestTs = v.ts;
        oldestKey = k;
      }
    }
    if (oldestKey) intradayRadarCache.delete(oldestKey);
  }
}

export function useRealIntradayRadar(
  symbol?: string | null,
  limit: number = 40
): RealIntradayRadarState {
  const cleanSym = (symbol || '').trim();
  const cacheKey = `${cleanSym.toUpperCase()}::${limit}`;

  const [radar, setRadar] = useState<IntradayRadarResponse | null>(() => {
    const hit = intradayRadarCache.get(cacheKey);
    return hit ? hit.data : null;
  });
  const [loading, setLoading] = useState<boolean>(() => {
    const hit = intradayRadarCache.get(cacheKey);
    return !hit;
  });
  const [refreshCount, setRefreshCount] = useState(0);

  const refresh = useCallback(() => {
    intradayRadarCache.delete(cacheKey);
    setRefreshCount((c) => c + 1);
  }, [cacheKey]);

  useEffect(() => {
    let alive = true;

    const hit = intradayRadarCache.get(cacheKey);
    if (hit && Date.now() - hit.ts < INTRADAY_RADAR_TTL_MS) {
      setRadar(hit.data);
      setLoading(false);
    } else {
      setLoading(true);
    }

    const doFetch = async () => {
      try {
        const cached = intradayRadarCache.get(cacheKey);
        if (cached && Date.now() - cached.ts < INTRADAY_RADAR_TTL_MS) {
          if (alive) {
            setRadar(cached.data);
            setLoading(false);
          }
          return;
        }

        const url = cleanSym
          ? `/api/quant/intraday_radar?symbol=${encodeURIComponent(cleanSym)}&limit=${limit}`
          : `/api/quant/intraday_radar?limit=${limit}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        if (!alive) return;
        if (json && json.status === 'ok') {
          const data = json as IntradayRadarResponse;
          setIntradayRadarCache(cacheKey, data);
          setRadar(data);
        } else {
          setRadar(null);
        }
      } catch (e) {
        console.error('[useRealIntradayRadar] 获取盘中异动与资金流向失败:', e);
        if (alive) {
          setRadar((prev) => prev ?? null);
        }
      } finally {
        if (alive) {
          setLoading(false);
        }
      }
    };

    doFetch();

    const intervalTimer = setInterval(() => {
      doFetch();
    }, 6_000);

    return () => {
      alive = false;
      clearInterval(intervalTimer);
    };
  }, [cacheKey, cleanSym, limit, refreshCount]);

  return { radar, loading, refresh };
}


// ==================== AI 今日关注 ====================

const FOCUS_TTL_MS = 60_000;
let focusCache: { data: FocusResponse | null; ts: number } = { data: null, ts: 0 };

/** 北京时间交易时段（工作日 09:15-15:05）粗判，用于决定是否轮询 */
function isChinaTradingHours(now: Date = new Date()): boolean {
  const bj = new Date(now.getTime() + (now.getTimezoneOffset() + 480) * 60_000);
  const day = bj.getDay();
  if (day === 0 || day === 6) return false;
  const minutes = bj.getHours() * 60 + bj.getMinutes();
  return minutes >= 9 * 60 + 15 && minutes <= 15 * 60 + 5;
}

export function useRealFocus(): {
  focus: FocusResponse | null;
  loading: boolean;
  error: boolean;
  refresh: () => void;
} {
  const [focus, setFocus] = useState<FocusResponse | null>(focusCache.data);
  const [loading, setLoading] = useState<boolean>(focusCache.data === null);
  const [error, setError] = useState(false);
  const [refreshCount, setRefreshCount] = useState(0);

  const refresh = useCallback(() => {
    focusCache = { data: focusCache.data, ts: 0 };
    setRefreshCount((c) => c + 1);
  }, []);

  useEffect(() => {
    let alive = true;
    const doFetch = async () => {
      if (focusCache.data && Date.now() - focusCache.ts < FOCUS_TTL_MS) {
        setFocus(focusCache.data);
        setLoading(false);
        return;
      }
      try {
        const res = await fetch('/api/quant/focus');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        if (!alive) return;
        if (json && json.status === 'ok') {
          focusCache = { data: json as FocusResponse, ts: Date.now() };
          setFocus(focusCache.data);
          setError(false);
        } else {
          setError(true);
        }
      } catch (e) {
        console.error('[useRealFocus] 获取今日关注失败:', e);
        if (alive) setError(true);
      } finally {
        if (alive) setLoading(false);
      }
    };

    doFetch();
    const timer = setInterval(() => {
      if (isChinaTradingHours()) doFetch();
    }, FOCUS_TTL_MS);

    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [refreshCount]);

  return { focus, loading, error, refresh };
}


// ==================== 全球宏观与跨市场传导雷达 ====================

const GLOBAL_RADAR_TTL_MS = 10_000;
const GLOBAL_RADAR_POLL_MS = 15_000;
let globalRadarCache: { data: GlobalMarketRadarResponse | null; ts: number } = { data: null, ts: 0 };

export function useRealGlobalRadar(): {
  radar: GlobalMarketRadarResponse | null;
  loading: boolean;
  refresh: () => void;
} {
  const [radar, setRadar] = useState<GlobalMarketRadarResponse | null>(globalRadarCache.data);
  const [loading, setLoading] = useState<boolean>(globalRadarCache.data === null);
  const [refreshCount, setRefreshCount] = useState(0);

  const refresh = useCallback(() => {
    globalRadarCache = { data: globalRadarCache.data, ts: 0 };
    setRefreshCount((c) => c + 1);
  }, []);

  useEffect(() => {
    let alive = true;
    const doFetch = async () => {
      if (globalRadarCache.data && Date.now() - globalRadarCache.ts < GLOBAL_RADAR_TTL_MS) {
        setRadar(globalRadarCache.data);
        setLoading(false);
        return;
      }
      try {
        const res = await fetch('/api/market/global_radar');
        if (!res.ok) throw new Error("HTTP " + res.status);
        const json = await res.json();
        if (!alive) return;
        if (json && json.status === 'ok') {
          globalRadarCache = { data: json as GlobalMarketRadarResponse, ts: Date.now() };
          setRadar(globalRadarCache.data);
        } else {
          setRadar(null);
        }
      } catch (e) {
        console.error('[useRealGlobalRadar] 获取全球宏观与跨市场雷达失败:', e);
        if (alive) {
          setRadar(null);
        }
      } finally {
        if (alive) {
          setLoading(false);
        }
      }
    };

    doFetch();
    const timer = setInterval(() => {
      doFetch();
    }, GLOBAL_RADAR_POLL_MS);

    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [refreshCount]);

  return { radar, loading, refresh };
}
