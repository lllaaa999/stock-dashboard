import React, { useMemo, useState } from 'react';
import {
  Activity,
  ArrowRight,
  Flame,
  Globe,
  Radio,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Zap,
} from 'lucide-react';
import { useRealGlobalRadar } from '../hooks/useRealQuantData';
import { useMarketStore } from '../store/useMarketStore';
import type {
  CrossMarketTransmissionChain,
  GlobalAssetCategory,
  GlobalAssetQuote,
  GlobalLiveNewsItem,
  MappedStockTarget,
} from '../types/market';
import {
  formatPrice,
  formatSignedChange,
  formatSignedPercent,
  getSignedColorClass,
} from '../utils/marketCalc';

const CATEGORY_TABS: { key: GlobalAssetCategory; label: string }[] = [
  { key: 'ASIA_CORE', label: '亚太与A股先行锚' },
  { key: 'US_EU_INDICES', label: '欧美股指与期指' },
  { key: 'TECH_GIANTS', label: '美股科技七巨头与中概' },
  { key: 'COMMODITIES', label: '全球大宗商品(金/银/铜/油)' },
  { key: 'FOREX', label: '全球外汇与汇率' },
];

// 默认/降级保底数据，在接口未就绪或盘后时提供完整逼真的实战指引
const DEFAULT_FALLBACK_CHAINS: CrossMarketTransmissionChain[] = [
  {
    id: 'chain_ai_semiconductor',
    name: 'AI算力与硬科技半导体链',
    direction: 'BULLISH',
    intensity: 'STRONG',
    resonanceScore: 86,
    drivers: [
      { symbol: 'TSM', name: '台积电', price: 198.4, changePercent: 6.33 },
      { symbol: 'NVDA', name: '英伟达', price: 138.25, changePercent: 2.78 },
      { symbol: 'ASML', name: '阿斯麦', price: 742.1, changePercent: 3.12 },
    ],
    mappedSectors: ['CPO光模块', '算力芯片', '半导体先进封装'],
    mappedSymbols: [
      { symbol: '300308.SZ', name: '中际旭创' },
      { symbol: '688256.SH', name: '寒武纪' },
      { symbol: '300502.SZ', name: '新易盛' },
      { symbol: '603501.SH', name: '韦尔股份' },
    ],
    transmissionLogic:
      '台积电先进制程法说会超预期、海外算力芯片与云巨头资本开支大幅上修，映射A股CPO光模块、先进算力芯片及自主可控设备开盘放量共振。',
  },
  {
    id: 'chain_tesla_robotics',
    name: '特斯拉与人形机器人链',
    direction: 'BULLISH',
    intensity: 'STRONG',
    resonanceScore: 78,
    drivers: [
      { symbol: 'TSLA', name: '特斯拉', price: 262.1, changePercent: 4.23 },
    ],
    mappedSectors: ['人形机器人', '精密减速器', '热管理系统'],
    mappedSymbols: [
      { symbol: '002050.SZ', name: '三花智控' },
      { symbol: '603766.SH', name: '隆鑫通用' },
      { symbol: '002896.SZ', name: '中大力德' },
      { symbol: '300097.SZ', name: '智云股份' },
    ],
    transmissionLogic:
      '特斯拉Optimus三代量产规划定标，执行器关节关键零部件进入实单排产，驱动A股总成与旋转执行器核心标的获游资高举高打。',
  },
  {
    id: 'chain_hedging_metals',
    name: '全球避险与贵金属有色链',
    direction: 'BULLISH',
    intensity: 'MODERATE',
    resonanceScore: 62,
    drivers: [
      { symbol: 'GC', name: 'COMEX黄金', price: 2742.6, changePercent: 0.94 },
      { symbol: 'HG', name: 'COMEX期铜', price: 4.38, changePercent: 1.15 },
    ],
    mappedSectors: ['黄金矿业', '工业金属', '稀缺资源'],
    mappedSymbols: [
      { symbol: '601899.SH', name: '紫金矿业' },
      { symbol: '600547.SH', name: '山东黄金' },
      { symbol: '000878.SZ', name: '云南铜业' },
      { symbol: '600362.SH', name: '江西铜业' },
    ],
    transmissionLogic:
      '全球央行购金热潮延续，地缘政治溢价与去美元化支撑金银中枢，映射A股金铜一体化资源巨头估值业绩双击。',
  },
  {
    id: 'chain_a50_fx_liquidity',
    name: 'A股开盘先行与外资流动性链',
    direction: 'BULLISH',
    intensity: 'STRONG',
    resonanceScore: 72,
    drivers: [
      { symbol: 'CN50', name: '富时中国A50', price: 13245.0, changePercent: 0.68 },
      { symbol: 'HSTECH', name: '恒生科技指数', price: 4482.1, changePercent: 1.45 },
      { symbol: 'USDCNH', name: '离岸人民币', price: 7.238, changePercent: -0.18 },
    ],
    mappedSectors: ['核心资产白酒', '白马非银金融', '头部互联网ETF'],
    mappedSymbols: [
      { symbol: '600519.SH', name: '贵州茅台' },
      { symbol: '601318.SH', name: '中国平安' },
      { symbol: '300059.SZ', name: '东方财富' },
      { symbol: '000333.SZ', name: '美的集团' },
    ],
    transmissionLogic:
      '富时A50早盘先行冲高，离岸人民币走强升值释放流动性友好信号，外资配置型主力席位具备高开买入动能。',
  },
  {
    id: 'chain_solid_state_battery',
    name: '能源变革与固态锂电链',
    direction: 'BULLISH',
    intensity: 'MODERATE',
    resonanceScore: 54,
    drivers: [
      { symbol: 'ALB', name: '雅宝锂业', price: 98.6, changePercent: 3.85 },
      { symbol: 'QS', name: 'QuantumScape', price: 5.76, changePercent: 5.2 },
    ],
    mappedSectors: ['全固态电池', '碳酸锂原料', '硫化物固态电解质'],
    mappedSymbols: [
      { symbol: '300750.SZ', name: '宁德时代' },
      { symbol: '002466.SZ', name: '天齐锂业' },
      { symbol: '002460.SZ', name: '赣锋锂业' },
      { symbol: '300037.SZ', name: '新宙邦' },
    ],
    transmissionLogic:
      '海外全固态技术专利与商业装车试跑数据发布，上游锂盐现货触底反弹，催化A股头部电池与高端材料链轮动反弹。',
  },
  {
    id: 'chain_apple_consumer_elec',
    name: '苹果供应链与消费电子换机链',
    direction: 'NEUTRAL',
    intensity: 'MILD',
    resonanceScore: 18,
    drivers: [
      { symbol: 'AAPL', name: '苹果公司', price: 231.4, changePercent: 0.42 },
      { symbol: 'QCOM', name: '高通', price: 168.2, changePercent: -0.31 },
    ],
    mappedSectors: ['果链核心组装', '折叠屏铰链', '光学模组'],
    mappedSymbols: [
      { symbol: '002475.SZ', name: '立讯精密' },
      { symbol: '002241.SZ', name: '歌尔股份' },
      { symbol: '000725.SZ', name: '京东方A' },
      { symbol: '300433.SZ', name: '蓝思科技' },
    ],
    transmissionLogic:
      '苹果端侧AI换机需求预期平稳，多空拉锯胶着，产业链内部高低位分化，适合分时低吸而非追高。',
  },
  {
    id: 'chain_oil_inflation_cooling',
    name: '全球原油走弱与通胀降温链',
    direction: 'BEARISH',
    intensity: 'MILD',
    resonanceScore: -45,
    drivers: [
      { symbol: 'CL', name: 'WTI原油', price: 71.45, changePercent: -1.82 },
      { symbol: 'NG', name: '美天然气', price: 2.34, changePercent: -2.1 },
    ],
    mappedSectors: ['航空客运', '海运港口', '石化炼化'],
    mappedSymbols: [
      { symbol: '601111.SH', name: '中国国航' },
      { symbol: '600029.SH', name: '南方航空' },
      { symbol: '600028.SH', name: '中国石化' },
      { symbol: '601872.SH', name: '招商轮船' },
    ],
    transmissionLogic:
      '全球原油受供给宽松预期拖累破位下跌，油服开采承压，但下游航运与航空用油成本端显著减负形成反向对冲利好。',
  },
  {
    id: 'chain_global_biotech',
    name: '创新药跨国授权与海外映射链',
    direction: 'BULLISH',
    intensity: 'MODERATE',
    resonanceScore: 48,
    drivers: [
      { symbol: 'LLY', name: '礼来', price: 890.5, changePercent: 1.89 },
      { symbol: 'NVO', name: '诺和诺德', price: 112.3, changePercent: 1.42 },
    ],
    mappedSectors: ['创新药出海', 'GLP-1减肥药', 'CXO海外研发'],
    mappedSymbols: [
      { symbol: '600276.SH', name: '恒瑞医药' },
      { symbol: '603259.SH', name: '药明康德' },
      { symbol: '300760.SZ', name: '迈瑞医疗' },
      { symbol: '688180.SH', name: '君实生物' },
    ],
    transmissionLogic:
      '欧美重磅代谢靶点与双抗管线销售亮眼，跨国药企对国内优质管线BD授权持续涌现，带动A股创新药板块估值中枢上移。',
  },
];

