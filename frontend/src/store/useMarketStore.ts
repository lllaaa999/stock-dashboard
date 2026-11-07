import { create } from 'zustand';
import {
  applyScenarioToQuote,
  createInitialIndices,
  createInitialQuotes,
} from '../data/seedMarket';
import { marketWsClient } from '../services/wsClient';
import type {
  AlertConditionType,
  ChartPeriod,
  ConnectionStatus,
  FullMarketScanData,
  IntradayPoint,
  MainIndicator,
  MarketIndexQuote,
  MarketScenario,
  PriceAlertRule,
  QuantModuleTabId,
  SubIndicator,
  TickData,
  TriggeredAlertEvent,
} from '../types/market';

/**
 * 原生 Canvas 图表命令式订阅通道 (Imperative Chart Update Bus)
 * 当 WebSocket 收到高频快照时，直接通知原生 Canvas 图表实例执行 updateData(tick)，
 * 彻底绕过 React Virtual DOM Diff 与组件重渲染。
 */
type TickListener = (tick: TickData) => void;
const symbolTickListeners = new Map<string, Set<TickListener>>();

type SubscriptionListener = (symbol: string) => void;
var onSymbolSubscribed: SubscriptionListener | null = null;
export function setSymbolSubscriptionHandler(fn: SubscriptionListener) {
  onSymbolSubscribed = fn;
}

export function subscribeSymbolImperativeTick(symbol: string, listener: TickListener): () => void {
  let set = symbolTickListeners.get(symbol);
  if (!set) {
    set = new Set();
    symbolTickListeners.set(symbol, set);
  }
  set.add(listener);
  return () => {
    const currentSet = symbolTickListeners.get(symbol);
    if (currentSet) {
      currentSet.delete(listener);
      if (currentSet.size === 0) {
        symbolTickListeners.delete(symbol);
      }
    }
  };
}

function emitImperativeTick(tick: TickData): void {
  const listeners = symbolTickListeners.get(tick.symbol);
  if (listeners) {
    listeners.forEach((fn) => fn(tick));
  }
}

const DEFAULT_WATCHLIST = [
  '600519.SH',
  '300750.SZ',
  '002594.SZ',
  '688981.SH',
  '601360.SH',
  '002230.SZ',
  '300059.SZ',
  '000651.SZ',
];

const DEFAULT_ALERT_RULES: PriceAlertRule[] = [
  {
    id: 'seed-alert-1',
    symbol: '600519.SH',
    stockName: '贵州茅台',
    condition: 'CHANGE_PCT_ABOVE',
    threshold: 5.0,
    enabled: true,
    triggered: false,
    createdAt: Date.now() - 3600000,
  },
  {
    id: 'seed-alert-2',
    symbol: '600519.SH',
    stockName: '贵州茅台',
    condition: 'CHANGE_PCT_BELOW',
    threshold: -2.0,
    enabled: true,
    triggered: false,
    createdAt: Date.now() - 1800000,
  },
  {
    id: 'seed-alert-3',
    symbol: '002594.SZ',
    stockName: '比亚迪',
    condition: 'CHANGE_PCT_ABOVE',
    threshold: 4.5,
    enabled: true,
    triggered: false,
    createdAt: Date.now() - 900000,
  },
];

function loadSavedWatchlist(): string[] {
  try {
    if (typeof localStorage === 'undefined') return DEFAULT_WATCHLIST;
    const saved = localStorage.getItem('alphapulse_watchlist_v1');
    if (saved) {
      const parsed = JSON.parse(saved);
      if (Array.isArray(parsed) && parsed.length > 0) {
        return parsed;
      }
    }
  } catch (e) {
    console.error('[loadSavedWatchlist] localStorage 读取失败，使用默认自选股:', e);
  }
  return DEFAULT_WATCHLIST;
}

