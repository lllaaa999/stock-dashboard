import type {
  AlertConditionType,
  FormattedOrderBookRow,
  KLineBar,
  OrderBook5,
  OrderBookLevel,
  OrderBookMetrics,
  PriceAlertRule,
  PriceDirection,
  TickData,
} from '../types/market';

const LEVEL_CN_NUMS: Record<1 | 2 | 3 | 4 | 5, string> = {
  1: '一',
  2: '二',
  3: '三',
  4: '四',
  5: '五',
};

/**
 * 判断价格相对于昨收价的涨跌平方向
 */
export function getPriceDirection(price: number | null | undefined, prevClose: number): PriceDirection {
  if (price === null || price === undefined || !Number.isFinite(price) || price <= 0) {
    return 'FLAT';
  }
  const diff = price - prevClose;
  if (Math.abs(diff) < 1e-4) return 'FLAT';
  return diff > 0 ? 'UP' : 'DOWN';
}

/**
 * 获取中国 A 股标准色彩类名（红涨 #F6465D、绿跌 #0ECB81、灰平 #787b86）
 */
export function getDirectionColorClass(direction: PriceDirection): string {
  switch (direction) {
    case 'UP':
      return 'text-[#F6465D]';
    case 'DOWN':
      return 'text-[#0ECB81]';
    default:
      return 'text-[#787b86]';
  }
}

/**
 * 根据数值正负返回涨跌颜色类名
 */
export function getSignedColorClass(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value) || Math.abs(value) < 1e-4) {
    return 'text-[#787b86]';
  }
  return value > 0 ? 'text-[#F6465D]' : 'text-[#0ECB81]';
}

/**
 * 格式化价格，空档或非法数值优雅降级为 '--'
 */
/** 可空数值格式化：未知一律显示 "—"，绝不把 null 渲染成 "null%" */
export function formatNullable(
  v: number | null | undefined,
  decimals = 2,
  suffix = ''
): string {
  return typeof v === 'number' && Number.isFinite(v) ? `${v.toFixed(decimals)}${suffix}` : '—';
}

export function formatPrice(price: number | null | undefined, decimals = 2): string {
  if (price === null || price === undefined || !Number.isFinite(price) || price <= 0) {
    return '--';
  }
  return price.toFixed(decimals);
}

/**
 * 格式化涨跌幅百分比
 */
export function formatSignedPercent(val: number | null | undefined, decimals = 2): string {
  if (val === null || val === undefined || !Number.isFinite(val)) {
    return '--';
  }
  const sign = val > 0 ? '+' : '';
  return `${sign}${val.toFixed(decimals)}%`;
}

/**
 * 格式化涨跌额
 */
export function formatSignedChange(val: number | null | undefined, decimals = 2): string {
  if (val === null || val === undefined || !Number.isFinite(val)) {
    return '--';
  }
  const sign = val > 0 ? '+' : '';
  return `${sign}${val.toFixed(decimals)}`;
}

/**
 * 格式化挂单手数或成交量（支持万手转换）
 */
export function formatVolumeHands(volume: number | null | undefined): string {
  if (volume === null || volume === undefined || !Number.isFinite(volume) || volume <= 0) {
    return '--';
  }
  if (volume >= 100000) {
    return `${(volume / 10000).toFixed(2)}万`;
  }
  return Math.round(volume).toLocaleString('en-US');
}

/**
 * 格式化成交金额（自动转换为万 / 亿）
 */
export function formatAmountCN(amount: number | null | undefined): string {
  if (amount === null || amount === undefined || !Number.isFinite(amount) || amount <= 0) {
    return '--';
  }
  if (amount >= 1e8) {
    return `${(amount / 1e8).toFixed(2)}亿`;
  }
  if (amount >= 1e4) {
    return `${(amount / 1e4).toFixed(1)}万`;
  }
  return amount.toFixed(0);
}

/**
 * 核心盘口衍生计算：基于 Level-1 五档盘口计算【委差】、【委比】及各档深度条比例
 *
 * 计算公式：
 * 1. TotalBid = ∑(买一 ~ 买五 有效挂单量)
 * 2. TotalAsk = ∑(卖一 ~ 卖五 有效挂单量)
 * 3. 委差 (Imbalance Volume) = TotalBid - TotalAsk
 * 4. 委比 (Imbalance Ratio) = ((TotalBid - TotalAsk) / (TotalBid + TotalAsk)) * 100%
 *
 * 空档保护：
 * - 涨停时：卖一至卖五全空（price/volume 为 null 或 0），此时 TotalAsk = 0，委比 = +100.00%，卖盘各档优雅显示为 '--'
 * - 跌停时：买一至买五全空，此时 TotalBid = 0，委比 = -100.00%，买盘各档优雅显示为 '--'
 * - 集合竞价无挂单时：TotalBid + TotalAsk = 0，委差与委比均降级为 '--'，防止除以 0 出现 NaN
 */