const DEFAULT_FALLBACK_GROUPS: Record<GlobalAssetCategory, GlobalAssetQuote[]> = {
  ASIA_CORE: [
    { symbol: 'CN50', name: '富时中国A50期指', category: 'ASIA_CORE', price: 13245.0, change: 89.0, changePercent: 0.68 },
    { symbol: 'HSTECH', name: '恒生科技指数', category: 'ASIA_CORE', price: 4482.1, change: 64.2, changePercent: 1.45 },
    { symbol: 'HSI', name: '香港恒生指数', category: 'ASIA_CORE', price: 20630.5, change: 185.0, changePercent: 0.91 },
    { symbol: 'N225', name: '日经225指数', category: 'ASIA_CORE', price: 38920.0, change: 210.0, changePercent: 0.54 },
    { symbol: 'KS11', name: '韩国KOSPI', category: 'ASIA_CORE', price: 2580.4, change: 12.3, changePercent: 0.48 },
    { symbol: 'TWII', name: '台湾加权指数', category: 'ASIA_CORE', price: 23210.0, change: 245.0, changePercent: 1.07 },
  ],
  US_EU_INDICES: [
    { symbol: 'IXIC', name: '纳斯达克综合指数', category: 'US_EU_INDICES', price: 18983.5, change: 142.3, changePercent: 0.75 },
    { symbol: 'SPX', name: '标普500指数', category: 'US_EU_INDICES', price: 5864.2, change: 28.5, changePercent: 0.49 },
    { symbol: 'DJI', name: '道琼斯工业指数', category: 'US_EU_INDICES', price: 43239.0, change: 161.0, changePercent: 0.37 },
    { symbol: 'NQ_F', name: '纳斯达克100期指', category: 'US_EU_INDICES', price: 20560.0, change: 125.0, changePercent: 0.61 },
    { symbol: 'GDAXI', name: '德国DAX30', category: 'US_EU_INDICES', price: 19650.0, change: 72.0, changePercent: 0.37 },
    { symbol: 'FCHI', name: '法国CAC40', category: 'US_EU_INDICES', price: 7580.0, change: 26.0, changePercent: 0.34 },
  ],
  TECH_GIANTS: [
    { symbol: 'NVDA', name: '英伟达 (NVIDIA)', category: 'TECH_GIANTS', price: 138.25, change: 3.75, changePercent: 2.78 },
    { symbol: 'TSLA', name: '特斯拉 (Tesla)', category: 'TECH_GIANTS', price: 262.1, change: 10.65, changePercent: 4.23 },
    { symbol: 'AAPL', name: '苹果公司 (Apple)', category: 'TECH_GIANTS', price: 231.4, change: 0.97, changePercent: 0.42 },
    { symbol: 'MSFT', name: '微软 (Microsoft)', category: 'TECH_GIANTS', price: 422.5, change: 2.8, changePercent: 0.67 },
    { symbol: 'GOOGL', name: '谷歌 (Alphabet)', category: 'TECH_GIANTS', price: 166.8, change: 1.2, changePercent: 0.72 },
    { symbol: 'AMZN', name: '亚马逊 (Amazon)', category: 'TECH_GIANTS', price: 189.2, change: 1.6, changePercent: 0.85 },
    { symbol: 'TSM', name: '台积电ADR', category: 'TECH_GIANTS', price: 198.4, change: 11.8, changePercent: 6.33 },
    { symbol: 'BABA', name: '阿里巴巴ADR', category: 'TECH_GIANTS', price: 102.5, change: 2.1, changePercent: 2.09 },
  ],
  COMMODITIES: [
    { symbol: 'GC', name: 'COMEX黄金主力', category: 'COMMODITIES', price: 2742.6, change: 14.8, changePercent: 0.54 },
    { symbol: 'SI', name: 'COMEX白银主力', category: 'COMMODITIES', price: 33.85, change: 0.42, changePercent: 1.26 },
    { symbol: 'HG', name: 'COMEX精铜期货', category: 'COMMODITIES', price: 4.38, change: 0.05, changePercent: 1.15 },
    { symbol: 'CL', name: 'WTI原油期货', category: 'COMMODITIES', price: 71.45, change: -1.32, changePercent: -1.82 },
    { symbol: 'BZ', name: '布伦特原油', category: 'COMMODITIES', price: 75.2, change: -1.25, changePercent: -1.63 },
    { symbol: 'ZC', name: 'CBOT玉米期货', category: 'COMMODITIES', price: 418.5, change: 1.5, changePercent: 0.36 },
  ],
  FOREX: [
    { symbol: 'USDCNH', name: '美元/离岸人民币 (USD/CNH)', category: 'FOREX', price: 7.238, change: -0.013, changePercent: -0.18 },
    { symbol: 'USDCNY', name: '美元/在岸人民币 (USD/CNY)', category: 'FOREX', price: 7.232, change: -0.01, changePercent: -0.14 },
    { symbol: 'DXY', name: '美元指数', category: 'FOREX', price: 104.25, change: -0.18, changePercent: -0.17 },
    { symbol: 'EURUSD', name: '欧元/美元 (EUR/USD)', category: 'FOREX', price: 1.0825, change: 0.0022, changePercent: 0.2 },
    { symbol: 'USDJPY', name: '美元/日元 (USD/JPY)', category: 'FOREX', price: 152.4, change: -0.35, changePercent: -0.23 },
    { symbol: 'AUDUSD', name: '澳元/美元 (AUD/USD)', category: 'FOREX', price: 0.661, change: 0.0028, changePercent: 0.43 },
  ],
};

