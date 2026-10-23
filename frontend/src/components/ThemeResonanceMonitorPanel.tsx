import React, { useMemo, useState } from 'react';
import * as d3 from 'd3';
import {
  Activity,
  Compass,
  Crosshair,
  Flame,
  Layers,
  TrendingUp,
  Zap,
} from 'lucide-react';
import type {
  ThemeAttackRole,
  ThemeResonanceItem,
  ThemeResonanceOverview,
  ThemeResonanceScenarioPreset,
} from '../types/market';
import {
  formatAmountCN,
  formatSignedPercent,
  getSignedColorClass,
} from '../utils/marketCalc';

interface ThemeResonanceMonitorPanelProps {
  overview: ThemeResonanceOverview;
  scenario: ThemeResonanceScenarioPreset;
  onChangeScenario: (preset: ThemeResonanceScenarioPreset) => void;
  selectedSymbol: string;
  onSelectSymbol: (symbol: string) => void;
  compact?: boolean;
}

interface HeatmapLeafData {
  name: string;
  value: number;
  theme?: ThemeResonanceItem;
}

function getAttackRoleStyle(role: ThemeAttackRole, changePercent: number) {
  switch (role) {
    case 'MAIN_ATTACK':
      return {
        tileBg: 'linear-gradient(135deg, rgba(246,70,93,0.34) 0%, rgba(153,27,48,0.22) 100%)',
        borderColor: 'rgba(246, 70, 93, 0.72)',
        activeBorderColor: '#F6465D',
        badgeClass: 'bg-[#F6465D]/25 text-[#ff6b81] border-[#F6465D]/60',
        barColor: '#F6465D',
        accentText: 'text-[#F6465D]',
      };
    case 'SUB_ROTATION':
      return {
        tileBg: 'linear-gradient(135deg, rgba(245,158,11,0.26) 0%, rgba(120,53,15,0.18) 100%)',
        borderColor: 'rgba(245, 158, 11, 0.58)',
        activeBorderColor: '#F59E0B',
        badgeClass: 'bg-[#F59E0B]/20 text-[#F59E0B] border-[#F59E0B]/50',
        barColor: '#F59E0B',
        accentText: 'text-[#F59E0B]',
      };
    case 'DEFENSIVE_HOLD':
      return {
        tileBg:
          changePercent >= 0
            ? 'linear-gradient(135deg, rgba(56,189,248,0.16) 0%, rgba(30,41,59,0.35) 100%)'
            : 'linear-gradient(135deg, rgba(14,203,129,0.14) 0%, rgba(19,23,34,0.4) 100%)',
        borderColor: 'rgba(56, 189, 248, 0.38)',
        activeBorderColor: '#38bdf8',
        badgeClass: 'bg-[#38bdf8]/15 text-[#38bdf8] border-[#38bdf8]/40',
        barColor: '#38bdf8',
        accentText: 'text-[#38bdf8]',
      };
    case 'EBB_RETREAT':
      return {
        tileBg: 'linear-gradient(135deg, rgba(14,203,129,0.24) 0%, rgba(6,78,59,0.20) 100%)',
        borderColor: 'rgba(14, 203, 129, 0.55)',
        activeBorderColor: '#0ECB81',
        badgeClass: 'bg-[#0ECB81]/20 text-[#0ECB81] border-[#0ECB81]/50',
        barColor: '#0ECB81',
        accentText: 'text-[#0ECB81]',
      };
  }
}

