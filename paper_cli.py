# -*- coding: utf-8 -*-
"""
paper_cli.py — 纸上模拟交易 CLI 入口转发器
实际核心已迁移至 scripts/paper_cli.py，本文件保留向下兼容快捷调用。
"""
import os
import sys

_SCRIPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts', 'paper_cli.py')

if __name__ == '__main__':
    if not os.path.exists(_SCRIPT_PATH):
        sys.exit(f"Error: {_SCRIPT_PATH} not found")
    with open(_SCRIPT_PATH, 'r', encoding='utf-8') as f:
        code = compile(f.read(), _SCRIPT_PATH, 'exec')
        exec(code, {'__name__': '__main__', '__file__': _SCRIPT_PATH})