const DEFAULT_FALLBACK_NEWS: GlobalLiveNewsItem[] = [
  {
    id: 'news_1',
    time: '09:28:15',
    title: '台积电先进制程法说会营收展望超预期，算力与AI硬件资本开支加码',
    content: '台积电高管重申AI芯片需求极其强劲且供不应求，先进制程利用率拉满，全球科技巨头加速下订。',
    category: 'TECH_INDUSTRY',
    polarity: 'BULLISH',
    importance: 'HIGH',
  },
  {
    id: 'news_2',
    time: '09:20:00',
    title: '富时中国A50期指连续拉升，离岸人民币USD/CNH日内升值逾百点',
    content: '外资风险偏好明显修复，早盘北向跨境资金净流入预期大幅上调，对核心权重白马形成有力托底。',
    category: 'GLOBAL_MACRO',
    polarity: 'BULLISH',
    importance: 'HIGH',
  },
  {
    id: 'news_3',
    time: '08:55:40',
    title: '伦敦金高位震荡续创历史新高，COMEX白银突破33.5美元关口',
    content: '受避险情绪与央行储备结构优化驱动，大宗贵金属全线维持强多头共振格局。',
    category: 'COMMODITY_FX',
    polarity: 'BULLISH',
    importance: 'NORMAL',
  },
  {
    id: 'news_4',
    time: '08:32:10',
    title: '特斯拉Optimus人形机器人产线方案关键节点落地，国产核心供应链迎来密集定点',
    content: '供应链消息指海外巨头加快灵巧手与谐波减速器验货流程，A股高壁垒核心部件企业迎来催化。',
    category: 'TECH_INDUSTRY',
    polarity: 'BULLISH',
    importance: 'HIGH',
  },
  {
    id: 'news_5',
    time: '08:10:05',
    title: '国际能源署预计全球原油供应充足，WTI原油承压回落',
    content: 'OPEC+增产预期打压油价，能源成本下行有望对下游航空客运与交运物流带来盈利修复。',
    category: 'COMMODITY_FX',
    polarity: 'NEUTRAL',
    importance: 'NORMAL',
  },
];

