from youzi_agent.state import (
    MarketState, Candidate, PatternHit, ThemeProfile, LeaderProfile,
)
from youzi_agent.reducers import dedupe_candidates_by_code

def test_market_state_typeddict_total_false():
    s: MarketState = {"target_date": "2026-04-25"}
    assert s["target_date"] == "2026-04-25"

def test_dedupe_candidates_keeps_highest_score():
    a = Candidate(code="600000", name="x", pattern_id="L1_first_board",
                  score=0.5, reason="r1", suggested_position=0.1)
    b = Candidate(code="600000", name="x", pattern_id="L2_weak_to_strong",
                  score=0.8, reason="r2", suggested_position=0.1)
    c = Candidate(code="000001", name="y", pattern_id="L1_first_board",
                  score=0.7, reason="r3", suggested_position=0.1)
    out = dedupe_candidates_by_code([a, b, c])
    assert len(out) == 2
    assert {x["code"] for x in out} == {"600000", "000001"}
    assert next(x for x in out if x["code"] == "600000")["score"] == 0.8
