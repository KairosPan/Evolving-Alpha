import pytest


@pytest.fixture(autouse=True)
def _auto_resume_for_phase1_tests(monkeypatch, request):
    """Phase 1 tests don't exercise interrupt/resume; set auto-resume so the
    graph drives end-to-end. Tests that exercise interrupts opt out via
    `@pytest.mark.no_auto_resume`."""
    if "no_auto_resume" in request.keywords:
        return
    monkeypatch.setenv("YOUZI_AUTO_RESUME", "1")


@pytest.fixture(autouse=True)
def _reset_sse_app_status():
    """sse_starlette caches an anyio.Event tied to the first test's loop;
    reset before each test so per-loop SSE works in isolation."""
    try:
        from sse_starlette.sse import AppStatus
        AppStatus.should_exit_event = None
    except Exception:
        pass
    yield
