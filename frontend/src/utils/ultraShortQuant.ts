import type {
  AuctionRadarMetrics,
  AuctionSignalType,
  BoardLadderSummary,
  BoardTierGroup,
  DragonRoleTag,
  DragonTigerAnalysis,
  DragonTigerCampSummary,
  DragonTigerGraphLink,
  DragonTigerGraphNode,
  DragonTigerNetworkData,
  DragonTigerPresetMode,
  DragonTigerSeatActivityProfile,
  DragonTigerSeatBattleRecord,
  DragonTigerSeatItem,
  DragonTigerSeatNature,
  EbbTideRiskLevel,
  IntradayPoint,
  LadderDistributionRow,
  LadderFaultZone,
  RegulatoryAlertLight,
  RegulatoryDeviationResult,
  RegulatoryHistory,
  RegulatoryMonitorOverview,
  ThemeAttackRole,
  ThemeResonanceItem,
  ThemeResonanceOverview,
  ThemeResonanceScenarioPreset,
  TickData,
  VWDVRResult,
} from '../types/market';

export function getDragonRoleLabel(role: DragonRoleTag): string {
  switch (role) {
    case 'SPACE_DRAGON':
      return '空间总龙';
    case 'PIONEER_DRAGON':
      return '日内先锋龙';
    case 'CAPACITY_CORE':
      return '容量中军龙';
    case 'TURNOVER_DRAGON':
      return '换手卡位龙';
    default:
      return '套利跟风';
  }
}

export interface AuctionRadarOverride {
  auctionChangePercent?: number;
  auctionAmount?: number;
  yesterdayAmount?: number;
  auctionVolumeRatio?: number;
  unmatchedHands?: number;
}

export interface VolumeRatioAnalysis {
  levelLabel: '缩量冷清' | '温和常态' | '放量异动' | '倍量抢筹' | '天量分歧';
  intensityScore: number; // 0 ~ 100
  description: string;
}

/**
 * 09:25 竞价量比与金额占比耦合分析算子
 */
export function analyzeAuctionVolumeRatio(
  auctionVolumeRatio: number,
  amountToYesterdayRatio: number,
  auctionChangePercent: number
): VolumeRatioAnalysis {
  const intensityScore = Number(
    Math.min(
      100,
      Math.max(5, auctionVolumeRatio * 10.5 + amountToYesterdayRatio * 2.4)
    ).toFixed(1)
  );

  if (amountToYesterdayRatio >= 20.0 || auctionVolumeRatio >= 7.0) {
    return {
      levelLabel: '天量分歧',
      intensityScore,
      description:
        auctionChangePercent >= 7.5
          ? '竞价天量顶格换手，需确认 09:30 开盘后能否秒板锁筹，防巨量炸板'
          : '竞价量比与占昨比双高但涨幅滞涨，潜伏获利盘集中出逃风险极高',
    };
  }
  if (auctionVolumeRatio >= 3.0 && amountToYesterdayRatio >= 6.0 && auctionChangePercent >= 2.5) {
    return {
      levelLabel: '倍量抢筹',
      intensityScore,
      description: '竞价量比 > 3.0x 且占昨比落入 6%~16% 黄金攻击区，典型游资主封点火信号',
    };
  }
  if (auctionVolumeRatio >= 2.0 || amountToYesterdayRatio >= 4.5) {
    return {
      levelLabel: '放量异动',
      intensityScore,
      description:
        auctionChangePercent >= 0
          ? '早盘集合竞价资金活跃度显著抬升，存在主动承接买盘'
          : '早盘放量低开，空头抛压在集合竞价阶段集中宣泄',
    };
  }
  if (auctionVolumeRatio >= 1.0) {
    return {
      levelLabel: '温和常态',
      intensityScore,
      description: '集合竞价量能平稳，筹码结构稳定，跟随板块日内轮动',
    };
  }
  return {
    levelLabel: '缩量冷清',
    intensityScore,
    description: '竞价交投清淡，缺乏超短游资主动引导',
  };
}

/**
 * 一、09:25 集合竞价雷达算子
 * 核心指标：
 * - 竞价金额占昨比 (%) = (09:25 竞价成交额 / 昨日全天成交总额) * 100%
 * - 竞价量比 & 未匹配买一/卖一封单手数
 * - 识别【超预期抢筹】、【一字巨封】、【弱转强】、【爆量兑现】与【竞价核按钮】
 */
export function calculateAuctionRadar(
  quote: TickData,
  override?: AuctionRadarOverride
): AuctionRadarMetrics {
  const us = quote.ultraShort;
  const auctionChangePercent =
    override?.auctionChangePercent ??
    us?.auctionChangePercent ??
    Number((((quote.open - quote.prevClose) / quote.prevClose) * 100).toFixed(2));
  const auctionPrice =
    override?.auctionChangePercent !== undefined
      ? Number((quote.prevClose * (1 + auctionChangePercent / 100)).toFixed(2))
      : us?.auctionPrice ?? quote.open;
  const yesterdayAmount = Math.max(
    1e6,
    override?.yesterdayAmount ?? us?.yesterdayAmount ?? quote.amount * 1.15
  );
  const auctionAmount =
    override?.auctionAmount ?? us?.auctionAmount ?? Math.round(yesterdayAmount * 0.065);
  const amountToYesterdayRatio = Number(((auctionAmount / yesterdayAmount) * 100).toFixed(2));
  const auctionVolumeRatio =
    override?.auctionVolumeRatio ??
    us?.auctionVolumeRatio ??
    Number((quote.volumeRatio * 1.4).toFixed(2));
  const unmatchedHands = override?.unmatchedHands ?? us?.auctionUnmatchedHands ?? 0;
  // 没有真实竞价数据时（不在后端雷达里），下面的竞价额/占昨比都是按系数估的，必须打标
  const estimated =
    override?.auctionAmount === undefined &&
    us?.auctionAmount === undefined &&
    us?.auctionVolumeRatio === undefined;

  let signal: AuctionSignalType = 'NORMAL';
  let signalLabel = '常规开盘';
  let signalReason = `${us?.yesterdayPerformanceNote ?? '昨常态收盘'}，竞价占昨比 ${amountToYesterdayRatio}%`;

  if (auctionChangePercent <= -6.5 || unmatchedHands <= -15000) {
    signal = 'NUCLEAR_BUTTON';
    signalLabel = '竞价核按钮';
    signalReason = `深水低开 ${auctionChangePercent > 0 ? '+' : ''}${auctionChangePercent.toFixed(
      2
    )}%，卖盘未匹配压单 ${Math.abs(unmatchedHands).toLocaleString('en-US')} 手，资金恐慌踩踏抢跑`;
  } else if (auctionChangePercent >= 9.8 && unmatchedHands >= 20000) {
    signal = 'LOCKED_LIMIT_UP';
    signalLabel = '一字巨封顶板';
    signalReason = `09:25 涨停价顶死，买一未匹配封单 ${unmatchedHands.toLocaleString(
      'en-US'
    )} 手，占昨比 ${amountToYesterdayRatio}% 惜售锁筹`;
  } else if (amountToYesterdayRatio >= 21.0 && auctionChangePercent < 6.0) {
    signal = 'OVERHEAT_DUMP';
    signalLabel = '爆量兑现预警';
    signalReason = `竞价金额占昨比高达 ${amountToYesterdayRatio}% (>20%警戒线)，但高开幅度仅 ${auctionChangePercent.toFixed(
      2
    )}%，警惕潜伏盘集中兑现`;
  } else if (auctionChangePercent >= 3.2 && amountToYesterdayRatio >= 6.5 && unmatchedHands >= 0) {
    signal = 'SUPER_GRAB';
    signalLabel = '超预期抢筹';
    signalReason = `${
      us?.yesterdayPerformanceNote ?? '昨分歧换手'
    }，今竞价高开 +${auctionChangePercent.toFixed(
      2
    )}% 且占昨比达 ${amountToYesterdayRatio}% (黄金抢筹区间 6%~16%)`;
  } else if (auctionChangePercent >= 1.5 && amountToYesterdayRatio >= 4.5) {
    signal = 'WEAK_TO_STRONG';
    signalLabel = '分歧弱转强';
    signalReason = `${
      us?.yesterdayPerformanceNote ?? '昨日分歧'
    }，今竞价放量高开 +${auctionChangePercent.toFixed(2)}%，占昨比 ${amountToYesterdayRatio}% 承接超预期`;
  }

  return {
    symbol: quote.symbol,
    code: quote.code,
    name: quote.name,
    sector: quote.sector,
    auctionPrice,
    auctionChangePercent,
    auctionAmount,
    yesterdayAmount,
    amountToYesterdayRatio,
    auctionVolumeRatio,
    unmatchedHands,
    signal,
    estimated,
    signalLabel,
    signalReason,
  };
}

export type LadderScenarioPreset = 'live' | 'severe_ebb' | 'healthy_full';

/**
 * 二、涨跌停连板梯队、晋级率与断层退潮监测引擎
 * 统计与推导：
 * - 最高空间板高度 (Space Dragon) 与次高板高度 (Second Max Board)
 * - 今日涨停板分布 vs 昨日连板基数逐层对比 (distributionComparison)
 * - 晋级空间断层自动扫描 (如 6板 与 3板 之间缺失 5板/4板，计算连续断层跨度 maxFaultSpan)
 * - 潜在退潮风险量化评分 (ebbTideRiskScore) 与多维退潮风险提示 (ebbTideRiskReasons)
 */
