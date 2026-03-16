"""Unit tests for agent.validator.validate()."""
from pathlib import Path

import pytest

from agent.validator import validate

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

VALID_WIDGET = '''\
"""
{
    "name": "test_widget",
    "version": 1,
    "title": "Test Widget",
    "description": "A test widget for unit tests",
    "tags": ["telemetry", "demo"],
    "category": "monitoring"
}
"""
import param


class TestWidget(param.Parameterized):
    def get_panel(self):
        return "hello"


def build():
    w = TestWidget()
    return w.get_panel()
'''

_MANIFEST_ONLY = '''\
"""
{
    "name": "%s",
    "version": 1,
    "title": "T",
    "description": "D",
    "tags": [],
    "category": "test"
}
"""
'''


def _minimal(name: str, extra: str = "") -> str:
    """Return a minimal valid widget with an optional code suffix."""
    return _MANIFEST_ONLY % name + "def build():\n    return None\n" + extra


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_valid_widget_passes():
    result = validate(VALID_WIDGET)
    assert result.ok is True
    assert result.error is None


def test_valid_widget_from_path(tmp_path):
    p = tmp_path / "widget_path_test_v1.py"
    p.write_text(VALID_WIDGET, encoding="utf-8")
    result = validate(p)
    assert result.ok is True


# ---------------------------------------------------------------------------
# Structural failures
# ---------------------------------------------------------------------------


def test_missing_build_fails():
    source = VALID_WIDGET.replace("def build():", "def notbuild():")
    result = validate(source)
    assert result.ok is False
    assert "build()" in result.error


def test_missing_manifest_fails():
    source = "import param\n\ndef build():\n    return None\n"
    result = validate(source)
    assert result.ok is False
    assert "MANIFEST" in result.error


def test_malformed_manifest_json_fails():
    source = '"""{not valid json}"""\n\ndef build():\n    return None\n'
    result = validate(source)
    assert result.ok is False
    assert "JSON" in result.error


def test_string_version_fails():
    source = '''\
"""
{
    "name": "version_widget",
    "version": "1",
    "title": "T",
    "description": "D",
    "tags": [],
    "category": "test"
}
"""

def build():
    return None
'''
    result = validate(source)
    assert result.ok is False
    assert "version" in result.error.lower()


def test_syntax_error_fails():
    source = (
        '"""\n{"name":"w","version":1,"title":"T","description":"D","tags":[],"category":"c"}\n"""\n'
        "def build(\n"
    )
    result = validate(source)
    assert result.ok is False
    assert "SyntaxError" in result.error


# ---------------------------------------------------------------------------
# Forbidden call patterns
# ---------------------------------------------------------------------------


def test_requests_get_fails():
    source = _minimal("rq") + "import requests\nrequests.get('http://example.com')\n"
    result = validate(source)
    assert result.ok is False
    assert "requests.get" in result.error


def test_subprocess_run_fails():
    source = _minimal("sp") + "import subprocess\nsubprocess.run(['ls'])\n"
    result = validate(source)
    assert result.ok is False
    assert "subprocess.run" in result.error


def test_time_sleep_fails():
    source = _minimal("ts") + "import time\ntime.sleep(1)\n"
    result = validate(source)
    assert result.ok is False
    assert "time.sleep" in result.error


def test_os_system_fails():
    source = _minimal("os") + "import os\nos.system('ls')\n"
    result = validate(source)
    assert result.ok is False
    assert "os.system" in result.error


# ---------------------------------------------------------------------------
# Allowed patterns that must NOT be rejected
# ---------------------------------------------------------------------------


def test_asyncio_create_subprocess_exec_in_async_method_passes():
    source = '''\
"""
{
    "name": "async_widget",
    "version": 1,
    "title": "Async Widget",
    "description": "Tests async subprocess in method",
    "tags": ["async"],
    "category": "test"
}
"""
import asyncio
import param


class AsyncWidget(param.Parameterized):
    async def run(self):
        proc = await asyncio.create_subprocess_exec("ls")
        return proc


def build():
    return AsyncWidget()
'''
    result = validate(source)
    assert result.ok is True


def test_exec_builtin_in_class_method_passes():
    source = '''\
"""
{
    "name": "exec_widget",
    "version": 1,
    "title": "Exec Widget",
    "description": "Tests exec() builtin in method",
    "tags": [],
    "category": "test"
}
"""
import param


class DynWidget(param.Parameterized):
    def run_code(self, code: str):
        exec(code)


def build():
    return DynWidget()
'''
    result = validate(source)
    assert result.ok is True


# ---------------------------------------------------------------------------
# Top-level bare expression
# ---------------------------------------------------------------------------


def test_top_level_bare_call_fails():
    source = '''\
"""
{
    "name": "bare_widget",
    "version": 1,
    "title": "Bare",
    "description": "Has bare call",
    "tags": [],
    "category": "test"
}
"""
import param

print("this is a bare call at module scope")


def build():
    return None
'''
    result = validate(source)
    assert result.ok is False
    assert "Bare top-level expression" in result.error


# ---------------------------------------------------------------------------
# Metadata extraction
# ---------------------------------------------------------------------------


def test_metadata_extracted_correctly():
    result = validate(VALID_WIDGET)
    assert result.ok is True
    meta = result.metadata
    assert meta["name"] == "test_widget"
    assert meta["title"] == "Test Widget"
    assert meta["category"] == "monitoring"
    assert "telemetry" in meta["tags"]
    assert meta["version"] == 1


# ---------------------------------------------------------------------------
# Example files
# ---------------------------------------------------------------------------

_EXAMPLES_DIR = Path("agent/prompts/examples")
_EXAMPLE_FILES = sorted(_EXAMPLES_DIR.glob("example_*.py"))


@pytest.mark.parametrize("example_file", _EXAMPLE_FILES, ids=[f.name for f in _EXAMPLE_FILES])
def test_all_example_files_pass_validator(example_file):
    result = validate(example_file.read_text(encoding="utf-8"))
    assert result.ok, f"{example_file.name}: {result.error}"