function loadSavedAlerts(): PriceAlertRule[] {
  try {
    if (typeof localStorage === 'undefined') return DEFAULT_ALERT_RULES;
    const saved = localStorage.getItem('alphapulse_alerts_v1');
    if (saved) {
      const parsed = JSON.parse(saved);
      if (Array.isArray(parsed)) {
        return parsed;
      }
    }
  } catch (e) {
    console.error('[loadSavedAlerts] localStorage 读取失败，使用默认预警规则:', e);
  }
  return DEFAULT_ALERT_RULES;
}

function persistAlerts(rules: PriceAlertRule[]): void {
  try {
    if (typeof localStorage === 'undefined') return;
    localStorage.setItem('alphapulse_alerts_v1', JSON.stringify(rules));
  } catch (e) {
    console.error('[persistAlerts] localStorage 写入失败:', e);
  }
}

export interface MarketStoreState {
  // 行情字典（以 symbol 为 key，方便子组件通过 s => s.quotes[symbol] 精确订阅）
  quotes: Record<string, TickData>;
  indices: Record<string, MarketIndexQuote>;
  symbolOrder: string[];

  // 当前选中的股票与图表配置
  selectedSymbol: string;
  period: ChartPeriod;
  mainIndicator: MainIndicator;
  subIndicator: SubIndicator;

  // 自选股与左侧列表检索状态
  watchlist: string[];
  searchQuery: string;
  filterCategory: 'all' | 'watchlist' | 'special';
  sortBy: 'default' | 'price' | 'changePercent';
  sortDir: 'asc' | 'desc';

  // 价格与涨跌幅预警规则状态
  alertRules: PriceAlertRule[];
  triggeredAlerts: TriggeredAlertEvent[];
  isAlertModalOpen: boolean;

  // 移动端底部面板与抽屉状态
  mobileBottomTab: 'orderbook' | 'trades' | 'fundamentals' | 'quant';
  isMobileWatchlistOpen: boolean;
  isArchModalOpen: boolean;

  // 超短游资量化工作台模式与子模块切换
  workspaceMode: 'chart' | 'auction' | 'quant' | 'screener';
  isCommandPaletteOpen: boolean;
  commandPaletteInitialQuery: string;
  quantModuleTab: QuantModuleTabId;

  // WebSocket 连接与节流监控状态
  connectionStatus: ConnectionStatus;
  batchWindowMs: number;
  lastServerTime: number;

  // Actions
  setSelectedSymbol: (symbol: string) => void;
  setPeriod: (period: ChartPeriod) => void;
  setMainIndicator: (indicator: MainIndicator) => void;
  setSubIndicator: (indicator: SubIndicator) => void;
  setSearchQuery: (query: string) => void;
  setFilterCategory: (category: 'all' | 'watchlist' | 'special') => void;
  toggleSort: (field: 'price' | 'changePercent') => void;
  toggleWatchlist: (symbol: string) => void;
  setMobileBottomTab: (tab: 'orderbook' | 'trades' | 'fundamentals' | 'quant') => void;
  setMobileWatchlistOpen: (open: boolean) => void;
  setArchModalOpen: (open: boolean) => void;
  setAlertModalOpen: (open: boolean) => void;
  setWorkspaceMode: (mode: 'chart' | 'auction' | 'quant' | 'screener') => void;
  setCommandPaletteOpen: (open: boolean, initialQuery?: string) => void;
  stepSelectedSymbol: (delta: 1 | -1) => void;
  togglePeriodIntradayDaily: () => void;
  setQuantModuleTab: (tab: QuantModuleTabId) => void;
  openQuantModule: (tab: QuantModuleTabId, symbol?: string) => void;
  setConnectionStatus: (status: ConnectionStatus) => void;
  setBatchWindowMs: (ms: number) => void;
  injectQuote: (quote: TickData) => void;
  selectAndSubscribeStock: (stock: Partial<TickData> & { symbol: string }) => void;
  intradayPointsMap: Record<string, IntradayPoint[]>;
  setIntradayPoints: (symbol: string, points: IntradayPoint[]) => void;
  fetchIntraday: (symbol: string) => Promise<IntradayPoint[]>;
  realThemeData: any | null;
  fetchThemeResonance: () => Promise<void>;

