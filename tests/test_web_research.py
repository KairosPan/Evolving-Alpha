# tests/test_web_research.py
from fastapi.testclient import TestClient

from youzi_web.app import create_app


def _seed_run(tmp_path, monkeypatch):
    monkeypatch.setenv("YOUZI_RUNS_DIR", str(tmp_path))
    from youzi.loop.run_store import RunStore
    from tests.test_run_store import make_report
    RunStore(tmp_path).save("sample", make_report(), {"window": "w", "scorer": "pool"})


def test_views_resilient_to_no_loop_report_and_foreign_file(tmp_path, monkeypatch):
    # hch_loop_report=None(类型允许)+ run 目录混入外来 json:三视图都 200(不 500)
    monkeypatch.setenv("YOUZI_RUNS_DIR", str(tmp_path))
    from youzi.loop.run_store import RunStore
    from tests.test_run_store import make_report
    rep = make_report().model_copy(update={"hch_loop_report": None})
    RunStore(tmp_path).save("noloop", rep, {"window": "w", "scorer": "pool"})
    (tmp_path / "foreign.json").write_text('{"hello": "x"}', encoding="utf-8")
    c = TestClient(create_app())
    for p in ("/research/compare", "/research/refine", "/research/trajectory"):
        assert c.get(p).status_code == 200


def test_compare_view(tmp_path, monkeypatch):
    _seed_run(tmp_path, monkeypatch)
    r = TestClient(create_app()).get("/research/compare")
    assert r.status_code == 200
    assert "HCH" in r.text and "Hexpert" in r.text
    assert "胜" in r.text or "未胜" in r.text          # verdict
    assert "sample" in r.text                          # 运行选择器


def test_refine_and_trajectory_views(tmp_path, monkeypatch):
    _seed_run(tmp_path, monkeypatch)
    c = TestClient(create_app())
    assert c.get("/research/refine").status_code == 200
    t = c.get("/research/trajectory")
    assert t.status_code == 200 and "W" in t.text       # trajectory 含选股 W


def test_empty_state(tmp_path, monkeypatch):
    monkeypatch.setenv("YOUZI_RUNS_DIR", str(tmp_path))   # 空 runs 目录
    c = TestClient(create_app())
    for path in ("/research/compare", "/research/refine", "/research/trajectory"):
        r = c.get(path)
        assert r.status_code == 200 and "还没有运行结果" in r.text


def test_subnav_enabled():
    r = TestClient(create_app()).get("/research/harness")
    assert "/research/compare" in r.text                 # 子导航点亮(有 href)
