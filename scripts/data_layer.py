# -*- coding: utf-8 -*-
"""统一数据层 · mootdx(实时行情+K线) + baostock(历史K线+财务)

设计原则：
  1. 多源回退 — 本层函数失败时返回 None，由上层回退原腾讯/东财接口
  2. 格式兼容 — 返回格式与 stock_dashboard.py 原函数完全一致，上层零改动
  3. 连接复用 — mootdx 客户端单例、baostock 登录态复用，避免重复握手

返回格式约定：
  realtime_quotes() → [{'code','name','price','pct','amount','vol'}, ...]
  kline_*()         → [[date, open, close, high, low, vol], ...]
"""
import sys, os, json, datetime, time

HERE = os.path.dirname(os.path.abspath(__file__))

# ============================================================================
# mootdx 客户端单例
# ============================================================================
_mootdx_client = None
_mootdx_init_failed = False


def _get_mootdx():
    """获取 mootdx 客户端单例，失败一次后不再重试（避免每次都超时）"""
    global _mootdx_client, _mootdx_init_failed
    if _mootdx_init_failed:
        return None
    if _mootdx_client is None:
        try:
            from mootdx.quotes import Quotes
            _mootdx_client = Quotes.factory(market='std')
        except Exception as e:
            print(f'[data_layer] mootdx 初始化失败: {e}')
            _mootdx_init_failed = True
            return None
    return _mootdx_client


# ============================================================================
# baostock 登录管理
# ============================================================================
_bs_logged = False
_bs_fail_count = 0          # 连续失败计数
_bs_disabled_until = 0      # 暂时禁用截止时间戳
_BS_MAX_FAIL = 10           # 连续失败超过此数后暂时禁用
_BS_DISABLE_SECONDS = 300   # 暂时禁用时长（5分钟）
_BS_RETRY = 2                # 单次查询重试次数
_BS_RETRY_INTERVAL = 1.0    # 重试间隔（秒）


def _bs_login():
    global _bs_logged
    if _bs_logged:
        return True
    try:
        import baostock as bs
        lg = bs.login()
        _bs_logged = (lg.error_code == '0')
        return _bs_logged
    except Exception as e:
        print(f'[data_layer] baostock 登录失败: {e}')
        return False


def bs_logout():
    """显式登出 baostock（程序结束时调用）"""
    global _bs_logged
    if _bs_logged:
        try:
            import baostock as bs
            bs.logout()
        except Exception:
            pass
        _bs_logged = False


# ============================================================================
# 股票名称缓存（从 data/stock_list.json 读取，补 mootdx 实时行情缺的 name）
# ============================================================================
_name_cache = None


def _get_name(code):
    """股票名称缓存：本地文件优先(7天过期) → mootdx stocks() → stock_list.json兜底"""
    global _name_cache
    if _name_cache is None:
        _name_cache = {}
        cache_path = os.path.join(HERE, '..', 'data', 'stock_names.json')
        # 1. 优先读本地缓存（7天内有效）
        if os.path.exists(cache_path):
            age = time.time() - os.path.getmtime(cache_path)
            if age < 7 * 86400:
                try:
                    with open(cache_path, encoding='utf-8') as f:
                        _name_cache = json.load(f)
                    if _name_cache:
                        return _name_cache.get(code, code)
                except Exception as e:
                    print(f'[data_layer] 名称缓存文件读取失败: {e}')
        # 2. 从 mootdx stocks() 拉取并写入本地缓存
        client = _get_mootdx()
        if client:
            try:
                df = client.stocks()
                if df is not None and len(df) > 0:
                    for _, row in df.iterrows():
                        c = str(row.get('code', ''))
                        n = str(row.get('name', ''))
                        if c and n and c not in _name_cache:
                            _name_cache[c] = n
                    if _name_cache:
                        try:
                            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                            with open(cache_path, 'w', encoding='utf-8') as f:
                                json.dump(_name_cache, f, ensure_ascii=False)
                        except Exception as e:
                            print(f'[data_layer] 名称缓存写入失败: {e}')
            except Exception as e:
                print(f'[data_layer] mootdx 名称列表加载失败: {e}')
        # 3. 兜底从本地 stock_list.json
        if not _name_cache:
            try:
                path = os.path.join(HERE, '..', 'data', 'stock_list.json')
                if os.path.exists(path):
                    with open(path, encoding='utf-8') as f:
                        for item in json.load(f):
                            _name_cache[item.get('code', '')] = item.get('name', '')
            except Exception as e:
                print(f'[data_layer] 本地名称缓存加载失败: {e}')
    return _name_cache.get(code, code)


