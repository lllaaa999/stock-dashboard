import type { FocusFact, FocusItem, FocusResponse } from '../types/market';

const LEVEL_RANK: Record<FocusItem['level'], number> = {
  RED: 0,
  YELLOW: 1,
  GREEN: 2,
  INFO: 3,
};

/** 按级别（RED > YELLOW > GREEN > INFO）再按分数降序排序，不修改入参 */
export function sortFocusItems(items: FocusItem[] | null | undefined): FocusItem[] {
  if (!items) return [];
  return [...items].sort((a, b) => {
    const la = LEVEL_RANK[a.level] ?? 99;
    const lb = LEVEL_RANK[b.level] ?? 99;
    if (la !== lb) return la - lb;
    return (b.score ?? 0) - (a.score ?? 0);
  });
}

/** 格式化单个关键数字，如 {label:'最高板',value:5,unit:'板'} → "最高板 5板" */
export function formatFocusFact(fact: FocusFact): string {
  let v: string;
  if (typeof fact.value === 'number') {
    v = Number.isFinite(fact.value)
      ? Number.isInteger(fact.value)
        ? String(fact.value)
        : fact.value.toFixed(2)
      : '--';
  } else {
    v = fact.value === '' || fact.value == null ? '--' : String(fact.value);
  }
  return `${fact.label} ${v}${fact.unit ?? ''}`;
}

/** 四区全部无内容（市场定调不计）视为空态 */
export function isFocusEmpty(focus: FocusResponse | null | undefined): boolean {
  if (!focus) return true;
  return (
    (focus.risks?.length ?? 0) +
      (focus.themes?.length ?? 0) +
      (focus.anomalies?.length ?? 0) +
      (focus.news?.length ?? 0) ===
    0
  );
}

export function levelLabel(level: FocusItem['level']): string {
  switch (level) {
    case 'RED':
      return '高风险';
    case 'YELLOW':
      return '留意';
    case 'GREEN':
      return '积极';
    default:
      return '信息';
  }
}
