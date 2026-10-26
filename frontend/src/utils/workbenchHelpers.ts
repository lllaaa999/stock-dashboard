import type { AuctionSignalType, DragonTigerSeatNature } from '../types/market';

/**
 * 后端 /api/quant/ladder 的晋级率、封板率在「无基数」时会返回 null
 * （例如节后第一天取不到上一交易日涨停池），直接 .toFixed 会让整页白屏。
 * 这类"算不出来"必须显示 "—"，不能显示 0.0%。
 */
export function fmtRate(v: number | null | undefined, digits = 1): string {
  return typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits) : '—';
}

export function getAuctionSignalBadgeClass(signal: AuctionSignalType): string {
  switch (signal) {
    case 'LOCKED_LIMIT_UP':
      return 'bg-[#F6465D]/20 text-[#F6465D] border-[#F6465D]/50';
    case 'SUPER_GRAB':
      return 'bg-[#F6465D]/15 text-[#ff6b81] border-[#F6465D]/40';
    case 'WEAK_TO_STRONG':
      return 'bg-[#F59E0B]/15 text-[#F59E0B] border-[#F59E0B]/40';
    case 'OVERHEAT_DUMP':
      return 'bg-[#a855f7]/15 text-[#c084fc] border-[#a855f7]/40';
    case 'NUCLEAR_BUTTON':
      return 'bg-[#0ECB81]/20 text-[#0ECB81] border-[#0ECB81]/50';
    default:
      return 'bg-[#131722] text-[#9ca3af] border-[#2a2e39]';
  }
}

export function getSeatNatureBadgeClass(nature: DragonTigerSeatNature): string {
  switch (nature) {
    case 'HOT_MONEY':
      return 'bg-[#F6465D]/20 text-[#F6465D] border-[#F6465D]/50';
    case 'INSTITUTION':
      return 'bg-[#F59E0B]/20 text-[#F59E0B] border-[#F59E0B]/50';
    case 'QUANT_CAMP':
      return 'bg-[#a855f7]/20 text-[#c084fc] border-[#a855f7]/50';
    case 'RETAIL_CAMP':
      return 'bg-[#38bdf8]/20 text-[#38bdf8] border-[#38bdf8]/50';
  }
}
