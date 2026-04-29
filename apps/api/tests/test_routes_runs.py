import json
from fastapi.testclient import TestClient
from apps.api.main import build_app


def test_runs_list_reads_runs_dir(tmp_path):
    runs = tmp_path / "runs"
    (runs / "2026-04-26").mkdir(parents=True)
    (runs / "2026-04-26" / "report.json").write_text(json.dumps({
        "candidates": [{"code": "600519"}],
        "errors": [],
        "plan": {"position_total_max": 0.6}
    }))
    client = TestClient(build_app(checkpoint_path=str(tmp_path / "ckpt.db"),
                                  runs_dir=str(runs)))
    r = client.get("/api/runs")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["date"] == "2026-04-26"
    assert body[0]["candidates_count"] == 1
    assert body[0]["has_plan"] is True
    assert body[0]["errors_count"] == 0


def test_runs_get_by_date_reads_state_snapshot(tmp_path):
    runs = tmp_path / "runs"
    (runs / "2026-04-26").mkdir(parents=True)
    snapshot = {"target_date": "2026-04-26", "emotion_phase": "warming"}
    (runs / "2026-04-26" / "state_snapshot.json").write_text(json.dumps(snapshot))
    client = TestClient(build_app(checkpoint_path=str(tmp_path / "ckpt.db"),
                                  runs_dir=str(runs)))
    r = client.get("/api/runs/2026-04-26")
    assert r.status_code == 200
    assert r.json() == snapshot