export function calculateBoardLadderSummary(
  quotes: TickData[],
  scenarioPreset: LadderScenarioPreset = 'live'
): BoardLadderSummary {
  const boardMap = new Map<number, BoardTierGroup['stocks']>();
  const yestBoardCountMap = new Map<number, number>();
  let maxBoardHeight = 0;
  let spaceDragonSymbol = '';
  let spaceDragonName = '--';

  let touchedLimitUpCount = 0;
  let sealedLimitUpCount = 0;
  let limitDownCount = 0;

  // 统计昨日各板基数与今日晋级数
  let yest1Count = 0;
  let today2Count = 0;
  let yest2Count = 0;
  let today3Count = 0;
  let yestHighCount = 0;
  let todayHighCount = 0;

  for (const q of quotes) {
    const us = q.ultraShort;
    let boards = us?.consecutiveBoards ?? 0;
    let yestBoards = us?.yesterdayBoards ?? 0;
    let isTouched = us?.isIntradayTouchedLimitUp ?? boards >= 1;
    let isLimitDown = q.phase === 'LIMIT_DOWN' || q.changePercent <= -9.8;

    // 支持沙盘推演预设场景：极端退潮断层 vs 完整健康主升梯队
    if (scenarioPreset === 'severe_ebb') {
      if (q.symbol === '002230.SZ') {
        // 模拟 3连板 科大讯飞 晋级失败断板，造成 5/4/3 板连续 3 层大断层
        boards = 0;
        yestBoards = 2;
        isTouched = true;
      } else if (q.symbol === '601899.SH' || q.symbol === '601318.SH') {
        isLimitDown = true;
      }
    } else if (scenarioPreset === 'healthy_full') {
      if (q.symbol === '600519.SH') {
        boards = 5;
        yestBoards = 4;
        isTouched = true;
      } else if (q.symbol === '601899.SH') {
        boards = 4;
        yestBoards = 3;
        isTouched = true;
      }
    }

    if (yestBoards >= 1) {
      yestBoardCountMap.set(yestBoards, (yestBoardCountMap.get(yestBoards) ?? 0) + 1);
    }

    if (yestBoards === 1) yest1Count++;
    if (yestBoards === 2) yest2Count++;
    if (yestBoards >= 3) yestHighCount++;

    if (boards === 2) today2Count++;
    if (boards === 3) today3Count++;
    if (boards >= 4) todayHighCount++;

    if (isTouched) touchedLimitUpCount++;
    if (boards >= 1 || (scenarioPreset === 'live' && q.phase === 'LIMIT_UP')) {
      sealedLimitUpCount++;
    }
    if (isLimitDown) limitDownCount++;

    if (boards >= 1) {
      if (boards > maxBoardHeight) {
        maxBoardHeight = boards;
        spaceDragonSymbol = q.symbol;
        spaceDragonName = q.name;
      }
      const list = boardMap.get(boards) ?? [];
      const bid1Vol = q.orderBook.bids[0]?.volume ?? 15000;
      list.push({
        symbol: q.symbol,
        code: q.code,
        name: q.name,
        sector: q.sector,
        price: q.price,
        changePercent: q.changePercent,
        firstSealTime: us?.firstSealTime ?? '09:32:15',
        sealOrderAmount: Math.round(bid1Vol * 100 * q.price),
        dragonRole: us?.dragonRole ?? (boards === maxBoardHeight ? 'SPACE_DRAGON' : 'FOLLOWER'),
      });
      boardMap.set(boards, list);
    }
  }

  // 检测从 maxBoardHeight 到 1板 之间的断层缺失高度与次高板高度
  const missingBoards: number[] = [];
  let secondMaxBoardHeight = 0;

  for (let b = maxBoardHeight - 1; b >= 1; b--) {
    const arr = boardMap.get(b);
    if (!arr || arr.length === 0) {
      missingBoards.push(b);
    } else if (secondMaxBoardHeight === 0) {
      secondMaxBoardHeight = b;
    }
  }

  // 聚类连续断层区间 (Fault Zones)
  const faultZones: LadderFaultZone[] = [];
  let maxFaultSpan = 0;
  if (missingBoards.length > 0) {
    const sortedAsc = [...missingBoards].sort((a, b) => a - b);
    let start = sortedAsc[0];
    let prev = sortedAsc[0];

    for (let i = 1; i <= sortedAsc.length; i++) {
      const cur = sortedAsc[i];
      if (cur === prev + 1) {
        prev = cur;
      } else {
        const spanSize = prev - start + 1;
        if (spanSize > maxFaultSpan) maxFaultSpan = spanSize;
        faultZones.push({
          fromBoard: start,
          toBoard: prev,
          spanSize,
          label:
            start === prev
              ? `${start}连板 (单层断层)`
              : `${start}连板 ~ ${prev}连板 (连续${spanSize}层真空断层)`,
        });
        start = cur;
        prev = cur;
      }
    }
  }

  // 构建今日涨停板分布 vs 昨日连板基数对比表 + 有股梯队列表
  const distributionComparison: LadderDistributionRow[] = [];
  const tiers: BoardTierGroup[] = [];

  for (let b = maxBoardHeight; b >= 1; b--) {
    const stocks = boardMap.get(b) ?? [];
    stocks.sort((a, c) => a.firstSealTime.localeCompare(c.firstSealTime));

    const rawYestBase = yestBoardCountMap.get(b - 1) ?? 0;
    const yestBase =
      b === 1
        ? 0
        : rawYestBase > 0
        ? Math.max(stocks.length, rawYestBase)
        : stocks.length > 0
        ? b === 2
          ? Math.max(stocks.length, yest1Count || stocks.length * 3)
          : b === 3
          ? Math.max(stocks.length, yest2Count || stocks.length * 2)
          : Math.max(stocks.length, yestHighCount || stocks.length + 1)
        : 2; // 断层层默认昨日有 2 家冲击晋级全部折戟

    const promotionRate =
      b === 1 ? null : Number(((stocks.length / Math.max(1, yestBase)) * 100).toFixed(1));
    const isFaultMissing = stocks.length === 0;
    const eliminatedCount = b === 1 ? 0 : Math.max(0, yestBase - stocks.length);

    distributionComparison.push({
      boardCount: b,
      label:
        b === maxBoardHeight && b >= 3
          ? `${b}连板 (最高标)`
          : isFaultMissing
          ? `${b}连板 (断层缺失)`
          : b === 1
          ? '首板 (1板)'
          : `${b}连板`,
      yesterdayBaseLabel:
        b === 1 ? '新发酵首板池' : `昨${b - 1}板 (${yestBase}家)`,
      yesterdayBaseCount: yestBase,
      yesterdayCandidateCount: b === 1 ? null : yestBase,
      todaySealedCount: stocks.length,
      eliminatedCount,
      promotionRate,
      isFaultMissing,
      isFaultLevel: isFaultMissing,
      stockNames: stocks.map((s) => s.name),
      stocks,
    });

    if (stocks.length > 0) {
      tiers.push({
        boardCount: b,
        label:
          b === maxBoardHeight && b >= 3
            ? `${b}连板 · 最高空间板`
            : b === 1
            ? '首板 (1板)'
            : `${b}连板`,
        yesterdayCount: yestBase,
        todaySealedCount: stocks.length,
        promotionRate,
        stocks,
      });
    }
  }

  const firstToSecondRate = Number(
    ((today2Count / Math.max(1, yest1Count || 3)) * 100).toFixed(1)
  );
  const secondToThirdRate = Number(
    ((today3Count / Math.max(1, yest2Count || 2)) * 100).toFixed(1)
  );
  const highBoardPromotionRate = Number(
    ((todayHighCount / Math.max(1, yestHighCount || 2)) * 100).toFixed(1)
  );
  const brokenBoardCount = Math.max(0, touchedLimitUpCount - sealedLimitUpCount);
  const sealSuccessRate =
    touchedLimitUpCount > 0
      ? Number(((sealedLimitUpCount / touchedLimitUpCount) * 100).toFixed(1))
      : 100;

  const hasLadderFault = missingBoards.length > 0;
  const topDragonIsolation =
    maxBoardHeight >= 4 && maxBoardHeight - secondMaxBoardHeight >= 2;

  // 量化计算潜在退潮风险评分 (0 ~ 100)
  const rawRiskScore =
    maxFaultSpan * 16 +
    missingBoards.length * 7 +
    (topDragonIsolation ? 14 : 0) +
    brokenBoardCount * 6 +
    limitDownCount * 8 +
    Math.max(0, (75 - sealSuccessRate) * 0.4);
  const ebbTideRiskScore = hasLadderFault
    ? Number(Math.min(98.5, Math.max(35, rawRiskScore)).toFixed(1))
    : Number(Math.min(32, Math.max(8, brokenBoardCount * 7 + limitDownCount * 8)).toFixed(1));

  const ebbTideRiskLevel: EbbTideRiskLevel =
    ebbTideRiskScore >= 72 || maxFaultSpan >= 3 || limitDownCount >= 3
      ? 'HIGH_EBB_RISK'
      : hasLadderFault || ebbTideRiskScore >= 42
      ? 'MEDIUM_FAULT_RISK'
      : 'LOW_HEALTHY';

  const ebbTideWarningTitle =
    ebbTideRiskLevel === 'HIGH_EBB_RISK'
      ? `【高危退潮风险警报】最高标 ${maxBoardHeight}板 孤立独苗 + 中位连续 ${maxFaultSpan} 层真空断层，谨防高位补跌与中位核按钮`
      : ebbTideRiskLevel === 'MEDIUM_FAULT_RISK'
      ? `【晋级空间断层与分化退潮提示】${maxBoardHeight}连板(${spaceDragonName}) 与 ${secondMaxBoardHeight}连板 之间缺失【${missingBoards
          .map((m) => `${m}板`)
          .join('、')}】，中位接力断层，警惕分歧退潮风险`
      : `【连板梯队完整健康】1板 至 ${maxBoardHeight}连板 阶梯连续无断层，中位护航充沛，接力生态处于安全主升期`;

  const ebbTideRiskReasons: string[] = [];
  if (hasLadderFault) {
    ebbTideRiskReasons.push(
      `空间断层对比：今日最高标为 ${maxBoardHeight}连板(${spaceDragonName})，而次高标仅为 ${secondMaxBoardHeight}连板，中间缺失【${missingBoards
        .map((m) => `${m}连板`)
        .join('、')}】（连续断层跨度 ${maxFaultSpan} 层），形成典型“顶层独苗 + 中间断代”失衡分布。`
    );
    ebbTideRiskReasons.push(
      `中位晋级塌陷：昨日冲击 ${missingBoards
        .map((m) => `${m}板`)
        .join('/')} 的中位连板股今日晋级率跌至 0.0%，中位接力资金严重断流，一旦最高标分歧炸板，缺乏中位身位卡位承接。`
    );
    ebbTideRiskReasons.push(
      `退潮传导预警：当前封板率 ${sealSuccessRate}%（炸板 ${brokenBoardCount} 家、跌停核按钮 ${limitDownCount} 家），退潮风险指数达 ${ebbTideRiskScore}/100，中位跟风股极易出现次日竞价核按钮或天地板亏钱效应。`
    );
  } else {
    ebbTideRiskReasons.push(
      `梯队结构完整：从首板至 ${maxBoardHeight}连板 每一层均有涨停封板标的驻守，无任何晋级空间断层。`
    );
    ebbTideRiskReasons.push(
      `接力承接良性：首板晋级率 ${firstToSecondRate}%、2进3晋级率 ${secondToThirdRate}%、封板率 ${sealSuccessRate}%，高低位资金梯次传导顺畅。`
    );
  }

  const tacticalPlaybook =
    ebbTideRiskLevel === 'HIGH_EBB_RISK'
      ? '【退潮防守策略】严禁接力 3板~5板 缩量中位股及跟风杂毛；控仓防守，仅关注最高空间活口分歧换手或等待新周期首板试错。'
      : ebbTideRiskLevel === 'MEDIUM_FAULT_RISK'
      ? '【哑铃型抱团策略】避开中位断层真空区，资金向两端聚焦：要么锁仓最高空间总龙（三六零），要么切入低位 1进2 / 首板高辨识度先锋龙。'
      : '【主升进攻策略】梯队完整无断层，可围绕主线题材日内先锋龙与 2进3 / 3进4 换手龙头积极博弈晋级。';

  const faultWarningText = hasLadderFault
    ? `梯队断层预警：最高标 ${maxBoardHeight}连板 (${spaceDragonName}) 下方缺失【${missingBoards
        .map((m) => `${m}连板`)
        .join('、')}】身位，中位接力存在断层，潜在退潮风险评分 ${ebbTideRiskScore} 分`
    : `梯队完整：1板至${maxBoardHeight}连板身位连续无断层，接力生态健康`;

  const sentimentPhase: BoardLadderSummary['sentimentPhase'] =
    limitDownCount >= 3 || ebbTideRiskLevel === 'HIGH_EBB_RISK'
      ? '退潮核按钮期'
      : sealSuccessRate >= 75 && maxBoardHeight >= 4
      ? '主升共振期'
      : brokenBoardCount >= 2
      ? '高潮分化期'
      : '混沌试错期';

  return {
    maxBoardHeight,
    secondMaxBoardHeight,
    spaceDragonSymbol,
    spaceDragonName,
    firstToSecondRate,
    secondToThirdRate,
    highBoardPromotionRate,
    sealSuccessRate,
    brokenBoardCount,
    limitDownCount,
    missingBoards,
    hasLadderFault,
    faultZones,
    maxFaultSpan,
    topDragonIsolation,
    ebbTideRiskLevel,
    ebbTideRiskScore,
    ebbTideWarningTitle,
    ebbTideRiskReasons,
    tacticalPlaybook,
    distributionComparison,
    faultWarningText,
    sentimentPhase,
    tiers,
  };
}

function parseSealMinutesSince925(sealTime: string | null): number {
  if (!sealTime) return 180;
  const parts = sealTime.split(':').map(Number);
  if (parts.length < 2 || Number.isNaN(parts[0]) || Number.isNaN(parts[1])) return 180;
  const totalMinutes = parts[0] * 60 + parts[1];
  const base925 = 9 * 60 + 25;
  return Math.max(0, totalMinutes - base925);
}

/**
 * 三、板块/题材共振监测与领涨龙头联动算子
 * “点”：板块内最早封板时间、最高连板身位、容量中军成交额与涨幅协同
 * “面”：板块整体均涨跌幅、板块内涨停个股密度 (limitUpDensityPercent)、板块红盘比、板块主力净流入额
 */
export function calculateThemeResonance(
  quotes: TickData[],
  scenario: ThemeResonanceScenarioPreset = 'live'
): ThemeResonanceItem[] {
  const sectorGroups = new Map<string, TickData[]>();
  for (const q of quotes) {
    const list = sectorGroups.get(q.sector) ?? [];
    list.push(q);
    sectorGroups.set(q.sector, list);
  }

  const rawItems: Omit<ThemeResonanceItem, 'capitalAttackSharePercent'>[] = [];

  sectorGroups.forEach((stocks, sectorName) => {
    const totalLive = stocks.length;
    if (totalLive === 0) return;

    // 构建板块完整梯队成员列表（仅使用实盘Tick标的，不注入硬编码种子数据）
    const combinedMembers: ThemeResonanceItem['memberStocks'] = stocks.map((s) => {
      const isLimUp =
        (s.ultraShort?.consecutiveBoards ?? 0) >= 1 ||
        s.phase === 'LIMIT_UP' ||
        s.changePercent >= (s.code.startsWith('300') || s.code.startsWith('688') ? 19.5 : 9.8);
      const role = s.ultraShort?.dragonRole ?? 'FOLLOWER';
      return {
        symbol: s.symbol,
        code: s.code,
        name: s.name,
        price: s.price,
        changePercent: s.changePercent,
        consecutiveBoards: s.ultraShort?.consecutiveBoards ?? (isLimUp ? 1 : 0),
        dragonRole: role,
        roleLabel: getDragonRoleLabel(role),
        firstSealTime: s.ultraShort?.firstSealTime ?? (isLimUp ? '09:45:00' : null),
        amount: s.amount,
        isLimitUp: isLimUp,
      };
    });

    // 针对沙盘模式调整实盘成员的表现
    const adjustedMembers = combinedMembers.map((m) => {
      if (scenario === 'ai_chip_mainstream' && (sectorName === '人工智能' || sectorName === '半导体')) {
        const boostedChange = m.isLimitUp ? m.changePercent : Number((m.changePercent + 2.4).toFixed(2));
        return {
          ...m,
          changePercent: boostedChange,
          isLimitUp: m.isLimitUp || boostedChange >= 9.8,
          consecutiveBoards: m.isLimitUp || boostedChange >= 9.8 ? Math.max(1, m.consecutiveBoards) : 0,
        };
      }
      if (scenario === 'rotation_divergence') {
        if (sectorName === '人工智能' && m.dragonRole !== 'SPACE_DRAGON') {
          return {
            ...m,
            changePercent: Number((m.changePercent - 3.8).toFixed(2)),
            isLimitUp: false,
          };
        }
        if (sectorName === '电池储能' || sectorName === '新能源车') {
          const boosted = Number(Math.min(10.0, m.changePercent + 4.5).toFixed(2));
          return {
            ...m,
            changePercent: boosted,
            isLimitUp: m.isLimitUp || boosted >= 9.8,
            consecutiveBoards: m.isLimitUp || boosted >= 9.8 ? Math.max(1, m.consecutiveBoards) : 0,
          };
        }
      }
      return m;
    });

    const memberCount = adjustedMembers.length;
    const sectorConstituentCount = Math.max(
      memberCount,
      Math.max(8, totalLive * 4)
    );

    let sumChange = 0;
    let upCount = 0;
    let limitUpCount = 0;
    let totalTurnoverCNY = 0;

    for (const m of adjustedMembers) {
      sumChange += m.changePercent;
      if (m.changePercent > 0) upCount++;
      if (m.isLimitUp || m.consecutiveBoards >= 1) {
        limitUpCount++;
      }
      totalTurnoverCNY += m.amount ?? 1500000000;
    }

    let netInflow = 0;
    for (const s of stocks) {
      const activeDiffHands = s.outerVolume - s.innerVolume;
      netInflow += activeDiffHands * 100 * s.price;
    }
    // 叠加板块梯队涨停溢价资金流
    if (limitUpCount >= 2) {
      netInflow += limitUpCount * 380000000;
    }
    if (scenario === 'ai_chip_mainstream' && (sectorName === '人工智能' || sectorName === '半导体')) {
      netInflow += 1650000000;
    } else if (scenario === 'rotation_divergence') {
      if (sectorName === '人工智能') netInflow -= 1200000000;
      if (sectorName === '电池储能' || sectorName === '新能源车') netInflow += 1450000000;
    }

    const sectorChangePercent = Number((sumChange / memberCount).toFixed(2));
    const upRatioPercent = Number(((upCount / memberCount) * 100).toFixed(1));

    // 计算板块内涨停个股密度 (%)
    const limitUpDensityPercent = Number(
      Math.min(100, (limitUpCount / sectorConstituentCount) * 100).toFixed(1)
    );

    const densityLevel: ThemeResonanceItem['densityLevel'] =
      limitUpDensityPercent >= 22
        ? '涨停潮高密区'
        : limitUpDensityPercent >= 12
        ? '梯队成型区'
        : limitUpDensityPercent > 0
        ? '局部试错区'
        : '冰点无溢价';

    // 识别日内先锋龙（优先取封板时间最早、连板最高、涨幅最大的个股）
    const sortedForPioneer = [...adjustedMembers].sort((a, b) => {
      const sealA = a.firstSealTime ?? '99:99:99';
      const sealB = b.firstSealTime ?? '99:99:99';
      if (sealA !== sealB) return sealA.localeCompare(sealB);
      if (b.consecutiveBoards !== a.consecutiveBoards) {
        return b.consecutiveBoards - a.consecutiveBoards;
      }
      return b.changePercent - a.changePercent;
    });
    const pioneer = sortedForPioneer[0];

    // 识别容量中军龙（优先取成交额最大、或者与先锋龙不同代码的次大成交核心标的，若仅1只则取自身）
    const sortedForCapacity = [...adjustedMembers].sort(
      (a, b) => (b.amount ?? 0) - (a.amount ?? 0)
    );
    const capacity =
      sortedForCapacity.find((m) => m.code !== pioneer.code && (m.amount ?? 0) >= 2500000000) ??
      sortedForCapacity[0];

    // 计算领涨龙头联动指数 (dragonLinkageScore: 0 ~ 100)
    // 1) 先锋点火强度 (0 ~ 40)
    const sealMins = parseSealMinutesSince925(pioneer.firstSealTime);
    const sealSpeedBonus = pioneer.firstSealTime
      ? Math.max(4, 22 - sealMins * 0.22)
      : Math.max(0, pioneer.changePercent * 1.4);
    const pioneerStrength = Math.min(
      40,
      Math.max(0, sealSpeedBonus + pioneer.consecutiveBoards * 4.5 + Math.max(0, pioneer.changePercent) * 0.9)
    );

    // 2) 容量中军协同度 (0 ~ 35)
    const capacityTurnBillion = (capacity.amount ?? 0) / 1_0000_0000;
    const capacitySynergy =
      capacity.changePercent >= 0
        ? Math.min(35, capacity.changePercent * 2.4 + Math.min(12, capacityTurnBillion * 0.14))
        : Math.max(0, 10 + capacity.changePercent * 1.5);

    // 3) 梯队涨停密度与红盘跟风传导 (0 ~ 25)
    const echelonFollowScore = Math.min(
      25,
      limitUpDensityPercent * 0.62 + (upRatioPercent / 100) * 9
    );

    const dragonLinkageScore = Number(
      Math.min(99.5, Math.max(12, pioneerStrength + capacitySynergy + echelonFollowScore)).toFixed(1)
    );

    const dragonLinkageStatus: ThemeResonanceItem['dragonLinkageStatus'] =
      dragonLinkageScore >= 72
        ? '先锋中军强联动'
        : dragonLinkageScore >= 48
        ? '单点脉冲跟风弱'
        : '龙头孤立背离';

    const dragonLinkageDesc =
      dragonLinkageStatus === '先锋中军强联动'
        ? `先锋「${pioneer.name}」(${
            pioneer.consecutiveBoards >= 1
              ? `${pioneer.consecutiveBoards}板·${pioneer.firstSealTime ?? '09:30'}封板`
              : `+${pioneer.changePercent.toFixed(2)}%`
          }) 点火定方向 → 容量中军「${capacity.name}」(${
            capacity.changePercent >= 0 ? '+' : ''
          }${capacity.changePercent.toFixed(2)}%·${((capacity.amount ?? 0) / 1_0000_0000).toFixed(
            1
          )}亿) 放量承接 → 涨停密度 ${limitUpDensityPercent}% 形成梯队共振`
        : dragonLinkageStatus === '单点脉冲跟风弱'
        ? `先锋「${pioneer.name}」日内领涨脉冲，中军「${capacity.name}」(${
            capacity.changePercent >= 0 ? '+' : ''
          }${capacity.changePercent.toFixed(2)}%) 温和跟涨，板块涨停密度 ${limitUpDensityPercent}% 属局部轮动`
        : `龙头「${pioneer.name}」孤立博弈，中军「${capacity.name}」(${capacity.changePercent.toFixed(
            2
          )}%) 资金负反馈，后排跟风断层`;

    // 计算点面共振综合得分 (0 ~ 100)
    const pointScore = Math.min(
      52,
      Math.max(
        0,
        pioneer.changePercent * 2.1 +
          pioneer.consecutiveBoards * 5.6 +
          (dragonLinkageScore / 100) * 15
      )
    );
    const surfaceScore = Math.min(
      48,
      Math.max(
        0,
        sectorChangePercent * 2.8 +
          limitUpDensityPercent * 0.92 +
          limitUpCount * 3.4 +
          (upRatioPercent / 100) * 8
      )
    );
    const resonanceScore = Number(
      Math.min(99.5, Math.max(12, pointScore + surfaceScore)).toFixed(1)
    );

    const resonanceStatus: ThemeResonanceItem['resonanceStatus'] =
      resonanceScore >= 78 && limitUpDensityPercent >= 20
        ? '主线强共振'
        : resonanceScore >= 48
        ? '局部轮动'
        : '分歧兑现';

    const attackRole: ThemeAttackRole =
      resonanceScore >= 78 && limitUpDensityPercent >= 20
        ? 'MAIN_ATTACK'
        : resonanceScore >= 52 && sectorChangePercent > 0
        ? 'SUB_ROTATION'
        : sectorChangePercent >= 0
        ? 'DEFENSIVE_HOLD'
        : 'EBB_RETREAT';

    const attackRoleLabel =
      attackRole === 'MAIN_ATTACK'
        ? '主攻核心主线'
        : attackRole === 'SUB_ROTATION'
        ? '支线轮动助攻'
        : attackRole === 'DEFENSIVE_HOLD'
        ? '防守分歧观察'
        : '资金兑现退潮';

    // D3 热力分布图矩形面积权重：综合板块成交规模、共振得分与涨停密度
    const turnoverBillion = Math.max(15, totalTurnoverCNY / 1_0000_0000);
    const heatWeight = Number(
      (
        turnoverBillion * 0.45 +
        resonanceScore * 1.35 +
        limitUpDensityPercent * 2.4 +
        dragonLinkageScore * 0.8
      ).toFixed(1)
    );

    const sortedMembers = [...adjustedMembers]
      .sort((a, b) => {
        if ((b.isLimitUp ? 1 : 0) !== (a.isLimitUp ? 1 : 0)) {
          return (b.isLimitUp ? 1 : 0) - (a.isLimitUp ? 1 : 0);
        }
        if (b.consecutiveBoards !== a.consecutiveBoards) {
          return b.consecutiveBoards - a.consecutiveBoards;
        }
        return b.changePercent - a.changePercent;
      })
      .map((s) => {
        const role: DragonRoleTag =
          s.code === pioneer.code && s.changePercent > 3
            ? s.consecutiveBoards >= 4
              ? 'SPACE_DRAGON'
              : 'PIONEER_DRAGON'
            : s.code === capacity.code
            ? 'CAPACITY_CORE'
            : s.dragonRole;
        return {
          ...s,
          dragonRole: role,
          roleLabel: getDragonRoleLabel(role),
        };
      });

    rawItems.push({
      sectorName,
      sectorChangePercent,
      limitUpCount,
      sectorConstituentCount,
      limitUpDensityPercent,
      densityLevel,
      upRatioPercent,
      totalNetInflowCNY: netInflow,
      totalTurnoverCNY,
      resonanceScore,
      resonanceStatus,
      dragonLinkageScore,
      dragonLinkageStatus,
      dragonLinkageDesc,
      attackRole,
      attackRoleLabel,
      heatWeight,
      pioneerDragon: {
        symbol: pioneer.symbol,
        name: pioneer.name,
        changePercent: pioneer.changePercent,
        firstSealTime: pioneer.firstSealTime ?? null,
        consecutiveBoards: pioneer.consecutiveBoards,
      },
      capacityCore: {
        symbol: capacity.symbol,
        name: capacity.name,
        changePercent: capacity.changePercent,
        amount: capacity.amount ?? 0,
      },
      memberStocks: sortedMembers,
    });
  });

  // 计算各板块占全市场做多进攻权重的百分比
  const attackScores = rawItems.map((item) =>
    Math.max(
      5,
      (item.resonanceScore / 100) * 45 +
        item.limitUpDensityPercent * 1.5 +
        Math.max(0, item.totalNetInflowCNY / 1_0000_0000) * 6
    )
  );
  const sumAttackScores = attackScores.reduce((acc, v) => acc + v, 0) || 1;

  const finalResults: ThemeResonanceItem[] = rawItems.map((item, idx) => ({
    ...item,
    capitalAttackSharePercent: Number(((attackScores[idx] / sumAttackScores) * 100).toFixed(1)),
  }));

  return finalResults.sort((a, b) => b.resonanceScore - a.resonanceScore);
}

