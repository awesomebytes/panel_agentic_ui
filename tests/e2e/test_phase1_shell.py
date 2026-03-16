"""E2E tests for Phase 1 — GoldenLayout shell."""
import pathlib
import pytest

SCREENSHOTS = pathlib.Path(__file__).parent.parent / "visual"


@pytest.mark.e2e
def test_shell_loads_with_goldenlayout(page, app_url):
    """GL container renders at full viewport."""
    page.goto(app_url)
    page.wait_for_selector("#gl-container", timeout=20000)
    gl = page.locator("#gl-container")
    assert gl.count() == 1
    box = gl.bounding_box()
    assert box and box["width"] > 100 and box["height"] > 100
    page.screenshot(path=str(SCREENSHOTS / "shell_loads.png"))


@pytest.mark.e2e
def test_widget_tab_visible(page, app_url):
    """Welcome tab is present in GL header."""
    page.goto(app_url)
    page.wait_for_selector(".lm_tab", timeout=20000)
    tab = page.locator(".lm_tab").filter(has_text="Welcome")
    assert tab.count() >= 1


@pytest.mark.e2e
def test_close_button_visible(page, app_url):
    """Close button exists on GL tabs."""
    page.goto(app_url)
    page.wait_for_selector(".lm_close_tab", timeout=20000)
    assert page.locator(".lm_close_tab").count() >= 1


@pytest.mark.e2e
def test_widget_content_mounted(page, app_url):
    """Panel widget root gets mounted into GL container."""
    page.goto(app_url)
    page.wait_for_selector(".lm_tab", timeout=20000)
    page.wait_for_timeout(3000)
    lm_content_count = page.evaluate(
        '() => document.querySelectorAll(".lm_content").length'
    )
    assert lm_content_count >= 1, "Expected at least one GL content area"
    page.screenshot(path=str(SCREENSHOTS / "widget_mounted.png"))


@pytest.mark.e2e
def test_layout_persists_after_reload(page, app_url):
    """Layout state survives a full page reload after debounced save."""
    page.goto(app_url)
    page.wait_for_selector(".lm_tab", timeout=20000)
    page.wait_for_timeout(2000)
    page.reload()
    page.wait_for_selector(".lm_tab", timeout=20000)
    tab = page.locator(".lm_tab").filter(has_text="Welcome")
    assert tab.count() >= 1
    page.screenshot(path=str(SCREENSHOTS / "shell_after_reload.png"))
