/**
 * 股票看盘平台核心类型定义 (Strictly Level-1 Market Data Specification)
 * 严禁包含任何 Level-2 专有结构（如 10 档盘口、千档队列、逐笔委托还原等）
 */

export type TradingPhase = 'TRADING' | 'CALL_AUCTION' | 'LIMIT_UP' | 'LIMIT_DOWN' | 'CLOSED';

export type PriceDirection = 'UP' | 'DOWN' | 'FLAT';

/**
 * 单档盘口挂单结构
 * 当处于涨跌停封板或集合竞价无挂单时，price 和 volume 允许为 null，UI 优雅降级为 '--'
 */
export interface OrderBookLevel {
  level: 1 | 2 | 3 | 4 | 5;
  price: number | null;
  volume: number | null; // 单位：手 (1手 = 100股)
}

/**
 * 标准 Level-1 五档盘口数据结构 (OrderBook5)
 * 买盘：买一至买五 (bids[0] ~ bids[4])
 * 卖盘：卖一至卖五 (asks[0] ~ asks[4]，UI 渲染时由卖五至卖一从高到低排列)
 */
export interface OrderBook5 {
  bids: [OrderBookLevel, OrderBookLevel, OrderBookLevel, OrderBookLevel, OrderBookLevel];
  asks: [OrderBookLevel, OrderBookLevel, OrderBookLevel, OrderBookLevel, OrderBookLevel];
}

/**
 * 渲染用的单档盘口视图模型（包含相对深度百分比与格式化文本）
 */
export interface FormattedOrderBookRow {
  side: 'ask' | 'bid';
  level: 1 | 2 | 3 | 4 | 5;
  label: string; // 如 '卖五', '卖一', '买一', '买五'
  rawPrice: number | null;
  rawVolume: number | null;
  priceText: string; // 无数据时为 '--'
  volumeText: string; // 无数据时为 '--'
  depthPercent: number; // 0 ~ 100，用于绘制半透明 Volume Depth Bar
  priceDirection: PriceDirection;
}

/**
 * 基于五档盘口实时计算的衍生指标：【委差】与【委比】
 */
export interface OrderBookMetrics {
  totalBidVolume: number; // 买一至买五总挂单手数
  totalAskVolume: number; // 卖一至卖五总挂单手数
  imbalanceVolume: number | null; // 委差 = TotalBid - TotalAsk
  imbalanceRatio: number | null; // 委比 = ((TotalBid - TotalAsk) / (TotalBid + TotalAsk)) * 100%
  imbalanceVolumeText: string; // 格式化委差（如 '+1,240' 或 '--'）
  imbalanceRatioText: string; // 格式化委比（如 '+34.52%' 或 '--'）
  bidPowerPercent: number; // 买盘力量占比 (0 ~ 100)，用于委比红绿进度条
  asksTopToBottom: FormattedOrderBookRow[]; // 卖五 -> 卖一（由高到低排列）
  bidsTopToBottom: FormattedOrderBookRow[]; // 买一 -> 买五（由高到低排列）
}

/**
 * Level-1 实时分笔成交简表项 (非 L2 逐笔还原，仅为 L1 快照切片成交明细)
 */
export interface TradeTick {
  id: string;
  time: string; // HH:mm:ss
  price: number;
  volume: number; // 成交手数
  side: 'BUY' | 'SELL' | 'NEUTRAL'; // B (外盘主动买) / S (内盘主动卖) / - (中性盘)
}

/**
 * Level-1 实时单只股票快照数据 (TickData)
 */
export interface TickData {
  symbol: string; // 如 '600519.SH'
  code: string; // 如 '600519'
  market: 'SH' | 'SZ';
  name: string; // 如 '贵州茅台'
  pinyin: string; // 拼音首字母，如 'gzmt'，用于左侧自选股快速检索
  sector: string; // 所属板块，如 '酿酒行业'
  price: number; // 最新价
  prevClose: number; // 昨收价
  open: number; // 今开价
  high: number; // 最高价
  low: number; // 最低价
  change: number; // 涨跌额
  changePercent: number; // 涨跌幅 (%)
  volume: number; // 总成交量（手）
  amount: number; // 总成交额（元）
  turnoverRate: number; // 换手率 (%)
  volumeRatio: number; // 量比
  amplitude: number; // 振幅 (%)
  peTtm: number; // 市盈率 (TTM)
  pb: number; // 市净率
  marketCap: number; // 总市值（亿元）
  floatMarketCap: number; // 流通市值（亿元）
  outerVolume: number; // 外盘（主动买，手）
  innerVolume: number; // 内盘（主动卖，手）
  limitUpPrice: number; // 涨停价
  limitDownPrice: number; // 跌停价
  phase: TradingPhase; // 当前交易状态（正常、涨停封板、跌停封板、集合竞价）
  orderBook: OrderBook5; // 五档盘口
  recentTrades: TradeTick[]; // 最近分笔成交明细
  ultraShort?: UltraShortProfile; // 超短游资量化扩展数据（09:25竞价、连板身位、法定异动逆推基准）
  updatedAt: number; // 时间戳 (ms)
}

