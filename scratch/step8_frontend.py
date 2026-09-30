# -*- coding: utf-8 -*-
"""交付③-A 前端：模拟页加「推演引擎」选择 + LLM 推演结构化渲染面板。

三处改动：① 控制区加引擎单选（规则秒级 / LLM 1-3 分钟）
          ② simBoard 后面加 llmBoard 容器
          ③ runSim() 按引擎拼 engine=llm 并渲染 LLM 面板（含未配置密钥的回落提示）
每处断言唯一命中。
"""
import pathlib
import subprocess

IDX = pathlib.Path(r"D:\股票看盘\web\templates\index.html")
t = IDX.read_text(encoding="utf-8")
fails = []


def edit(old, new, tag, expect=1):
    global t
    n = t.count(old)
    if n != expect:
        fails.append(f'{tag}: 命中 {n} 次(期望 {expect})')
        print(f'  FAIL  {tag}: 命中 {n} 次')
        return
    t = t.replace(old, new)
    print(f'  OK    {tag}')


# ① 引擎选择器
edit("""          <button class="btn btn-primary" style="padding:10px 20px;font-weight:700;display:flex;align-items:center;gap:6px;" onclick="runSim()">
            <span>🔮</span>
            <span>启动推演</span>
          </button>
        </div>""",
     """          <button class="btn btn-primary" style="padding:10px 20px;font-weight:700;display:flex;align-items:center;gap:6px;" onclick="runSim()">
            <span>🔮</span>
            <span>启动推演</span>
          </button>
        </div>

        <!-- 推演引擎选择（2026-09-30 新增：规则秒级 / LLM 读当日消息面） -->
        <div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap;font-size:13px;margin-bottom:10px;padding:8px 10px;background:var(--bg-subtle);border:1px solid var(--border);border-radius:8px;">
          <span style="color:var(--text-secondary);font-weight:600;">🧠 推演引擎:</span>
          <label style="display:flex;align-items:center;gap:5px;cursor:pointer;">
            <input type="radio" name="simEngine" value="rule" checked onchange="toggleSimEngine()">
            <span>规则引擎（秒级）</span>
          </label>
          <label style="display:flex;align-items:center;gap:5px;cursor:pointer;">
            <input type="radio" name="simEngine" value="llm" onchange="toggleSimEngine()">
            <span>LLM 消息面推演（读当日事件表）</span>
          </label>
          <span id="simEngineNote" style="color:var(--text-muted);"></span>
        </div>""", 'HTML: 引擎选择器')

# ② LLM 面板容器
edit('<div id="simBoard" style="display:none;margin-bottom:16px;"></div>',
     '<div id="simBoard" style="display:none;margin-bottom:16px;"></div>\n'
     '      <!-- LLM 推演结构化结果（2026-09-30 新增） -->\n'
     '      <div id="llmBoard" style="display:none;margin-bottom:16px;"></div>',
     'HTML: llmBoard 容器')

# ③ runSim: 读取引擎 + 提示语 + 面板清理
edit("""  box.style.display = 'block';
  box.textContent = '⏳ 正在加载势力博弈记忆与市场即时数据，推演中...';
  if(board) board.style.display = 'none';""",
     """  const eng = simEngine();
  const llmBox = document.getElementById('llmBoard');
  box.style.display = 'block';
  box.textContent = eng === 'llm'
    ? '⏳ LLM 消息面推演中：当日事件表 → 九方冲击矩阵 → 多轮博弈（约 1-3 分钟，请勿关闭页面）...'
    : '⏳ 正在加载势力博弈记忆与市场即时数据，推演中...';
  if(board) board.style.display = 'none';
  if(llmBox) llmBox.style.display = 'none';""", 'JS: runSim 引擎提示')

edit("""    if(code) params.push('code=' + code);
    const r = await fetch('/api/sim' + (params.length ? ('?' + params.join('&')) : ''));""",
     """    if(code) params.push('code=' + code);
    if(eng === 'llm' && !code) params.push('engine=llm');
    const r = await fetch('/api/sim' + (params.length ? ('?' + params.join('&')) : ''));""",
     'JS: runSim 拼 engine')

