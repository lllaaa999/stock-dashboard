import urllib.request, time

t0 = time.time()
urllib.request.urlopen('http://qt.gtimg.cn/q=sh600664', timeout=5).read()
print('HTTP plain took:', time.time() - t0, 's')