/**
 * K 线标准柱状数据 (KLineBar)
 */
export interface KLineBar {
  time: string; // 日期 'YYYY-MM-DD' 或分钟时间 'YYYY-MM-DD HH:mm'
  timestamp: number; // 秒级时间戳
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number; // 成交手数
  amount: number; // 成交金额
  turnoverRate?: number;
}

/**
 * 分时图单点结构 (IntradayPoint)
 */
export interface IntradayPoint {
  time: string; // '09:30' ~ '15:00'
  timestamp: number;
  price: number;
  avgPrice: number; // 均价线 (VWAP)
  volume: number; // 当分钟成交量（手）
  changePercent: number;
}

/**
 * 核心市场指数快照（跑马灯监控）
 */
export interface MarketIndexQuote {
  symbol: string; // '000001.SH'
  name: string; // '上证指数'
  price: number;
  prevClose: number;
  change: number;
  changePercent: number;
  volume: number; // 亿手
  amount: number; // 亿元
  upCount: number; // 上涨家数
  downCount: number; // 下跌家数
  flatCount: number; // 平盘家数
}

export type ChartPeriod = 'intraday' | '5m' | '15m' | '30m' | '60m' | '1D' | '1W' | '1M';

export type MainIndicator = 'MA' | 'EMA' | 'BOLL' | 'NONE';

export type SubIndicator = 'VOL' | 'MACD' | 'KDJ' | 'RSI';

export type ConnectionStatus = 'CONNECTED' | 'CONNECTING' | 'RECONNECTING' | 'DISCONNECTED';

export type MarketScenario = 'normal' | 'limit_up' | 'limit_down' | 'call_auction';

/**
 * 一、09:25 集合竞价雷达信号定性
 */
export type AuctionSignalType =
  | 'SUPER_GRAB' // 超预期抢筹（爆量高开、弱转强）
  | 'LOCKED_LIMIT_UP' // 一字/T字巨封涨停
  | 'WEAK_TO_STRONG' // 分歧转一致弱转强
  | 'OVERHEAT_DUMP' // 竞价天量兑现预警
  | 'NUCLEAR_BUTTON' // 竞价核按钮（深水/跌停大单压盘）
  | 'NORMAL'; // 常规竞价

/**
 * 二、题材先锋与游资身位角色标签
 */
export type DragonRoleTag =
  | 'SPACE_DRAGON' // 全市场最高空间板总龙
  | 'PIONEER_DRAGON' // 板块日内最早封板点火先锋龙
  | 'CAPACITY_CORE' // 百亿成交大容量趋势中军
  | 'TURNOVER_DRAGON' // 换手卡位活口龙
  | 'FOLLOWER'; // 板块后排跟风/套利

/**
 * 个股超短游资量化扩展元数据（严格基于 L1 快照、涨停池/炸板池与日K历史计算）
 *
 * ⚠️ 字段分两类：
 *  ① 真实可算（后端 /api/market/quote 与 /api/quant/ladder 提供）：
 *     poolDate / consecutiveBoards / yesterdayBoards / firstSealTime / dragonRole /
 *     sealOrderAmount / sealRatioPct / brokenTimes / auctionPrice / auctionChangePercent 等
 *  ② 免费源拆不出来（后端不给，前端显示"—"，**不允许再写硬编码常量冒充**）：
 *     auctionVolume / auctionAmount / auctionUnmatchedHands / auctionVolumeRatio /
 *     stockReturnT1·T2 / indexReturnT1·T2 / indexReturnToday / cumDeviation10d / abnormalCount10d
 */
export interface UltraShortProfile {
  // —— 口径日：这套身位数据描述的是哪一个交易日（盘前/周末会落后于实时报价）——
  poolDate?: string; // 如 '20261023'
  prevPoolDate?: string | null;
  isCurrentSession?: boolean; // poolDate 是否就是今天
  source?: string; // 'eastmoney_pool'

  // 09:25 竞价核心原始数据（免费源只能可靠拿到开盘价，其余为估算，故可选）
  auctionPrice?: number | null; // 09:25 撮合开盘价 = 当日开盘价
  auctionChangePercent?: number | null; // 09:25 竞价涨跌幅 (%)
  auctionVolume?: number; // 竞价成交手数（后端不提供）
  auctionAmount?: number; // 竞价成交金额（后端不提供）
  yesterdayAmount?: number | null; // 昨日全天成交总额（昨日在池子里时才有）
  auctionUnmatchedHands?: number; // 竞价未匹配手数（后端不提供）
  auctionVolumeRatio?: number; // 竞价量比（后端不提供）
  yesterdayPerformanceNote?: string; // 昨日形态描述（昨炸板分歧/昨N连板/昨首板/昨未涨停）