/**
 * 全市场板块/题材共振监测与主流资金进攻方向全景诊断算子
 */
export function analyzeMarketThemeResonance(
  quotes: TickData[],
  scenario: ThemeResonanceScenarioPreset = 'live'
): ThemeResonanceOverview {
  const themes = calculateThemeResonance(quotes, scenario);

  const mainstreamAttackSectors = themes
    .filter((t) => t.attackRole === 'MAIN_ATTACK')
    .map((t) => t.sectorName);
  const effectiveMainstream =
    mainstreamAttackSectors.length > 0
      ? mainstreamAttackSectors
      : themes.slice(0, 2).map((t) => t.sectorName);

  const subRotationSectors = themes
    .filter((t) => t.attackRole === 'SUB_ROTATION')
    .map((t) => t.sectorName);

  const retreatSectors = themes
    .filter((t) => t.attackRole === 'EBB_RETREAT')
    .map((t) => t.sectorName);

  const topThemes = themes.slice(0, 3);
  const marketResonanceScore =
    topThemes.length > 0
      ? Number(
          (
            topThemes.reduce(
              (acc, t) => acc + t.resonanceScore * 0.6 + t.dragonLinkageScore * 0.4,
              0
            ) / topThemes.length
          ).toFixed(1)
        )
      : 50;

  const mainstreamConcentrationPercent = Number(
    themes
      .slice(0, 2)
      .reduce((acc, t) => acc + t.capitalAttackSharePercent, 0)
      .toFixed(1)
  );

  const totalMarketLimitUpCount = themes.reduce((acc, t) => acc + t.limitUpCount, 0);
  const avgLimitUpDensityPercent =
    themes.length > 0
      ? Number(
          (
            themes.reduce((acc, t) => acc + t.limitUpDensityPercent, 0) / themes.length
          ).toFixed(1)
        )
      : 0;

  const top1 = themes[0];
  const top2 = themes[1];

  const attackDirectionHeadline =
    top1 && top2
      ? `当日主流资金主攻【${top1.sectorName}】(涨停密度 ${top1.limitUpDensityPercent}% · 龙头联动 ${top1.dragonLinkageScore}分) 与【${top2.sectorName}】(涨停密度 ${top2.limitUpDensityPercent}%)，双主线合计虹吸全市场 ${mainstreamConcentrationPercent}% 进攻火力`
      : top1
      ? `当日主流资金聚焦【${top1.sectorName}】(涨停密度 ${top1.limitUpDensityPercent}% · 龙头联动 ${top1.dragonLinkageScore}分)`
      : '全市场暂无显著主线共振';

  const tacticalPlaybook =
    marketResonanceScore >= 75
      ? `主线强共振抱团期：优先围绕【${effectiveMainstream.join(
          ' / '
        )}】的日内先锋龙（最早封板）与百亿容量中军做分歧低吸或换手打板，规避【${
          retreatSectors.join(' / ') || '弱势边缘板块'
        }】的高位退潮补跌。`
      : marketResonanceScore >= 55
      ? `多线轮动博弈期：资金在【${effectiveMainstream.join(
          ' / '
        )}】与【${subRotationSectors.join(
          ' / '
        )}】间高低切轮动，建议聚焦前排首板/二板先锋，不宜追高后排跟风。`
      : `存量分歧防守期：板块涨停密度普遍偏低，龙头联动效应减弱，建议严控仓位等待新主线先锋点火。`;

  return {
    scenario,
    themes,
    mainstreamAttackSectors: effectiveMainstream,
    subRotationSectors,
    retreatSectors,
    marketResonanceScore,
    mainstreamConcentrationPercent,
    totalMarketLimitUpCount,
    avgLimitUpDensityPercent,
    attackDirectionHeadline,
    tacticalPlaybook,
  };
}

/**
 * 四、现行注册制法定复利异动监管逆推算子 (k ∈ {2, 3} 法定窗口 & 10日100%严重异动特停预警)
 *
 * 数学推导（严格遵循沪深交易所现行交易规则）：
 * 设个股在窗口 k ∈ {2, 3} 内的累计复利涨幅为：
 *   R_stock(k) = ∏_{i=1}^{k} (1 + r_{s,i}) - 1
 * 对应基准指数在窗口 k 内的累计复利涨幅为：
 *   R_index(k) = ∏_{i=1}^{k} (1 + r_{m,i}) - 1
 * 法定偏离值阈值 T_limit：主板为 20% (0.20)，创业板/科创板为 30% (0.30)。
 *
 * 逆推今日不触发异动的极限安全涨幅 r_{safe, k}：
 *   (1 + R_{stock, k-1}) * (1 + r_{safe, k}) - 1 - R_{index, k} = T_limit
 *   => 1 + r_{safe, k} = (1 + T_limit + R_{index, k}) / (1 + R_{stock, k-1})
 *   => 触发临界价 P_{trigger, k} = P_{prevClose} * (1 + r_{safe, k})
 *
 * 最终取 k=2 与 k=3 中更严苛（价格更低）的窗口作为今日异动红线：
 *   P_{trigger}^* = min(P_{trigger, 2}, P_{trigger, 3})
 */
