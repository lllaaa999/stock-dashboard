import React, { useEffect, useRef, useState } from 'react';
import {
  generateKLinesForSymbol,
} from '../data/seedMarket';
import {
  subscribeSymbolImperativeTick,
  useMarketStore,
} from '../store/useMarketStore';
import type {
  ChanAnalysis,
  ChartPeriod,
  IntradayPoint,
  KLineBar,
  MainIndicator,
  SubIndicator,
  TickData,
} from '../types/market';
import {
  calculateBOLL,
  calculateEMA,
  calculateKDJ,
  calculateMACD,
  calculateRSI,
  calculateSMA,
  formatPrice,
  formatSignedPercent,
  formatVolumeHands,
} from '../utils/marketCalc';

/**
 * 原生 Canvas 高性能金融图表控制器 (Native Canvas Imperative Chart Instance)
 * 核心设计原则：
 * 1. 通过独立 DOM Ref 挂载 Canvas，完全脱离 React Virtual DOM 树。
 * 2. 提供命令式 setData() 与 updateData(tick) 接口，收到 WebSocket 实时 Tick 时
 *    直接原地更新最后一根 K 线或分时点并重绘 Canvas，不触发任何 React setState。
 * 3. 原生支持移动端单指拖拽平移 (Single-finger Pan) 与双指捏合缩放 (Pinch-to-Zoom)。
 */
class NativeFinancialChartInstance {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private width = 0;
  private height = 0;
  private dpr = 1;

  private period: ChartPeriod = '1D';
  private mainIndicator: MainIndicator = 'MA';
  private subIndicator: SubIndicator = 'VOL';
  private prevClose = 100;

  private klines: KLineBar[] = [];
  private intraday: IntradayPoint[] = [];
  // 缠论图层：笔 / 中枢 / 买卖点（数据来自 /api/quant/chan，与图表同周期K线）
  private chan: ChanAnalysis | null = null;
  private showChan = true;

  // 可视窗口范围（以柱索引计）
  private visibleCount = 65;
  private rightOffsetBars = 0; // 距离最新一根柱的偏移量（>= 0）

  // 交互状态（鼠标十字光标、单指拖拽、双指捏合）
  private hoverIndex: number | null = null;
  private hoverY: number | null = null;
  private isDragging = false;
  private dragStartX = 0;
  private dragStartOffset = 0;
  private initialPinchDistance: number | null = null;
  private initialPinchVisibleCount = 65;

  // 预计算的指标缓存
  private ma5: (number | null)[] = [];
  private ma10: (number | null)[] = [];
  private ma20: (number | null)[] = [];
  private ma60: (number | null)[] = [];
  private ema12: (number | null)[] = [];
  private ema26: (number | null)[] = [];
  private boll = calculateBOLL([]);
  private macd = calculateMACD([]);
  private kdj = calculateKDJ([]);
  private rsi14: (number | null)[] = [];

