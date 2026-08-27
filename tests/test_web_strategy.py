# tests/test_web_strategy.py — 策略模块:API + 三页 + 三大件 IA(离线,真实种子 H)
import pytest
from fastapi.testclient import TestClient

from youzi_web.app import create_app


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUZI_RUNS_DIR", str(tmp_path))   # 决策/研究页空态兜底
    return TestClient(create_app())


# ── JSON API(真实种子 H) ─────────────────────────────────────────────────

def test_api_skills_full_and_filters(client):
    all_ = client.get("/api/strategy/skills").json()["skills"]
    assert len(all_) >= 50                                    # 种子 57 技能
    row = all_[0]
    for k in ("skill_id", "name_cn", "status", "trigger", "taboo", "stats"):
        assert k in row
    assert row["stats"]["n"] == 0                             # 种子零战绩,诚实展示
    active = client.get("/api/strategy/skills", params={"status": "active"}).json()["skills"]
    assert active and all(s["status"] == "active" for s in active)
    zhusheng = client.get("/api/strategy/skills", params={"phase": "主升"}).json()["skills"]
    assert zhusheng and all(("主升" in s["phases"]) or s["applies_all"] for s in zhusheng)


def test_api_lens_respects_budgets(client):
    lens = client.get("/api/strategy/lens", params={"phase": "主升"}).json()
    assert lens["phase"] == "主升"
    assert 0 < len(lens["skills"]) <= 20                      # skill_budget
    assert len(lens["lessons"]) <= 12                         # memory_budget
    assert len(lens["trials"]) <= 3                           # 试验位


def test_api_doctrine_immutable_core(client):
    d = client.get("/api/strategy/doctrine").json()
    assert len(d["immutable"]) == 10                          # 10 条纪律红线
    assert d["mutable"]
    assert all("guidance" in e for e in d["immutable"])


def test_api_cycle_seven_phases(client):
    c = client.get("/api/strategy/cycle").json()["phases"]
    assert len(c) == 7
    assert all(p["transitions"] for p in c)


def test_api_memory_sorted_by_weight(client):
    m = client.get("/api/strategy/memory").json()["lessons"]
    assert len(m) >= 20                                       # 种子 21 记忆
    weights = [x["weight"] for x in m]
    assert weights == sorted(weights, reverse=True)


# ── 页面 ─────────────────────────────────────────────────────────────────

def test_skills_page_library_and_lens(client):
    r = client.get("/strategy/skills")
    assert r.status_code == 200
    assert "相位透镜" in r.text and "agent" in r.text.lower()
    assert "待实战" in r.text                                 # 零战绩诚实态


def test_skills_page_phase_lens(client):
    r = client.get("/strategy/skills", params={"phase": "主升"})
    assert r.status_code == 200
    assert "主升" in r.text and "试验" in r.text.replace("试验位", "试验")


def test_doctrine_page(client):
    r = client.get("/strategy/doctrine")
    assert r.status_code == 200
    assert "纪律红线" in r.text and "Refiner" in r.text       # immutable 说明
    assert "口诀" in r.text                                   # 记忆区


def test_cycle_page_ring_links_to_lens(client):
    r = client.get("/strategy/cycle")
    assert r.status_code == 200
    assert "<svg" in r.text
    assert "/strategy/skills?phase=" in r.text                # 相位环 → 透镜联动


# ── 三大件 IA ────────────────────────────────────────────────────────────

def test_rail_three_features(client):
    text = client.get("/strategy/skills").text
    for href in ("/market/board", "/strategy/skills", "/account/overview"):
        assert href in text
    assert text.count('class="rail-item') == 3                # 顶栏只放三件


def test_account_placeholder(client):
    r = client.get("/account/overview")
    assert r.status_code == 200
    assert "持仓" in r.text                                   # 说明将来内容


def test_old_urls_still_work_under_strategy(client):
    for p in ("/decision/cockpit", "/research/compare", "/research/harness"):
        assert client.get(p).status_code == 200