export function calculateRegulatoryDeviation(
  quote: TickData,
  indexOverrideTodayPct?: number,
  history?: RegulatoryHistory
): RegulatoryDeviationResult {
  const us = quote.ultraShort;
  const is30Rule =
    us?.boardRuleType === 'CHINEXT_STAR_30' ||
    quote.code.startsWith('300') ||
    quote.code.startsWith('688');

  const ruleThresholdPercent = is30Rule ? 30 : 20;
  const boardRuleLabel = is30Rule ? '创业板/科创板 ±30%' : '沪深主板 ±20%';
  const T = ruleThresholdPercent / 100;

  // T-1 / T-2 涨跌幅：优先用后端真实日K（/api/quant/regulatory 的 history），
  // 其次用 ultraShort 里带的真值；两者都没有才退回 0（保守假设无历史涨跌），
  // 并把 historySource 标成 'estimated' 让 UI 打「估算」标。
  // 修复：原占位值 5.2%/4.8%/0.65% 等会直接参与异动临界价和红黄灯计算，
  // 可能产生虚假的"特停高危"告警误导交易决策。改用 0 后不会凭空推高累计偏离度。
  const rawStockT1 = history?.stock_return_t1 ?? us?.stockReturnT1 ?? null;
  const rawStockT2 = history?.stock_return_t2 ?? us?.stockReturnT2 ?? null;
  const rawIndexT1 = history?.index_return_t1 ?? us?.indexReturnT1 ?? null;
  const rawIndexT2 = history?.index_return_t2 ?? us?.indexReturnT2 ?? null;
  const rawIndexToday =
    indexOverrideTodayPct ?? history?.index_return_today ?? us?.indexReturnToday ?? null;

  const historySource: 'kline' | 'estimated' =
    rawStockT1 != null && rawStockT2 != null && rawIndexT1 != null && rawIndexT2 != null
      ? 'kline'
      : 'estimated';

  const stockReturnT1Percent = Number((rawStockT1 ?? 0).toFixed(2));
  const stockReturnT2Percent = Number((rawStockT2 ?? 0).toFixed(2));
  const indexReturnT1Percent = Number((rawIndexT1 ?? 0).toFixed(2));
  const indexReturnT2Percent = Number((rawIndexT2 ?? 0).toFixed(2));
  const indexReturnTodayPercent = Number((rawIndexToday ?? 0).toFixed(2));

  const rS1 = stockReturnT1Percent / 100;
  const rS2 = stockReturnT2Percent / 100;
  const rM1 = indexReturnT1Percent / 100;
  const rM2 = indexReturnT2Percent / 100;
  const rMToday = indexReturnTodayPercent / 100;

  const rSToday = (quote.price - quote.prevClose) / quote.prevClose;

  // 1. k = 2 (连续2个交易日窗口：T-1 与 Today)
  const stockCum2 = (1 + rS1) * (1 + rSToday) - 1;
  const indexCum2 = (1 + rM1) * (1 + rMToday) - 1;
  const stockCumReturn2DayPercent = Number((stockCum2 * 100).toFixed(2));
  const indexCumReturn2DayPercent = Number((indexCum2 * 100).toFixed(2));
  const dev2DayCurrentPercent = Number(((stockCum2 - indexCum2) * 100).toFixed(2));
  const windowSaturation2DayPercent = Number(
    Math.max(0, (Math.abs(dev2DayCurrentPercent) / ruleThresholdPercent) * 100).toFixed(1)
  );

  // 逆推 k=2 今日触发异动的临界涨幅
  const maxSafeFactor2 = (1 + T + indexCum2) / Math.max(0.1, 1 + rS1);
  const maxSafeChange2DayPercent = Number(((maxSafeFactor2 - 1) * 100).toFixed(2));
  const triggerPrice2Day = Number((quote.prevClose * maxSafeFactor2).toFixed(2));

  // 2. k = 3 (连续3个交易日窗口：T-2, T-1 与 Today)
  const stockPrior2 = (1 + rS2) * (1 + rS1);
  const stockCum3 = stockPrior2 * (1 + rSToday) - 1;
  const indexCum3 = (1 + rM2) * (1 + rM1) * (1 + rMToday) - 1;
  const stockCumReturn3DayPercent = Number((stockCum3 * 100).toFixed(2));
  const indexCumReturn3DayPercent = Number((indexCum3 * 100).toFixed(2));
  const dev3DayCurrentPercent = Number(((stockCum3 - indexCum3) * 100).toFixed(2));
  const windowSaturation3DayPercent = Number(
    Math.max(0, (Math.abs(dev3DayCurrentPercent) / ruleThresholdPercent) * 100).toFixed(1)
  );

  // 逆推 k=3 今日触发异动的临界涨幅
  const maxSafeFactor3 = (1 + T + indexCum3) / Math.max(0.1, stockPrior2);
  const maxSafeChange3DayPercent = Number(((maxSafeFactor3 - 1) * 100).toFixed(2));
  const triggerPrice3Day = Number((quote.prevClose * maxSafeFactor3).toFixed(2));

  // 3. 取 k ∈ {2, 3} 中更严苛（触发价更低）的约束窗口
  const bindingWindowK: 2 | 3 = triggerPrice2Day <= triggerPrice3Day ? 2 : 3;
  const effectiveTriggerPrice = Math.min(triggerPrice2Day, triggerPrice3Day);
  const effectiveMaxSafeChangePercent = Math.min(
    maxSafeChange2DayPercent,
    maxSafeChange3DayPercent
  );
  const remainingSafeMarginPercent = Number(
    Math.max(0, effectiveMaxSafeChangePercent - quote.changePercent).toFixed(2)
  );

  const isTriggeredToday =
    dev2DayCurrentPercent >= ruleThresholdPercent ||
    dev3DayCurrentPercent >= ruleThresholdPercent ||
    quote.price >= effectiveTriggerPrice;

  // 4. 10日 100% 严重异动与 10日 4次同向异动停牌核查（特停）锁死预警
  // 10日偏离度：只有后端法规引擎（/api/quant/regulatory）才知道真实值。
  // 以前拿不到就硬塞 42.5%，等于每只票都显示"10日偏离 42.5%"，还拿去判红黄绿灯。
  // 现在拿不到就是 null → UI 显示 "—"，只有已知的字段才参与判定（不拿假数字报警）。
  const base10d = us?.cumDeviation10d ?? null;
  const todayNetDev = quote.changePercent - rMToday * 100;
  const cumDeviation10dPercent =
    base10d === null ? null : Number(Math.max(0, base10d + todayNetDev).toFixed(2));
  const remainingTo100Percent =
    cumDeviation10dPercent === null
      ? null
      : Number(Math.max(0, 100 - cumDeviation10dPercent).toFixed(2));
  const abnormalCount10d = us?.abnormalCount10d ?? null;
  const remainingAbnormalTimes10d =
    abnormalCount10d === null
      ? null
      : Math.max(0, 4 - abnormalCount10d - (isTriggeredToday ? 1 : 0));

  const severeSuspensionLockWarning =
    (remainingTo100Percent !== null && remainingTo100Percent <= 14.0) ||
    (abnormalCount10d !== null && abnormalCount10d >= 3);

  // 文案里不能出现 "null%"：null 一律显示为 "—"
  const fmtDev = (v: number | null | undefined, digits = 1): string =>
    typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits) : '—';

  // 综合特停风险评分 (0 ~ 100)
  const maxWindowSat = Math.max(windowSaturation2DayPercent, windowSaturation3DayPercent);
  const suspensionRiskScore = Number(
    Math.min(
      99.5,
      Math.max(
        8,
        (cumDeviation10dPercent ?? 0) * 0.55 +
          (abnormalCount10d ?? 0) * 11 +
          Math.min(100, maxWindowSat) * 0.25 +
          (severeSuspensionLockWarning ? 15 : 0)
      )
    ).toFixed(1)
  );

  // 5. 红黄绿三色交通信号灯判定
  let alertLight: RegulatoryAlertLight = 'GREEN';
  let alertLightLabel: RegulatoryDeviationResult['alertLightLabel'] = '绿灯 · 安全运行区间';
  let alertLightReason = `k=${bindingWindowK} 窗口占用 ${maxWindowSat.toFixed(
    1
  )}%，距异动线余量 ${remainingSafeMarginPercent}%，10日偏离 ${fmtDev(cumDeviation10dPercent, 2)}% 处于安全区间`;
  let tacticalPlaybook = `当前距离 k=${bindingWindowK} 法定异动临界价 (${effectiveTriggerPrice.toFixed(
    2
  )}元) 空间充裕，可按盘口承接与题材主线节奏正常博弈。`;

  if (severeSuspensionLockWarning || isTriggeredToday) {
    alertLight = 'RED';
    alertLightLabel = '红灯 · 特停/触线高危';
    if (severeSuspensionLockWarning && isTriggeredToday) {
      alertLightReason = `已突破 k=${bindingWindowK} 法定${ruleThresholdPercent}%异动线，且10日偏离达 ${fmtDev(cumDeviation10dPercent, 2)}% (近10日已${fmtDev(abnormalCount10d, 0)}次异动)，逼近100%严重异动/4次同向异动特停红线！`;
      tacticalPlaybook = `【极高危特停锁死预警】若今日封死涨停将触发严重异动或第4次异动监管重点监控，游资主封资金极易在尾盘主动漏单控涨幅（压在 ${effectiveTriggerPrice.toFixed(
        2
      )}元 下方），切勿盲目满仓排队顶一字！`;
    } else if (severeSuspensionLockWarning) {
      alertLightReason = `10日累计偏离高达 ${fmtDev(cumDeviation10dPercent, 2)}% (距100%红线仅剩 ${fmtDev(remainingTo100Percent)}%，近10日已${fmtDev(abnormalCount10d, 0)}次异动)，处于特停重点监控高危区！`;
      tacticalPlaybook = `【严重异动压线博弈】主力资金大概率采取“断板换手压涨幅”策略，严格控制收盘价低于 ${effectiveTriggerPrice.toFixed(
        2
      )}元 (${effectiveMaxSafeChangePercent > 0 ? '+' : ''}${effectiveMaxSafeChangePercent}%) 以绕开第4次异动与100%严重异动。`;
    } else {
      alertLightReason = `今日实时${bindingWindowK}日偏离达 ${Math.max(
        dev2DayCurrentPercent,
        dev3DayCurrentPercent
      ).toFixed(2)}% (≥${ruleThresholdPercent}%阈值)，已触发普通异动龙虎榜披露条件。`;
      tacticalPlaybook = `【今日已触及普通异动】盘后将公布3日/2日龙虎榜席位明细；当前10日累计偏离 ${fmtDev(cumDeviation10dPercent, 2)}% 尚有 ${fmtDev(remainingTo100Percent)}% 缓冲空间，重点观察封单稳定性与次日溢价。`;
    }
  } else if (
    remainingSafeMarginPercent <= 4.5 ||
    maxWindowSat >= 75 ||
    (cumDeviation10dPercent ?? 0) >= 62 ||
    (abnormalCount10d ?? 0) >= 2
  ) {
    alertLight = 'YELLOW';
    alertLightLabel = '黄灯 · 异动压线临界';
    alertLightReason = `主约束 k=${bindingWindowK} 窗口饱和度已达 ${maxWindowSat.toFixed(
      1
    )}%，距触发异动临界价 ${effectiveTriggerPrice.toFixed(
      2
    )}元 仅差 ${remainingSafeMarginPercent}% 涨幅！`;
    tacticalPlaybook = `【异动压线临界区】今日若冲高至 ${effectiveTriggerPrice.toFixed(
      2
    )}元 (${
      effectiveMaxSafeChangePercent > 0 ? '+' : ''
    }${effectiveMaxSafeChangePercent}%) 将触发 k=${bindingWindowK} 异动，关注主力是选择“压线收盘绕监管”还是“暴力封板硬顶异动”。`;
  }

  let statusSummary = `距 k=${bindingWindowK} 法定${ruleThresholdPercent}%异动线还差 ${remainingSafeMarginPercent.toFixed(
    2
  )}% (临界价 ${effectiveTriggerPrice.toFixed(2)}元)`;

  if (severeSuspensionLockWarning && isTriggeredToday) {
    statusSummary = `【高危特停锁死预警】已触及 k=${bindingWindowK} 异动且10日偏离达 ${fmtDev(cumDeviation10dPercent, 2)}% (距100%红线仅剩 ${fmtDev(remainingTo100Percent)}%)`;
  } else if (severeSuspensionLockWarning) {
    statusSummary = `【10日100%严重异动逼近】10日累计偏离 ${fmtDev(cumDeviation10dPercent, 2)}%，今日安全上限 ${effectiveTriggerPrice.toFixed(
      2
    )}元 (${effectiveMaxSafeChangePercent > 0 ? '+' : ''}${effectiveMaxSafeChangePercent}%)`;
  } else if (isTriggeredToday) {
    statusSummary = `【今日已触发 k=${bindingWindowK} 法定异动】当前${bindingWindowK}日偏离达 ${Math.max(
      dev2DayCurrentPercent,
      dev3DayCurrentPercent
    ).toFixed(2)}% (≥${ruleThresholdPercent}%红线)，盘后将披露龙虎榜`;
  }

  return {
    symbol: quote.symbol,
    code: quote.code,
    name: quote.name,
    sector: quote.sector,
    ruleThresholdPercent,
    boardRuleLabel,
    currentPrice: quote.price,
    currentChangePercent: quote.changePercent,
    stockReturnT2Percent,
    stockReturnT1Percent,
    indexReturnT2Percent,
    indexReturnT1Percent,
    indexReturnTodayPercent,
    stockCumReturn2DayPercent,
    indexCumReturn2DayPercent,
    dev2DayCurrentPercent,
    windowSaturation2DayPercent,
    maxSafeChange2DayPercent,
    triggerPrice2Day,
    stockCumReturn3DayPercent,
    indexCumReturn3DayPercent,
    dev3DayCurrentPercent,
    windowSaturation3DayPercent,
    maxSafeChange3DayPercent,
    triggerPrice3Day,
    bindingWindowK,
    effectiveTriggerPrice,
    effectiveMaxSafeChangePercent,
    remainingSafeMarginPercent,
    isTriggeredToday,
    cumDeviation10dPercent,
    remainingTo100Percent,
    abnormalCount10d,
    remainingAbnormalTimes10d,
    severeSuspensionLockWarning,
    suspensionRiskScore,
    alertLight,
    alertLightLabel,
    alertLightReason,
    tacticalPlaybook,
    statusSummary,
    historySource,
  };
}

/**
 * 全市场个股监管异动与红黄灯特停风险汇总算子
 */
export function analyzeMarketRegulatoryOverview(
  quotes: TickData[],
  indexOverrideTodayPct?: number,
  historyMap?: Record<string, RegulatoryHistory>
): RegulatoryMonitorOverview {
  const items = quotes
    .map((q) => calculateRegulatoryDeviation(q, indexOverrideTodayPct, historyMap?.[q.symbol]))
    .sort((a, b) => {
      const rank = { RED: 3, YELLOW: 2, GREEN: 1 };
      if (rank[b.alertLight] !== rank[a.alertLight]) {
        return rank[b.alertLight] - rank[a.alertLight];
      }
      return b.suspensionRiskScore - a.suspensionRiskScore;
    });

  const redLightCount = items.filter((i) => i.alertLight === 'RED').length;
  const yellowLightCount = items.filter((i) => i.alertLight === 'YELLOW').length;
  const greenLightCount = items.filter((i) => i.alertLight === 'GREEN').length;
  const suspensionWarningCount = items.filter((i) => i.severeSuspensionLockWarning).length;
  const triggeredTodayCount = items.filter((i) => i.isTriggeredToday).length;

  return {
    items,
    redLightCount,
    yellowLightCount,
    greenLightCount,
    suspensionWarningCount,
    triggeredTodayCount,
    highestRiskStock: items[0] ?? null,
  };
}

/**
 * 五、真实成交量加权承接算子 (VW-DVR: Volume-Weighted Dynamic Volume Support Ratio)
 *
 * 严格基于 Level-1 分时成交量序列、VWAP 均价线与外盘主动买盘占比构建：
 * 1. 水上筹码锚定率 η_vwap = ∑(P_i >= VWAP 的成交量) / ∑总成交量
 * 2. 分时回撤买盘吸收率 α_dip = 分时回踩企稳切片的主动买量占比与外盘比加权
 * 3. 下影线支撑弹性 β_shadow = (Price - Low) / max(0.01, High - Low)
 * 4. VW-DVR = 0.42 * η_vwap + 0.35 * α_dip + 0.23 * β_shadow ∈ [0, 100]
 */
export function calculateVWDVR(quote: TickData, intradayPoints?: IntradayPoint[]): VWDVRResult {
  let vwap = Number(((quote.high + quote.low + quote.price * 2) / 4).toFixed(2));
  let aboveVwapVol = 0;
  let totalVol = 0;
  let dipRecoveryVol = 0;
  let dipTotalVol = 0;

  if (intradayPoints && intradayPoints.length > 5) {
    const lastPt = intradayPoints[intradayPoints.length - 1];
    vwap = lastPt.avgPrice;

    for (let i = 0; i < intradayPoints.length; i++) {
      const pt = intradayPoints[i];
      totalVol += pt.volume;
      if (pt.price >= pt.avgPrice - 1e-4) {
        aboveVwapVol += pt.volume;
      }
      if (i >= 2) {
        const prev1 = intradayPoints[i - 1];
        const prev2 = intradayPoints[i - 2];
        // 识别回踩企稳切片 (前一分钟回落、当前分钟企稳回升)
        if (prev1.price <= prev2.price) {
          dipTotalVol += pt.volume + prev1.volume;
          if (pt.price >= prev1.price) {
            dipRecoveryVol += pt.volume * 1.35;
          }
        }
      }
    }
  }

  const totalOuterInner = Math.max(1, quote.outerVolume + quote.innerVolume);
  const outerRatioPercent = (quote.outerVolume / totalOuterInner) * 100;

  const aboveVwapVolumeRatio =
    totalVol > 0
      ? Number(Math.min(100, (aboveVwapVol / totalVol) * 100).toFixed(1))
      : quote.price >= vwap
      ? Number(Math.min(96, 58 + Math.max(0, quote.changePercent) * 3.5).toFixed(1))
      : Number(Math.max(12, 42 + quote.changePercent * 3.2).toFixed(1));

  const rawDipAbsorption =
    dipTotalVol > 0
      ? (dipRecoveryVol / dipTotalVol) * 55 + outerRatioPercent * 0.45
      : outerRatioPercent;
  const dipBuyAbsorptionRatio = Number(
    Math.min(98, Math.max(10, rawDipAbsorption)).toFixed(1)
  );

  const highLowSpan = Math.max(0.01, quote.high - quote.low);
  const lowerShadowResilience =
    quote.phase === 'LIMIT_UP'
      ? 98.0
      : quote.phase === 'LIMIT_DOWN'
      ? 5.0
      : Number(
          Math.min(100, Math.max(0, ((quote.price - quote.low) / highLowSpan) * 100)).toFixed(1)
        );

  const priceToVwapDiffPercent = Number((((quote.price - vwap) / vwap) * 100).toFixed(2));

  const rawScore =
    aboveVwapVolumeRatio * 0.42 +
    dipBuyAbsorptionRatio * 0.35 +
    lowerShadowResilience * 0.23;

  const vwDvrScore = Number(Math.min(99.2, Math.max(5.0, rawScore)).toFixed(1));

  let signal: VWDVRResult['signal'] = 'HEALTHY_TURNOVER';
  let signalLabel = '良性换手承接';
  let actionAdvice = '分时均价线附近筹码交换充分，回踩存在买盘托底，适合盯住均价线低吸或去弱留强';

  if (vwDvrScore >= 74) {
    signal = 'STRONG_ABSORPTION';
    signalLabel = '强力承接·分歧转一致';
    actionAdvice =
      '全天大部分筹码锁定在 VWAP 均价线上方，分时回撤缩量且主动买盘迅速吞噬抛压，具备游资主封/锁仓特征';
  } else if (vwDvrScore < 48) {
    signal = 'WEAK_DISTRIBUTION';
    signalLabel = '承接衰竭·派发预警';
    actionAdvice =
      '跌破日内 VWAP 均价线且水下放量滞涨，主动卖盘（内盘）占优，谨防冲高回落、炸板大面或尾盘抢跑';
  }

  return {
    symbol: quote.symbol,
    code: quote.code,
    name: quote.name,
    vwap,
    priceToVwapDiffPercent,
    aboveVwapVolumeRatio,
    dipBuyAbsorptionRatio,
    lowerShadowResilience,
    vwDvrScore,
    signal,
    signalLabel,
    actionAdvice,
  };
}

