import type {
  ChartPeriod,
  IntradayPoint,
  KLineBar,
  MarketIndexQuote,
  MarketScenario,
  OrderBook5,
  TickData,
  TradeTick,
  TradingPhase,
  UltraShortProfile,
} from '../types/market';

interface StockSeedConfig {
  symbol: string;
  code: string;
  market: 'SH' | 'SZ';
  name: string;
  pinyin: string;
  sector: string;
  prevClose: number;
  price: number;
  open: number;
  high: number;
  low: number;
  volume: number; // 手
  turnoverRate: number;
  volumeRatio: number;
  peTtm: number;
  pb: number;
  marketCap: number; // 亿
  floatMarketCap: number; // 亿
  limitRate: number; // 0.10 or 0.20
  initialPhase: TradingPhase;
}

export const STOCK_SEED_CONFIGS: StockSeedConfig[] = [
  {
    symbol: '600519.SH',
    code: '600519',
    market: 'SH',
    name: '贵州茅台',
    pinyin: 'gzmt',
    sector: '酿酒行业',
    prevClose: 1548.0,
    price: 1582.6,
    open: 1555.0,
    high: 1591.0,
    low: 1551.2,
    volume: 42860,
    turnoverRate: 0.34,
    volumeRatio: 1.42,
    peTtm: 23.8,
    pb: 8.45,
    marketCap: 19880,
    floatMarketCap: 19880,
    limitRate: 0.1,
    initialPhase: 'TRADING',
  },
  {
    symbol: '300750.SZ',
    code: '300750',
    market: 'SZ',
    name: '宁德时代',
    pinyin: 'ndsd',
    sector: '电池储能',
    prevClose: 246.5,
    price: 256.88,
    open: 248.2,
    high: 259.5,
    low: 247.6,
    volume: 386400,
    turnoverRate: 1.85,
    volumeRatio: 1.76,
    peTtm: 21.4,
    pb: 4.92,
    marketCap: 11300,
    floatMarketCap: 9850,
    limitRate: 0.2,
    initialPhase: 'TRADING',
  },
  {
    symbol: '002594.SZ',
    code: '002594',
    market: 'SZ',
    name: '比亚迪',
    pinyin: 'byd',
    sector: '新能源车',
    prevClose: 292.0,
    price: 301.45,
    open: 294.0,
    high: 304.8,
    low: 293.1,
    volume: 294500,
    turnoverRate: 2.54,
    volumeRatio: 1.65,
    peTtm: 24.6,
    pb: 5.68,
    marketCap: 8770,
    floatMarketCap: 3510,
    limitRate: 0.1,
    initialPhase: 'TRADING',
  },
  {
    symbol: '688981.SH',
    code: '688981',
    market: 'SH',
    name: '中芯国际',
    pinyin: 'zxgj',
    sector: '半导体',
    prevClose: 91.2,
    price: 97.65,
    open: 92.5,
    high: 99.1,
    low: 91.8,
    volume: 1185000,
    turnoverRate: 5.96,
    volumeRatio: 2.38,
    peTtm: 112.5,
    pb: 3.42,
    marketCap: 7780,
    floatMarketCap: 1940,
    limitRate: 0.2,
    initialPhase: 'TRADING',
  },
  {
    symbol: '300059.SZ',
    code: '300059',
    market: 'SZ',
    name: '东方财富',
    pinyin: 'dfcf',
    sector: '互联网金融',
    prevClose: 23.4,
    price: 22.92,
    open: 23.35,
    high: 23.68,
    low: 22.75,
    volume: 4820000,
    turnoverRate: 3.62,
    volumeRatio: 1.18,
    peTtm: 38.2,
    pb: 4.55,
    marketCap: 3618,
    floatMarketCap: 3060,
    limitRate: 0.2,
    initialPhase: 'TRADING',
  },
  {
    symbol: '601318.SH',
    code: '601318',
    market: 'SH',
    name: '中国平安',
    pinyin: 'zgpa',
    sector: '非银金融',
    prevClose: 56.8,
    price: 57.64,
    open: 57.0,
    high: 58.12,
    low: 56.72,
    volume: 945000,
    turnoverRate: 0.88,
    volumeRatio: 1.12,
    peTtm: 9.4,
    pb: 1.12,
    marketCap: 10490,
    floatMarketCap: 6210,
    limitRate: 0.1,
    initialPhase: 'TRADING',
  },
  {
    symbol: '600036.SH',
    code: '600036',
    market: 'SH',
    name: '招商银行',
    pinyin: 'zsyh',
    sector: '银行',
    prevClose: 39.25,
    price: 38.92,
    open: 39.2,
    high: 39.38,
    low: 38.76,
    volume: 612000,
    turnoverRate: 0.3,
    volumeRatio: 0.94,
    peTtm: 6.7,
    pb: 0.98,
    marketCap: 9810,
    floatMarketCap: 8015,
    limitRate: 0.1,
    initialPhase: 'TRADING',
  },
  {
    symbol: '601360.SH',
    code: '601360',
    market: 'SH',
    name: '三六零',
    pinyin: 'sll',
    sector: '人工智能',
    prevClose: 10.5,
    price: 11.55, // 涨停价
    open: 10.82,
    high: 11.55,
    low: 10.78,
    volume: 2680000,
    turnoverRate: 3.75,
    volumeRatio: 3.45,
    peTtm: 88.0,
    pb: 2.65,
    marketCap: 825,
    floatMarketCap: 825,
    limitRate: 0.1,
    initialPhase: 'LIMIT_UP',
  },
  {
    symbol: '002230.SZ',
    code: '002230',
    market: 'SZ',
    name: '科大讯飞',
    pinyin: 'kdxf',
    sector: '人工智能',
    prevClose: 46.8,
    price: 47.95,
    open: 47.95,
    high: 47.95,
    low: 47.95,
    volume: 58400,
    turnoverRate: 0.27,
    volumeRatio: 1.92,
    peTtm: 96.4,
    pb: 6.35,
    marketCap: 1108,
    floatMarketCap: 1042,
    limitRate: 0.1,
    initialPhase: 'CALL_AUCTION',
  },
  {
    symbol: '000858.SZ',
    code: '000858',
    market: 'SZ',
    name: '五粮液',
    pinyin: 'wly',
    sector: '酿酒行业',
    prevClose: 146.2,
    price: 148.85,
    open: 146.9,
    high: 149.6,
    low: 146.1,
    volume: 192000,
    turnoverRate: 0.5,
    volumeRatio: 1.26,
    peTtm: 17.8,
    pb: 4.32,
    marketCap: 5778,
    floatMarketCap: 5778,
    limitRate: 0.1,
    initialPhase: 'TRADING',
  },
  {
    symbol: '601899.SH',
    code: '601899',
    market: 'SH',
    name: '紫金矿业',
    pinyin: 'zjky',
    sector: '有色金属',
    prevClose: 17.45,
    price: 17.88,
    open: 17.52,
    high: 18.02,
    low: 17.41,
    volume: 1840000,
    turnoverRate: 0.89,
    volumeRatio: 1.33,
    peTtm: 16.5,
    pb: 3.85,
    marketCap: 4750,
    floatMarketCap: 3680,
    limitRate: 0.1,
    initialPhase: 'TRADING',
  },
  {
    symbol: '000651.SZ',
    code: '000651',
    market: 'SZ',
    name: '格力电器',
    pinyin: 'gldq',
    sector: '家用电器',
    prevClose: 44.2,
    price: 39.78, // 跌停示范
    open: 41.5,
    high: 41.8,
    low: 39.78,
    volume: 895000,
    turnoverRate: 1.61,
    volumeRatio: 2.15,
    peTtm: 7.8,
    pb: 1.86,
    marketCap: 2240,
    floatMarketCap: 2218,
    limitRate: 0.1,
    initialPhase: 'LIMIT_DOWN',
  },
];

