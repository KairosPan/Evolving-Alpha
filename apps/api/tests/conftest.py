import pytest


@pytest.fixture(autouse=True)
def _auto_resume_for_phase1_tests(monkeypatch, request):
    """Phase 1 tests don't exercise interrupt/resume; set auto-resume so the
    graph drives end-to-end. Tests that exercise interrupts opt out via
    `@pytest.mark.no_auto_resume`."""
    if "no_auto_resume" in request.keywords:
        return
    monkeypatch.setenv("YOUZI_AUTO_RESUME", "1")
