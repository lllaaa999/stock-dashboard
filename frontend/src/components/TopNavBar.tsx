import React from 'react';
import { useMarketStore } from '../store/useMarketStore';

export const TopNavBar: React.FC = () => {
  const workspaceMode = useMarketStore((s) => s.workspaceMode);
  const quantModuleTab = useMarketStore((s) => s.quantModuleTab);
  const setWorkspaceMode = useMarketStore((s) => s.setWorkspaceMode);
  const openQuantModule = useMarketStore((s) => s.openQuantModule);
  const setFilterCategory = useMarketStore((s) => s.setFilterCategory);
  const setArchModalOpen = useMarketStore((s) => s.setArchModalOpen);

  return (
    <header className="flex items-center justify-between gap-8 px-4 h-11 bg-[#0d0e12] border-b border-[#2a2e39] select-none shrink-0">
      {/* Zone 1: Single text element wordmark */}
      <a
        href="#top"
        onClick={(e) => {
          e.preventDefault();
          setFilterCategory('all');
          setWorkspaceMode('chart');
        }}
        className="text-sm sm:text-base font-bold tracking-tight text-white whitespace-nowrap shrink-0"
      >
        AlphaPulse L1
      </a>

      {/* Zone 2: 4 clean single-line text navigation links */}
      <nav
        aria-label="主工作台视图导航"
        className="hidden md:flex items-center gap-6 text-xs font-medium text-[#9ca3af]"
      >
        <button
          type="button"
          onClick={() => setWorkspaceMode('chart')}
          className={`hover:text-white transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
            workspaceMode === 'chart'
              ? 'text-white underline underline-offset-4 decoration-[#2962ff]'
              : ''
          }`}
        >
          主图看盘工作台
        </button>
        <button
          type="button"
          data-testid="nav-quant-overview"
          onClick={() => openQuantModule('overview')}
          className={`hover:text-white transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
            workspaceMode === 'quant' && quantModuleTab === 'overview'
              ? 'text-[#F6465D] font-semibold underline underline-offset-4 decoration-[#F6465D]'
              : ''
          }`}
        >
          超短游资作战室
        </button>
        <button
          type="button"
          data-testid="nav-quant-auction"
          onClick={() => openQuantModule('auction')}
          className={`hover:text-white transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
            workspaceMode === 'quant' && quantModuleTab === 'auction'
              ? 'text-[#F59E0B] font-semibold underline underline-offset-4 decoration-[#F59E0B]'
              : ''
          }`}
        >
          09:25竞价雷达
        </button>
        <button
          type="button"
          data-testid="nav-quant-regulatory"
          onClick={() => openQuantModule('regulatory')}
          className={`hover:text-white transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
            workspaceMode === 'quant' && quantModuleTab === 'regulatory'
              ? 'text-[#38bdf8] font-semibold underline underline-offset-4 decoration-[#38bdf8]'
              : ''
          }`}
        >
          连板梯队与异动逆推
        </button>
      </nav>

      {/* Zone 3: 1 primary action */}
      <div className="flex items-center gap-3 shrink-0">
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

