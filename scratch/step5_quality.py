# -*- coding: utf-8 -*-
"""P2-⑤ 涨停质量分: 新增 stock_dashboard.limit_up_quality(), 接进 E/F/H 策略排序 + Web 结构化输出。
保留每个文件原有的行尾风格(LF/CRLF), 每处替换都断言命中次数, 失败则整体不落盘。
"""
import pathlib
import subprocess

ROOT = pathlib.Path(r"D:\股票看盘")
SD = ROOT / "scripts" / "stock_dashboard.py"
SL = ROOT / "scripts" / "strategies_lib.py"

fails = []


def load(p):
    b = p.read_bytes()
    nl = "\r\n" if b.count(b"\r\n") else "\n"
    return b.decode("utf-8").replace("\r\n", "\n"), nl


def save(p, t, nl):
    p.write_bytes(t.replace("\n", nl).encode("utf-8"))


def rep(t, old, new, expect=1, tag=""):
    n = t.count(old)
    if n != expect:
        fails.append(f"[{tag}] 命中 {n} 次(期望 {expect})")
        print(f"  FAIL  {tag}: 命中 {n} 次(期望 {expect})")
        return t
    print(f"  OK    {tag}")
    return t.replace(old, new)


# ============ A. stock_dashboard.py: 新增涨停质量分 ============
sd_t, sd_nl = load(SD)

QUAL = '''# ==================== 涨停质量分 (2026-09-30 P2) ====================
def _lu_num(v):
    return float(v) if isinstance(v, (int, float)) else 0.0


def _lu_time_score(fbt):
    """封板时间分 0~10(越早越强)。依据: 9:25 竞价封板 3 日超额 +5.7%, 10:00 后递减, 14:00 后 -2.4%"""
    if not fbt:
        return None
    if fbt <= 93000:
        return 10.0
    if fbt <= 100000:
        return 8.0
    if fbt <= 113000:
        return 5.0
    if fbt <= 140000:
        return 2.0
    return 0.0


def _lu_seal_score(ratio_pct):
    """封单强度分 0~10 = 封单额/流通市值。>5% -> 3日超额 +8.4%, 1~5% -> +3.1%, <1% -> -0.7%"""
    if ratio_pct is None:
        return None
    if ratio_pct >= 5:
        return 10.0
    if ratio_pct >= 1:
        return 7.0
    if ratio_pct >= 0.5:
        return 4.0
    if ratio_pct >= 0.1:
        return 2.0
    return 0.0


def _lu_board_score(lbc):
    """连板结构分 0~10。依据: 第 2 板 alpha 最强, 4 板后衰减, 6 板以上转负"""
    if not lbc:
        return None
    return {1: 4.0, 2: 10.0, 3: 6.0, 4: 2.0}.get(int(lbc), 0.0)


def limit_up_quality(d):
    """涨停质量分 0~10 = 0.35x封板时间 + 0.35x封单强度 + 0.30x连板结构, 缺项按权重归一, 烂板扣分。

    只用池子里现成的字段(fbt/fund/ltsz/lbc/zbc), 不额外发请求。
    依据: 涨停板因子实证(竞价封板 +5.7% / 封单占流通>5% +8.4% / 第 2 板 alpha 最强)。
    E/F/H 策略用它当首要排序键, 并通过 x['qlty'] 把分数带给 CLI 与 Web。
    返回 (score, detail)。
    """
    try:
        fbt = int(d.get('fbt') or 0)
    except Exception:
        fbt = 0
    try:
        lbc = int(d.get('lbc') or 0)
    except Exception:
        lbc = 0
    try:
        zbc = int(d.get('zbc') or 0)
    except Exception:
        zbc = 0
    ltsz = _lu_num(d.get('ltsz'))
    ratio = (_lu_num(d.get('fund')) / ltsz * 100) if ltsz > 0 else None

    parts = []
    tv, sv, bv = _lu_time_score(fbt), _lu_seal_score(ratio), _lu_board_score(lbc)
    if tv is not None:
        parts.append((tv, 0.35, 'time'))
    if sv is not None:
        parts.append((sv, 0.35, 'seal'))
    if bv is not None:
        parts.append((bv, 0.30, 'board'))
    if not parts:
        return 0.0, {'score': 0.0, 'missing': True, 'used_factors': 0}
    wsum = sum(p[1] for p in parts)
    score = sum(p[0] * p[1] for p in parts) / wsum
    if zbc >= 3:
        score -= 1.5
    elif zbc == 2:
        score -= 0.7
    score = max(0.0, min(10.0, round(score, 2)))
    return score, {
        'score': score, 'fbt': fbt, 'lbc': lbc, 'zbc': zbc,
        'seal_ratio_pct': round(ratio, 2) if ratio is not None else None,
        'parts': {p[2]: p[0] for p in parts},
        'used_factors': len(parts), 'missing': len(parts) < 3,
    }


'''

