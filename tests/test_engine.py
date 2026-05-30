# tests/test_engine.py
from datetime import date
import pandas as pd
import pytest
from youzi.replay.engine import ReplayEngine
from youzi.replay.firewall import LookaheadError
from tests.conftest import FakeSource


def _src(days):
    frames = {}
    for i, d in enumerate(days):
        frames[("zt", d)] = pd.DataFrame(
            {"code": [str(i)], "name": [f"t{i}"], "boards": [i + 1]})
        frames[("prev", d)] = pd.DataFrame({"code": ["x"], "pct": [1.0]})
        frames[("blowup", d)] = pd.DataFrame(columns=["code"])
        frames[("dt", d)] = pd.DataFrame(columns=["code"])
    return FakeSource(frames, days)


def test_engine_walks_forward_and_is_reset_free():
    days = [date(2024, 6, 26), date(2024, 6, 27), date(2024, 6, 28)]
    eng = ReplayEngine(_src(days), start=days[0], end=days[-1])
    seen = [eng.cursor]
    eng.observe()                 # 观察首日
    while eng.step():
        seen.append(eng.cursor)
        eng.observe()             # 每到新交易日观察一次
    assert seen == days                      # 逐日前进
    # reset-free:游标停在末日,history 累积了 3 天
    assert eng.cursor == days[-1]
    assert len(eng.history) == 3


def test_observe_idempotent_per_cursor():
    days = [date(2024, 6, 26), date(2024, 6, 27)]
    eng = ReplayEngine(_src(days), start=days[0], end=days[-1])
    eng.observe(); eng.observe()
    assert len(eng.history) == 1   # 同一游标多次 observe 不重复入 history


def test_engine_observe_is_firewalled():
    days = [date(2024, 6, 26), date(2024, 6, 27)]
    eng = ReplayEngine(_src(days), start=days[0], end=days[-1])
    st = eng.observe()
    assert st.date == days[0]
    # 直接越过游标取未来数据 -> 拦截
    with pytest.raises(LookaheadError):
        eng.guarded_source.zt_pool(days[1])