  // 价格预警管理 Actions
  addAlertRule: (input: {
    symbol: string;
    stockName: string;
    condition: AlertConditionType;
    threshold: number;
  }) => PriceAlertRule;
  removeAlertRule: (id: string) => void;
  toggleAlertRule: (id: string) => void;
  resetAlertRule: (id: string) => void;
  markRulesTriggered: (
    triggeredList: {
      ruleId: string;
      price: number;
      changePercent: number;
      message: string;
      timestamp: number;
    }[]
  ) => void;
  dismissTriggeredAlert: (eventId: string) => void;
  clearAllTriggeredAlerts: () => void;

  // 批量合并服务端快照
  applyInitSnapshot: (
    quotes: TickData[],
    indices: MarketIndexQuote[],
    batchWindowMs: number,
    serverTime: number
  ) => void;
  applySnapshotBatch: (
    quotesBatch: TickData[],
    indicesBatch: MarketIndexQuote[],
    batchWindowMs: number,
    serverTime: number
  ) => void;
  triggerScenario: (symbol: string, scenario: MarketScenario) => Promise<void>;

  // 错误通知 (非侵入式 toast)
  errorToasts: ErrorToast[];
  pushErrorToast: (message: string, opts?: { severity?: 'error' | 'warning'; durationMs?: number }) => void;
  dismissErrorToast: (id: string) => void;

  // 首屏种子数据标记（WebSocket 首次收到真实数据后置 false）
  isDemoData: boolean;

  // 全市场竞价扫描数据
  fullMarketScanData: FullMarketScanData | null;
  fetchFullMarketScan: () => Promise<void>;
}

export interface ErrorToast {
  id: string;
  message: string;
  severity: 'error' | 'warning';
  createdAt: number;
  durationMs: number;
}

let errorToastSeq = 0;
/** 在 React 组件外推送错误 toast 的便捷函数 */
export function pushErrorToast(message: string, opts?: { severity?: 'error' | 'warning'; durationMs?: number }) {
  useMarketStore.getState().pushErrorToast(message, opts);
}

/** 6 位代码补交易所后缀。920/4/8 为北交所，且必须先于「9=沪市」。裸 000001 仍是平安（.SZ）。 */
export function normalizeExchangeSymbol(raw: string): string {
  const s = String(raw || '').trim().toUpperCase();
  if (!s) return s;
  if (s.endsWith('.SS')) return s.slice(0, -3) + '.SH';
  if (/\.(SH|SZ|BJ)$/.test(s)) return s;
  const m = s.match(/^(?:SH|SZ|BJ)?(\d{6})$/);
  if (!m) return s;
  const code = m[1];
  const head = s.replace(code, '');
  if (head === 'SH') return `${code}.SH`;
  if (head === 'SZ') return `${code}.SZ`;
  if (head === 'BJ') return `${code}.BJ`;
  if (code.startsWith('920') || code.startsWith('4') || code.startsWith('8')) return `${code}.BJ`;
  if (code.startsWith('6') || code.startsWith('5') || code.startsWith('9')) return `${code}.SH`;
  return `${code}.SZ`;
}

