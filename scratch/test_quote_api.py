import urllib.request
import json
import re

def get_ths_realhead(code: str):
    prefix = 'hs_' + code
    url = f'http://d.10jqka.com.cn/v2/realhead/{prefix}/last.js'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'http://stockpage.10jqka.com.cn/'})
    with urllib.request.urlopen(req, timeout=5) as resp:
        raw = resp.read().decode('utf-8', errors='ignore')
        m = re.search(r'\((.*)\)', raw)
        if not m:
            return None
        items = json.loads(m.group(1)).get('items', {})
        return {
            'code': code,
            'name': items.get('name'),
            'price': float(items.get('10', 0)),
            'change_pct': float(items.get('199112', 0)),
            'change_amt': float(items.get('264648', 0)),
            'open': float(items.get('7', 0)),
            'high': float(items.get('8', 0)),
            'low': float(items.get('9', 0)),
            'prev_close': float(items.get('6', 0)),
            'turnover_rate': float(items.get('1968584', 0)),
            'vwap': float(items.get('1378761', 0)),
            'volume_hand': float(items.get('13', 0)),
            'amount_wan': round(float(items.get('19', 0)) / 10000, 2),
            'bid1': (float(items.get('24', 0)), float(items.get('25', 0))),
            'ask1': (float(items.get('30', 0)), float(items.get('31', 0))),
            'upper_limit': float(items.get('69', 0)),
            'lower_limit': float(items.get('70', 0)),
            'status': items.get('stockStatus'),
            'time': items.get('time')
        }

if __name__ == '__main__':
    stocks = ['600519', '300033', '000001', '688981']
    for c in stocks:
        q = get_ths_realhead(c)
        if q:
            name = q['name']
            price = q['price']
            chg = q['change_pct']
            turn = q['turnover_rate']
            amt = q['amount_wan']
            status = q['status']
            b1 = q['bid1']
            a1 = q['ask1']
            up = q['upper_limit']
            dn = q['lower_limit']
            print(f"[{c} {name}] 现价:{price} 涨跌:{chg:+.2f}% 换手:{turn}% 成交:{amt}万 状态:{status}")
            print(f"   买一: {b1[0]} ({int(b1[1])}股) | 卖一: {a1[0]} ({int(a1[1])}股) | 涨停:{up} 跌停:{dn}")
