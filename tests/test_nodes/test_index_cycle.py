import numpy as np
import pandas as pd
from youzi_agent.nodes.index_cycle import index_cycle_node, _macd, _classify_phase

def test_macd_outputs_three_series():
    closes = pd.Series(np.linspace(100, 120, 100))
    dif, dea, hist = _macd(closes)
    assert len(dif) == len(dea) == len(hist) == 100
    assert not pd.isna(dif.iloc[-1])

def test_classify_phase_uptrend():
    closes = pd.Series(np.linspace(100, 200, 80))
    assert _classify_phase(closes) == "uptrend"

def test_classify_phase_downtrend():
    closes = pd.Series(np.linspace(200, 100, 80))
    assert _classify_phase(closes) == "downtrend"

def test_index_cycle_node_returns_phase():
    closes_sh = np.linspace(3000, 3500, 100)
    closes_cyb = np.linspace(2000, 2300, 100)
    raw = {
        "idx_sh":  pd.DataFrame({"close": closes_sh,  "amount": np.linspace(1e10, 2e10, 100)}),
        "idx_cyb": pd.DataFrame({"close": closes_cyb, "amount": np.linspace(5e9, 8e9, 100)}),
    }
    out = index_cycle_node({"raw": raw, "target_date": "2026-04-25"})
    assert out["index_phase"] in {"uptrend", "top", "downtrend", "bottom", "oscillation"}
    assert "sz_macd" in out and "cyb_macd" in out
    assert out["market_volume"] > 0