  // 连板梯队与身位数据
  consecutiveBoards: number; // 当前连板高度（0 表示非连板，1 表示首板，>=2 表示连板高度）
  yesterdayBoards: number; // 昨日连板数（用于计算 N进N+1 晋级率）
  isIntradayTouchedLimitUp: boolean; // 今日是否曾触及涨停（用于计算封板率/炸板率）
  isSealed?: boolean; // 是否封死涨停（在涨停池内）
  firstSealTime?: string | null; // 首次封死涨停时间（如 '09:25:00'，未封板为 null）
  dragonRole: DragonRoleTag; // 身位定性
  sealOrderAmount?: number; // 封单金额（元）
  sealRatioPct?: number | null; // 封单额 / 流通市值 (%)
  brokenTimes?: number; // 当日炸板次数
  sector?: string | null;
  limitUpPrice?: number | null;
  poolChangePercent?: number | null; // 池子口径（那个交易日）的涨幅
  changePercent?: number | null; // 优先取实时报价涨幅

  // 法定复利异动监管逆推历史输入 (k ∈ {2, 3}) —— 免费源拆不出来，缺省时前端显示"—"
  boardRuleType: 'MAIN_20' | 'CHINEXT_STAR_30'; // 主板 20% 偏离阈值 vs 创业板/科创板 30% 偏离阈值
  stockReturnT1?: number; // T-1 日个股涨跌幅 (%)
  stockReturnT2?: number; // T-2 日个股涨跌幅 (%)
  indexReturnT1?: number; // T-1 日对应基准指数涨跌幅 (%)
  indexReturnT2?: number; // T-2 日对应基准指数涨跌幅 (%)
  indexReturnToday?: number; // 今日对应基准指数实时涨跌幅 (%)
  cumDeviation10d?: number; // 近 10 个交易日累计涨跌幅偏离值 (%)
  abnormalCount10d?: number; // 近 10 日已触发同向异动次数
}

/**
 * 09:25 竞价雷达单标的计算结果
 */
export interface AuctionRadarMetrics {
  symbol: string;
  code: string;
  name: string;
  sector: string;
  auctionPrice: number;
  auctionChangePercent: number;
  auctionAmount: number;
  yesterdayAmount: number;
  amountToYesterdayRatio: number; // 竞价金额占昨比 (%) = (竞价金额 / 昨全天成交额) * 100
  auctionVolumeRatio: number; // 竞价量比
  unmatchedHands: number; // 正为抢筹未匹配买单，负为核按钮未匹配卖单
  signal: AuctionSignalType;
  signalLabel: string;
  signalReason: string;
  /**
   * 金额口径：'auction' = 真正的 9:25 集合竞价成交额；
   * 'intraday' = 开盘后累计成交额（此时"占昨比"是当日成交/昨日全天，不是竞价占昨）；
   * 'pre' = 竞价还没开始。后端 /api/quant/auction_radar 提供。
   */
  amountBasis?: 'auction' | 'intraday' | 'pre';
  /** true = 该股不在后端雷达结果里，竞价额/占昨比是按"昨日成交×系数"估算出来的，不是真实竞价数据 */
  estimated?: boolean;
}

/**
 * 连板梯队单层结构与全市场晋级率汇总
 */
export interface BoardTierGroup {
  boardCount: number; // 如 6, 5, 4, 3, 2, 1
  label: string; // 如 '6连板 (空间板)', '3连板', '首板 (1板)'
  yesterdayCount: number; // 昨日 (boardCount - 1) 板基数
  todaySealedCount: number; // 今日成功晋级封板数
  promotionRate: number | null; // 晋级率 (%) = todaySealedCount / yesterdayCount * 100
  stocks: {
    symbol: string;
    code: string;
    name: string;
    sector: string;
    price: number;
    changePercent: number;
    firstSealTime: string;
    sealOrderAmount: number; // 买一封单金额 (元)
    dragonRole: DragonRoleTag;
    ultraShort?: UltraShortProfile | null; // 后端 /api/quant/ladder 直出的真实身位档案
  }[];
}

export interface LadderDistributionRow {
  boardCount: number; // 连板高度 1 ~ maxBoardHeight
  label: string; // 如 '6连板 (最高标)', '5连板 (断层)', '首板 (1板)'
  yesterdayBaseLabel: string; // 如 '昨5板 (1家)', '昨4板 (1家)', '昨首板 (4家)'
  yesterdayBaseCount: number; // 昨日对应低一板基数
  yesterdayCandidateCount: number | null; // 昨日(N-1)板候选家数 (首板为 null)
  todaySealedCount: number; // 今日成功晋级封板家数
  eliminatedCount: number; // 晋级失败淘汰家数
  promotionRate: number | null; // 晋级率 (%)
  isFaultMissing: boolean; // 是否为断层真空层
  isFaultLevel: boolean; // 是否为晋级空间断层层级
  stockNames: string[]; // 该层封板股票名称列表
  stocks: BoardTierGroup['stocks']; // 该层封板股票详情列表
}

export interface LadderFaultZone {
  fromBoard: number; // 断层起始板数（低）
  toBoard: number; // 断层结束板数（高）
  spanSize: number; // 连续断层跨度层数
  label: string; // 如 '4连板 ~ 5连板 (连续2层断层)'
}

export type EbbTideRiskLevel = 'HIGH_EBB_RISK' | 'MEDIUM_FAULT_RISK' | 'LOW_HEALTHY';