function createPlaceholderQuote(stock: Partial<TickData> & { symbol: string }): TickData {
  const p = typeof stock.price === 'number' && Number.isFinite(stock.price) && stock.price > 0 ? stock.price : 10.0;
  const prev = typeof stock.prevClose === 'number' && Number.isFinite(stock.prevClose) && stock.prevClose > 0 ? stock.prevClose : p;
  const chg = typeof stock.change === 'number' ? stock.change : Number((p - prev).toFixed(2));
  const chgPct = typeof stock.changePercent === 'number' ? stock.changePercent : (prev > 0 ? Number(((chg / prev) * 100).toFixed(2)) : 0);

  return {
    symbol: stock.symbol,
    code: stock.code || stock.symbol.replace(/\.(SH|SZ|BJ)$/i, ''),
    market: (stock.market || (stock.symbol.endsWith('.SH') ? 'SH' : 'SZ')) as any,
    name: stock.name || stock.symbol,
    pinyin: stock.pinyin || '',
    sector: stock.sector || 'A股核心',
    price: p,
    prevClose: prev,
    open: stock.open ?? p,
    high: stock.high ?? p,
    low: stock.low ?? p,
    change: chg,
    changePercent: chgPct,
    volume: stock.volume ?? 0,
    amount: stock.amount ?? 0,
    turnoverRate: stock.turnoverRate ?? 0,
    volumeRatio: stock.volumeRatio ?? 1.0,
    amplitude: stock.amplitude ?? 0,
    // 基本面占位值不能编：全链路单位统一是「亿元」（seed: 19880 / 后端: 16660.34），
    // 之前兜底写 1e10（元），显示成 "10000000000亿"；PE/PB 也不该给默认 15.0/1.5。
    // 统一置 0，由面板按 <=0 显示 "--"。
    peTtm: stock.peTtm ?? 0,
    pb: stock.pb ?? 0,
    marketCap: stock.marketCap ?? 0,
    floatMarketCap: stock.floatMarketCap ?? 0,
    outerVolume: stock.outerVolume ?? 0,
    innerVolume: stock.innerVolume ?? 0,
    limitUpPrice: stock.limitUpPrice ?? Number((prev * 1.1).toFixed(2)),
    limitDownPrice: stock.limitDownPrice ?? Number((prev * 0.9).toFixed(2)),
    phase: stock.phase ?? 'TRADING',
    orderBook: stock.orderBook ?? {
      bids: [
        { level: 1, price: p, volume: 100 },
        { level: 2, price: p - 0.01, volume: 80 },
        { level: 3, price: p - 0.02, volume: 60 },
        { level: 4, price: p - 0.03, volume: 50 },
        { level: 5, price: p - 0.04, volume: 40 },
      ],
      asks: [
        { level: 1, price: p + 0.01, volume: 100 },
        { level: 2, price: p + 0.02, volume: 80 },
        { level: 3, price: p + 0.03, volume: 60 },
        { level: 4, price: p + 0.04, volume: 50 },
        { level: 5, price: p + 0.05, volume: 40 },
      ],
    },
    recentTrades: stock.recentTrades ?? [],
    ultraShort: stock.ultraShort,
    updatedAt:
      typeof stock.updatedAt === 'number' && Number.isFinite(stock.updatedAt)
        ? stock.updatedAt
        : Date.now(),
  };
}

const initialQuotes = createInitialQuotes();
const initialIndices = createInitialIndices();
let intradayFetchSeq = 0; // 竞态保护：快速切换 symbol 时丢弃过期 fetch 结果

