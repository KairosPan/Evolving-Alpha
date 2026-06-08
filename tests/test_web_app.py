# tests/test_web_app.py
from fastapi.testclient import TestClient

from youzi_web.app import create_app


def test_shell_boots():
    client = TestClient(create_app())
    r = client.get("/")
    assert r.status_code == 200
    assert "youzi" in r.text          # 外壳 chrome 渲染(图标轨 logo/标题)