/**
 * ============================================================================
 * 算子六：龙虎榜席位性质识别与游资/机构/量化博弈解析引擎
 * ============================================================================
 * 自动识别营业部性质：
 * - HOT_MONEY: 游资常用席位（作手新一、章盟主、孙哥、赵老哥、炒股养家、宁波敢死队等）
 * - INSTITUTION: 机构专用 / 沪股通专用 / 深股通专用
 * - QUANT_CAMP: 量化大本营（华泰总部、中信上分、中金上分、国君总部、瑞银花园石桥路等）
 * - RETAIL_CAMP: 散户合力大本营（东财拉萨团结路/东环路天团）
 */
export interface BrokerSeatNatureMeta {
  nature: DragonTigerSeatNature;
  natureLabel: string;
  seatTag: string;
  operatingStyle: string;
}

const KNOWN_SEAT_DICTIONARY: {
  keyword: string;
  nature: DragonTigerSeatNature;
  natureLabel: string;
  seatTag: string;
  operatingStyle: string;
}[] = [
  {
    keyword: '南京太平南路',
    nature: 'HOT_MONEY',
    natureLabel: '游资常用席位',
    seatTag: '顶级游资 · 作手新一',
    operatingStyle: '主线高标连板主封 / 龙头首阴反包接力',
  },
  {
    keyword: '上海溧阳路',
    nature: 'HOT_MONEY',
    natureLabel: '游资常用席位',
    seatTag: '顶级游资 · 孙哥/溧阳路',
    operatingStyle: '空间龙点火主封 / 溢价锁仓引导情绪',
  },
  {
    keyword: '上海江苏路',
    nature: 'HOT_MONEY',
    natureLabel: '游资常用席位',
    seatTag: '顶级游资 · 章盟主',
    operatingStyle: '百亿容量趋势中军重仓推升 / 主升大格局',
  },
  {
    keyword: '绍兴证券营业部',
    nature: 'HOT_MONEY',
    natureLabel: '游资常用席位',
    seatTag: '顶级游资 · 赵老哥',
    operatingStyle: '大周期题材主线重仓接力 / 点面共振主封',
  },
  {
    keyword: '上海宛平南路',
    nature: 'HOT_MONEY',
    natureLabel: '游资常用席位',
    seatTag: '顶级游资 · 炒股养家',
    operatingStyle: '情绪周期冰点试错 / 独一字通道排板锁仓',
  },
  {
    keyword: '宁波解放南路',
    nature: 'HOT_MONEY',
    natureLabel: '游资常用席位',
    seatTag: '顶级游资 · 宁波敢死队',
    operatingStyle: '高位连板硬封 / 强分歧转一致扫板',
  },
  {
    keyword: '杭州庆春路',
    nature: 'HOT_MONEY',
    natureLabel: '游资常用席位',
    seatTag: '一线游资 · 杭州庆春路',
    operatingStyle: '题材前排先锋点火 / 首板二板接力套利',
  },
  {
    keyword: '北京中关村大街',
    nature: 'HOT_MONEY',
    natureLabel: '游资常用席位',
    seatTag: '顶级游资 · 中关村北京帮',
    operatingStyle: '科技与硬核主线龙头抱团主升',
  },
  {
    keyword: '上海闵行区东川路',
    nature: 'HOT_MONEY',
    natureLabel: '游资常用席位',
    seatTag: '顶级游资 · 上海超短帮',
    operatingStyle: '大容量核心中军分歧低吸与主升加仓',
  },
  {
    keyword: '机构专用',
    nature: 'INSTITUTION',
    natureLabel: '机构专用',
    seatTag: '机构专用 · 公募/险资专席',
    operatingStyle: '产业逻辑驱动 / 容量中军波段建仓锁仓',
  },
  {
    keyword: '沪股通专用',
    nature: 'INSTITUTION',
    natureLabel: '机构专用',
    seatTag: '北向资金 · 沪股通专席',
    operatingStyle: '外资权重核心资产与高流动性龙头配置',
  },
  {
    keyword: '深股通专用',
    nature: 'INSTITUTION',
    natureLabel: '机构专用',
    seatTag: '北向资金 · 深股通专席',
    operatingStyle: '外资成长赛道中军波段与日内做T并发',
  },
  {
    keyword: '华泰证券股份有限公司总部',
    nature: 'QUANT_CAMP',
    natureLabel: '量化大本营',
    seatTag: '量化大本营 · 华泰总部',
    operatingStyle: '高频算法打板助涨助跌 / 次日冲高机械兑现',
  },
  {
    keyword: '中国国际金融股份有限公司上海分公司',
    nature: 'QUANT_CAMP',
    natureLabel: '量化大本营',
    seatTag: '量化大本营 · 中金上分',
    operatingStyle: '量化多因子篮子扫货 / 融券日内T+0套利',
  },
  {
    keyword: '中信证券股份有限公司上海分公司',
    nature: 'QUANT_CAMP',
    natureLabel: '量化大本营',
    seatTag: '量化大本营 · 中信上分',
    operatingStyle: '毫秒级通道扫板 / 高频统计套利进出',
  },
  {
    keyword: '国泰君安证券股份有限公司总部',
    nature: 'QUANT_CAMP',
    natureLabel: '量化大本营',
    seatTag: '量化大本营 · 国君总部',
    operatingStyle: '量化趋势跟随与DMA高频对冲策略',
  },
  {
    keyword: '花园石桥路',
    nature: 'QUANT_CAMP',
    natureLabel: '量化大本营',
    seatTag: '量化大本营 · 瑞银QFII量化',
    operatingStyle: '外资高频算法做市与极端分歧套利',
  },
  {
    keyword: '拉萨团结路',
    nature: 'RETAIL_CAMP',
    natureLabel: '散户大本营',
    seatTag: '散户大本营 · 东财拉萨天团',
    operatingStyle: '全市场散户高换手跟风接盘 / 分歧博弈温床',
  },
  {
    keyword: '拉萨东环路',
    nature: 'RETAIL_CAMP',
    natureLabel: '散户大本营',
    seatTag: '散户大本营 · 东财拉萨天团',
    operatingStyle: '散户打板与低吸合力席位 / 筹码分散度风向标',
  },
];

export function identifyBrokerSeatNature(branchName: string): BrokerSeatNatureMeta {
  for (const entry of KNOWN_SEAT_DICTIONARY) {
    if (branchName.includes(entry.keyword)) {
      return {
        nature: entry.nature,
        natureLabel: entry.natureLabel,
        seatTag: entry.seatTag,
        operatingStyle: entry.operatingStyle,
      };
    }
  }
  if (branchName.includes('机构')) {
    return {
      nature: 'INSTITUTION',
      natureLabel: '机构专用',
      seatTag: '机构专用席位',
      operatingStyle: '机构趋势配置',
    };
  }
  if (branchName.includes('分公司') || branchName.includes('总部')) {
    return {
      nature: 'QUANT_CAMP',
      natureLabel: '量化大本营',
      seatTag: '量化算法席位',
      operatingStyle: '程序化高频助涨助跌 / 次日兑现压力偏大',
    };
  }
  if (branchName.includes('拉萨')) {
    return {
      nature: 'RETAIL_CAMP',
      natureLabel: '散户大本营',
      seatTag: '散户大本营 · 拉萨席位',
      operatingStyle: '散户高换手跟风合力',
    };
  }
  return {
    nature: 'HOT_MONEY',
    natureLabel: '游资常用席位',
    seatTag: '一线活跃游资席位',
    operatingStyle: '短线题材点火与接力套利',
  };
}

interface RawSeatSeed {
  branchName: string;
  buyRatio: number; // 占当日总成交额比例 (%)
  sellRatio: number;
}

/**
 * 为不同形态的个股生成真实感极强的龙虎榜前五买席与前五卖席原始披露数据
 */
