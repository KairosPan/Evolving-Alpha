import pandas as pd
from youzi.data.source import _normalize


def test_normalize_dedupes_duplicate_boards_columns():
    df = pd.DataFrame({"代码": ["1"], "连板数": [3], "昨日连板数": [2]})
    out = _normalize(df)
    # 两个中文列都映射到 boards -> 去重后只剩一列,不崩
    assert list(out.columns).count("boards") == 1
    assert out["code"].iloc[0] == "000001"


def test_normalize_empty_has_blowups_column():
    out = _normalize(pd.DataFrame())
    assert "blowups" in out.columns
