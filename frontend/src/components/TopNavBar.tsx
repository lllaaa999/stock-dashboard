import React from 'react';
import { Keyboard, Radar, Layers, BarChart2, ShieldAlert, Filter } from 'lucide-react';
import { useMarketStore } from '../store/useMarketStore';

export const TopNavBar: React.FC = () => {
  const workspaceMode = useMarketStore((s) => s.workspaceMode);
  const quantModuleTab = useMarketStore((s) => s.quantModuleTab);
  const period = useMarketStore((s) => s.period);
  const setWorkspaceMode = useMarketStore((s) => s.setWorkspaceMode);
  const openQuantModule = useMarketStore((s) => s.openQuantModule);
  const setFilterCategory = useMarketStore((s) => s.setFilterCategory);
  const setArchModalOpen = useMarketStore((s) => s.setArchModalOpen);
  const setCommandPaletteOpen = useMarketStore((s) => s.setCommandPaletteOpen);

  return (
    <header className="flex items-center justify-between gap-4 px-4 h-11 bg-[#0d0e12] border-b border-[#2a2e39] select-none shrink-0">
      {/* Zone 1: 品牌标识与全屏工作区状态指示 */}
      <div className="flex items-center gap-3 shrink-0">
        <a
          href="#top"
          onClick={(e) => {
            e.preventDefault();
            setFilterCategory('all');
            setWorkspaceMode('chart');
          }}
          className="flex items-center gap-2 text-sm sm:text-base font-bold tracking-tight text-white whitespace-nowrap shrink-0"
        >
          <span className="w-2 h-2 rounded-full bg-[#2962ff] shadow-[0_0_8px_#2962ff]" />
          <span>AlphaPulse L1</span>
        </a>
        <span className="hidden lg:inline-block px-1.5 py-0.5 rounded bg-[#131722] border border-[#2a2e39] text-[10px] font-mono text-[#787b86]">
          TDX 毫秒级引擎
        </span>
      </div>

      {/* Zone 2: 100% 满屏一级视图独占切换器 (彻底告别上下硬拼割裂) */}
      <nav
        aria-label="主工作台视图导航"
        className="hidden md:flex items-center gap-1.5 bg-[#131722] p-1 rounded-md border border-[#2a2e39]"
      >
        <button
          type="button"
          data-testid="nav-chart-workbench"
          onClick={() => setWorkspaceMode('chart')}
          className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium transition-all whitespace-nowrap shrink-0 cursor-pointer ${
            workspaceMode === 'chart'
              ? 'bg-[#2962ff] text-white font-semibold shadow-sm'
              : 'text-[#9ca3af] hover:text-white hover:bg-[#1e222d]'
          }`}
        >
          <BarChart2 className="w-3.5 h-3.5" />
          <span>主图看盘工作台</span>
          <span className="text-[10px] font-mono opacity-80">
            ({period === 'intraday' ? '分时' : period})
          </span>
        </button>

        <button
          type="button"
          data-testid="nav-quant-auction"
          onClick={() => setWorkspaceMode('auction')}
          className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium transition-all whitespace-nowrap shrink-0 cursor-pointer ${
            workspaceMode === 'auction'
              ? 'bg-[#F59E0B] text-[#0d0e12] font-bold shadow-sm'
              : 'text-[#9ca3af] hover:text-[#F59E0B] hover:bg-[#1e222d]'
          }`}
        >
          <Radar className="w-3.5 h-3.5" />
          <span>09:25 竞价雷达</span>
        </button>

        <button
          type="button"
          data-testid="nav-quant-overview"
          onClick={() => openQuantModule('overview')}
          className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium transition-all whitespace-nowrap shrink-0 cursor-pointer ${
            workspaceMode === 'quant' && quantModuleTab !== 'regulatory'
              ? 'bg-[#F6465D] text-white font-semibold shadow-sm'
              : 'text-[#9ca3af] hover:text-[#F6465D] hover:bg-[#1e222d]'
          }`}
        >
          <Layers className="w-3.5 h-3.5" />
          <span>超短游资作战室</span>
        </button>

        <button
          type="button"
          data-testid="nav-quant-regulatory"
          onClick={() => openQuantModule('regulatory')}
          className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium transition-all whitespace-nowrap shrink-0 cursor-pointer ${
            workspaceMode === 'quant' && quantModuleTab === 'regulatory'
              ? 'bg-[#38bdf8] text-[#0d0e12] font-bold shadow-sm'
              : 'text-[#9ca3af] hover:text-[#38bdf8] hover:bg-[#1e222d]'
          }`}
        >
          <ShieldAlert className="w-3.5 h-3.5" />
          <span>连板梯队与异动逆推</span>
        </button>

        <button
          type="button"
          data-testid="nav-screener"
          onClick={() => setWorkspaceMode('screener')}
          className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium transition-all whitespace-nowrap shrink-0 cursor-pointer ${
            workspaceMode === 'screener'
              ? 'bg-[#2EB872] text-white font-semibold shadow-sm'
              : 'text-[#9ca3af] hover:text-[#2EB872] hover:bg-[#1e222d]'
          }`}
        >
          <Filter className="w-3.5 h-3.5" />
          <span>选股</span>
        </button>
      </nav>

      {/* Zone 3: 通达信键盘精灵唤醒器 + 终端配置 */}
      <div className="flex items-center gap-2.5 shrink-0">
        <button
          type="button"
          data-testid="open-tdx-sprite-btn"
          onClick={() => setCommandPaletteOpen(true)}
          title="直接敲击数字代码或拼音首字母即可唤出键盘精灵 (快捷键: 任意键 / Space切分时日K / ↑↓切股)"
          className="hidden sm:flex items-center gap-2 px-2.5 py-1 rounded bg-[#131722] hover:bg-[#1e222d] border border-[#2a2e39] hover:border-[#2962ff] text-xs text-[#9ca3af] hover:text-white transition-colors cursor-pointer"
        >
          <Keyboard className="w-3.5 h-3.5 text-[#38bdf8]" />
          <span>键盘精灵检索</span>
          <kbd className="px-1 py-0.2 rounded bg-[#1e222d] border border-[#2a2e39] font-mono text-[10px] text-[#787b86]">
            代码/拼音
          </kbd>
        </button>

        <button
          type="button"
          onClick={() => setArchModalOpen(true)}
          className="px-3 py-1.5 text-xs font-medium text-white bg-[#2962ff] rounded hover:bg-[#1e53e5] transition-colors whitespace-nowrap shrink-0 cursor-pointer"
        >
          终端设置与PWA安装
        </button>
      </div>
    </header>
  );
};
