/**
 * 选股面板：策略选股（12策略按情绪周期自适应）+ 形态选股（8形态全市场扫描）
 * 后端：GET /api/strategies、GET /api/screen
 */
import React, { useCallback, useEffect, useState } from 'react';
import { useMarketStore } from '../store/useMarketStore';

interface StratItem {
  code: string;
  name: string;
  industry?: string;
  price: number;
  pct: number;
  quality?: number;
  desc?: string;
  dedup_sources?: string[];
}

interface StratGroup {
  key: string;
  name: string;
  stage_hint: string;
  active: boolean;
  count: number;
  items: StratItem[];
}

interface StrategiesResponse {
  status: string;
  date?: string;
  stage?: string;
  advice?: string;
  allow?: string[];
  mode?: string;
  strategies?: StratGroup[];
  dedup?: { removed: number; overlaps: Record<string, unknown> };
  updated?: string;
  elapsed?: number;
  from_cache?: boolean;
  cache_age?: number;
}

interface ScreenItem {
  code: string;
  name: string;
  price: number;
  pct: number;
  vol_ratio?: number;
  note?: string;
}

type ScreenResults = Record<string, ScreenItem[]>;

const pctColor = (p: number) =>
  p > 0 ? 'text-[#F6465D]' : p < 0 ? 'text-[#2EB872]' : 'text-[#9ca3af]';