  // 指标重算节流：避免每 tick 全量重算历史 K 线的所有指标
  private lastIndicatorCalcTime = 0;
  private static readonly INDICATOR_THROTTLE_MS = 200; // 高频行情下最多每 200ms 重算一次

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas;
    const context = canvas.getContext('2d');
    if (!context) {
      throw new Error('Failed to initialize 2D canvas context');
    }
    this.ctx = context;
    this.bindEvents();
  }

  public resize(width: number, height: number): void {
    if (width <= 0 || height <= 0) return;
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.width = width;
    this.height = height;
    this.canvas.width = Math.floor(width * this.dpr);
    this.canvas.height = Math.floor(height * this.dpr);
    this.render();
  }

  public setConfig(period: ChartPeriod, mainInd: MainIndicator, subInd: SubIndicator): void {
    const periodChanged = this.period !== period;
    this.period = period;
    this.mainIndicator = mainInd;
    this.subIndicator = subInd;
    if (periodChanged) {
      this.rightOffsetBars = 0;
      this.hoverIndex = null;
    }
    this.render();
  }

  public setKLineData(bars: KLineBar[], prevClose: number): void {
    this.klines = bars;
    this.prevClose = prevClose;
    this.rightOffsetBars = 0;
    this.recomputeIndicators();
    this.render();
  }

  public setChanData(chan: ChanAnalysis | null, show?: boolean): void {
    this.chan = chan;
    if (show !== undefined) this.showChan = show;
    this.render();
  }

  public setChanVisible(show: boolean): void {
    this.showChan = show;
    this.render();
  }

  /** 时间 -> K线索引（缠论按完整时间对齐：日/周/月K为 YYYY-MM-DD，分钟K为 YYYY-MM-DD HH:mm） */
  private buildDateIndex(): Map<string, number> {
    const map = new Map<string, number>();
    for (let i = 0; i < this.klines.length; i++) {
      const d = String(this.klines[i].time || '');
      if (d) map.set(d, i);
    }
    return map;
  }

  public setIntradayData(points: IntradayPoint[], prevClose: number): void {
    this.intraday = points;
    this.prevClose = prevClose;
    this.render();
  }

  /**
   * 核心高频命令式更新 API：直接推入最新 Tick 快照，不经过 React Virtual DOM Diff
   */
  public updateData(tick: TickData): void {
    this.prevClose = tick.prevClose;

    if (this.period === 'intraday') {
      if (this.intraday.length > 0) {
        const lastIdx = this.intraday.length - 1;
        const lastPt = this.intraday[lastIdx];
        const nextPrice = tick.price;
        const nextAvg = Number(((lastPt.avgPrice * 0.92 + nextPrice * 0.08)).toFixed(2));
        const nextChg = Number((((nextPrice - tick.prevClose) / tick.prevClose) * 100).toFixed(2));
        this.intraday[lastIdx] = {
          ...lastPt,
          price: nextPrice,
          avgPrice: nextAvg,
          volume: lastPt.volume + Math.max(1, Math.round((tick.recentTrades[0]?.volume ?? 10) * 0.2)),
          changePercent: nextChg,
        };
      }
      this.render();
      return;
    }

    if (this.klines.length > 0) {
      const lastIdx = this.klines.length - 1;
      const lastBar = this.klines[lastIdx];
      const nextClose = tick.price;
      this.klines[lastIdx] = {
        ...lastBar,
        close: nextClose,
        high: Math.max(lastBar.high, nextClose, tick.high),
        low: Math.min(lastBar.low, nextClose, tick.low),
        volume: tick.volume,
        amount: tick.amount,
      };
      this.recomputeIndicatorsThrottled();
      this.render();
    }
  }

  /**
   * 全量重算所有指标（用于 setKLineData / setConfig 等低频场景）
   */
  private recomputeIndicators(): void {
    if (this.klines.length === 0) return;
    this.recomputeMainIndicators();
    this.recomputeSubIndicators();
    this.lastIndicatorCalcTime = Date.now();
  }

  /**
   * 节流 + 按需重算：仅在高频 tick 场景下调用
   * 限制为每 INDICATOR_THROTTLE_MS 最多一次，且只计算当前可见的指标
   */
  private recomputeIndicatorsThrottled(): void {
    if (this.klines.length === 0) return;
    const now = Date.now();
    if (now - this.lastIndicatorCalcTime < NativeFinancialChartInstance.INDICATOR_THROTTLE_MS) return;
    this.recomputeMainIndicators();
    this.recomputeSubIndicators();
    this.lastIndicatorCalcTime = now;
  }

  /**
   * 按需重算主图指标（仅计算当前 mainIndicator 需要的指标）
   */
  private recomputeMainIndicators(): void {
    switch (this.mainIndicator) {
      case 'MA':
        this.ma5 = calculateSMA(this.klines, 5);
        this.ma10 = calculateSMA(this.klines, 10);
        this.ma20 = calculateSMA(this.klines, 20);
        this.ma60 = calculateSMA(this.klines, 60);
        break;
      case 'EMA':
        this.ema12 = calculateEMA(this.klines, 12);
        this.ema26 = calculateEMA(this.klines, 26);
        break;
      case 'BOLL':
        this.boll = calculateBOLL(this.klines, 20, 2);
        break;
      case 'NONE':
        break;
    }
  }

  /**
   * 按需重算副图指标（仅计算当前 subIndicator 需要的指标）
   */
  private recomputeSubIndicators(): void {
    switch (this.subIndicator) {
      case 'MACD':
        this.macd = calculateMACD(this.klines, 12, 26, 9);
        break;
      case 'KDJ':
        this.kdj = calculateKDJ(this.klines, 9);
        break;
      case 'RSI':
        this.rsi14 = calculateRSI(this.klines, 14);
        break;
      case 'VOL':
        break;
    }
  }

  public zoomBy(deltaBars: number): void {
    if (this.period === 'intraday') return;
    this.visibleCount = Math.max(24, Math.min(120, this.visibleCount + deltaBars));
    this.render();
  }

  public resetView(): void {
    this.visibleCount = 65;
    this.rightOffsetBars = 0;
    this.hoverIndex = null;
    this.render();
  }

  private bindEvents(): void {
    const onMouseMove = (e: MouseEvent) => {
      const rect = this.canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;

      if (this.isDragging && this.period !== 'intraday') {
        const dx = x - this.dragStartX;
        const plotW = Math.max(100, this.width - 68);
        const barWidth = plotW / this.visibleCount;
        const shiftedBars = Math.round(dx / barWidth);
        const maxOffset = Math.max(0, this.klines.length - this.visibleCount);
        this.rightOffsetBars = Math.max(0, Math.min(maxOffset, this.dragStartOffset + shiftedBars));
        this.render();
        return;
      }

      this.updateHoverFromPoint(x, y);
    };

    const onMouseDown = (e: MouseEvent) => {
      const rect = this.canvas.getBoundingClientRect();
      this.isDragging = true;
      this.dragStartX = e.clientX - rect.left;
      this.dragStartOffset = this.rightOffsetBars;
    };

    const onMouseUp = () => {
      this.isDragging = false;
    };

    const onMouseLeave = () => {
      this.isDragging = false;
      this.hoverIndex = null;
      this.hoverY = null;
      this.render();
    };

    const onWheel = (e: WheelEvent) => {
      if (this.period === 'intraday') return;
      e.preventDefault();
      const step = e.deltaY > 0 ? 6 : -6;
      this.zoomBy(step);
    };

    // 移动端单指拖拽与双指捏合缩放支持 (Touch Pan & Pinch-to-Zoom)
    const onTouchStart = (e: TouchEvent) => {
      if (e.touches.length === 2) {
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        this.initialPinchDistance = Math.hypot(dx, dy);
        this.initialPinchVisibleCount = this.visibleCount;
        this.isDragging = false;
      } else if (e.touches.length === 1) {
        const rect = this.canvas.getBoundingClientRect();
        const x = e.touches[0].clientX - rect.left;
        const y = e.touches[0].clientY - rect.top;
        this.isDragging = true;
        this.dragStartX = x;
        this.dragStartOffset = this.rightOffsetBars;
        this.updateHoverFromPoint(x, y);
      }
    };

    const onTouchMove = (e: TouchEvent) => {
      if (e.touches.length === 2 && this.initialPinchDistance !== null && this.period !== 'intraday') {
        e.preventDefault();
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        const dist = Math.hypot(dx, dy);
        if (dist > 10) {
          const scale = this.initialPinchDistance / dist;
          this.visibleCount = Math.max(24, Math.min(120, Math.round(this.initialPinchVisibleCount * scale)));
          this.render();
        }
      } else if (e.touches.length === 1) {
        const rect = this.canvas.getBoundingClientRect();
        const x = e.touches[0].clientX - rect.left;
        const y = e.touches[0].clientY - rect.top;
        if (this.isDragging && this.period !== 'intraday') {
          const dx = x - this.dragStartX;
          const plotW = Math.max(100, this.width - 68);
          const barWidth = plotW / this.visibleCount;
          const shiftedBars = Math.round(dx / barWidth);
          const maxOffset = Math.max(0, this.klines.length - this.visibleCount);
          this.rightOffsetBars = Math.max(0, Math.min(maxOffset, this.dragStartOffset + shiftedBars));
        }
        this.updateHoverFromPoint(x, y);
      }
    };

    const onTouchEnd = () => {
      this.isDragging = false;
      this.initialPinchDistance = null;
    };

    this.canvas.addEventListener('mousemove', onMouseMove);
    this.canvas.addEventListener('mousedown', onMouseDown);
    window.addEventListener('mouseup', onMouseUp);
    this.canvas.addEventListener('mouseleave', onMouseLeave);
    this.canvas.addEventListener('wheel', onWheel, { passive: false });
    this.canvas.addEventListener('touchstart', onTouchStart, { passive: true });
    this.canvas.addEventListener('touchmove', onTouchMove, { passive: false });
    this.canvas.addEventListener('touchend', onTouchEnd);

    this.cleanupEvents = () => {
      this.canvas.removeEventListener('mousemove', onMouseMove);
      this.canvas.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('mouseup', onMouseUp);
      this.canvas.removeEventListener('mouseleave', onMouseLeave);
      this.canvas.removeEventListener('wheel', onWheel);
      this.canvas.removeEventListener('touchstart', onTouchStart);
      this.canvas.removeEventListener('touchmove', onTouchMove);
      this.canvas.removeEventListener('touchend', onTouchEnd);
    };
  }

  private cleanupEvents: () => void = () => {};

  public destroy(): void {
    this.cleanupEvents();
  }

  private updateHoverFromPoint(x: number, y: number): void {
    const rightAxisW = 64;
    const plotW = this.width - rightAxisW;
    if (x < 0 || x > plotW) {
      this.hoverIndex = null;
      this.hoverY = null;
      this.render();
      return;
    }

    this.hoverY = y;
    if (this.period === 'intraday') {
      const totalSlots = Math.max(240, this.intraday.length);
      const idx = Math.min(this.intraday.length - 1, Math.max(0, Math.floor((x / plotW) * totalSlots)));
      this.hoverIndex = idx;
    } else {
      const total = this.klines.length;
      const endIdx = Math.max(0, total - this.rightOffsetBars);
      const startIdx = Math.max(0, endIdx - this.visibleCount);
      const count = Math.max(1, endIdx - startIdx);
      const rel = Math.min(count - 1, Math.max(0, Math.floor((x / plotW) * count)));
      this.hoverIndex = startIdx + rel;
    }
    this.render();
  }

  public render(): void {
    if (this.width <= 0 || this.height <= 0) return;
    const ctx = this.ctx;
    ctx.save();
    ctx.scale(this.dpr, this.dpr);

    // 1. 填充深黑灰主背景 (#131722)
    ctx.fillStyle = '#131722';
    ctx.fillRect(0, 0, this.width, this.height);

    const rightAxisW = 64;
    const topHudH = 26;
    const bottomAxisH = 22;
    const subHeaderH = 20;
    const usableH = this.height - topHudH - bottomAxisH;
    const mainH = Math.floor(usableH * 0.68);
    const subH = usableH - mainH - subHeaderH;

    const plotW = Math.max(60, this.width - rightAxisW);
    const mainTop = topHudH;
    const mainBottom = mainTop + mainH;
    const subTop = mainBottom + subHeaderH;
    const subBottom = subTop + subH;

    // 2. 绘制网格背景线 (#1f2430)
    this.drawGrid(ctx, plotW, mainTop, mainBottom, subTop, subBottom);

    if (this.period === 'intraday') {
      this.drawIntraday(ctx, plotW, mainTop, mainH, subTop, subH);
    } else {
      this.drawKLines(ctx, plotW, mainTop, mainH, subTop, subH);
    }

    ctx.restore();
  }

  private drawGrid(
    ctx: CanvasRenderingContext2D,
    plotW: number,
    mainTop: number,
    mainBottom: number,
    subTop: number,
    subBottom: number
  ): void {
    ctx.strokeStyle = '#1e222d';
    ctx.lineWidth = 1;

    // 主图水平网格线 (4等分)
    for (let i = 0; i <= 4; i++) {
      const y = Math.floor(mainTop + ((mainBottom - mainTop) * i) / 4) + 0.5;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(plotW, y);
      ctx.stroke();
    }

    // 副图水平网格线 (2等分)
    for (let i = 0; i <= 2; i++) {
      const y = Math.floor(subTop + ((subBottom - subTop) * i) / 2) + 0.5;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(plotW, y);
      ctx.stroke();
    }

    // 垂直网格线 (5等分)
    for (let i = 1; i <= 5; i++) {
      const x = Math.floor((plotW * i) / 5) + 0.5;
      ctx.beginPath();
      ctx.moveTo(x, mainTop);
      ctx.lineTo(x, mainBottom);
      ctx.moveTo(x, subTop);
      ctx.lineTo(x, subBottom);
      ctx.stroke();
    }

    // 主副图分割线与右侧坐标轴分割线
    ctx.strokeStyle = '#2a2e39';
    ctx.beginPath();
    ctx.moveTo(0, mainBottom + 0.5);
    ctx.lineTo(this.width, mainBottom + 0.5);
    ctx.moveTo(0, subTop - 0.5);
    ctx.lineTo(this.width, subTop - 0.5);
    ctx.moveTo(plotW + 0.5, 0);
    ctx.lineTo(plotW + 0.5, this.height);
    ctx.stroke();
  }

  private drawIntraday(
    ctx: CanvasRenderingContext2D,
    plotW: number,
    mainTop: number,
    mainH: number,
    subTop: number,
    subH: number
  ): void {
    const pts = this.intraday;
    if (pts.length === 0) return;

    const totalSlots = 241; // A股全天 241 分钟
    let maxDiff = this.prevClose * 0.01;
    let maxVol = 1;

    for (const p of pts) {
      const d = Math.abs(p.price - this.prevClose);
      if (d > maxDiff) maxDiff = d;
      if (p.volume > maxVol) maxVol = p.volume;
    }
    maxDiff *= 1.12;

    const maxPrice = this.prevClose + maxDiff;
    const minPrice = Math.max(0.01, this.prevClose - maxDiff);
    const priceRange = Math.max(0.01, maxPrice - minPrice);

    const getX = (idx: number) => (idx / (totalSlots - 1)) * plotW;
    const getY = (price: number) => mainTop + mainH - ((price - minPrice) / priceRange) * mainH;

    // 1. 昨收价基准虚线
    const prevCloseY = Math.floor(getY(this.prevClose)) + 0.5;
    ctx.save();
    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = '#787b86';
    ctx.beginPath();
    ctx.moveTo(0, prevCloseY);
    ctx.lineTo(plotW, prevCloseY);
    ctx.stroke();
    ctx.restore();

    // 2. 分时均线偏离带 (VWAP Deviation Band: 水上承接红带 / 水下分歧绿带)
    if (pts.length > 1) {
      ctx.save();
      ctx.beginPath();
      pts.forEach((p, idx) => {
        const x = getX(idx);
        const y = getY(p.price);
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      for (let idx = pts.length - 1; idx >= 0; idx--) {
        const x = getX(idx);
        const y = getY(pts[idx].avgPrice);
        ctx.lineTo(x, y);
      }
      ctx.closePath();
      const latestPt = pts[pts.length - 1];
      ctx.fillStyle =
        latestPt.price >= latestPt.avgPrice
          ? 'rgba(246, 70, 93, 0.12)'
          : 'rgba(14, 203, 129, 0.12)';
      ctx.fill();
      ctx.restore();
    }

    // 3. 分时价格蓝白曲线 + 渐变面积图
    ctx.beginPath();
    pts.forEach((p, idx) => {
      const x = getX(idx);
      const y = getY(p.price);
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = '#38BDF8';
    ctx.lineWidth = 1.65;
    ctx.stroke();

    const lastX = getX(pts.length - 1);
    ctx.lineTo(lastX, mainTop + mainH);
    ctx.lineTo(0, mainTop + mainH);
    ctx.closePath();
    const grad = ctx.createLinearGradient(0, mainTop, 0, mainTop + mainH);
    grad.addColorStop(0, 'rgba(56, 189, 248, 0.20)');
    grad.addColorStop(1, 'rgba(56, 189, 248, 0.01)');
    ctx.fillStyle = grad;
    ctx.fill();

    // 4. 均价线 (VWAP 明黄色 #F59E0B)
    ctx.beginPath();
    pts.forEach((p, idx) => {
      const x = getX(idx);
      const y = getY(p.avgPrice);
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = '#F59E0B';
    ctx.lineWidth = 1.35;
    ctx.stroke();

    // 5. 副图分时成交量柱 (含异常放量柱 >2.5x 均量高亮金边标识)
    const avgVol =
      pts.reduce((acc, item) => acc + item.volume, 0) / Math.max(1, pts.length);
    const barW = Math.max(1.5, (plotW / totalSlots) * 0.72);
    pts.forEach((p, idx) => {
      const x = getX(idx);
      const prevP = idx > 0 ? pts[idx - 1].price : this.prevClose;
      const isUp = p.price >= prevP;
      const isAbnormalSpike = p.volume >= avgVol * 2.5 && p.volume > 0;
      const h = (p.volume / maxVol) * (subH - 6);
      if (isAbnormalSpike) {
        ctx.fillStyle = isUp ? '#F59E0B' : '#38BDF8';
      } else {
        ctx.fillStyle = isUp ? 'rgba(246, 70, 93, 0.85)' : 'rgba(14, 203, 129, 0.85)';
      }
      ctx.fillRect(x - barW / 2, subTop + subH - h, barW, h);
    });

    // 5. 右侧价格坐标轴标签
    ctx.font = '11px "JetBrains Mono", "Noto Sans SC", monospace';
    ctx.textAlign = 'right';
    const rightX = this.width - 6;

    ctx.fillStyle = '#F6465D';
    ctx.fillText(maxPrice.toFixed(2), rightX, mainTop + 12);

    ctx.fillStyle = '#787b86';
    ctx.fillText(this.prevClose.toFixed(2), rightX, prevCloseY + 4);

    ctx.fillStyle = '#0ECB81';
    ctx.fillText(minPrice.toFixed(2), rightX, mainTop + mainH - 4);

    // 6. 顶部 HUD 指标栏
    const activePt =
      this.hoverIndex !== null && pts[this.hoverIndex] ? pts[this.hoverIndex] : pts[pts.length - 1];
    ctx.textAlign = 'left';
    ctx.font = '11px "JetBrains Mono", "Noto Sans SC", monospace';
    ctx.fillStyle = '#9ca3af';
    ctx.fillText(`时间 ${activePt.time}`, 10, 17);
    ctx.fillStyle = '#38BDF8';
    ctx.fillText(`分时 ${activePt.price.toFixed(2)} (${formatSignedPercent(activePt.changePercent)})`, 95, 17);
    const vwapDiffPct =
      activePt.avgPrice > 0
        ? ((activePt.price - activePt.avgPrice) / activePt.avgPrice) * 100
        : 0;
    ctx.fillStyle = '#F59E0B';
    ctx.fillText(
      `均价 ${activePt.avgPrice.toFixed(2)} (偏离 ${formatSignedPercent(vwapDiffPct)})`,
      255,
      17
    );

    // 副图 HUD
    ctx.fillStyle = '#9ca3af';
    ctx.fillText(`分时量 ${formatVolumeHands(activePt.volume)}手`, 10, subTop - 6);

    // 底部时间刻度
    ctx.fillStyle = '#787b86';
    ctx.textAlign = 'left';
    ctx.fillText('09:30', 6, this.height - 6);
    ctx.textAlign = 'center';
    ctx.fillText('11:30/13:00', plotW / 2, this.height - 6);
    ctx.textAlign = 'right';
    ctx.fillText('15:00', plotW - 6, this.height - 6);

    // 十字准星
    if (this.hoverIndex !== null && pts[this.hoverIndex]) {
      const cx = getX(this.hoverIndex);
      const cy = getY(pts[this.hoverIndex].price);
      this.drawCrosshair(ctx, cx, cy, plotW, mainTop, mainTop + mainH, subTop, subTop + subH, pts[this.hoverIndex].price);
    }
  }

  private drawKLines(
    ctx: CanvasRenderingContext2D,
    plotW: number,
    mainTop: number,
    mainH: number,
    subTop: number,
    subH: number
  ): void {
    const total = this.klines.length;
    if (total === 0) return;

    const endIdx = Math.max(1, total - this.rightOffsetBars);
    const startIdx = Math.max(0, endIdx - this.visibleCount);
    const slice = this.klines.slice(startIdx, endIdx);
    const count = slice.length;
    if (count === 0) return;

    // 1. 计算主图极值范围（包含叠加指标）
    let maxPrice = -Infinity;
    let minPrice = Infinity;
    let highestBarIdx = startIdx;
    let lowestBarIdx = startIdx;

    for (let i = startIdx; i < endIdx; i++) {
      const b = this.klines[i];
      if (b.high > maxPrice) {
        maxPrice = b.high;
        highestBarIdx = i;
      }
      if (b.low < minPrice) {
        minPrice = b.low;
        lowestBarIdx = i;
      }
      if (this.mainIndicator === 'BOLL' && this.boll[i]) {
        if (this.boll[i].upper !== null && this.boll[i].upper! > maxPrice) maxPrice = this.boll[i].upper!;
        if (this.boll[i].lower !== null && this.boll[i].lower! < minPrice) minPrice = this.boll[i].lower!;
      }
    }

    const padding = Math.max(0.05, (maxPrice - minPrice) * 0.08);
    const topVal = maxPrice + padding;
    const bottomVal = Math.max(0.01, minPrice - padding);
    const range = Math.max(0.01, topVal - bottomVal);

    const stepX = plotW / this.visibleCount;
    const candleW = Math.max(2, Math.min(18, stepX * 0.72));

    const getX = (globalIdx: number) => (globalIdx - startIdx + 0.5) * stepX;
    const getY = (val: number) => mainTop + mainH - ((val - bottomVal) / range) * mainH;

    // 1.5 缠论中枢（虚线框，画在K线之下，避免遮挡蜡烛）
    const chanActive = this.showChan && !!this.chan && this.period !== 'intraday';
    const dateIdx = chanActive ? this.buildDateIndex() : null;
    if (chanActive && dateIdx && this.chan) {
      ctx.save();
      ctx.setLineDash([4, 3]);
      ctx.font = '10px "JetBrains Mono", "Noto Sans SC", sans-serif';
      for (const zs of this.chan.zhongshu_list || []) {
        const i0 = dateIdx.get(String(zs.start_date || ''));
        const i1 = dateIdx.get(String(zs.end_date || ''));
        if (i0 === undefined || i1 === undefined) continue;
        if (i1 < startIdx || i0 >= endIdx) continue;
        const xa = getX(Math.max(i0, startIdx)) - stepX / 2;
        const xb = getX(Math.min(i1, endIdx - 1)) + stepX / 2;
        const ya = getY(zs.hi);
        const yb = getY(zs.lo);
        ctx.fillStyle = 'rgba(251, 191, 36, 0.10)';
        ctx.fillRect(xa, ya, xb - xa, yb - ya);
        ctx.strokeStyle = 'rgba(251, 191, 36, 0.8)';
        ctx.lineWidth = 1;
        ctx.strokeRect(xa + 0.5, ya + 0.5, xb - xa, yb - ya);
        if (xb - xa > 54) {
          ctx.fillStyle = '#fbbf24';
          ctx.textAlign = 'left';
          ctx.fillText(`中枢 ${zs.lo.toFixed(2)}~${zs.hi.toFixed(2)}`, xa + 3, ya - 3);
        }
      }
      ctx.restore();
    }

    // 2. 绘制 K 线蜡烛图 (A股红涨 #F6465D, 绿跌 #0ECB81)
    for (let i = startIdx; i < endIdx; i++) {
      const b = this.klines[i];
      const x = getX(i);
      const isUp = b.close >= b.open;
      const color = isUp ? '#F6465D' : '#0ECB81';

      const highY = getY(b.high);
      const lowY = getY(b.low);
      const openY = getY(b.open);
      const closeY = getY(b.close);

      // 上下影线
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(Math.floor(x) + 0.5, highY);
      ctx.lineTo(Math.floor(x) + 0.5, lowY);
      ctx.stroke();

      // 蜡烛柱体
      const bodyTop = Math.min(openY, closeY);
      const bodyH = Math.max(1.5, Math.abs(closeY - openY));
      ctx.fillStyle = color;
      ctx.fillRect(x - candleW / 2, bodyTop, candleW, bodyH);
    }

    // 3. 标记可视区间最高价与最低价指引
    ctx.font = '10px "JetBrains Mono", "Noto Sans SC", "WenQuanYi Zen Hei", sans-serif';
    ctx.fillStyle = '#d1d4dc';
    const highX = getX(highestBarIdx);
    const highY = getY(this.klines[highestBarIdx].high);
    ctx.textAlign = highX > plotW * 0.75 ? 'right' : 'left';
    ctx.fillText(
      `← ${this.klines[highestBarIdx].high.toFixed(2)}`,
      highX > plotW * 0.75 ? highX - 4 : highX + 4,
      Math.max(mainTop + 12, highY)
    );

    const lowX = getX(lowestBarIdx);
    const lowY = getY(this.klines[lowestBarIdx].low);
    ctx.textAlign = lowX > plotW * 0.75 ? 'right' : 'left';
    ctx.fillText(
      `← ${this.klines[lowestBarIdx].low.toFixed(2)}`,
      lowX > plotW * 0.75 ? lowX - 4 : lowX + 4,
      Math.min(mainTop + mainH - 4, lowY + 10)
    );

    // 4. 绘制主图叠加指标线 (MA / EMA / BOLL)
    const drawOverlayLine = (arr: (number | null)[], color: string) => {
      ctx.beginPath();
      let started = false;
      for (let i = startIdx; i < endIdx; i++) {
        const val = arr[i];
        if (val === null || val === undefined) continue;
        const x = getX(i);
        const y = getY(val);
        if (!started) {
          ctx.moveTo(x, y);
          started = true;
        } else {
          ctx.lineTo(x, y);
        }
      }
      if (started) {
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.25;
        ctx.stroke();
      }
    };

    const focusIdx =
      this.hoverIndex !== null && this.hoverIndex >= startIdx && this.hoverIndex < endIdx
        ? this.hoverIndex
        : endIdx - 1;

    ctx.textAlign = 'left';
    ctx.font = '11px "JetBrains Mono", "Noto Sans SC", "WenQuanYi Zen Hei", sans-serif';

    if (this.mainIndicator === 'MA') {
      drawOverlayLine(this.ma5, '#F59E0B'); // 明黄 MA5
      drawOverlayLine(this.ma10, '#A855F7'); // 浅紫 MA10
      drawOverlayLine(this.ma20, '#38BDF8'); // 天蓝 MA20
      drawOverlayLine(this.ma60, '#10B981'); // 青绿 MA60

      const isCompact = plotW < 400;
      ctx.font = isCompact
        ? '10px "JetBrains Mono", "Noto Sans SC", monospace'
        : '11px "JetBrains Mono", "Noto Sans SC", monospace';
      ctx.fillStyle = '#F59E0B';
      ctx.fillText(`MA5:${formatPrice(this.ma5[focusIdx])}`, 6, 17);
      ctx.fillStyle = '#A855F7';
      ctx.fillText(`MA10:${formatPrice(this.ma10[focusIdx])}`, isCompact ? 84 : 106, 17);
      ctx.fillStyle = '#38BDF8';
      ctx.fillText(`MA20:${formatPrice(this.ma20[focusIdx])}`, isCompact ? 166 : 212, 17);
      ctx.fillStyle = '#10B981';
      ctx.fillText(`MA60:${formatPrice(this.ma60[focusIdx])}`, isCompact ? 248 : 318, 17);
    } else if (this.mainIndicator === 'EMA') {
      drawOverlayLine(this.ema12, '#F59E0B');
      drawOverlayLine(this.ema26, '#38BDF8');

      ctx.fillStyle = '#F59E0B';
      ctx.fillText(`EMA12: ${formatPrice(this.ema12[focusIdx])}`, 10, 17);
      ctx.fillStyle = '#38BDF8';
      ctx.fillText(`EMA26: ${formatPrice(this.ema26[focusIdx])}`, 128, 17);
    } else if (this.mainIndicator === 'BOLL') {
      drawOverlayLine(
        this.boll.map((b) => b.mid),
        '#F59E0B'
      );
      drawOverlayLine(
        this.boll.map((b) => b.upper),
        '#A855F7'
      );
      drawOverlayLine(
        this.boll.map((b) => b.lower),
        '#38BDF8'
      );

      const bp = this.boll[focusIdx];
      ctx.fillStyle = '#F59E0B';
      ctx.fillText(`MID: ${formatPrice(bp?.mid)}`, 10, 17);
      ctx.fillStyle = '#A855F7';
      ctx.fillText(`UPPER: ${formatPrice(bp?.upper)}`, 112, 17);
      ctx.fillStyle = '#38BDF8';
      ctx.fillText(`LOWER: ${formatPrice(bp?.lower)}`, 228, 17);
    }

    // 4.5 缠论笔 + 买卖点（金色折线 + 顶底分型 + 买卖点箭头）
    if (chanActive && dateIdx && this.chan) {
      const pts: { x: number; y: number; type: string }[] = [];
      for (const bp of this.chan.bi_points || []) {
        const i = dateIdx.get(String(bp[0] || ''));
        if (i === undefined) continue;
        pts.push({ x: getX(i), y: getY(Number(bp[1])), type: String(bp[2] || '') });
      }
      if (pts.length >= 2) {
        ctx.save();
        ctx.beginPath();
        pts.forEach((pt, k) => (k === 0 ? ctx.moveTo(pt.x, pt.y) : ctx.lineTo(pt.x, pt.y)));
        ctx.strokeStyle = 'rgba(251, 191, 36, 0.95)';
        ctx.lineWidth = 1.6;
        ctx.lineJoin = 'round';
        ctx.stroke();
        for (const pt of pts) {
          ctx.beginPath();
          ctx.arc(pt.x, pt.y, 2.2, 0, Math.PI * 2);
          ctx.fillStyle = pt.type === '顶' ? '#F6465D' : '#0ECB81';
          ctx.fill();
        }
        ctx.restore();
      }

      const showChanLabels = this.visibleCount <= 120;
      ctx.font = '10px "JetBrains Mono", "Noto Sans SC", sans-serif';
      ctx.textAlign = 'center';
      for (const sig of this.chan.signals || []) {
        const i = dateIdx.get(String(sig.date || ''));
        if (i === undefined || i < startIdx || i >= endIdx) continue;
        const x = getX(i);
        const y = getY(Number(sig.price));
        const isBuy = /买|底/.test(`${sig.type}${sig.desc}`);
        const color = sig.color || (isBuy ? '#10b981' : '#ef4444');
        ctx.save();
        ctx.fillStyle = color;
        ctx.beginPath();
        if (isBuy) {
          ctx.moveTo(x, y + 3);
          ctx.lineTo(x - 5, y + 11);
          ctx.lineTo(x + 5, y + 11);
        } else {
          ctx.moveTo(x, y - 3);
          ctx.lineTo(x - 5, y - 11);
          ctx.lineTo(x + 5, y - 11);
        }
        ctx.closePath();
        ctx.fill();
        ctx.restore();
        if (showChanLabels) {
          ctx.fillStyle = '#ffffff';
          ctx.fillText(String(sig.type).slice(0, 4), x, y + (isBuy ? 24 : -16));
        }
      }
    }

    // 5. 绘制最新价实时横线与右侧高亮价签
    const latestBar = this.klines[this.klines.length - 1];
    if (latestBar) {
      const latestY = getY(latestBar.close);
      const isUp = latestBar.close >= this.prevClose;
      const tagColor = isUp ? '#F6465D' : '#0ECB81';

      if (latestY >= mainTop && latestY <= mainTop + mainH) {
        ctx.save();
        ctx.setLineDash([2, 3]);
        ctx.strokeStyle = tagColor;
        ctx.beginPath();
        ctx.moveTo(0, latestY);
        ctx.lineTo(plotW, latestY);
        ctx.stroke();
        ctx.restore();

        ctx.fillStyle = tagColor;
        ctx.fillRect(plotW + 1, latestY - 9, this.width - plotW - 1, 18);
        ctx.fillStyle = '#ffffff';
        ctx.textAlign = 'right';
        ctx.font = '600 10.5px "JetBrains Mono", "Noto Sans SC", "WenQuanYi Zen Hei", sans-serif';
        ctx.fillText(latestBar.close.toFixed(2), this.width - 4, latestY + 3.5);
      }
    }

    // 6. 右侧价格刻度值
    ctx.font = '10.5px "JetBrains Mono", "Noto Sans SC", "WenQuanYi Zen Hei", sans-serif';
    ctx.fillStyle = '#787b86';
    ctx.textAlign = 'right';
    for (let i = 0; i <= 4; i++) {
      const val = topVal - (range * i) / 4;
      const y = mainTop + (mainH * i) / 4;
      ctx.fillText(val.toFixed(2), this.width - 5, Math.min(mainTop + mainH - 3, Math.max(mainTop + 11, y + 3)));
    }

    // 7. 绘制副图指标 (VOL / MACD / KDJ / RSI)
    this.drawSubChart(ctx, startIdx, endIdx, getX, candleW, subTop, subH, focusIdx);

    // 8. 底部日期刻度
    ctx.fillStyle = '#787b86';
    ctx.font = '10px "JetBrains Mono", "Noto Sans SC", "WenQuanYi Zen Hei", sans-serif';
    const firstBar = this.klines[startIdx];
    const midBar = this.klines[Math.floor((startIdx + endIdx - 1) / 2)];
    const lastVisibleBar = this.klines[endIdx - 1];
    if (firstBar) {
      ctx.textAlign = 'left';
      ctx.fillText(firstBar.time, 6, this.height - 6);
    }
    if (midBar) {
      ctx.textAlign = 'center';
      ctx.fillText(midBar.time, plotW / 2, this.height - 6);
    }
    if (lastVisibleBar) {
      ctx.textAlign = 'right';
      ctx.fillText(lastVisibleBar.time, plotW - 6, this.height - 6);
    }

    // 9. 绘制十字光标与悬停详情卡片
    if (this.hoverIndex !== null && this.hoverIndex >= startIdx && this.hoverIndex < endIdx) {
      const hb = this.klines[this.hoverIndex];
      const cx = getX(this.hoverIndex);
      const cy = this.hoverY ?? getY(hb.close);
      const cursorPrice = topVal - ((cy - mainTop) / mainH) * range;
      this.drawCrosshair(
        ctx,
        cx,
        cy,
        plotW,
        mainTop,
        mainTop + mainH,
        subTop,
        subTop + subH,
        cursorPrice,
        hb
      );
    }
  }

  private drawSubChart(
    ctx: CanvasRenderingContext2D,
    startIdx: number,
    endIdx: number,
    getX: (idx: number) => number,
    candleW: number,
    subTop: number,
    subH: number,
    focusIdx: number
  ): void {
    ctx.textAlign = 'left';
    ctx.font = '11px "JetBrains Mono", "Noto Sans SC", "WenQuanYi Zen Hei", sans-serif';

    if (this.subIndicator === 'VOL') {
      let maxVol = 1;
      for (let i = startIdx; i < endIdx; i++) {
        if (this.klines[i].volume > maxVol) maxVol = this.klines[i].volume;
      }
      for (let i = startIdx; i < endIdx; i++) {
        const b = this.klines[i];
        const x = getX(i);
        const isUp = b.close >= b.open;
        const h = Math.max(1.5, (b.volume / maxVol) * (subH - 6));
        ctx.fillStyle = isUp ? 'rgba(246, 70, 93, 0.82)' : 'rgba(14, 203, 129, 0.82)';
        ctx.fillRect(x - candleW / 2, subTop + subH - h, candleW, h);
      }
      const fb = this.klines[focusIdx];
      ctx.fillStyle = '#9ca3af';
      ctx.fillText(`VOL: ${formatVolumeHands(fb?.volume)}手`, 10, subTop - 5);
      ctx.fillStyle = '#F59E0B';
      ctx.fillText(`成交额: ${(fb ? fb.amount / 1e8 : 0).toFixed(2)}亿`, 135, subTop - 5);
      return;
    }

    if (this.subIndicator === 'MACD') {
      let maxAbs = 0.01;
      for (let i = startIdx; i < endIdx; i++) {
        const m = this.macd[i];
        if (!m) continue;
        maxAbs = Math.max(maxAbs, Math.abs(m.dif), Math.abs(m.dea), Math.abs(m.hist));
      }
      maxAbs *= 1.15;
      const zeroY = subTop + subH / 2;
      const getSubY = (v: number) => zeroY - (v / maxAbs) * (subH / 2 - 4);

      for (let i = startIdx; i < endIdx; i++) {
        const m = this.macd[i];
        if (!m) continue;
        const x = getX(i);
        const y = getSubY(m.hist);
        ctx.fillStyle = m.hist >= 0 ? '#F6465D' : '#0ECB81';
        const top = Math.min(zeroY, y);
        const h = Math.max(1, Math.abs(y - zeroY));
        ctx.fillRect(x - Math.max(1.5, candleW * 0.45) / 2, top, Math.max(1.5, candleW * 0.45), h);
      }

      const drawMacdLine = (selector: (m: { dif: number; dea: number }) => number, color: string) => {
        ctx.beginPath();
        for (let i = startIdx; i < endIdx; i++) {
          const x = getX(i);
          const y = getSubY(selector(this.macd[i]));
          if (i === startIdx) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.2;
        ctx.stroke();
      };

      drawMacdLine((m) => m.dif, '#F59E0B');
      drawMacdLine((m) => m.dea, '#38BDF8');

      const fm = this.macd[focusIdx];
      ctx.fillStyle = '#9ca3af';
      ctx.fillText('MACD(12,26,9)', 10, subTop - 5);
      ctx.fillStyle = '#F59E0B';
      ctx.fillText(`DIF: ${fm?.dif.toFixed(2) ?? '--'}`, 112, subTop - 5);
      ctx.fillStyle = '#38BDF8';
      ctx.fillText(`DEA: ${fm?.dea.toFixed(2) ?? '--'}`, 202, subTop - 5);
      ctx.fillStyle = (fm?.hist ?? 0) >= 0 ? '#F6465D' : '#0ECB81';
      ctx.fillText(`MACD: ${fm?.hist.toFixed(2) ?? '--'}`, 292, subTop - 5);
      return;
    }

    if (this.subIndicator === 'KDJ') {
      const getSubY = (v: number) => subTop + subH - (Math.max(-10, Math.min(110, v)) + 10) / 120 * (subH - 6);
      const drawKdjLine = (selector: (p: { k: number; d: number; j: number }) => number, color: string) => {
        ctx.beginPath();
        for (let i = startIdx; i < endIdx; i++) {
          const x = getX(i);
          const y = getSubY(selector(this.kdj[i]));
          if (i === startIdx) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.2;
        ctx.stroke();
      };

      drawKdjLine((p) => p.k, '#F59E0B');
      drawKdjLine((p) => p.d, '#38BDF8');
      drawKdjLine((p) => p.j, '#A855F7');

      const fk = this.kdj[focusIdx];
      ctx.fillStyle = '#9ca3af';
      ctx.fillText('KDJ(9,3,3)', 10, subTop - 5);
      ctx.fillStyle = '#F59E0B';
      ctx.fillText(`K: ${fk?.k.toFixed(1) ?? '--'}`, 92, subTop - 5);
      ctx.fillStyle = '#38BDF8';
      ctx.fillText(`D: ${fk?.d.toFixed(1) ?? '--'}`, 162, subTop - 5);
      ctx.fillStyle = '#A855F7';
      ctx.fillText(`J: ${fk?.j.toFixed(1) ?? '--'}`, 232, subTop - 5);
      return;
    }

    if (this.subIndicator === 'RSI') {
      const getSubY = (v: number) => subTop + subH - (Math.max(0, Math.min(100, v)) / 100) * (subH - 6);
      ctx.beginPath();
      let started = false;
      for (let i = startIdx; i < endIdx; i++) {
        const val = this.rsi14[i];
        if (val === null) continue;
        const x = getX(i);
        const y = getSubY(val);
        if (!started) {
          ctx.moveTo(x, y);
          started = true;
        } else {
          ctx.lineTo(x, y);
        }
      }
      if (started) {
        ctx.strokeStyle = '#F59E0B';
        ctx.lineWidth = 1.3;
        ctx.stroke();
      }
      ctx.fillStyle = '#9ca3af';
      ctx.fillText('RSI(14)', 10, subTop - 5);
      ctx.fillStyle = '#F59E0B';
      ctx.fillText(`RSI: ${this.rsi14[focusIdx]?.toFixed(2) ?? '--'}`, 75, subTop - 5);
    }
  }

  private drawCrosshair(
    ctx: CanvasRenderingContext2D,
    cx: number,
    cy: number,
    plotW: number,
    mainTop: number,
    mainBottom: number,
    subTop: number,
    subBottom: number,
    cursorPrice: number,
    hoveredBar?: KLineBar
  ): void {
    ctx.save();
    ctx.setLineDash([3, 3]);
    ctx.strokeStyle = 'rgba(209, 212, 220, 0.45)';
    ctx.lineWidth = 1;

    // 垂直十字线
    ctx.beginPath();
    ctx.moveTo(Math.floor(cx) + 0.5, mainTop);
    ctx.lineTo(Math.floor(cx) + 0.5, mainBottom);
    ctx.moveTo(Math.floor(cx) + 0.5, subTop);
    ctx.lineTo(Math.floor(cx) + 0.5, subBottom);
    ctx.stroke();

    // 水平十字线
    if (cy >= mainTop && cy <= mainBottom) {
      ctx.beginPath();
      ctx.moveTo(0, Math.floor(cy) + 0.5);
      ctx.lineTo(plotW, Math.floor(cy) + 0.5);
      ctx.stroke();

      // 右侧游标价格框
      ctx.fillStyle = '#2a2e39';
      ctx.fillRect(plotW + 1, cy - 9, this.width - plotW - 1, 18);
      ctx.fillStyle = '#ffffff';
      ctx.font = '10.5px "JetBrains Mono", monospace';
      ctx.textAlign = 'right';
      ctx.fillText(Math.max(0, cursorPrice).toFixed(2), this.width - 4, cy + 3.5);
    }

    // 悬停 K 线 OHLC 浮层卡片
    if (hoveredBar) {
      const boxX = cx > plotW * 0.5 ? 10 : plotW - 142;
      const boxY = mainTop + 8;
      ctx.fillStyle = 'rgba(19, 23, 34, 0.92)';
      ctx.strokeStyle = '#2a2e39';
      ctx.setLineDash([]);
      ctx.fillRect(boxX, boxY, 134, 96);
      ctx.strokeRect(boxX, boxY, 134, 96);

      const isUp = hoveredBar.close >= hoveredBar.open;
      const cColor = isUp ? '#F6465D' : '#0ECB81';
      ctx.font = '10.5px "JetBrains Mono", monospace';
      ctx.textAlign = 'left';
      ctx.fillStyle = '#9ca3af';
      ctx.fillText(hoveredBar.time, boxX + 8, boxY + 16);

      ctx.fillText('开', boxX + 8, boxY + 34);
      ctx.fillText('高', boxX + 8, boxY + 50);
      ctx.fillText('低', boxX + 8, boxY + 66);
      ctx.fillText('收', boxX + 8, boxY + 82);

      ctx.textAlign = 'right';
      ctx.fillStyle = cColor;
      ctx.fillText(hoveredBar.open.toFixed(2), boxX + 126, boxY + 34);
      ctx.fillText(hoveredBar.high.toFixed(2), boxX + 126, boxY + 50);
      ctx.fillText(hoveredBar.low.toFixed(2), boxX + 126, boxY + 66);
      ctx.fillText(hoveredBar.close.toFixed(2), boxX + 126, boxY + 82);
    }

    ctx.restore();
  }
}

const PERIOD_OPTIONS: { id: ChartPeriod; label: string }[] = [
  { id: 'intraday', label: '分时' },
  { id: '5m', label: '5分' },
  { id: '15m', label: '15分' },
  { id: '30m', label: '30分' },
  { id: '60m', label: '60分' },
  { id: '1D', label: '日K' },
  { id: '1W', label: '周K' },
  { id: '1M', label: '月K' },
];

const MAIN_INDICATORS: { id: MainIndicator; label: string }[] = [
  { id: 'MA', label: 'MA均线' },
  { id: 'EMA', label: 'EMA' },
  { id: 'BOLL', label: 'BOLL布林' },
];

const SUB_INDICATORS: { id: SubIndicator; label: string }[] = [
  { id: 'VOL', label: 'VOL成交量' },
  { id: 'MACD', label: 'MACD' },
  { id: 'KDJ', label: 'KDJ' },
  { id: 'RSI', label: 'RSI' },
];

export const FinancialChart: React.FC = () => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const chartInstanceRef = useRef<NativeFinancialChartInstance | null>(null);

  // Zustand 精确订阅最小状态单元（仅订阅周期、指标与当前股票代码，不订阅高频 quotes 字典！）
  const selectedSymbol = useMarketStore((s) => s.selectedSymbol);
  const period = useMarketStore((s) => s.period);
  const mainIndicator = useMarketStore((s) => s.mainIndicator);
  const subIndicator = useMarketStore((s) => s.subIndicator);
  const setPeriod = useMarketStore((s) => s.setPeriod);
  // 缠论图层：笔/中枢/买卖点（数据来自 /api/quant/chan，与图表同周期K线）
  const [chanData, setChanData] = useState<ChanAnalysis | null>(null);
  const [showChan, setShowChan] = useState(true);
  const setMainIndicator = useMarketStore((s) => s.setMainIndicator);
  const setSubIndicator = useMarketStore((s) => s.setSubIndicator);

  // 1. 初始化原生 Canvas 图表实例并监听容器尺寸自适应
  useEffect(() => {
    if (!canvasRef.current || !containerRef.current) return;

    const instance = new NativeFinancialChartInstance(canvasRef.current);
    chartInstanceRef.current = instance;

    const rect = containerRef.current.getBoundingClientRect();
    instance.resize(rect.width, rect.height);

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        instance.resize(width, height);
      }
    });
    observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
      instance.destroy();
      chartInstanceRef.current = null;
    };
  }, []);

  // 2. 切换周期或指标时更新图表配置与数据
  useEffect(() => {
    const instance = chartInstanceRef.current;
    if (!instance) return;

    instance.setConfig(period, mainIndicator, subIndicator);

    const currentQuote = useMarketStore.getState().quotes[selectedSymbol];
    if (!currentQuote) return;

    // 优先读取真实缓存序列，同时向后端请求同步最新分时/K线
    const cachedIntraday = useMarketStore.getState().intradayPointsMap[selectedSymbol];
    if (period === 'intraday') {
      if (cachedIntraday && cachedIntraday.length > 0) {
        instance.setIntradayData(cachedIntraday, currentQuote.prevClose || 10);
      }
    } else {
      if (currentQuote.price && currentQuote.prevClose) {
        instance.setKLineData(generateKLinesForSymbol(currentQuote, period, 120), currentQuote.prevClose);
      }
    }

    let cancelled = false;
    fetch(`/api/market/klines/${encodeURIComponent(selectedSymbol)}?period=${encodeURIComponent(period)}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (cancelled || !data || !chartInstanceRef.current) return;
        const safePrev = data.prevClose || currentQuote.prevClose || 10;
        if (period === 'intraday' && Array.isArray(data.intraday)) {
          useMarketStore.getState().setIntradayPoints(selectedSymbol, data.intraday);
          chartInstanceRef.current.setIntradayData(data.intraday, safePrev);
        } else if (Array.isArray(data.klines)) {
          chartInstanceRef.current.setKLineData(data.klines, safePrev);
        }
      })
      .catch((e) => {
        console.error('[FinancialChart] 获取K线/分时数据失败:', selectedSymbol, e);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedSymbol, period, mainIndicator, subIndicator]);

  // 2.5 拉取缠论结构（按当前周期：5分/15分/日/周/月）：分时不请求；随标的/周期切换刷新
  useEffect(() => {
    if (period === 'intraday') {
      setChanData(null);
      chartInstanceRef.current?.setChanData(null, showChan);
      return;
    }
    let cancelled = false;
    fetch(`/api/quant/chan/${encodeURIComponent(selectedSymbol)}?period=${encodeURIComponent(period)}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (cancelled) return;
        if (data && data.status === 'ok' && data.chan) {
          setChanData(data.chan as ChanAnalysis);
        } else {
          setChanData(null);
        }
      })
      .catch((e) => {
        console.error('[FinancialChart] 获取缠论结构数据失败:', selectedSymbol, e);
        if (!cancelled) setChanData(null);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSymbol, period]);

  // 2.6 缠论数据/开关变化时下发给 Canvas 实例
  useEffect(() => {
    chartInstanceRef.current?.setChanData(chanData, showChan);
  }, [chanData, showChan]);

  // 3. 绑定命令式高频 Tick 通道：收到 WebSocket 快照时直接调用 instance.updateData(tick)
  useEffect(() => {
    const unsubscribe = subscribeSymbolImperativeTick(selectedSymbol, (tick) => {
      chartInstanceRef.current?.updateData(tick);
    });
    return unsubscribe;
  }, [selectedSymbol]);

  return (
    <div className="flex flex-col flex-1 min-h-0 bg-[#131722] select-none">
      {/* 图表周期与技术指标工具栏 */}
      <div className="flex items-center justify-between gap-2 px-3 py-1.5 bg-[#1e222d] border-b border-[#2a2e39] overflow-x-auto">
        {/* 周期切换组 */}
        <div className="flex items-center gap-1 shrink-0" role="tablist" aria-label="图表周期切换">
          {PERIOD_OPTIONS.map((opt) => {
            const active = period === opt.id;
            return (
              <button
                key={opt.id}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setPeriod(opt.id)}
                className={`px-2.5 py-1 text-xs font-medium rounded transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
                  active
                    ? 'bg-[#2962ff] text-white'
                    : 'text-[#9ca3af] hover:text-white hover:bg-[#2a2e39]'
                }`}
              >
                {opt.label}
              </button>
            );
          })}
        </div>

        {/* 主副图技术指标叠加组 */}
        <div className="flex items-center gap-1.5 shrink-0">
          {period !== 'intraday' && (
            <>
              <div className="flex items-center gap-0.5 bg-[#131722] p-0.5 rounded border border-[#2a2e39]">
                {MAIN_INDICATORS.map((ind) => {
                  const active = mainIndicator === ind.id;
                  return (
                    <button
                      key={ind.id}
                      type="button"
                      onClick={() => setMainIndicator(ind.id)}
                      className={`px-2 py-0.5 text-[11px] font-medium rounded transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
                        active
                          ? 'bg-[#2a2e39] text-[#F59E0B]'
                          : 'text-[#787b86] hover:text-[#d1d4dc]'
                      }`}
                    >
                      {ind.label}
                    </button>
                  );
                })}
              </div>

              <button
                type="button"
                data-testid="chan-layer-toggle"
                data-chan-bi={chanData?.bi_points?.length ?? 0}
                data-chan-zs={chanData?.zhongshu_list?.length ?? 0}
                data-chan-sig={chanData?.signals?.length ?? 0}
                data-chan-on={showChan ? '1' : '0'}
                onClick={() => setShowChan((v) => !v)}
                title={
                  chanData
                    ? `缠论图层：${chanData.bi_points?.length ?? 0} 笔 · ${chanData.zhongshu_list?.length ?? 0} 中枢 · ${chanData.signals?.length ?? 0} 买卖点（点击开关）`
                    : '缠论数据加载中…'
                }
                className={`px-2 py-0.5 text-[11px] font-medium rounded border transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
                  showChan && chanData
                    ? 'bg-[#F59E0B]/20 text-[#F59E0B] border-[#F59E0B]/50'
                    : 'bg-[#131722] text-[#787b86] hover:text-[#d1d4dc] border-[#2a2e39]'
                } ${chanData ? '' : 'opacity-50'}`}
              >
                缠论
                {chanData && (chanData.signals?.length ?? 0) > 0 && (
                  <span className="ml-1 font-mono text-[10px] opacity-80">
                    {chanData.signals.length}
                  </span>
                )}
              </button>

              <div className="flex items-center gap-0.5 bg-[#131722] p-0.5 rounded border border-[#2a2e39]">
                {SUB_INDICATORS.map((ind) => {
                  const active = subIndicator === ind.id;
                  return (
                    <button
                      key={ind.id}
                      type="button"
                      onClick={() => setSubIndicator(ind.id)}
                      className={`px-2 py-0.5 text-[11px] font-medium rounded transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
                        active
                          ? 'bg-[#2a2e39] text-[#38BDF8]'
                          : 'text-[#787b86] hover:text-[#d1d4dc]'
                      }`}
                    >
                      {ind.label}
                    </button>
                  );
                })}
              </div>

              <div className="hidden sm:flex items-center gap-1 ml-1">
                <button
                  type="button"
                  aria-label="放大K线"
                  onClick={() => chartInstanceRef.current?.zoomBy(-12)}
                  className="px-2 py-0.5 text-xs font-mono text-[#9ca3af] bg-[#131722] hover:text-white border border-[#2a2e39] rounded cursor-pointer"
                >
                  +
                </button>
                <button
                  type="button"
                  aria-label="缩小K线"
                  onClick={() => chartInstanceRef.current?.zoomBy(12)}
                  className="px-2 py-0.5 text-xs font-mono text-[#9ca3af] bg-[#131722] hover:text-white border border-[#2a2e39] rounded cursor-pointer"
                >
                  -
                </button>
                <button
                  type="button"
                  aria-label="重置图表视图"
                  onClick={() => chartInstanceRef.current?.resetView()}
                  className="px-2 py-0.5 text-[11px] text-[#9ca3af] bg-[#131722] hover:text-white border border-[#2a2e39] rounded whitespace-nowrap shrink-0 cursor-pointer"
                >
                  复位
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      {/* 原生 Canvas 挂载容器 (支持单指拖拽平移与双指捏合缩放) */}
      <div
        ref={containerRef}
        className="relative flex-1 min-h-[260px] w-full overflow-hidden touch-none"
      >
        <canvas
          ref={canvasRef}
          data-testid="financial-kline-canvas"
          className="block w-full h-full cursor-crosshair"
        />
      </div>
    </div>
  );
};