/**
 * 构建符合交易状态（正常、涨停封板、跌停封板、集合竞价）的 Level-1 五档盘口
 */
export function buildOrderBookForPhase(
  price: number,
  phase: TradingPhase,
  limitUpPrice: number,
  limitDownPrice: number,
  seedOffset = 0
): OrderBook5 {
  const tickStep = price >= 100 ? 0.1 : 0.01;
  const roundPrice = (p: number) => Number(p.toFixed(2));

  if (phase === 'LIMIT_UP') {
    // 涨停封板：买一巨量封单，买二~买五正常递减；卖一~卖五全部为空档 null (UI 渲染为 '--')
    return {
      bids: [
        { level: 1, price: limitUpPrice, volume: 128500 + seedOffset * 10 },
        { level: 2, price: roundPrice(limitUpPrice - tickStep), volume: 4200 },
        { level: 3, price: roundPrice(limitUpPrice - tickStep * 2), volume: 2680 },
        { level: 4, price: roundPrice(limitUpPrice - tickStep * 3), volume: 1850 },
        { level: 5, price: roundPrice(limitUpPrice - tickStep * 4), volume: 1120 },
      ],
      asks: [
        { level: 1, price: null, volume: null },
        { level: 2, price: null, volume: null },
        { level: 3, price: null, volume: null },
        { level: 4, price: null, volume: null },
        { level: 5, price: null, volume: null },
      ],
    };
  }

  if (phase === 'LIMIT_DOWN') {
    // 跌停封板：买一~买五全部为空档 null (UI 渲染为 '--')；卖一巨量封单
    return {
      bids: [
        { level: 1, price: null, volume: null },
        { level: 2, price: null, volume: null },
        { level: 3, price: null, volume: null },
        { level: 4, price: null, volume: null },
        { level: 5, price: null, volume: null },
      ],
      asks: [
        { level: 1, price: limitDownPrice, volume: 86400 + seedOffset * 10 },
        { level: 2, price: roundPrice(limitDownPrice + tickStep), volume: 3100 },
        { level: 3, price: roundPrice(limitDownPrice + tickStep * 2), volume: 1920 },
        { level: 4, price: roundPrice(limitDownPrice + tickStep * 3), volume: 1450 },
        { level: 5, price: roundPrice(limitDownPrice + tickStep * 4), volume: 980 },
      ],
    };
  }

  if (phase === 'CALL_AUCTION') {
    // 集合竞价阶段：买一、卖一为撮合参考价，买二/卖二为未撮合量，买三~买五与卖三~卖五为空档 null
    return {
      bids: [
        { level: 1, price: roundPrice(price), volume: 6420 + seedOffset },
        { level: 2, price: null, volume: 1280 },
        { level: 3, price: null, volume: null },
        { level: 4, price: null, volume: null },
        { level: 5, price: null, volume: null },
      ],
      asks: [
        { level: 1, price: roundPrice(price), volume: 6420 + seedOffset },
        { level: 2, price: null, volume: 840 },
        { level: 3, price: null, volume: null },
        { level: 4, price: null, volume: null },
        { level: 5, price: null, volume: null },
      ],
    };
  }

  // 正常连续竞价五档盘口
  const baseVol = price > 500 ? 80 : price > 100 ? 450 : 2200;
  return {
    bids: [
      { level: 1, price: roundPrice(price - tickStep * 0), volume: Math.round(baseVol * 1.35 + (seedOffset % 90)) },
      { level: 2, price: roundPrice(price - tickStep * 1), volume: Math.round(baseVol * 0.95 + (seedOffset % 70)) },
      { level: 3, price: roundPrice(price - tickStep * 2), volume: Math.round(baseVol * 1.65 + (seedOffset % 110)) },
      { level: 4, price: roundPrice(price - tickStep * 3), volume: Math.round(baseVol * 0.75 + (seedOffset % 50)) },
      { level: 5, price: roundPrice(price - tickStep * 4), volume: Math.round(baseVol * 1.15 + (seedOffset % 80)) },
    ],
    asks: [
      { level: 1, price: roundPrice(price + tickStep * 1), volume: Math.round(baseVol * 1.05 + (seedOffset % 85)) },
      { level: 2, price: roundPrice(price + tickStep * 2), volume: Math.round(baseVol * 0.85 + (seedOffset % 65)) },
      { level: 3, price: roundPrice(price + tickStep * 3), volume: Math.round(baseVol * 1.45 + (seedOffset % 120)) },
      { level: 4, price: roundPrice(price + tickStep * 4), volume: Math.round(baseVol * 0.65 + (seedOffset % 45)) },
      { level: 5, price: roundPrice(price + tickStep * 5), volume: Math.round(baseVol * 1.25 + (seedOffset % 95)) },
    ],
  };
}

