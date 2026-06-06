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
