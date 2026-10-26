import test from 'node:test';
import assert from 'node:assert/strict';
import {
  calculateOrderBookMetrics,
  calculateSMA,
  calculateEMA,
  calculateBOLL,
  calculateMACD,
  calculateKDJ,
  calculateRSI,
  filterAndSortStocks,
  formatPrice,
  formatVolumeHands,
  evaluatePriceAlertRule,
  formatAlertConditionLabel,
  buildAlertTriggerMessage,
} from './marketCalc';
import type { KLineBar, OrderBook5, PriceAlertRule, TickData } from '../types/market';

test('OrderBook5 正常五档盘口计算：委差、委比与卖五至卖一排序', () => {
  const orderBook: OrderBook5 = {
    bids: [
      { level: 1, price: 1500.0, volume: 300 },
      { level: 2, price: 1499.8, volume: 200 },
      { level: 3, price: 1499.5, volume: 150 },
      { level: 4, price: 1499.2, volume: 100 },
      { level: 5, price: 1499.0, volume: 50 },
    ],
    asks: [
      { level: 1, price: 1500.2, volume: 100 },
      { level: 2, price: 1500.5, volume: 100 },
      { level: 3, price: 1500.8, volume: 80 },
      { level: 4, price: 1501.0, volume: 70 },
      { level: 5, price: 1501.5, volume: 50 },
    ],
  };

  const metrics = calculateOrderBookMetrics(orderBook, 1490.0);

  // TotalBid = 300+200+150+100+50 = 800
  // TotalAsk = 100+100+80+70+50 = 400
  assert.equal(metrics.totalBidVolume, 800);
  assert.equal(metrics.totalAskVolume, 400);

  // 委差 = 800 - 400 = +400
  assert.equal(metrics.imbalanceVolume, 400);
  assert.equal(metrics.imbalanceVolumeText, '+400');

  // 委比 = (400 / 1200) * 100 = +33.33%
  assert.equal(metrics.imbalanceRatioText, '+33.33%');

  // 卖盘必须由卖五至卖一由高到低排列
  assert.deepEqual(
    metrics.asksTopToBottom.map((r) => r.label),
    ['卖五', '卖四', '卖三', '卖二', '卖一']
  );
  assert.equal(metrics.asksTopToBottom[0].priceText, '1501.50');
  assert.equal(metrics.asksTopToBottom[4].priceText, '1500.20');

  // 买盘必须由买一至买五排列
  assert.deepEqual(
    metrics.bidsTopToBottom.map((r) => r.label),
    ['买一', '买二', '买三', '买四', '买五']
  );
  // 最大挂单量 300（买一），深度条应为 100%
  assert.equal(metrics.bidsTopToBottom[0].depthPercent, 100);
});

test('OrderBook5 涨停封板空档保护：卖一至卖五全空优雅降级为 --', () => {
  const limitUpBook: OrderBook5 = {
    bids: [
      { level: 1, price: 11.0, volume: 95000 },
      { level: 2, price: 10.99, volume: 1200 },
      { level: 3, price: 10.98, volume: 800 },
      { level: 4, price: 10.97, volume: 600 },
      { level: 5, price: 10.96, volume: 400 },
    ],
    asks: [
      { level: 1, price: null, volume: null },
      { level: 2, price: null, volume: null },
      { level: 3, price: null, volume: null },
      { level: 4, price: null, volume: null },
      { level: 5, price: null, volume: null },
    ],
  };

  const metrics = calculateOrderBookMetrics(limitUpBook, 10.0);
  assert.equal(metrics.totalAskVolume, 0);
  assert.equal(metrics.imbalanceRatioText, '+100.00%');
  for (const askRow of metrics.asksTopToBottom) {
    assert.equal(askRow.priceText, '--');
    assert.equal(askRow.volumeText, '--');
    assert.equal(askRow.depthPercent, 0);
  }
});

