import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import stock_dashboard as sd

def test_chan():
    kl = sd.kline_tx('sh600664', 160)
    if not kl:
        print("K-line fetch failed")
        return
    from stock_dashboard import _ema
    
    closes = [r[2] for r in kl]
    e12, e26 = _ema(closes, 12), _ema(closes, 26)
    dif = [a - b for a, b in zip(e12, e26)]
    dea = _ema(dif, 9)
    hist = [(a - b) * 2 for a, b in zip(dif, dea)]

    bars = []
    for i, r in enumerate(kl):
        h, l = float(r[3]), float(r[4])
        if bars and ((h >= bars[-1][1] and l <= bars[-1][2]) or (h <= bars[-1][1] and l >= bars[-1][2])):
            up = len(bars) < 2 or bars[-2][1] <= bars[-1][1]
            if up:
                bars[-1][1] = max(bars[-1][1], h); bars[-1][2] = max(bars[-1][2], l)
            else:
                bars[-1][1] = min(bars[-1][1], h); bars[-1][2] = min(bars[-1][2], l)
            bars[-1][0] = r[0]; bars[-1][3] = i
        else:
            bars.append([r[0], h, l, i])

    fx = []
    for i in range(1, len(bars) - 1):
        p0, p1, p2 = bars[i - 1], bars[i], bars[i + 1]
        if p1[1] > p0[1] and p1[1] > p2[1]:
            fx.append([i, '顶', p1[1], p1[0], p1[3]])
        elif p1[2] < p0[2] and p1[2] < p2[2]:
            fx.append([i, '底', p1[2], p1[0], p1[3]])

    bi = []
    for f in fx:
        if not bi:
            bi.append(f); continue
        lf = bi[-1]
        if f[1] == lf[1]:
            if (f[1] == '顶' and f[2] > lf[2]) or (f[1] == '底' and f[2] < lf[2]):
                bi[-1] = f
        elif f[0] - lf[0] >= 4:
            bi.append(f)

    print(f"Total bi points: {len(bi)}")
    for b in bi[-6:]:
        print(f"  {b[3]}: {b[1]}分型 @ {b[2]:.2f}")

    legs = [(bi[j - 1], bi[j]) for j in range(1, len(bi))]
    l3 = legs[-3:]
    los = [min(a[2], b[2]) for a, b in l3]
    his = [max(a[2], b[2]) for a, b in l3]
    zs_lo, zs_hi = max(los), min(his)
    print(f"Zhongshu range: [{zs_lo:.2f} ~ {zs_hi:.2f}], valid: {zs_lo < zs_hi}")
    print(f"Zhongshu dates: {l3[0][0][3]} ~ {l3[-1][1][3]}")

if __name__ == '__main__':
    test_chan()