function buildRawSeatsForQuote(
  quote: TickData,
  presetMode: DragonTigerPresetMode
): {
  boardType: '1D' | '3D';
  listingReason: string;
  buys: RawSeatSeed[];
  sells: RawSeatSeed[];
} {
  const boards = quote.ultraShort?.consecutiveBoards ?? 0;

  if (presetMode === 'hot_inst_resonance') {
    return {
      boardType: boards >= 2 ? '3D' : '1D',
      listingReason: '日涨幅偏离值达7%的证券（游资+机构主封共振推演）',
      buys: [
        { branchName: '国泰君安证券股份有限公司上海江苏路证券营业部', buyRatio: 4.85, sellRatio: 0.12 },
        { branchName: '机构专用 (买二)', buyRatio: 3.92, sellRatio: 0.0 },
        { branchName: '国泰君安证券股份有限公司南京太平南路证券营业部', buyRatio: 3.45, sellRatio: 0.08 },
        { branchName: '机构专用 (买四)', buyRatio: 2.88, sellRatio: 0.35 },
        { branchName: '中信证券股份有限公司上海溧阳路证券营业部', buyRatio: 2.42, sellRatio: 0.15 },
      ],
      sells: [
        { branchName: '华泰证券股份有限公司总部', buyRatio: 0.45, sellRatio: 2.35 },
        { branchName: '中信建投证券股份有限公司杭州庆春路证券营业部', buyRatio: 0.12, sellRatio: 1.85 },
        { branchName: '中国国际金融股份有限公司上海分公司', buyRatio: 0.38, sellRatio: 1.62 },
        { branchName: '东方财富证券股份有限公司拉萨团结路第二证券营业部', buyRatio: 0.92, sellRatio: 1.48 },
        { branchName: '机构专用 (卖五)', buyRatio: 0.65, sellRatio: 1.25 },
      ],
    };
  }

  if (presetMode === 'quant_crowded') {
    return {
      boardType: '1D',
      listingReason: '日换手率达20%的证券（量化大本营扎堆抢筹推演）',
      buys: [
        { branchName: '华泰证券股份有限公司总部', buyRatio: 4.15, sellRatio: 1.85 },
        { branchName: '中国国际金融股份有限公司上海分公司', buyRatio: 3.65, sellRatio: 1.42 },
        { branchName: '中信证券股份有限公司上海分公司', buyRatio: 3.12, sellRatio: 1.28 },
        { branchName: '国泰君安证券股份有限公司总部', buyRatio: 2.55, sellRatio: 0.95 },
        { branchName: '瑞银证券有限责任公司上海花园石桥路证券营业部', buyRatio: 2.18, sellRatio: 0.88 },
      ],
      sells: [
        { branchName: '国泰君安证券股份有限公司南京太平南路证券营业部', buyRatio: 0.15, sellRatio: 3.45 },
        { branchName: '中国银河证券股份有限公司绍兴证券营业部', buyRatio: 0.08, sellRatio: 2.95 },
        { branchName: '华泰证券股份有限公司总部', buyRatio: 2.15, sellRatio: 2.62 },
        { branchName: '东方财富证券股份有限公司拉萨团结路第二证券营业部', buyRatio: 1.25, sellRatio: 2.18 },
        { branchName: '中信证券股份有限公司上海分公司', buyRatio: 1.42, sellRatio: 1.95 },
      ],
    };
  }

  if (presetMode === 'retail_takeover') {
    return {
      boardType: '1D',
      listingReason: '日振幅值达15%的证券（拉萨散户大本营接盘推演）',
      buys: [
        { branchName: '东方财富证券股份有限公司拉萨团结路第二证券营业部', buyRatio: 3.85, sellRatio: 2.45 },
        { branchName: '东方财富证券股份有限公司拉萨东环路第二证券营业部', buyRatio: 3.42, sellRatio: 2.12 },
        { branchName: '东方财富证券股份有限公司拉萨东环路第一证券营业部', buyRatio: 2.95, sellRatio: 1.88 },
        { branchName: '东方财富证券股份有限公司拉萨团结路第一证券营业部', buyRatio: 2.64, sellRatio: 1.75 },
        { branchName: '华泰证券股份有限公司总部', buyRatio: 1.95, sellRatio: 1.62 },
      ],
      sells: [
        { branchName: '中信证券股份有限公司上海溧阳路证券营业部', buyRatio: 0.12, sellRatio: 4.85 },
        { branchName: '国泰君安证券股份有限公司南京太平南路证券营业部', buyRatio: 0.05, sellRatio: 4.12 },
        { branchName: '机构专用 (卖三)', buyRatio: 0.0, sellRatio: 3.55 },
        { branchName: '中国银河证券股份有限公司绍兴证券营业部', buyRatio: 0.18, sellRatio: 2.98 },
        { branchName: '光大证券股份有限公司宁波解放南路证券营业部', buyRatio: 0.08, sellRatio: 2.45 },
      ],
    };
  }

  // 默认实盘模式 ('live')：根据各股真实超短身位与板块特征精准生成
  switch (quote.symbol) {
    case '601360.SH': // 三六零 6连板空间龙：顶级游资锁仓接力三日榜
      return {
        boardType: '3D',
        listingReason: '连续三个交易日内收盘价格涨幅偏离值累计达20%的证券',
        buys: [
          { branchName: '国泰君安证券股份有限公司南京太平南路证券营业部', buyRatio: 5.12, sellRatio: 0.18 },
          { branchName: '中信证券股份有限公司上海溧阳路证券营业部', buyRatio: 4.35, sellRatio: 0.22 },
          { branchName: '华鑫证券有限责任公司上海宛平南路证券营业部', buyRatio: 3.88, sellRatio: 0.0 },
          { branchName: '中国银河证券股份有限公司绍兴证券营业部', buyRatio: 3.25, sellRatio: 0.45 },
          { branchName: '光大证券股份有限公司宁波解放南路证券营业部', buyRatio: 2.76, sellRatio: 0.12 },
        ],
        sells: [
          { branchName: '中信建投证券股份有限公司杭州庆春路证券营业部', buyRatio: 0.25, sellRatio: 2.95 },
          { branchName: '华泰证券股份有限公司总部', buyRatio: 0.85, sellRatio: 2.42 },
          { branchName: '东方财富证券股份有限公司拉萨团结路第二证券营业部', buyRatio: 1.35, sellRatio: 2.15 },
          { branchName: '中国国际金融股份有限公司上海分公司', buyRatio: 0.62, sellRatio: 1.88 },
          { branchName: '东方财富证券股份有限公司拉萨东环路第二证券营业部', buyRatio: 1.12, sellRatio: 1.65 },
        ],
      };

    case '002230.SZ': // 科大讯飞 3连板：章盟主 + 双机构专用 + 深股通 共振主封
      return {
        boardType: '1D',
        listingReason: '日涨幅偏离值达7%的证券',
        buys: [
          { branchName: '国泰君安证券股份有限公司上海江苏路证券营业部', buyRatio: 4.65, sellRatio: 0.15 },
          { branchName: '机构专用 (买二)', buyRatio: 3.95, sellRatio: 0.0 },
          { branchName: '深股通专用', buyRatio: 3.48, sellRatio: 1.12 },
          { branchName: '机构专用 (买四)', buyRatio: 2.92, sellRatio: 0.24 },
          { branchName: '中国银河证券股份有限公司北京中关村大街证券营业部', buyRatio: 2.55, sellRatio: 0.08 },
        ],
        sells: [
          { branchName: '华泰证券股份有限公司总部', buyRatio: 0.92, sellRatio: 2.65 },
          { branchName: '中信证券股份有限公司上海分公司', buyRatio: 0.75, sellRatio: 2.18 },
          { branchName: '深股通专用 (卖三)', buyRatio: 1.45, sellRatio: 1.95 },
          { branchName: '东方财富证券股份有限公司拉萨团结路第二证券营业部', buyRatio: 1.18, sellRatio: 1.72 },
          { branchName: '中信建投证券股份有限公司杭州庆春路证券营业部', buyRatio: 0.15, sellRatio: 1.48 },
        ],
      };

    case '300059.SZ': // 东方财富 冲高回落爆量：量化大本营 + 拉萨天团扎堆，游资机构兑现
      return {
        boardType: '1D',
        listingReason: '日换手率达20%的证券',
        buys: [
          { branchName: '华泰证券股份有限公司总部', buyRatio: 3.45, sellRatio: 2.12 },
          { branchName: '中国国际金融股份有限公司上海分公司', buyRatio: 2.98, sellRatio: 1.85 },
          { branchName: '东方财富证券股份有限公司拉萨团结路第二证券营业部', buyRatio: 2.75, sellRatio: 2.35 },
          { branchName: '中信证券股份有限公司上海分公司', buyRatio: 2.42, sellRatio: 1.76 },
          { branchName: '东方财富证券股份有限公司拉萨东环路第二证券营业部', buyRatio: 2.18, sellRatio: 1.92 },
        ],
        sells: [
          { branchName: '国泰君安证券股份有限公司上海江苏路证券营业部', buyRatio: 0.25, sellRatio: 4.15 },
          { branchName: '机构专用 (卖二)', buyRatio: 0.0, sellRatio: 3.68 },
          { branchName: '深股通专用', buyRatio: 1.42, sellRatio: 3.25 },
          { branchName: '中国银河证券股份有限公司绍兴证券营业部', buyRatio: 0.18, sellRatio: 2.85 },
          { branchName: '华泰证券股份有限公司总部 (卖五)', buyRatio: 1.95, sellRatio: 2.52 },
        ],
      };

    case '000651.SZ': // 格力电器 跌停核按钮：机构与北向大举出逃，拉萨散户与量化被动接盘
      return {
        boardType: '1D',
        listingReason: '日跌幅偏离值达7%的证券',
        buys: [
          { branchName: '东方财富证券股份有限公司拉萨团结路第二证券营业部', buyRatio: 2.45, sellRatio: 1.15 },
          { branchName: '东方财富证券股份有限公司拉萨东环路第一证券营业部', buyRatio: 2.12, sellRatio: 0.98 },
          { branchName: '华泰证券股份有限公司总部', buyRatio: 1.85, sellRatio: 1.42 },
          { branchName: '东方财富证券股份有限公司拉萨东环路第二证券营业部', buyRatio: 1.65, sellRatio: 0.88 },
          { branchName: '瑞银证券有限责任公司上海花园石桥路证券营业部', buyRatio: 1.38, sellRatio: 0.95 },
        ],
        sells: [
          { branchName: '机构专用 (卖一)', buyRatio: 0.0, sellRatio: 5.45 },
          { branchName: '深股通专用', buyRatio: 0.65, sellRatio: 4.62 },
          { branchName: '机构专用 (卖三)', buyRatio: 0.0, sellRatio: 3.88 },
          { branchName: '中国国际金融股份有限公司上海分公司', buyRatio: 0.42, sellRatio: 3.15 },
          { branchName: '国泰君安证券股份有限公司总部', buyRatio: 0.28, sellRatio: 2.75 },
        ],
      };

    case '688981.SH': // 中芯国际 2连板科创板：北京帮+章盟主+机构共振
      return {
        boardType: '1D',
        listingReason: '有价格涨跌幅限制的日收盘价格涨幅达到15%的前五只证券',
        buys: [
          { branchName: '国泰君安证券股份有限公司上海江苏路证券营业部', buyRatio: 4.25, sellRatio: 0.18 },
          { branchName: '中国银河证券股份有限公司北京中关村大街证券营业部', buyRatio: 3.68, sellRatio: 0.12 },
          { branchName: '机构专用 (买三)', buyRatio: 3.35, sellRatio: 0.0 },
          { branchName: '沪股通专用', buyRatio: 2.95, sellRatio: 0.85 },
          { branchName: '申万宏源证券有限公司上海闵行区东川路证券营业部', buyRatio: 2.48, sellRatio: 0.22 },
        ],
        sells: [
          { branchName: '中国国际金融股份有限公司上海分公司', buyRatio: 0.82, sellRatio: 2.45 },
          { branchName: '华泰证券股份有限公司总部', buyRatio: 0.65, sellRatio: 2.12 },
          { branchName: '机构专用 (卖三)', buyRatio: 0.35, sellRatio: 1.85 },
          { branchName: '中信证券股份有限公司上海分公司', buyRatio: 0.58, sellRatio: 1.62 },
          { branchName: '东方财富证券股份有限公司拉萨团结路第二证券营业部', buyRatio: 0.95, sellRatio: 1.38 },
        ],
      };

    default: {
      // 其他核心标的（茅台、宁德、比亚迪等）：根据当日涨跌与连板身位动态生成
      const isStrongUp = quote.changePercent >= 3.0 || boards >= 1;
      return {
        boardType: boards >= 2 ? '3D' : '1D',
        listingReason:
          boards >= 1
            ? '日涨幅偏离值达7%的证券'
            : '日成交金额排名前五的行业龙头重点监控席位切片',
        buys: isStrongUp
          ? [
              { branchName: '国泰君安证券股份有限公司上海江苏路证券营业部', buyRatio: 4.18, sellRatio: 0.15 },
              { branchName: '机构专用 (买二)', buyRatio: 3.72, sellRatio: 0.25 },
              { branchName: quote.symbol.endsWith('.SH') ? '沪股通专用' : '深股通专用', buyRatio: 3.25, sellRatio: 0.92 },
              { branchName: '中信证券股份有限公司上海溧阳路证券营业部', buyRatio: 2.68, sellRatio: 0.18 },
              { branchName: '申万宏源证券有限公司上海闵行区东川路证券营业部', buyRatio: 2.15, sellRatio: 0.32 },
            ]
          : [
              { branchName: '国泰君安证券股份有限公司上海江苏路证券营业部', buyRatio: 3.45, sellRatio: 0.22 },
              { branchName: quote.symbol.endsWith('.SH') ? '沪股通专用' : '深股通专用', buyRatio: 3.12, sellRatio: 1.35 },
              { branchName: '申万宏源证券有限公司上海闵行区东川路证券营业部', buyRatio: 2.58, sellRatio: 0.35 },
              { branchName: '机构专用 (买四)', buyRatio: 2.24, sellRatio: 0.42 },
              { branchName: '中信证券股份有限公司上海溧阳路证券营业部', buyRatio: 1.86, sellRatio: 0.28 },
            ],
        sells: [
          { branchName: '中国银河证券股份有限公司绍兴证券营业部', buyRatio: 0.65, sellRatio: 2.55 },
          { branchName: '中国国际金融股份有限公司上海分公司', buyRatio: 0.75, sellRatio: 2.18 },
          { branchName: '华泰证券股份有限公司总部', buyRatio: 0.58, sellRatio: 1.88 },
          { branchName: '东方财富证券股份有限公司拉萨团结路第二证券营业部', buyRatio: 0.95, sellRatio: 1.62 },
          { branchName: '中信建投证券股份有限公司杭州庆春路证券营业部', buyRatio: 0.42, sellRatio: 1.42 },
        ],
      };
    }
  }
}

export function analyzeStockDragonTigerList(
  quote: TickData,
  presetMode: DragonTigerPresetMode = 'live'
): DragonTigerAnalysis {
  const dailyAmount = Math.max(quote.amount, 5_0000_0000); // 保底按 5 亿成交额归一化
  const raw = buildRawSeatsForQuote(quote, presetMode);

  const buySeats: DragonTigerSeatItem[] = raw.buys.map((item, idx) => {
    const meta = identifyBrokerSeatNature(item.branchName);
    const buyAmount = Math.round((dailyAmount * item.buyRatio) / 100);
    const sellAmount = Math.round((dailyAmount * item.sellRatio) / 100);
    return {
      rank: idx + 1,
      side: 'BUY',
      branchName: item.branchName,
      nature: meta.nature,
      natureLabel: meta.natureLabel,
      seatTag: meta.seatTag,
      operatingStyle: meta.operatingStyle,
      buyAmount,
      sellAmount,
      netAmount: buyAmount - sellAmount,
      turnoverSharePercent: Number(item.buyRatio.toFixed(2)),
    };
  });

  const sellSeats: DragonTigerSeatItem[] = raw.sells.map((item, idx) => {
    const meta = identifyBrokerSeatNature(item.branchName);
    const buyAmount = Math.round((dailyAmount * item.buyRatio) / 100);
    const sellAmount = Math.round((dailyAmount * item.sellRatio) / 100);
    return {
      rank: idx + 1,
      side: 'SELL',
      branchName: item.branchName,
      nature: meta.nature,
      natureLabel: meta.natureLabel,
      seatTag: meta.seatTag,
      operatingStyle: meta.operatingStyle,
      buyAmount,
      sellAmount,
      netAmount: buyAmount - sellAmount,
      turnoverSharePercent: Number(item.sellRatio.toFixed(2)),
    };
  });

  const totalBuyAmount = buySeats.reduce((acc, s) => acc + s.buyAmount, 0);
  const totalSellAmount = sellSeats.reduce((acc, s) => acc + s.sellAmount, 0);
  const totalNetAmount = totalBuyAmount - totalSellAmount;

  const buyTurnoverRatioPercent = Number(((totalBuyAmount / dailyAmount) * 100).toFixed(2));
  const sellTurnoverRatioPercent = Number(((totalSellAmount / dailyAmount) * 100).toFixed(2));
  const netTurnoverRatioPercent = Number(((totalNetAmount / dailyAmount) * 100).toFixed(2));

  // 按四大席位性质（游资常用席位 / 机构专用 / 量化大本营 / 散户大本营）汇总买卖力量
  const campOrder: { nature: DragonTigerSeatNature; label: string }[] = [
    { nature: 'HOT_MONEY', label: '游资常用席位' },
    { nature: 'INSTITUTION', label: '机构专用' },
    { nature: 'QUANT_CAMP', label: '量化大本营' },
    { nature: 'RETAIL_CAMP', label: '散户大本营' },
  ];

  const allSeats = [...buySeats, ...sellSeats];
  const campBreakdown: DragonTigerCampSummary[] = campOrder.map(({ nature, label }) => {
    const matchingBuySide = buySeats.filter((s) => s.nature === nature);
    const matchingAll = allSeats.filter((s) => s.nature === nature);
    const buyAmt = matchingBuySide.reduce((sum, s) => sum + s.buyAmount, 0);
    const sellAmt = sellSeats
      .filter((s) => s.nature === nature)
      .reduce((sum, s) => sum + s.sellAmount, 0);
    const repTags = Array.from(new Set(matchingAll.map((s) => s.seatTag))).slice(0, 2);

    return {
      nature,
      label,
      buyAmount: buyAmt,
      sellAmount: sellAmt,
      netAmount: buyAmt - sellAmt,
      buySharePercent:
        totalBuyAmount > 0 ? Number(((buyAmt / totalBuyAmount) * 100).toFixed(1)) : 0,
      seatCount: matchingAll.length,
      representativeTags: repTags,
    };
  });

  const hotSummary = campBreakdown.find((c) => c.nature === 'HOT_MONEY')!;
  const instSummary = campBreakdown.find((c) => c.nature === 'INSTITUTION')!;
  const quantSummary = campBreakdown.find((c) => c.nature === 'QUANT_CAMP')!;
  const retailSummary = campBreakdown.find((c) => c.nature === 'RETAIL_CAMP')!;

  // 判定买方主导阵营
  const sortedByBuy = [...campBreakdown].sort((a, b) => b.buyAmount - a.buyAmount);
  const dominantCamp = sortedByBuy[0]?.nature ?? 'HOT_MONEY';

  // 席位协同与博弈定性判定
  let synergyVerdict: DragonTigerAnalysis['synergyVerdict'] = 'TOP_HOT_LOCK';
  let synergyLabel = '顶级游资主封接力';
  let nextDayPremiumScore = 78;
  let actionablePlaybook = '';

  if (totalNetAmount < -dailyAmount * 0.04) {
    synergyVerdict = 'MAIN_FORCE_EXIT';
    synergyLabel = '主力席位大举出逃 · 谨防核按钮';
    nextDayPremiumScore = 22;
    actionablePlaybook =
      '卖席前五呈现机构/大游资集中净卖出，买席以拉萨散户或量化被动挂单为主，筹码严重派发，次日严禁盲目抄底。';
  } else if (retailSummary.buySharePercent >= 55) {
    synergyVerdict = 'RETAIL_TAKEOVER_WARN';
    synergyLabel = '拉萨散户大本营霸榜接盘 · 分歧预警';
    nextDayPremiumScore = 34;
    actionablePlaybook =
      '买席前五被东方财富拉萨天团占据超 55% 份额，而一线游资在卖席集中兑现，次日集合竞价若无超预期抢筹大概率低开走弱。';
  } else if (quantSummary.buySharePercent >= 50) {
    synergyVerdict = 'QUANT_CROWDED_RISK';
    synergyLabel = '量化大本营扎堆抢筹 · 防次日冲高砸盘';
    nextDayPremiumScore = 46;
    actionablePlaybook =
      '华泰总部/中金上分/中信上分等量化算法席位占买盘主导，量化资金纪律性极强，次日冲高 3%~5% 极易触发程序化集中兑现，切忌盘中追高。';
  } else if (hotSummary.buySharePercent >= 32 && instSummary.buySharePercent >= 28) {
    synergyVerdict = 'HOT_INST_RESONANCE';
    synergyLabel = '游资+机构协同共振主封 · 溢价极高';
    nextDayPremiumScore = 92;
    actionablePlaybook =
      '顶级游资（负责点火封板提供弹性）与机构/北向专席（负责锁仓托底）同榜大额净买入，卖席抛压已被完全吞噬，次日高溢价连板或趋势加速概率极大。';
  } else {
    synergyVerdict = 'TOP_HOT_LOCK';
    synergyLabel = '顶级游资豪华阵容主封 · 接力强锁仓';
    nextDayPremiumScore = 85;
    actionablePlaybook =
      '买席前五汇聚作手新一、孙哥、养家等一线游资且买一/买二锁仓坚决，卖席以良性换手获利盘为主，次日重点观察 09:25 竞价金额占昨比是否处于 8%~15% 黄金接力区。';
  }

  return {
    symbol: quote.symbol,
    code: quote.code,
    name: quote.name,
    sector: quote.sector,
    price: quote.price,
    changePercent: quote.changePercent,
    dailyAmount,
    boardType: raw.boardType,
    listingReason: raw.listingReason,
    buySeats,
    sellSeats,
    totalBuyAmount,
    totalSellAmount,
    totalNetAmount,
    buyTurnoverRatioPercent,
    sellTurnoverRatioPercent,
    netTurnoverRatioPercent,
    campBreakdown,
    dominantCamp,
    synergyVerdict,
    synergyLabel,
    nextDayPremiumScore,
    actionablePlaybook,
    isSimulated: true, // 龙虎榜席位数据为前端模拟生成，非真实接口数据
  };
}

