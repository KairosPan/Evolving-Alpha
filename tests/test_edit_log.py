from youzi.harness.edit_log import EditLog, EditRecord


def test_edit_log_appends_with_monotonic_seq():
    log = EditLog()
    r0 = log.append("write_skill", "skill", "a", "create", "甲")
    r1 = log.append("rewrite_doctrine", "doctrine", "退潮作战", "rewrite")
    assert isinstance(r0, EditRecord)
    assert r0.seq == 0 and r1.seq == 1
    assert len(log) == 2


def test_edit_log_queries():
    log = EditLog()
    log.append("write_skill", "skill", "a", "create")
    log.append("retire_skill", "skill", "a", "dormant")
    log.append("process_memory", "memory", "l1", "create")
    assert [r.target_id for r in log.by_kind("skill")] == ["a", "a"]
    assert [r.seq for r in log.by_tool("write_skill")] == [0]
    assert len(log.records()) == 3
