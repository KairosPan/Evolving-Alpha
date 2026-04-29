import pytest


@pytest.fixture(autouse=True)
def _auto_resume_for_phase1_tests(monkeypatch):
    """Phase 1 tests don't exercise interrupt/resume; set auto-resume so the
    graph drives end-to-end. Phase 3+ tests that exercise interrupts will
    monkeypatch.delenv this in their own fixture."""
    monkeypatch.setenv("YOUZI_AUTO_RESUME", "1")