/**
 * ============================================================================
 * 算子七：龙虎榜游资大佬席位活跃度画像 & D3.js 关联网络图拓扑生成引擎
 * ============================================================================
 */
interface SeatActivitySeed {
  keyword: string;
  shortBranchName: string;
  activityScore: number;
  appearances30d: number;
  totalCapital30d: number;
  nextDayAvgPremiumPercent: number;
  sealWinRatePercent: number;
  holdingHorizon: string;
  favoriteSectors: string[];
  coAppearingAllies: string[];
  allyStocks: {
    symbol: string;
    name: string;
    sector: string;
    roleLabel: string;
    buyAmount: number;
    netAmount: number;
    nextDayPremiumPercent: number;
  }[];
}

const SEAT_ACTIVITY_SEEDS: SeatActivitySeed[] = [
  {
    keyword: '南京太平南路',
    shortBranchName: '国君南京太平南路',
    activityScore: 96,
    appearances30d: 44,
    totalCapital30d: 42_8000_0000,
    nextDayAvgPremiumPercent: 4.86,
    sealWinRatePercent: 79.5,
    holdingHorizon: '主线高标连板格局锁仓 2~3 日 / 首阴反包加仓',
    favoriteSectors: ['人工智能', '算力芯片', '信创安全'],
    coAppearingAllies: ['顶级游资 · 孙哥/溧阳路', '顶级游资 · 炒股养家', '顶级游资 · 赵老哥'],
    allyStocks: [
      {
        symbol: '601360.SH',
        name: '三六零',
        sector: '人工智能',
        roleLabel: '6连板空间龙买一锁仓',
        buyAmount: 3_4200_0000,
        netAmount: 3_3000_0000,
        nextDayPremiumPercent: 7.45,
      },
      {
        symbol: '002230.SZ',
        name: '科大讯飞',
        sector: '人工智能',
        roleLabel: '3连板主升协同扫板',
        buyAmount: 2_1800_0000,
        netAmount: 2_0500_0000,
        nextDayPremiumPercent: 5.28,
      },
      {
        symbol: '688981.SH',
        name: '中芯国际',
        sector: '半导体',
        roleLabel: '20cm先锋点火助攻',
        buyAmount: 1_8500_0000,
        netAmount: 1_6200_0000,
        nextDayPremiumPercent: 4.15,
      },
    ],
  },
  {
    keyword: '上海江苏路',
    shortBranchName: '国君上海江苏路',
    activityScore: 95,
    appearances30d: 39,
    totalCapital30d: 58_6000_0000,
    nextDayAvgPremiumPercent: 4.42,
    sealWinRatePercent: 77.2,
    holdingHorizon: '百亿容量中军波段重仓锁仓 / 机构共振推升',
    favoriteSectors: ['人工智能', '半导体', '新能源车'],
    coAppearingAllies: ['机构专用 · 公募/险资专席', '顶级游资 · 中关村北京帮', '顶级游资 · 孙哥/溧阳路'],
    allyStocks: [
      {
        symbol: '002230.SZ',
        name: '科大讯飞',
        sector: '人工智能',
        roleLabel: '容量中军买一重仓主封',
        buyAmount: 3_8600_0000,
        netAmount: 3_7200_0000,
        nextDayPremiumPercent: 5.65,
      },
      {
        symbol: '688981.SH',
        name: '中芯国际',
        sector: '半导体',
        roleLabel: '科创硬核中军买一主封',
        buyAmount: 4_1200_0000,
        netAmount: 3_9500_0000,
        nextDayPremiumPercent: 4.92,
      },
      {
        symbol: '002594.SZ',
        name: '比亚迪',
        sector: '新能源车',
        roleLabel: '趋势突破大单主封',
        buyAmount: 2_9500_0000,
        netAmount: 2_7600_0000,
        nextDayPremiumPercent: 3.68,
      },
    ],
  },
  {
    keyword: '上海溧阳路',
    shortBranchName: '中信上海溧阳路',
    activityScore: 93,
    appearances30d: 37,
    totalCapital30d: 36_4000_0000,
    nextDayAvgPremiumPercent: 4.58,
    sealWinRatePercent: 76.8,
    holdingHorizon: 'T+1 溢价引导 / 空间龙分歧转一致重手接力',
    favoriteSectors: ['人工智能', '低空经济', '人形机器人'],
    coAppearingAllies: ['顶级游资 · 作手新一', '顶级游资 · 章盟主', '顶级游资 · 宁波敢死队'],
    allyStocks: [
      {
        symbol: '601360.SH',
        name: '三六零',
        sector: '人工智能',
        roleLabel: '买二合力锁仓拱卫高标',
        buyAmount: 2_9200_0000,
        netAmount: 2_7800_0000,
        nextDayPremiumPercent: 6.85,
      },
      {
        symbol: '300750.SZ',
        name: '宁德时代',
        sector: '锂电池',
        roleLabel: '创业板权重共振点火',
        buyAmount: 2_1500_0000,
        netAmount: 1_9600_0000,
        nextDayPremiumPercent: 3.92,
      },
    ],
  },
  {
    keyword: '绍兴证券营业部',
    shortBranchName: '银河绍兴营业部',
    activityScore: 91,
    appearances30d: 33,
    totalCapital30d: 34_2000_0000,
    nextDayAvgPremiumPercent: 4.18,
    sealWinRatePercent: 75.0,
    holdingHorizon: '大周期主线二板/三板确认后重仓扫板',
    favoriteSectors: ['人工智能', '互联网金融', '半导体'],
    coAppearingAllies: ['顶级游资 · 作手新一', '顶级游资 · 炒股养家', '顶级游资 · 孙哥/溧阳路'],
    allyStocks: [
      {
        symbol: '601360.SH',
        name: '三六零',
        sector: '人工智能',
        roleLabel: '买四重仓接力高标',
        buyAmount: 2_1800_0000,
        netAmount: 1_8800_0000,
        nextDayPremiumPercent: 6.12,
      },
      {
        symbol: '300059.SZ',
        name: '东方财富',
        sector: '互联网金融',
        roleLabel: '高位大换手博弈',
        buyAmount: 1_6500_0000,
        netAmount: -1_1200_0000,
        nextDayPremiumPercent: 2.35,
      },
    ],
  },
  {
    keyword: '上海宛平南路',
    shortBranchName: '华鑫上海宛平南路',
    activityScore: 89,
    appearances30d: 29,
    totalCapital30d: 28_9000_0000,
    nextDayAvgPremiumPercent: 5.24,
    sealWinRatePercent: 81.4,
    holdingHorizon: '情绪周期冰点试错 + 一字通道排板锁仓',
    favoriteSectors: ['人工智能', '信创安全', '固态电池'],
    coAppearingAllies: ['顶级游资 · 作手新一', '顶级游资 · 宁波敢死队'],
    allyStocks: [
      {
        symbol: '601360.SH',
        name: '三六零',
        sector: '人工智能',
        roleLabel: '买三零卖出纯锁仓',
        buyAmount: 2_6000_0000,
        netAmount: 2_6000_0000,
        nextDayPremiumPercent: 7.82,
      },
      {
        symbol: '002230.SZ',
        name: '科大讯飞',
        sector: '人工智能',
        roleLabel: '首板排板先手锁仓',
        buyAmount: 1_4500_0000,
        netAmount: 1_4500_0000,
        nextDayPremiumPercent: 5.45,
      },
    ],
  },
  {
    keyword: '宁波解放南路',
    shortBranchName: '光大宁波解放南路',
    activityScore: 88,
    appearances30d: 31,
    totalCapital30d: 26_5000_0000,
    nextDayAvgPremiumPercent: 3.95,
    sealWinRatePercent: 73.6,
    holdingHorizon: '高位换手硬封 / T+1 冲高兑现与强留弱走',
    favoriteSectors: ['人工智能', '高端制造', '算力硬件'],
    coAppearingAllies: ['顶级游资 · 作手新一', '顶级游资 · 赵老哥'],
    allyStocks: [
      {
        symbol: '601360.SH',
        name: '三六零',
        sector: '人工智能',
        roleLabel: '买五分歧转一致扫板',
        buyAmount: 1_8500_0000,
        netAmount: 1_7600_0000,
        nextDayPremiumPercent: 5.88,
      },
    ],
  },
  {
    keyword: '北京中关村大街',
    shortBranchName: '银河北京中关村大街',
    activityScore: 90,
    appearances30d: 28,
    totalCapital30d: 31_8000_0000,
    nextDayAvgPremiumPercent: 4.62,
    sealWinRatePercent: 78.0,
    holdingHorizon: '硬科技主线抱团 2~5 日波段锁仓',
    favoriteSectors: ['半导体', '人工智能', '光刻机'],
    coAppearingAllies: ['顶级游资 · 章盟主', '机构专用 · 公募/险资专席'],
    allyStocks: [
      {
        symbol: '688981.SH',
        name: '中芯国际',
        sector: '半导体',
        roleLabel: '买二科技抱团主封',
        buyAmount: 3_5600_0000,
        netAmount: 3_4400_0000,
        nextDayPremiumPercent: 5.18,
      },
      {
        symbol: '002230.SZ',
        name: '科大讯飞',
        sector: '人工智能',
        roleLabel: '买五协同机构封板',
        buyAmount: 2_1200_0000,
        netAmount: 2_0500_0000,
        nextDayPremiumPercent: 4.75,
      },
    ],
  },
  {
    keyword: '上海闵行区东川路',
    shortBranchName: '申万上海闵行东川路',
    activityScore: 87,
    appearances30d: 26,
    totalCapital30d: 29_4000_0000,
    nextDayAvgPremiumPercent: 3.85,
    sealWinRatePercent: 74.2,
    holdingHorizon: '大容量核心中军分歧低吸与主升加仓',
    favoriteSectors: ['半导体', '酿酒行业', '新能源车'],
    coAppearingAllies: ['顶级游资 · 章盟主', '北向资金 · 沪股通专席'],
    allyStocks: [
      {
        symbol: '688981.SH',
        name: '中芯国际',
        sector: '半导体',
        roleLabel: '买五中军趋势加仓',
        buyAmount: 2_4000_0000,
        netAmount: 2_1800_0000,
        nextDayPremiumPercent: 4.12,
      },
      {
        symbol: '600519.SH',
        name: '贵州茅台',
        sector: '酿酒行业',
        roleLabel: '买三大容量趋势建仓',
        buyAmount: 1_9500_0000,
        netAmount: 1_6800_0000,
        nextDayPremiumPercent: 2.65,
      },
    ],
  },
  {
    keyword: '杭州庆春路',
    shortBranchName: '中信建投杭州庆春路',
    activityScore: 84,
    appearances30d: 35,
    totalCapital30d: 21_2000_0000,
    nextDayAvgPremiumPercent: 3.15,
    sealWinRatePercent: 68.5,
    holdingHorizon: 'T+1 超短打板套利 / 次日集合竞价或早盘冲高兑现',
    favoriteSectors: ['人工智能', '消费电子', '无人驾驶'],
    coAppearingAllies: ['顶级游资 · 作手新一', '量化大本营 · 华泰总部'],
    allyStocks: [
      {
        symbol: '601360.SH',
        name: '三六零',
        sector: '人工智能',
        roleLabel: '卖一获利盘良性换手兑现',
        buyAmount: 4200_0000,
        netAmount: -1_8200_0000,
        nextDayPremiumPercent: 3.45,
      },
    ],
  },
  {
    keyword: '华泰证券股份有限公司总部',
    shortBranchName: '华泰证券总部 (Glab量化)',
    activityScore: 97,
    appearances30d: 86,
    totalCapital30d: 64_5000_0000,
    nextDayAvgPremiumPercent: 1.45,
    sealWinRatePercent: 58.4,
    holdingHorizon: '日内高频算法扫板 / T+1 冲高机械分批兑现',
    favoriteSectors: ['互联网金融', '人工智能', '全市场高换手标的'],
    coAppearingAllies: ['量化大本营 · 中金上分', '量化大本营 · 中信上分'],
    allyStocks: [
      {
        symbol: '300059.SZ',
        name: '东方财富',
        sector: '互联网金融',
        roleLabel: '买一高频量化做T扫货',
        buyAmount: 3_1200_0000,
        netAmount: 1_2400_0000,
        nextDayPremiumPercent: 1.15,
      },
    ],
  },
  {
    keyword: '机构专用',
    shortBranchName: '机构专用席位',
    activityScore: 92,
    appearances30d: 62,
    totalCapital30d: 78_2000_0000,
    nextDayAvgPremiumPercent: 3.92,
    sealWinRatePercent: 74.8,
    holdingHorizon: '产业景气度驱动 / 中线波段锁仓 5~20 日',
    favoriteSectors: ['人工智能', '半导体', '锂电池'],
    coAppearingAllies: ['顶级游资 · 章盟主', '北向资金 · 深股通专席'],
    allyStocks: [
      {
        symbol: '002230.SZ',
        name: '科大讯飞',
        sector: '人工智能',
        roleLabel: '买二/买四双机构锁仓主封',
        buyAmount: 3_2800_0000,
        netAmount: 3_1500_0000,
        nextDayPremiumPercent: 5.12,
      },
    ],
  },
];

export function formatShortBranchName(branchName: string): string {
  for (const seed of SEAT_ACTIVITY_SEEDS) {
    if (branchName.includes(seed.keyword)) {
      return seed.shortBranchName;
    }
  }
  return branchName
    .replace('股份有限公司', '')
    .replace('有限责任公司', '')
    .replace('证券营业部', '')
    .replace('东方财富证券', '东财')
    .replace('中国国际金融', '中金')
    .replace('国泰君安证券', '国君')
    .replace('中国银河证券', '银河')
    .replace('中信建投证券', '中信建投')
    .replace('申万宏源证券有限公司', '申万');
}

/**
 * 获取任意龙虎榜席位的详细活跃度画像与近期历史战绩（点击 D3 网络图节点时展示）
 */
