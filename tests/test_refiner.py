# tests/test_refiner.py
import pytest
from youzi.refine.refiner import Refiner, RefinerConfig, RefineReport, AppliedEdit, RejectedEdit
from youzi.refine.ops import RefineOp
from youzi.harness.metatools import MetaTools
from youzi.llm.client import MockLLMClient
from tests.test_metatools import _harness


def _refiner(h=None, cfg=None):
    h = h or _harness()
    meta = MetaTools(h)
    r = Refiner(h, MockLLMClient('{"ops": []}'), meta, cfg or RefinerConfig())
    return r, h, meta


def test_apply_op_accept_promote():
    # _harness 的技能 a 是 active;先 retire→revive 使其 incubating,再 promote
    r, h, meta = _refiner()
    meta.retire_skill("a"); meta.revive_skill("a")     # a -> incubating
    ok, res = r._apply_op(RefineOp(tool="promote_skill", args={"skill_id": "a"},
                                   rationale="胜率回升"), "K", PASS_K())
    assert ok and isinstance(res, AppliedEdit)
    assert res.tool == "promote_skill" and res.target_id == "a"
    assert h.skills.get("a").status == "active"


def test_apply_op_reject_immutable():
    r, h, meta = _refiner()
    ok, res = r._apply_op(RefineOp(tool="rewrite_doctrine",
                                   args={"section": "纪律:退潮不接力", "new_guidance": "篡改"},
                                   rationale="想放松"), "p", PASS_P())
    assert not ok and isinstance(res, RejectedEdit)
    assert "Immutable" in res.reason
    assert h.doctrine.get("纪律:退潮不接力").guidance == "退潮禁接力"   # 未变
    assert len(meta.log) == 0                                           # 未记日志


def test_apply_op_reject_invalid_transition():
    r, h, _ = _refiner()
    ok, res = r._apply_op(RefineOp(tool="revive_skill", args={"skill_id": "a"},
                                   rationale="复活"), "K", PASS_K())   # a 是 active,非 dormant
    assert not ok and "InvalidTransition" in res.reason


def test_apply_op_reject_wrong_pass_tool():
    r, _, _ = _refiner()
    ok, res = r._apply_op(RefineOp(tool="rewrite_doctrine", args={"section": "x", "new_guidance": "y"},
                                   rationale="r"), "K", PASS_K())      # rewrite 不在 K-pass
    assert not ok and "本 K-pass" in res.reason


def test_apply_op_reject_missing_rationale():
    r, _, _ = _refiner()
    ok, res = r._apply_op(RefineOp(tool="promote_skill", args={"skill_id": "a"}, rationale="  "),
                          "K", PASS_K())
    assert not ok and "rationale" in res.reason


def test_apply_op_reject_hallucinated_target():
    r, _, _ = _refiner()
    ok, res = r._apply_op(RefineOp(tool="patch_skill", args={"skill_id": "不存在", "notes": "x"},
                                   rationale="r"), "K", PASS_K())
    assert not ok and "KeyError" in res.reason


def test_apply_op_reject_duplicate_write():
    r, _, _ = _refiner()
    skill = {"skill_id": "a", "name_cn": "重复", "type": "pattern",
             "applicable_regime": ["主升"], "trigger": "t", "entry": "e",
             "exit_stop": "x", "status": "incubating"}
    ok, res = r._apply_op(RefineOp(tool="write_skill", args=skill, rationale="r"), "K", PASS_K())
    assert not ok and "重复" in res.reason


def test_apply_op_reject_malformed_skill_args():
    r, _, _ = _refiner()
    bad = {"skill_id": "z", "name_cn": "缺字段"}        # 缺 type/trigger/... → ValidationError
    ok, res = r._apply_op(RefineOp(tool="write_skill", args=bad, rationale="r"), "K", PASS_K())
    assert not ok and ("ValidationError" in res.reason or "validation" in res.reason.lower())


# 小工具:从 ops 取白名单,避免在测试里硬写 frozenset
def PASS_K():
    from youzi.refine.ops import PASS_TOOLS
    return PASS_TOOLS["K"]


def PASS_P():
    from youzi.refine.ops import PASS_TOOLS
    return PASS_TOOLS["p"]


from youzi.refine.refiner_prompt import build_refiner_system_prompt  # noqa
from youzi.refine.credit import CreditReport
from youzi.eval.trajectory import Trajectory


def _empty_evidence():
    return Trajectory(steps=[], horizon=1), CreditReport(n_scored=0), []


def _run_refine(scripts, h=None, cfg=None):
    """scripts:按 p/K/M 三次 live 调用顺序给出的 LLM 响应列表。"""
    h = h or _harness()
    meta = MetaTools(h)
    llm = MockLLMClient(scripts)
    r = Refiner(h, llm, meta, cfg or RefinerConfig())
    traj, credit, sigs = _empty_evidence()
    return r.refine(traj, credit, sigs), h, meta, llm


