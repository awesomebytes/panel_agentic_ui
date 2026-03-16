"""Keyword-based example selector for widget code generation."""

import json
import re
from pathlib import Path

_STOP_WORDS: frozenset[str] = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "its", "be", "as", "are",
    "was", "were", "that", "this", "which", "i", "me", "my", "we", "our",
    "you", "your", "he", "she", "they", "their", "what", "how", "can",
    "do", "make", "create", "add", "show", "get", "new", "panel", "widget",
})


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if w not in _STOP_WORDS and len(w) > 1}


def _extract_manifest_tags(source: str) -> set[str]:
    """Parse the module-level docstring and return tags as a set of keywords."""
    match = re.match(r'\s*(?:"""|\'\'\')(.*?)(?:"""|\'\'\')' , source, re.DOTALL)
    if not match:
        return set()
    try:
        manifest = json.loads(match.group(1).strip())
        tags: list[str] = manifest.get("tags", [])
        return _tokenize(" ".join(tags))
    except (json.JSONDecodeError, AttributeError):
        return set()


def _score(query_tokens: set[str], path: Path, source: str) -> int:
    filename_tokens = _tokenize(path.stem)
    manifest_tokens = _extract_manifest_tags(source)
    return len(query_tokens & (filename_tokens | manifest_tokens))


def select_examples(
    query: str,
    examples_dir: Path,
    max_examples: int = 3,
) -> list[str]:
    """Return file contents of the top-scoring examples for the given query.

    Scores are based on keyword overlap between the query and each example's
    filename stem plus MANIFEST tags. Files with zero overlap are excluded.
    Returns an empty list if the directory is empty or no matches exist.
    """
    candidates = sorted(examples_dir.glob("*.py"))
    if not candidates:
        return []

    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    scored: list[tuple[int, Path, str]] = []
    for path in candidates:
        source = path.read_text(encoding="utf-8")
        score = _score(query_tokens, path, source)
        if score > 0:
            scored.append((score, path, source))

    scored.sort(key=lambda t: t[0], reverse=True)
    return [source for _, _, source in scored[:max_examples]]