test('OrderBook5 集合竞价全空盘口保护：不抛异常且委比委差降级为 --', () => {
  const emptyBook: OrderBook5 = {
    bids: [
      { level: 1, price: null, volume: null },
      { level: 2, price: null, volume: null },
      { level: 3, price: null, volume: null },
      { level: 4, price: null, volume: null },
      { level: 5, price: null, volume: null },
    ],
    asks: [
      { level: 1, price: null, volume: null },
      { level: 2, price: null, volume: null },
      { level: 3, price: null, volume: null },
      { level: 4, price: null, volume: null },
      { level: 5, price: null, volume: null },
    ],
  };

  const metrics = calculateOrderBookMetrics(emptyBook, 20.0);
  assert.equal(metrics.imbalanceVolume, null);
  assert.equal(metrics.imbalanceRatio, null);
  assert.equal(metrics.imbalanceVolumeText, '--');
  assert.equal(metrics.imbalanceRatioText, '--');
  assert.equal(metrics.bidPowerPercent, 50);
});

test('技术指标计算准确性：SMA, EMA, BOLL, MACD, KDJ, RSI', () => {
  const sampleBars: KLineBar[] = Array.from({ length: 30 }, (_, i) => ({
    time: `2026-09-${String(i + 1).padStart(2, '0')}`,
    timestamp: 1700000000 + i * 86400,
    open: 100 + i,
    high: 102 + i,
    low: 99 + i,
    close: 101 + i,
    volume: 10000 + i * 100,
    amount: 1000000 + i * 10000,
  }));

  const sma5 = calculateSMA(sampleBars, 5);
  assert.equal(sma5[3], null);
  // 第5根K线 (index 4): close 为 101, 102, 103, 104, 105 -> 均值 103
  assert.equal(sma5[4], 103);

  const ema5 = calculateEMA(sampleBars, 5);
  assert.equal(ema5.length, 30);
  assert.ok((ema5[29] ?? 0) > 125);

  const boll = calculateBOLL(sampleBars, 20, 2);
  assert.equal(boll[18].mid, null);
  assert.ok(boll[19].mid !== null && boll[19].upper! > boll[19].mid! && boll[19].lower! < boll[19].mid!);

  const macd = calculateMACD(sampleBars);
  assert.equal(macd.length, 30);
  assert.ok(macd[29].dif > 0);

  const kdj = calculateKDJ(sampleBars, 9);
  assert.equal(kdj.length, 30);
  assert.ok(kdj[29].k > 50);

  const rsi = calculateRSI(sampleBars, 14);
  assert.equal(rsi[13], null);
  assert.equal(rsi[14], 100); // 单边上涨序列 RSI = 100
});

test('自选股拼音首字母与代码过滤', () => {
  const mockStocks = [
    {
      symbol: '600519.SH',
      code: '600519',
      name: '贵州茅台',
      pinyin: 'gzmt',
      sector: '酿酒行业',
      price: 1580,
      changePercent: 2.15,
      phase: 'TRADING',
    },
    {
      symbol: '002594.SZ',
      code: '002594',
      name: '比亚迪',
      pinyin: 'byd',
      sector: '新能源车',
      price: 295,
      changePercent: 4.3,
      phase: 'TRADING',
    },
  ] as unknown as TickData[];

  const byPinyin = filterAndSortStocks(mockStocks, 'BYD', 'all', []);
  assert.equal(byPinyin.length, 1);
  assert.equal(byPinyin[0].code, '002594');

  const byCode = filterAndSortStocks(mockStocks, '6005', 'all', []);
  assert.equal(byCode.length, 1);
  assert.equal(byCode[0].name, '贵州茅台');

  assert.equal(formatPrice(null), '--');
  assert.equal(formatVolumeHands(125000), '12.50万');
});

test('价格与涨跌幅预警阈值计算与触发判定', () => {
  const sampleTick = {
    symbol: '600519.SH',
    code: '600519',
    name: '贵州茅台',
    price: 1585.0,
    prevClose: 1548.0,
    change: 37.0,
    changePercent: 2.39,
  } as unknown as TickData;

  const upRule: PriceAlertRule = {
    id: 'r-1',
    symbol: '600519.SH',
    stockName: '贵州茅台',
    condition: 'CHANGE_PCT_ABOVE',
    threshold: 2.0,
    enabled: true,
    triggered: false,
    createdAt: Date.now(),
  };

  assert.equal(evaluatePriceAlertRule(upRule, sampleTick), true);
  assert.equal(formatAlertConditionLabel('CHANGE_PCT_ABOVE', 2.0), '涨跌幅 ≥ +2.00%');
  assert.ok(buildAlertTriggerMessage(upRule, sampleTick).includes('贵州茅台 (600519.SH) 触发预警'));

  // 已触发或未启用的规则不应重复触发
  assert.equal(evaluatePriceAlertRule({ ...upRule, triggered: true }, sampleTick), false);
  assert.equal(evaluatePriceAlertRule({ ...upRule, enabled: false }, sampleTick), false);

  // 跌幅阈值未达到时不触发
  const downRule: PriceAlertRule = {
    ...upRule,
    id: 'r-2',
    condition: 'CHANGE_PCT_BELOW',
    threshold: -1.5,
  };
  assert.equal(evaluatePriceAlertRule(downRule, sampleTick), false);
});