sd_t = rep(sd_t, "def _pool(kind, ymd):", QUAL + "def _pool(kind, ymd):", 1, "sd: 插入质量分函数")

# ============ B. strategies_lib.py: E/F/H 接质量分 ============
sl_t, sl_nl = load(SL)

sl_t = rep(sl_t,
           '    """首板+早封+零炸+封单比>=1.5%+小盘<=80亿, 按封单比排序"""',
           '    """首板+早封+零炸+封单比>=1.5%+小盘<=80亿; 按涨停质量分排序(同分看封单占比)"""',
           1, "sl-E: 文档串")

sl_t = rep(sl_t, '''        out.append((ratio, x, fbt, amt))
    out.sort(key=lambda t: -t[0])
    for ratio, x, fbt, amt in out[:10]:
        w('%s %-6s [%s] 首封%s 封单%.1f亿(占流通%.1f%%) 流通%.0f亿 额%.1f亿' % (
            x.get('c'), x.get('n'), x.get('hybk', '-'),
            fbt[:2] + ':' + fbt[2:4], _num(x.get('fund')) / 1e8, ratio,
            _num(x.get('ltsz')) / 1e8, amt / 1e8))
    return out''', '''        q, _qd = sd.limit_up_quality(x)
        x['qlty'] = q                       # 带出去给 CLI/Web/Agent 复用(2026-09-30 P2-⑤)
        out.append((q, ratio, x, fbt, amt))
    out.sort(key=lambda t: (-t[0], -t[1]))
    for q, ratio, x, fbt, amt in out[:10]:
        w('%s %-6s [%s] 质量%.1f 首封%s 封单%.1f亿(占流通%.1f%%) 流通%.0f亿 额%.1f亿' % (
            x.get('c'), x.get('n'), x.get('hybk', '-'), q,
            fbt[:2] + ':' + fbt[2:4], _num(x.get('fund')) / 1e8, ratio,
            _num(x.get('ltsz')) / 1e8, amt / 1e8))
    return out''', 1, "sl-E: 排序+输出")

sl_t = rep(sl_t, '''        score = -pct_t1 + (10 if fbt <= '100000' else 0) + min(_num(r.get('f62')) / 1e8, 5)
        out.append((score, code, x, pct_t1, fbt))
    out.sort(key=lambda t: -t[0])
    for sc, code, x, pct_t1, fbt in out[:8]:
        w('%s %-6s [%s] T-1断板%+.1f%%后今反包 首封%s 炸%d 主力净入%+.1f亿' % (
            code, x.get('n'), x.get('hybk', '-'), pct_t1,
            fbt[:2] + ':' + fbt[2:4], x.get('zbc', 0),
            _num((by_code().get(code) or {}).get('f62')) / 1e8))
    return out''', '''        q, _qd = sd.limit_up_quality(x)
        x['qlty'] = q
        score = -pct_t1 + (10 if fbt <= '100000' else 0) + min(_num(r.get('f62')) / 1e8, 5)
        out.append((q, score, code, x, pct_t1, fbt))
    out.sort(key=lambda t: (-t[0], -t[1]))
    for q, sc, code, x, pct_t1, fbt in out[:8]:
        w('%s %-6s [%s] 质量%.1f T-1断板%+.1f%%后今反包 首封%s 炸%d 主力净入%+.1f亿' % (
            code, x.get('n'), x.get('hybk', '-'), q, pct_t1,
            fbt[:2] + ':' + fbt[2:4], x.get('zbc', 0),
            _num((by_code().get(code) or {}).get('f62')) / 1e8))
    return out''', 1, "sl-F: 排序+输出")

