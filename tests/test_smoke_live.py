import os
import pytest
from youzi_agent.graph import build_graph
from youzi_agent.cli import _default_date

pytestmark = pytest.mark.live


@pytest.fixture(autouse=True)
def _require_key():
    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY not set; skipping live smoke")


def test_live_full_pipeline_today(tmp_path):
    date = _default_date()
    g = build_graph(checkpoint_path=str(tmp_path / "ck.db"))
    out = g.invoke(
        {"target_date": date, "use_llm": True},
        config={"configurable": {"thread_id": f"smoke-{date}"}},
    )
    assert out["plan"]["date"] == date
    print(f"[smoke] emotion_phase={out.get('emotion_phase')} "
          f"candidates={len(out['plan']['candidates'])} "
          f"errors={len(out.get('errors', []))}")
