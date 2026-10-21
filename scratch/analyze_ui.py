# -*- coding: utf-8 -*-
import re

with open('web/templates/index.html', 'r', encoding='utf-8') as f:
    text = f.read()

print("File size:", len(text), "bytes")
tabs = re.findall(r'class="tab-btn[^"]*"[^>]*data-tab="([^"]+)"', text)
print("Tabs:", tabs)

cards = re.findall(r'<div[^>]*class="card[^"]*"[^>]*>.*?<h3>(.*?)</h3>', text, re.DOTALL)
print("Cards count:", len(cards))
for c in cards:
    clean = re.sub(r'<.*?>', '', c).strip()
    print("  Card:", clean)

scripts = re.findall(r'<script>(.*?)</script>', text, re.DOTALL)
print("Inline script blocks:", len(scripts))