export interface BoardLadderSummary {
  maxBoardHeight: number; // 当前最高空间板高度
  secondMaxBoardHeight: number; // 次高板高度（用于计算最高标孤立度）
  spaceDragonSymbol: string;
  spaceDragonName: string;
  firstToSecondRate: number; // 首板晋级率 (1进2 %)
  secondToThirdRate: number; // 2进3 晋级率 (%)
  highBoardPromotionRate: number; // 3板及以上高位晋级率 (%)
  sealSuccessRate: number; // 今日封板率 (%)
  brokenBoardCount: number; // 今日炸板家数
  limitDownCount: number; // 跌停/核按钮家数
  missingBoards: number[]; // 断层缺失的连板高度列表（如 [5, 4]）
  hasLadderFault: boolean; // 是否存在连板梯队断层
  faultZones: LadderFaultZone[]; // 连续断层区间列表
  maxFaultSpan: number; // 最大连续断层跨度
  topDragonIsolation: boolean; // 最高空间板是否处于断层孤立独苗状态 (maxBoard - secondMaxBoard >= 2)
  ebbTideRiskLevel: EbbTideRiskLevel; // 潜在退潮风险等级
  ebbTideRiskScore: number; // 潜在退潮风险量化评分 (0 ~ 100)
  ebbTideWarningTitle: string; // 退潮风险核心警示标题
  ebbTideRiskReasons: string[]; // 退潮风险多维归因列表
  tacticalPlaybook: string; // 游资应对策略建议
  distributionComparison: LadderDistributionRow[]; // 今日涨停板分布与昨日基数逐层对比
  faultWarningText: string; // 断层监测结论
  sentimentPhase: '主升共振期' | '高潮分化期' | '混沌试错期' | '退潮核按钮期';
  tiers: BoardTierGroup[];
}

export type ThemeResonanceScenarioPreset =
  | 'live'
  | 'ai_chip_mainstream'
  | 'rotation_divergence';

export type ThemeAttackRole =
  | 'MAIN_ATTACK'      // 主流资金主攻方向
  | 'SUB_ROTATION'     // 支线轮动进攻
  | 'DEFENSIVE_HOLD'   // 防守观察/分歧
  | 'EBB_RETREAT';     // 资金兑现退潮

/**
 * 题材点面共振、涨停密度与领涨龙头联动识别结果
 */
export interface ThemeResonanceItem {
  sectorName: string;
  sectorChangePercent: number; // 板块“面”整体涨幅 (%)
  limitUpCount: number; // 板块内涨停家数
  sectorConstituentCount: number; // 板块核心跟踪成分股基数
  limitUpDensityPercent: number; // 板块内涨停个股密度 (%) = limitUpCount / sectorConstituentCount * 100
  densityLevel: '涨停潮高密区' | '梯队成型区' | '局部试错区' | '冰点无溢价';
  upRatioPercent: number; // 板块内红盘家数占比 (%)
  totalNetInflowCNY: number; // 板块主力净买额 (元)
  totalTurnoverCNY: number; // 板块总成交额 (元)
  resonanceScore: number; // 点面共振综合得分 (0 ~ 100)
  resonanceStatus: '主线强共振' | '局部轮动' | '分歧兑现';
  dragonLinkageScore: number; // 领涨龙头联动指数 (0 ~ 100)：衡量先锋龙封板、中军放量与后排跟风协同度
  dragonLinkageStatus: '先锋中军强联动' | '单点脉冲跟风弱' | '龙头孤立背离';
  dragonLinkageDesc: string; // 龙头联动传导链条描述
  attackRole: ThemeAttackRole; // 当日主力资金进攻角色定性
  attackRoleLabel: string; // '主攻核心主线' | '支线轮动助攻' | '分歧观察区' | '资金兑现退潮'
  capitalAttackSharePercent: number; // 占全市场做多资金进攻权重 (%)
  heatWeight: number; // D3 矩形树图/热力分布图面积权重
  pioneerDragon: {
    symbol: string;
    name: string;
    changePercent: number;
    firstSealTime: string | null;
    consecutiveBoards: number;
  };
  capacityCore: {
    symbol: string;
    name: string;
    changePercent: number;
    amount: number;
  };
  memberStocks: {
    symbol: string;
    code: string;
    name: string;
    price: number;
    changePercent: number;
    consecutiveBoards: number;
    dragonRole: DragonRoleTag;
    roleLabel: string;
    firstSealTime: string | null;
    amount?: number;
    isLimitUp?: boolean;
  }[];
}

/**
 * 全市场板块/题材共振监测与主流资金进攻方向汇总
 */
export interface ThemeResonanceOverview {
  scenario: ThemeResonanceScenarioPreset;
  themes: ThemeResonanceItem[];
  mainstreamAttackSectors: string[]; // 当日主流资金进攻主线名称列表
  subRotationSectors: string[]; // 支线轮动题材列表
  retreatSectors: string[]; // 退潮兑现题材列表
  marketResonanceScore: number; // 全市场主线共振强度指数 (0 ~ 100)
  mainstreamConcentrationPercent: number; // 前二主线资金与涨停集中度 (%)
  totalMarketLimitUpCount: number; // 全市场题材池合计涨停家数
  avgLimitUpDensityPercent: number; // 热门题材平均涨停密度 (%)
  attackDirectionHeadline: string; // 主流资金进攻方向核心结论
  tacticalPlaybook: string; // 游资接力与仓位配置策略建议
}

