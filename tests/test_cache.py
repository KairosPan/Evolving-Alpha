# tests/test_cache.py
from datetime import date
import pandas as pd
from youzi.data.cache import PITStore


def test_put_then_get_roundtrip(tmp_path):
    store = PITStore(root=tmp_path)
    df = pd.DataFrame({"code": ["000001"], "boards": [7]})
    store.put("zt", date(2024, 6, 27), df)
    got = store.get("zt", date(2024, 6, 27))
    assert got is not None
    assert list(got["code"]) == ["000001"]
    assert int(got["boards"].iloc[0]) == 7


def test_get_missing_returns_none(tmp_path):
    store = PITStore(root=tmp_path)
    assert store.get("zt", date(2024, 6, 27)) is None


def test_has(tmp_path):
    store = PITStore(root=tmp_path)
    assert not store.has("zt", date(2024, 6, 27))
    store.put("zt", date(2024, 6, 27), pd.DataFrame({"code": ["1"]}))
    assert store.has("zt", date(2024, 6, 27))