def test_refine_g_pass_is_noop_three_live_calls():
    # 三个 pass 都给空 ops;ΔG 不发调用 → MockLLM 恰好被调 3 次
    rep, h, meta, llm = _run_refine(['{"ops": []}', '{"ops": []}', '{"ops": []}'])
    assert len(llm.calls) == 3
    assert any("G-pass reserved" in n for n in rep.notes)
    assert rep.applied == [] and rep.rejected == []


def test_refine_happy_path_applies_and_logs():
    # p: 改 mutable doctrine;K: 新建 failure_detector 技能;M: 写一条 loss 教训
    p_ops = '{"ops": [{"tool": "rewrite_doctrine", "args": {"section": "主升作战", "new_guidance": "只打最高板"}, "rationale": "杂毛连亏"}]}'
    k_ops = ('{"ops": [{"tool": "write_skill", "args": {"skill_id": "fd1", "name_cn": "追高板防闷",'
             ' "type": "failure_detector", "applicable_regime": ["主升"], "trigger": "最高板尾盘弱",'
             ' "entry": "不追", "exit_stop": "次日低开走", "status": "incubating"}, "rationale": "chased_into_nuke 反复"}]}')
    m_ops = '{"ops": [{"tool": "process_memory", "args": {"lesson_id": "ls1", "regime": "主升", "outcome": "loss", "lesson": "追最高板被闷"}, "rationale": "记牢"}]}'
    rep, h, meta, llm = _run_refine([p_ops, k_ops, m_ops])
    assert {e.tool for e in rep.applied} == {"rewrite_doctrine", "write_skill", "process_memory"}
    assert rep.rejected == []
    assert h.doctrine.get("主升作战").guidance == "只打最高板"
    assert h.skills.get("fd1") is not None and h.skills.get("fd1").type == "failure_detector"
    assert h.memory.get("ls1") is not None
    # 全进 EditLog,且带 rationale
    assert len(meta.log) == 3
    assert all(rec.rationale for rec in meta.log.records())


def test_refine_rejects_immutable_in_p_pass():
    p_ops = '{"ops": [{"tool": "rewrite_doctrine", "args": {"section": "纪律:退潮不接力", "new_guidance": "放松"}, "rationale": "想改"}]}'
    rep, h, meta, llm = _run_refine([p_ops, '{"ops": []}', '{"ops": []}'])
    assert rep.applied == []
    assert len(rep.rejected) == 1 and "Immutable" in rep.rejected[0].reason
    assert h.doctrine.get("纪律:退潮不接力").guidance == "退潮禁接力"
    assert len(meta.log) == 0


def test_refine_per_pass_cap_enforced():
    # K-pass 给 3 个 promote,但 cap=1 → 1 applied(被 a 占用?需先 incubating)+ 余者超限拒绝
    h = _harness()
    # 准备 3 个 incubating 技能 b/c/d
    from youzi.harness.skill import Skill
    for sid in ("b", "c", "d"):
        h.skills.write(Skill.from_seed({"skill_id": sid, "name_cn": sid, "type": "pattern",
                                        "applicable_regime": ["主升"], "trigger": "t",
                                        "entry": "e", "exit_stop": "x", "status": "incubating"}))
    k_ops = ('{"ops": ['
             '{"tool": "promote_skill", "args": {"skill_id": "b"}, "rationale": "r"},'
             '{"tool": "promote_skill", "args": {"skill_id": "c"}, "rationale": "r"},'
             '{"tool": "promote_skill", "args": {"skill_id": "d"}, "rationale": "r"}]}')
    cfg = RefinerConfig(max_edits_per_pass=1, max_edits_per_refine=12)
    rep, h2, meta, llm = _run_refine(['{"ops": []}', k_ops, '{"ops": []}'], h=h, cfg=cfg)
    assert len(rep.applied) == 1
    assert len(rep.rejected) == 2 and all("per-pass" in r.reason for r in rep.rejected)


def test_refine_per_refine_cap_enforced():
    h = _harness()
    from youzi.harness.skill import Skill
    for sid in ("b", "c", "d"):
        h.skills.write(Skill.from_seed({"skill_id": sid, "name_cn": sid, "type": "pattern",
                                        "applicable_regime": ["主升"], "trigger": "t",
                                        "entry": "e", "exit_stop": "x", "status": "incubating"}))
    k_ops = ('{"ops": ['
             '{"tool": "promote_skill", "args": {"skill_id": "b"}, "rationale": "r"},'
             '{"tool": "promote_skill", "args": {"skill_id": "c"}, "rationale": "r"}]}')
    cfg = RefinerConfig(max_edits_per_pass=5, max_edits_per_refine=1)
    rep, h2, meta, llm = _run_refine(['{"ops": []}', k_ops, '{"ops": []}'], h=h, cfg=cfg)
    assert len(rep.applied) == 1
    assert len(rep.rejected) == 1 and "per-refine" in rep.rejected[0].reason
