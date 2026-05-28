import time
import urllib.request

url='http://127.0.0.1:8000'
for i in range(6):
    t0=time.time()
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            r.read()
        dt=time.time()-t0
        print(f'req {i+1}: {dt:.3f}s')
    except Exception as e:
        print('req', i+1, 'error', e)
    time.sleep(0.2)