import {
  analyzeAuctionVolumeRatio,
  analyzeMarketRegulatoryOverview,
  analyzeMarketThemeResonance,
  analyzeStockDragonTigerList,
  buildDragonTigerNetworkData,
  calculateAuctionRadar,
  calculateBoardLadderSummary,
  calculateThemeResonance,
  calculateRegulatoryDeviation,
  calculateVWDVR,
  getBrokerSeatActivityProfile,
  identifyBrokerSeatNature,
} from './ultraShortQuant';
import { createInitialQuotes, generateIntradayForSymbol } from '../data/seedMarket';

test('09:25 竞价雷达算子：识别一字巨封、超预期抢筹、爆量兑现与竞价核按钮及量比耦合分析', () => {
  const quotes = createInitialQuotes();

  // 1. 三六零 (601360.SH): 09:25 一字巨封顶板
  const q360 = calculateAuctionRadar(quotes['601360.SH']);
  assert.equal(q360.signal, 'LOCKED_LIMIT_UP');
  assert.equal(q360.signalLabel, '一字巨封顶板');
  assert.ok(q360.amountToYesterdayRatio > 5);

  // 2. 科大讯飞 (002230.SZ): 09:25 超预期抢筹 (占昨比 11.6%) + 倍量抢筹定性
  const qKdxf = calculateAuctionRadar(quotes['002230.SZ']);
  assert.equal(qKdxf.signal, 'SUPER_GRAB');
  assert.equal(qKdxf.signalLabel, '超预期抢筹');
  assert.equal(qKdxf.amountToYesterdayRatio, 11.6);
  const volKdxf = analyzeAuctionVolumeRatio(
    qKdxf.auctionVolumeRatio,
    qKdxf.amountToYesterdayRatio,
    qKdxf.auctionChangePercent
  );
  assert.equal(volKdxf.levelLabel, '倍量抢筹');
  assert.ok(volKdxf.intensityScore >= 80);

  // 3. 东方财富 (300059.SZ): 竞价金额占昨比 > 20% 爆量兑现预警 + 天量分歧定性
  const qDfcf = calculateAuctionRadar(quotes['300059.SZ']);
  assert.equal(qDfcf.signal, 'OVERHEAT_DUMP');
  assert.ok(qDfcf.amountToYesterdayRatio >= 21.0);
  const volDfcf = analyzeAuctionVolumeRatio(
    qDfcf.auctionVolumeRatio,
    qDfcf.amountToYesterdayRatio,
    qDfcf.auctionChangePercent
  );
  assert.equal(volDfcf.levelLabel, '天量分歧');

  // 4. 格力电器 (000651.SZ): 竞价深水核按钮
  const qGldq = calculateAuctionRadar(quotes['000651.SZ']);
  assert.equal(qGldq.signal, 'NUCLEAR_BUTTON');
  assert.ok(qGldq.unmatchedHands < -50000);

  // 5. 动态仿真参数覆盖校验：将常规股覆盖为竞价核按钮
  const simNuclear = calculateAuctionRadar(quotes['600519.SH'], {
    auctionChangePercent: -8.5,
    unmatchedHands: -42000,
  });
  assert.equal(simNuclear.signal, 'NUCLEAR_BUTTON');
});

