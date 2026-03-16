"""LLM provider abstraction and generate-validate-load pipeline."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, AsyncIterator

import httpx

from agent.chat_manager import ChatSession
from agent.example_selector import select_examples
from agent.validator import validate
from config import Settings
from shell.golden_shell import GoldenShell
from shell.hot_load import cleanup_old_versions, hot_load_with_fallback, update_manifest
from shell.widget_registry import WidgetRegistry

log = logging.getLogger(__name__)

MAX_RETRIES = 3

_SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / "system.md"
_CODE_FENCE_RE = re.compile(r"```python\s*\n(.*?)```", re.DOTALL)


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

class AnthropicProvider:
    """Anthropic Messages API via httpx.AsyncClient."""

    _API_URL = "https://api.anthropic.com/v1/messages"
    _API_VERSION = "2023-06-01"

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": self._API_VERSION,
            "content-type": "application/json",
        }

    async def complete(self, system: str, messages: list[dict]) -> str:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                self._API_URL,
                headers=self._headers(),
                json={
                    "model": self._model,
                    "max_tokens": 8192,
                    "system": system,
                    "messages": messages,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]

    async def stream(self, system: str, messages: list[dict]) -> AsyncIterator[str]:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                self._API_URL,
                headers={**self._headers(), "accept": "text/event-stream"},
                json={
                    "model": self._model,
                    "max_tokens": 8192,
                    "system": system,
                    "messages": messages,
                    "stream": True,
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if not payload or payload == "[DONE]":
                        continue
                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            yield delta.get("text", "")


class OpenAIProvider:
    """OpenAI Chat Completions API via httpx.AsyncClient."""

    _API_URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "content-type": "application/json",
        }

    async def complete(self, system: str, messages: list[dict]) -> str:
        all_messages = [{"role": "system", "content": system}, *messages]
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                self._API_URL,
                headers=self._headers(),
                json={"model": self._model, "messages": all_messages},
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def stream(self, system: str, messages: list[dict]) -> AsyncIterator[str]:
        all_messages = [{"role": "system", "content": system}, *messages]
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                self._API_URL,
                headers=self._headers(),
                json={"model": self._model, "messages": all_messages, "stream": True},
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if not payload or payload == "[DONE]":
                        continue
                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    delta = event.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content")
                    if content:
                        yield content


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_provider(settings: Settings) -> AnthropicProvider | OpenAIProvider:
    """Return the configured LLM provider."""
    if settings.llm_provider == "openai":
        return OpenAIProvider(api_key=settings.openai_api_key, model=settings.llm_model)
    return AnthropicProvider(api_key=settings.anthropic_api_key, model=settings.llm_model)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_code(response: str) -> str | None:
    """Return the content of the first ```python ... ``` block, or None."""
    match = _CODE_FENCE_RE.search(response)
    return match.group(1) if match else None


def _build_system_prompt(
    registry: WidgetRegistry,
    user_request: str,
    examples_dir: Path,
) -> str:
    template = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")

    loaded = registry.list_names()
    loaded_str = ", ".join(loaded) if loaded else "(none)"

    examples: list[str] = []
    if examples_dir.is_dir():
        examples = select_examples(user_request, examples_dir)
    examples_str = "\n\n---\n\n".join(examples) if examples else "(no relevant examples found)"

    return (
        template
        .replace("{loaded_widgets}", loaded_str)
        .replace("{selected_examples}", examples_str)
    )


def _retry_messages(
    original_messages: list[dict],
    last_response: str,
    last_error: str,
) -> list[dict]:
    """Append the failed attempt and correction request to the message list."""
    msgs = list(original_messages)
    if last_response:
        msgs.append({"role": "assistant", "content": last_response})
    msgs.append({
        "role": "user",
        "content": (
            "The widget code you generated failed validation with this error:\n\n"
            f"```\n{last_error}\n```\n\n"
            "Please fix the code and respond with a corrected ```python ... ``` block."
        ),
    })
    return msgs


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

async def generate_and_load(
    user_request: str,
    session: ChatSession,
    shell: GoldenShell,
    registry: WidgetRegistry,
    settings: Settings,
) -> bool:
    """Generate a widget via LLM, validate it, and hot-load it into the shell.

    Returns True on success, False after MAX_RETRIES failures.
    """
    provider = get_provider(settings)
    widgets_dir = Path(settings.widgets_dir)
    manifest_path = widgets_dir / "manifest.json"
    examples_dir = widgets_dir / "examples"

    system_prompt = _build_system_prompt(registry, user_request, examples_dir)

    # Build initial message list from session history (user + assistant turns only)
    base_messages: list[dict[str, Any]] = [
        {"role": m["role"], "content": m["content"]}
        for m in session.history
        if m["role"] in ("user", "assistant")
    ]

    last_response = ""
    last_error = ""

    for attempt in range(MAX_RETRIES):
        current_messages = (
            base_messages
            if attempt == 0
            else _retry_messages(base_messages, last_response, last_error)
        )

        log.info(
            "generate_and_load: attempt %d/%d for %r",
            attempt + 1,
            MAX_RETRIES,
            user_request[:60],
        )

        try:
            last_response = await provider.complete(system_prompt, current_messages)
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:300] if exc.response else ""
            if "insufficient_quota" in body or "billing" in body.lower():
                last_error = "OpenAI API quota exceeded — check billing at platform.openai.com"
                log.error(last_error)
                break
            if exc.response and exc.response.status_code == 429:
                import asyncio
                wait = 2 ** (attempt + 1)
                log.warning("Rate limited, waiting %ds before retry", wait)
                await asyncio.sleep(wait)
            last_error = f"LLM API error: {exc}"
            log.error("Attempt %d: %s", attempt + 1, last_error)
            continue
        except httpx.HTTPError as exc:
            last_error = f"LLM API error: {exc}"
            log.error("Attempt %d: %s", attempt + 1, last_error)
            continue

        code = extract_code(last_response)
        if code is None:
            last_error = "No ```python``` code block found in LLM response."
            log.warning("Attempt %d: %s", attempt + 1, last_error)
            continue

        result = validate(code)
        if not result.ok:
            last_error = result.error or "Unknown validation error"
            log.warning("Attempt %d validation failed: %s", attempt + 1, last_error)
            continue

        # --- Validation passed ---
        metadata: dict = result.metadata  # type: ignore[assignment]
        name: str = metadata["name"]
        version: int = metadata["version"]
        widget_path = widgets_dir / f"widget_{name}_v{version}.py"

        try:
            widgets_dir.mkdir(parents=True, exist_ok=True)
            widget_path.write_text(code, encoding="utf-8")
        except OSError as exc:
            msg = f"Failed to write widget file: {exc}"
            log.error(msg)
            session.add_message("assistant", f"Error: {msg}")
            return False

        component, load_error = hot_load_with_fallback(widget_path, name, registry)
        if load_error:
            last_error = f"Widget runtime error: {load_error}"
            log.warning("Attempt %d hot_load failed: %s", attempt + 1, last_error)
            widget_path.unlink(missing_ok=True)
            continue

        registry.add(name, component)

        try:
            shell.add_widget(name, metadata.get("title", name))
        except Exception as exc:
            log.error("shell.add_widget failed for %r: %s", name, exc)

        try:
            update_manifest(manifest_path, metadata)
        except Exception as exc:
            log.error("update_manifest failed: %s", exc)

        try:
            deleted = cleanup_old_versions(widgets_dir, name)
            if deleted:
                log.debug(
                    "cleanup_old_versions: removed %d old file(s) for %r: %s",
                    len(deleted),
                    name,
                    [p.name for p in deleted],
                )
        except Exception as exc:
            log.error("cleanup_old_versions failed for %r: %s", name, exc)

        success_msg = (
            f"Widget **{metadata.get('title', name)}** created and added to the dashboard."
        )
        session.add_message("assistant", success_msg)
        log.info(
            "generate_and_load: success — widget=%r file=%s",
            name,
            widget_path.name,
        )
        return True

    # All attempts exhausted
    error_msg = (
        f"Failed to generate a valid widget after {MAX_RETRIES} attempts. "
        f"Last error: {last_error}"
    )
    session.add_message("assistant", error_msg)
    log.error(
        "generate_and_load: all retries exhausted for %r — %s",
        user_request[:60],
        last_error,
    )
    return False
