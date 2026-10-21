import xml.etree.ElementTree as ET

tree = ET.parse(r'D:\同花顺远航版\bin\data\public\block_tree.xml')
concepts = []
industries = []
for node in tree.getroot().iter():
    name = node.attrib.get('DisplayName', '')
    bid = node.attrib.get('BlockId', '')
    if any(k in name for k in ['人工智能', '机器人', '半导体', '华为', '低空经济', '新能源', '芯片']):
        concepts.append((name, bid, node.attrib))

print(f"Total matching hot concepts/industries: {len(concepts)}")
for c in concepts[:20]:
    print(c)