function buildInitialTrades(price: number, phase: TradingPhase): TradeTick[] {
  const step = price >= 100 ? 0.1 : 0.01;
  const baseVol = price > 500 ? 12 : price > 100 ? 68 : 320;
  const times = [
    '14:56:42',
    '14:56:39',
    '14:56:36',
    '14:56:33',
    '14:56:30',
    '14:56:27',
    '14:56:24',
    '14:56:21',
    '14:56:18',
    '14:56:15',
    '14:56:12',
    '14:56:09',
    '14:56:06',
    '14:56:03',
  ];

  return times.map((time, idx) => {
    const offset = phase === 'TRADING' ? ((idx % 3) - 1) * step : 0;
    const side: 'BUY' | 'SELL' | 'NEUTRAL' =
      phase === 'LIMIT_UP'
        ? 'BUY'
        : phase === 'LIMIT_DOWN'
        ? 'SELL'
        : idx % 3 === 0
        ? 'BUY'
        : idx % 3 === 1
        ? 'SELL'
        : 'BUY';
    return {
      id: `init-${idx}-${time}`,
      time,
      price: Number((price + offset).toFixed(2)),
      volume: Math.max(1, Math.round(baseVol * (0.6 + ((idx * 37) % 100) / 50))),
      side,
    };
  });
}

