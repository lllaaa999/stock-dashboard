/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useCallback, useEffect, useState } from 'react';
import { BellRing, X } from 'lucide-react';
import { FinancialChart } from './components/FinancialChart';
import { CommandPaletteModal } from './components/CommandPaletteModal';
import ErrorToast from './components/ErrorToast';
import { IndexTickerBar } from './components/IndexTickerBar';
import { OrderBook5Panel } from './components/OrderBook5Panel';
import { PriceAlertModal } from './components/PriceAlertModal';
import { PWAInstallModal } from './components/PWAInstallModal';
import { StockQuoteHeader } from './components/StockQuoteHeader';
import { TopNavBar } from './components/TopNavBar';
import { TradeTicksAndMetricsPanel } from './components/TradeTicksAndMetricsPanel';
import { UltraShortStockDiagnosticStrip } from './components/UltraShortStockDiagnosticStrip';
import { WatchlistPanel } from './components/WatchlistPanel';

// 大体积工作台按需加载：首屏只加载 chart 模式必需代码，切到 auction/quant 时再拉对应 chunk
const CallAuctionRadarPlugin = React.lazy(() =>
  import('./components/CallAuctionRadarPlugin').then((m) => ({ default: m.CallAuctionRadarPlugin }))
);
const UltraShortQuantWorkbench = React.lazy(() =>
  import('./components/UltraShortQuantWorkbench').then((m) => ({ default: m.UltraShortQuantWorkbench }))
);
import { marketWsClient } from './services/wsClient';
import { useMarketStore } from './store/useMarketStore';
import {
  buildAlertTriggerMessage,
  evaluatePriceAlertRule,
  formatPrice,
  formatSignedPercent,
} from './utils/marketCalc';

/**
 * 浏览器原生 Notification API 推送封装
 * 当用户已授予通知权限 (permission === 'granted') 时，发送系统级桌面/移动端通知推送；
 * 若处于 PWA ServiceWorker 环境，同时兼容 registration.showNotification。
 */
function sendBrowserNotification(title: string, body: string, tag: string): void {
  if (typeof window === 'undefined' || !('Notification' in window)) {
    return;
  }
  if (window.Notification.permission !== 'granted') {
    return;
  }

  try {
    const notification = new window.Notification(title, {
      body,
      icon: '/pwa-192x192.png',
      badge: '/pwa-192x192.png',
      tag,
    });
    notification.onclick = () => {
      window.focus();
      notification.close();
    };
  } catch (e) {
    console.error('[sendBrowserNotification] 原生通知 API 失败，尝试 ServiceWorker 降级:', e);
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.ready
        .then((reg) =>
          reg.showNotification(title, {
            body,
            icon: '/pwa-192x192.png',
            tag,
          })
        )
        .catch((e) => {
          console.error('[sendBrowserNotification] ServiceWorker 通知推送失败:', e);
        });
    }
  }
}

/**
 * React.lazy chunk 加载失败时的兜底边界，避免整页白屏
 */
