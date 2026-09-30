# -*- coding: utf-8 -*-
"""把 step4 误改成 CRLF 的三个文件恢复为原来的 LF(内容零改动, 只改行尾), 并自检。"""
import pathlib

ROOT = pathlib.Path(r"D:\股票看盘")
targets = ["scripts/data_feed.py", "web/main.py", ".gitignore"]

for rel in targets:
    p = ROOT / rel
    b = p.read_bytes()
    before_crlf = b.count(b"\r\n")
    fixed = b.replace(b"\r\n", b"\n")
    p.write_bytes(fixed)
    print(f"{rel:24s} CRLF {before_crlf} -> {fixed.count(chr(13).encode() + chr(10).encode())}"
          f" | LF 总数 {fixed.count(chr(10).encode())}")

print()
print("== 复核 5 个文件现在的行尾(应为: 与备份一致) ==")
pairs = [
    ("scripts/data_feed.py", "scratch/step4_backup_20260930/data_feed.py"),
    ("scripts/stock_dashboard.py", "scratch/step4_backup_20260930/stock_dashboard.py"),
    ("web/main.py", "scratch/step4_backup_20260930/main.py"),
    ("web/templates/index.html", "scratch/step4_backup_20260930/index.html"),
    (".gitignore", "scratch/step4_backup_20260930/.gitignore"),
]
for cur, bak in pairs:
    a = (ROOT / cur).read_bytes()
    b = (ROOT / bak).read_bytes()
    same_style = (a.count(b"\r\n") == 0) == (b.count(b"\r\n") == 0)
    print(f"{cur:34s} {'风格一致 OK' if same_style else '仍不一致 !!'}")