function buildUltraShortProfile(cfg: StockSeedConfig, amount: number): UltraShortProfile {
  const is30Rule = cfg.code.startsWith('300') || cfg.code.startsWith('688');
  const boardRuleType = is30Rule ? 'CHINEXT_STAR_30' : 'MAIN_20';

  switch (cfg.symbol) {
    case '601360.SH': {
      // 6连板空间总龙：09:25 一字巨封顶板 + 10日累计偏离逼近100%特停红线
      const yesterdayAmount = 3120000000;
      const auctionAmount = 248000000; // 占昨比 ~7.95% 惜售锁筹
      return {
        auctionPrice: 11.55,
        auctionChangePercent: 10.0,
        auctionVolume: Math.round(auctionAmount / (11.55 * 100)),
        auctionAmount,
        yesterdayAmount,
        auctionUnmatchedHands: 128500,
        auctionVolumeRatio: 4.85,
        yesterdayPerformanceNote: '昨5连板加速T字板',
        consecutiveBoards: 6,
        yesterdayBoards: 5,
        isIntradayTouchedLimitUp: true,
        firstSealTime: '09:25:00',
        dragonRole: 'SPACE_DRAGON',
        boardRuleType,
        stockReturnT1: 10.02,
        stockReturnT2: 9.98,
        indexReturnT1: 0.85,
        indexReturnT2: 0.42,
        indexReturnToday: 1.05,
        cumDeviation10d: 89.4,
        abnormalCount10d: 3,
      };
    }
    case '002230.SZ': {
      // 3连板人工智能日内先锋龙：09:25 爆量高开超预期抢筹
      const yesterdayAmount = 4850000000;
      const auctionAmount = 562600000; // 占昨比 11.60% 黄金抢筹
      return {
        auctionPrice: 49.25,
        auctionChangePercent: 5.24,
        auctionVolume: Math.round(auctionAmount / (49.25 * 100)),
        auctionAmount,
        yesterdayAmount,
        auctionUnmatchedHands: 14600,
        auctionVolumeRatio: 6.42,
        yesterdayPerformanceNote: '昨2板烂板分歧换手',
        consecutiveBoards: 3,
        yesterdayBoards: 2,
        isIntradayTouchedLimitUp: true,
        firstSealTime: '09:33:18',
        dragonRole: 'PIONEER_DRAGON',
        boardRuleType,
        stockReturnT1: 10.01,
        stockReturnT2: 9.96,
        indexReturnT1: 1.12,
        indexReturnT2: 0.55,
        indexReturnToday: 1.82,
        cumDeviation10d: 34.8,
        abnormalCount10d: 1,
      };
    }
    case '688981.SH': {
      // 2连板科创板20cm容量中军龙：30%异动阈值逆推示范
      const yesterdayAmount = 9680000000;
      const auctionAmount = 885000000; // 占昨比 9.14%
      return {
        auctionPrice: 95.6,
        auctionChangePercent: 4.82,
        auctionVolume: Math.round(auctionAmount / (95.6 * 100)),
        auctionAmount,
        yesterdayAmount,
        auctionUnmatchedHands: 9200,
        auctionVolumeRatio: 3.95,
        yesterdayPerformanceNote: '昨20cm首板百亿主升',
        consecutiveBoards: 2,
        yesterdayBoards: 1,
        isIntradayTouchedLimitUp: true,
        firstSealTime: '09:42:06',
        dragonRole: 'CAPACITY_CORE',
        boardRuleType: 'CHINEXT_STAR_30',
        stockReturnT1: 19.98,
        stockReturnT2: 6.45,
        indexReturnT1: 1.65,
        indexReturnT2: 0.88,
        indexReturnToday: 3.35,
        cumDeviation10d: 38.6,
        abnormalCount10d: 1,
      };
    }
    case '300750.SZ': {
      // 首板 (1板) 创业板20cm先锋：超预期抢筹
      const yesterdayAmount = 8420000000;
      const auctionAmount = 682000000; // 占昨比 8.10%
      return {
        auctionPrice: 255.2,
        auctionChangePercent: 3.53,
        auctionVolume: Math.round(auctionAmount / (255.2 * 100)),
        auctionAmount,
        yesterdayAmount,
        auctionUnmatchedHands: 6800,
        auctionVolumeRatio: 3.12,
        yesterdayPerformanceNote: '昨缩量十字星洗盘',
        consecutiveBoards: 1,
        yesterdayBoards: 0,
        isIntradayTouchedLimitUp: true,
        firstSealTime: '10:05:42',
        dragonRole: 'PIONEER_DRAGON',
        boardRuleType: 'CHINEXT_STAR_30',
        stockReturnT1: 11.4,
        stockReturnT2: 8.6,
        indexReturnT1: 1.25,
        indexReturnT2: 0.72,
        indexReturnToday: 2.52,
        cumDeviation10d: 26.4,
        abnormalCount10d: 0,
      };
    }
    case '002594.SZ': {
      // 首板 (1板) 换手卡位龙：分歧弱转强
      const yesterdayAmount = 7950000000;
      const auctionAmount = 468000000; // 占昨比 5.89%
      return {
        auctionPrice: 298.5,
        auctionChangePercent: 2.23,
        auctionVolume: Math.round(auctionAmount / (298.5 * 100)),
        auctionAmount,
        yesterdayAmount,
        auctionUnmatchedHands: 4200,
        auctionVolumeRatio: 2.58,
        yesterdayPerformanceNote: '昨冲高回落长上影分歧',
        consecutiveBoards: 1,
        yesterdayBoards: 0,
        isIntradayTouchedLimitUp: true,
        firstSealTime: '10:28:15',
        dragonRole: 'TURNOVER_DRAGON',
        boardRuleType: 'MAIN_20',
        stockReturnT1: 8.25,
        stockReturnT2: 5.6,
        indexReturnT1: 0.92,
        indexReturnT2: 0.48,
        indexReturnToday: 1.82,
        cumDeviation10d: 21.5,
        abnormalCount10d: 0,
      };
    }
    case '300059.SZ': {
      // 竞价天量爆量兑现预警 + 冲高炸板样本 (昨日首板，今日1进2失败)
      const yesterdayAmount = 9200000000;
      const auctionAmount = 2162000000; // 占昨比 23.50% (>20%爆量警戒)
      return {
        auctionPrice: 24.15,
        auctionChangePercent: 3.21,
        auctionVolume: Math.round(auctionAmount / (24.15 * 100)),
        auctionAmount,
        yesterdayAmount,
        auctionUnmatchedHands: -3400,
        auctionVolumeRatio: 7.85,
        yesterdayPerformanceNote: '昨尾盘偷袭烂板',
        consecutiveBoards: 0,
        yesterdayBoards: 1,
        isIntradayTouchedLimitUp: true, // 曾触及涨停后炸板，用于真实计算封板率
        firstSealTime: null,
        dragonRole: 'CAPACITY_CORE',
        boardRuleType: 'CHINEXT_STAR_30',
        stockReturnT1: 14.8,
        stockReturnT2: 7.2,
        indexReturnT1: 1.45,
        indexReturnT2: 0.6,
        indexReturnToday: 2.52,
        cumDeviation10d: 29.8,
        abnormalCount10d: 0,
      };
    }
    case '000651.SZ': {
      // 竞价核按钮示范（昨日断板后今日竞价深水核按钮跌停）
      const yesterdayAmount = 3680000000;
      const auctionAmount = 412000000;
      return {
        auctionPrice: 40.35,
        auctionChangePercent: -8.71,
        auctionVolume: Math.round(auctionAmount / (40.35 * 100)),
        auctionAmount,
        yesterdayAmount,
        auctionUnmatchedHands: -86400,
        auctionVolumeRatio: 4.12,
        yesterdayPerformanceNote: '昨高位天量断板大面',
        consecutiveBoards: 0,
        yesterdayBoards: 2,
        isIntradayTouchedLimitUp: false,
        firstSealTime: null,
        dragonRole: 'FOLLOWER',
        boardRuleType: 'MAIN_20',
        stockReturnT1: -6.8,
        stockReturnT2: 10.0,
        indexReturnT1: 0.9,
        indexReturnT2: 0.5,
        indexReturnToday: 1.82,
        cumDeviation10d: 12.4,
        abnormalCount10d: 0,
      };
    }
    case '600519.SH': {
      // 酿酒容量中军龙：分歧弱转强 + 主板 k∈{2,3} 异动逆推
      const yesterdayAmount = 6150000000;
      const auctionAmount = 398000000; // 占昨比 6.47%
      return {
        auctionPrice: 1576.0,
        auctionChangePercent: 1.81,
        auctionVolume: Math.round(auctionAmount / (1576.0 * 100)),
        auctionAmount,
        yesterdayAmount,
        auctionUnmatchedHands: 1850,
        auctionVolumeRatio: 2.34,
        yesterdayPerformanceNote: '昨缩量回踩5日线企稳',
        consecutiveBoards: 0,
        yesterdayBoards: 0,
        isIntradayTouchedLimitUp: false,
        firstSealTime: null,
        dragonRole: 'CAPACITY_CORE',
        boardRuleType: 'MAIN_20',
        stockReturnT1: 6.85,
        stockReturnT2: 5.42,
        indexReturnT1: 0.82,
        indexReturnT2: 0.45,
        indexReturnToday: 1.05,
        cumDeviation10d: 18.6,
        abnormalCount10d: 0,
      };
    }
    default: {
      const yesterdayAmount = Math.max(1500000000, Math.round(amount * 1.18));
      const auctionChangePercent = Number((((cfg.open - cfg.prevClose) / cfg.prevClose) * 100).toFixed(2));
      const ratio = auctionChangePercent >= 1.5 ? 0.058 : 0.036;
      const auctionAmount = Math.round(yesterdayAmount * ratio);
      return {
        auctionPrice: cfg.open,
        auctionChangePercent,
        auctionVolume: Math.max(100, Math.round(auctionAmount / (cfg.open * 100))),
        auctionAmount,
        yesterdayAmount,
        auctionUnmatchedHands: auctionChangePercent >= 0 ? 1600 : -900,
        auctionVolumeRatio: Number((cfg.volumeRatio * 1.35).toFixed(2)),
        yesterdayPerformanceNote: auctionChangePercent >= 1.0 ? '昨良性换手洗盘' : '昨窄幅震荡整理',
        consecutiveBoards: 0,
        yesterdayBoards: cfg.symbol === '601899.SH' ? 1 : 0,
        isIntradayTouchedLimitUp: false,
        firstSealTime: null,
        dragonRole: cfg.marketCap >= 8000 ? 'CAPACITY_CORE' : 'FOLLOWER',
        boardRuleType,
        stockReturnT1: 4.6,
        stockReturnT2: 3.8,
        indexReturnT1: 0.75,
        indexReturnT2: 0.4,
        indexReturnToday: 1.05,
        cumDeviation10d: 16.2,
        abnormalCount10d: 0,
      };
    }
  }
}