sl_t = rep(sl_t, '''        score = -pct_t1 + (t2[5] / max(t1[5], 1)) + min(_num(r.get('f10')), 10) * 0.5
        out.append((score, code, x, pct_t1, fbt))
    out.sort(key=lambda t: -t[0])
    for sc, code, x, pct_t1, fbt in out[:8]:
        w('%s %-6s [%s] %d板N字 T-1回调%+.1f%%今反包 首封%s' % (
            code, x.get('n'), x.get('hybk', '-'), int(x.get('lbc', 1)),
            pct_t1, fbt[:2] + ':' + fbt[2:4]))
    return out''', '''        q, _qd = sd.limit_up_quality(x)
        x['qlty'] = q
        score = -pct_t1 + (t2[5] / max(t1[5], 1)) + min(_num(r.get('f10')), 10) * 0.5
        out.append((q, score, code, x, pct_t1, fbt))
    out.sort(key=lambda t: (-t[0], -t[1]))
    for q, sc, code, x, pct_t1, fbt in out[:8]:
        w('%s %-6s [%s] 质量%.1f %d板N字 T-1回调%+.1f%%今反包 首封%s' % (
            code, x.get('n'), x.get('hybk', '-'), q, int(x.get('lbc', 1)),
            pct_t1, fbt[:2] + ':' + fbt[2:4]))
    return out''', 1, "sl-H: 排序+输出")

# --- Web 结构化适配器: 元组多了一位, 必须同步 ---
sl_t = rep(sl_t, "                    for ratio, x, fbt, amt in (raw or [])[:10]:",
           "                    for _q, ratio, x, fbt, amt in (raw or [])[:10]:", 1, "web适配-E: 解包")
sl_t = rep(sl_t, "                    for sc, c, x, pct_t1, fbt in (raw or [])[:8]:",
           "                    for _q, sc, c, x, pct_t1, fbt in (raw or [])[:8]:", 2, "web适配-F/H: 解包")

sl_t = rep(sl_t,
           """                            'desc': f"首封{fbt[:2]}:{fbt[2:4]} 封单{_num(x.get('fund'))/1e8:.1f}亿(占流通{ratio:.1f}%) 流通{_num(x.get('ltsz'))/1e8:.0f}亿 额{amt/1e8:.1f}亿",""",
           """                            'quality': _q,
                            'desc': f"质量{_q:.1f} 首封{fbt[:2]}:{fbt[2:4]} 封单{_num(x.get('fund'))/1e8:.1f}亿(占流通{ratio:.1f}%) 流通{_num(x.get('ltsz'))/1e8:.0f}亿 额{amt/1e8:.1f}亿",""",
           1, "web适配-E: quality 字段")
sl_t = rep(sl_t,
           """                            'desc': f"T-1断板{pct_t1:+.1f}%后今反包 首封{fbt[:2]}:{fbt[2:4]} 炸{x.get('zbc', 0)}次 主力净入{_num(r.get('f62'))/1e8:+.1f}亿",""",
           """                            'quality': _q,
                            'desc': f"质量{_q:.1f} T-1断板{pct_t1:+.1f}%后今反包 首封{fbt[:2]}:{fbt[2:4]} 炸{x.get('zbc', 0)}次 主力净入{_num(r.get('f62'))/1e8:+.1f}亿",""",
           1, "web适配-F: quality 字段")
sl_t = rep(sl_t,
           """                            'desc': f"{int(x.get('lbc', 1))}板N字 T-1回调{pct_t1:+.1f}%今反包 首封{fbt[:2]}:{fbt[2:4]}",""",
           """                            'quality': _q,
                            'desc': f"质量{_q:.1f} {int(x.get('lbc', 1))}板N字 T-1回调{pct_t1:+.1f}%今反包 首封{fbt[:2]}:{fbt[2:4]}",""",
           1, "web适配-H: quality 字段")

if fails:
    print()
    print("有断言未命中, 不落盘:", fails)
    raise SystemExit(1)

save(SD, sd_t, sd_nl)
save(SL, sl_t, sl_nl)
print()
print(f"已写回: {SD} ({SD.stat().st_size}B)")
print(f"已写回: {SL} ({SL.stat().st_size}B)")

PY = r"C:\Users\28769\AppData\Local\Programs\Python\Python312\python.exe"
for f in (SD, SL):
    r = subprocess.run([PY, "-m", "py_compile", str(f)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    print(f"{f.name} py_compile rc={r.returncode} {(r.stdout or '') + (r.stderr or '')}")