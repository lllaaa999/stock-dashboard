import test from 'node:test';
import assert from 'node:assert/strict';
import { formatFocusFact, isFocusEmpty, levelLabel, sortFocusItems } from './focusUtils';
import type { FocusItem, FocusResponse } from '../types/market';

function item(id: string, level: FocusItem['level'], score: number): FocusItem {
  return {
    id,
    category: 'RISK',
    level,
    title: id,
    facts: [],
    symbols: [],
    narrative: '',
    narrativeSource: 'template',
    evidence: [],
    score,
    updatedAt: 0,
  };
}

function resp(partial: Partial<FocusResponse>): FocusResponse {
  return {
    status: 'ok',
    marketTone: { phase: '', text: '', level: 'INFO' },
    risks: [],
    themes: [],
    anomalies: [],
    news: [],
    narrativeMode: 'template',
    disclaimer: '',
    updatedAt: 0,
    ...partial,
  };
}

test('sortFocusItems: 红色优先于黄绿，同级按分数降序', () => {
  const out = sortFocusItems([
    item('g', 'GREEN', 99),
    item('y', 'YELLOW', 50),
    item('r1', 'RED', 10),
    item('r2', 'RED', 80),
  ]);
  assert.deepEqual(out.map((i) => i.id), ['r2', 'r1', 'y', 'g']);
});

test('sortFocusItems: 不修改入参且容忍 null', () => {
  const src = [item('a', 'GREEN', 1), item('b', 'RED', 1)];
  sortFocusItems(src);
  assert.equal(src[0].id, 'a');
  assert.deepEqual(sortFocusItems(null), []);
});

test('formatFocusFact: 整数、小数与单位', () => {
  assert.equal(formatFocusFact({ label: '最高板', value: 5, unit: '板' }), '最高板 5板');
  assert.equal(formatFocusFact({ label: '涨幅', value: 3.14159, unit: '%' }), '涨幅 3.14%');
});

test('formatFocusFact: 字符串与缺失值', () => {
  assert.equal(formatFocusFact({ label: '阶段', value: '高潮' }), '阶段 高潮');
  assert.equal(formatFocusFact({ label: '量比', value: NaN }), '量比 --');
});

test('isFocusEmpty: null 与四区全空为空态', () => {
  assert.equal(isFocusEmpty(null), true);
  assert.equal(isFocusEmpty(resp({})), true);
});

test('isFocusEmpty: 任一区有内容则非空', () => {
  assert.equal(isFocusEmpty(resp({ news: [item('n', 'INFO', 1)] })), false);
});

test('levelLabel: 级别文案', () => {
  assert.equal(levelLabel('RED'), '高风险');
  assert.equal(levelLabel('INFO'), '信息');
});