export function createInitialQuotes(): Record<string, TickData> {
  const quotes: Record<string, TickData> = {};
  const now = Date.now();

  STOCK_SEED_CONFIGS.forEach((cfg, index) => {
    const limitUpPrice = Number((cfg.prevClose * (1 + cfg.limitRate)).toFixed(2));
    const limitDownPrice = Number((cfg.prevClose * (1 - cfg.limitRate)).toFixed(2));
    const change = Number((cfg.price - cfg.prevClose).toFixed(2));
    const changePercent = Number(((change / cfg.prevClose) * 100).toFixed(2));
    const amount = Math.round(cfg.volume * 100 * cfg.price);
    const amplitude = Number((((cfg.high - cfg.low) / cfg.prevClose) * 100).toFixed(2));
    const outerVolume = Math.round(cfg.volume * (change >= 0 ? 0.58 : 0.38));
    const innerVolume = cfg.volume - outerVolume;

    quotes[cfg.symbol] = {
      symbol: cfg.symbol,
      code: cfg.code,
      market: cfg.market,
      name: cfg.name,
      pinyin: cfg.pinyin,
      sector: cfg.sector,
      price: cfg.price,
      prevClose: cfg.prevClose,
      open: cfg.open,
      high: cfg.high,
      low: cfg.low,
      change,
      changePercent,
      volume: cfg.volume,
      amount,
      turnoverRate: cfg.turnoverRate,
      volumeRatio: cfg.volumeRatio,
      amplitude,
      peTtm: cfg.peTtm,
      pb: cfg.pb,
      marketCap: cfg.marketCap,
      floatMarketCap: cfg.floatMarketCap,
      outerVolume,
      innerVolume,
      limitUpPrice,
      limitDownPrice,
      phase: cfg.initialPhase,
      orderBook: buildOrderBookForPhase(cfg.price, cfg.initialPhase, limitUpPrice, limitDownPrice, index * 13),
      recentTrades: buildInitialTrades(cfg.price, cfg.initialPhase),
      ultraShort: buildUltraShortProfile(cfg, amount),
      updatedAt: now,
    };
  });

  return quotes;
}

