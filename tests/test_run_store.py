# tests/test_run_store.py
import tempfile
from pathlib import Path

from youzi.harness.snapshot import SnapshotStore
from youzi.loop.compare import compare_harnesses
from youzi.loop.inner_loop import LoopConfig
from youzi.loop.run_store import RunStore
from tests.test_compare import _w_src, _SeqFactory, _CountFactory, _PICK_W, _NO_TRADE
from tests.test_inner_loop import _seed_h


def make_report():
    src = _w_src()
    return compare_harnesses(
        _CountFactory(_seed_h), src, src.trading_calendar()[0], src.trading_calendar()[-1],
        agent_llm_factory=_SeqFactory([_PICK_W, _NO_TRADE]),
        refiner_llm_factory=_SeqFactory(['{"ops": []}']),
        store_factory=_CountFactory(lambda: SnapshotStore(tempfile.mkdtemp())),
        loop_config=LoopConfig(horizon=1))


def test_save_load_roundtrip(tmp_path):
    store = RunStore(tmp_path)
    rep = make_report()
    store.save("r1", rep, {"window": "w", "scorer": "pool"})
    got, meta = store.load("r1")
    assert set(got.arms) == {"HCH", "Hexpert", "Hmin_highest", "Hmin_notrade"}
    assert got.arms["HCH"].report.mean_score == rep.arms["HCH"].report.mean_score
    assert len(got.hch_loop_report.refine_events) == len(rep.hch_loop_report.refine_events)
    assert meta["run_id"] == "r1" and meta["window"] == "w"


def test_list_newest_first_and_atomic(tmp_path):
    store = RunStore(tmp_path)
    rep = make_report()
    store.save("aaa", rep, {"window": "1"})
    store.save("bbb", rep, {"window": "2"})
    ids = [m["run_id"] for m in store.list()]
    assert ids == ["bbb", "aaa"]                 # 新→旧(run_id 倒序)
    assert list(tmp_path.glob("*.tmp")) == []    # 原子写不留临时


def test_sample_run_writes_a_run(tmp_path, monkeypatch):
    monkeypatch.setenv("YOUZI_RUNS_DIR", str(tmp_path))
    import scripts.sample_run as sr
    sr.main()
    metas = RunStore(tmp_path).list()
    assert any(m["run_id"] == "sample" for m in metas)
    rep, _ = RunStore(tmp_path).load("sample")
    assert "HCH" in rep.arms