export function calculateOrderBookMetrics(
  orderBook: OrderBook5 | null | undefined,
  prevClose: number
): OrderBookMetrics {
  const safeBids: OrderBookLevel[] = orderBook?.bids ?? [
    { level: 1, price: null, volume: null },
    { level: 2, price: null, volume: null },
    { level: 3, price: null, volume: null },
    { level: 4, price: null, volume: null },
    { level: 5, price: null, volume: null },
  ];
  const safeAsks: OrderBookLevel[] = orderBook?.asks ?? [
    { level: 1, price: null, volume: null },
    { level: 2, price: null, volume: null },
    { level: 3, price: null, volume: null },
    { level: 4, price: null, volume: null },
    { level: 5, price: null, volume: null },
  ];

  let totalBidVolume = 0;
  let totalAskVolume = 0;
  let maxSingleVolume = 0;

  for (const b of safeBids) {
    const vol = b && b.price !== null && b.price > 0 && b.volume !== null && b.volume > 0 ? b.volume : 0;
    totalBidVolume += vol;
    if (vol > maxSingleVolume) maxSingleVolume = vol;
  }

  for (const a of safeAsks) {
    const vol = a && a.price !== null && a.price > 0 && a.volume !== null && a.volume > 0 ? a.volume : 0;
    totalAskVolume += vol;
    if (vol > maxSingleVolume) maxSingleVolume = vol;
  }

  const totalVolume = totalBidVolume + totalAskVolume;

  let imbalanceVolume: number | null = null;
  let imbalanceRatio: number | null = null;
  let imbalanceVolumeText = '--';
  let imbalanceRatioText = '--';
  let bidPowerPercent = 50;

  if (totalVolume > 0) {
    imbalanceVolume = totalBidVolume - totalAskVolume;
    imbalanceRatio = (imbalanceVolume / totalVolume) * 100;
    const sign = imbalanceVolume > 0 ? '+' : '';
    imbalanceVolumeText = `${sign}${Math.round(imbalanceVolume).toLocaleString('en-US')}`;
    const ratioSign = imbalanceRatio > 0 ? '+' : '';
    imbalanceRatioText = `${ratioSign}${imbalanceRatio.toFixed(2)}%`;
    bidPowerPercent = Math.max(0, Math.min(100, (totalBidVolume / totalVolume) * 100));
  }

  const formatRow = (item: OrderBookLevel, side: 'ask' | 'bid'): FormattedOrderBookRow => {
    const isValid =
      item !== undefined &&
      item !== null &&
      item.price !== null &&
      Number.isFinite(item.price) &&
      item.price > 0 &&
      item.volume !== null &&
      Number.isFinite(item.volume) &&
      item.volume > 0;

    const rawPrice = isValid ? item.price : null;
    const rawVolume = isValid ? item.volume : null;
    const depthPercent =
      isValid && maxSingleVolume > 0 && rawVolume !== null
        ? Math.min(100, Math.max(4, (rawVolume / maxSingleVolume) * 100))
        : 0;

    const lvl = (item?.level ?? 1) as 1 | 2 | 3 | 4 | 5;
    return {
      side,
      level: lvl,
      label: `${side === 'ask' ? '卖' : '买'}${LEVEL_CN_NUMS[lvl]}`,
      rawPrice,
      rawVolume,
      priceText: isValid ? formatPrice(rawPrice) : '--',
      volumeText: isValid && rawVolume !== null ? Math.round(rawVolume).toLocaleString('en-US') : '--',
      depthPercent,
      priceDirection: getPriceDirection(rawPrice, prevClose),
    };
  };

  // 卖盘必须由卖五至卖一从高到低排列 (Ask 5 -> Ask 4 -> Ask 3 -> Ask 2 -> Ask 1)
  const asksSortedLevels = [...safeAsks].sort((a, b) => b.level - a.level);
  const asksTopToBottom = asksSortedLevels.map((a) => formatRow(a, 'ask'));

  // 买盘由买一至买五从高到低排列 (Bid 1 -> Bid 2 -> Bid 3 -> Bid 4 -> Bid 5)
  const bidsSortedLevels = [...safeBids].sort((a, b) => a.level - b.level);
  const bidsTopToBottom = bidsSortedLevels.map((b) => formatRow(b, 'bid'));

  return {
    totalBidVolume,
    totalAskVolume,
    imbalanceVolume,
    imbalanceRatio,
    imbalanceVolumeText,
    imbalanceRatioText,
    bidPowerPercent,
    asksTopToBottom,
    bidsTopToBottom,
  };
}