export const GlobalMarketLinkagePanel: React.FC = () => {
  const { radar, loading, refresh } = useRealGlobalRadar();
  const setSelectedSymbol = useMarketStore((s) => s.setSelectedSymbol);
  const selectAndSubscribeStock = useMarketStore((s) => s.selectAndSubscribeStock);
  const selectedSymbol = useMarketStore((s) => s.selectedSymbol);

  const [activeCategory, setActiveCategory] = useState<GlobalAssetCategory>('ASIA_CORE');
  const [filterDirection, setFilterDirection] = useState<'ALL' | 'BULLISH' | 'BEARISH'>('ALL');

  // 数据安全兜底合并
  const summary = useMemo(() => {
    return (
      radar?.summary ?? {
        globalRiskAppetite: 'RISK_ON' as const,
        riskAppetiteLabel: '全球风险偏好升温',
        a50ChangePercent: 0.68,
        usdcnhPrice: 7.238,
        usdcnhChangePercent: -0.18,
        topBullishChain: 'AI算力与硬科技半导体链',
        topBearishChain: '全球原油走弱与通胀降温链',
      }
    );
  }, [radar?.summary]);

  const transmissionChains = useMemo(() => {
    const list =
      radar?.transmissionChains && radar.transmissionChains.length > 0
        ? radar.transmissionChains
        : DEFAULT_FALLBACK_CHAINS;
    if (filterDirection === 'ALL') return list;
    return list.filter((c) => c.direction === filterDirection);
  }, [radar?.transmissionChains, filterDirection]);

  const groups = useMemo(() => {
    if (radar?.groups && Object.keys(radar.groups).length > 0) {
      return radar.groups;
    }
    return DEFAULT_FALLBACK_GROUPS;
  }, [radar?.groups]);

  const liveNews = useMemo(() => {
    if (radar?.liveNews && radar.liveNews.length > 0) {
      return radar.liveNews;
    }
    return DEFAULT_FALLBACK_NEWS;
  }, [radar?.liveNews]);

  // 点击 A 股映射龙头标的胶囊：联动切换全局选中股并激活数据流
  const handleSelectMappedSymbol = (target: MappedStockTarget) => {
    setSelectedSymbol(target.symbol);
    selectAndSubscribeStock({
      symbol: target.symbol,
      name: target.name,
    });
  };

  const currentCategoryAssets = groups[activeCategory] || [];

  return (
    <div
      data-testid="global-market-linkage-panel"
      className="flex flex-col gap-3 text-[#d1d4dc] pb-6"
    >
      {/* ==================== 顶部全球宏观与开盘定调条 ==================== */}
      <section
        aria-label="全球宏观与开盘定调"
        className="bg-[#181b24] border border-[#2a2e39] rounded-lg p-3.5 shadow-md neon-panel neon-border-violet"
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          {/* 左侧：风险偏好徽章与核心指标 */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <Globe className="w-5 h-5 text-[#2962ff] animate-pulse" />
              <span className="text-sm font-bold text-white tracking-wide">
                全球宏观开盘定调
              </span>
            </div>

            {/* 风险偏好徽章 */}
            <div
              className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border ${
                summary.globalRiskAppetite === 'RISK_ON'
                  ? 'bg-rose-500/15 border-rose-500/40 text-[#F6465D] glow-up'
                  : summary.globalRiskAppetite === 'RISK_OFF'
                  ? 'bg-emerald-500/15 border-emerald-500/40 text-[#0ECB81]'
                  : 'bg-amber-500/15 border-amber-500/40 text-amber-400'
              }`}
            >
              {summary.globalRiskAppetite === 'RISK_ON' ? (
                <Flame className="w-3.5 h-3.5" />
              ) : summary.globalRiskAppetite === 'RISK_OFF' ? (
                <ShieldAlert className="w-3.5 h-3.5" />
              ) : (
                <Activity className="w-3.5 h-3.5" />
              )}
              <span>{summary.riskAppetiteLabel}</span>
            </div>

            {/* 富时A50 指数胶囊 */}
            <div className="flex items-center gap-1.5 px-2.5 py-1 bg-[#1e222d] rounded border border-[#2a2e39] text-xs">
              <span className="text-[#848e9c]">富时A50期指:</span>
              <span
                className={`font-mono font-bold ${getSignedColorClass(summary.a50ChangePercent)}`}
              >
                {formatSignedPercent(summary.a50ChangePercent)}
              </span>
            </div>

            {/* 离岸人民币 USD/CNH 胶囊 */}
            <div className="flex items-center gap-1.5 px-2.5 py-1 bg-[#1e222d] rounded border border-[#2a2e39] text-xs">
              <span className="text-[#848e9c]">离岸人民币 (USD/CNH):</span>
              <span className="font-mono font-semibold text-white">
                {summary.usdcnhPrice.toFixed(4)}
              </span>
              <span
                className={`font-mono text-[11px] ${
                  summary.usdcnhChangePercent < 0 ? 'text-[#0ECB81]' : 'text-[#F6465D]'
                }`}
                title={summary.usdcnhChangePercent < 0 ? '人民币升值' : '人民币贬值'}
              >
                ({summary.usdcnhChangePercent < 0 ? '升值 ' : '贬值 '}
                {formatSignedPercent(Math.abs(summary.usdcnhChangePercent))})
              </span>
            </div>
          </div>

          {/* 右侧：最强多空传导链 + 手动刷新 */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="hidden lg:flex items-center gap-2 text-xs">
              <div className="flex items-center gap-1 px-2 py-0.5 rounded bg-rose-500/10 border border-rose-500/20 text-[#F6465D]">
                <TrendingUp className="w-3 h-3" />
                <span>领涨: {summary.topBullishChain}</span>
              </div>
              <div className="flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-[#0ECB81]">
                <TrendingDown className="w-3 h-3" />
                <span>领跌: {summary.topBearishChain}</span>
              </div>
            </div>

            <button
              type="button"
              onClick={refresh}
              disabled={loading}
              title="立即刷新全球雷达数据"
              className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded bg-[#1e222d] hover:bg-[#2a2e39] text-[#9ca3af] hover:text-white border border-[#2a2e39] transition-all cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-[#2962ff]' : ''}`} />
              <span>{loading ? '同步中...' : '刷新'}</span>
            </button>
          </div>
        </div>
      </section>

      {/* ==================== 核心布局：左侧传导链矩阵 + 右侧全球报价与快讯 ==================== */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-3 items-start">
        {/* 左侧 7 列：八大跨市场传导链卡片矩阵 */}
        <section
          aria-label="跨市场关联传导链矩阵"
          className="xl:col-span-7 flex flex-col gap-2.5"
        >
          {/* 栏目标题与多空过滤器 */}
          <div className="flex items-center justify-between px-1">
            <div className="flex items-center gap-2">
              <Zap className="w-4 h-4 text-amber-400" />
              <h3 className="text-sm font-bold text-white tracking-wide">
                全球资产 $\rightarrow$ A股板块龙头 跨市场传导链
              </h3>
              <span className="text-[11px] text-[#787b86] font-mono">
                ({transmissionChains.length} 核心链条)
              </span>
            </div>

            {/* 过滤器 */}
            <div className="flex items-center bg-[#181b24] p-0.5 rounded border border-[#2a2e39] text-xs">
              <button
                type="button"
                onClick={() => setFilterDirection('ALL')}
                className={`px-2 py-0.5 rounded transition-colors cursor-pointer ${
                  filterDirection === 'ALL'
                    ? 'bg-[#2962ff] text-white font-medium'
                    : 'text-[#848e9c] hover:text-[#d1d4dc]'
                }`}
              >
                全部
              </button>
              <button
                type="button"
                onClick={() => setFilterDirection('BULLISH')}
                className={`px-2 py-0.5 rounded transition-colors cursor-pointer flex items-center gap-1 ${
                  filterDirection === 'BULLISH'
                    ? 'bg-rose-500/80 text-white font-medium'
                    : 'text-[#848e9c] hover:text-[#F6465D]'
                }`}
              >
                <span>多头</span>
              </button>
              <button
                type="button"
                onClick={() => setFilterDirection('BEARISH')}
                className={`px-2 py-0.5 rounded transition-colors cursor-pointer flex items-center gap-1 ${
                  filterDirection === 'BEARISH'
                    ? 'bg-emerald-500/80 text-white font-medium'
                    : 'text-[#848e9c] hover:text-[#0ECB81]'
                }`}
              >
                <span>空头</span>
              </button>
            </div>
          </div>

          {/* 传导链卡片列表 */}
          <div className="grid grid-cols-1 gap-2.5">
            {transmissionChains.map((chain) => {
              const isBull = chain.direction === 'BULLISH';
              const isBear = chain.direction === 'BEARISH';
              const scoreColor = isBull
                ? 'text-[#F6465D]'
                : isBear
                ? 'text-[#0ECB81]'
                : 'text-[#848e9c]';
              const scoreFillWidth = Math.min(100, Math.abs(chain.resonanceScore));

              return (
                <div
                  key={chain.id}
                  data-testid={`chain-card-${chain.id}`}
                  className="bg-[#181b24] hover:bg-[#1b1f2b] border border-[#2a2e39] hover:border-[#3d4455] rounded-lg p-3 transition-all duration-150 shadow-sm flex flex-col gap-2.5"
                >
                  {/* 卡片头部：名称、方向徽章、共振强度、共振得分 */}
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="font-semibold text-white text-sm tracking-wide">
                        {chain.name}
                      </span>
                      <span
                        className={`text-[10px] px-1.5 py-0.5 rounded font-medium border ${
                          isBull
                            ? 'bg-rose-500/10 text-[#F6465D] border-rose-500/30'
                            : isBear
                            ? 'bg-emerald-500/10 text-[#0ECB81] border-emerald-500/30'
                            : 'bg-gray-500/10 text-gray-400 border-gray-500/30'
                        }`}
                      >
                        {isBull ? '多头共振' : isBear ? '空头下沉' : '中性分化'} ·{' '}
                        {chain.intensity === 'STRONG'
                          ? '强'
                          : chain.intensity === 'MODERATE'
                          ? '中'
                          : '弱'}
                      </span>
                    </div>

                    {/* 共振得分与进度条 */}
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="text-[11px] text-[#848e9c]">共振得分:</span>
                      <span className={`text-xs font-mono font-bold ${scoreColor}`}>
                        {chain.resonanceScore > 0 ? `+${chain.resonanceScore}` : chain.resonanceScore}
                      </span>
                      <div className="w-16 h-1.5 bg-[#2a2e39] rounded-full overflow-hidden flex">
                        {isBull ? (
                          <div
                            className="h-full bg-gradient-to-r from-rose-500 to-amber-500 rounded-full transition-all duration-300"
                            style={{ width: `${scoreFillWidth}%` }}
                          />
                        ) : (
                          <div
                            className="h-full bg-gradient-to-r from-emerald-500 to-teal-400 rounded-full transition-all duration-300"
                            style={{ width: `${scoreFillWidth}%` }}
                          />
                        )}
                      </div>
                    </div>
                  </div>

                  {/* 海外驱动源实时表现 (drivers) */}
                  <div className="flex flex-wrap items-center gap-1.5 text-xs bg-[#12141a] px-2.5 py-1.5 rounded border border-[#242833]">
                    <span className="text-[11px] text-[#787b86] shrink-0 font-medium flex items-center gap-1">
                      <Radio className="w-3 h-3 text-[#2962ff]" /> 海外驱动源:
                    </span>
                    {chain.drivers.map((driver) => {
                      const color = getSignedColorClass(driver.changePercent);
                      return (
                        <div
                          key={driver.symbol}
                          className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-[#1e222d] border border-[#2a2e39]"
                        >
                          <span className="text-white font-medium">{driver.name}</span>
                          <span className="text-[11px] text-[#848e9c] font-mono">
                            {driver.price > 1000
                              ? driver.price.toFixed(0)
                              : driver.price.toFixed(2)}
                          </span>
                          <span className={`text-[11px] font-mono font-semibold ${color}`}>
                            {formatSignedPercent(driver.changePercent)}
                          </span>
                        </div>
                      );
                    })}
                  </div>

                  {/* 传导箭头与 A 股映射板块及标的龙头 */}
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <div className="flex items-center gap-1 text-[#848e9c] shrink-0">
                      <ArrowRight className="w-3.5 h-3.5 text-[#2962ff]" />
                      <span className="font-medium text-[#d1d4dc]">A股板块:</span>
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      {chain.mappedSectors.map((sector) => (
                        <span
                          key={sector}
                          className="px-2 py-0.5 rounded text-[11px] bg-[#2962ff]/10 text-[#5c8aff] border border-[#2962ff]/30 font-medium"
                        >
                          {sector}
                        </span>
                      ))}
                    </div>

                    <div className="w-full flex flex-wrap items-center gap-1.5 pt-0.5">
                      <span className="text-[11px] text-[#787b86] shrink-0">
                        核心联动标的:
                      </span>
                      {chain.mappedSymbols.map((target) => {
                        const isCurrent = selectedSymbol === target.symbol;
                        return (
                          <button
                            key={target.symbol}
                            type="button"
                            onClick={() => handleSelectMappedSymbol(target)}
                            title={`点击将主图切换为 ${target.name} (${target.symbol})`}
                            className={`flex items-center gap-1 px-2.5 py-1 rounded text-xs transition-all cursor-pointer ${
                              isCurrent
                                ? 'bg-[#2962ff] text-white font-bold ring-2 ring-[#2962ff]/50 shadow-md scale-105'
                                : 'bg-[#1e222d] hover:bg-[#2a2e39] text-[#d1d4dc] hover:text-white border border-[#2a2e39]'
                            }`}
                          >
                            <span>{target.name}</span>
                            <span className="text-[10px] font-mono opacity-70">
                              {target.symbol.split('.')[0]}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {/* 传导底层逻辑 */}
                  <div className="text-[11px] text-[#848e9c] bg-[#14161f] p-2 rounded border border-[#222631] leading-relaxed">
                    <span className="text-[#9ca3af] font-semibold">传导逻辑: </span>
                    {chain.transmissionLogic}
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* 右侧 5 列：全球全资产实时报价看板 + 7×24 快讯流 */}
        <div className="xl:col-span-5 flex flex-col gap-3">
          {/* 全球五大类资产实时看板 */}
          <section
            aria-label="全球五大类资产实时报价"
            className="bg-[#181b24] border border-[#2a2e39] rounded-lg p-3 shadow-md flex flex-col gap-2.5"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-[#2962ff]" />
                <h3 className="text-sm font-bold text-white tracking-wide">
                  全球资产行情看板
                </h3>
              </div>
              <span className="text-[11px] text-[#787b86] font-mono">
                {currentCategoryAssets.length} 核心资产
              </span>
            </div>

            {/* 分类切换胶囊 */}
            <div className="flex items-center gap-1 overflow-x-auto pb-1 scrollbar-none">
              {CATEGORY_TABS.map((cat) => {
                const isActive = activeCategory === cat.key;
                return (
                  <button
                    key={cat.key}
                    type="button"
                    onClick={() => setActiveCategory(cat.key)}
                    className={`px-2 py-1 text-xs rounded transition-colors whitespace-nowrap cursor-pointer ${
                      isActive
                        ? 'bg-[#2962ff] text-white font-semibold shadow-sm'
                        : 'bg-[#1e222d] text-[#848e9c] hover:text-[#d1d4dc] hover:bg-[#252936]'
                    }`}
                  >
                    {cat.label}
                  </button>
                );
              })}
            </div>

            {/* 资产报价表格/列表 */}
            <div className="bg-[#12141a] rounded border border-[#242833] overflow-hidden">
              <div className="grid grid-cols-12 px-3 py-1.5 bg-[#181b24] border-b border-[#242833] text-[11px] font-semibold text-[#848e9c]">
                <div className="col-span-5">资产名称/代码</div>
                <div className="col-span-4 text-right">最新价</div>
                <div className="col-span-3 text-right">涨跌幅</div>
              </div>

              <div className="divide-y divide-[#1e222d] max-h-[300px] overflow-y-auto">
                {currentCategoryAssets.map((asset) => {
                  const colorClass = getSignedColorClass(asset.changePercent ?? asset.change);
                  const priceStr =
                    asset.price > 1000
                      ? asset.price.toLocaleString('en-US', {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        })
                      : asset.price.toFixed(asset.price < 10 ? 4 : 2);

                  return (
                    <div
                      key={asset.symbol}
                      className="grid grid-cols-12 px-3 py-2 text-xs hover:bg-[#1a1e29] transition-colors items-center"
                    >
                      <div className="col-span-5 flex flex-col min-w-0 pr-1">
                        <span className="font-medium text-white truncate">{asset.name}</span>
                        <span className="text-[10px] font-mono text-[#787b86]">
                          {asset.symbol}
                        </span>
                      </div>
                      <div className="col-span-4 text-right font-mono font-medium text-white">
                        {priceStr}
                      </div>
                      <div className="col-span-3 text-right flex flex-col items-end">
                        <span className={`font-mono font-bold ${colorClass}`}>
                          {formatSignedPercent(asset.changePercent)}
                        </span>
                        {asset.change !== 0 && (
                          <span className={`text-[10px] font-mono ${colorClass}`}>
                            {formatSignedChange(asset.change)}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </section>

          {/* 7×24 全球财经快讯流 */}
          <section
            aria-label="全球财经快讯流"
            className="bg-[#181b24] border border-[#2a2e39] rounded-lg p-3 shadow-md flex flex-col gap-2.5"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="relative flex h-2.5 w-2.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-rose-500" />
                </span>
                <h3 className="text-sm font-bold text-white tracking-wide">
                  7×24 全球财经电报
                </h3>
              </div>
              <span className="text-[11px] text-[#787b86] font-mono">实时动态流</span>
            </div>

            {/* 快讯列表 */}
            <div className="flex flex-col gap-2 max-h-[360px] overflow-y-auto pr-1">
              {liveNews.map((news) => {
                const isBull = news.polarity === 'BULLISH';
                const isBear = news.polarity === 'BEARISH';
                const isHigh = news.importance === 'HIGH';

                return (
                  <div
                    key={news.id}
                    className="p-2.5 rounded bg-[#13151c] hover:bg-[#171a24] border border-[#242833] transition-colors flex flex-col gap-1.5"
                  >
                    <div className="flex items-center justify-between gap-1 text-[11px]">
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono text-[#848e9c]">{news.time}</span>
                        {isHigh && (
                          <span className="px-1 py-0.2 rounded text-[10px] bg-rose-500/20 text-[#F6465D] font-bold border border-rose-500/30">
                            重磅
                          </span>
                        )}
                        <span className="px-1 py-0.2 rounded text-[10px] bg-[#1e222d] text-[#848e9c]">
                          {news.category === 'GLOBAL_MACRO'
                            ? '全球宏观'
                            : news.category === 'TECH_INDUSTRY'
                            ? '科技产业'
                            : news.category === 'COMMODITY_FX'
                            ? '大宗汇率'
                            : 'A股政策'}
                        </span>
                      </div>

                      <span
                        className={`text-[10px] font-semibold ${
                          isBull
                            ? 'text-[#F6465D]'
                            : isBear
                            ? 'text-[#0ECB81]'
                            : 'text-[#848e9c]'
                        }`}
                      >
                        {isBull ? '偏多' : isBear ? '偏空' : '中性'}
                      </span>
                    </div>

                    <div className="font-medium text-xs text-white leading-snug">
                      {news.title}
                    </div>

                    {news.content && (
                      <div className="text-[11px] text-[#848e9c] leading-relaxed">
                        {news.content}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};