test('涨跌停连板梯队引擎：今日涨停板分布对比、晋级空间断层监测与潜在退潮风险预警', () => {
  const quotes = Object.values(createInitialQuotes());
  const ladder = calculateBoardLadderSummary(quotes, 'live');

  // 最高空间板应为 6连板 三六零，次高板为 3连板 科大讯飞
  assert.equal(ladder.maxBoardHeight, 6);
  assert.equal(ladder.secondMaxBoardHeight, 3);
  assert.equal(ladder.spaceDragonSymbol, '601360.SH');
  assert.equal(ladder.spaceDragonName, '三六零');

  // 6板 与 3板 之间缺失 5连板、4连板，必须触发晋级空间断层与高危退潮风险预警
  assert.equal(ladder.hasLadderFault, true);
  assert.deepEqual(ladder.missingBoards, [5, 4]);
  assert.equal(ladder.maxFaultSpan, 2);
  assert.equal(ladder.topDragonIsolation, true);
  assert.equal(ladder.faultZones.length, 1);
  assert.equal(ladder.faultZones[0].fromBoard, 4);
  assert.equal(ladder.faultZones[0].toBoard, 5);
  assert.equal(ladder.faultZones[0].spanSize, 2);
  assert.equal(ladder.ebbTideRiskLevel, 'HIGH_EBB_RISK');
  assert.ok(ladder.ebbTideRiskScore >= 68);
  assert.ok(ladder.ebbTideWarningTitle.includes('高危退潮风险警报'));
  assert.equal(ladder.ebbTideRiskReasons.length, 3);

  // 自动对比今日涨停分布与昨日连板基数 (6板~1板 共 6 层)
  assert.equal(ladder.distributionComparison.length, 6);
  const row5 = ladder.distributionComparison.find((r) => r.boardCount === 5);
  const row4 = ladder.distributionComparison.find((r) => r.boardCount === 4);
  assert.ok(row5 && row5.isFaultLevel && row5.todaySealedCount === 0 && row5.yesterdayCandidateCount! > 0);
  assert.ok(row4 && row4.isFaultLevel && row4.todaySealedCount === 0 && row4.yesterdayCandidateCount! > 0);

  // 高危退潮沙盘 (缺 5/4/3 板，连续 3 层断层)
  const severeLadder = calculateBoardLadderSummary(quotes, 'severe_ebb');
  assert.deepEqual(severeLadder.missingBoards, [5, 4, 3]);
  assert.equal(severeLadder.maxFaultSpan, 3);
  assert.equal(severeLadder.secondMaxBoardHeight, 2);
  assert.ok(severeLadder.ebbTideRiskScore > ladder.ebbTideRiskScore);

  // 完整健康梯队沙盘 (1~6板无断层)
  const healthyLadder = calculateBoardLadderSummary(quotes, 'healthy_full');
  assert.equal(healthyLadder.hasLadderFault, false);
  assert.equal(healthyLadder.missingBoards.length, 0);
  assert.equal(healthyLadder.maxFaultSpan, 0);
  assert.equal(healthyLadder.ebbTideRiskLevel, 'LOW_HEALTHY');

  // 封板率与晋级率校验
  assert.ok(ladder.firstToSecondRate > 0);
  assert.ok(ladder.sealSuccessRate > 60 && ladder.sealSuccessRate < 100);
});

test('题材点面共振与先锋龙身位识别：点面共振得分、板块内涨停密度与先锋龙/中军龙联动', () => {
  const quotes = Object.values(createInitialQuotes());
  const themes = calculateThemeResonance(quotes);

  assert.ok(themes.length >= 5);
  // 人工智能板块含 6板三六零 + 3板科大讯飞及梯队涨停标杆，应排在主线强共振前列
  const aiTheme = themes.find((t) => t.sectorName === '人工智能');
  assert.ok(aiTheme);
  assert.equal(aiTheme.resonanceStatus, '主线强共振');
  assert.equal(aiTheme.pioneerDragon.symbol, '601360.SH');
  assert.ok(aiTheme.limitUpCount >= 5);
  assert.ok(aiTheme.limitUpDensityPercent >= 25);
  assert.equal(aiTheme.densityLevel, '涨停潮高密区');
  assert.equal(aiTheme.dragonLinkageStatus, '先锋中军强联动');
  assert.ok(aiTheme.dragonLinkageScore >= 75);
  assert.equal(aiTheme.attackRole, 'MAIN_ATTACK');
});