# ============================================================================
# 1. 实时行情（mootdx，秒级，买卖五档）
# ============================================================================
def realtime_quotes(codes):
    """批量实时行情。
    codes: 代码列表，支持 '600664' / 'sh600664' / 'sh.600664' 混合格式
    返回: [{'code','name','price','pct','amount','vol'}, ...]  失败返回 None
    """
    client = _get_mootdx()
    if client is None:
        return None
    try:
        # 统一成纯数字代码
        pure = []
        for c in codes:
            c = str(c).strip().lower()
            c = c.replace('sh.', '').replace('sz.', '').replace('sh', '').replace('sz', '')
            if c:
                pure.append(c)
        if not pure:
            return None

        # mootdx 支持批量（列表或逗号分隔）
        df = client.quotes(symbol=pure if len(pure) > 1 else pure[0])
        if df is None or len(df) == 0:
            return None

        result = []
        for _, row in df.iterrows():
            price = float(row.get('price', 0) or 0)
            last_close = float(row.get('last_close', 0) or 0)
            pct = (price - last_close) / last_close * 100 if last_close else 0.0
            code = str(row.get('code', ''))
            result.append({
                'code': code,
                'name': _get_name(code),
                'price': price,
                'pct': round(pct, 2),
                'amount': float(row.get('amount', 0) or 0),
                'vol': float(row.get('vol', 0) or 0),
            })
        return result
    except Exception as e:
        print(f'[data_layer] mootdx 实时行情失败: {e}')
        return None


# ============================================================================
# 2. 日K线（mootdx，快速，近期数据，自动前复权）
# ============================================================================
def kline_mootdx(code, days=160):
    """日K线（mootdx，速度快，适合近期数据）。
    code: 纯数字代码，如 '600664'
    返回: [[date, open, close, high, low, vol], ...]  失败返回 None
    """
    client = _get_mootdx()
    if client is None:
        return None
    try:
        df = client.bars(symbol=code, frequency=9, offset=days)
        if df is None or len(df) == 0:
            return None
        result = []
        for idx, row in df.iterrows():
            # idx 是 Timestamp，取日期部分
            date_str = idx.strftime('%Y-%m-%d') if hasattr(idx, 'strftime') else str(idx)[:10]
            result.append([
                date_str,
                float(row.get('open', 0) or 0),
                float(row.get('close', 0) or 0),
                float(row.get('high', 0) or 0),
                float(row.get('low', 0) or 0),
                float(row.get('vol', 0) or 0),
            ])
        return result
    except Exception as e:
        print(f'[data_layer] mootdx K线失败({code}): {e}')
        return None


