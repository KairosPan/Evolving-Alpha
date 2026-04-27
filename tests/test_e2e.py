from unittest.mock import patch
from youzi_agent.graph import build_graph


def test_e2e_full_graph_no_llm(tmp_path, mock_akshare_client):
    with patch("youzi_agent.nodes.market_sensor.AkshareClient",
               return_value=mock_akshare_client):
        g = build_graph(checkpoint_path=str(tmp_path / "ck.db"))
        out = g.invoke(
            {"target_date": "2026-04-25", "use_llm": False},
            config={"configurable": {"thread_id": "e2e"}},
        )
    assert out["plan"]["date"] == "2026-04-25"
    assert (tmp_path).exists()
    plan_codes = [c["code"] for c in out["plan"]["candidates"]]
    assert isinstance(plan_codes, list)
    assert out.get("emotion_phase") in {
        "chaos", "recovery", "warming", "main_rise", "climax",
        "divergence", "decay_1", "decay_mid", "decay_2",
    }