export type RegulatoryAlertLight = 'RED' | 'YELLOW' | 'GREEN';

/**
 * 现行注册制法定复利异动监管逆推与红黄灯特停监测结果 (k ∈ {2, 3} 窗口 + 10日100%/4次异动特停预警)
 */
export interface RegulatoryDeviationResult {
  symbol: string;
  code: string;
  name: string;
  sector: string;
  ruleThresholdPercent: number; // 20% (主板) 或 30% (创业板/科创板)
  boardRuleLabel: string; // '沪深主板 ±20%' | '创业板/科创板 ±30%'
  currentPrice: number;
  currentChangePercent: number;

  // 逐日历史与当日涨跌幅明细 (%)
  stockReturnT2Percent: number; // T-2 日个股涨幅 (%)
  stockReturnT1Percent: number; // T-1 日个股涨幅 (%)
  indexReturnT2Percent: number; // T-2 日对应基准指数涨幅 (%)
  indexReturnT1Percent: number; // T-1 日对应基准指数涨幅 (%)
  indexReturnTodayPercent: number; // 今日对应基准指数涨幅 (%)

  // k = 2 (连续2个交易日) 实时涨跌幅与复利偏离逆推
  stockCumReturn2DayPercent: number; // 2个交易日个股累计复利涨跌幅 (%)
  indexCumReturn2DayPercent: number; // 2个交易日基准指数累计复利涨跌幅 (%)
  dev2DayCurrentPercent: number; // 当前实时2日累计偏离值 (%)
  windowSaturation2DayPercent: number; // 2日异动窗口额度占用率 (0 ~ 100+%)
  maxSafeChange2DayPercent: number; // 今日不触发2日异动的极限安全涨幅 (%)
  triggerPrice2Day: number; // 触发2日异动的精确临界价 (元)

  // k = 3 (连续3个交易日) 实时涨跌幅与复利偏离逆推
  stockCumReturn3DayPercent: number; // 3个交易日个股累计复利涨跌幅 (%)
  indexCumReturn3DayPercent: number; // 3个交易日基准指数累计复利涨跌幅 (%)
  dev3DayCurrentPercent: number; // 当前实时3日累计偏离值 (%)
  windowSaturation3DayPercent: number; // 3日异动窗口额度占用率 (0 ~ 100+%)
  maxSafeChange3DayPercent: number; // 今日不触发3日异动的极限安全涨幅 (%)
  triggerPrice3Day: number; // 触发3日异动的精确临界价 (元)

  // 取 k ∈ {2, 3} 最严苛绑定窗口
  bindingWindowK: 2 | 3;
  effectiveTriggerPrice: number; // min(triggerPrice2Day, triggerPrice3Day)
  effectiveMaxSafeChangePercent: number; // 综合安全涨幅上限 (%)
  remainingSafeMarginPercent: number; // 距离今日触线临界涨幅的剩余安全余量 (%)
  isTriggeredToday: boolean; // 当前价格是否已触及或突破 k∈{2,3} 法定异动线

  // 10日 100% 严重异动与 10日 4次同向异动特停锁死预警
  cumDeviation10dPercent: number | null; // 实时10日累计偏离值 (%)，无真实值时为 null → 显示 '—'
  remainingTo100Percent: number | null; // 距离 100% 严重异动红线剩余空间 (%)，无真实值时为 null
  abnormalCount10d: number | null; // 近10个交易日已触发异动次数 (满4次触发严重异动)，未知为 null
  remainingAbnormalTimes10d: number | null; // 距10日4次严重异动剩余次数，未知为 null
  severeSuspensionLockWarning: boolean; // 是否触发严重异动/特停锁死高危预警
  suspensionRiskScore: number; // 特停风险综合指数 (0 ~ 100)

  // 红黄绿信号灯预警体系
  alertLight: RegulatoryAlertLight; // 'RED' | 'YELLOW' | 'GREEN'
  alertLightLabel: '红灯 · 特停/触线高危' | '黄灯 · 异动压线临界' | '绿灯 · 安全运行区间';
  alertLightReason: string;
  tacticalPlaybook: string;
  statusSummary: string;

  /**
   * T-1/T-2 涨跌幅的来源：
   *  'kline'     = 来自 /api/quant/regulatory 返回的真实日K（可放心用）
   *  'estimated' = 后端没给（该股不在当前请求里），前端用的是占位默认值，必须打「估算」标
   */
  historySource: 'kline' | 'estimated';
}

/**
 * 交易所法规引擎（后端 /api/quant/regulatory 的 regulatory 段）—— 真实口径
 * 与前端本地 2/3 日模型不同：这里是按交易所规则（偏离度/10日4次/严重异动）+ 真实指数基准算的。
 */