export function createInitialIndices(): Record<string, MarketIndexQuote> {
  return {
    '000001.SH': {
      symbol: '000001.SH',
      name: '上证指数',
      price: 3342.86,
      prevClose: 3308.12,
      change: 34.74,
      changePercent: 1.05,
      volume: 4.82,
      amount: 6420.5,
      upCount: 1682,
      downCount: 512,
      flatCount: 84,
    },
    '399001.SZ': {
      symbol: '399001.SZ',
      name: '深证成指',
      price: 10785.42,
      prevClose: 10592.6,
      change: 192.82,
      changePercent: 1.82,
      volume: 6.15,
      amount: 8940.2,
      upCount: 2145,
      downCount: 640,
      flatCount: 95,
    },
    '399006.SZ': {
      symbol: '399006.SZ',
      name: '创业板指',
      price: 2268.15,
      prevClose: 2212.4,
      change: 55.75,
      changePercent: 2.52,
      volume: 2.46,
      amount: 4310.8,
      upCount: 1042,
      downCount: 280,
      flatCount: 32,
    },
    '000688.SH': {
      symbol: '000688.SH',
      name: '科创50',
      price: 1024.68,
      prevClose: 991.5,
      change: 33.18,
      changePercent: 3.35,
      volume: 0.96,
      amount: 1865.4,
      upCount: 468,
      downCount: 92,
      flatCount: 14,
    },
    '000300.SH': {
      symbol: '000300.SH',
      name: '沪深300',
      price: 3986.24,
      prevClose: 3934.1,
      change: 52.14,
      changePercent: 1.33,
      volume: 3.12,
      amount: 5120.0,
      upCount: 238,
      downCount: 56,
      flatCount: 6,
    },
  };
}

