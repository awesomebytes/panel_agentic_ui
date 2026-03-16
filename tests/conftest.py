import json
import subprocess
import time

import httpx
import pytest

CLEAN_LAYOUT = {
    "root": {
        "type": "row",
        "content": [
            {
                "type": "stack",
                "size": "75%",
                "content": [
                    {
                        "type": "component",
                        "componentType": "panel-widget",
                        "componentState": {"widget_name": "welcome"},
                        "title": "Welcome",
                    }
                ],
            },
            {
                "type": "column",
                "size": "25%",
                "content": [
                    {
                        "type": "stack",
                        "size": "100%",
                        "content": [
                            {
                                "type": "component",
                                "componentType": "panel-widget",
                                "componentState": {"widget_name": "__chat__"},
                                "title": "Chat",
                            },
                            {
                                "type": "component",
                                "componentType": "panel-widget",
                                "componentState": {"widget_name": "__widget_picker__"},
                                "title": "Widget Library",
                            },
                        ],
                    }
                ],
            },
        ],
    }
}


@pytest.fixture(scope="session")
def app_url():
    """Start the Panel app and return the URL."""
    import pathlib

    project_root = pathlib.Path(__file__).parent.parent
    layout_file = project_root / "layout.json"
    layout_file.write_text(json.dumps(CLEAN_LAYOUT))

    port = 5099
    url = f"http://localhost:{port}"
    proc = subprocess.Popen(
        [
            "pixi",
            "run",
            "panel",
            "serve",
            "main.py",
            "--port",
            str(port),
            "--address",
            "127.0.0.1",
            f"--allow-websocket-origin=localhost:{port}",
            "--num-threads=2",
        ],
        cwd=str(project_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    for _ in range(30):
        try:
            r = httpx.get(url, timeout=2, follow_redirects=True)
            if r.status_code in (200, 302):
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        proc.kill()
        stdout = proc.stdout.read().decode() if proc.stdout else ""
        raise RuntimeError(f"Panel server did not start in 30s. Output:\n{stdout}")
    yield url
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
