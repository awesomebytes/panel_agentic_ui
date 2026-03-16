"""E2E tests for Phase 2 — Chat Panel."""
import pathlib

import pytest

SCREENSHOTS = pathlib.Path(__file__).parent.parent / "visual"


@pytest.mark.e2e
def test_chat_tab_visible(page, app_url):
    """Chat tab is present in GL header."""
    page.goto(app_url)
    page.wait_for_selector(".lm_tab", timeout=20000)
    tab = page.locator(".lm_tab").filter(has_text="Chat")
    assert tab.count() >= 1
    page.screenshot(path=str(SCREENSHOTS / "chat_tab_visible.png"))


@pytest.mark.e2e
def test_welcome_and_chat_both_visible(page, app_url):
    """Both Welcome and Chat tabs are present."""
    page.goto(app_url)
    page.wait_for_selector(".lm_tab", timeout=20000)
    welcome = page.locator(".lm_tab").filter(has_text="Welcome")
    chat = page.locator(".lm_tab").filter(has_text="Chat")
    assert welcome.count() >= 1
    assert chat.count() >= 1


@pytest.mark.e2e
def test_two_gl_columns_visible(page, app_url):
    """Layout has two columns (main + chat)."""
    page.goto(app_url)
    page.wait_for_selector(".lm_content", timeout=20000)
    page.wait_for_timeout(2000)
    content_areas = page.locator(".lm_content").count()
    assert content_areas >= 2, f"Expected at least 2 content areas, got {content_areas}"
    page.screenshot(path=str(SCREENSHOTS / "two_columns.png"))
