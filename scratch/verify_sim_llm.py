# -*- coding: utf-8 -*-
"""交付② 验证：LLM 推演链路（配置/种子/JSON 容错/重试/多轮/落盘/无密钥回落）+ 引擎接入口行为。

全部离线可复现：用内置样例响应(mock_call)跑通链路；用真实 _sim_pipeline 验证冲击注入确实生效。
"""
import io
import json
import pathlib
import sys
import urllib.error

ROOT = pathlib.Path(r"D:\股票看盘")
sys.path.insert(0, str(ROOT / "scripts"))
import stock_dashboard as sd          # noqa: E402
import sim_llm as sl                  # noqa: E402

fails = []


def check(name, cond, extra=''):
    print(('PASS  ' if cond else 'FAIL  ') + name + (('   ' + str(extra)) if extra else ''))
    if not cond:
        fails.append(name)


print("== 1. 配置发现（无密钥时如实报告）==")
cfg = sl.load_llm_config(quiet=True)
check("默认 base_url 指向 DeepSeek", cfg['base_url'].startswith('https://api.deepseek.com'), cfg['base_url'])
check("默认模型 deepseek-chat", cfg['model'] == 'deepseek-chat', cfg['model'])
check("has_key 为布尔且与来源一致", isinstance(cfg['has_key'], bool), (cfg['has_key'], cfg['source']))
check("来源可见", cfg['source'] in ('none', 'env', 'config/llm.local.json', 'hermes .env (DashScope)'), cfg['source'])

print()
print("== 2. 种子构建（读交付①的事件表）==")
seed, err = sl.build_seed(None, 20)
if err:
    check("当日事件表存在（需先跑 news_events.py）", False, err)
    seed = None
else:
    check("含日期/事件表/板块榜三段", all(k in seed['text'] for k in ('【日期】', '【当日事件表', '【消息面板块榜')))
    check("事件条数 = 20", seed['events_used'] == 20, seed['events_used'])
    check("sha 16 位", len(seed['sha']) == 16, seed['sha'])
    check("种子紧凑 <4000 字符", len(seed['text']) < 4000, len(seed['text']))
    check("市场微结构已带入", isinstance(seed['facts'], dict), list(seed['facts'])[:4])

print()
print("== 3. JSON 容错解析 ==")
for name, txt in [('纯 JSON', '{"a":1}'), ('```json 包裹', '```json\n{"a":1}\n```'),
                  ('带前后解释文字', '结果如下：{"a":1}\n以上。')]:
    try:
        check(f"  {name}", sl._extract_json(txt) == {'a': 1})
    except Exception as e:
        check(f"  {name}", False, f'{type(e).__name__}: {e}')
try:
    sl._extract_json('完全没有 JSON')
    check("  无 JSON → 抛错", False)
except Exception:
    check("  无 JSON → 抛错", True)

print()
print("== 4. response_format 不被支持时自动重试 ==")
attempts = []


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def read(self):
        return json.dumps(self._p).encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_urlopen(req, timeout=None):
    attempts.append(json.loads(req.data.decode('utf-8')))
    if len(attempts) == 1:
        raise urllib.error.HTTPError(req.full_url, 400, 'Bad Request', None,
                                     io.BytesIO(b'response_format unsupported'))
    return _Resp({'choices': [{'message': {'content': '{"ok":1}'}}], 'usage': {'total_tokens': 10}})


_real_urlopen = sl.urllib.request.urlopen
sl.urllib.request.urlopen = fake_urlopen
try:
    cfg_t = dict(cfg, api_key='dummy', model='dummy')
    content, usage = sl.call_llm([{'role': 'user', 'content': 'x'}], cfg_t)
    check("首次 400 后去掉 response_format 重试成功", content == '{"ok":1}' and len(attempts) == 2, len(attempts))
    check("重试请求里确实没有 response_format", 'response_format' not in attempts[1], list(attempts[1].keys()))
finally:
    sl.urllib.request.urlopen = _real_urlopen

