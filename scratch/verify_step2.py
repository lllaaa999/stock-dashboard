# -*- coding: utf-8 -*-
"""Step2 验证: 启动器固化 / 存档单点 / 新哨兵

用法: python scratch/verify_step2.py
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(r"D:\股票看盘")
PROJ = ROOT / "data" / "stock_data" / "sentiment_history.jsonl"
HERM_DIR = pathlib.Path(r"C:\Users\28769\AppData\Local\hermes\stock_data")
BATS = [ROOT / "一键启动股票看盘.bat", pathlib.Path(r"C:\Users\28769\Desktop\启动股票看盘.bat")]
PY = r"C:\Users\28769\AppData\Local\Programs\Python\Python312\python.exe"
TMP = pathlib.Path(r"C:\Users\28769\AppData\Local\Temp")

fails = []


def check(name, cond, extra=''):
    print(('PASS  ' if cond else 'FAIL  ') + name + (('   ' + str(extra)) if extra else ''))
    if not cond:
        fails.append(name)


print("== 1. 启动器文件性质（GBK / CRLF / 无 BOM / 含变量行）==")
for b in BATS:
    raw = b.read_bytes()
    no_bom = not raw.startswith(b"\xef\xbb\xbf")
    txt = raw.decode('gbk')
    crlf_only = "\r\n" in txt and "\n" not in txt.replace("\r\n", "")
    head_ok = txt.lstrip().startswith("@echo off")
    var_ok = "set STOCK_DATA_HOME=D:\\股票看盘\\data" in txt
    check(f"{b.name}", no_bom and crlf_only and head_ok and var_ok,
          f"无BOM={no_bom} 纯CRLF={crlf_only} 开头={head_ok} 变量={var_ok}")

print()
print("== 2. 启动器行为：同一条 set 行是否真的改变落点（含反面控制）==")
CODE = ("import sys;sys.path.insert(0,r'D:\\股票看盘\\scripts');"
        "import stock_dashboard as sd;print('DATA_DIR='+sd.DATA_DIR)")
probe_with = TMP / "probe_with_env.bat"
probe_with.write_bytes(("@echo off\r\n"
                        "set STOCK_DATA_HOME=D:\\股票看盘\\data\r\n"
                        f'"{PY}" -c "{CODE}"\r\n').encode("gbk"))
probe_without = TMP / "probe_without_env.bat"
probe_without.write_bytes(("@echo off\r\n"
                           f'"{PY}" -c "{CODE}"\r\n').encode("gbk"))


def run_bat(p):
    r = subprocess.run(["cmd", "/c", str(p)], capture_output=True, timeout=180)
    blob = (r.stdout or b"") + (r.stderr or b"")
    for enc in ("utf-8", "gbk"):
        try:
            return blob.decode(enc)
        except UnicodeDecodeError:
            continue
    return blob.decode("gbk", errors="replace")


o1 = run_bat(probe_with)
o2 = run_bat(probe_without)
print("   设了变量  :", o1.strip().splitlines()[-1] if o1.strip() else "(空)")
print("   没设变量  :", o2.strip().splitlines()[-1] if o2.strip() else "(空)")
check("设了变量 -> DATA_DIR 落在项目 data\\stock_data", "DATA_DIR=D:\\股票看盘\\data\\stock_data" in o1)
check("没设变量 -> 同样落项目目录（真实规则：脚本上级 data/ 优先于环境变量，见 stock_dashboard.py:28-32）",
      "DATA_DIR=D:\\股票看盘\\data\\stock_data" in o2)

print()
print("== 2b. 回落分支：没有同级 data/ 的副本（旧 Hermes 技能副本/cron 那种）==")
import os
import shutil

far = TMP / "sdcopy" / "scripts"
far.mkdir(parents=True, exist_ok=True)
shutil.copy2(ROOT / "scripts" / "stock_dashboard.py", far / "stock_dashboard.py")
fake_home = TMP / "fake_hermes_home"
(fake_home / "stock_data").mkdir(parents=True, exist_ok=True)
base_env = {k: v for k, v in os.environ.items() if k not in ("STOCK_DATA_HOME", "HERMES_HOME")}
base_env["HERMES_HOME"] = str(fake_home)
FAR_CODE = f"import sys;sys.path.insert(0,r'{far}');import stock_dashboard as sd;print('DATA_DIR='+sd.DATA_DIR)"


def run_py(extra):
    env = dict(base_env)
    env.update(extra)
    r = subprocess.run([PY, "-c", FAR_CODE], capture_output=True, timeout=180, env=env)
    blob = (r.stdout or b"") + (r.stderr or b"")
    for enc in ("utf-8", "gbk"):
        try:
            return blob.decode(enc)
        except UnicodeDecodeError:
            continue
    return blob.decode("gbk", errors="replace")


o3 = run_py({})
o4 = run_py({"STOCK_DATA_HOME": r"D:\股票看盘\data"})
print("   无变量(HERMES_HOME=假home):", o3.strip().splitlines()[-1] if o3.strip() else "(空)")
print("   有变量(=项目 data)        :", o4.strip().splitlines()[-1] if o4.strip() else "(空)")
check("无变量 -> 落到 HERMES_HOME\\stock_data（这正是当年分叉的机制）",
      "fake_hermes_home" in o3.replace("/", "\\"))
check("有变量 -> 覆盖为项目 data\\stock_data（保险生效）",
      "DATA_DIR=D:\\股票看盘\\data\\stock_data" in o4)

print()
print("== 3. 存档单点 ==")
recs = [json.loads(l) for l in PROJ.read_text(encoding='utf-8').splitlines() if l.strip()]
dates = [str(r['date']) for r in recs]
check("权威存档条数 >= 30", len(recs) >= 30, len(recs))
check("含 20260929（Hermes 侧原先缺的那条）", "20260929" in dates)
check("日期严格升序且不重复", dates == sorted(dates) and len(dates) == len(set(dates)))
check("Hermes 侧已无活动的第二份存档", not (HERM_DIR / "sentiment_history.jsonl").exists())
check("Hermes 侧 legacy 冻结档存在", (HERM_DIR / "sentiment_history.jsonl.legacy-20260930").exists())

print()
print("== 4. 新哨兵 sync_check.ps1 ==")
r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", str(ROOT / "scripts" / "sync_check.ps1")],
                   capture_output=True, timeout=180)
blob = (r.stdout or b"") + (r.stderr or b"")
out = None
for enc in ("utf-8", "gbk"):
    try:
        out = blob.decode(enc)
        break
    except UnicodeDecodeError:
        continue
if out is None:
    out = blob.decode("gbk", errors="replace")
print("   exit =", r.returncode)
for ln in out.strip().splitlines():
    print("   " + ln)
check("哨兵退出码 0（无问题）", r.returncode == 0)
check("哨兵指向权威存档并报条数", "权威存档" in out and "条" in out)

print()
print("FAILED:", fails if fails else "无 —— 全部通过")
sys.exit(1 if fails else 0)