/**
 * 动态切换某只股票的盘口场景（正常连续竞价 / 涨停封板空卖档 / 跌停封板空买档 / 集合竞价部分空档）
 */
export function applyScenarioToQuote(quote: TickData, scenario: MarketScenario): TickData {
  const next = { ...quote };
  if (scenario === 'limit_up') {
    next.phase = 'LIMIT_UP';
    next.price = next.limitUpPrice;
    next.high = Math.max(next.high, next.limitUpPrice);
  } else if (scenario === 'limit_down') {
    next.phase = 'LIMIT_DOWN';
    next.price = next.limitDownPrice;
    next.low = Math.min(next.low, next.limitDownPrice);
  } else if (scenario === 'call_auction') {
    next.phase = 'CALL_AUCTION';
    next.price = Number((next.prevClose * 1.018).toFixed(2));
  } else {
    next.phase = 'TRADING';
    next.price = Number((next.prevClose * 1.022).toFixed(2));
  }

  next.change = Number((next.price - next.prevClose).toFixed(2));
  next.changePercent = Number(((next.change / next.prevClose) * 100).toFixed(2));
  next.orderBook = buildOrderBookForPhase(next.price, next.phase, next.limitUpPrice, next.limitDownPrice, 18);
  next.updatedAt = Date.now();
  return next;
}

/**
 * 确定性伪随机数生成器，保证每次生成的历史 K 线与分时图走势真实且稳定
 */