/**
 * 简单移动平均线 (SMA) 计算
 */
export function calculateSMA(bars: KLineBar[], period: number): (number | null)[] {
  const result: (number | null)[] = new Array(bars.length).fill(null);
  if (period <= 0 || bars.length < period) return result;

  let sum = 0;
  for (let i = 0; i < bars.length; i++) {
    sum += bars[i].close;
    if (i >= period) {
      sum -= bars[i - period].close;
    }
    if (i >= period - 1) {
      result[i] = Number((sum / period).toFixed(2));
    }
  }
  return result;
}

/**
 * 指数移动平均线 (EMA) 计算
 */
export function calculateEMA(bars: KLineBar[], period: number): (number | null)[] {
  const result: (number | null)[] = new Array(bars.length).fill(null);
  if (period <= 0 || bars.length === 0) return result;

  const k = 2 / (period + 1);
  let ema = bars[0].close;
  result[0] = Number(ema.toFixed(2));

  for (let i = 1; i < bars.length; i++) {
    ema = bars[i].close * k + ema * (1 - k);
    result[i] = Number(ema.toFixed(2));
  }
  return result;
}

/**
 * 布林带 (BOLL) 计算：中轨 MA(20)，上下轨 ±2 倍标准差
 */
export interface BollPoint {
  mid: number | null;
  upper: number | null;
  lower: number | null;
}

export function calculateBOLL(bars: KLineBar[], period = 20, multiplier = 2): BollPoint[] {
  const sma = calculateSMA(bars, period);
  return bars.map((_, idx) => {
    const mid = sma[idx];
    if (mid === null || idx < period - 1) {
      return { mid: null, upper: null, lower: null };
    }
    let varianceSum = 0;
    for (let j = idx - period + 1; j <= idx; j++) {
      const diff = bars[j].close - mid;
      varianceSum += diff * diff;
    }
    const stdDev = Math.sqrt(varianceSum / period);
    return {
      mid: Number(mid.toFixed(2)),
      upper: Number((mid + multiplier * stdDev).toFixed(2)),
      lower: Number((mid - multiplier * stdDev).toFixed(2)),
    };
  });
}

/**
 * MACD 指标计算 (12, 26, 9)
 */
export interface MacdPoint {
  dif: number;
  dea: number;
  hist: number;
}

export function calculateMACD(bars: KLineBar[], fast = 12, slow = 26, signal = 9): MacdPoint[] {
  if (bars.length === 0) return [];
  const kFast = 2 / (fast + 1);
  const kSlow = 2 / (slow + 1);
  const kSignal = 2 / (signal + 1);

  let emaFast = bars[0].close;
  let emaSlow = bars[0].close;
  let dea = 0;

  return bars.map((bar, i) => {
    if (i > 0) {
      emaFast = bar.close * kFast + emaFast * (1 - kFast);
      emaSlow = bar.close * kSlow + emaSlow * (1 - kSlow);
    }
    const dif = emaFast - emaSlow;
    dea = i === 0 ? dif : dif * kSignal + dea * (1 - kSignal);
    const hist = (dif - dea) * 2;
    return {
      dif: Number(dif.toFixed(3)),
      dea: Number(dea.toFixed(3)),
      hist: Number(hist.toFixed(3)),
    };
  });
}

/**
 * KDJ 随机指标计算 (9, 3, 3)
 */
export interface KdjPoint {
  k: number;
  d: number;
  j: number;
}

export function calculateKDJ(bars: KLineBar[], period = 9): KdjPoint[] {
  if (bars.length === 0) return [];
  let k = 50;
  let d = 50;

  return bars.map((bar, idx) => {
    const start = Math.max(0, idx - period + 1);
    let highest = -Infinity;
    let lowest = Infinity;
    for (let i = start; i <= idx; i++) {
      if (bars[i].high > highest) highest = bars[i].high;
      if (bars[i].low < lowest) lowest = bars[i].low;
    }
    const range = highest - lowest;
    const rsv = range < 1e-6 ? 50 : ((bar.close - lowest) / range) * 100;
    k = (2 / 3) * k + (1 / 3) * rsv;
    d = (2 / 3) * d + (1 / 3) * k;
    const j = 3 * k - 2 * d;
    return {
      k: Number(k.toFixed(2)),
      d: Number(d.toFixed(2)),
      j: Number(j.toFixed(2)),
    };
  });
}