export function getBrokerSeatActivityProfile(
  branchName: string,
  seatItem?: DragonTigerSeatItem,
  currentSymbol = '601360.SH',
  currentStockName = '三六零',
  currentSector = '人工智能'
): DragonTigerSeatActivityProfile {
  const meta = identifyBrokerSeatNature(branchName);
  const matchedSeed = SEAT_ACTIVITY_SEEDS.find((s) => branchName.includes(s.keyword));

  // 基于 branchName 构造确定性哈希微调，保证不同机构/营业部数据真实且唯一
  let hash = 0;
  for (let i = 0; i < branchName.length; i++) {
    hash = (hash * 31 + branchName.charCodeAt(i)) % 1000;
  }

  const activityScore =
    matchedSeed?.activityScore ??
    (meta.nature === 'HOT_MONEY'
      ? 86 + (hash % 10)
      : meta.nature === 'QUANT_CAMP'
      ? 91 + (hash % 7)
      : meta.nature === 'INSTITUTION'
      ? 88 + (hash % 8)
      : 82 + (hash % 12));

  const appearances30d =
    matchedSeed?.appearances30d ??
    (meta.nature === 'QUANT_CAMP'
      ? 65 + (hash % 25)
      : meta.nature === 'RETAIL_CAMP'
      ? 95 + (hash % 30)
      : 24 + (hash % 18));

  const totalCapital30d =
    matchedSeed?.totalCapital30d ??
    Math.round((appearances30d * (8500_0000 + (hash % 45) * 150_0000))) ;

  const avgSingleBuyAmount = Math.round(totalCapital30d / Math.max(1, appearances30d));

  const nextDayAvgPremiumPercent =
    matchedSeed?.nextDayAvgPremiumPercent ??
    (meta.nature === 'HOT_MONEY'
      ? Number((3.6 + (hash % 18) * 0.1).toFixed(2))
      : meta.nature === 'INSTITUTION'
      ? Number((3.2 + (hash % 14) * 0.1).toFixed(2))
      : meta.nature === 'QUANT_CAMP'
      ? Number((1.1 + (hash % 12) * 0.1).toFixed(2))
      : Number((-0.8 + (hash % 10) * 0.1).toFixed(2)));

  const sealWinRatePercent =
    matchedSeed?.sealWinRatePercent ??
    (meta.nature === 'HOT_MONEY'
      ? Number((72 + (hash % 9) * 0.8).toFixed(1))
      : meta.nature === 'INSTITUTION'
      ? Number((70 + (hash % 8) * 0.7).toFixed(1))
      : meta.nature === 'QUANT_CAMP'
      ? Number((56 + (hash % 9) * 0.6).toFixed(1))
      : Number((46 + (hash % 8) * 0.5).toFixed(1)));

  const activityLevelLabel: DragonTigerSeatActivityProfile['activityLevelLabel'] =
    activityScore >= 92
      ? '极度活跃 · 市场风向标'
      : activityScore >= 85
      ? '高度活跃 · 主线常客'
      : '中度活跃 · 波段出击';

  const currentBattle: DragonTigerSeatBattleRecord = {
    date: '今日当期榜单',
    symbol: currentSymbol,
    name: currentStockName,
    sector: currentSector,
    roleLabel: seatItem
      ? `${seatItem.side === 'BUY' ? `主买${seatItem.rank}` : `主卖${seatItem.rank}`} · 占成交 ${seatItem.turnoverSharePercent}%`
      : '今日龙虎榜核心博弈席位',
    buyAmount: seatItem?.buyAmount ?? 1_8500_0000,
    netAmount: seatItem?.netAmount ?? 1_4200_0000,
    nextDayPremiumPercent: nextDayAvgPremiumPercent,
  };

  const historicalBattles: DragonTigerSeatBattleRecord[] = (
    matchedSeed?.allyStocks ?? [
      {
        symbol: '601360.SH',
        name: '三六零',
        sector: '人工智能',
        roleLabel: '主线高标协同接力',
        buyAmount: 2_1500_0000,
        netAmount: 1_8200_0000,
        nextDayPremiumPercent: 5.12,
      },
      {
        symbol: '002230.SZ',
        name: '科大讯飞',
        sector: '人工智能',
        roleLabel: '容量中军趋势主封',
        buyAmount: 1_9200_0000,
        netAmount: 1_5600_0000,
        nextDayPremiumPercent: 4.25,
      },
    ]
  )
    .filter((b) => b.symbol !== currentSymbol)
    .slice(0, 3)
    .map((b, idx) => ({
      date: idx === 0 ? 'T-1 交易日' : idx === 1 ? 'T-3 交易日' : 'T-5 交易日',
      symbol: b.symbol,
      name: b.name,
      sector: b.sector,
      roleLabel: b.roleLabel,
      buyAmount: b.buyAmount,
      netAmount: b.netAmount,
      nextDayPremiumPercent: b.nextDayPremiumPercent,
    }));

  const recentBattles = [currentBattle, ...historicalBattles];

  const baseWeekCount = Math.max(3, Math.round(appearances30d / 4));
  const baseWeekCap = Math.round(totalCapital30d / 4);
  const monthlyTrend = [
    { weekLabel: 'W-3周', count: Math.max(2, baseWeekCount - 2), capital: Math.round(baseWeekCap * 0.82) },
    { weekLabel: 'W-2周', count: baseWeekCount, capital: Math.round(baseWeekCap * 0.95) },
    { weekLabel: '上周', count: baseWeekCount + 1, capital: Math.round(baseWeekCap * 1.06) },
    { weekLabel: '本周', count: baseWeekCount + 2, capital: Math.round(baseWeekCap * 1.17) },
  ];

  return {
    branchName,
    shortBranchName: formatShortBranchName(branchName),
    seatTag: meta.seatTag,
    nature: meta.nature,
    natureLabel: meta.natureLabel,
    operatingStyle: meta.operatingStyle,
    activityLevelLabel,
    activityScore,
    appearances30d,
    totalCapital30d,
    avgSingleBuyAmount,
    nextDayAvgPremiumPercent,
    sealWinRatePercent,
    holdingHorizon:
      matchedSeed?.holdingHorizon ??
      (meta.nature === 'HOT_MONEY'
        ? 'T+1 连板溢价接力 / 龙头分歧转一致锁仓'
        : meta.nature === 'INSTITUTION'
        ? '基本面与产业趋势波段锁仓'
        : meta.nature === 'QUANT_CAMP'
        ? '日内高频算法套利 / T+1 冲高兑现'
        : '高换手分歧跟风博弈'),
    favoriteSectors: matchedSeed?.favoriteSectors ?? ['人工智能', '半导体', '新能源车'],
    coAppearingAllies:
      matchedSeed?.coAppearingAllies ?? ['顶级游资 · 章盟主', '顶级游资 · 作手新一', '机构专用席位'],
    recentBattles,
    monthlyTrend,
  };
}

/**
 * 构建 D3.js 龙虎榜个股-游资大佬席位关联网络图数据
 * - 中心节点：当前选定个股 (TARGET_STOCK)
 * - 一级关联节点：当日龙虎榜出现的游资大佬营业部及其他核心席位 (BROKER_SEAT)
 * - 二级协同节点：顶级游资同日/近期跨股协同上榜的核心关联个股 (ALLY_STOCK)
 * - 连线粗细 (strokeWidth)：严格按买入金额 (buyAmount) 线性映射 (2.0px ~ 9.5px)
 */
export function buildDragonTigerNetworkData(
  analysis: DragonTigerAnalysis,
  options?: {
    onlyHotMoney?: boolean;
    includeAllyStocks?: boolean;
  }
): DragonTigerNetworkData {
  const onlyHotMoney = options?.onlyHotMoney ?? false;
  const includeAllyStocks = options?.includeAllyStocks ?? true;

  // 1. 汇总并去重当日上榜营业部（若同一营业部同时出现在买卖前五，合并其买卖金额）
  const seatMap = new Map<
    string,
    {
      seat: DragonTigerSeatItem;
      side: 'BUY' | 'SELL' | 'BOTH';
      rankLabel: string;
    }
  >();

  for (const b of analysis.buySeats) {
    seatMap.set(b.branchName, {
      seat: { ...b },
      side: 'BUY',
      rankLabel: `买${b.rank}`,
    });
  }

  for (const s of analysis.sellSeats) {
    const existing = seatMap.get(s.branchName);
    if (existing) {
      const mergedBuy = Math.max(existing.seat.buyAmount, s.buyAmount);
      const mergedSell = Math.max(existing.seat.sellAmount, s.sellAmount);
      existing.seat.buyAmount = mergedBuy;
      existing.seat.sellAmount = mergedSell;
      existing.seat.netAmount = mergedBuy - mergedSell;
      existing.side = 'BOTH';
      existing.rankLabel = `${existing.rankLabel}/卖${s.rank}`;
    } else {
      seatMap.set(s.branchName, {
        seat: { ...s },
        side: 'SELL',
        rankLabel: `卖${s.rank}`,
      });
    }
  }

  let mergedSeats = Array.from(seatMap.values());

  if (onlyHotMoney) {
    const hotOnly = mergedSeats.filter((m) => m.seat.nature === 'HOT_MONEY');
    // 若极端沙盘模式下 HOT_MONEY 少于 2 个，保留买方前 3 席位确保网络图拓扑完整
    mergedSeats = hotOnly.length >= 2 ? hotOnly : mergedSeats.slice(0, 5);
  }

  // 计算连线买入金额极值，用于线性映射连线粗细 strokeWidth (2.0px ~ 9.5px)
  const effectiveBuyAmounts = mergedSeats.map((m) => Math.max(m.seat.buyAmount, 500_0000));
  const maxBuyAmount = Math.max(...effectiveBuyAmounts, 1_0000_0000);
  const minBuyAmount = Math.min(...effectiveBuyAmounts, maxBuyAmount);

  const computeStrokeWidth = (buyAmt: number): number => {
    const clamped = Math.max(0, buyAmt);
    if (maxBuyAmount <= minBuyAmount) return 5.5;
    const ratio = Math.min(1, Math.max(0, (clamped - minBuyAmount) / (maxBuyAmount - minBuyAmount)));
    return Number((2.0 + ratio * 7.5).toFixed(2));
  };

  const computeNodeRadius = (buyAmt: number, nature: DragonTigerSeatNature): number => {
    const base = nature === 'HOT_MONEY' ? 22 : 19;
    if (maxBuyAmount <= minBuyAmount) return base + 4;
    const ratio = Math.min(1, Math.max(0, (buyAmt - minBuyAmount) / (maxBuyAmount - minBuyAmount)));
    return Math.round(base + ratio * 9);
  };

  const centerNodeId = `stock-${analysis.symbol}`;
  const nodes: DragonTigerGraphNode[] = [
    {
      id: centerNodeId,
      nodeType: 'TARGET_STOCK',
      label: analysis.name,
      subLabel: `${analysis.symbol} · ${analysis.boardType === '3D' ? '三日榜' : '单日榜'}`,
      symbol: analysis.symbol,
      buyAmount: analysis.totalBuyAmount,
      sellAmount: analysis.totalSellAmount,
      netAmount: analysis.totalNetAmount,
      turnoverSharePercent: analysis.buyTurnoverRatioPercent,
      radius: 34,
    },
  ];

  const links: DragonTigerGraphLink[] = [];
  const allyStockNodeMap = new Map<string, DragonTigerGraphNode>();

  mergedSeats.forEach((entry, idx) => {
    const { seat, side, rankLabel } = entry;
    const seatNodeId = `seat-${idx}-${seat.branchName}`;
    const profile = getBrokerSeatActivityProfile(
      seat.branchName,
      seat,
      analysis.symbol,
      analysis.name,
      analysis.sector
    );

    const isHotMoney = seat.nature === 'HOT_MONEY';
    const shortTag = seat.seatTag.includes('·')
      ? seat.seatTag.split('·')[1].trim()
      : seat.seatTag;

    nodes.push({
      id: seatNodeId,
      nodeType: 'BROKER_SEAT',
      label: isHotMoney ? `游资 · ${shortTag}` : shortTag,
      subLabel: `${rankLabel} · ${profile.shortBranchName}`,
      branchName: seat.branchName,
      nature: seat.nature,
      natureLabel: seat.natureLabel,
      side,
      rankLabel,
      buyAmount: seat.buyAmount,
      sellAmount: seat.sellAmount,
      netAmount: seat.netAmount,
      turnoverSharePercent: seat.turnoverSharePercent,
      activityProfile: profile,
      radius: computeNodeRadius(seat.buyAmount, seat.nature),
    });

    const strokeWidth = computeStrokeWidth(seat.buyAmount);
    links.push({
      id: `link-${centerNodeId}-${seatNodeId}`,
      sourceId: centerNodeId,
      targetId: seatNodeId,
      linkType: side === 'SELL' ? 'PRIMARY_SELL' : 'PRIMARY_BUY',
      side: side === 'SELL' ? 'SELL' : 'BUY',
      buyAmount: seat.buyAmount,
      sellAmount: seat.sellAmount,
      netAmount: seat.netAmount,
      strokeWidth,
      turnoverSharePercent: seat.turnoverSharePercent,
      description: `${profile.shortBranchName} (${rankLabel}) 买入 ${(seat.buyAmount / 1_0000_0000).toFixed(2)}亿`,
    });

    // 为游资大佬席位挂载近期同榜协同个股 (ALLY_STOCK)，构建二阶关联网络
    if (includeAllyStocks && seat.nature === 'HOT_MONEY') {
      const coStock = profile.recentBattles.find((b) => b.symbol !== analysis.symbol);
      if (coStock) {
        const allyId = `ally-${coStock.symbol}`;
        if (!allyStockNodeMap.has(allyId)) {
          const allyNode: DragonTigerGraphNode = {
            id: allyId,
            nodeType: 'ALLY_STOCK',
            label: `${coStock.name}`,
            subLabel: `游资协同标的 · ${coStock.sector}`,
            symbol: coStock.symbol,
            buyAmount: coStock.buyAmount,
            sellAmount: Math.max(0, coStock.buyAmount - coStock.netAmount),
            netAmount: coStock.netAmount,
            turnoverSharePercent: 3.2,
            radius: 17,
          };
          allyStockNodeMap.set(allyId, allyNode);
          nodes.push(allyNode);
        }

        links.push({
          id: `link-${seatNodeId}-${allyId}`,
          sourceId: seatNodeId,
          targetId: allyId,
          linkType: 'CO_APPEAR_STOCK',
          side: 'BUY',
          buyAmount: coStock.buyAmount,
          sellAmount: Math.max(0, coStock.buyAmount - coStock.netAmount),
          netAmount: coStock.netAmount,
          strokeWidth: Math.max(1.6, Number((computeStrokeWidth(coStock.buyAmount) * 0.65).toFixed(2))),
          turnoverSharePercent: 3.2,
          description: `${shortTag} 同榜协同主封 ${coStock.name}`,
        });
      }
    }
  });

  const hotMoneySeats = mergedSeats.filter((m) => m.seat.nature === 'HOT_MONEY');
  const totalHotMoneyBuyAmount = hotMoneySeats.reduce((acc, m) => acc + m.seat.buyAmount, 0);

  return {
    symbol: analysis.symbol,
    stockName: analysis.name,
    nodes,
    links,
    maxBuyAmount,
    minBuyAmount,
    hotMoneySeatCount: hotMoneySeats.length,
    totalHotMoneyBuyAmount,
  };
}


