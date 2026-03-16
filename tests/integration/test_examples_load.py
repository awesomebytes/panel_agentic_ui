"""Integration tests: load each example widget via hot_load and verify build()."""
import shutil
from pathlib import Path

import panel as pn
import pytest

_EXAMPLES_DIR = Path("agent/prompts/examples")
_EXAMPLE_FILES = sorted(_EXAMPLES_DIR.glob("example_*.py"))


@pytest.mark.parametrize("example_file", _EXAMPLE_FILES, ids=[f.name for f in _EXAMPLE_FILES])
async def test_example_loads_and_builds(example_file, tmp_path):
    from shell.hot_load import hot_load

    dest = tmp_path / example_file.name
    shutil.copy(example_file, dest)

    module = hot_load(dest)
    assert hasattr(module, "build"), f"{example_file.name} has no build()"

    result = module.build()
    assert isinstance(result, pn.viewable.Viewable), (
        f"{example_file.name}: build() returned {type(result).__name__!r}, "
        "expected a Panel Viewable"
    )