# ============================================================================
# 3. 历史日K线（baostock，稳定，可查长期，前复权）
# ============================================================================
def kline_baostock(code, days=160, start_date=None):
    """历史日K线（baostock，稳定规范，前复权）。
    code: 纯数字代码，如 '600664'
    返回: [[date, open, close, high, low, vol], ...]  失败返回 None
    优化：重试机制 + 连续失败暂时禁用 + 错误日志抑制
    """
    global _bs_fail_count, _bs_disabled_until

    # 检查是否被暂时禁用
    now = time.time()
    if now < _bs_disabled_until:
        return None

    if not _bs_login():
        return None

    import baostock as bs
    bs_code = ('sh.' if code.startswith(('6', '5', '9')) else 'sz.') + code

    if start_date is None:
        start_date = (datetime.date.today() - datetime.timedelta(days=days * 2)).strftime('%Y-%m-%d')

    last_error = None
    for attempt in range(_BS_RETRY + 1):
        try:
            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,open,high,low,close,volume,amount",
                start_date=start_date,
                frequency="d",
                adjustflag="2",
            )
            if rs.error_code != '0':
                last_error = rs.error_msg
                if attempt < _BS_RETRY:
                    time.sleep(_BS_RETRY_INTERVAL)
                    continue
                # 最终失败
                _bs_fail_count += 1
                if _bs_fail_count >= _BS_MAX_FAIL:
                    _bs_disabled_until = time.time() + _BS_DISABLE_SECONDS
                    print(f'[data_layer] baostock 连续失败{_bs_fail_count}次，暂时禁用{_BS_DISABLE_SECONDS//60}分钟')
                elif _bs_fail_count <= 3:  # 只打印前3次错误，避免刷屏
                    print(f'[data_layer] baostock 查询失败({code}): {rs.error_msg}')
                return None

            result = []
            while rs.next():
                row = rs.get_row_data()
                try:
                    result.append([
                        row[0],
                        float(row[1] or 0),
                        float(row[4] or 0),
                        float(row[2] or 0),
                        float(row[3] or 0),
                        float(row[5] or 0) / 100,
                    ])
                except (ValueError, IndexError):
                    continue

            if result:
                _bs_fail_count = 0  # 成功重置计数
                return result[-days:] if len(result) > days else result
            return None

        except Exception as e:
            last_error = str(e)
            if attempt < _BS_RETRY:
                time.sleep(_BS_RETRY_INTERVAL)
                continue
            _bs_fail_count += 1
            if _bs_fail_count >= _BS_MAX_FAIL:
                _bs_disabled_until = time.time() + _BS_DISABLE_SECONDS
                print(f'[data_layer] baostock 连续异常{_bs_fail_count}次，暂时禁用{_BS_DISABLE_SECONDS//60}分钟')
            elif _bs_fail_count <= 3:
                print(f'[data_layer] baostock K线异常({code}): {e}')
            return None

    return None


# ============================================================================
# 4. 统一K线入口（mootdx 优先 → baostock 兜底 → 返回 None 让上层回退腾讯）
# ============================================================================
def kline(code, days=160):
    """统一K线接口：优先 mootdx（快），失败用 baostock（稳），都失败返回 None。
    code: 支持 '600664' / 'sh600664' / 'sz000001' 格式
    """
    # 统一成纯数字
    code = str(code).strip().lower()
    code = code.replace('sh.', '').replace('sz.', '').replace('sh', '').replace('sz', '')

    # 优先 mootdx
    kl = kline_mootdx(code, days)
    if kl and len(kl) >= 1:
        return kl

    # 兜底 baostock
    kl = kline_baostock(code, days)
    if kl and len(kl) >= 1:
        return kl

    return None


# ============================================================================
# 自测
# ============================================================================
if __name__ == '__main__':
    sys.stdout = __import__('io').TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    print("=" * 60)
    print("data_layer 自测")
    print("=" * 60)

    # 实时行情
    print("\n--- 实时行情: 600664 + 000001 ---")
    q = realtime_quotes(['600664', '000001'])
    if q:
        for x in q:
            print(f"  {x['code']} {x['name']} 价{x['price']} 涨跌{x['pct']:+.2f}% 额{x['amount']:.0f}")
    else:
        print("  ✗ 失败")

    # K线 mootdx
    print("\n--- K线(mootdx): 600664 最近5根 ---")
    kl = kline_mootdx('600664', 5)
    if kl:
        for r in kl:
            print(f"  {r[0]} O:{r[1]:.2f} C:{r[2]:.2f} H:{r[3]:.2f} L:{r[4]:.2f} V:{r[5]:.0f}")
    else:
        print("  ✗ 失败")

    # K线 baostock
    print("\n--- K线(baostock): 600664 最近5根 ---")
    kl2 = kline_baostock('600664', 5)
    if kl2:
        for r in kl2:
            print(f"  {r[0]} O:{r[1]:.2f} C:{r[2]:.2f} H:{r[3]:.2f} L:{r[4]:.2f} V:{r[5]:.0f}")
    else:
        print("  ✗ 失败")

    # 统一K线
    print("\n--- 统一K线(kline): 000001 最近3根 ---")
    kl3 = kline('sz000001', 3)
    if kl3:
        for r in kl3:
            print(f"  {r[0]} C:{r[2]:.2f}")
    else:
        print("  ✗ 失败")

    bs_logout()
    print("\n自测完成")