/**
 * RSI 相对强弱指标计算
 */
export function calculateRSI(bars: KLineBar[], period = 14): (number | null)[] {
  const result: (number | null)[] = new Array(bars.length).fill(null);
  if (bars.length <= period) return result;

  let avgGain = 0;
  let avgLoss = 0;

  for (let i = 1; i <= period; i++) {
    const diff = bars[i].close - bars[i - 1].close;
    if (diff >= 0) avgGain += diff;
    else avgLoss -= diff;
  }
  avgGain /= period;
  avgLoss /= period;

  result[period] = avgLoss === 0 ? 100 : Number((100 - 100 / (1 + avgGain / avgLoss)).toFixed(2));

  for (let i = period + 1; i < bars.length; i++) {
    const diff = bars[i].close - bars[i - 1].close;
    const gain = diff > 0 ? diff : 0;
    const loss = diff < 0 ? -diff : 0;
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
    result[i] = avgLoss === 0 ? 100 : Number((100 - 100 / (1 + avgGain / avgLoss)).toFixed(2));
  }
  return result;
}

/**
 * 自选股列表检索与排序（支持股票代码、中文名称、拼音首字母过滤）
 */
export function filterAndSortStocks(
  stocks: TickData[],
  query: string,
  category: 'all' | 'watchlist' | 'special',
  watchlistSymbols: string[],
  sortBy: 'default' | 'price' | 'changePercent' = 'default',
  sortDir: 'asc' | 'desc' = 'desc'
): TickData[] {
  const q = query.trim().toLowerCase();
  const watchSet = new Set(watchlistSymbols);

  const filtered = stocks.filter((item) => {
    if (category === 'watchlist' && !watchSet.has(item.symbol)) {
      return false;
    }
    if (category === 'special' && item.phase === 'TRADING') {
      return false;
    }
    if (!q) return true;
    return (
      item.code.toLowerCase().includes(q) ||
      item.symbol.toLowerCase().includes(q) ||
      item.name.toLowerCase().includes(q) ||
      item.pinyin.toLowerCase().includes(q) ||
      item.sector.toLowerCase().includes(q)
    );
  });

  if (sortBy === 'default') {
    return filtered;
  }

  return [...filtered].sort((a, b) => {
    const valA = sortBy === 'price' ? a.price : a.changePercent;
    const valB = sortBy === 'price' ? b.price : b.changePercent;
    return sortDir === 'asc' ? valA - valB : valB - valA;
  });
}

/**
 * 校验单条价格/涨跌幅预警规则是否被当前实时 Tick 行情触发
 */
export function evaluatePriceAlertRule(rule: PriceAlertRule, tick: TickData): boolean {
  if (!rule.enabled || rule.triggered || rule.symbol !== tick.symbol) {
    return false;
  }
  if (!Number.isFinite(rule.threshold)) {
    return false;
  }

  switch (rule.condition) {
    case 'CHANGE_PCT_ABOVE':
      return tick.changePercent >= rule.threshold;
    case 'CHANGE_PCT_BELOW':
      return tick.changePercent <= rule.threshold;
    case 'PRICE_ABOVE':
      return tick.price >= rule.threshold;
    case 'PRICE_BELOW':
      return tick.price <= rule.threshold;
    default:
      return false;
  }
}

/**
 * 格式化预警条件为可读中文描述
 */
export function formatAlertConditionLabel(
  condition: AlertConditionType,
  threshold: number
): string {
  switch (condition) {
    case 'CHANGE_PCT_ABOVE':
      return `涨跌幅 ≥ ${threshold > 0 ? '+' : ''}${threshold.toFixed(2)}%`;
    case 'CHANGE_PCT_BELOW':
      return `涨跌幅 ≤ ${threshold > 0 ? '+' : ''}${threshold.toFixed(2)}%`;
    case 'PRICE_ABOVE':
      return `最新价 ≥ ${threshold.toFixed(2)}元`;
    case 'PRICE_BELOW':
      return `最新价 ≤ ${threshold.toFixed(2)}元`;
  }
}

/**
 * 构建触发预警时的通知正文文案
 */
export function buildAlertTriggerMessage(rule: PriceAlertRule, tick: TickData): string {
  const condText = formatAlertConditionLabel(rule.condition, rule.threshold);
  return `${tick.name} (${tick.symbol}) 触发预警 [${condText}]，当前现价 ${formatPrice(
    tick.price
  )} 元 (${formatSignedPercent(tick.changePercent)})`;
}