export const ThemeResonanceMonitorPanel: React.FC<ThemeResonanceMonitorPanelProps> = ({
  overview,
  scenario,
  onChangeScenario,
  selectedSymbol,
  onSelectSymbol,
}) => {
  const { themes } = overview;

  // 默认选中共振得分最高的板块，或用户点击热力图选中的板块
  const [selectedSectorName, setSelectedSectorName] = useState<string | null>(null);
  // 热力图色彩维度切换：综合共振强度 vs 板块涨停密度 vs 龙头联动指数
  const [heatmapMetricMode, setHeatmapMetricMode] = useState<
    'resonance' | 'density' | 'linkage'
  >('resonance');

  const activeTheme = useMemo(() => {
    if (selectedSectorName) {
      const found = themes.find((t) => t.sectorName === selectedSectorName);
      if (found) return found;
    }
    return themes[0] ?? null;
  }, [themes, selectedSectorName]);

  // 使用 D3.treemap 计算实时题材热力分布图布局坐标 (百分比坐标 0~100，完美自适应响应式容器)
  const treemapLeaves = useMemo(() => {
    if (themes.length === 0) return [];

    const rootData: { name: string; children: HeatmapLeafData[] } = {
      name: 'market_themes',
      children: themes.map((t) => {
        const weight =
          heatmapMetricMode === 'density'
            ? Math.max(48, t.limitUpDensityPercent * 4.2 + t.resonanceScore * 0.65)
            : heatmapMetricMode === 'linkage'
            ? Math.max(48, t.dragonLinkageScore * 1.55 + t.heatWeight * 0.45)
            : Math.max(48, t.heatWeight);
        return {
          name: t.sectorName,
          value: weight,
          theme: t,
        };
      }),
    };

    const hierarchyRoot = d3
      .hierarchy<HeatmapLeafData | { name: string; children: HeatmapLeafData[] }>(rootData)
      .sum((d) => ('value' in d ? d.value : 0))
      .sort((a, b) => (b.value ?? 0) - (a.value ?? 0));

    const treemapLayout = d3
      .treemap<HeatmapLeafData | { name: string; children: HeatmapLeafData[] }>()
      .size([100, 100])
      .paddingInner(0.8)
      .paddingOuter(0.4)
      .round(false);

    const laidOut = treemapLayout(hierarchyRoot);
    return laidOut.leaves().map((leaf) => {
      const data = leaf.data as HeatmapLeafData;
      return {
        sectorName: data.name,
        theme: data.theme!,
        x0: leaf.x0,
        y0: leaf.y0,
        x1: leaf.x1,
        y1: leaf.y1,
        widthPct: Math.max(0, leaf.x1 - leaf.x0),
        heightPct: Math.max(0, leaf.y1 - leaf.y0),
      };
    });
  }, [themes, heatmapMetricMode]);

  const scenarioOptions: { id: ThemeResonanceScenarioPreset; label: string }[] = [
    { id: 'live', label: '实盘题材共振' },
    { id: 'ai_chip_mainstream', label: 'AI+算力双主线爆发' },
    { id: 'rotation_divergence', label: '高低切轮动分化' },
  ];

  if (!activeTheme) return null;

  return (
    <section
      aria-label="板块/题材共振监测"
      data-testid="theme-resonance-monitor-panel"
      className="bg-[#1e222d] border border-[#2a2e39] rounded-md overflow-hidden"
    >
      {/* 顶部标题栏与沙盘场景切换器 */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 bg-[#131722] border-b border-[#2a2e39]">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-[#F6465D]" />
          <h2 className="text-xs sm:text-sm font-bold text-white">
            板块/题材共振监测 (“面”涨停密度 × “点”领涨龙头联动 · 实时题材热力分布图)
          </h2>
          <span className="hidden md:inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono tabular-nums bg-[#F6465D]/15 text-[#F6465D] border border-[#F6465D]/40">
            主攻方向自动识别
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] text-[#787b86]">行情结构推演:</span>
          {scenarioOptions.map((opt) => {
            const isActive = scenario === opt.id;
            return (
              <button
                key={opt.id}
                type="button"
                data-testid={`theme-scenario-${opt.id}`}
                onClick={() => onChangeScenario(opt.id)}
                className={`px-2 py-0.5 rounded text-[11px] font-medium border transition-colors cursor-pointer whitespace-nowrap ${
                  isActive
                    ? 'bg-[#2962ff] text-white border-[#2962ff]'
                    : 'bg-[#1e222d] text-[#9ca3af] border-[#2a2e39] hover:text-white'
                }`}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* 一、当日主流资金进攻方向核心雷达横幅 */}
      <div
        data-testid="mainstream-attack-direction-banner"
        className="p-3 bg-[#161a24] border-b border-[#2a2e39]"
      >
        <div className="grid grid-cols-1 xl:grid-cols-12 gap-3 items-center">
          {/* 左侧：主流资金进攻方向结论与战术预案 */}
          <div className="xl:col-span-8 space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-[#F6465D]/20 border border-[#F6465D]/50 text-[#F6465D] text-xs font-bold">
                <Compass className="w-3.5 h-3.5" />
                当日主流资金进攻方向
              </span>
              {overview.mainstreamAttackSectors.map((secName) => (
                <button
                  key={secName}
                  type="button"
                  onClick={() => setSelectedSectorName(secName)}
                  className="px-2 py-0.5 rounded bg-[#F6465D] text-white text-xs font-bold hover:opacity-90 transition-opacity cursor-pointer"
                >
                  ★ 主攻: {secName}
                </button>
              ))}
              {overview.subRotationSectors.length > 0 && (
                <span className="text-xs text-[#F59E0B] font-mono tabular-nums">
                  支线轮动: {overview.subRotationSectors.join(' / ')}
                </span>
              )}
              {overview.retreatSectors.length > 0 && (
                <span className="text-xs text-[#0ECB81] font-mono tabular-nums">
                  退潮规避: {overview.retreatSectors.join(' / ')}
                </span>
              )}
            </div>

            <div
              data-testid="attack-direction-headline"
              className="text-xs sm:text-sm font-bold text-white leading-snug"
            >
              {overview.attackDirectionHeadline}
            </div>

            <p className="text-xs text-[#9ca3af] leading-relaxed">
              <strong className="text-[#38bdf8]">游资主线作战指南：</strong>
              {overview.tacticalPlaybook}
            </p>
          </div>

          {/* 右侧：四维全市场题材共振核心量化指标卡 */}
          <div className="xl:col-span-4 grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-2 gap-2">
            <div className="p-2 rounded bg-[#131722] border border-[#2a2e39]">
              <div className="text-[10px] text-[#787b86] whitespace-nowrap">
                主线共振强度指数
              </div>
              <div className="mt-0.5 flex items-baseline justify-between font-mono tabular-nums">
                <span
                  data-testid="market-resonance-score"
                  className={`text-base font-bold ${
                    overview.marketResonanceScore >= 72
                      ? 'text-[#F6465D]'
                      : overview.marketResonanceScore >= 52
                      ? 'text-[#F59E0B]'
                      : 'text-[#0ECB81]'
                  }`}
                >
                  {overview.marketResonanceScore}
                </span>
                <span className="text-[10px] text-[#9ca3af]">/ 100</span>
              </div>
            </div>

            <div className="p-2 rounded bg-[#131722] border border-[#2a2e39]">
              <div className="text-[10px] text-[#787b86] whitespace-nowrap">
                前二主线火力集中度
              </div>
              <div className="mt-0.5 flex items-baseline justify-between font-mono tabular-nums">
                <span
                  data-testid="mainstream-concentration-pct"
                  className="text-base font-bold text-[#F6465D]"
                >
                  {overview.mainstreamConcentrationPercent}%
                </span>
                <span className="text-[10px] text-[#9ca3af]">资金抱团</span>
              </div>
            </div>

            <div className="p-2 rounded bg-[#131722] border border-[#2a2e39]">
              <div className="text-[10px] text-[#787b86] whitespace-nowrap">
                题材池涨停总家数
              </div>
              <div className="mt-0.5 flex items-baseline justify-between font-mono tabular-nums">
                <span
                  data-testid="market-total-limitup-count"
                  className="text-base font-bold text-[#F59E0B]"
                >
                  {overview.totalMarketLimitUpCount} 家
                </span>
                <span className="text-[10px] text-[#9ca3af]">封板梯队</span>
              </div>
            </div>

            <div className="p-2 rounded bg-[#131722] border border-[#2a2e39]">
              <div className="text-[10px] text-[#787b86] whitespace-nowrap">
                全市场平均涨停密度
              </div>
              <div className="mt-0.5 flex items-baseline justify-between font-mono tabular-nums">
                <span
                  data-testid="market-avg-density-pct"
                  className="text-base font-bold text-[#38bdf8]"
                >
                  {overview.avgLimitUpDensityPercent}%
                </span>
                <span className="text-[10px] text-[#9ca3af]">板块均值</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 二、核心双栏工作区：左侧 D3 实时题材热力分布图 (7列) + 右侧 涨停密度与领涨龙头联动深度拆解 (5列) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 border-b border-[#2a2e39]">
        {/* 左侧：实时题材热力分布图 (D3 Treemap 矩阵热力图) */}
        <div className="lg:col-span-7 p-3 border-b lg:border-b-0 lg:border-r border-[#2a2e39] flex flex-col justify-between bg-[#0d0e12]">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-2.5">
            <div className="flex items-center gap-2">
              <Flame className="w-4 h-4 text-[#F6465D]" />
              <span className="text-xs font-bold text-white">
                实时题材热力分布图 (面积 = 资金进攻权重 · 色温 = 共振与涨停密度)
              </span>
            </div>

            {/* 热力面积权重维度切换 */}
            <div className="flex items-center gap-1 bg-[#131722] p-0.5 rounded border border-[#2a2e39] text-[11px]">
              <button
                type="button"
                data-testid="heatmap-mode-resonance"
                onClick={() => setHeatmapMetricMode('resonance')}
                className={`px-2 py-0.5 rounded cursor-pointer transition-colors ${
                  heatmapMetricMode === 'resonance'
                    ? 'bg-[#2962ff] text-white font-semibold'
                    : 'text-[#9ca3af] hover:text-white'
                }`}
              >
                综合共振权重
              </button>
              <button
                type="button"
                data-testid="heatmap-mode-density"
                onClick={() => setHeatmapMetricMode('density')}
                className={`px-2 py-0.5 rounded cursor-pointer transition-colors ${
                  heatmapMetricMode === 'density'
                    ? 'bg-[#2962ff] text-white font-semibold'
                    : 'text-[#9ca3af] hover:text-white'
                }`}
              >
                涨停密度优先
              </button>
              <button
                type="button"
                data-testid="heatmap-mode-linkage"
                onClick={() => setHeatmapMetricMode('linkage')}
                className={`px-2 py-0.5 rounded cursor-pointer transition-colors ${
                  heatmapMetricMode === 'linkage'
                    ? 'bg-[#2962ff] text-white font-semibold'
                    : 'text-[#9ca3af] hover:text-white'
                }`}
              >
                龙头联动优先
              </button>
            </div>
          </div>

          {/* D3 Treemap 响应式题材热力分布画布 */}
          <div
            data-testid="theme-heatmap-distribution"
            className="relative w-full h-[380px] sm:h-[410px] rounded bg-[#131722] border border-[#2a2e39] overflow-hidden select-none"
          >
            {treemapLeaves.map((leaf) => {
              const { theme, widthPct, heightPct, x0, y0 } = leaf;
              const isSelected = activeTheme.sectorName === theme.sectorName;
              const styleMeta = getAttackRoleStyle(
                theme.attackRole,
                theme.sectorChangePercent
              );
              const isNarrowTile = widthPct < 21;
              const isCompactTile = widthPct < 26 || heightPct < 34;
              const isTinyTile = widthPct < 18 || heightPct < 22;

              return (
                <div
                  key={theme.sectorName}
                  role="button"
                  tabIndex={0}
                  data-testid={`heatmap-tile-${theme.sectorName}`}
                  onClick={() => setSelectedSectorName(theme.sectorName)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      setSelectedSectorName(theme.sectorName);
                    }
                  }}
                  style={{
                    left: `${x0}%`,
                    top: `${y0}%`,
                    width: `${widthPct}%`,
                    height: `${heightPct}%`,
                    background: styleMeta.tileBg,
                    borderColor: isSelected
                      ? '#ffffff'
                      : styleMeta.borderColor,
                    boxShadow: isSelected
                      ? `inset 0 0 0 1.5px ${styleMeta.activeBorderColor}, 0 0 16px rgba(246,70,93,0.28)`
                      : 'none',
                  }}
                  className="absolute p-1.5 sm:p-2 border rounded-[3px] transition-all duration-150 cursor-pointer overflow-hidden flex flex-col justify-between hover:brightness-110"
                >
                  {/* 区块顶部：板块名称 + 均涨幅 + 进攻角色标签 */}
                  <div className="min-w-0">
                    {isNarrowTile ? (
                      <div className="space-y-0.5">
                        <div className="font-bold text-white text-[11px] leading-tight truncate">
                          {theme.sectorName}
                        </div>
                        <div
                          className={`font-mono tabular-nums text-[11px] font-bold leading-tight ${getSignedColorClass(
                            theme.sectorChangePercent
                          )}`}
                        >
                          {formatSignedPercent(theme.sectorChangePercent)}
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-center justify-between gap-1">
                        <span className="font-bold text-white text-xs sm:text-sm truncate">
                          {theme.sectorName}
                        </span>
                        <span
                          className={`font-mono tabular-nums text-xs sm:text-sm font-bold shrink-0 ${getSignedColorClass(
                            theme.sectorChangePercent
                          )}`}
                        >
                          {formatSignedPercent(theme.sectorChangePercent)}
                        </span>
                      </div>
                    )}

                    {!isTinyTile && (
                      <div className="mt-0.5 flex flex-wrap items-center gap-1">
                        <span
                          className={`px-1.5 py-0.2 rounded border text-[10px] font-semibold leading-tight whitespace-nowrap ${styleMeta.badgeClass}`}
                        >
                          {theme.attackRoleLabel}
                        </span>
                        <span className="text-[10px] font-mono tabular-nums text-[#d1d4dc] whitespace-nowrap">
                          共振 <strong>{theme.resonanceScore}</strong>
                        </span>
                      </div>
                    )}
                  </div>

                  {/* 区块中部：涨停密度进度条与龙头联动核心指标 */}
                  {!isCompactTile && (
                    <div className="my-1 space-y-1">
                      <div className="flex items-center justify-between gap-1 text-[10px] font-mono tabular-nums whitespace-nowrap">
                        <span className="text-[#d1d4dc]">
                          涨停密度:{' '}
                          <strong className="text-white">
                            {theme.limitUpDensityPercent}%
                          </strong>{' '}
                          ({theme.limitUpCount}/{theme.sectorConstituentCount}家)
                        </span>
                        <span className="text-[#F59E0B]">
                          联动 {theme.dragonLinkageScore}分
                        </span>
                      </div>
                      <div className="w-full h-1.5 bg-[#0d0e12]/80 rounded overflow-hidden">
                        <div
                          className="h-full rounded transition-all"
                          style={{
                            width: `${Math.min(100, Math.max(8, theme.limitUpDensityPercent * 2.5))}%`,
                            backgroundColor: styleMeta.barColor,
                          }}
                        />
                      </div>
                    </div>
                  )}

                  {/* 区块底部：先锋龙与中军龙快览 */}
                  {!isTinyTile && (
                    <div className="pt-1 border-t border-white/10 flex items-center justify-between gap-1 text-[10px] font-mono tabular-nums truncate">
                      <span className="text-[#d1d4dc] truncate">
                        先锋:{' '}
                        <strong className="text-white">
                          {theme.pioneerDragon.name}
                        </strong>
                        {theme.pioneerDragon.consecutiveBoards >= 1
                          ? `(${theme.pioneerDragon.consecutiveBoards}板)`
                          : ''}
                      </span>
                      <span className="text-[#9ca3af] shrink-0">
                        火力 {theme.capitalAttackSharePercent}%
                      </span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* 热力图图例与交互说明 */}
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[11px] text-[#9ca3af]">
            <div className="flex flex-wrap items-center gap-3">
              <span className="inline-flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-xs bg-[#F6465D] inline-block" />
                主攻核心主线 (共振≥78 &amp; 高涨停密度)
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-xs bg-[#F59E0B] inline-block" />
                支线轮动助攻 (局部脉冲)
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-xs bg-[#38bdf8] inline-block" />
                防守分歧观察
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-xs bg-[#0ECB81] inline-block" />
                资金兑现退潮 (净流出/跌停负反馈)
              </span>
            </div>
            <span className="text-[#787b86]">
              点击任一题材热力区块 → 右侧拆解龙头联动链条
            </span>
          </div>
        </div>

        {/* 右侧：选定题材的涨停密度与领涨龙头三阶联动深度拆解 */}
        <div
          data-testid="theme-linkage-detail-panel"
          className="lg:col-span-5 p-3 bg-[#131722] flex flex-col justify-between space-y-3"
        >
          {/* 顶部：选定题材头部 */}
          <div>
            <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-[#2a2e39]">
              <div className="flex items-center gap-2">
                <Crosshair className="w-4 h-4 text-[#38bdf8]" />
                <span
                  data-testid="selected-theme-title"
                  className="text-sm font-bold text-white"
                >
                  【{activeTheme.sectorName}】涨停密度与龙头联动拆解
                </span>
                <span
                  className={`font-mono tabular-nums text-xs font-bold ${getSignedColorClass(
                    activeTheme.sectorChangePercent
                  )}`}
                >
                  {formatSignedPercent(activeTheme.sectorChangePercent)}
                </span>
              </div>
              <span
                className={`px-2 py-0.5 rounded border text-[11px] font-semibold ${
                  getAttackRoleStyle(
                    activeTheme.attackRole,
                    activeTheme.sectorChangePercent
                  ).badgeClass
                }`}
              >
                {activeTheme.attackRoleLabel}
              </span>
            </div>

            {/* 三维核心量化指标卡：涨停密度 / 龙头联动指数 / 主力净买额 */}
            <div className="grid grid-cols-3 gap-2 mt-2.5 text-xs">
              <div className="p-2 rounded bg-[#1e222d] border border-[#2a2e39]">
                <div className="text-[10px] text-[#787b86] whitespace-nowrap">
                  板块内涨停密度
                </div>
                <div className="mt-1 flex items-baseline justify-between font-mono tabular-nums">
                  <span
                    data-testid="selected-theme-density"
                    className="text-sm font-bold text-[#F6465D]"
                  >
                    {activeTheme.limitUpDensityPercent}%
                  </span>
                  <span className="text-[10px] text-[#9ca3af]">
                    {activeTheme.limitUpCount}/{activeTheme.sectorConstituentCount}家
                  </span>
                </div>
                <div className="mt-0.5 text-[10px] text-[#F59E0B]">
                  {activeTheme.densityLevel}
                </div>
              </div>

              <div className="p-2 rounded bg-[#1e222d] border border-[#2a2e39]">
                <div className="text-[10px] text-[#787b86] whitespace-nowrap">
                  领涨龙头联动指数
                </div>
                <div className="mt-1 flex items-baseline justify-between font-mono tabular-nums">
                  <span
                    data-testid="selected-theme-linkage-score"
                    className="text-sm font-bold text-[#38bdf8]"
                  >
                    {activeTheme.dragonLinkageScore}
                  </span>
                  <span className="text-[10px] text-[#9ca3af]">/ 100</span>
                </div>
                <div className="mt-0.5 text-[10px] text-[#0ECB81] truncate">
                  {activeTheme.dragonLinkageStatus}
                </div>
              </div>

              <div className="p-2 rounded bg-[#1e222d] border border-[#2a2e39]">
                <div className="text-[10px] text-[#787b86] whitespace-nowrap">
                  主力净流入 / 火力占比
                </div>
                <div className="mt-1 flex items-baseline justify-between font-mono tabular-nums">
                  <span
                    className={`text-sm font-bold ${
                      activeTheme.totalNetInflowCNY >= 0
                        ? 'text-[#F6465D]'
                        : 'text-[#0ECB81]'
                    }`}
                  >
                    {activeTheme.totalNetInflowCNY >= 0 ? '+' : '-'}
                    {formatAmountCN(Math.abs(activeTheme.totalNetInflowCNY))}
                  </span>
                </div>
                <div className="mt-0.5 text-[10px] font-mono tabular-nums text-[#9ca3af]">
                  占全市场火力 {activeTheme.capitalAttackSharePercent}%
                </div>
              </div>
            </div>

            {/* 领涨龙头传导链条定性诊断框 */}
            <div className="mt-2.5 p-2.5 rounded bg-[#161a24] border border-[#2a2e39] space-y-2">
              <div className="flex items-center justify-between text-[11px]">
                <span className="font-bold text-[#F59E0B] flex items-center gap-1">
                  <Zap className="w-3.5 h-3.5" />
                  领涨龙头三阶联动传导链
                </span>
                <span className="font-mono tabular-nums text-[#9ca3af]">
                  红盘比 {activeTheme.upRatioPercent}% · 点面共振 {activeTheme.resonanceScore}分
                </span>
              </div>

              <p
                data-testid="selected-theme-linkage-desc"
                className="text-xs text-[#d1d4dc] leading-relaxed"
              >
                {activeTheme.dragonLinkageDesc}
              </p>

              {/* 先锋龙 × 容量中军 联动双卡 */}
              <div className="grid grid-cols-2 gap-2 pt-1">
                <button
                  type="button"
                  data-testid="theme-pioneer-dragon-card"
                  onClick={() => onSelectSymbol(activeTheme.pioneerDragon.symbol)}
                  className="text-left p-2 rounded bg-[#1e222d] hover:bg-[#262b38] border border-[#F6465D]/40 transition-colors cursor-pointer"
                >
                  <div className="flex items-center justify-between gap-1 text-[10px] whitespace-nowrap">
                    <span className="text-[#F6465D] font-semibold">
                      [1] 点火先锋龙
                    </span>
                    <span className="font-mono tabular-nums text-[#9ca3af]">
                      {activeTheme.pioneerDragon.firstSealTime
                        ? `${activeTheme.pioneerDragon.firstSealTime}封`
                        : '日内领涨'}
                    </span>
                  </div>
                  <div className="mt-1 flex items-center justify-between">
                    <span className="text-xs font-bold text-white">
                      {activeTheme.pioneerDragon.name}
                    </span>
                    <span
                      className={`font-mono tabular-nums text-xs font-bold ${getSignedColorClass(
                        activeTheme.pioneerDragon.changePercent
                      )}`}
                    >
                      {formatSignedPercent(activeTheme.pioneerDragon.changePercent)}
                    </span>
                  </div>
                  <div className="mt-0.5 text-[10px] font-mono tabular-nums text-[#F59E0B]">
                    {activeTheme.pioneerDragon.consecutiveBoards >= 1
                      ? `当前 ${activeTheme.pioneerDragon.consecutiveBoards} 连板身位标杆`
                      : '日内弹性先锋标杆'}
                  </div>
                </button>

                <button
                  type="button"
                  data-testid="theme-capacity-core-card"
                  onClick={() => onSelectSymbol(activeTheme.capacityCore.symbol)}
                  className="text-left p-2 rounded bg-[#1e222d] hover:bg-[#262b38] border border-[#38bdf8]/40 transition-colors cursor-pointer"
                >
                  <div className="flex items-center justify-between gap-1 text-[10px] whitespace-nowrap">
                    <span className="text-[#38bdf8] font-semibold">
                      [2] 容量中军龙
                    </span>
                    <span className="font-mono tabular-nums text-[#9ca3af]">
                      成交 {formatAmountCN(activeTheme.capacityCore.amount)}
                    </span>
                  </div>
                  <div className="mt-1 flex items-center justify-between">
                    <span className="text-xs font-bold text-white">
                      {activeTheme.capacityCore.name}
                    </span>
                    <span
                      className={`font-mono tabular-nums text-xs font-bold ${getSignedColorClass(
                        activeTheme.capacityCore.changePercent
                      )}`}
                    >
                      {formatSignedPercent(activeTheme.capacityCore.changePercent)}
                    </span>
                  </div>
                  <div className="mt-0.5 text-[10px] font-mono tabular-nums text-[#9ca3af]">
                    大资金主战场流动性锚点
                  </div>
                </button>
              </div>
            </div>
          </div>

          {/* 底部：该题材内部涨停与核心联动梯队成员列表 */}
          <div className="flex-1 min-h-0 flex flex-col">
            <div className="flex items-center justify-between text-[11px] text-[#9ca3af] mb-1.5">
              <span className="font-semibold text-white">
                板块内涨停与跟风梯队成分股 ({activeTheme.memberStocks.length}只核心标的)
              </span>
              <span>点击联动切换个股</span>
            </div>

            <div className="overflow-y-auto max-h-[175px] rounded border border-[#2a2e39] bg-[#1e222d] divide-y divide-[#2a2e39]/60">
              {activeTheme.memberStocks.map((member) => {
                const isCurrentStock = member.symbol === selectedSymbol;
                return (
                  <button
                    key={`${activeTheme.sectorName}-${member.code}`}
                    type="button"
                    onClick={() => onSelectSymbol(member.symbol)}
                    className={`w-full px-2.5 py-1.5 flex items-center justify-between text-xs transition-colors cursor-pointer ${
                      isCurrentStock
                        ? 'bg-[#2962ff]/20'
                        : 'hover:bg-[#262b38]'
                    }`}
                  >
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span
                        className={`px-1.5 py-0.2 rounded text-[10px] font-semibold shrink-0 ${
                          member.dragonRole === 'SPACE_DRAGON' ||
                          member.dragonRole === 'PIONEER_DRAGON'
                            ? 'bg-[#F6465D]/20 text-[#F6465D]'
                            : member.dragonRole === 'CAPACITY_CORE'
                            ? 'bg-[#38bdf8]/20 text-[#38bdf8]'
                            : 'bg-[#131722] text-[#9ca3af]'
                        }`}
                      >
                        {member.roleLabel}
                      </span>
                      <span className="font-bold text-white truncate">
                        {member.name}
                      </span>
                      <span className="font-mono tabular-nums text-[10px] text-[#787b86]">
                        {member.code}
                      </span>
                    </div>

                    <div className="flex items-center gap-2 font-mono tabular-nums shrink-0">
                      {member.consecutiveBoards >= 1 ? (
                        <span className="px-1.5 py-0.2 rounded bg-[#F6465D]/20 text-[#F6465D] text-[10px] font-bold">
                          {member.consecutiveBoards}板
                          {member.firstSealTime ? ` · ${member.firstSealTime.slice(0, 5)}` : ''}
                        </span>
                      ) : (
                        <span className="text-[10px] text-[#787b86]">趋势跟风</span>
                      )}
                      <span
                        className={`font-bold w-14 text-right ${getSignedColorClass(
                          member.changePercent
                        )}`}
                      >
                        {formatSignedPercent(member.changePercent)}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* 三、全市场板块/题材共振监测与主力进攻方向全景排行表 */}
      <div
        data-testid="theme-resonance-comparison-table"
        className="overflow-x-auto"
      >
        <div className="px-3 py-2 bg-[#131722] border-b border-[#2a2e39] flex flex-wrap items-center justify-between gap-2 text-xs">
          <div className="flex items-center gap-1.5">
            <TrendingUp className="w-3.5 h-3.5 text-[#F6465D]" />
            <span className="font-bold text-white">
              全市场热门题材涨停密度与龙头联动排行矩阵
            </span>
          </div>
          <span className="text-[11px] text-[#787b86]">
            按题材点面共振得分降序排列 · 辅助快速锁定当日主流资金主攻板块
          </span>
        </div>

        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="border-b border-[#2a2e39] text-[#787b86] bg-[#161a24] text-[11px]">
              <th className="py-2 px-3 whitespace-nowrap">板块/题材名称</th>
              <th className="py-2 px-2 text-center whitespace-nowrap">主力进攻方向定性</th>
              <th className="py-2 px-2 text-right whitespace-nowrap">板块均涨幅</th>
              <th className="py-2 px-2.5 text-right whitespace-nowrap">
                涨停家数 / 涨停密度
              </th>
              <th className="py-2 px-2.5 whitespace-nowrap">
                点火先锋龙 (身位/封板)
              </th>
              <th className="py-2 px-2.5 whitespace-nowrap">
                容量中军龙 (涨幅/成交)
              </th>
              <th className="py-2 px-2.5 text-right whitespace-nowrap">
                领涨龙头联动指数
              </th>
              <th className="py-2 px-2.5 text-right whitespace-nowrap">
                主力净买额 / 火力占比
              </th>
              <th className="py-2 px-3 text-right whitespace-nowrap">点面共振总分</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#2a2e39]/60">
            {themes.map((theme) => {
              const isSelected = activeTheme.sectorName === theme.sectorName;
              const roleMeta = getAttackRoleStyle(
                theme.attackRole,
                theme.sectorChangePercent
              );

              return (
                <tr
                  key={theme.sectorName}
                  onClick={() => setSelectedSectorName(theme.sectorName)}
                  className={`cursor-pointer transition-colors ${
                    isSelected ? 'bg-[#2962ff]/15' : 'hover:bg-[#262b38]'
                  }`}
                >
                  <td className="py-2 px-3 whitespace-nowrap">
                    <div className="flex items-center gap-1.5">
                      <span className="font-bold text-white">{theme.sectorName}</span>
                      <span className="text-[10px] text-[#787b86] font-mono tabular-nums">
                        (红盘 {theme.upRatioPercent}%)
                      </span>
                    </div>
                  </td>

                  <td className="py-2 px-2 text-center whitespace-nowrap">
                    <span
                      className={`px-2 py-0.5 rounded border text-[11px] font-semibold ${roleMeta.badgeClass}`}
                    >
                      {theme.attackRoleLabel}
                    </span>
                  </td>

                  <td
                    className={`py-2 px-2 text-right font-mono tabular-nums font-bold whitespace-nowrap ${getSignedColorClass(
                      theme.sectorChangePercent
                    )}`}
                  >
                    {formatSignedPercent(theme.sectorChangePercent)}
                  </td>

                  <td className="py-2 px-2.5 text-right font-mono tabular-nums whitespace-nowrap">
                    <span className="font-bold text-[#F6465D]">
                      {theme.limitUpDensityPercent}%
                    </span>
                    <span className="ml-1.5 text-[11px] text-[#9ca3af]">
                      ({theme.limitUpCount}/{theme.sectorConstituentCount}家)
                    </span>
                  </td>

                  <td className="py-2 px-2.5 whitespace-nowrap">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectSymbol(theme.pioneerDragon.symbol);
                      }}
                      className="inline-flex items-center gap-1.5 hover:underline cursor-pointer"
                    >
                      <span className="font-semibold text-white">
                        {theme.pioneerDragon.name}
                      </span>
                      <span
                        className={`font-mono tabular-nums font-semibold ${getSignedColorClass(
                          theme.pioneerDragon.changePercent
                        )}`}
                      >
                        {formatSignedPercent(theme.pioneerDragon.changePercent)}
                      </span>
                      {theme.pioneerDragon.consecutiveBoards >= 1 && (
                        <span className="text-[10px] font-mono tabular-nums text-[#F59E0B]">
                          [{theme.pioneerDragon.consecutiveBoards}板]
                        </span>
                      )}
                    </button>
                  </td>

                  <td className="py-2 px-2.5 whitespace-nowrap">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectSymbol(theme.capacityCore.symbol);
                      }}
                      className="inline-flex items-center gap-1.5 hover:underline cursor-pointer"
                    >
                      <span className="font-semibold text-white">
                        {theme.capacityCore.name}
                      </span>
                      <span
                        className={`font-mono tabular-nums font-semibold ${getSignedColorClass(
                          theme.capacityCore.changePercent
                        )}`}
                      >
                        {formatSignedPercent(theme.capacityCore.changePercent)}
                      </span>
                      <span className="text-[10px] font-mono tabular-nums text-[#787b86]">
                        ({formatAmountCN(theme.capacityCore.amount)})
                      </span>
                    </button>
                  </td>

                  <td className="py-2 px-2.5 text-right font-mono tabular-nums whitespace-nowrap">
                    <span
                      className={`font-bold ${
                        theme.dragonLinkageScore >= 72
                          ? 'text-[#F6465D]'
                          : theme.dragonLinkageScore >= 48
                          ? 'text-[#F59E0B]'
                          : 'text-[#0ECB81]'
                      }`}
                    >
                      {theme.dragonLinkageScore}分
                    </span>
                    <span className="ml-1 text-[10px] text-[#787b86]">
                      ({theme.dragonLinkageStatus})
                    </span>
                  </td>

                  <td className="py-2 px-2.5 text-right font-mono tabular-nums whitespace-nowrap">
                    <span
                      className={`font-semibold ${
                        theme.totalNetInflowCNY >= 0
                          ? 'text-[#F6465D]'
                          : 'text-[#0ECB81]'
                      }`}
                    >
                      {theme.totalNetInflowCNY >= 0 ? '+' : '-'}
                      {formatAmountCN(Math.abs(theme.totalNetInflowCNY))}
                    </span>
                    <span className="ml-1 text-[10px] text-[#787b86]">
                      ({theme.capitalAttackSharePercent}%)
                    </span>
                  </td>

                  <td className="py-2 px-3 text-right font-mono tabular-nums whitespace-nowrap">
                    <span className="font-bold text-[#38bdf8]">
                      {theme.resonanceScore}
                    </span>
                    <span className="ml-1 text-[10px] text-[#9ca3af]">
                      ({theme.resonanceStatus})
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
};