export const useMarketStore = create<MarketStoreState>((set, get) => ({
  quotes: initialQuotes,
  indices: initialIndices,
  symbolOrder: Object.keys(initialQuotes),

  selectedSymbol: '600519.SH',
  intradayPointsMap: {},
  realThemeData: null,
  period: '1D',
  mainIndicator: 'MA',
  subIndicator: 'VOL',

  watchlist: loadSavedWatchlist(),
  searchQuery: '',
  filterCategory: 'all',
  sortBy: 'default',
  sortDir: 'desc',

  alertRules: loadSavedAlerts(),
  triggeredAlerts: [],
  isAlertModalOpen: false,

  mobileBottomTab: 'orderbook',
  isMobileWatchlistOpen: false,
  isArchModalOpen: false,

  workspaceMode: 'chart',
  quantModuleTab: 'focus',
  isCommandPaletteOpen: false,
  commandPaletteInitialQuery: '',

  connectionStatus: 'CONNECTING',
  batchWindowMs: 150,
  lastServerTime: Date.now(),

  errorToasts: [],
  isDemoData: true,

  fullMarketScanData: null,
  fetchFullMarketScan: async () => {
    try {
      const res = await fetch('/api/quant/full_market_scan');
      if (!res.ok) return;
      const data = await res.json();
      if (data && data.status === 'ok') {
        set({ fullMarketScanData: data as FullMarketScanData });
      }
    } catch (e) {
      console.error('[fetchFullMarketScan] 获取全市场竞价扫描数据失败:', e);
    }
  },
  pushErrorToast: (message, opts) => {
    const id = `err-${++errorToastSeq}-${Date.now()}`;
    const toast: ErrorToast = {
      id,
      message,
      severity: opts?.severity ?? 'error',
      createdAt: Date.now(),
      durationMs: opts?.durationMs ?? 5000,
    };
    set((state) => ({ errorToasts: [...state.errorToasts, toast].slice(-5) }));
    setTimeout(() => {
      useMarketStore.getState().dismissErrorToast(id);
    }, toast.durationMs);
  },
  dismissErrorToast: (id) =>
    set((state) => ({ errorToasts: state.errorToasts.filter((t) => t.id !== id) })),

  setSelectedSymbol: (symbol) => {
    const normalized = normalizeExchangeSymbol(symbol);
    set({
      selectedSymbol: normalized,
      isMobileWatchlistOpen: false,
    });
    if (onSymbolSubscribed) {
      onSymbolSubscribed(normalized);
    }
    get().fetchIntraday(normalized);
    const current = get().quotes[normalized];
    if (!current) {
      const placeholder = createPlaceholderQuote({ symbol: normalized });
      get().injectQuote(placeholder);
      fetch(`/api/market/quote/${encodeURIComponent(normalized)}`)
        .then((res) => res.json())
        .then((data) => {
          if (data && data.status === 'ok' && data.quote) {
            get().injectQuote(data.quote);
          }
        })
        .catch((e) => {
          console.error('[setSelectedSymbol] 获取个股行情失败:', e);
          pushErrorToast(`获取 ${normalized} 行情数据失败，请检查网络连接`);
        });
    }
  },

  setIntradayPoints: (symbol, points) =>
    set((state) => {
      const nextMap = { ...state.intradayPointsMap, [symbol]: points };
      const keys = Object.keys(nextMap);
      if (keys.length > 50) {
        for (const k of keys.slice(0, keys.length - 50)) delete nextMap[k];
      }
      return { intradayPointsMap: nextMap };
    }),

  fetchIntraday: async (symbol) => {
    const seq = ++intradayFetchSeq;
    try {
      const res = await fetch(`/api/market/klines/${encodeURIComponent(symbol)}?period=intraday`);
      if (seq !== intradayFetchSeq) return []; // 竞态：用户已切换到其他 symbol
      if (!res.ok) return [];
      const data = await res.json();
      if (seq !== intradayFetchSeq) return []; // 二次检查
      const pts: IntradayPoint[] = Array.isArray(data.intraday) ? data.intraday : [];
      set((state) => {
        const nextMap = { ...state.intradayPointsMap, [symbol]: pts };
        const keys = Object.keys(nextMap);
        if (keys.length > 50) {
          for (const k of keys.slice(0, keys.length - 50)) delete nextMap[k];
        }
        return { intradayPointsMap: nextMap };
      });
      return pts;
    } catch (e) {
      console.error('[fetchIntraday] 获取分时数据失败:', symbol, e);
      return [];
    }
  },

  fetchThemeResonance: async () => {
    try {
      const res = await fetch('/api/quant/theme_resonance');
      if (!res.ok) return;
      const data = await res.json();
      if (data && data.status === 'ok') {
        set({ realThemeData: data });
      }
    } catch (e) {
      console.error('[fetchThemeResonance] 获取题材共振数据失败:', e);
    }
  },

  injectQuote: (quote) => {
    set((state) => ({
      quotes: {
        ...state.quotes,
        [quote.symbol]: quote,
      },
      symbolOrder: state.symbolOrder.includes(quote.symbol)
        ? state.symbolOrder
        : [quote.symbol, ...state.symbolOrder],
    }));
    emitImperativeTick(quote);
  },

  selectAndSubscribeStock: (stock) => {
    const sym = stock.symbol;
    set((state) => {
      const existing = state.quotes[sym];
      const merged = existing ? { ...existing, ...stock } : createPlaceholderQuote(stock);
      return {
        selectedSymbol: sym,
        quotes: {
          ...state.quotes,
          [sym]: merged,
        },
        symbolOrder: state.symbolOrder.includes(sym) ? state.symbolOrder : [sym, ...state.symbolOrder],
        isMobileWatchlistOpen: false,
      };
    });
    if (onSymbolSubscribed) {
      onSymbolSubscribed(sym);
    }
    get().fetchIntraday(sym);
    fetch(`/api/market/quote/${encodeURIComponent(sym)}`)
      .then((res) => res.json())
      .then((data) => {
        if (data && data.status === 'ok' && data.quote) {
          get().injectQuote(data.quote);
        }
      })
      .catch((e) => {
        console.error('[selectAndSubscribeStock] 获取个股行情失败:', e);
        pushErrorToast(`获取 ${sym} 行情数据失败，请检查网络连接`);
      });
  },

  setPeriod: (period) => set({ period }),

  setMainIndicator: (mainIndicator) => set({ mainIndicator }),

  setSubIndicator: (subIndicator) => set({ subIndicator }),

  setSearchQuery: (searchQuery) => set({ searchQuery }),

  setFilterCategory: (filterCategory) => set({ filterCategory }),

  toggleSort: (field) =>
    set((state) => {
      if (state.sortBy !== field) {
        return { sortBy: field, sortDir: 'desc' };
      }
      if (state.sortDir === 'desc') {
        return { sortBy: field, sortDir: 'asc' };
      }
      return { sortBy: 'default', sortDir: 'desc' };
    }),

  toggleWatchlist: (symbol) =>
    set((state) => {
      const exists = state.watchlist.includes(symbol);
      const next = exists
        ? state.watchlist.filter((s) => s !== symbol)
        : [symbol, ...state.watchlist];
      try {
        localStorage.setItem('alphapulse_watchlist_v1', JSON.stringify(next));
      } catch (e) {
        console.error('[toggleWatchlist] localStorage 写入失败:', e);
      }
      if (!exists) {
        // 新加自选时触发 WS 增量订阅，避免连接期间手动添加的标的无行情推送（F-16 修复补项）
        try {
          marketWsClient.subscribe(symbol);
        } catch (e) {
          console.warn('[toggleWatchlist] WS subscribe 失败:', symbol, e);
        }
      }
      return { watchlist: next };
    }),

  setMobileBottomTab: (mobileBottomTab) => set({ mobileBottomTab }),

  setMobileWatchlistOpen: (isMobileWatchlistOpen) => set({ isMobileWatchlistOpen }),

  setArchModalOpen: (isArchModalOpen) => set({ isArchModalOpen }),

  setAlertModalOpen: (isAlertModalOpen) => set({ isAlertModalOpen }),

  setWorkspaceMode: (workspaceMode) => set({ workspaceMode }),

  setCommandPaletteOpen: (isCommandPaletteOpen, initialQuery = '') =>
    set({
      isCommandPaletteOpen,
      commandPaletteInitialQuery: isCommandPaletteOpen ? initialQuery : '',
    }),

  stepSelectedSymbol: (delta) => {
    const state = get();
    const allStocks = state.symbolOrder.map((sym) => state.quotes[sym]).filter(Boolean);
    const list =
      state.filterCategory === 'watchlist'
        ? allStocks.filter((s) => state.watchlist.includes(s.symbol))
        : state.filterCategory === 'special'
        ? allStocks.filter((s) => s.phase !== 'TRADING')
        : allStocks;
    const symbols = (list.length > 0 ? list : allStocks).map((s) => s.symbol);
    if (symbols.length === 0) return;
    const currentIdx = symbols.indexOf(state.selectedSymbol);
    const nextIdx =
      currentIdx === -1
        ? 0
        : (currentIdx + delta + symbols.length) % symbols.length;
    get().setSelectedSymbol(symbols[nextIdx]);
  },

  togglePeriodIntradayDaily: () => {
    const state = get();
    const nextPeriod: ChartPeriod = state.period === 'intraday' ? '1D' : 'intraday';
    set({ period: nextPeriod, workspaceMode: 'chart' });
  },

  setQuantModuleTab: (quantModuleTab) => set({ quantModuleTab }),

  openQuantModule: (quantModuleTab, symbol) =>
    set((state) => ({
      workspaceMode: quantModuleTab === 'auction' ? 'auction' : 'quant',
      quantModuleTab,
      selectedSymbol: symbol ?? state.selectedSymbol,
    })),

  setConnectionStatus: (connectionStatus) => set({ connectionStatus }),

  setBatchWindowMs: (batchWindowMs) => set({ batchWindowMs }),

  addAlertRule: ({ symbol, stockName, condition, threshold }) => {
    const newRule: PriceAlertRule = {
      id: `alert-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      symbol,
      stockName,
      condition,
      threshold: Number(threshold.toFixed(2)),
      enabled: true,
      triggered: false,
      createdAt: Date.now(),
    };
    set((state) => {
      const next = [newRule, ...state.alertRules];
      persistAlerts(next);
      return { alertRules: next };
    });
    return newRule;
  },

  removeAlertRule: (id) =>
    set((state) => {
      const next = state.alertRules.filter((r) => r.id !== id);
      persistAlerts(next);
      return { alertRules: next };
    }),

  toggleAlertRule: (id) =>
    set((state) => {
      const next = state.alertRules.map((r) =>
        r.id === id ? { ...r, enabled: !r.enabled, triggered: false } : r
      );
      persistAlerts(next);
      return { alertRules: next };
    }),

  resetAlertRule: (id) =>
    set((state) => {
      const next = state.alertRules.map((r) =>
        r.id === id
          ? {
              ...r,
              enabled: true,
              triggered: false,
              triggeredAt: undefined,
              triggeredPrice: undefined,
              triggeredChangePercent: undefined,
            }
          : r
      );
      persistAlerts(next);
      return { alertRules: next };
    }),

  markRulesTriggered: (triggeredList) => {
    if (triggeredList.length === 0) return;
    set((state) => {
      const map = new Map(triggeredList.map((item) => [item.ruleId, item]));
      const nextEvents: TriggeredAlertEvent[] = [];

      const nextRules = state.alertRules.map((rule) => {
        const hit = map.get(rule.id);
        if (!hit) return rule;
        nextEvents.push({
          id: `evt-${hit.timestamp}-${rule.id}`,
          ruleId: rule.id,
          symbol: rule.symbol,
          stockName: rule.stockName,
          condition: rule.condition,
          threshold: rule.threshold,
          price: hit.price,
          changePercent: hit.changePercent,
          message: hit.message,
          timestamp: hit.timestamp,
        });
        return {
          ...rule,
          triggered: true,
          triggeredAt: hit.timestamp,
          triggeredPrice: hit.price,
          triggeredChangePercent: hit.changePercent,
        };
      });

      persistAlerts(nextRules);
      return {
        alertRules: nextRules,
        triggeredAlerts: [...nextEvents, ...state.triggeredAlerts].slice(0, 15),
      };
    });
  },

  dismissTriggeredAlert: (eventId) =>
    set((state) => ({
      triggeredAlerts: state.triggeredAlerts.filter((e) => e.id !== eventId),
    })),

  clearAllTriggeredAlerts: () => set({ triggeredAlerts: [] }),

  applyInitSnapshot: (quotesList, indicesList, batchWindowMs, serverTime) => {
    // INIT 只覆盖服务端带回的标的，保留自选里尚未推送的行情，避免列表被快照清空。
    set((state) => {
      const quotes = { ...state.quotes };
      for (const q of quotesList) {
        const prev = quotes[q.symbol];
        quotes[q.symbol] = prev ? { ...prev, ...q } : q;
      }
      const indices = { ...state.indices };
      for (const idx of indicesList) indices[idx.symbol] = idx;
      const incoming = quotesList.map((q) => q.symbol);
      // INIT 时丢弃服务端未推送的种子 symbolOrder 条目：种子 12 只与后端 INIT 8 只仅 4 只重叠，
      // 并集会让 8 只假股永驻 symbolOrder；改由 watchlist + incoming 重建即可覆盖用户自选与服务端实推。
      const symbolOrder = Array.from(
        new Set([...state.watchlist, ...incoming])
      );
      return {
        quotes,
        indices,
        symbolOrder,
        batchWindowMs,
        lastServerTime: serverTime,
        isDemoData: false,
      };
    });
    const active = get().quotes[get().selectedSymbol];
    if (active) {
      emitImperativeTick(active);
    }
  },

  applySnapshotBatch: (quotesBatch, indicesBatch, batchWindowMs, serverTime) => {
    if (quotesBatch.length === 0 && indicesBatch.length === 0) return;

    set((state) => {
      // 性能优化：仅在确有 quote 更新时才浅拷贝整个 dict，
      // 避免仅 indices 刷新时也触发全量 quotes 引用变更导致无谓 re-render
      const nextQuotes = quotesBatch.length > 0 ? { ...state.quotes } : state.quotes;
      for (const q of quotesBatch) {
        // 合并而非整体替换：WebSocket 快照只有 L1 报价字段，
        // 直接替换会把 REST 补上的 ultraShort（连板身位/首封时间）冲掉，
        // 导致「连板梯队最高 0 板」在连上 WS 几秒后又复现。
        nextQuotes[q.symbol] = { ...state.quotes[q.symbol], ...q };
      }

      const nextIndices = indicesBatch.length > 0 ? { ...state.indices } : state.indices;
      for (const idx of indicesBatch) {
        nextIndices[idx.symbol] = idx;
      }

      return {
        quotes: nextQuotes,
        indices: nextIndices,
        batchWindowMs,
        lastServerTime: serverTime,
      };
    });

    // 命令式触发当前选中股票的 Canvas 图表 updateData()，不触发图表组件 Virtual DOM 重绘
    const selected = get().selectedSymbol;
    for (const q of quotesBatch) {
      if (q.symbol === selected) {
        emitImperativeTick(q);
      }
    }
  },

  triggerScenario: async (symbol, scenario) => {
    // 1. 乐观更新本地状态，确保零延迟响应
    const current = get().quotes[symbol];
    if (current) {
      const optimistic = applyScenarioToQuote(current, scenario);
      set((state) => ({
        quotes: {
          ...state.quotes,
          [symbol]: optimistic,
        },
      }));
      emitImperativeTick(optimistic);
    }

    // 2. 同步至服务端权威状态
    try {
      const res = await fetch('/api/market/scenario', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol, scenario }),
      });
      if (res.ok) {
        const data = (await res.json()) as { ok: boolean; quote: TickData };
        if (data.quote) {
          set((state) => ({
            quotes: {
              ...state.quotes,
              [symbol]: data.quote,
            },
          }));
          emitImperativeTick(data.quote);
        }
      }
    } catch (e) {
      console.error('[triggerScenario] 场景推演请求失败:', symbol, scenario, e);
      pushErrorToast(`场景推演请求失败，请检查网络后重试`, { severity: 'warning' });
    }
  },
}));

