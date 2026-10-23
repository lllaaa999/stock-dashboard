import React, { useEffect, useMemo, useRef, useState } from 'react';
import * as d3 from 'd3';
import {
  Activity,
  Award,
  Flame,
  GitBranch,
  Layers,
  Sparkles,
  Target,
  TrendingUp,
  Users,
  Zap,
} from 'lucide-react';
import type {
  DragonTigerAnalysis,
  DragonTigerGraphLink,
  DragonTigerGraphNode,
  DragonTigerSeatNature,
} from '../types/market';
import { buildDragonTigerNetworkData } from '../utils/ultraShortQuant';
import { formatAmountCN, formatSignedPercent } from '../utils/marketCalc';

interface DragonTigerNetworkGraphProps {
  analysis: DragonTigerAnalysis;
  onSelectSymbol?: (symbol: string) => void;
}

interface SimNode extends DragonTigerGraphNode, d3.SimulationNodeDatum {
  x: number;
  y: number;
  fx?: number | null;
  fy?: number | null;
}

interface SimLink extends d3.SimulationLinkDatum<SimNode> {
  id: string;
  source: SimNode;
  target: SimNode;
  linkType: DragonTigerGraphLink['linkType'];
  side: DragonTigerGraphLink['side'];
  buyAmount: number;
  sellAmount: number;
  netAmount: number;
  strokeWidth: number;
  turnoverSharePercent: number;
  description: string;
}

function getSeatNodeColors(nature?: DragonTigerSeatNature): {
  fill: string;
  stroke: string;
  badgeBg: string;
  text: string;
} {
  switch (nature) {
    case 'HOT_MONEY':
      return {
        fill: '#2b1219',
        stroke: '#F6465D',
        badgeBg: 'bg-[#F6465D]/20 text-[#F6465D] border-[#F6465D]/50',
        text: '#F6465D',
      };
    case 'INSTITUTION':
      return {
        fill: '#292012',
        stroke: '#F59E0B',
        badgeBg: 'bg-[#F59E0B]/20 text-[#F59E0B] border-[#F59E0B]/50',
        text: '#F59E0B',
      };
    case 'QUANT_CAMP':
      return {
        fill: '#221433',
        stroke: '#a855f7',
        badgeBg: 'bg-[#a855f7]/20 text-[#c084fc] border-[#a855f7]/50',
        text: '#c084fc',
      };
    case 'RETAIL_CAMP':
      return {
        fill: '#102721',
        stroke: '#0ECB81',
        badgeBg: 'bg-[#0ECB81]/20 text-[#0ECB81] border-[#0ECB81]/50',
        text: '#0ECB81',
      };
    default:
      return {
        fill: '#162038',
        stroke: '#38bdf8',
        badgeBg: 'bg-[#38bdf8]/20 text-[#38bdf8] border-[#38bdf8]/50',
        text: '#38bdf8',
      };
  }
}

