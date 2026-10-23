import React from 'react';
import { X, Download, Smartphone, Sliders } from 'lucide-react';
import { usePWAInstall } from '../hooks/usePWAInstall';
import { marketWsClient } from '../services/wsClient';
import { useMarketStore } from '../store/useMarketStore';
import type { MarketScenario } from '../types/market';

export const PWAInstallModal: React.FC = () => {
  const isOpen = useMarketStore((s) => s.isArchModalOpen);
  const setOpen = useMarketStore((s) => s.setArchModalOpen);
  const batchWindowMs = useMarketStore((s) => s.batchWindowMs);
  const selectedSymbol = useMarketStore((s) => s.selectedSymbol);
  const quote = useMarketStore((s) => s.quotes[s.selectedSymbol]);
  const triggerScenario = useMarketStore((s) => s.triggerScenario);

  const { isInstallable, isInstalled, isIOS, install } = usePWAInstall();

  if (!isOpen) return null;

  const currentScenario: MarketScenario =
    quote?.phase === 'LIMIT_UP'
      ? 'limit_up'
      : quote?.phase === 'LIMIT_DOWN'
      ? 'limit_down'
      : quote?.phase === 'CALL_AUCTION'
      ? 'call_auction'
      : 'normal';

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-terminal-settings-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={() => setOpen(false)}
    >
      <div
        className="w-full max-w-lg rounded-lg bg-[#1e222d] border border-[#2a2e39] text-[#d1d4dc] shadow-xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#2a2e39] bg-[#131722]">
          <h2
            id="modal-terminal-settings-title"
            className="text-sm font-semibold text-white"
          >
            终端参数设置与 PWA 离线安装
          </h2>
          <button
            type="button"
            aria-label="关闭设置弹窗"
            onClick={() => setOpen(false)}
            className="p-1 text-[#787b86] hover:text-white cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-4 space-y-4 max-h-[80vh] overflow-y-auto text-xs">
          {/* 1. PWA 应用安装区块 */}
          <div className="p-3 rounded bg-[#131722] border border-[#2a2e39]">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="text-xs font-semibold text-white flex items-center gap-1.5">
                  <Smartphone className="w-3.5 h-3.5 text-[#38BDF8]" />
                  <span>安装为独立桌面 / 手机看盘应用 (PWA)</span>
                </h3>
                <p className="mt-1 text-[11px] text-[#787b86]">
                  支持全屏独立窗口运行（standalone）、iOS 刘海与底部安全区适配及静态资源离线缓存。
                </p>
              </div>
              {isInstalled ? (
                <span className="text-[11px] text-[#0ECB81] font-medium whitespace-nowrap shrink-0">
                  已安装为独立应用
                </span>
              ) : isInstallable ? (
                <button
                  type="button"
                  onClick={() => {
                    void install();
                  }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-[#2962ff] text-white font-medium hover:bg-[#1e53e5] transition-colors whitespace-nowrap shrink-0 cursor-pointer"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>立即安装终端</span>
                </button>
              ) : null}
            </div>

            {!isInstalled && !isInstallable && (
              <div className="mt-2.5 pt-2.5 border-t border-[#2a2e39] text-[11px] text-[#9ca3af]">
                {isIOS ? (
                  <p>
                    iOS Safari 安装指引：点击浏览器底部工具栏的<strong>「分享」</strong>按钮，向下滑动并选择<strong>「添加到主屏幕」</strong>即可全屏启动。
                  </p>
                ) : (
                  <p>
                    桌面 Chrome / Edge 安装指引：点击浏览器地址栏右侧的<strong>「安装 AlphaPulse」</strong>图标，或在菜单中选择“安装应用”。
                  </p>
                )}
              </div>
            )}
          </div>

          {/* 2. 服务端快照节流时间窗口控制 (100ms ~ 200ms) */}
          <div className="p-3 rounded bg-[#131722] border border-[#2a2e39]">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-white flex items-center gap-1.5">
                <Sliders className="w-3.5 h-3.5 text-[#F59E0B]" />
                <span>服务端 WebSocket 快照合并节流窗口 (Batch Throttle)</span>
              </span>
              <span className="font-mono tabular-nums text-[#F59E0B] font-semibold">
                {batchWindowMs} ms
              </span>
            </div>
            <p className="mt-1 text-[11px] text-[#787b86]">
              服务端将高频上游行情在时间窗口内执行字典合并后批量下发，杜绝逐条广播引发前端主线程阻塞。
            </p>
            <div className="grid grid-cols-3 gap-2 mt-2.5">
              {[100, 150, 200].map((ms) => (
                <button
                  key={ms}
                  type="button"
                  onClick={() => marketWsClient.setServerBatchWindow(ms)}
                  className={`py-1.5 rounded font-mono tabular-nums font-medium border transition-colors cursor-pointer ${
                    batchWindowMs === ms
                      ? 'bg-[#2962ff] border-[#2962ff] text-white'
                      : 'bg-[#1e222d] border-[#2a2e39] text-[#9ca3af] hover:text-white'
                  }`}
                >
                  {ms}ms 窗口
                </button>
              ))}
            </div>
          </div>

          {/* 3. Level-1 极端盘口空档保护验证 */}
          {quote && (
            <div className="p-3 rounded bg-[#131722] border border-[#2a2e39]">
              <div className="font-semibold text-white">
                当前标的 ({quote.name} {selectedSymbol}) 五档空档保护测试
              </div>
              <p className="mt-1 text-[11px] text-[#787b86]">
                一键切换当前股票至涨停、跌停或集合竞价阶段，验证五档盘口空档自动降级为 <code className="font-mono text-[#d1d4dc]">--</code> 与委比极值计算。
              </p>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-2.5">
                {(
                  [
                    { id: 'normal', label: '正常连续竞价' },
                    { id: 'limit_up', label: '涨停(卖盘全空)' },
                    { id: 'limit_down', label: '跌停(买盘全空)' },
                    { id: 'call_auction', label: '集合竞价(3-5空)' },
                  ] as { id: MarketScenario; label: string }[]
                ).map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      void triggerScenario(selectedSymbol, item.id);
                    }}
                    className={`py-1.5 px-2 rounded text-[11px] font-medium border transition-colors cursor-pointer ${
                      currentScenario === item.id
                        ? 'bg-[#2962ff] border-[#2962ff] text-white'
                        : 'bg-[#1e222d] border-[#2a2e39] text-[#9ca3af] hover:text-white'
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* 4. 云端生产环境 Nginx WSS 反向代理规范配置 */}
          <div className="p-3 rounded bg-[#131722] border border-[#2a2e39]">
            <div className="font-semibold text-white mb-1">
              云服务器 Nginx SSL 卸载与 WSS 长连接保活配置
            </div>
            <pre className="p-2.5 rounded bg-[#0d0e12] border border-[#2a2e39] font-mono text-[11px] text-[#9ca3af] overflow-x-auto leading-relaxed">
{`location /ws {
    proxy_pass http://127.0.0.1:3000/ws;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 90s; # 配合前端 30s Ping/Pong 心跳保活
}`}
            </pre>
          </div>
        </div>

        <div className="flex justify-end px-4 py-2.5 border-t border-[#2a2e39] bg-[#131722]">
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
