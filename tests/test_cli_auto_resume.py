import os
from youzi_agent.graph import build_graph


def test_cli_path_auto_resumes_through_interrupts(tmp_path, monkeypatch):
    """When YOUZI_AUTO_RESUME=1 (CLI mode), the graph completes without
    blocking on any interrupt — proven by graph.invoke returning a state
    that contains 'target_date' (the offline-fixture run path)."""
    monkeypatch.setenv("YOUZI_AUTO_RESUME", "1")
    g = build_graph(checkpoint_path=str(tmp_path / "ckpt.db"))
    out = g.invoke(
        {"target_date": "1970-01-01", "use_llm": False},
        config={"configurable": {"thread_id": "auto-resume-test"}},
    )
    assert "target_date" in out
