import pandas as pd
from pathlib import Path
from youzi_agent.data.cache import disk_cache

def test_disk_cache_writes_and_reads_parquet(tmp_path):
    calls = {"n": 0}

    @disk_cache(cache_dir=tmp_path, ttl="eod")
    def fetch(date: str) -> pd.DataFrame:
        calls["n"] += 1
        return pd.DataFrame({"a": [1, 2], "date": [date, date]})

    df1 = fetch("2026-04-25")
    df2 = fetch("2026-04-25")          # second call should hit cache
    assert calls["n"] == 1
    assert df1.equals(df2)
    assert (tmp_path / "2026-04-25" / "fetch.parquet").exists()

def test_disk_cache_separates_by_args(tmp_path):
    @disk_cache(cache_dir=tmp_path, ttl="eod")
    def fetch(date: str, code: str) -> pd.DataFrame:
        return pd.DataFrame({"v": [hash((date, code)) % 1000]})

    a = fetch("2026-04-25", "600000")
    b = fetch("2026-04-25", "000001")
    assert not a.equals(b)

def test_disk_cache_refresh_bypasses(tmp_path):
    calls = {"n": 0}

    @disk_cache(cache_dir=tmp_path, ttl="eod")
    def fetch(date: str) -> pd.DataFrame:
        calls["n"] += 1
        return pd.DataFrame({"v": [calls["n"]]})

    fetch("2026-04-25")
    fetch("2026-04-25", _refresh=True)
    assert calls["n"] == 2