test('注册制法定复利异动监管逆推 (k ∈ {2, 3}) 与 10日100%特停锁死预警', () => {
  const quotes = createInitialQuotes();

  // 1. 科大讯飞 (主板 20% 偏离阈值，T-2=+9.96%, T-1=+10.01%)
  const regKdxf = calculateRegulatoryDeviation(quotes['002230.SZ']);
  assert.equal(regKdxf.ruleThresholdPercent, 20);
  // k=3 复利累计涨幅已极高，k=3 的触发临界价应显著低于 k=2 触发临界价
  assert.equal(regKdxf.bindingWindowK, 3);
  assert.ok(regKdxf.triggerPrice3Day < regKdxf.triggerPrice2Day);

  // 2. 中芯国际 (科创板 30% 偏离阈值)
  const regSmic = calculateRegulatoryDeviation(quotes['688981.SH']);
  assert.equal(regSmic.ruleThresholdPercent, 30);
  assert.ok(regSmic.effectiveTriggerPrice > 95);

  // 3. 三六零 (6连板，10日累计偏离 > 95%，触发高危特停锁死预警)
  const reg360 = calculateRegulatoryDeviation(quotes['601360.SH']);
  assert.equal(reg360.severeSuspensionLockWarning, true);
  assert.ok((reg360.remainingTo100Percent ?? 0) < 10);
});

test('真实成交量加权承接算子 (VW-DVR)：水上筹码锁定率与回撤买盘吸收率', () => {
  const quotes = createInitialQuotes();
  const qMoutai = quotes['600519.SH'];
  const intraday = generateIntradayForSymbol(qMoutai);

  const dvr = calculateVWDVR(qMoutai, intraday);
  assert.ok(dvr.vwap > 1500);
  assert.ok(dvr.vwDvrScore >= 5 && dvr.vwDvrScore <= 100);
  assert.ok(dvr.aboveVwapVolumeRatio >= 0 && dvr.aboveVwapVolumeRatio <= 100);

  // 跌停股格力电器应表现为承接衰竭
  const qGree = quotes['000651.SZ'];
  const dvrGree = calculateVWDVR(qGree, generateIntradayForSymbol(qGree));
  assert.equal(dvrGree.signal, 'WEAK_DISTRIBUTION');
  assert.ok(dvrGree.vwDvrScore < 48);
});

test('龙虎榜席位性质识别与资金博弈解析：自动识别游资常用席位、机构专用、量化大本营与散户合力', () => {
  // 1. 席位性质字典精准分类
  const zuoshou = identifyBrokerSeatNature('国泰君安证券股份有限公司南京太平南路证券营业部');
  assert.equal(zuoshou.nature, 'HOT_MONEY');
  assert.equal(zuoshou.natureLabel, '游资常用席位');
  assert.ok(zuoshou.seatTag.includes('作手新一'));

  const inst = identifyBrokerSeatNature('机构专用 (买二)');
  assert.equal(inst.nature, 'INSTITUTION');
  assert.equal(inst.natureLabel, '机构专用');

  const quant = identifyBrokerSeatNature('华泰证券股份有限公司总部');
  assert.equal(quant.nature, 'QUANT_CAMP');
  assert.equal(quant.natureLabel, '量化大本营');

  const retail = identifyBrokerSeatNature('东方财富证券股份有限公司拉萨团结路第二证券营业部');
  assert.equal(retail.nature, 'RETAIL_CAMP');
  assert.equal(retail.natureLabel, '散户大本营');

  const quotes = createInitialQuotes();

  // 2. 科大讯飞 (002230.SZ)：游资(章盟主/北京帮) + 机构专用/深股通 共振主封
  const dtKdxf = analyzeStockDragonTigerList(quotes['002230.SZ'], 'live');
  assert.equal(dtKdxf.buySeats.length, 5);
  assert.equal(dtKdxf.sellSeats.length, 5);
  assert.equal(dtKdxf.synergyVerdict, 'HOT_INST_RESONANCE');
  assert.ok(dtKdxf.totalNetAmount > 0);
  assert.ok(dtKdxf.nextDayPremiumScore >= 85);

  // 3. 三六零 (601360.SH)：6连板顶级游资豪华锁仓接力三日榜
  const dt360 = analyzeStockDragonTigerList(quotes['601360.SH'], 'live');
  assert.equal(dt360.boardType, '3D');
  assert.equal(dt360.dominantCamp, 'HOT_MONEY');
  assert.equal(dt360.synergyVerdict, 'TOP_HOT_LOCK');

  // 4. 东方财富 (300059.SZ)：量化大本营扎堆预警
  const dtDfcf = analyzeStockDragonTigerList(quotes['300059.SZ'], 'quant_crowded');
  assert.equal(dtDfcf.dominantCamp, 'QUANT_CAMP');
  assert.equal(dtDfcf.synergyVerdict, 'QUANT_CROWDED_RISK');

  // 5. 拉萨散户接盘预警沙盘
  const dtRetail = analyzeStockDragonTigerList(quotes['600519.SH'], 'retail_takeover');
  assert.equal(dtRetail.dominantCamp, 'RETAIL_CAMP');
  assert.ok(
    dtRetail.synergyVerdict === 'RETAIL_TAKEOVER_WARN' ||
      dtRetail.synergyVerdict === 'MAIN_FORCE_EXIT'
  );
});

