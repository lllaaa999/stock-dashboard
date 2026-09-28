import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'web'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

import main

print("Calling main.api_stock('600664')...")
res = main.api_stock('600664')
print("Status code:", res.status_code)
data = json.loads(res.body.decode('utf-8'))
chan = data.get('chan')
print("Chan present:", chan is not None)
if chan:
    print("  Status:", chan.get('status'))
    print("  Cur dir:", chan.get('cur_dir'))
    print("  Bi count:", len(chan.get('bi_points', [])))
    print("  Zhongshu:", chan.get('last_zhongshu'))
    print("  Signals:", chan.get('signals'))
    print("  Summary:", chan.get('summary'))
