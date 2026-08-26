# scripts/_resume_capture.py — 一次性:hang-proof 续抓 OHLCV(15s socket 超时 + 每码 catch-all)。
import glob
import socket
import time
from datetime import date

import pandas as pd

socket.setdefaulttimeout(15)   # 关键:akshare requests 无超时 → 全局兜底,stalled read 转异常

from youzi.data.cache import PITStore
from youzi.data.source import AkshareSource

SNAP = "data/snap_0526_0612"
START, END = date(2026, 5, 26), date(2026, 6, 12)

store = PITStore(SNAP)
src = AkshareSource()
codes = set()
for f in glob.glob(f"{SNAP}/*/2026*.parquet"):
    try:
        df = pd.read_parquet(f)
        if "code" in df.columns:
            codes.update(str(c) for c in df["code"])
    except Exception:
        pass
codes = sorted(codes)
empty = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
skipped = fetched = failed = 0
for code in codes:
    if store.has_ohlcv(code):
        skipped += 1
        continue
    try:
        df = src.daily_ohlcv(code, START, END)
        fetched += 1
    except Exception:
        df = empty
        failed += 1
    store.put_ohlcv(code, df)
    if (fetched + failed) % 25 == 0:
        print(f"progress {skipped + fetched + failed}/{len(codes)} fetched={fetched} failed={failed}", flush=True)
    time.sleep(0.2)
print(f"DONE total={len(codes)} skipped={skipped} fetched={fetched} failed_empty={failed}", flush=True)
