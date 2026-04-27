import pandas as pd
from youzi_agent.nodes.leader_tracker import leader_tracker_node, _strength

def _state():
    ztb = pd.DataFrame({
        "代码": ["600202", "002438", "300999", "600000"],
        "名称": ["中核科技", "江苏神通", "新票", "浦发"],
        "连板数": [4, 3, 1, 1],
        "封单金额": [3e8, 1.5e8, 0.5e8, 0.2e8],
        "首次封板时间": ["09:30", "09:45", "10:30", "13:50"],
        "炸板次数": [0, 0, 0, 2],
    })
    return {
        "raw": {"ztb_today": ztb},
        "themes": {
            "核电": {"name": "核电", "members": ["600202", "002438"],
                     "leader": "600202", "phase": "vertical",
                     "catalysts": [], "resonance_score": 0.8},
        },
        "consec_top": 4,
    }

def test_strength_score_orders_by_consec_then_seal():
    a = _strength({"连板数": 4, "封单金额": 3e8, "首次封板时间": "09:30", "炸板次数": 0})
    b = _strength({"连板数": 3, "封单金额": 1e8, "首次封板时间": "10:00", "炸板次数": 1})
    assert a > b

def test_leader_tracker_assigns_total_role():
    out = leader_tracker_node(_state())
    leaders = out["leader_stack"]
    total = next(l for l in leaders if l["role"] == "total")
    assert total["code"] == "600202"
    assert total["consec_boards"] == 4

def test_leader_tracker_succession_healthy():
    out = leader_tracker_node(_state())
    assert out["succession_status"] in {"healthy", "first_div"}
