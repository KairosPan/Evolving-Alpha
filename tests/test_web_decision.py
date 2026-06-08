def test_skill_plan_resolves_and_degrades():
    from youzi_web.data_access import skill_plan, seed_harness
    h = seed_harness()
    name = h.skills.all()[0].name_cn
    plan = skill_plan(name, h)
    assert plan is not None and "trigger" in plan and "taboo" in plan
    assert skill_plan("不存在的模式xyz", h) is None         # join 不到 → None


def test_cockpit_context_enriches(tmp_path, monkeypatch):
    monkeypatch.setenv("YOUZI_RUNS_DIR", str(tmp_path))
    from youzi.loop.run_store import RunStore
    from tests.test_run_store import make_report
    RunStore(tmp_path).save("sample", make_report(), {"window": "w", "scorer": "pool"})
    from youzi_web.features.decision.service import cockpit_context
    ctx = cockpit_context(None, None)
    assert ctx["run_id"] == "sample" and ctx["step"] is not None
    assert ctx["days"]                                       # 有日期可选
    assert ctx["candidates"] and "cand" in ctx["candidates"][0]   # 候选 enrich(cand/plan/outcome)