class LazyBoundary extends React.Component<
  { children: React.ReactNode; label?: string },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(e: unknown) { console.error('[LazyBoundary] chunk 加载失败:', e); }
  render() {
    if (this.state.failed) {
      return (
        <div className="flex-1 min-h-[260px] flex flex-col items-center justify-center gap-2 text-[#787b86] text-sm">
          <span>{this.props.label ?? '模块'}加载失败</span>
          <button
            type="button"
            onClick={() => this.setState({ failed: false })}
            className="px-3 py-1 text-xs border border-[#2a2e39] rounded hover:text-white cursor-pointer"
          >
            重试
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function App() {
  const workspaceMode = useMarketStore((s) => s.workspaceMode);
  const isDemoData = useMarketStore((s) => s.isDemoData);
  const mobileBottomTab = useMarketStore((s) => s.mobileBottomTab);
  const setMobileBottomTab = useMarketStore((s) => s.setMobileBottomTab);
  const isMobileWatchlistOpen = useMarketStore((s) => s.isMobileWatchlistOpen);
  const setMobileWatchlistOpen = useMarketStore((s) => s.setMobileWatchlistOpen);
  const triggeredAlerts = useMarketStore((s) => s.triggeredAlerts);
  const dismissTriggeredAlert = useMarketStore((s) => s.dismissTriggeredAlert);
  const setSelectedSymbol = useMarketStore((s) => s.setSelectedSymbol);
  const setAlertModalOpen = useMarketStore((s) => s.setAlertModalOpen);
  const isCommandPaletteOpen = useMarketStore((s) => s.isCommandPaletteOpen);
  const setCommandPaletteOpen = useMarketStore((s) => s.setCommandPaletteOpen);
  const stepSelectedSymbol = useMarketStore((s) => s.stepSelectedSymbol);
  const togglePeriodIntradayDaily = useMarketStore((s) => s.togglePeriodIntradayDaily);

  const [notificationPermission, setNotificationPermission] = useState<
    NotificationPermission | 'unsupported'
  >(() => {
    if (typeof window === 'undefined' || !('Notification' in window)) {
      return 'unsupported';
    }
    return window.Notification.permission;
  });

  // 请求浏览器通知权限
  const handleRequestNotificationPermission = useCallback(async () => {
    if (typeof window === 'undefined' || !('Notification' in window)) {
      setNotificationPermission('unsupported');
      return;
    }
    try {
      const result = await window.Notification.requestPermission();
      setNotificationPermission(result);
      if (result === 'granted') {
        sendBrowserNotification(
          'AlphaPulse L1 价格预警已启用',
          '当自选股触及设定的涨跌幅或目标价阈值时，您将收到实时系统推送。',
          'alphapulse-permission-granted'
        );
      }
    } catch (e) {
      console.error('[handleRequestNotificationPermission] 通知权限请求失败:', e);
    }
  }, []);

  // 发送测试预警通知（验证浏览器 Notification API 与终端内横幅）
  const handleSendTestNotification = useCallback(() => {
    const state = useMarketStore.getState();
    const activeQuote = state.quotes[state.selectedSymbol];
    if (!activeQuote) return;

    const testMessage = `${activeQuote.name} (${activeQuote.symbol}) 预警通道测试：当前现价 ${formatPrice(
      activeQuote.price
    )} 元 (${formatSignedPercent(activeQuote.changePercent)})`;

    if (
      typeof window !== 'undefined' &&
      'Notification' in window &&
      window.Notification.permission === 'default'
    ) {
      void handleRequestNotificationPermission();
    }

    sendBrowserNotification(
      `[预警测试] ${activeQuote.name} (${activeQuote.symbol})`,
      testMessage,
      `test-${Date.now()}`
    );

    // 同步注入一条测试提醒横幅以提供即时视觉反馈
    const tempRule = state.addAlertRule({
      symbol: activeQuote.symbol,
      stockName: activeQuote.name,
      condition: 'CHANGE_PCT_ABOVE',
      threshold: Number((activeQuote.changePercent - 0.01).toFixed(2)),
    });
    state.markRulesTriggered([
      {
        ruleId: tempRule.id,
        price: activeQuote.price,
        changePercent: activeQuote.changePercent,
        message: testMessage,
        timestamp: Date.now(),
      },
    ]);
  }, [handleRequestNotificationPermission]);

  // 1. 建立 WebSocket 实时行情连接
  useEffect(() => {
    marketWsClient.connect();
    return () => {
      marketWsClient.disconnect();
    };
  }, []);

  // 2. 核心价格/涨跌幅预警监控引擎：
  // 通过 Zustand 底层 store.subscribe 监听行情快照与规则变化，避免 App 根组件因高频 Tick 重渲染
  useEffect(() => {
    const checkAlerts = (state: ReturnType<typeof useMarketStore.getState>) => {
      const { alertRules, quotes, markRulesTriggered } = state;
      if (alertRules.length === 0) return;

      const newlyTriggered: {
        ruleId: string;
        price: number;
        changePercent: number;
        message: string;
        timestamp: number;
      }[] = [];

      const now = Date.now();
      for (const rule of alertRules) {
        if (!rule.enabled || rule.triggered) continue;
        const tick = quotes[rule.symbol];
        if (!tick) continue;

        if (evaluatePriceAlertRule(rule, tick)) {
          const message = buildAlertTriggerMessage(rule, tick);
          newlyTriggered.push({
            ruleId: rule.id,
            price: tick.price,
            changePercent: tick.changePercent,
            message,
            timestamp: now,
          });

          // 触发浏览器 Notification API 推送
          sendBrowserNotification(
            `行情预警触发 · ${tick.name} (${tick.code})`,
            message,
            `alert-${rule.id}`
          );
        }
      }

      if (newlyTriggered.length > 0) {
        markRulesTriggered(newlyTriggered);
      }
    };

    // 初始立即校验一次，随后在每次 WebSocket 批量快照或新增预警规则时自动比对
    checkAlerts(useMarketStore.getState());
    const unsubscribe = useMarketStore.subscribe((state) => {
      checkAlerts(state);
    });

    return unsubscribe;
  }, []);

  // 3. 通达信式全局键盘盲操引擎 (↑/↓切股, Space/F5切分时日K, 任意键唤出键盘精灵)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const activeTag = (document.activeElement?.tagName || '').toUpperCase();
      const isInputFocused =
        activeTag === 'INPUT' ||
        activeTag === 'TEXTAREA' ||
        activeTag === 'SELECT' ||
        (document.activeElement as HTMLElement)?.isContentEditable;

      if (isInputFocused || useMarketStore.getState().isCommandPaletteOpen) {
        return;
      }

      if (e.key === 'ArrowUp') {
        e.preventDefault();
        stepSelectedSymbol(-1);
        return;
      }

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        stepSelectedSymbol(1);
        return;
      }

      if (e.key === ' ' || e.key === 'F5') {
        e.preventDefault();
        togglePeriodIntradayDaily();
        return;
      }

      // 单字符输入（0-9 或 a-z / A-Z），且未按下 Ctrl / Alt / Meta 快捷键组合
      if (/^[0-9a-zA-Z]$/.test(e.key) && !e.ctrlKey && !e.altKey && !e.metaKey) {
        e.preventDefault();
        setCommandPaletteOpen(true, e.key);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [stepSelectedSymbol, togglePeriodIntradayDaily, setCommandPaletteOpen]);

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-[#0d0e12] text-[#d1d4dc]">
      {/* 1. 顶部三区导航栏与核心指数跑马灯监控条 */}
      <TopNavBar />
      <IndexTickerBar />

      {/* 2. 实时触发的价格预警浮动推送通知栏 (Top-Right Toast Stack) */}
      {triggeredAlerts.length > 0 && (
        <div
          aria-live="polite"
          data-testid="triggered-alert-banner-list"
          className="fixed top-12 right-4 z-40 flex flex-col gap-2 w-80 sm:w-96 pointer-events-none"
        >
          {triggeredAlerts.slice(0, 3).map((evt) => (
            <div
              key={evt.id}
              role="status"
              className="pointer-events-auto flex items-start justify-between gap-2.5 p-3 rounded-lg bg-[#1e222d] border border-[#F59E0B] shadow-2xl text-xs"
            >
              <div
                onClick={() => {
                  setSelectedSymbol(evt.symbol);
                  setAlertModalOpen(true);
                }}
                className="flex items-start gap-2 min-w-0 cursor-pointer"
              >
                <BellRing className="w-4 h-4 text-[#F59E0B] shrink-0 mt-0.5" />
                <div className="min-w-0">
                  <div className="font-semibold text-[#F59E0B] flex items-center gap-1.5">
                    <span>涨跌幅/价格预警触发</span>
                    <span className="font-mono text-[10px] text-[#9ca3af]">
                      {new Date(evt.timestamp).toLocaleTimeString('zh-CN', {
                        hour12: false,
                      })}
                    </span>
                  </div>
                  <p className="mt-1 text-[#d1d4dc] leading-snug break-words">
                    {evt.message}
                  </p>
                </div>
              </div>
              <button
                type="button"
                aria-label="关闭此条预警通知"
                onClick={() => dismissTriggeredAlert(evt.id)}
                className="p-1 text-[#787b86] hover:text-white shrink-0 cursor-pointer"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* 3. 主工作台：PC 端三栏满视口网格 (>=768px) / 移动端单列自适应流 (<768px) */}
      <main className="flex-1 min-h-0 flex flex-col md:grid md:grid-cols-[276px_minmax(0,1fr)_308px] overflow-hidden">
        {/* 左侧栏 (PC 常驻)：自选股高密度列表 (支持代码/拼音首字母过滤) */}
        <div className="hidden md:flex md:flex-col h-full min-h-0 overflow-hidden">
          <WatchlistPanel />
        </div>

        {/* 中间主区域：100% 满屏一级工作台 (彻底铲除上下硬拼割裂) */}
        <div className="flex flex-col flex-1 min-h-0 overflow-hidden md:border-r md:border-[#2a2e39]">
          <StockQuoteHeader />
          <LazyBoundary label="工作台">
            <React.Suspense
              fallback={
                <div className="flex-1 min-h-[260px] flex items-center justify-center text-[#787b86] text-sm">
                  工作台加载中…
                </div>
              }
            >
              {workspaceMode === 'chart' && (
                <>
                  <UltraShortStockDiagnosticStrip />
                  <FinancialChart />
                </>
              )}
              {workspaceMode === 'auction' && <CallAuctionRadarPlugin />}
              {workspaceMode === 'quant' && <UltraShortQuantWorkbench />}
            </React.Suspense>
          </LazyBoundary>

          {/* 移动端专属 (<768px)：底部分屏 Tab 切换展示【五档盘口】、【超短游资】、【实时成交简表】、【基本面/指标】 */}
          <div className="flex md:hidden flex-col h-[325px] shrink-0 border-t border-[#2a2e39] bg-[#1e222d] pb-safe">
            <div
              role="tablist"
              aria-label="移动端盘口与指标切换"
              className="grid grid-cols-4 border-b border-[#2a2e39] bg-[#131722] shrink-0"
            >
              <button
                type="button"
                role="tab"
                aria-selected={mobileBottomTab === 'orderbook'}
                onClick={() => setMobileBottomTab('orderbook')}
                className={`min-h-[42px] text-xs font-medium transition-colors whitespace-nowrap cursor-pointer ${
                  mobileBottomTab === 'orderbook'
                    ? 'text-white border-b-2 border-[#2962ff] bg-[#1e222d]'
                    : 'text-[#787b86] hover:text-[#d1d4dc]'
                }`}
              >
                五档盘口
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={mobileBottomTab === 'quant'}
                onClick={() => setMobileBottomTab('quant')}
                className={`min-h-[42px] text-xs font-medium transition-colors whitespace-nowrap cursor-pointer ${
                  mobileBottomTab === 'quant'
                    ? 'text-[#F6465D] font-bold border-b-2 border-[#F6465D] bg-[#1e222d]'
                    : 'text-[#F59E0B] hover:text-white'
                }`}
              >
                超短游资
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={mobileBottomTab === 'trades'}
                onClick={() => setMobileBottomTab('trades')}
                className={`min-h-[42px] text-xs font-medium transition-colors whitespace-nowrap cursor-pointer ${
                  mobileBottomTab === 'trades'
                    ? 'text-white border-b-2 border-[#2962ff] bg-[#1e222d]'
                    : 'text-[#787b86] hover:text-[#d1d4dc]'
                }`}
              >
                实时成交
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={mobileBottomTab === 'fundamentals'}
                onClick={() => setMobileBottomTab('fundamentals')}
                className={`min-h-[42px] text-xs font-medium transition-colors whitespace-nowrap cursor-pointer ${
                  mobileBottomTab === 'fundamentals'
                    ? 'text-white border-b-2 border-[#2962ff] bg-[#1e222d]'
                    : 'text-[#787b86] hover:text-[#d1d4dc]'
                }`}
              >
                基本面/指标
              </button>
            </div>

            <div className="flex-1 min-h-0 overflow-y-auto">
              {mobileBottomTab === 'orderbook' && <OrderBook5Panel />}
              {mobileBottomTab === 'quant' && (
                <LazyBoundary label="超短模块">
                  <React.Suspense
                    fallback={<div className="p-4 text-center text-[#787b86] text-xs">加载中…</div>}
                  >
                    <UltraShortQuantWorkbench compact />
                  </React.Suspense>
                </LazyBoundary>
              )}
              {mobileBottomTab === 'trades' && (
                <TradeTicksAndMetricsPanel forcedTab="trades" />
              )}
              {mobileBottomTab === 'fundamentals' && (
                <TradeTicksAndMetricsPanel forcedTab="fundamentals" />
              )}
            </div>
          </div>
        </div>

        {/* 右侧栏 (PC 常驻)：上半部 Level-1 五档盘口 + 委比条，下半部实时成交明细与换手指标 */}
        <div className="hidden md:flex md:flex-col h-full min-h-0 overflow-hidden bg-[#1e222d]">
          <OrderBook5Panel />
          <TradeTicksAndMetricsPanel />
        </div>
      </main>

      {/* 移动端自选股快速切换抽屉 (<768px) */}
      {isMobileWatchlistOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="移动端自选股切换抽屉"
          className="fixed inset-0 z-50 md:hidden flex bg-black/70"
          onClick={() => setMobileWatchlistOpen(false)}
        >
          <div
            className="w-[84%] max-w-xs h-full bg-[#1e222d] flex flex-col shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-3 py-2.5 border-b border-[#2a2e39] bg-[#131722]">
              <span className="text-xs font-semibold text-white">
                切换股票标的 (支持拼音/代码)
              </span>
              <button
                type="button"
                aria-label="关闭自选股列表"
                onClick={() => setMobileWatchlistOpen(false)}
                className="p-1 text-[#787b86] hover:text-white cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="flex-1 min-h-0 overflow-hidden">
              <WatchlistPanel />
            </div>
          </div>
        </div>
      )}

      {/* 选定股票的价格与涨跌幅提醒配置弹窗 */}
      <PriceAlertModal
        notificationPermission={notificationPermission}
        onRequestPermission={handleRequestNotificationPermission}
        onSendTestNotification={handleSendTestNotification}
      />

      {/* PWA 安装与终端参数弹窗 */}
      <PWAInstallModal />

      {/* 通达信键盘精灵全市场检索浮层 */}
      <CommandPaletteModal />

      {/* 首屏种子数据演示标记 */}
      {isDemoData && (
        <div
          className="fixed top-14 left-1/2 -translate-x-1/2 z-50 px-3 py-1 rounded-full bg-[#F59E0B]/15 border border-[#F59E0B]/50 text-[#F59E0B] text-xs font-medium pointer-events-none"
          role="status"
          aria-live="polite"
        >
          演示数据 · 等待 WebSocket 实时行情接入
        </div>
      )}

      {/* 非侵入式错误提示 */}
      <ErrorToast />
    </div>
  );
}
