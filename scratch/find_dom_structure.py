# -*- coding: utf-8 -*-
with open('web/templates/index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f"Total lines: {len(lines)}")
for i, l in enumerate(lines):
    if '<div id=' in l or '<section' in l or 'class="tab' in l or 'function ' in l[:20]:
        if any(kw in l for kw in ['view', 'tab', 'panel', 'container', 'modal', 'chart', 'init', 'render', 'switch']):
            print(f"Line {i+1:4d}: {l.strip()[:100]}")
