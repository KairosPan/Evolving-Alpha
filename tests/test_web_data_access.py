# tests/test_web_data_access.py
from youzi_web.data_access import harness_view, seed_harness


def test_seed_harness_view_structure():
    v = harness_view(seed_harness())
    assert {"skills", "memory", "doctrine"} <= set(v)
    assert len(v["skills"]) > 0 and "entries" in v["doctrine"]
    # 种子 stats n=0 → hit_rate/nuke_rate 为 None
    s0 = v["skills"][0]
    assert s0["stats"]["hit_rate"] is None and s0["stats"]["nuke_rate"] is None


def test_harness_view_computes_rates():
    h = seed_harness()
    sk = h.skills.all()[0]
    sk.stats.n = 8; sk.stats.wins = 4; sk.stats.nukes = 2
    v = harness_view(h)
    st = next(s for s in v["skills"] if s["skill_id"] == sk.skill_id)["stats"]
    assert st["hit_rate"] == 0.5 and st["nuke_rate"] == 0.25