test('D3.js 龙虎榜游资席位关联网络图与席位活跃度画像：连线粗细严格正比于买入金额，节点含完整活跃度指标', () => {
  const quotes = createInitialQuotes();
  const dt360 = analyzeStockDragonTigerList(quotes['601360.SH'], 'live');

  // 1. 构建完整关联网络图数据
  const net = buildDragonTigerNetworkData(dt360, {
    onlyHotMoney: false,
    includeAllyStocks: true,
  });

  const targetNodes = net.nodes.filter((n) => n.nodeType === 'TARGET_STOCK');
  const seatNodes = net.nodes.filter((n) => n.nodeType === 'BROKER_SEAT');
  const allyNodes = net.nodes.filter((n) => n.nodeType === 'ALLY_STOCK');

  assert.equal(targetNodes.length, 1);
  assert.equal(targetNodes[0].label, '三六零');
  assert.equal(seatNodes.length, 10);
  assert.ok(allyNodes.length >= 2);
  assert.equal(net.hotMoneySeatCount, 6);

  // 2. 验证一级连线粗细 (strokeWidth) 与买入金额 (buyAmount) 单调正相关
  const primaryLinks = net.links.filter((l) => l.linkType !== 'CO_APPEAR_STOCK');
  assert.equal(primaryLinks.length, 10);

  for (let i = 0; i < primaryLinks.length; i++) {
    for (let j = 0; j < primaryLinks.length; j++) {
      if (primaryLinks[i].buyAmount > primaryLinks[j].buyAmount) {
        assert.ok(
          primaryLinks[i].strokeWidth >= primaryLinks[j].strokeWidth,
          `买额更高的连线 (${primaryLinks[i].buyAmount}) 粗细 (${primaryLinks[i].strokeWidth}) 应不小于买额较低连线 (${primaryLinks[j].buyAmount}, ${primaryLinks[j].strokeWidth})`
        );
      }
    }
  }

  // 最大买入席位（买1 作手新一）连线粗细应达到上限 9.5px，最小买入席位应为下限 2.0px
  const maxLink = primaryLinks.reduce((a, b) => (a.buyAmount >= b.buyAmount ? a : b));
  const minLink = primaryLinks.reduce((a, b) => (a.buyAmount <= b.buyAmount ? a : b));
  assert.equal(maxLink.strokeWidth, 9.5);
  assert.equal(minLink.strokeWidth, 2.0);

  // 3. 验证『仅游资大佬席位』筛选模式
  const hotNet = buildDragonTigerNetworkData(dt360, {
    onlyHotMoney: true,
    includeAllyStocks: false,
  });
  const hotSeatNodes = hotNet.nodes.filter((n) => n.nodeType === 'BROKER_SEAT');
  assert.equal(hotSeatNodes.length, 6);
  assert.ok(hotSeatNodes.every((n) => n.nature === 'HOT_MONEY'));

  // 4. 验证点击节点展示的『席位活跃度画像』数据完整性
  const zuoshouProfile = getBrokerSeatActivityProfile(
    '国泰君安证券股份有限公司南京太平南路证券营业部',
    dt360.buySeats[0],
    dt360.symbol,
    dt360.name,
    dt360.sector
  );
  assert.equal(zuoshouProfile.seatTag, '顶级游资 · 作手新一');
  assert.equal(zuoshouProfile.activityScore, 96);
  assert.equal(zuoshouProfile.appearances30d, 44);
  assert.ok(zuoshouProfile.totalCapital30d > 40_0000_0000);
  assert.ok(zuoshouProfile.nextDayAvgPremiumPercent > 4.0);
  assert.ok(zuoshouProfile.sealWinRatePercent > 75);
  assert.equal(zuoshouProfile.monthlyTrend.length, 4);
  assert.ok(zuoshouProfile.recentBattles.length >= 3);
});