export const StockScreenerPanel: React.FC = () => {
  const setSelectedSymbol = useMarketStore((s) => s.setSelectedSymbol);
  const setWorkspaceMode = useMarketStore((s) => s.setWorkspaceMode);

  const [tab, setTab] = useState<'strategies' | 'screen' | 'ledger'>('strategies');
  const [stratMode, setStratMode] = useState('auto');
  const [patternQuery, setPatternQuery] = useState('');
  const [expandedPatterns, setExpandedPatterns] = useState<Record<string, boolean>>({});

  // 策略选股状态
  const [stratData, setStratData] = useState<StrategiesResponse | null>(null);
  const [stratLoading, setStratLoading] = useState(false);
  const [stratError, setStratError] = useState<string | null>(null);

  // 形态选股状态
  const [screenResults, setScreenResults] = useState<ScreenResults | null>(null);
  const [screenLoading, setScreenLoading] = useState(false);
  const [screenError, setScreenError] = useState<string | null>(null);

  const loadStrategies = useCallback(async (refresh = false) => {
    setStratLoading(true);
    setStratError(null);
    try {
      const url = `/api/strategies?mode=${encodeURIComponent(stratMode)}${refresh ? '&refresh=true' : ''}`;
      const res = await fetch(url);
      const data = await res.json();
      if (data.status === 'error') throw new Error(data.error || '策略接口返回错误');
      setStratData(data);
    } catch (e) {
      setStratError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setStratLoading(false);
    }
  }, [stratMode]);

  useEffect(() => {
    loadStrategies();
  }, [loadStrategies]);

  const runScreen = useCallback(async () => {
    setScreenLoading(true);
    setScreenError(null);
    setScreenResults(null);
    try {
      // 全市场扫描约1-2分钟，给足超时
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 180000);
      const qs = patternQuery.trim() ? `?patterns=${encodeURIComponent(patternQuery.trim())}` : '';
      const res = await fetch(`/api/screen${qs}`, { signal: controller.signal });
      clearTimeout(timer);
      const data = await res.json();
      if (data.status === 'error') throw new Error(data.error || '扫描失败');
      setScreenResults(data.results || {});
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') {
        setScreenError('扫描超时（180秒），全市场K线拉取较慢，可稍后重试');
      } else {
        setScreenError(e instanceof Error ? e.message : '扫描失败');
      }
    } finally {
      setScreenLoading(false);
    }
  }, [patternQuery]);

  const handlePickStock = useCallback(
    (code: string) => {
      setSelectedSymbol(code);
      setWorkspaceMode('chart');
    },
    [setSelectedSymbol, setWorkspaceMode]
  );

  // ============ 策略选股渲染 ============
  const renderStrategies = () => {
    if (stratLoading && !stratData) {
      return <div className="flex-1 flex items-center justify-center text-[#787b86] text-sm">策略库加载中（首次约5-10秒）…</div>;
    }
    if (stratError) {
      return (
        <div className="flex-1 flex flex-col items-center justify-center gap-2">
          <div className="text-[#F6465D] text-sm">{stratError}</div>
          <button onClick={() => loadStrategies()} className="px-3 py-1.5 text-xs bg-[#2962ff] text-white rounded hover:bg-[#1e53e5]">重试</button>
        </div>
      );
    }
    if (!stratData) return null;

    const activeStrats = (stratData.strategies || []).filter((s) =>
      stratMode === 'auto' ? s.active && s.count > 0 : true
    );
    const totalCandidates = activeStrats.reduce((sum, s) => sum + s.count, 0);

    return (
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* 情绪周期状态条 */}
        <div className="rounded-lg border border-[#2a2e39] bg-[#131722] p-3 flex flex-wrap items-center gap-3 text-xs">
          <label className="flex items-center gap-1 text-[#787b86]">
            模式
            <select
              value={stratMode}
              onChange={(e) => setStratMode(e.target.value)}
              className="bg-[#1e222d] border border-[#2a2e39] rounded px-1 py-0.5 text-[#d1d4dc]"
            >
              <option value="auto">auto 情绪自适应</option>
              <option value="all">all 全部策略</option>
              {['E', 'F', 'G', 'H', 'I', 'J', 'K', 'L'].map((k) => (
                <option key={k} value={k}>
                  仅 {k}
                </option>
              ))}
            </select>
          </label>
          <span className="text-[#787b86]">当前周期</span>
          <span className="px-2 py-0.5 rounded bg-[#2962ff]/20 text-[#2962ff] font-semibold">{stratData.stage || '-'}</span>
          <span className="text-[#d1d4dc]">{stratData.advice || ''}</span>
          <span className="text-[#787b86] ml-auto">
            候选 {totalCandidates} 只 · 去重 {stratData.dedup?.removed ?? 0} 条
            {stratData.from_cache ? ` · 缓存(${stratData.cache_age ?? 0}s)` : ''}
            {stratData.elapsed ? ` · 耗时${stratData.elapsed}s` : ''}
          </span>
          <button
            onClick={() => loadStrategies(true)}
            className="px-2 py-0.5 rounded bg-[#1e222d] text-[#9ca3af] hover:text-white hover:bg-[#2a2e39]"
          >
            刷新
          </button>
        </div>

        {/* 策略分组 */}
        {activeStrats.length === 0 ? (
          <div className="text-center text-[#787b86] py-12 text-sm">当前周期无活跃策略候选</div>
        ) : (
          activeStrats.map((sg) => (
            <div key={sg.key} className="rounded-lg border border-[#2a2e39] bg-[#131722] overflow-hidden">
              <div className="flex items-center gap-2 px-3 py-2 border-b border-[#2a2e39] bg-[#1e222d]">
                <span className="px-1.5 py-0.5 rounded bg-[#F59E0B]/20 text-[#F59E0B] text-[10px] font-mono">{sg.key}</span>
                <span className="text-sm font-semibold text-white">{sg.name}</span>
                <span className="text-[10px] text-[#787b86]">{sg.stage_hint}</span>
                {!sg.active && (
                  <span className="text-[10px] text-[#787b86] border border-[#2a2e39] rounded px-1">未激活</span>
                )}
                <span className="ml-auto text-[10px] text-[#787b86]">{sg.count} 只</span>
              </div>
              <div className="divide-y divide-[#1e222d]">
                {sg.items.map((it) => (
                  <button
                    key={it.code}
                    onClick={() => handlePickStock(it.code)}
                    className="w-full text-left px-3 py-2 flex items-center gap-3 hover:bg-[#1e222d] transition-colors cursor-pointer"
                  >
                    <span className="font-mono text-xs text-[#9ca3af] w-16">{it.code}</span>
                    <span className="text-xs text-white w-20 truncate">{it.name}</span>
                    {it.quality != null && it.quality > 0 && (
                      <span className="text-[10px] text-[#F59E0B] w-10 text-right">Q{it.quality.toFixed(1)}</span>
                    )}
                    <span className={`text-xs font-mono w-16 text-right ${pctColor(it.pct)}`}>
                      {it.pct >= 0 ? '+' : ''}{it.pct.toFixed(2)}%
                    </span>
                    <span className="text-xs font-mono text-[#9ca3af] w-14 text-right">{it.price.toFixed(2)}</span>
                    <span className="text-[10px] text-[#787b86] flex-1 truncate">{it.desc}</span>
                    {it.dedup_sources && it.dedup_sources.length > 0 && (
                      <span className="text-[10px] text-[#38bdf8]">多策略</span>
                    )}
                  </button>
                ))}
              </div>
            </div>
          ))
        )}
      </div>
    );
  };

  // ============ 形态选股渲染 ============
  const renderScreen = () => {
    return (
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <div className="rounded-lg border border-[#2a2e39] bg-[#131722] p-3">
          <div className="flex items-center gap-3">
            <div className="flex-1">
              <div className="text-sm font-semibold text-white mb-1">全市场8形态扫描</div>
              <div className="text-[11px] text-[#787b86]">
                打板 / 趋势 / 龙回头 / 首阴反包 / N字反包 / 均线粘合 / 地量反转 / 缺口突破 / 低吸
              </div>
              <input
                value={patternQuery}
                onChange={(e) => setPatternQuery(e.target.value)}
                placeholder="只扫指定形态，逗号分隔；留空扫全部"
                className="mt-2 w-full bg-[#0d0e12] border border-[#2a2e39] rounded px-2 py-1 text-[11px] text-[#d1d4dc]"
              />
            </div>
            <button
              onClick={runScreen}
              disabled={screenLoading}
              className="px-4 py-2 rounded bg-[#2962ff] text-white text-xs font-semibold hover:bg-[#1e53e5] disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {screenLoading ? '扫描中（1-2分钟）…' : '开始扫描'}
            </button>
          </div>
          {screenError && <div className="mt-2 text-xs text-[#F6465D]">{screenError}</div>}
        </div>

        {screenLoading && (
          <div className="flex items-center justify-center py-12 text-[#787b86] text-sm">
            正在拉取全市场K线并逐只判定形态，请稍候…
          </div>
        )}

        {screenResults && !screenLoading && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Object.entries(screenResults).map(([pattern, list]) => {
              if (!list || list.length === 0) return null;
              return (
                <div key={pattern} className="rounded-lg border border-[#2a2e39] bg-[#131722] overflow-hidden">
                  <div className="flex items-center gap-2 px-3 py-2 border-b border-[#2a2e39] bg-[#1e222d]">
                    <span className="text-sm font-semibold text-white">{pattern}</span>
                    <span className="ml-auto text-[10px] text-[#787b86]">{list.length} 只</span>
                  </div>
                  <div className="divide-y divide-[#1e222d] max-h-80 overflow-y-auto">
                    {(expandedPatterns[pattern] ? list : list.slice(0, 15)).map((it) => (
                      <button
                        key={it.code}
                        onClick={() => handlePickStock(it.code)}
                        className="w-full text-left px-3 py-1.5 flex items-center gap-2 hover:bg-[#1e222d] transition-colors cursor-pointer"
                      >
                        <span className="font-mono text-[11px] text-[#9ca3af] w-16">{it.code}</span>
                        <span className="text-[11px] text-white flex-1 truncate">{it.name}</span>
                        <span className={`text-[11px] font-mono w-14 text-right ${pctColor(it.pct)}`}>
                          {it.pct >= 0 ? '+' : ''}{it.pct.toFixed(2)}%
                        </span>
                        <span className="text-[10px] text-[#787b86] w-12 text-right">{it.price.toFixed(2)}</span>
                      </button>
                    ))}
                    {list.length > 15 && !expandedPatterns[pattern] && (
                      <button
                        type="button"
                        onClick={() => setExpandedPatterns((prev) => ({ ...prev, [pattern]: true }))}
                        className="w-full px-3 py-1.5 text-left text-[10px] text-[#38bdf8] hover:text-white"
                      >
                        展开其余 {list.length - 15} 只
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
            {Object.values(screenResults).every((l) => !l || l.length === 0) && (
              <div className="col-span-2 text-center text-[#787b86] py-12 text-sm">本次扫描无形态命中</div>
            )}
          </div>
        )}
      </div>
    );
  };

  const renderLedger = () => <ResearchLedger />;

  return (
    <div className="flex flex-col h-full min-h-0 bg-[#0d0e12]">
      {/* 子tab切换 */}
      <div className="flex items-center gap-1 px-4 py-2 border-b border-[#2a2e39] bg-[#131722] shrink-0">
        <button
          onClick={() => setTab('strategies')}
          className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
            tab === 'strategies'
              ? 'bg-[#2962ff] text-white'
              : 'text-[#9ca3af] hover:text-white hover:bg-[#1e222d]'
          }`}
        >
          策略选股（情绪自适应）
        </button>
        <button
          onClick={() => setTab('screen')}
          className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
            tab === 'screen'
              ? 'bg-[#F6465D] text-white'
              : 'text-[#9ca3af] hover:text-white hover:bg-[#1e222d]'
          }`}
        >
          形态选股（全市场扫描）
        </button>
        <button
          onClick={() => setTab('ledger')}
          className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
            tab === 'ledger'
              ? 'bg-[#F59E0B] text-[#0d0e12]'
              : 'text-[#9ca3af] hover:text-white hover:bg-[#1e222d]'
          }`}
        >
          数据 / 回测 / 模拟盘
        </button>
      </div>
      {tab === 'strategies' ? renderStrategies() : tab === 'screen' ? renderScreen() : renderLedger()}
    </div>
  );
};

const ResearchLedger: React.FC = () => {
  const [statusText, setStatusText] = useState('加载中…');
  const [presets, setPresets] = useState<{ key: string; name: string; default_code?: string }[]>([]);
  const [report, setReport] = useState<string>('尚未读取');
  const [backtest, setBacktest] = useState<string>('');

  useEffect(() => {
    let alive = true;
    fetch('/api/data_status')
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (!alive) return;
        const sources = j?.sources || {};
        const bits = Object.entries(sources)
          .slice(0, 6)
          .map(([name, info]) => {
            const st = (info as { status?: string })?.status || 'unknown';
            return `${name}:${st}`;
          });
        setStatusText(bits.join(' · ') || '无数据源状态');
      })
      .catch(() => { if (alive) setStatusText('数据源状态不可用'); });
    fetch('/api/backtest/presets')
      .then((r) => (r.ok ? r.json() : []))
      .then((rows) => { if (alive) setPresets(Array.isArray(rows) ? rows : []); })
      .catch(() => { if (alive) setPresets([]); });
    fetch('/api/paper/report')
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (!alive) return;
        if (!j) {
          setReport('模拟盘报告不可用');
          return;
        }
        setReport(
          `成交 ${j.trades ?? '—'} 笔 · 胜率 ${j.win_rate_pct ?? '—'}% · 回撤 ${j.max_drawdown_pct ?? '—'}%`
        );
      })
      .catch(() => { if (alive) setReport('模拟盘报告不可用'); });
    return () => { alive = false; };
  }, []);

  const runPreset = (key: string, code: string) => {
    setBacktest(`${key} 回测中…`);
    const q = new URLSearchParams({ strategy: key, code: code || 'sh000001', days: '120' });
    fetch(`/api/backtest/run?${q}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (!j) {
          setBacktest('回测失败');
          return;
        }
        const m = j.summary || j.metrics || j;
        setBacktest(
          `${key} 收益 ${m.total_return_pct ?? '—'}% 回撤 ${m.max_drawdown_pct ?? '—'}%`
        );
      })
      .catch(() => setBacktest('回测失败'));
  };

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-3 text-xs text-[#d1d4dc]">
      <div className="rounded border border-[#2a2e39] bg-[#131722] p-3">
        <div className="text-[#787b86] mb-1">数据源健康</div>
        <div>{statusText}</div>
      </div>
      <div className="rounded border border-[#2a2e39] bg-[#131722] p-3">
        <div className="text-[#787b86] mb-1">模拟盘</div>
        <div>{report}</div>
      </div>
      <div className="rounded border border-[#2a2e39] bg-[#131722] p-3 space-y-2">
        <div className="text-[#787b86]">回测预设（点击运行）</div>
        {presets.map((p) => (
          <button
            key={p.key}
            type="button"
            onClick={() => runPreset(p.key, p.default_code || 'sh000001')}
            className="block w-full text-left px-2 py-1 rounded hover:bg-[#1e222d]"
          >
            {p.name}
          </button>
        ))}
        {backtest && <div className="text-[#F59E0B]">{backtest}</div>}
      </div>
    </div>
  );
};
