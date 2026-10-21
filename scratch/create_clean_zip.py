# -*- coding: utf-8 -*-
"""
创建纯净的 project_review.zip 代码审查归档包
输出路径: 用户桌面 (C:\\Users\\28769\\Desktop\\project_review.zip)
"""
import os
import zipfile
from pathlib import Path

ROOT_DIR = Path('D:/股票看盘').resolve()
DESKTOP_DIR = Path.home() / 'Desktop'
TARGET_ZIP = DESKTOP_DIR / 'project_review.zip'

EXCLUDE_DIRS = {
    'node_modules',
    '.git',
    '.venv',
    'venv',
    'env',
    '__pycache__',
    'scratch',
    '.pytest_cache',
    '.idea',
    '.vscode',
    'tools'
}

EXCLUDE_EXTS = {
    '.pyc',
    '.pyo',
    '.pyd',
    '.bak',
    '.tmp',
    '.log',
    '.DS_Store'
}

# 单独排除的大体积临时数据文件或子路径
EXCLUDE_REL_PATHS = {
    'data/snapshot_cache.json',
}


def should_exclude(rel_path: str) -> bool:
    # 统一用正斜杠
    norm_path = rel_path.replace('\\', '/')
    parts = norm_path.split('/')
    
    # 检查文件夹黑名单
    for part in parts[:-1]:
        if part in EXCLUDE_DIRS:
            return True
            
    # 检查后缀黑名单
    ext = os.path.splitext(norm_path)[1].lower()
    if ext in EXCLUDE_EXTS:
        return True
        
    # 检查特定路径
    if norm_path in EXCLUDE_REL_PATHS:
        return True
        
    # 排除 data/news 整个大体积新闻缓存目录
    if norm_path.startswith('data/news/'):
        return True

    return False


def main():
    print(f"正在扫描并打包: {ROOT_DIR}")
    print(f"目标压缩包: {TARGET_ZIP}")
    
    # 如果目标文件已存在，先删除
    if TARGET_ZIP.exists():
        TARGET_ZIP.unlink()
        
    packed_files = []
    total_raw_size = 0
    
    with zipfile.ZipFile(TARGET_ZIP, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
        for root, dirs, files in os.walk(ROOT_DIR):
            for file in sorted(files):
                full_path = Path(root) / file
                rel_path = full_path.relative_to(ROOT_DIR)
                rel_str = str(rel_path).replace('\\', '/')
                
                if should_exclude(rel_str):
                    continue
                    
                file_size = full_path.stat().st_size
                total_raw_size += file_size
                # 写入 zip，统一放在 project_review/ 根目录下
                arcname = f"project_review/{rel_str}"
                zipf.write(full_path, arcname=arcname)
                packed_files.append((rel_str, file_size))
                
    zip_size = TARGET_ZIP.stat().st_size
    print("\n" + "=" * 60)
    print("📦 打包完成！清单汇总：")
    print("=" * 60)
    for p, sz in packed_files:
        print(f"  + {p:45s} ({sz/1024:6.1f} KB)")
    print("=" * 60)
    print(f"✅ 文件总数: {len(packed_files)} 个")
    print(f"✅ 原始体积: {total_raw_size/1024/1024:.2f} MB")
    print(f"✅ 压缩后体积: {zip_size/1024/1024:.2f} MB ({zip_size/1024:.1f} KB)")
    print(f"✅ 保存位置: {TARGET_ZIP}")
    print("=" * 60)


if __name__ == '__main__':
    main()