test('板块/题材共振监测与主流资金进攻方向识别：涨停密度、龙头联动与沙盘推演对比', () => {
  const quotes = Object.values(createInitialQuotes());

  // 1. 实盘题材共振全景分析
  const liveOverview = analyzeMarketThemeResonance(quotes, 'live');
  assert.ok(liveOverview.themes.length >= 8);
  assert.ok(liveOverview.mainstreamAttackSectors.includes('人工智能'));
  assert.ok(liveOverview.mainstreamAttackSectors.includes('半导体'));
  assert.ok(liveOverview.retreatSectors.includes('家用电器'));
  assert.ok(liveOverview.marketResonanceScore >= 70);
  assert.ok(liveOverview.mainstreamConcentrationPercent >= 30);
  assert.ok(liveOverview.totalMarketLimitUpCount >= 12);

  // 验证全市场进攻火力权重百分比总和接近 100%
  const sumShare = liveOverview.themes.reduce(
    (acc, t) => acc + t.capitalAttackSharePercent,
    0
  );
  assert.ok(Math.abs(sumShare - 100) <= 1.0);

  // 2. AI+算力双主线爆发沙盘：人工智能与半导体的涨停密度和龙头联动分应进一步提升
  const aiBurstOverview = analyzeMarketThemeResonance(quotes, 'ai_chip_mainstream');
  const aiLive = liveOverview.themes.find((t) => t.sectorName === '人工智能')!;
  const aiBurst = aiBurstOverview.themes.find((t) => t.sectorName === '人工智能')!;
  assert.ok(aiBurst.limitUpDensityPercent >= aiLive.limitUpDensityPercent);
  assert.ok(aiBurst.heatWeight >= aiLive.heatWeight);

  // 3. 高低切轮动分化沙盘：电池储能与新能源车的涨停密度和进攻权重应显著上升
  const rotationOverview = analyzeMarketThemeResonance(quotes, 'rotation_divergence');
  const storageLive = liveOverview.themes.find((t) => t.sectorName === '电池储能')!;
  const storageRot = rotationOverview.themes.find((t) => t.sectorName === '电池储能')!;
  assert.ok(storageRot.limitUpDensityPercent >= storageLive.limitUpDensityPercent);
  assert.ok(storageRot.resonanceScore >= storageLive.resonanceScore);
});

test('监管异动监测模块：2/3日涨跌幅实时计算、法定异动窗口逆推与红黄绿三色信号灯预警', () => {
  const quotesMap = createInitialQuotes();
  const quotes = Object.values(quotesMap);

  const overview = analyzeMarketRegulatoryOverview(quotes);
  assert.equal(overview.items.length, quotes.length);
  assert.equal(
    overview.redLightCount + overview.yellowLightCount + overview.greenLightCount,
    quotes.length
  );
  assert.ok(overview.redLightCount >= 1);
  assert.ok(overview.yellowLightCount >= 1);
  assert.ok(overview.greenLightCount >= 1);

  // 1. 三六零 (601360.SH): 6连板空间龙，10日累计偏离 > 95% 且近10日已3次异动 -> 红灯预警
  const r360 = calculateRegulatoryDeviation(quotesMap['601360.SH']);
  assert.equal(r360.alertLight, 'RED');
  assert.equal(r360.alertLightLabel, '红灯 · 特停/触线高危');
  assert.equal(r360.severeSuspensionLockWarning, true);
  assert.ok(r360.stockCumReturn2DayPercent > 20);
  assert.ok(r360.stockCumReturn3DayPercent > 30);

  // 2. 科大讯飞 (002230.SZ): T-2=+9.96%, T-1=+10.01%, 今日高开 -> 3日窗口占用极高，应触发红灯或黄灯压线预警
  const rKdxf = calculateRegulatoryDeviation(quotesMap['002230.SZ']);
  assert.ok(rKdxf.alertLight === 'RED' || rKdxf.alertLight === 'YELLOW');
  assert.equal(rKdxf.bindingWindowK, 3);
  assert.ok(rKdxf.windowSaturation3DayPercent >= 85);

  // 3. 招商银行 (600036.SH): 温和波动大盘股 -> 绿灯安全区间
  const rCmb = calculateRegulatoryDeviation(quotesMap['600036.SH']);
  assert.equal(rCmb.alertLight, 'GREEN');
  assert.equal(rCmb.alertLightLabel, '绿灯 · 安全运行区间');
  assert.equal(rCmb.severeSuspensionLockWarning, false);
});
