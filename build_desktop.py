# -*- coding: utf-8 -*-
"""
一键打包 Windows 独立桌面软件 (AlphaPulse股票看盘.exe)
用法：
    py -3.12 build_desktop.py
打包产物：
    dist/AlphaPulse股票看盘/AlphaPulse股票看盘.exe
"""
import os
import sys
import shutil
import subprocess

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = os.path.dirname(os.path.abspath(__file__))


def main() -> None:
    web_dist = os.path.join(ROOT, "web", "dist", "index.html")
    if not os.path.isfile(web_dist):
        print("[!] Missing web/dist/index.html, run bun run build in frontend first")
        sys.exit(1)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name",
        "AlphaPulse",
        "--add-data",
        f"web{os.pathsep}web",
        "--add-data",
        f"scripts{os.pathsep}scripts",
        "--add-data",
        f"core{os.pathsep}core",
        "--hidden-import",
        "uvicorn.logging",
        "--hidden-import",
        "uvicorn.loops",
        "--hidden-import",
        "uvicorn.loops.auto",
        "--hidden-import",
        "uvicorn.protocols",
        "--hidden-import",
        "uvicorn.protocols.http",
        "--hidden-import",
        "uvicorn.protocols.http.auto",
        "--hidden-import",
        "uvicorn.protocols.websockets",
        "--hidden-import",
        "uvicorn.protocols.websockets.auto",
        "--hidden-import",
        "uvicorn.lifespan",
        "--hidden-import",
        "uvicorn.lifespan.on",
        "desktop_app.py",
    ]

    print("[1/2] Running PyInstaller build ...")
    subprocess.check_call(cmd, cwd=ROOT)

    # 将基础数据字典复制到输出目录外层，方便用户持久化保存自选股、龙虎榜账本与配置
    out_dir = os.path.join(ROOT, "dist", "AlphaPulse")
    out_data = os.path.join(out_dir, "data")
    os.makedirs(out_data, exist_ok=True)
    for fname in ("stock_list.json", "stock_names.json", "ths_concepts.json", "lhb_seat_ledger.json"):
        src = os.path.join(ROOT, "data", fname)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(out_data, fname))

    out_cfg = os.path.join(out_dir, "config")
    os.makedirs(out_cfg, exist_ok=True)
    example_cfg = os.path.join(ROOT, "config", "llm.local.json.example")
    if os.path.isfile(example_cfg):
        shutil.copy2(example_cfg, os.path.join(out_cfg, "llm.local.json.example"))

    print(f"\n[2/2] Build complete! Output dir: {out_dir}")
    print(f"Executable: {os.path.join(out_dir, 'AlphaPulse.exe')}")


if __name__ == "__main__":
    main()