function seededRandom(seed: number): () => number {
  let s = seed % 2147483647;
  if (s <= 0) s += 2147483646;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

function hashSymbol(str: string): number {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return Math.abs(h);
}

/**
 * 生成指定股票与周期的历史 K 线序列（最后1根与当前最新价对齐）
 */
export function generateKLinesForSymbol(quote: TickData, period: ChartPeriod, count = 120): KLineBar[] {
  const rand = seededRandom(hashSymbol(`${quote.symbol}-${period}`));
  const bars: KLineBar[] = [];

  const volatility =
    period === '5m' ? 0.0045 : period === '15m' ? 0.0075 : period === '30m' ? 0.011 : period === '60m' ? 0.015 : period === '1W' ? 0.038 : period === '1M' ? 0.065 : 0.022;

  // 从历史价格向当前最新价反向推演，确保最后一根 K 线收盘价 == quote.price
  const closes: number[] = new Array(count);
  closes[count - 1] = quote.price;
  closes[count - 2] = quote.prevClose;

  for (let i = count - 3; i >= 0; i--) {
    const delta = (rand() - 0.488) * volatility;
    const prev = closes[i + 1] / (1 + delta);
    closes[i] = Math.max(1.5, Number(prev.toFixed(2)));
  }

  const baseTimeSec = Math.floor(Date.now() / 1000);
  const stepSec =
    period === '5m'
      ? 300
      : period === '15m'
      ? 900
      : period === '30m'
      ? 1800
      : period === '60m'
      ? 3600
      : period === '1W'
      ? 86400 * 7
      : period === '1M'
      ? 86400 * 30
      : 86400;

  for (let i = 0; i < count; i++) {
    const isLast = i === count - 1;
    const close = closes[i];
    const prevClose = i > 0 ? closes[i - 1] : close * 0.99;
    const open = isLast
      ? quote.open
      : Number((prevClose * (1 + (rand() - 0.5) * volatility * 0.65)).toFixed(2));
    const maxOC = Math.max(open, close);
    const minOC = Math.min(open, close);
    const high = isLast
      ? Math.max(quote.high, maxOC)
      : Number((maxOC * (1 + rand() * volatility * 0.65)).toFixed(2));
    const low = isLast
      ? Math.min(quote.low, minOC)
      : Number((minOC * (1 - rand() * volatility * 0.65)).toFixed(2));

    const volFactor = 0.55 + rand() * 1.1 + (Math.abs(close - open) / close) * 18;
    const volume = isLast ? quote.volume : Math.round((quote.volume * 0.85 * volFactor) / (period === '5m' ? 36 : period === '15m' ? 16 : period === '30m' ? 8 : period === '60m' ? 4 : 1));
    const amount = Math.round(volume * 100 * ((open + close + high + low) / 4));

    const ts = baseTimeSec - (count - 1 - i) * stepSec;
    const d = new Date(ts * 1000);
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    const hh = String(d.getHours()).padStart(2, '0');
    const min = String(d.getMinutes()).padStart(2, '0');

    const timeLabel = period === '5m' || period === '15m' || period === '30m' || period === '60m' ? `${mm}-${dd} ${hh}:${min}` : `${yyyy}-${mm}-${dd}`;

    bars.push({
      time: timeLabel,
      timestamp: ts,
      open,
      high,
      low,
      close,
      volume,
      amount,
      turnoverRate: Number((quote.turnoverRate * (0.6 + rand() * 0.8)).toFixed(2)),
    });
  }

  return bars;
}

/**
 * 生成 A 股标准日内分时图序列（09:30 - 11:30, 13:00 - 15:00，含均价线 VWAP）
 */
export function generateIntradayForSymbol(quote: TickData): IntradayPoint[] {
  const rand = seededRandom(hashSymbol(`${quote.symbol}-intraday`));
  const points: IntradayPoint[] = [];

  const timeSlots: string[] = [];
  // 上午盘 09:30 ~ 11:30 (121个点)
  for (let m = 9 * 60 + 30; m <= 11 * 60 + 30; m++) {
    const hh = String(Math.floor(m / 60)).padStart(2, '0');
    const mm = String(m % 60).padStart(2, '0');
    timeSlots.push(`${hh}:${mm}`);
  }
  // 下午盘 13:01 ~ 15:00 (120个点)
  for (let m = 13 * 60 + 1; m <= 15 * 60; m++) {
    const hh = String(Math.floor(m / 60)).padStart(2, '0');
    const mm = String(m % 60).padStart(2, '0');
    timeSlots.push(`${hh}:${mm}`);
  }

  const totalPoints = 200; // 当前交易进行到的分钟数
  const startPrice = quote.open;
  const endPrice = quote.price;

  let cumVolume = 0;
  let cumAmount = 0;
  let current = startPrice;

  for (let i = 0; i < totalPoints; i++) {
    const progress = i / (totalPoints - 1);
    const targetDrift = startPrice + (endPrice - startPrice) * progress;
    const noise = (rand() - 0.5) * quote.prevClose * 0.0035;
    current = i === totalPoints - 1 ? endPrice : Number((current * 0.72 + targetDrift * 0.28 + noise).toFixed(2));
    current = Math.min(quote.limitUpPrice, Math.max(quote.limitDownPrice, current));

    const minuteVol = Math.max(
      20,
      Math.round((quote.volume / totalPoints) * (i < 15 || i > totalPoints - 15 ? 1.8 : 0.5 + rand() * 1.1))
    );
    cumVolume += minuteVol;
    cumAmount += minuteVol * current;
    const avgPrice = Number((cumAmount / cumVolume).toFixed(2));
    const changePercent = Number((((current - quote.prevClose) / quote.prevClose) * 100).toFixed(2));

    points.push({
      time: timeSlots[i] ?? '14:55',
      timestamp: Date.now() - (totalPoints - i) * 60000,
      price: current,
      avgPrice,
      volume: minuteVol,
      changePercent,
    });
  }

  return points;
}
