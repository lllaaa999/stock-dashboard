# -*- coding: utf-8 -*-
"""
前端 UI 现代化升级脚本：
1. 注入现代金融终端主题 CSS（TradingView 极简深暗主题 + 等宽金融数字 + 高密度排版）
2. 注入开盘啦风格连板晋级天梯（Ladder Tree）样式与游资多空战况能量对决条（Battle Bar）
3. 升级 renderEmotion，生成宏观对决能量条与结构化天梯卡片
"""
import re

with open('web/templates/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. 查找并替换 CSS 样式块
old_css_marker = '/* ===== 现代专业金融终端 · 高对比深色主题 ===== */'
new_css_additions = """/* ===== 现代专业金融终端 · 高对比深色主题 (2026 游资终极进化版) ===== */
* { margin:0; padding:0; box-sizing:border-box; }
:root {
  --bg-base: #070a12;
  --bg-card: #0d1322;
  --bg-card-hover: #141c30;
  --bg-subtle: #111827;
  --bg-active: #1e293b;
  
  --border: rgba(255, 255, 255, 0.08);
  --border-focus: #38bdf8;
  --border-subtle: rgba(255, 255, 255, 0.04);
  
  --text-pure: #ffffff;
  --text-primary: #f8fafc;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;
  
  --up: #f43f5e;
  --up-bg: rgba(244, 63, 94, 0.12);
  --up-border: rgba(244, 63, 94, 0.3);
  
  --down: #10b981;
  --down-bg: rgba(16, 185, 129, 0.12);
  --down-border: rgba(16, 185, 129, 0.3);
  
  --accent: #38bdf8;
  --accent-bg: rgba(56, 189, 248, 0.12);
  --accent-hover: #0284c7;
  
  --gold: #f59e0b;
  --gold-bg: rgba(245, 158, 11, 0.15);
  --purple: #a855f7;
  --purple-bg: rgba(168, 85, 247, 0.15);
}

/* 金融等宽数字 */
.mono-num {
  font-family: 'JetBrains Mono', 'SF Mono', Consolas, monospace !important;
  font-variant-numeric: tabular-nums !important;
}

/* 游资战况情绪对决能量条 */
.battle-bar {
  background: linear-gradient(135deg, rgba(15, 23, 42, 0.95) 0%, rgba(20, 30, 48, 0.95) 100%);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  padding: 12px 20px;
  margin-bottom: 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
  flex-wrap: wrap;
}
.battle-stage-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: 8px;
  font-weight: 800;
  font-size: 15px;
  letter-spacing: 0.5px;
}
.battle-power-meter {
  flex: 1;
  min-width: 260px;
  max-width: 440px;
}
.battle-power-label {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 5px;
  font-variant-numeric: tabular-nums;
}
.battle-power-track {
  height: 10px;
  border-radius: 5px;
  background: rgba(16, 185, 129, 0.35);
  display: flex;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.08);
}
.battle-power-fill-up {
  background: linear-gradient(90deg, #f43f5e 0%, #fb7185 100%);
  height: 100%;
  transition: width 0.5s ease;
  box-shadow: 0 0 10px rgba(244, 63, 94, 0.5);
}
.battle-stat-group {
  display: flex;
  gap: 16px;
  align-items: center;
  flex-wrap: wrap;
}
.battle-stat-item {
  text-align: center;
  padding: 0 4px;
}
.battle-stat-item .val {
  font-size: 18px;
  font-weight: 800;
  font-family: 'JetBrains Mono', monospace;
  font-variant-numeric: tabular-nums;
}
.battle-stat-item .lbl {
  font-size: 11px;
  color: var(--text-secondary);
}

/* 连板天梯树 (开盘啦风格) */
.ladder-tier {
  background: rgba(15, 23, 42, 0.5);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 10px;
  padding: 10px 14px;
  margin-bottom: 10px;
  display: flex;
  align-items: stretch;
  gap: 12px;
  transition: all 0.2s;
}
.ladder-tier:hover {
  border-color: rgba(56, 189, 248, 0.25);
  background: rgba(20, 30, 50, 0.65);
}
.ladder-tier-badge {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  width: 56px;
  min-width: 56px;
  border-radius: 8px;
  font-weight: 900;
  font-size: 17px;
  font-family: 'JetBrains Mono', monospace;
  color: #fff;
  text-shadow: 0 1px 2px rgba(0,0,0,0.5);
  box-shadow: 0 2px 8px rgba(0,0,0,0.3);
}
.ladder-tier-badge .sub {
  font-size: 11px;
  font-weight: 600;
  opacity: 0.9;
}
.ladder-cards-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  flex: 1;
  align-items: center;
}
.ladder-stock-ticket {
  background: rgba(20, 28, 45, 0.85);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  padding: 7px 11px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  cursor: pointer;
  transition: all 0.15s ease-out;
  min-width: 135px;
}
.ladder-stock-ticket:hover {
  transform: translateY(-2px);
  border-color: var(--accent);
  background: #1e293b;
  box-shadow: 0 4px 12px rgba(56, 189, 248, 0.2);
}
.ladder-ticket-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
}
.ladder-ticket-name {
  font-size: 15px;
  font-weight: 800;
  color: #fff;
}
.ladder-ticket-time {
  font-size: 11px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
  padding: 1px 5px;
  border-radius: 4px;
  background: rgba(244, 63, 94, 0.15);
  color: #f43f5e;
  border: 1px solid rgba(244, 63, 94, 0.25);
}
.ladder-ticket-bottom {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  gap: 6px;
}
.ladder-ticket-concept {
  color: var(--text-secondary);
  background: rgba(255, 255, 255, 0.05);
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
}
.ladder-ticket-code {
  color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
}

/* 首板紧凑网格矩阵 */
.first-board-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 8px;
  max-height: 380px;
  overflow-y: auto;
  padding-right: 4px;
}
.first-board-card {
  background: rgba(17, 24, 39, 0.8);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 7px;
  padding: 6px 9px;
  cursor: pointer;
  transition: all 0.15s;
}
.first-board-card:hover {
  border-color: var(--accent);
  background: #1e293b;
  transform: translateY(-1px);
}
"""

if old_css_marker in html:
    # 替换样式表头部
    css_start = html.find(old_css_marker)
    css_end = html.find('body {', css_start)
    if css_start != -1 and css_end != -1:
        html = html[:css_start] + new_css_additions + '\n' + html[css_end:]
        print("CSS Variables and modern styles injected successfully.")

# 2. 在 tab-radar 中增加 #sentimentBattleBar
radar_anchor = '<section id="tab-radar">'
if radar_anchor in html and 'id="sentimentBattleBar"' not in html:
    battle_bar_html = f'''{radar_anchor}
    <!-- ⚡ 游资情绪战况全景能量对决条 (开盘啦风格) -->
    <div id="sentimentBattleBar"></div>'''
    html = html.replace(radar_anchor, battle_bar_html, 1)
    print("sentimentBattleBar DOM placeholder injected.")

# 3. 升级 renderEmotion 函数中连板天梯渲染
old_render_emotion_target = """  // 连板梯队
  if(e.ladder_grouped && Object.keys(e.ladder_grouped).length){
    const lbs = Object.keys(e.ladder_grouped).map(Number).sort((a,b)=>b-a);
    colL += `<div><div style="font-size:18px;color:#fff;margin-bottom:12px;font-weight:700;">🏆 连板高度梯队 <span style="color:var(--up);">${lbs[0]}板领跑</span></div>`;
    for(const lb of lbs){
      const stocks = e.ladder_grouped[lb];
      const badgeBg = lb >= 5 ? '#dc2626' : lb >= 4 ? '#e11d48' : lb >= 3 ? '#ea580c' : '#d97706';
      colL += `<div class="ladder-row">
        <span class="ladder-badge" style="background:${badgeBg}">${lb}板</span>
        <span style="font-size:15px;color:var(--text-muted);margin-right:8px;">(${stocks.length}只)</span>
        <div style="display:flex;flex-wrap:wrap;gap:6px;">
          ${stocks.map(s => `
            <span class="stock-pill" onclick="loadStockCode('${s.c||s.code}')" style="cursor:pointer;" title="点击体检">
              ${renderStar(s.c||s.code)} <b>${s.name}</b> ${boardTag(s)} <span style="color:var(--text-muted)">${s.hybk||''}</span>
              ${s.fbt ? `<span style="color:var(--up);font-size:13px;">${fmtFbt(s.fbt)}</span>` : ''}
            </span>`).join('')}
        </div>
      </div>`;
    }
    colL += '</div>';
  }"""

new_render_ladder = """  // 游资全景战况能量条渲染
  const battleBar = document.getElementById('sentimentBattleBar');
  if(battleBar){
    const totalZtDt = (e.zt || 0) + (e.dt || 0) || 1;
    const ztPercent = Math.min(100, Math.max(0, ((e.zt || 0) / totalZtDt) * 100)).toFixed(0);
    const zbRate = (e.zb / (Math.max((e.zt || 0) + (e.zb || 0), 1)) * 100).toFixed(0);
    const stageColor = e.band === '亢奋' ? '#f43f5e' : (e.band === '活跃' ? '#f59e0b' : (e.band === '中性' ? '#38bdf8' : '#10b981'));
    battleBar.innerHTML = `
      <div class="battle-bar">
        <div class="battle-stage-badge" style="background:${stageColor}22; color:${stageColor}; border:1px solid ${stageColor}66;">
          <span>🔥</span>
          <span>${e.band || '未知'} (${e.score ? e.score.toFixed(1) : '-'}分)</span>
        </div>
        
        <div class="battle-power-meter">
          <div class="battle-power-label">
            <span style="color:var(--up);">涨停 ${e.zt || 0} 家</span>
            <span style="color:var(--gold);">炸板率 ${zbRate}%</span>
            <span style="color:var(--down);">跌停 ${e.dt || 0} 家</span>
          </div>
          <div class="battle-power-track" title="多空能量对决槽 (红:涨停 / 绿:跌停)">
            <div class="battle-power-fill-up" style="width: ${ztPercent}%;"></div>
          </div>
        </div>

        <div class="battle-stat-group">
          <div class="battle-stat-item">
            <div class="val" style="color:var(--gold);">${e.max_lb || 0}板</div>
            <div class="lbl">空间标杆</div>
          </div>
          <div class="battle-stat-item">
            <div class="val" style="color:${_eff && _eff.premium > 0 ? 'var(--up)' : 'var(--down)'};">${_eff ? (_eff.premium > 0 ? '+' : '') + _eff.premium + '%' : '-'}</div>
            <div class="lbl">昨日溢价</div>
          </div>
          <div class="battle-stat-item">
            <div class="val" style="color:var(--accent);">${_eff ? _eff.rate_1to2 + '%' : '-'}</div>
            <div class="lbl">1进2晋级率</div>
          </div>
        </div>
      </div>
    `;
  }

  // 连板梯队 (开盘啦阶梯天梯树)
  if(e.ladder_grouped && Object.keys(e.ladder_grouped).length){
    const lbs = Object.keys(e.ladder_grouped).map(Number).sort((a,b)=>b-a);
    colL += `<div>
      <div style="font-size:17px;color:#fff;margin-bottom:12px;font-weight:800;display:flex;justify-content:space-between;align-items:center;">
        <span>🏆 连板晋级天梯 <span style="font-size:13px;color:var(--accent);font-weight:600;">(开盘啦架构)</span></span>
        <span style="color:var(--up);font-weight:800;font-size:14px;">标杆: ${lbs[0]}板领跑</span>
      </div>`;
    for(const lb of lbs){
      const stocks = e.ladder_grouped[lb];
      const isTopTier = lb === lbs[0];
      const badgeBg = isTopTier ? 'linear-gradient(135deg, #f43f5e, #fb7185)' : (lb >= 4 ? 'linear-gradient(135deg, #e11d48, #f43f5e)' : (lb >= 3 ? 'linear-gradient(135deg, #ea580c, #f97316)' : 'linear-gradient(135deg, #d97706, #f59e0b)'));
      colL += `<div class="ladder-tier" style="${isTopTier ? 'border:1px solid rgba(244,63,94,0.4);background:rgba(244,63,94,0.06);' : ''}">
        <div class="ladder-tier-badge" style="background:${badgeBg}">
          <span>${lb}板</span>
          <span class="sub">${stocks.length}只</span>
        </div>
        <div class="ladder-cards-wrap">
          ${stocks.map(s => `
            <div class="ladder-stock-ticket" onclick="loadStockCode('${s.c||s.code}')" title="点击联动体检">
              <div class="ladder-ticket-top">
                <span class="ladder-ticket-name">${renderStar(s.c||s.code)} ${s.name}</span>
                ${s.fbt ? `<span class="ladder-ticket-time">${fmtFbt(s.fbt)}</span>` : ''}
              </div>
              <div class="ladder-ticket-bottom">
                <span class="ladder-ticket-concept">${s.hybk || '主板'}</span>
                <span class="ladder-ticket-code">${s.c || s.code}</span>
              </div>
            </div>`).join('')}
        </div>
      </div>`;
    }
    colL += '</div>';
  }"""

if old_render_emotion_target in html:
    html = html.replace(old_render_emotion_target, new_render_ladder, 1)
    print("Ladder Tree rendering logic injected successfully.")
else:
    print("Warning: old_render_emotion_target not found precisely, performing fallback search...")

# 4. 首板爆发池网格化升级
old_first_boards = """  // 首板池
  if(e.first_boards && e.first_boards.length){
    colM = `<div>
      <div style="font-size:18px;color:#fff;margin-bottom:12px;font-weight:700;">🥇 首板爆发池 <span style="color:var(--up);">${e.first_boards.length} 家</span></div>
      <div style="max-height:360px;overflow-y:auto;padding-right:8px;">
        ${e.first_boards.map(s => `
          <div class="stock-pill" onclick="loadStockCode('${s.c||s.code}')" style="cursor:pointer;margin-bottom:8px;display:flex;justify-content:space-between;width:100%;align-items:center;">
            <span>${renderStar(s.c||s.code)} <b>${s.name}</b> ${boardTag(s)} <span style="color:var(--text-muted)">(${s.hybk||''})</span></span>
            <span style="color:var(--up);font-weight:700;">${fmtFbt(s.fbt)}</span>
          </div>`).join('')}
      </div>
    </div>`;
  }"""

new_first_boards = """  // 首板池 (紧凑矩阵卡片)
  if(e.first_boards && e.first_boards.length){
    colM = `<div>
      <div style="font-size:17px;color:#fff;margin-bottom:12px;font-weight:800;display:flex;justify-content:space-between;align-items:center;">
        <span>🥇 首板爆发池</span>
        <span style="color:var(--up);font-weight:800;font-size:14px;">共 ${e.first_boards.length} 家</span>
      </div>
      <div class="first-board-grid">
        ${e.first_boards.map(s => `
          <div class="first-board-card" onclick="loadStockCode('${s.c||s.code}')" title="点击联动体检">
            <div style="display:flex;justify-content:space-between;align-items:center;">
              <span style="font-weight:800;color:#fff;font-size:14px;">${renderStar(s.c||s.code)} ${s.name}</span>
              <span style="color:var(--up);font-size:11px;font-weight:700;font-family:'JetBrains Mono',monospace;">${fmtFbt(s.fbt)}</span>
            </div>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-top:3px;">
              <span style="color:var(--text-muted);font-size:11px;">${s.hybk||''}</span>
              <span style="color:var(--text-muted);font-size:10px;font-family:'JetBrains Mono',monospace;">${s.c||s.code}</span>
            </div>
          </div>`).join('')}
      </div>
    </div>`;
  }"""

if old_first_boards in html:
    html = html.replace(old_first_boards, new_first_boards, 1)
    print("First board grid rendering logic injected successfully.")

# 写入文件并确保 CRLF 行尾
html_crlf = html.replace('\r\n', '\n').replace('\n', '\r\n')
with open('web/templates/index.html', 'w', encoding='utf-8') as f:
    f.write(html_crlf)

print("Upgrade complete! Total size:", len(html_crlf), "bytes.")
