"""GitHub PR creator for generated Panel widgets."""
from __future__ import annotations

import base64
import logging
from pathlib import Path

import httpx

from config import Settings

log = logging.getLogger(__name__)

_GH_API = "https://api.github.com"


class GitHubPRCreator:
    """Creates GitHub pull requests for generated widgets.

    Uploads the widget file, a chat-log markdown document, and optionally
    promotes the widget as a few-shot example.  All GitHub API calls are
    made with ``httpx.AsyncClient`` — never ``requests``.
    """

    @staticmethod
    def is_configured(settings: Settings) -> bool:
        """Return True when both a token and a valid owner/repo are set."""
        return bool(
            settings.github_token
            and settings.github_repo
            and "/" in settings.github_repo
        )

    def __init__(self, settings: Settings) -> None:
        if not settings.github_token:
            raise ValueError("github_token is empty — set MONITOR_GITHUB_TOKEN")
        if "/" not in settings.github_repo:
            raise ValueError(
                f"github_repo must be 'owner/repo', got: {settings.github_repo!r}"
            )
        self._token = settings.github_token
        self._owner, self._repo = settings.github_repo.split("/", 1)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def _get_default_branch_sha(self, client: httpx.AsyncClient) -> str:
        resp = await client.get(
            f"{_GH_API}/repos/{self._owner}/{self._repo}/git/ref/heads/main",
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()["object"]["sha"]

    async def _create_branch(
        self, client: httpx.AsyncClient, branch: str, sha: str
    ) -> None:
        resp = await client.post(
            f"{_GH_API}/repos/{self._owner}/{self._repo}/git/refs",
            headers=self._headers(),
            json={"ref": f"refs/heads/{branch}", "sha": sha},
        )
        resp.raise_for_status()

    async def _upload_file(
        self,
        client: httpx.AsyncClient,
        repo_path: str,
        content: str,
        message: str,
        branch: str,
    ) -> None:
        encoded = base64.b64encode(content.encode()).decode()
        resp = await client.put(
            f"{_GH_API}/repos/{self._owner}/{self._repo}/contents/{repo_path}",
            headers=self._headers(),
            json={"message": message, "content": encoded, "branch": branch},
        )
        resp.raise_for_status()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_pr(
        self,
        widget_name: str,
        widget_path: str | Path,
        description: str,
        chat_log: str,
        include_as_example: bool = False,
    ) -> str:
        """Create a GitHub PR containing the widget and its generation log.

        Args:
            widget_name: Canonical widget name (snake_case).
            widget_path: Path to the versioned ``.py`` file on disk.
            description: Human-readable description for the PR body.
            chat_log: Full chat conversation that produced the widget.
            include_as_example: When ``True``, also copy the widget to
                ``agent/prompts/examples/`` so it can be used as a few-shot
                example in future generations.

        Returns:
            HTML URL of the opened pull request.
        """
        widget_path = Path(widget_path)
        widget_filename = widget_path.name
        widget_content = widget_path.read_text(encoding="utf-8")
        branch = f"widget/{widget_name}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            base_sha = await self._get_default_branch_sha(client)
            await self._create_branch(client, branch, base_sha)

            await self._upload_file(
                client,
                f"widgets/{widget_filename}",
                widget_content,
                f"Add widget: {widget_name}",
                branch,
            )

            chat_log_md = (
                f"# Widget: {widget_name}\n\n"
                f"## Description\n\n{description}\n\n"
                f"## Chat Log\n\n{chat_log}"
            )
            await self._upload_file(
                client,
                f"docs/widget_logs/{widget_name}.md",
                chat_log_md,
                f"Add chat log for widget: {widget_name}",
                branch,
            )

            if include_as_example:
                await self._upload_file(
                    client,
                    f"agent/prompts/examples/{widget_filename}",
                    widget_content,
                    f"Add example: {widget_name}",
                    branch,
                )

            pr_body_lines = [
                f"## Widget: `{widget_name}`",
                "",
                description,
                "",
                "## Files",
                "",
                f"- `widgets/{widget_filename}` — widget implementation",
                f"- `docs/widget_logs/{widget_name}.md` — generation chat log",
            ]
            if include_as_example:
                pr_body_lines.append(
                    f"- `agent/prompts/examples/{widget_filename}` — added as example"
                )

            resp = await client.post(
                f"{_GH_API}/repos/{self._owner}/{self._repo}/pulls",
                headers=self._headers(),
                json={
                    "title": f"Add widget: {widget_name}",
                    "body": "\n".join(pr_body_lines),
                    "head": branch,
                    "base": "main",
                },
            )
            resp.raise_for_status()
            pr_url: str = resp.json()["html_url"]
            log.info("PR created: %s", pr_url)
            return pr_url
