import subprocess
import sys

def test_cli_help_runs():
    r = subprocess.run([sys.executable, "-m", "youzi_agent", "--help"],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert "youzi-agent" in r.stdout.lower() or "usage" in r.stdout.lower()

def test_cli_resolves_default_date():
    from youzi_agent.cli import _default_date
    d = _default_date()
    assert len(d) == 10 and d[4] == "-" and d[7] == "-"