export interface RegulatoryEngineResult {
  stock_code: string;
  board_name: string; // '沪深主板(10cm)' 等
  prev_close: number;
  curr_price: number;
  limit_up_price: number;
  safe_price: number; // 今日不触发异动的最高安全价
  normal_safe_price: number;
  severe_safe_price: number;
  headroom_pct: number; // 距安全价的剩余空间 (小数，0.1732 = 17.32%)
  severe_headroom_pct: number;
  is_unconstrained_today: boolean;
  is_severe_unconstrained_today: boolean;
  is_normal_triggered_now: boolean;
  is_severe_triggered_now: boolean;
  is_severe_locked: boolean;
  normal_triggers_in_prev_9d: number;
  will_Upgrade_to_severe_on_normal: boolean;
  binding_window: {
    window_type: string;
    window_days: number;
    start_date: string;
    base_price_adj: number;
    base_index: number;
    threshold: number;
    safe_price: number;
    exact_trigger_price: number;
    curr_cum_dev: number;
  } | null;
  action_advice: string;
}

/** 后端返回的 T-1/T-2 真实涨跌幅（供本地 2/3 日模型用） */
export interface RegulatoryHistory {
  source: string; // 'kline'
  dates: string[];
  date_t2?: string;
  date_t1?: string;
  date_today?: string;
  stock_return_t1?: number | null;
  stock_return_t2?: number | null;
  index_return_t1?: number | null;
  index_return_t2?: number | null;
  index_return_today?: number | null;
}

/** 缠论分型/笔端点：[日期, 价格, '顶'|'底', K线索引] */
export type ChanBiPoint = [string, number, string, number];

export interface ChanZhongshu {
  lo: number;
  hi: number;
  start_date: string;
  end_date: string;
  pos?: string; // 现价相对中枢位置: 内部 / 上方 / 下方
}

export interface ChanSignal {
  date: string;
  price: number;
  type: string; // 底背驰 / 一买候选 / 顶背驰 / 一卖警戒 …
  desc: string;
  color?: string;
}

/** 缠论结构分析（后端 /api/quant/chan/{symbol} → core.chan.chan_analysis_structured） */
export interface ChanAnalysis {
  status: string;
  cur_dir?: string;
  trail?: string;
  bi_points: ChanBiPoint[];
  bi_list?: ChanBiPoint[];
  zhongshu_list: ChanZhongshu[];
  last_zhongshu: ChanZhongshu | null;
  signals: ChanSignal[];
  divergence?: string | null;
  hint?: string;
  summary?: string;
}

/**
 * 全市场监管异动监测汇总结果
 */
export interface RegulatoryMonitorOverview {
  items: RegulatoryDeviationResult[];
  redLightCount: number;
  yellowLightCount: number;
  greenLightCount: number;
  suspensionWarningCount: number;
  triggeredTodayCount: number;
  highestRiskStock: RegulatoryDeviationResult | null;
}

/**
 * 真实成交量加权承接算子 (VW-DVR: Volume-Weighted Dynamic Volume Support Ratio)
 */
export interface VWDVRResult {
  symbol: string;
  code: string;
  name: string;
  vwap: number; // 日内真实成交量加权均价
  priceToVwapDiffPercent: number; // 最新价相对 VWAP 乖离率 (%)
  aboveVwapVolumeRatio: number; // 水上（>=VWAP）成交量占总成交量比例 (%)
  dipBuyAbsorptionRatio: number; // 分时回踩切片外盘主动承接吸收率 (%)
  lowerShadowResilience: number; // 日内下影线探底回升韧性系数 (0 ~ 100)
  vwDvrScore: number; // 综合真实成交量加权承接算子得分 (0 ~ 100)
  signal: 'STRONG_ABSORPTION' | 'HEALTHY_TURNOVER' | 'WEAK_DISTRIBUTION';
  signalLabel: string;
  actionAdvice: string;
}

/**
 * 六、龙虎榜席位性质分类与游资/机构/量化博弈分析 (基于沪深交易所公开龙虎榜前五买卖席位披露)
 */
export type DragonTigerSeatNature =
  | 'HOT_MONEY' // 游资常用席位（如作手新一、章盟主、赵老哥、炒股养家、孙哥等）
  | 'INSTITUTION' // 机构专用 / 沪深股通北向配置席位
  | 'QUANT_CAMP' // 量化大本营（如华泰总部、中信上分、中金上分等高频算法席位）
  | 'RETAIL_CAMP'; // 散户合力大本营（如东方财富拉萨团结路/东环路天团）

export interface DragonTigerSeatItem {
  rank: number; // 1 ~ 5
  side: 'BUY' | 'SELL';
  branchName: string; // 营业部全称
  nature: DragonTigerSeatNature; // 席位性质分类
  natureLabel: string; // '游资常用席位' | '机构专用' | '量化大本营' | '散户大本营'
  seatTag: string; // 席位名号（如 '顶级游资 · 作手新一'、'机构专用'、'量化大本营 · 华泰总部'）
  operatingStyle: string; // 操盘风格标签（如 '龙头连板主封/格局锁仓'、'高频打板/次日冲高兑现'）
  buyAmount: number; // 买入金额 (元)
  sellAmount: number; // 卖出金额 (元)
  netAmount: number; // 净买额 = buyAmount - sellAmount (元)
  turnoverSharePercent: number; // 占当日总成交额比例 (%)
}