export const DragonTigerNetworkGraph: React.FC<DragonTigerNetworkGraphProps> = ({
  analysis,
  onSelectSymbol,
}) => {
  const [onlyHotMoney, setOnlyHotMoney] = useState<boolean>(false);
  const [includeAllyStocks, setIncludeAllyStocks] = useState<boolean>(true);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  // 构建网络图节点与连线数据
  const networkData = useMemo(
    () =>
      buildDragonTigerNetworkData(analysis, {
        onlyHotMoney,
        includeAllyStocks,
      }),
    [analysis, onlyHotMoney, includeAllyStocks]
  );

  // 所有的营业部节点列表
  const seatNodes = useMemo(
    () => networkData.nodes.filter((n) => n.nodeType === 'BROKER_SEAT'),
    [networkData.nodes]
  );

  // 默认选中第一个游资大佬节点（若无则选中买一节点）
  const activeSeatNode = useMemo(() => {
    if (selectedNodeId) {
      const found = seatNodes.find((n) => n.id === selectedNodeId);
      if (found) return found;
    }
    const firstHotMoney = seatNodes.find((n) => n.nature === 'HOT_MONEY');
    return firstHotMoney ?? seatNodes[0] ?? null;
  }, [seatNodes, selectedNodeId]);

  // 当切换股票或过滤模式时，若当前选中节点不在新拓扑中则自动对齐到默认游资节点
  useEffect(() => {
    if (activeSeatNode && activeSeatNode.id !== selectedNodeId) {
      setSelectedNodeId(activeSeatNode.id);
    }
  }, [activeSeatNode, selectedNodeId]);

  // 使用 D3.js (d3.forceSimulation + d3.scaleLinear) 计算节点稳定拓扑坐标与连线粗细
  const layout = useMemo(() => {
    const width = 680;
    const height = 430;
    const cx = width / 2;
    const cy = height / 2 - 6;

    // 使用 d3.scaleLinear 映射买入金额到连线粗细 (2.0px ~ 9.5px)
    const strokeScale = d3
      .scaleLinear()
      .domain([
        Math.max(0, networkData.minBuyAmount),
        Math.max(networkData.minBuyAmount + 1, networkData.maxBuyAmount),
      ])
      .range([2.0, 9.5])
      .clamp(true);

    const brokerNodes = networkData.nodes.filter((n) => n.nodeType === 'BROKER_SEAT');
    const allyNodes = networkData.nodes.filter((n) => n.nodeType === 'ALLY_STOCK');

    // 采用椭圆形初始靶向锚点 + D3 力导向排斥碰撞，充分利用宽屏横向空间并消除标签重叠
    const simNodes: SimNode[] = networkData.nodes.map((node) => {
      if (node.nodeType === 'TARGET_STOCK') {
        return {
          ...node,
          x: cx,
          y: cy,
          fx: cx,
          fy: cy,
        };
      }
      if (node.nodeType === 'BROKER_SEAT') {
        const idx = brokerNodes.findIndex((b) => b.id === node.id);
        const total = Math.max(1, brokerNodes.length);
        const angle = (idx / total) * Math.PI * 2 - Math.PI / 2;
        const rx = 198;
        const ry = 136;
        return {
          ...node,
          x: cx + Math.cos(angle) * rx,
          y: cy + Math.sin(angle) * ry,
        };
      }
      const idx = allyNodes.findIndex((a) => a.id === node.id);
      const total = Math.max(1, allyNodes.length);
      const angle = ((idx + 0.5) / total) * Math.PI * 2 - Math.PI / 3;
      const rx = 285;
      const ry = 172;
      return {
        ...node,
        x: cx + Math.cos(angle) * rx,
        y: cy + Math.sin(angle) * ry,
      };
    });

    const nodeById = new Map<string, SimNode>(simNodes.map((n) => [n.id, n]));

    const simLinks: SimLink[] = networkData.links
      .map((l): SimLink | null => {
        const source = nodeById.get(l.sourceId);
        const target = nodeById.get(l.targetId);
        if (!source || !target) return null;
        const computedWidth =
          l.linkType === 'CO_APPEAR_STOCK'
            ? Math.max(1.8, Number((strokeScale(l.buyAmount) * 0.62).toFixed(2)))
            : Number(strokeScale(l.buyAmount).toFixed(2));
        return {
          ...l,
          source,
          target,
          strokeWidth: computedWidth,
        };
      })
      .filter((l): l is SimLink => l !== null);

    // 保存初始椭圆锚点以供 d3.forceX / d3.forceY 温柔约束
    const targetPos = new Map<string, { tx: number; ty: number }>(
      simNodes.map((n) => [n.id, { tx: n.x, ty: n.y }])
    );

    const simulation = d3
      .forceSimulation<SimNode>(simNodes)
      .force(
        'link',
        d3
          .forceLink<SimNode, SimLink>(simLinks)
          .id((d) => d.id)
          .distance((d) => (d.linkType === 'CO_APPEAR_STOCK' ? 84 : 155))
          .strength((d) => (d.linkType === 'CO_APPEAR_STOCK' ? 0.35 : 0.45))
      )
      .force('charge', d3.forceManyBody<SimNode>().strength(-260))
      .force(
        'x',
        d3
          .forceX<SimNode>((d) => targetPos.get(d.id)?.tx ?? cx)
          .strength((d) => (d.nodeType === 'TARGET_STOCK' ? 1 : 0.78))
      )
      .force(
        'y',
        d3
          .forceY<SimNode>((d) => targetPos.get(d.id)?.ty ?? cy)
          .strength((d) => (d.nodeType === 'TARGET_STOCK' ? 1 : 0.78))
      )
      .force(
        'collide',
        d3
          .forceCollide<SimNode>()
          .radius((d) => (d.nodeType === 'BROKER_SEAT' ? d.radius + 32 : d.radius + 22))
          .iterations(4)
      )
      .stop();

    for (let i = 0; i < 140; i++) {
      simulation.tick();
    }

    // 边界安全约束，防止节点或底部双行标签超出 SVG 视口
    for (const node of simNodes) {
      if (node.nodeType !== 'TARGET_STOCK') {
        node.x = Math.max(68, Math.min(width - 68, node.x));
        node.y = Math.max(38, Math.min(height - 54, node.y));
      }
    }

    return {
      width,
      height,
      cx,
      cy,
      nodes: simNodes,
      links: simLinks,
    };
  }, [networkData]);

  // D3 脉冲高亮动效绑定
  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    svg
      .selectAll('.d3-active-ring')
      .attr('opacity', 0.95)
      .transition()
      .duration(650)
      .attr('opacity', 0.4);
  }, [activeSeatNode?.id, analysis.symbol]);

  const activeProfile = activeSeatNode?.activityProfile;

  return (
    <div
      data-testid="dragon-tiger-d3-network-panel"
      className="border-b border-[#2a2e39] bg-[#131722]"
    >
      {/* 顶部工具栏：关联网络图说明 + 游资大佬筛选开关 */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 bg-[#161a24] border-b border-[#2a2e39]">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1.5">
            <GitBranch className="w-4 h-4 text-[#F6465D]" />
            <span className="text-xs font-bold text-white">
              D3.js 游资大佬席位关联网络图 (个股 — 营业部资金拓扑)
            </span>
          </div>
          <span className="px-2 py-0.5 rounded bg-[#F6465D]/15 text-[#F6465D] border border-[#F6465D]/40 text-[11px] font-mono tabular-nums font-semibold">
            游资席位 {networkData.hotMoneySeatCount} 家 · 游资买额{' '}
            {formatAmountCN(networkData.totalHotMoneyBuyAmount)}
          </span>
          <span className="text-[11px] text-[#9ca3af] hidden sm:inline">
            连线粗细正比于席位买入金额 · 点击任意席位节点展示『席位活跃度与历史战绩』
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
          <button
            type="button"
            data-testid="d3-filter-all-seats"
            onClick={() => setOnlyHotMoney(false)}
            className={`px-2 py-0.5 rounded border transition-colors cursor-pointer ${
              !onlyHotMoney
                ? 'bg-[#2962ff] border-[#2962ff] text-white font-semibold'
                : 'bg-[#0d0e12] border-[#2a2e39] text-[#9ca3af] hover:text-white'
            }`}
          >
            全部上榜席位 ({seatNodes.length})
          </button>
          <button
            type="button"
            data-testid="d3-filter-hot-money-only"
            onClick={() => setOnlyHotMoney(true)}
            className={`px-2 py-0.5 rounded border transition-colors cursor-pointer ${
              onlyHotMoney
                ? 'bg-[#F6465D] border-[#F6465D] text-white font-semibold'
                : 'bg-[#0d0e12] border-[#2a2e39] text-[#9ca3af] hover:text-white'
            }`}
          >
            仅游资大佬席位
          </button>
          <button
            type="button"
            data-testid="d3-toggle-ally-stocks"
            onClick={() => setIncludeAllyStocks((prev) => !prev)}
            className={`px-2 py-0.5 rounded border transition-colors cursor-pointer ${
              includeAllyStocks
                ? 'bg-[#1e222d] border-[#38bdf8]/60 text-[#38bdf8] font-medium'
                : 'bg-[#0d0e12] border-[#2a2e39] text-[#787b86] hover:text-white'
            }`}
          >
            {includeAllyStocks ? '已展开: 游资跨股协同标的' : '展开游资协同标的'}
          </button>
        </div>
      </div>

      {/* 快捷游资/营业部节点切换栏（与 D3 网络图节点双向同步，方便一键点选检视活跃度） */}
      <div className="flex flex-wrap items-center gap-1.5 px-3 py-1.5 bg-[#0f131c] border-b border-[#2a2e39] text-[11px]">
        <span className="text-[#787b86] mr-1 flex items-center gap-1">
          <Target className="w-3 h-3 text-[#F59E0B]" />
          点击检视席位活跃度:
        </span>
        {seatNodes.map((seatNode, index) => {
          const isSelected = activeSeatNode?.id === seatNode.id;
          const colors = getSeatNodeColors(seatNode.nature);
          return (
            <button
              key={seatNode.id}
              type="button"
              data-testid={`d3-seat-pill-${index}`}
              onClick={() => setSelectedNodeId(seatNode.id)}
              className={`flex items-center gap-1 px-2 py-0.5 rounded border transition-all cursor-pointer whitespace-nowrap ${
                isSelected
                  ? 'bg-[#2962ff]/25 border-[#38bdf8] text-white font-bold shadow-sm'
                  : 'bg-[#161a24] border-[#2a2e39] text-[#9ca3af] hover:text-white'
              }`}
            >
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{ backgroundColor: colors.stroke }}
              />
              <span>{seatNode.rankLabel}</span>
              <span>{seatNode.label}</span>
              <span className="font-mono tabular-nums text-[10px] text-[#F6465D]">
                买{formatAmountCN(seatNode.buyAmount)}
              </span>
            </button>
          );
        })}
      </div>

      {/* 主体双栏：左侧 D3.js 力导向关联网络图 SVG，右侧 选中席位活跃度与历史战绩深度画像 */}
      <div className="grid grid-cols-1 xl:grid-cols-12 divide-y xl:divide-y-0 xl:divide-x divide-[#2a2e39]">
        {/* 左侧 7 列：D3.js 关联网络图 */}
        <div className="xl:col-span-7 flex flex-col justify-between bg-[#0d0e12] p-2.5 relative">
          <div className="w-full overflow-hidden rounded border border-[#2a2e39]/80 bg-[#0b0e14]">
            <svg
              ref={svgRef}
              data-testid="dragon-tiger-d3-svg"
              viewBox={`0 0 ${layout.width} ${layout.height}`}
              className="w-full h-[380px] sm:h-[410px] select-none block"
            >
              <defs>
                <pattern
                  id="dt-grid-pattern"
                  width="28"
                  height="28"
                  patternUnits="userSpaceOnUse"
                >
                  <path
                    d="M 28 0 L 0 0 0 28"
                    fill="none"
                    stroke="#1e222d"
                    strokeWidth="0.7"
                  />
                </pattern>
                <radialGradient id="dt-center-glow" cx="50%" cy="50%" r="50%">
                  <stop offset="0%" stopColor="#F6465D" stopOpacity="0.22" />
                  <stop offset="65%" stopColor="#2962ff" stopOpacity="0.06" />
                  <stop offset="100%" stopColor="#0b0e14" stopOpacity="0" />
                </radialGradient>
              </defs>

              {/* 背景坐标网格与椭圆轨道环 */}
              <rect width={layout.width} height={layout.height} fill="url(#dt-grid-pattern)" />
              <circle
                cx={layout.cx}
                cy={layout.cy}
                r={195}
                fill="url(#dt-center-glow)"
                pointerEvents="none"
              />
              <ellipse
                cx={layout.cx}
                cy={layout.cy}
                rx={198}
                ry={136}
                fill="none"
                stroke="#2a2e39"
                strokeDasharray="4 4"
                strokeWidth="1"
              />
              {includeAllyStocks && (
                <ellipse
                  cx={layout.cx}
                  cy={layout.cy}
                  rx={285}
                  ry={172}
                  fill="none"
                  stroke="#1e222d"
                  strokeDasharray="2 5"
                  strokeWidth="1"
                />
              )}

              {/* 1. 渲染连线层 (连线粗细 strokeWidth 严格正比于席位买入金额 buyAmount) */}
              <g className="d3-links-layer">
                {layout.links.map((link, idx) => {
                  const isSelectedLink =
                    activeSeatNode &&
                    (link.source.id === activeSeatNode.id ||
                      link.target.id === activeSeatNode.id);

                  const strokeColor =
                    link.linkType === 'CO_APPEAR_STOCK'
                      ? '#38bdf8'
                      : link.side === 'BUY'
                      ? '#F6465D'
                      : '#0ECB81';

                  const midX = (link.source.x + link.target.x) / 2;
                  const midY = (link.source.y + link.target.y) / 2;

                  return (
                    <g key={link.id}>
                      {/* 选中连线高亮外发光底线 */}
                      {isSelectedLink && (
                        <line
                          x1={link.source.x}
                          y1={link.source.y}
                          x2={link.target.x}
                          y2={link.target.y}
                          stroke={strokeColor}
                          strokeWidth={link.strokeWidth + 6}
                          strokeOpacity={0.24}
                          strokeLinecap="round"
                        />
                      )}

                      {/* 主连线：strokeWidth 由买入金额线性映射 */}
                      <line
                        data-testid={`d3-link-${idx}`}
                        data-buy-amount={link.buyAmount}
                        data-stroke-width={link.strokeWidth}
                        x1={link.source.x}
                        y1={link.source.y}
                        x2={link.target.x}
                        y2={link.target.y}
                        stroke={strokeColor}
                        strokeWidth={link.strokeWidth}
                        strokeOpacity={
                          link.linkType === 'CO_APPEAR_STOCK'
                            ? isSelectedLink
                              ? 0.88
                              : 0.38
                            : isSelectedLink
                            ? 0.98
                            : 0.72
                        }
                        strokeDasharray={link.linkType === 'CO_APPEAR_STOCK' ? '4 3' : undefined}
                        strokeLinecap="round"
                      />

                      {/* 选中席位连线中点高亮显示买入金额与粗细映射值 */}
                      {isSelectedLink && link.linkType !== 'CO_APPEAR_STOCK' && (
                        <g transform={`translate(${midX}, ${midY})`}>
                          <rect
                            x={-36}
                            y={-9}
                            width={72}
                            height={18}
                            rx={4}
                            fill="#0d0e12"
                            fillOpacity={0.95}
                            stroke="#38bdf8"
                            strokeWidth={1.3}
                          />
                          <text
                            textAnchor="middle"
                            dominantBaseline="central"
                            fill="#ffffff"
                            fontSize="9.5"
                            fontFamily="JetBrains Mono, monospace"
                            fontWeight="700"
                          >
                            买{formatAmountCN(link.buyAmount)}
                          </text>
                        </g>
                      )}
                    </g>
                  );
                })}
              </g>

              {/* 2. 渲染节点层 (中心选定个股 + 游资大佬/龙虎榜营业部节点 + 跨股协同标的节点) */}
              <g className="d3-nodes-layer">
                {layout.nodes.map((node) => {
                  if (node.nodeType === 'TARGET_STOCK') {
                    return (
                      <g
                        key={node.id}
                        data-testid="d3-target-stock-node"
                        transform={`translate(${node.x}, ${node.y})`}
                        className="cursor-pointer focus:outline-none"
                        onClick={() => {
                          if (seatNodes[0]) setSelectedNodeId(seatNodes[0].id);
                        }}
                      >
                        <circle
                          r={node.radius + 7}
                          fill="none"
                          stroke="#F6465D"
                          strokeWidth="1.5"
                          strokeDasharray="3 3"
                          opacity={0.65}
                        />
                        <circle
                          r={node.radius}
                          fill="#1e1b2e"
                          stroke="#F6465D"
                          strokeWidth="3"
                        />
                        <text
                          y={-5}
                          textAnchor="middle"
                          fill="#ffffff"
                          fontSize="12"
                          fontWeight="800"
                        >
                          {node.label}
                        </text>
                        <text
                          y={11}
                          textAnchor="middle"
                          fill="#F59E0B"
                          fontSize="9.5"
                          fontFamily="JetBrains Mono, monospace"
                          fontWeight="600"
                        >
                          {analysis.code}
                        </text>
                      </g>
                    );
                  }

                  if (node.nodeType === 'ALLY_STOCK') {
                    return (
                      <g
                        key={node.id}
                        data-testid={`d3-ally-stock-node-${node.symbol}`}
                        transform={`translate(${node.x}, ${node.y})`}
                        className="cursor-pointer focus:outline-none"
                        onClick={() => {
                          if (node.symbol && onSelectSymbol) {
                            onSelectSymbol(node.symbol);
                          }
                        }}
                      >
                        <circle
                          r={node.radius}
                          fill="#111927"
                          stroke="#38bdf8"
                          strokeWidth="1.6"
                          strokeDasharray="2 2"
                        />
                        <text
                          y={-2}
                          textAnchor="middle"
                          fill="#38bdf8"
                          fontSize="10"
                          fontWeight="700"
                        >
                          {node.label}
                        </text>
                        <text y={9} textAnchor="middle" fill="#9ca3af" fontSize="8">
                          协同股
                        </text>
                      </g>
                    );
                  }

                  // 龙虎榜营业部节点 (BROKER_SEAT)
                  const seatIdx = seatNodes.findIndex((s) => s.id === node.id);
                  const isSelected = activeSeatNode?.id === node.id;
                  const colors = getSeatNodeColors(node.nature);
                  const activityScore = node.activityProfile?.activityScore ?? 88;

                  return (
                    <g
                      key={node.id}
                      role="button"
                      tabIndex={0}
                      aria-label={`${node.label} ${node.subLabel} 买入 ${formatAmountCN(node.buyAmount)}`}
                      data-testid={`d3-seat-node-${seatIdx}`}
                      data-seat-branch={node.branchName}
                      transform={`translate(${node.x}, ${node.y})`}
                      className="cursor-pointer focus:outline-none"
                      style={{ outline: 'none' }}
                      onClick={() => setSelectedNodeId(node.id)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          setSelectedNodeId(node.id);
                        }
                      }}
                    >
                      {/* 选中态动态外圈 */}
                      {isSelected && (
                        <circle
                          className="d3-active-ring"
                          r={node.radius + 7}
                          fill="none"
                          stroke="#38bdf8"
                          strokeWidth="2.5"
                        />
                      )}

                      {/* 营业部节点主圆 */}
                      <circle
                        r={node.radius}
                        fill={colors.fill}
                        stroke={isSelected ? '#ffffff' : colors.stroke}
                        strokeWidth={isSelected ? 3 : 2.2}
                      />

                      {/* 节点内显示席位顺位 (买1~买5 / 卖1~卖5) 与活跃度分 */}
                      <text
                        y={-4}
                        textAnchor="middle"
                        fill="#ffffff"
                        fontSize="10.5"
                        fontWeight="800"
                        fontFamily="JetBrains Mono, monospace"
                      >
                        {node.rankLabel}
                      </text>
                      <text
                        y={9}
                        textAnchor="middle"
                        fill={colors.text}
                        fontSize="8.5"
                        fontWeight="700"
                        fontFamily="JetBrains Mono, monospace"
                      >
                        活{activityScore}
                      </text>

                      {/* 节点下方双行胶囊：第1行游资/机构名号，第2行买入金额 */}
                      <g transform={`translate(0, ${node.radius + 15})`}>
                        <rect
                          x={-52}
                          y={-12}
                          width={104}
                          height={26}
                          rx={4}
                          fill={isSelected ? '#1e293b' : '#131722'}
                          fillOpacity={0.94}
                          stroke={isSelected ? '#38bdf8' : colors.stroke}
                          strokeWidth={isSelected ? 1.4 : 0.8}
                        />
                        <text
                          y={-3}
                          textAnchor="middle"
                          dominantBaseline="central"
                          fill={isSelected ? '#ffffff' : colors.text}
                          fontSize="9.5"
                          fontWeight="700"
                        >
                          {node.label.length > 10 ? node.label.slice(0, 10) : node.label}
                        </text>
                        <text
                          y={8}
                          textAnchor="middle"
                          dominantBaseline="central"
                          fill="#d1d4dc"
                          fontSize="8.5"
                          fontFamily="JetBrains Mono, monospace"
                          fontWeight="600"
                        >
                          买{formatAmountCN(node.buyAmount)}
                        </text>
                      </g>
                    </g>
                  );
                })}
              </g>
            </svg>
          </div>

          {/* 底部图例说明条 */}
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 px-1 text-[11px] text-[#9ca3af]">
            <div className="flex flex-wrap items-center gap-3">
              <span className="flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded-full bg-[#F6465D] inline-block" />
                <span>游资大佬席位</span>
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded-full bg-[#F59E0B] inline-block" />
                <span>机构/北向专席</span>
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded-full bg-[#a855f7] inline-block" />
                <span>量化大本营</span>
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded-full bg-[#0ECB81] inline-block" />
                <span>拉萨散户席位</span>
              </span>
            </div>

            <div className="flex items-center gap-2 font-mono tabular-nums text-[10px]">
              <span className="text-[#787b86]">连线粗细映射买额:</span>
              <span className="inline-flex items-center gap-1">
                <span className="w-4 h-[2px] bg-[#F6465D] inline-block" />
                {formatAmountCN(networkData.minBuyAmount)}
              </span>
              <span>→</span>
              <span className="inline-flex items-center gap-1">
                <span className="w-5 h-[6px] bg-[#F6465D] rounded-full inline-block" />
                {formatAmountCN(networkData.maxBuyAmount)}
              </span>
            </div>
          </div>
        </div>

        {/* 右侧 5 列：点击节点展示的『席位活跃度与历史战绩深度画像』 */}
        <div
          data-testid="dragon-tiger-seat-activity-inspector"
          className="xl:col-span-5 p-3 bg-[#131722] flex flex-col justify-between space-y-2.5"
        >
          {activeSeatNode && activeProfile ? (
            <>
              {/* 1. 席位头部身份与综合活跃度指数 */}
              <div className="space-y-2">
                <div className="flex items-start justify-between gap-2 border-b border-[#2a2e39] pb-2">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="px-1.5 py-0.5 rounded bg-[#2962ff]/20 text-[#38bdf8] border border-[#38bdf8]/40 text-[10px] font-mono font-bold">
                        {activeSeatNode.rankLabel}
                      </span>
                      <span
                        className={`px-1.5 py-0.5 rounded border text-[10px] font-bold ${
                          getSeatNodeColors(activeProfile.nature).badgeBg
                        }`}
                      >
                        {activeProfile.natureLabel}
                      </span>
                      <span className="px-1.5 py-0.5 rounded bg-[#F59E0B]/15 text-[#F59E0B] border border-[#F59E0B]/30 text-[10px] font-semibold">
                        {activeProfile.activityLevelLabel}
                      </span>
                    </div>

                    <h4
                      data-testid="inspector-seat-tag"
                      className="text-sm font-bold text-white mt-1.5 truncate"
                    >
                      {activeProfile.seatTag}
                    </h4>
                    <div
                      data-testid="inspector-branch-name"
                      className="text-[11px] text-[#9ca3af] truncate mt-0.5"
                    >
                      {activeProfile.branchName}
                    </div>
                  </div>

                  {/* 席位活跃度仪表分 */}
                  <div className="bg-[#1e222d] border border-[#2a2e39] rounded px-2.5 py-1.5 text-right shrink-0">
                    <div className="text-[10px] text-[#787b86] flex items-center justify-end gap-1">
                      <Flame className="w-3 h-3 text-[#F6465D]" />
                      <span>席位活跃度</span>
                    </div>
                    <div
                      data-testid="inspector-activity-score"
                      className="font-mono tabular-nums text-lg font-extrabold text-[#F6465D]"
                    >
                      {activeProfile.activityScore}
                      <span className="text-[11px] text-[#9ca3af] font-normal"> / 100</span>
                    </div>
                  </div>
                </div>

                {/* 当日针对选定个股的买卖博弈明细 */}
                <div className="grid grid-cols-3 gap-2 bg-[#161a24] p-2 rounded border border-[#2a2e39] font-mono tabular-nums text-xs">
                  <div>
                    <div className="text-[10px] text-[#787b86] font-sans">本股当日买入</div>
                    <div
                      data-testid="inspector-current-buy"
                      className="font-bold text-[#F6465D] mt-0.5"
                    >
                      {activeSeatNode.buyAmount > 0
                        ? formatAmountCN(activeSeatNode.buyAmount)
                        : '0.00元'}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-[#787b86] font-sans">本股当日卖出</div>
                    <div className="font-semibold text-[#0ECB81] mt-0.5">
                      {activeSeatNode.sellAmount > 0
                        ? formatAmountCN(activeSeatNode.sellAmount)
                        : '0.00元 (锁仓)'}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-[#787b86] font-sans">本股席位净额</div>
                    <div
                      className={`font-bold mt-0.5 ${
                        activeSeatNode.netAmount >= 0 ? 'text-[#F6465D]' : 'text-[#0ECB81]'
                      }`}
                    >
                      {activeSeatNode.netAmount >= 0 ? '+' : '-'}
                      {formatAmountCN(Math.abs(activeSeatNode.netAmount))}
                    </div>
                  </div>
                </div>

                {/* 2. 近 30 日席位活跃度核心量化指标 4 宫格 */}
                <div className="grid grid-cols-2 gap-2">
                  <div className="p-2 rounded bg-[#1e222d] border border-[#2a2e39]">
                    <div className="text-[10px] text-[#787b86] flex items-center gap-1">
                      <Activity className="w-3 h-3 text-[#38bdf8]" />
                      近30日上榜次数
                    </div>
                    <div
                      data-testid="inspector-appearances-30d"
                      className="font-mono tabular-nums text-sm font-bold text-white mt-0.5"
                    >
                      {activeProfile.appearances30d} 次
                    </div>
                    <div className="text-[10px] text-[#9ca3af] font-mono tabular-nums">
                      场均买 {formatAmountCN(activeProfile.avgSingleBuyAmount)}
                    </div>
                  </div>

                  <div className="p-2 rounded bg-[#1e222d] border border-[#2a2e39]">
                    <div className="text-[10px] text-[#787b86] flex items-center gap-1">
                      <Zap className="w-3 h-3 text-[#F59E0B]" />
                      近30日总动用资金
                    </div>
                    <div
                      data-testid="inspector-capital-30d"
                      className="font-mono tabular-nums text-sm font-bold text-[#F59E0B] mt-0.5"
                    >
                      {formatAmountCN(activeProfile.totalCapital30d)}
                    </div>
                    <div className="text-[10px] text-[#9ca3af]">单席位核心体量</div>
                  </div>

                  <div className="p-2 rounded bg-[#1e222d] border border-[#2a2e39]">
                    <div className="text-[10px] text-[#787b86] flex items-center gap-1">
                      <TrendingUp className="w-3 h-3 text-[#F6465D]" />
                      上榜次日平均溢价
                    </div>
                    <div
                      data-testid="inspector-nextday-premium"
                      className={`font-mono tabular-nums text-sm font-bold mt-0.5 ${
                        activeProfile.nextDayAvgPremiumPercent >= 0
                          ? 'text-[#F6465D]'
                          : 'text-[#0ECB81]'
                      }`}
                    >
                      {formatSignedPercent(activeProfile.nextDayAvgPremiumPercent)}
                    </div>
                    <div className="text-[10px] text-[#9ca3af]">T+1 接力溢价效应</div>
                  </div>

                  <div className="p-2 rounded bg-[#1e222d] border border-[#2a2e39]">
                    <div className="text-[10px] text-[#787b86] flex items-center gap-1">
                      <Award className="w-3 h-3 text-[#0ECB81]" />
                      主封次日红盘胜率
                    </div>
                    <div
                      data-testid="inspector-win-rate"
                      className="font-mono tabular-nums text-sm font-bold text-white mt-0.5"
                    >
                      {activeProfile.sealWinRatePercent}%
                    </div>
                    <div className="text-[10px] text-[#9ca3af] truncate">
                      {activeProfile.holdingHorizon.split('/')[0]}
                    </div>
                  </div>
                </div>

                {/* 3. 近 4 周上榜活跃度柱状趋势 & 主攻题材偏好 + 协同游资盟友 */}
                <div className="p-2.5 rounded bg-[#161a24] border border-[#2a2e39] space-y-2">
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="text-[#9ca3af] font-semibold flex items-center gap-1">
                      <Layers className="w-3 h-3 text-[#38bdf8]" />
                      近 4 周上榜出击频次与资金活跃度趋势
                    </span>
                    <span className="font-mono tabular-nums text-[10px] text-[#787b86]">
                      {activeProfile.holdingHorizon.split('/')[0]}
                    </span>
                  </div>

                  <div className="grid grid-cols-4 gap-2 pt-0.5">
                    {activeProfile.monthlyTrend.map((w) => {
                      const maxCount = Math.max(
                        ...activeProfile.monthlyTrend.map((m) => m.count),
                        1
                      );
                      const heightPct = Math.max(25, Math.round((w.count / maxCount) * 100));
                      return (
                        <div
                          key={w.weekLabel}
                          className="bg-[#0d0e12] p-1.5 rounded border border-[#2a2e39]/70 flex flex-col justify-between"
                        >
                          <div className="flex items-center justify-between text-[10px] font-mono tabular-nums">
                            <span className="text-[#787b86]">{w.weekLabel}</span>
                            <span className="text-white font-bold">{w.count}次</span>
                          </div>
                          <div className="w-full h-1.5 bg-[#1e222d] rounded overflow-hidden my-1">
                            <div
                              className="h-full bg-[#F6465D] rounded"
                              style={{ width: `${heightPct}%` }}
                            />
                          </div>
                          <div className="text-[10px] font-mono tabular-nums text-[#9ca3af] text-right">
                            {formatAmountCN(w.capital)}
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  <div className="flex flex-wrap items-center justify-between gap-1.5 pt-1 border-t border-[#2a2e39]/60 text-[11px]">
                    <div className="flex flex-wrap items-center gap-1">
                      <span className="text-[#787b86]">主攻题材:</span>
                      {activeProfile.favoriteSectors.map((sec) => (
                        <span
                          key={sec}
                          className="px-1.5 py-0.5 rounded bg-[#1e222d] text-[#d1d4dc] border border-[#2a2e39] text-[10px]"
                        >
                          {sec}
                        </span>
                      ))}
                    </div>
                    <div className="flex flex-wrap items-center gap-1">
                      <Users className="w-3 h-3 text-[#F59E0B]" />
                      <span className="text-[#787b86]">高频协同:</span>
                      <span className="text-[#F59E0B] text-[10px] font-medium">
                        {activeProfile.coAppearingAllies.slice(0, 2).join(' · ')}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* 4. 该席位近期上榜代表战役列表 */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="font-semibold text-white flex items-center gap-1">
                    <Sparkles className="w-3 h-3 text-[#F59E0B]" />
                    该席位近期龙虎榜协同战役明细
                  </span>
                  <span className="text-[10px] text-[#787b86]">点击关联个股可联动切换</span>
                </div>
                <div className="divide-y divide-[#2a2e39]/70 rounded border border-[#2a2e39] bg-[#0d0e12]">
                  {activeProfile.recentBattles.map((battle, i) => (
                    <div
                      key={`${battle.symbol}-${i}`}
                      onClick={() => {
                        if (onSelectSymbol) onSelectSymbol(battle.symbol);
                      }}
                      className="px-2.5 py-1.5 flex items-center justify-between gap-2 text-[11px] hover:bg-[#1e222d]/70 cursor-pointer transition-colors"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="font-bold text-white">{battle.name}</span>
                          <span className="font-mono tabular-nums text-[10px] text-[#787b86]">
                            {battle.symbol}
                          </span>
                          <span className="px-1 py-0.2 rounded bg-[#1e222d] text-[#9ca3af] text-[10px]">
                            {battle.date}
                          </span>
                        </div>
                        <div className="text-[10px] text-[#9ca3af] truncate mt-0.5">
                          {battle.roleLabel}
                        </div>
                      </div>

                      <div className="text-right font-mono tabular-nums shrink-0">
                        <div className="text-[#F6465D] font-semibold">
                          买 {formatAmountCN(battle.buyAmount)}
                        </div>
                        <div
                          className={`text-[10px] ${
                            battle.nextDayPremiumPercent >= 0
                              ? 'text-[#F59E0B]'
                              : 'text-[#0ECB81]'
                          }`}
                        >
                          次日溢价 {formatSignedPercent(battle.nextDayPremiumPercent)}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
};
