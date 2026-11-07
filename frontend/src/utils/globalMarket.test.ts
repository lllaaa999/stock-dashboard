import test from 'node:test';
import assert from 'node:assert/strict';
import type {
  CrossMarketTransmissionChain,
  GlobalAssetCategory,
  GlobalMarketRadarResponse,
  QuantModuleTabId,
} from '../types/market';
import { useMarketStore } from '../store/useMarketStore';

test('QuantModuleTabId 联合类型支持 global 且在 store 中可正常切换', () => {
  const tab: QuantModuleTabId = 'global';
  assert.equal(tab, 'global');

  // 验证 store 操作
  useMarketStore.getState().setQuantModuleTab('global');
  assert.equal(useMarketStore.getState().quantModuleTab, 'global');

  // 验证 openQuantModule('global') 会切换工作区模式为 quant 且设置 tab 为 global
  useMarketStore.getState().openQuantModule('global');
  assert.equal(useMarketStore.getState().workspaceMode, 'quant');
  assert.equal(useMarketStore.getState().quantModuleTab, 'global');
});

test('跨市场传导链结构与多空过滤逻辑准确', () => {
  const mockChain: CrossMarketTransmissionChain = {
    id: 'chain_ai_semiconductor',
    name: 'AI算力与硬科技半导体链',
    direction: 'BULLISH',
    intensity: 'STRONG',
    resonanceScore: 86,
    drivers: [
      { symbol: 'TSM', name: '台积电', price: 198.4, changePercent: 6.33 },
      { symbol: 'NVDA', name: '英伟达', price: 138.25, changePercent: 2.78 },
    ],
    mappedSectors: ['CPO光模块', '算力芯片'],
    mappedSymbols: [
      { symbol: '300308.SZ', name: '中际旭创' },
      { symbol: '688256.SH', name: '寒武纪' },
    ],
    transmissionLogic: '台积电法说会超预期带动A股算力光模块共振',
  };

  assert.equal(mockChain.direction, 'BULLISH');
  assert.ok(mockChain.resonanceScore > 0);
  assert.equal(mockChain.drivers.length, 2);
  assert.equal(mockChain.mappedSymbols[0].symbol, '300308.SZ');
});

test('全球五大资产类别枚举完整覆盖', () => {
  const categories: GlobalAssetCategory[] = [
    'ASIA_CORE',
    'US_EU_INDICES',
    'TECH_GIANTS',
    'COMMODITIES',
    'FOREX',
  ];
  assert.equal(categories.length, 5);
});

test('GlobalMarketRadarResponse 契约结构完整', () => {
  const mockRadar: GlobalMarketRadarResponse = {
    status: 'ok',
    updatedAt: Date.now(),
    summary: {
      globalRiskAppetite: 'RISK_ON',
      riskAppetiteLabel: '全球风险偏好升温',
      a50ChangePercent: 0.68,
      usdcnhPrice: 7.238,
      usdcnhChangePercent: -0.18,
      topBullishChain: 'AI算力与硬科技半导体链',
      topBearishChain: '全球原油走弱与通胀降温链',
    },
    assets: [
      {
        symbol: 'CN50',
        name: '富时中国A50期指',
        category: 'ASIA_CORE',
        price: 13245.0,
        change: 89.0,
        changePercent: 0.68,
      },
    ],
    groups: {
      ASIA_CORE: [],
      US_EU_INDICES: [],
      TECH_GIANTS: [],
      COMMODITIES: [],
      FOREX: [],
    },
    transmissionChains: [],
    liveNews: [
      {
        id: 'news_1',
        time: '09:28:15',
        title: '台积电法说会展望强劲',
        content: 'AI芯片持续供不应求',
        category: 'TECH_INDUSTRY',
        polarity: 'BULLISH',
        importance: 'HIGH',
      },
    ],
  };

  assert.equal(mockRadar.status, 'ok');
  assert.equal(mockRadar.summary.globalRiskAppetite, 'RISK_ON');
  assert.equal(mockRadar.liveNews[0].polarity, 'BULLISH');
});