export interface DragonTigerCampSummary {
  nature: DragonTigerSeatNature;
  label: string;
  buyAmount: number;
  sellAmount: number;
  netAmount: number;
  buySharePercent: number; // 占前五总买额比例 (%)
  seatCount: number; // 上榜席位数
  representativeTags: string[]; // 代表席位名号
}

export type DragonTigerPresetMode =
  | 'live'
  | 'hot_inst_resonance'
  | 'quant_crowded'
  | 'retail_takeover';

export interface DragonTigerAnalysis {
  symbol: string;
  code: string;
  name: string;
  sector: string;
  price: number;
  changePercent: number;
  dailyAmount: number;
  boardType: '1D' | '3D'; // 单日榜 vs 连续三日榜
  listingReason: string; // 上榜原因（如 '日涨幅偏离值达7%的证券'）
  buySeats: DragonTigerSeatItem[]; // 买入前五营业部
  sellSeats: DragonTigerSeatItem[]; // 卖出前五营业部
  totalBuyAmount: number; // 前五合计买入额 (元)
  totalSellAmount: number; // 前五合计卖出额 (元)
  totalNetAmount: number; // 前五合计净买额 (元)
  buyTurnoverRatioPercent: number; // 前五买入占总成交比 (%)
  sellTurnoverRatioPercent: number; // 前五卖出占总成交比 (%)
  netTurnoverRatioPercent: number; // 龙虎榜净额占总成交比 (%)
  campBreakdown: DragonTigerCampSummary[]; // 四大资金阵营（游资/机构/量化/散户）汇总
  dominantCamp: DragonTigerSeatNature;
  synergyVerdict:
    | 'HOT_INST_RESONANCE' // 游资+机构共振主封
    | 'TOP_HOT_LOCK' // 顶级游资重仓接力锁仓
    | 'QUANT_CROWDED_RISK' // 量化大本营扎堆 (防次日冲高砸盘)
    | 'RETAIL_TAKEOVER_WARN' // 散户大本营接盘预警
    | 'MAIN_FORCE_EXIT'; // 主力席位大举出逃
  synergyLabel: string;
  nextDayPremiumScore: number; // 次日溢价预期评分 (0 ~ 100)
  actionablePlaybook: string; // 次日集合竞价与分时应对策略
  isSimulated: boolean; // 龙虎榜席位数据是否为前端模拟（true=非真实接口数据）
}

/**
 * 龙虎榜游资大佬/营业部席位近期上榜战绩明细
 */
export interface DragonTigerSeatBattleRecord {
  date: string; // 上榜日期，如 '2026-10-22'
  symbol: string;
  name: string;
  sector: string;
  roleLabel: string; // 如 '主封买一 (3连板)' / '格局锁仓' / '分歧引导'
  buyAmount: number; // 买入额 (元)
  netAmount: number; // 净买额 (元)
  nextDayPremiumPercent: number; // 次日溢价率 (%)
}

/**
 * 龙虎榜营业部席位活跃度与历史操盘画像 (点击网络图节点时展示)
 */
export interface DragonTigerSeatActivityProfile {
  branchName: string; // 营业部全称
  shortBranchName: string; // 营业部简称（如 '国君南京太平南路'）
  seatTag: string; // 席位名号（如 '顶级游资 · 作手新一'）
  nature: DragonTigerSeatNature;
  natureLabel: string;
  operatingStyle: string;
  activityLevelLabel: '极度活跃 · 市场风向标' | '高度活跃 · 主线常客' | '中度活跃 · 波段出击';
  activityScore: number; // 席位综合活跃度指数 (0 ~ 100)
  appearances30d: number; // 近30日上榜次数 (次)
  totalCapital30d: number; // 近30日累计动用买方资金 (元)
  avgSingleBuyAmount: number; // 单次上榜场均买入额 (元)
  nextDayAvgPremiumPercent: number; // 上榜次日平均溢价率 (%)
  sealWinRatePercent: number; // 封板次日溢价胜率 (%)
  holdingHorizon: string; // 持仓周期特征（如 'T+1 溢价锁仓 / 主升格局 2~3 日'）
  favoriteSectors: string[]; // 主攻题材偏好
  coAppearingAllies: string[]; // 高频同榜协同席位名号
  recentBattles: DragonTigerSeatBattleRecord[]; // 近期代表性上榜战役
  monthlyTrend: { weekLabel: string; count: number; capital: number }[]; // 近4周上榜频次与资金趋势
}

/**
 * D3.js 龙虎榜席位关联网络图节点与连线数据结构
 */
