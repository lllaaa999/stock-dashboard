import React, { useEffect, useState } from 'react';
import { Bell, BellRing, CheckCircle2, Plus, RotateCcw, Trash2, X } from 'lucide-react';
import { useMarketStore } from '../store/useMarketStore';
import type { AlertConditionType } from '../types/market';
import {
  formatAlertConditionLabel,
  formatPrice,
  formatSignedPercent,
  getSignedColorClass,
} from '../utils/marketCalc';

interface PriceAlertModalProps {
  notificationPermission: NotificationPermission | 'unsupported';
  onRequestPermission: () => Promise<void>;
  onSendTestNotification: () => void;
}

export const PriceAlertModal: React.FC<PriceAlertModalProps> = ({
  notificationPermission,
  onRequestPermission,
  onSendTestNotification,
}) => {
  const isOpen = useMarketStore((s) => s.isAlertModalOpen);
  const setOpen = useMarketStore((s) => s.setAlertModalOpen);
  const selectedSymbol = useMarketStore((s) => s.selectedSymbol);
  const quote = useMarketStore((s) => s.quotes[s.selectedSymbol]);
  const alertRules = useMarketStore((s) => s.alertRules);
  const triggeredAlerts = useMarketStore((s) => s.triggeredAlerts);

  const addAlertRule = useMarketStore((s) => s.addAlertRule);
  const removeAlertRule = useMarketStore((s) => s.removeAlertRule);
  const toggleAlertRule = useMarketStore((s) => s.toggleAlertRule);
  const resetAlertRule = useMarketStore((s) => s.resetAlertRule);
  const clearAllTriggeredAlerts = useMarketStore((s) => s.clearAllTriggeredAlerts);

  const [condition, setCondition] = useState<AlertConditionType>('CHANGE_PCT_ABOVE');
  const [thresholdInput, setThresholdInput] = useState<string>('3.00');
  const conditionRef = React.useRef<AlertConditionType>('CHANGE_PCT_ABOVE');
  const thresholdInputRef = React.useRef<string>('3.00');
  const [errorMsg, setErrorMsg] = useState<string>('');
  const [scopeTab, setScopeTab] = useState<'current' | 'all'>('current');

  const updateCondition = (nextCond: AlertConditionType) => {
    conditionRef.current = nextCond;
    setCondition(nextCond);
  };

  const updateThresholdInput = (val: string) => {
    thresholdInputRef.current = val;
    setThresholdInput(val);
  };

  // 当切换股票或切换预警类型时，初始化合理的默认参考值
  useEffect(() => {
    if (!quote) return;
    setErrorMsg('');
    if (condition === 'CHANGE_PCT_ABOVE') {
      const suggested = Math.max(0.5, Number((quote.changePercent + 1.0).toFixed(2)));
      updateThresholdInput(suggested.toFixed(2));
    } else if (condition === 'CHANGE_PCT_BELOW') {
      const suggested = Math.min(-0.5, Number((quote.changePercent - 1.5).toFixed(2)));
      updateThresholdInput(suggested.toFixed(2));
    } else if (condition === 'PRICE_ABOVE') {
      updateThresholdInput((quote.price * 1.02).toFixed(2));
    } else if (condition === 'PRICE_BELOW') {
      updateThresholdInput((quote.price * 0.98).toFixed(2));
    }
  }, [selectedSymbol, condition, quote?.symbol]);

  if (!isOpen || !quote) return null;

  const isChangePctMode =
    condition === 'CHANGE_PCT_ABOVE' || condition === 'CHANGE_PCT_BELOW';

  const handleAddRule = (e: React.FormEvent) => {
    e.preventDefault();
    const activeCondition = conditionRef.current;
    const activeIsChangePct =
      activeCondition === 'CHANGE_PCT_ABOVE' || activeCondition === 'CHANGE_PCT_BELOW';
    const trimmed = thresholdInputRef.current.trim();
    if (!trimmed) {
      setErrorMsg('请输入有效的预警阈值数值');
      return;
    }
    const parsed = Number(trimmed);
    if (!Number.isFinite(parsed)) {
      setErrorMsg('预警阈值必须为合法数字');
      return;
    }
    if (!activeIsChangePct && parsed <= 0) {
      setErrorMsg('目标股票价格必须大于 0');
      return;
    }
    if (activeIsChangePct && (parsed < -30 || parsed > 30)) {
      setErrorMsg('A股涨跌幅阈值需在 -30% 至 +30% 范围内');
      return;
    }

    setErrorMsg('');
    addAlertRule({
      symbol: quote.symbol,
      stockName: quote.name,
      condition: activeCondition,
      threshold: parsed,
    });
  };

  const applyQuickPreset = (cond: AlertConditionType, val: number) => {
    updateCondition(cond);
    updateThresholdInput(val.toFixed(2));
    setErrorMsg('');
  };

  const visibleRules =
    scopeTab === 'current'
      ? alertRules.filter((r) => r.symbol === selectedSymbol)
      : alertRules;

  const priceColor = getSignedColorClass(quote.change);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-price-alert-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 select-none"
      onClick={() => setOpen(false)}
    >
      <div
        className="w-full max-w-xl rounded-lg bg-[#1e222d] border border-[#2a2e39] text-[#d1d4dc] shadow-2xl overflow-hidden flex flex-col max-h-[88vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 弹窗头部 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#2a2e39] bg-[#131722] shrink-0">
          <div className="flex items-center gap-2">
            <BellRing className="w-4 h-4 text-[#F59E0B]" />
            <h2 id="modal-price-alert-title" className="text-sm font-semibold text-white">
              价格与涨跌幅智能预警 ({quote.name} {quote.symbol})
            </h2>
          </div>
          <button
            type="button"
            aria-label="关闭价格预警弹窗"
            onClick={() => setOpen(false)}
            className="p-1 text-[#787b86] hover:text-white cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-4 space-y-4 overflow-y-auto text-xs flex-1 min-h-0">
          {/* 1. 浏览器系统通知权限状态栏 */}
          <div className="flex flex-wrap items-center justify-between gap-2 p-3 rounded bg-[#131722] border border-[#2a2e39]">
            <div className="space-y-0.5">
              <div className="font-medium text-white flex items-center gap-1.5">
                <span>浏览器 Notification 推送状态：</span>
                <span
                  className={`font-mono ${
                    notificationPermission === 'granted'
                      ? 'text-[#0ECB81]'
                      : notificationPermission === 'denied'
                      ? 'text-[#F6465D]'
                      : 'text-[#F59E0B]'
                  }`}
                >
                  {notificationPermission === 'granted'
                    ? '已开启系统级桌面/手机推送'
                    : notificationPermission === 'denied'
                    ? '系统通知被阻止（已启用终端内实时横幅提醒）'
                    : notificationPermission === 'unsupported'
                    ? '当前环境不支持系统通知（已启用终端内横幅提醒）'
                    : '未授权（默认启用终端横幅，可点击右侧开启系统通知）'}
                </span>
              </div>
              <p className="text-[11px] text-[#787b86]">
                当实时 Level-1 行情触及设定阈值时，将同步调用浏览器 Notification API 与看盘工作台预警横幅。
              </p>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              {notificationPermission === 'default' && (
                <button
                  type="button"
                  onClick={() => {
                    void onRequestPermission();
                  }}
                  className="px-2.5 py-1.5 rounded bg-[#2962ff] text-white font-medium hover:bg-[#1e53e5] transition-colors whitespace-nowrap cursor-pointer"
                >
                  开启浏览器通知权限
                </button>
              )}
              <button
                type="button"
                onClick={onSendTestNotification}
                className="px-2.5 py-1.5 rounded bg-[#2a2e39] text-[#d1d4dc] hover:text-white hover:bg-[#363c4e] transition-colors whitespace-nowrap cursor-pointer"
              >
                发送测试推送
              </button>
            </div>
          </div>

          {/* 2. 当前选定股票实时基准行情与新建预警表单 */}
          <form
            onSubmit={handleAddRule}
            className="p-3.5 rounded bg-[#131722] border border-[#2a2e39] space-y-3"
          >
            <div className="flex items-center justify-between border-b border-[#2a2e39] pb-2">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-white text-sm">{quote.name}</span>
                <span className="font-mono text-[#787b86]">{quote.symbol}</span>
              </div>
              <div className="flex items-center gap-3 font-mono tabular-nums">
                <span className="text-[#787b86]">当前价:</span>
                <span className={`font-bold text-sm ${priceColor}`}>
                  {formatPrice(quote.price)}
                </span>
                <span className={`font-semibold ${priceColor}`}>
                  ({formatSignedPercent(quote.changePercent)})
                </span>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-12 gap-2.5 items-end">
              <div className="sm:col-span-5">
                <label
                  htmlFor="alert-condition-select"
                  className="block text-[11px] text-[#9ca3af] mb-1"
                >
                  预警触发条件
                </label>
                <select
                  id="alert-condition-select"
                  aria-label="预警触发条件"
                  value={condition}
                  onChange={(e) => updateCondition(e.target.value as AlertConditionType)}
                  className="w-full h-9 px-2.5 rounded bg-[#1e222d] border border-[#2a2e39] text-white text-xs focus:outline-none focus:border-[#2962ff]"
                >
                  <option value="CHANGE_PCT_ABOVE">涨跌幅高于或等于 (≥ %)</option>
                  <option value="CHANGE_PCT_BELOW">涨跌幅低于或等于 (≤ %)</option>
                  <option value="PRICE_ABOVE">最新价高于或等于 (≥ 元)</option>
                  <option value="PRICE_BELOW">最新价低于或等于 (≤ 元)</option>
                </select>
              </div>

              <div className="sm:col-span-4">
                <label
                  htmlFor="alert-threshold-input"
                  className="block text-[11px] text-[#9ca3af] mb-1"
                >
                  {isChangePctMode ? '涨跌幅阈值 (%)' : '目标价格阈值 (元)'}
                </label>
                <div className="relative flex items-center">
                  <input
                    id="alert-threshold-input"
                    type="number"
                    step="0.01"
                    aria-label="预警阈值数值"
                    value={thresholdInput}
                    onChange={(e) => {
                      updateThresholdInput(e.target.value);
                      if (errorMsg) setErrorMsg('');
                    }}
                    placeholder={isChangePctMode ? '例如 3.00' : '例如 1600.00'}
                    className="w-full h-9 pl-2.5 pr-8 rounded bg-[#1e222d] border border-[#2a2e39] font-mono tabular-nums text-white text-xs focus:outline-none focus:border-[#2962ff]"
                  />
                  <span className="absolute right-2.5 text-[#787b86] font-mono">
                    {isChangePctMode ? '%' : '元'}
                  </span>
                </div>
              </div>

              <div className="sm:col-span-3">
                <button
                  type="submit"
                  className="w-full h-9 flex items-center justify-center gap-1 rounded bg-[#2962ff] text-white font-medium hover:bg-[#1e53e5] transition-colors whitespace-nowrap cursor-pointer"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>添加预警</span>
                </button>
              </div>
            </div>

            {/* 快捷涨跌幅预设按钮 */}
            <div className="flex flex-wrap items-center gap-1.5 pt-1">
              <span className="text-[11px] text-[#787b86] mr-1">快捷涨跌幅阈值:</span>
              {[
                { label: '立即触发测试 (≥当前-0.5%)', cond: 'CHANGE_PCT_ABOVE' as const, val: Number((quote.changePercent - 0.5).toFixed(2)) },
                { label: '涨幅 ≥ +3.0%', cond: 'CHANGE_PCT_ABOVE' as const, val: 3.0 },
                { label: '涨幅 ≥ +5.0%', cond: 'CHANGE_PCT_ABOVE' as const, val: 5.0 },
                { label: '涨停预警 (+9.9%)', cond: 'CHANGE_PCT_ABOVE' as const, val: 9.9 },
                { label: '跌幅 ≤ -2.0%', cond: 'CHANGE_PCT_BELOW' as const, val: -2.0 },
                { label: '跌幅 ≤ -5.0%', cond: 'CHANGE_PCT_BELOW' as const, val: -5.0 },
              ].map((preset) => (
                <button
                  key={preset.label}
                  type="button"
                  onClick={() => applyQuickPreset(preset.cond, preset.val)}
                  className="px-2 py-0.5 rounded bg-[#1e222d] border border-[#2a2e39] text-[11px] font-mono tabular-nums text-[#9ca3af] hover:text-white hover:border-[#38BDF8] transition-colors cursor-pointer"
                >
                  {preset.label}
                </button>
              ))}
            </div>

            {errorMsg && (
              <p role="alert" className="text-xs text-[#F6465D] font-medium">
                {errorMsg}
              </p>
            )}
          </form>

          {/* 3. 已配置的预警规则列表 */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1 bg-[#131722] p-0.5 rounded border border-[#2a2e39]">
                <button
                  type="button"
                  onClick={() => setScopeTab('current')}
                  className={`px-2.5 py-1 rounded text-[11px] font-medium transition-colors cursor-pointer ${
                    scopeTab === 'current'
                      ? 'bg-[#2a2e39] text-white'
                      : 'text-[#787b86] hover:text-[#d1d4dc]'
                  }`}
                >
                  当前股票 ({alertRules.filter((r) => r.symbol === selectedSymbol).length})
                </button>
                <button
                  type="button"
                  onClick={() => setScopeTab('all')}
                  className={`px-2.5 py-1 rounded text-[11px] font-medium transition-colors cursor-pointer ${
                    scopeTab === 'all'
                      ? 'bg-[#2a2e39] text-white'
                      : 'text-[#787b86] hover:text-[#d1d4dc]'
                  }`}
                >
                  全部标的预警 ({alertRules.length})
                </button>
              </div>
              <span className="text-[11px] text-[#787b86]">
                实时对比 WebSocket 快照流自动触发
              </span>
            </div>

            {visibleRules.length === 0 ? (
              <div className="p-6 text-center rounded bg-[#131722] border border-[#2a2e39] text-[#787b86]">
                当前暂无价格预警规则，请在上方设定涨跌幅或价格阈值后点击“添加预警”。
              </div>
            ) : (
              <div className="divide-y divide-[#2a2e39] rounded bg-[#131722] border border-[#2a2e39]">
                {visibleRules.map((rule) => {
                  const isUpCond =
                    rule.condition === 'CHANGE_PCT_ABOVE' ||
                    rule.condition === 'PRICE_ABOVE';
                  return (
                    <div
                      key={rule.id}
                      data-testid="price-alert-rule-row"
                      className="flex items-center justify-between gap-2 px-3 py-2.5"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-white">
                            {rule.stockName}
                          </span>
                          <span className="font-mono text-[11px] text-[#787b86]">
                            {rule.symbol}
                          </span>
                          <span
                            className={`font-mono tabular-nums font-semibold ${
                              isUpCond ? 'text-[#F6465D]' : 'text-[#0ECB81]'
                            }`}
                          >
                            {formatAlertConditionLabel(rule.condition, rule.threshold)}
                          </span>
                        </div>

                        <div className="mt-0.5 text-[11px] text-[#787b86] font-mono tabular-nums">
                          {rule.triggered ? (
                            <span className="text-[#F59E0B] flex items-center gap-1">
                              <CheckCircle2 className="w-3 h-3 inline" />
                              <span>
                                已触发 · 触发价 {formatPrice(rule.triggeredPrice)} (
                                {formatSignedPercent(rule.triggeredChangePercent)})
                              </span>
                            </span>
                          ) : rule.enabled ? (
                            <span className="text-[#0ECB81]">监控中 · 等待行情触达阈值</span>
                          ) : (
                            <span>已暂停监控</span>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center gap-1.5 shrink-0">
                        {rule.triggered ? (
                          <button
                            type="button"
                            aria-label={`重新启用预警 ${rule.stockName}`}
                            onClick={() => resetAlertRule(rule.id)}
                            className="flex items-center gap-1 px-2 py-1 rounded bg-[#2a2e39] text-[#F59E0B] hover:bg-[#363c4e] transition-colors cursor-pointer"
                          >
                            <RotateCcw className="w-3 h-3" />
                            <span>重置监控</span>
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={() => toggleAlertRule(rule.id)}
                            className={`px-2 py-1 rounded border transition-colors cursor-pointer ${
                              rule.enabled
                                ? 'bg-[#1e222d] border-[#2a2e39] text-[#d1d4dc] hover:text-white'
                                : 'bg-[#1e222d] border-[#2a2e39] text-[#787b86] hover:text-white'
                            }`}
                          >
                            {rule.enabled ? '暂停' : '启用'}
                          </button>
                        )}
                        <button
                          type="button"
                          aria-label={`删除预警 ${rule.stockName}`}
                          onClick={() => removeAlertRule(rule.id)}
                          className="p-1.5 rounded text-[#787b86] hover:text-[#F6465D] hover:bg-[#2a2e39] transition-colors cursor-pointer"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* 4. 历史触发推送日志 */}
          {triggeredAlerts.length > 0 && (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-white flex items-center gap-1.5">
                  <Bell className="w-3.5 h-3.5 text-[#F59E0B]" />
                  <span>最近触发记录 ({triggeredAlerts.length})</span>
                </span>
                <button
                  type="button"
                  onClick={clearAllTriggeredAlerts}
                  className="text-[11px] text-[#787b86] hover:text-white cursor-pointer"
                >
                  清空记录
                </button>
              </div>
              <div className="divide-y divide-[#2a2e39] rounded bg-[#131722] border border-[#2a2e39] max-h-36 overflow-y-auto">
                {triggeredAlerts.map((evt) => (
                  <div
                    key={evt.id}
                    className="px-3 py-2 text-[11px] flex items-center justify-between gap-2"
                  >
                    <span className="text-[#d1d4dc]">{evt.message}</span>
                    <span className="font-mono tabular-nums text-[#787b86] shrink-0">
                      {new Date(evt.timestamp).toLocaleTimeString('zh-CN', {
                        hour12: false,
                      })}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="flex justify-end px-4 py-2.5 border-t border-[#2a2e39] bg-[#131722] shrink-0">
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="px-4 py-1.5 rounded bg-[#2a2e39] text-xs font-medium text-white hover:bg-[#363c4e] transition-colors cursor-pointer"
          >
            完成
          </button>
        </div>
      </div>
    </div>
  );
};
