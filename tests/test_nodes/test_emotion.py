import pandas as pd
from youzi_agent.nodes.emotion import emotion_node, _ma5_turn, classify_emotion

def test_ma5_turn_up():
    rc = [1500, 1400, 1300, 1200, 1100, 1200, 1500]
    assert _ma5_turn(rc) == "turn_up"

def test_ma5_continue_up():
    rc = [1000, 1200, 1400, 1600, 1800, 2000, 2200]
    assert _ma5_turn(rc) == "continue_up"

def test_classify_emotion_chaos():
    assert classify_emotion(red_count=900, ma5=1500, ma3=1500,
                            ma5_turn="continue_down", blast_rate=0.5,
                            consec_top=2, lu_count=20) == "chaos"

def test_classify_emotion_climax():
    assert classify_emotion(red_count=4200, ma5=3500, ma3=3700,
                            ma5_turn="continue_up", blast_rate=0.1,
                            consec_top=8, lu_count=120) == "climax"

def test_classify_emotion_main_rise():
    assert classify_emotion(red_count=2800, ma5=2500, ma3=2700,
                            ma5_turn="continue_up", blast_rate=0.15,
                            consec_top=6, lu_count=80) == "main_rise"

def test_emotion_node_uses_activity_history():
    activity = pd.DataFrame([
        {"date": f"2026-04-{d:02d}", "red_count": rc}
        for d, rc in zip(range(15, 26), [1100, 1200, 1300, 1400, 1500,
                                          1600, 1700, 1800, 1900, 2000, 2100])
    ])
    state = {
        "raw": {"activity": activity},
        "limit_up_count": 60,
        "consec_top": 5,
        "blast_rate": 0.18,
        "target_date": "2026-04-25",
    }
    out = emotion_node(state)
    assert out["emotion_phase"] in {"recovery", "warming", "main_rise"}
    assert isinstance(out["sentiment_value"], int)