print()
print("== 5. dry-run 全链路（不调 API）==")
p = sl.run(dry_run=True, quiet=True)
check("run() 成功且 engine=llm", p.get('ok') and p.get('engine') == 'llm', p.get('reason'))
check("冲击矩阵覆盖九方", len(p.get('impact') or {}) == 9, list((p.get('impact') or {}).keys()))
check("多轮行数 = rounds-1（默认 3 轮 → 2 行）", len(p.get('rounds') or []) == 2, len(p.get('rounds') or []))
check("加权合力为数值", isinstance(p.get('net'), (int, float)), p.get('net'))
check("板块优先级/风险点/情景齐备", bool(p.get('theme_priority')) and bool(p.get('risk_points')) and bool(p.get('scenarios')))
check("token 记账有效", (p.get('usage') or {}).get('total_tokens', 0) > 0, p.get('usage'))
out = pathlib.Path(p.get('saved_to', ''))
check("归档文件已落盘且可解析", out.exists() and isinstance(json.loads(out.read_text(encoding='utf-8')), dict), str(out))
check("归档里保留原始响应(可对账)", 'raw_first_call' in json.loads(out.read_text(encoding='utf-8')))
check("dry_run 标记为真", p.get('dry_run') is True)
check("多轮含交叉判断与次日定性", all(r.get('cross') and r.get('next_day') for r in (p.get('rounds') or [])),
      [(r.get('cross'), r.get('next_day')) for r in (p.get('rounds') or [])][:1])
check("冲击值确实落进最终立场(非全零)", any(abs(v) > 0 for v in (p.get('stances_final') or {}).values()),
      p.get('stances_final'))

print()
print("== 6. 无密钥时不硬调、如实回落 ==")
if cfg['has_key']:
    print("SKIP  已检测到密钥，跳过回落测试（避免真实计费调用）")
else:
    r = sl.run(dry_run=False, quiet=True)
    check("无密钥 → ok=False 且 reason=no_api_key", r.get('ok') is False and r.get('reason') == 'no_api_key', r.get('reason'))
    check("给出可执行的指引", 'llm.local.json' in (r.get('hint') or ''), (r.get('hint') or '')[:60])

print()
print("== 7. 引擎接入口（真实 _sim_pipeline 行为）==")
ag0 = {n: 0.0 for n, _w, _d in sl.FORCES}
base, _ = sd._sim_pipeline(dict(ag0), use_memory=False, verbose=False)
llmish, _ = sd._sim_pipeline(dict(ag0), use_memory=False, verbose=False,
                             impact_override={'游资': 30, '机构': -20}, impact_note='验证')
check("冲击注入生效：游资偏多、机构偏空", llmish['游资'] > base['游资'] and llmish['机构'] < base['机构'],
      (round(llmish['游资'], 1), round(base['游资'], 1), round(llmish['机构'], 1), round(base['机构'], 1)))
try:
    ag2, _ = sd._sim_pipeline(dict(ag0), use_memory=False, verbose=False,
                              impact_override={'游资': 30, 'theme_priority': [{'sector': '银行'}]})
    check("带 theme_priority 列表不崩（非数值项被忽略）", isinstance(ag2['游资'], float), ag2['游资'])
except Exception as e:
    check("带 theme_priority 列表不崩（非数值项被忽略）", False, f'{type(e).__name__}: {e}')

src_sd = (ROOT / 'scripts' / 'stock_dashboard.py').read_text(encoding='utf-8')
check("sim_world 支持 llm_impact/llm_note", "def sim_world(scenario=None, llm_impact=None, llm_note='')" in src_sd)
check("管道调用处透传冲击", "impact_override=llm_impact, impact_note=llm_note" in src_sd)
src_main = (ROOT / 'web' / 'main.py').read_text(encoding='utf-8')
check("/api/sim 带 engine 参数", 'def api_sim(scenario: str = "", code: str = "", engine: str = "rule")' in src_main)
check("返回体带 llm 载荷", 'llm=llm_payload,' in src_main)
check("无密钥时标 rule(fallback)", 'rule(fallback)' in src_main)

print()
print("FAILED:", fails if fails else "无 —— 全部通过")
sys.exit(1 if fails else 0)