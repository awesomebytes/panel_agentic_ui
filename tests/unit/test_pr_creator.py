"""Unit tests for agent.pr_creator.GitHubPRCreator."""
from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import pytest
import respx

from agent.pr_creator import GitHubPRCreator
from config import Settings

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OWNER = "testowner"
REPO = "testrepo"
WIDGET_NAME = "cpu_monitor"
WIDGET_FILENAME = f"widget_{WIDGET_NAME}_v1.py"
BASE_SHA = "abc123def456"
PR_URL = f"https://github.com/{OWNER}/{REPO}/pull/42"
DESCRIPTION = "A CPU monitor widget"
CHAT_LOG = "User: make a cpu widget\nAssistant: here it is"

_REFS_URL = f"https://api.github.com/repos/{OWNER}/{REPO}/git/refs"
_REF_MAIN_URL = f"https://api.github.com/repos/{OWNER}/{REPO}/git/ref/heads/main"
_CONTENTS_RE = re.compile(
    rf"https://api\.github\.com/repos/{OWNER}/{REPO}/contents/.*"
)
_PULLS_URL = f"https://api.github.com/repos/{OWNER}/{REPO}/pulls"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_settings() -> Settings:
    return Settings(github_token="ghp_test_token", github_repo=f"{OWNER}/{REPO}")


@pytest.fixture()
def widget_file(tmp_path: Path) -> Path:
    path = tmp_path / WIDGET_FILENAME
    path.write_text("# widget source\ndef build(): pass\n", encoding="utf-8")
    return path


def _setup_routes(router: respx.MockRouter) -> dict[str, respx.Route]:
    """Register all GitHub API mock routes and return them by name."""
    get_ref = router.get(_REF_MAIN_URL).mock(
        return_value=httpx.Response(200, json={"object": {"sha": BASE_SHA}})
    )
    create_branch = router.post(_REFS_URL).mock(
        return_value=httpx.Response(
            201, json={"ref": f"refs/heads/widget/{WIDGET_NAME}"}
        )
    )
    upload_file = router.put(_CONTENTS_RE).mock(
        return_value=httpx.Response(201, json={"content": {"sha": "file_sha"}})
    )
    create_pr = router.post(_PULLS_URL).mock(
        return_value=httpx.Response(201, json={"html_url": PR_URL})
    )
    return {
        "get_ref": get_ref,
        "create_branch": create_branch,
        "upload_file": upload_file,
        "create_pr": create_pr,
    }


async def _invoke(widget_file: Path, *, include_as_example: bool = False) -> str:
    creator = GitHubPRCreator(_make_settings())
    return await creator.create_pr(
        WIDGET_NAME,
        widget_file,
        DESCRIPTION,
        CHAT_LOG,
        include_as_example=include_as_example,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_branch_created_with_correct_name(widget_file: Path) -> None:
    with respx.MockRouter(assert_all_called=False) as router:
        routes = _setup_routes(router)
        await _invoke(widget_file)

    payload = json.loads(routes["create_branch"].calls[0].request.content)
    assert payload["ref"] == f"refs/heads/widget/{WIDGET_NAME}"


async def test_widget_file_uploaded(widget_file: Path) -> None:
    with respx.MockRouter(assert_all_called=False) as router:
        routes = _setup_routes(router)
        await _invoke(widget_file)

    called_urls = [str(c.request.url) for c in routes["upload_file"].calls]
    assert any(f"widgets/{WIDGET_FILENAME}" in url for url in called_urls)


async def test_chat_log_uploaded(widget_file: Path) -> None:
    with respx.MockRouter(assert_all_called=False) as router:
        routes = _setup_routes(router)
        await _invoke(widget_file)

    called_urls = [str(c.request.url) for c in routes["upload_file"].calls]
    assert any(f"docs/widget_logs/{WIDGET_NAME}.md" in url for url in called_urls)


async def test_pr_opened_with_correct_title(widget_file: Path) -> None:
    with respx.MockRouter(assert_all_called=False) as router:
        routes = _setup_routes(router)
        await _invoke(widget_file)

    payload = json.loads(routes["create_pr"].calls[0].request.content)
    assert payload["title"] == f"Add widget: {WIDGET_NAME}"


async def test_pr_body_non_empty(widget_file: Path) -> None:
    with respx.MockRouter(assert_all_called=False) as router:
        routes = _setup_routes(router)
        await _invoke(widget_file)

    payload = json.loads(routes["create_pr"].calls[0].request.content)
    assert payload["body"]


async def test_returns_pr_url(widget_file: Path) -> None:
    with respx.MockRouter(assert_all_called=False) as router:
        _setup_routes(router)
        result = await _invoke(widget_file)

    assert result == PR_URL


async def test_example_uploaded_when_flagged(widget_file: Path) -> None:
    with respx.MockRouter(assert_all_called=False) as router:
        routes = _setup_routes(router)
        await _invoke(widget_file, include_as_example=True)

    called_urls = [str(c.request.url) for c in routes["upload_file"].calls]
    assert any(
        f"agent/prompts/examples/{WIDGET_FILENAME}" in url for url in called_urls
    )


async def test_example_not_uploaded_when_not_flagged(widget_file: Path) -> None:
    with respx.MockRouter(assert_all_called=False) as router:
        routes = _setup_routes(router)
        await _invoke(widget_file, include_as_example=False)

    called_urls = [str(c.request.url) for c in routes["upload_file"].calls]
    assert not any("agent/prompts/examples" in url for url in called_urls)