edit("""      box.textContent = head + d.text;

      if(board && d.forces && d.forces.length > 0){""",
     """      box.textContent = head + d.text;
      if(llmBox) renderLLMPanel(llmBox, d);

      if(board && d.forces && d.forces.length > 0){""", 'JS: runSim 渲染 LLM 面板')

# ④ 新增 JS 函数
edit("async function updateFeedStatus(){",
     """/* ===== 推演引擎选择 + LLM 推演面板（2026-09-30 新增 · 消息面→推演 交付③）===== */
function simEngine(){
  const el = document.querySelector('input[name="simEngine"]:checked');
  return el ? el.value : 'rule';
}
function toggleSimEngine(){
  const note = document.getElementById('simEngineNote');
  if(!note) return;
  note.textContent = simEngine() === 'llm'
    ? 'LLM 读当日消息面事件表推演：1-3 分钟、约 1 万 tokens；未配密钥/调用失败会自动回落规则引擎'
    : '秒级返回：市场微结构 + 九方传染模型';
}
function renderLLMPanel(el, d){
  const llm = d.llm || {};
  el.style.display = 'block';
  if(!llm.ok){
    el.innerHTML = '<div class="card" style="border-left:4px solid #f59e0b;">'
      + '<div style="font-weight:700;color:#fbbf24;font-size:16px;">🤖 LLM 推演未执行 —— 已回落规则引擎</div>'
      + '<div style="margin-top:6px;color:var(--text-secondary);font-size:13px;">原因: '
      + (llm.reason || '-') + '<br>' + (llm.hint || '') + '</div></div>';
    return;
  }
  const impact = llm.impact || {};
  const vals = Object.values(impact).map(v => Math.abs(Number(v) || 0));
  const maxAbs = Math.max(1, ...vals);
  let bars = '';
  for(const k in impact){
    const v = Number(impact[k]) || 0;
    const w = Math.round(Math.abs(v) / maxAbs * 100);
    const col = v > 0 ? '#ff4d4f' : (v < 0 ? '#22c55e' : '#94a3b8');
    bars += '<div style="display:flex;align-items:center;gap:8px;margin:3px 0;font-size:13px;">'
      + '<span style="width:82px;color:var(--text-secondary);">' + k + '</span>'
      + '<span style="flex:1;background:var(--bg-subtle);height:12px;border-radius:6px;overflow:hidden;">'
      + '<span style="display:block;height:12px;width:' + w + '%;background:' + col + ';"></span></span>'
      + '<span style="width:46px;text-align:right;font-weight:700;color:' + col + ';">'
      + (v > 0 ? '+' : '') + v + '</span></div>';
  }
  let themes = '';
  (llm.theme_priority || []).slice(0, 8).forEach(function(t){
    const p = Number(t.polarity) || 0;
    const col = p > 0 ? '#ff4d4f' : (p < 0 ? '#22c55e' : '#94a3b8');
    themes += '<span style="display:inline-block;margin:3px 6px 3px 0;padding:3px 9px;border-radius:12px;'
      + 'border:1px solid ' + col + '55;background:' + col + '18;color:' + col + ';font-size:13px;">'
      + t.sector + ' · 强度' + t.strength + '</span>';
  });
  let rounds = '';
  (llm.rounds || []).forEach(function(r){
    rounds += '<div style="margin:5px 0;font-size:13px;color:var(--text-secondary);">'
      + '<b style="color:#38bdf8;">R' + r.round + '</b> ' + (r.cross || r.error || '-')
      + (r.next_day ? '<br><span style="color:var(--text-pure);">次日定性：' + r.next_day + '</span>' : '')
      + (r.confidence !== undefined && r.confidence !== null ? '（置信 ' + r.confidence + '）' : '') + '</div>';
  });
  let risks = '';
  (llm.risk_points || []).forEach(function(r){
    risks += '<li style="margin:3px 0;font-size:13px;"><b style="color:#fbbf24;">' + r.item + '</b>'
      + '<span style="color:var(--text-secondary);"> —— ' + (r.reason || '') + '</span></li>';
  });
  let scen = '';
  [['optimistic', '乐观', '#ff4d4f'], ['neutral', '中性', '#94a3b8'], ['pessimistic', '悲观', '#22c55e']]
    .forEach(function(kv){
      const s = (llm.scenarios || {})[kv[0]] || {};
      if(!s.trigger && !s.path) return;
      scen += '<div style="flex:1;min-width:200px;padding:8px 10px;border:1px solid ' + kv[2] + '44;'
        + 'border-radius:8px;background:' + kv[2] + '10;">'
        + '<div style="font-weight:700;color:' + kv[2] + ';">' + kv[1] + '</div>'
        + '<div style="font-size:13px;color:var(--text-secondary);margin-top:4px;">触发：' + (s.trigger || '-') + '</div>'
        + '<div style="font-size:13px;margin-top:3px;">' + (s.path || '') + '</div>'
        + '<div style="font-size:13px;color:var(--text-muted);margin-top:3px;">方向：'
        + ((s.sectors || []).join('、') || '-') + '</div></div>';
    });
  const use = llm.usage || {};
  el.innerHTML = '<div class="card" style="border-left:4px solid #38bdf8;">'
    + '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">'
    + '<div style="font-weight:700;font-size:17px;color:var(--text-pure);">🤖 LLM 消息面推演'
    + (llm.dry_run ? '<span style="color:#fbbf24;">（DRY-RUN 样例）</span>' : '') + '</div>'
    + '<div style="font-size:13px;color:var(--text-secondary);">模型 ' + (llm.model || '-')
    + '　|　' + (use.calls || 0) + ' 次调用 / ' + (use.total_tokens || 0) + ' tokens　|　'
    + (llm.elapsed_s || '-') + 's　|　种子 sha ' + (llm.seed_sha || '-')
    + (llm.partial ? '　|　<span style="color:#fbbf24;">部分轮次失败</span>' : '') + '</div></div>'
    + '<div style="margin-top:10px;font-size:13px;color:var(--text-secondary);">'
    + '合力 <b style="color:var(--text-pure);">' + (llm.net || 0) + '</b>（刻度 ' + (llm.net_pct || 0) + '）'
    + '　权重口径与规则引擎一致；数值聚合仍由规则引擎完成</div>'
    + '<div style="margin-top:10px;"><b style="font-size:14px;">九方冲击矩阵（LLM 判断）</b>' + bars + '</div>'
    + (themes ? '<div style="margin-top:12px;"><b style="font-size:14px;">板块 / 题材优先级</b><div style="margin-top:4px;">' + themes + '</div></div>' : '')
    + (rounds ? '<div style="margin-top:12px;"><b style="font-size:14px;">多轮博弈修正</b>' + rounds + '</div>' : '')
    + (risks ? '<div style="margin-top:12px;"><b style="font-size:14px;">风险点</b><ul style="margin:6px 0 0 18px;padding:0;">' + risks + '</ul></div>' : '')
    + (scen ? '<div style="margin-top:12px;"><b style="font-size:14px;">三档情景预案</b><div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:6px;">' + scen + '</div></div>' : '')
    + (llm.narrative ? '<div style="margin-top:12px;font-size:14px;"><b>叙事：</b>' + llm.narrative + '</div>' : '')
    + ((llm.key_variables || []).length ? '<div style="margin-top:6px;font-size:13px;color:var(--text-secondary);">关键变量：' + llm.key_variables.join(' / ') + '</div>' : '')
    + '</div>';
  return;
}

async function updateFeedStatus(){""", 'JS: 新增 LLM 面板函数')

if fails:
    print()
    print('断言未命中, 不落盘:', fails)
    raise SystemExit(1)

IDX.write_text(t, encoding="utf-8")
print(f'\n已写回 {IDX} ({IDX.stat().st_size}B)')
# 语法自检：抽出 <script> 段做一次 JS 括号配平（无 node 时的兜底检查）
scripts = t.split('<script>')[1].split('</script>')[0] if '<script>' in t else ''
for ch_open, ch_close, name in (('{', '}', '花括号'), ('(', ')', '圆括号'), ('[', ']', '方括号')):
    print(f'  {name}配平: {scripts.count(ch_open) - scripts.count(ch_close)}（应为 0，仅作粗检）')