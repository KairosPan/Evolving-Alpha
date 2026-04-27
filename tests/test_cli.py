import subprocess
import sys

def test_cli_help_runs():
    r = subprocess.run([sys.executable, "-m", "youzi_agent", "--help"],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert "youzi-agent" in r.stdout.lower() or "usage" in r.stdout.lower()

def test_cli_resolves_default_date():
    from youzi_agent.cli import _default_date
    d = _default_date()
    assert len(d) == 10 and d[4] == "-" and d[7] == "-"


def test_cli_exit_code_when_plan_missing(monkeypatch):
    """Spec §12: exit 1 when graph aborts before plan is built (no errors, no plan)."""
    from youzi_agent import cli
    # State with no plan and no errors — graph aborted cleanly before trade_planner ran.
    fake_graph = type("G", (), {"invoke": lambda self, *a, **k: {}})()
    monkeypatch.setattr(cli, "build_graph", lambda **kw: fake_graph)
    rc = cli.main(["2026-04-25", "--no-llm"])
    # No plan in returned state → exit 1
    assert rc == 1


def test_cli_unique_thread_id_per_run(monkeypatch):
    """Re-runs must not append to the same checkpointer thread."""
    from youzi_agent import cli
    seen_ids = []
    class FakeGraph:
        def invoke(self, _state, config):
            seen_ids.append(config["configurable"]["thread_id"])
            return {"plan": {"date": "2026-04-25", "candidates": []}}
    monkeypatch.setattr(cli, "build_graph", lambda **kw: FakeGraph())
    cli.main(["2026-04-25", "--no-llm"])
    cli.main(["2026-04-25", "--no-llm"])
    assert seen_ids[0] != seen_ids[1]
    assert seen_ids[0].startswith("2026-04-25-")