export interface DragonTigerGraphNode {
  id: string;
  nodeType: 'TARGET_STOCK' | 'BROKER_SEAT' | 'ALLY_STOCK';
  label: string; // 节点主标题（如 '三六零' 或 '顶级游资 · 作手新一'）
  subLabel: string; // 节点副标题（如 '601360.SH' 或 '国君南京太平南路'）
  branchName?: string; // 若为营业部节点，对应完整 branchName
  symbol?: string; // 若为股票节点，对应股票代码
  nature?: DragonTigerSeatNature;
  natureLabel?: string;
  side?: 'BUY' | 'SELL' | 'BOTH';
  rankLabel?: string; // 如 '买1' / '卖2' / '买卖同榜'
  buyAmount: number; // 当日买入金额 (元)
  sellAmount: number; // 当日卖出金额 (元)
  netAmount: number; // 当日净买额 (元)
  turnoverSharePercent: number;
  activityProfile?: DragonTigerSeatActivityProfile;
  radius: number; // 节点视觉半径 (px)
}

export interface DragonTigerGraphLink {
  id: string;
  sourceId: string;
  targetId: string;
  linkType: 'PRIMARY_BUY' | 'PRIMARY_SELL' | 'CO_APPEAR_STOCK';
  side: 'BUY' | 'SELL';
  buyAmount: number; // 连线代表的核心买入金额 (元)，决定连线粗细
  sellAmount: number;
  netAmount: number;
  strokeWidth: number; // 基于买入金额映射的连线粗细 (px, 1.8 ~ 9.5)
  turnoverSharePercent: number;
  description: string;
}

export interface DragonTigerNetworkData {
  symbol: string;
  stockName: string;
  nodes: DragonTigerGraphNode[];
  links: DragonTigerGraphLink[];
  maxBuyAmount: number;
  minBuyAmount: number;
  hotMoneySeatCount: number;
  totalHotMoneyBuyAmount: number;
}

/**
 * 全市场竞价扫描信号类型（与接力雷达的 AuctionSignalType 不同，新增 FAKE_HIGH）
 */
export type FullScanSignalType =
  | 'SUPER_GRAB'       // 超预期抢筹
  | 'NUCLEAR_BUTTON'   // 竞价核按钮
  | 'LOCKED_LIMIT_UP'  // 一字封单
  | 'FAKE_HIGH';       // 缩量假高开

/**
 * 全市场竞价扫描单标的信号项
 */
export interface FullMarketScanItem {
  code: string;
  name: string;
  price: number;
  open_pct: number;   // 开盘涨幅 (%)
  pct: number;        // 涨跌幅 (%)
  vol_ratio: number;  // 量比
  amount: number;     // 成交额 (元)
  signal: FullScanSignalType;
  signalLabel: string;
}

/**
 * 全市场竞价扫描 API 响应 (/api/quant/full_market_scan)
 */
export interface FullMarketScanData {
  status: string;
  scan_items: FullMarketScanItem[];
  grabCount: number;
  nuclearCount: number;
  fakeHighCount: number;
  lockedCount: number;
  total_scanned: number;
  updated_at: string;
}

export type QuantModuleTabId =
  | 'overview'
  | 'auction'
  | 'ladder'
  | 'resonance'
  | 'regulatory'
  | 'vwdvr'
  | 'dragon_tiger';

/**
 * 价格与涨跌幅预警条件类型
 * - CHANGE_PCT_ABOVE: 涨跌幅高于或等于指定阈值 (%)，如 +3.00%
 * - CHANGE_PCT_BELOW: 涨跌幅低于或等于指定阈值 (%)，如 -2.00%
 * - PRICE_ABOVE: 最新价高于或等于目标价 (元)
 * - PRICE_BELOW: 最新价低于或等于目标价 (元)
 */
export type AlertConditionType =
  | 'CHANGE_PCT_ABOVE'
  | 'CHANGE_PCT_BELOW'
  | 'PRICE_ABOVE'
  | 'PRICE_BELOW';

export interface PriceAlertRule {
  id: string;
  symbol: string;
  stockName: string;
  condition: AlertConditionType;
  threshold: number;
  enabled: boolean;
  triggered: boolean;
  triggeredAt?: number;
  triggeredPrice?: number;
  triggeredChangePercent?: number;
  createdAt: number;
}

export interface TriggeredAlertEvent {
  id: string;
  ruleId: string;
  symbol: string;
  stockName: string;
  condition: AlertConditionType;
  threshold: number;
  price: number;
  changePercent: number;
  message: string;
  timestamp: number;
}

/**
 * WebSocket 服务端推送与客户端消息协议
 */
export type WSServerMessage =
  | {
      type: 'INIT_SNAPSHOT';
      quotes: TickData[];
      indices: MarketIndexQuote[];
      batchWindowMs: number;
      serverTime: number;
    }
  | {
      type: 'SNAPSHOT_BATCH';
      quotes: TickData[];
      indices: MarketIndexQuote[];
      batchWindowMs: number;
      serverTime: number;
    }
  | {
      type: 'PONG';
      clientTimestamp: number;
      serverTime: number;
    };

export type WSClientMessage =
  | {
      type: 'PING';
      timestamp: number;
    }
  | {
      type: 'SUBSCRIBE';
      symbols: string[];
    }
  | {
      type: 'SET_BATCH_WINDOW';
      windowMs: number;
    };

