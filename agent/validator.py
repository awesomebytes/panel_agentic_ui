"""AST-based static validator for LLM-generated widget files."""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

MANIFEST_REQUIRED: frozenset[str] = frozenset(
    {"name", "version", "title", "description", "tags", "category"}
)

FORBIDDEN: frozenset[str] = frozenset({
    "requests.get",
    "requests.post",
    "requests.put",
    "requests.delete",
    "urllib.request.urlopen",
    "time.sleep",
    "subprocess.run",
    "subprocess.call",
    "subprocess.check_output",
    "subprocess.check_call",
    "os.system",
    "os.popen",
})

_TOP_LEVEL_ALLOWED = (
    ast.Assign,
    ast.AugAssign,
    ast.AnnAssign,
    ast.Import,
    ast.ImportFrom,
    ast.ClassDef,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.If,  # e.g. if TYPE_CHECKING: / if __name__ == "__main__":
)


@dataclass
class ValidationResult:
    ok: bool
    error: str | None = None
    metadata: dict | None = None


def _fail(msg: str) -> ValidationResult:
    return ValidationResult(ok=False, error=msg)


def _call_path(node: ast.expr) -> str | None:
    """Reconstruct dotted attribute path for a call target, e.g. 'requests.get'."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_path(node.value)
        return f"{base}.{node.attr}" if base is not None else None
    return None


def _first_forbidden(tree: ast.Module) -> str | None:
    """Return the first forbidden call path found anywhere in the tree, or None."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            path = _call_path(node.func)
            if path and path in FORBIDDEN:
                return path
    return None


def _top_level_bare_call(tree: ast.Module) -> str | None:
    """
    Return an error string if any bare expression statement exists at module level,
    excluding the leading module docstring.
    """
    for idx, stmt in enumerate(tree.body):
        if not isinstance(stmt, ast.Expr):
            continue
        # The first statement may be the module docstring — allow it.
        if idx == 0 and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
            continue
        return (
            f"Bare top-level expression at line {stmt.lineno}; "
            "only assignments, imports, and definitions are allowed at module scope"
        )
    return None


def validate(source: str | Path) -> ValidationResult:
    """
    Stage 1: AST validation of a widget source file.

    Accepts either a source-code string or a Path to a .py file.
    Returns a ValidationResult with metadata populated from the MANIFEST on success.
    """
    if isinstance(source, Path):
        try:
            code = source.read_text(encoding="utf-8")
        except OSError as exc:
            return _fail(f"Cannot read file: {exc}")
    else:
        code = source

    # ── Syntax ────────────────────────────────────────────────────────────────
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return _fail(f"SyntaxError at line {exc.lineno}: {exc.msg}")

    # ── MANIFEST docstring ─────────────────────────────────────────────────────
    first = tree.body[0] if tree.body else None
    if not (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return _fail("Module docstring (MANIFEST) is missing")

    try:
        manifest: dict = json.loads(first.value.value)
    except json.JSONDecodeError as exc:
        return _fail(f"MANIFEST docstring is not valid JSON: {exc}")

    missing = MANIFEST_REQUIRED - manifest.keys()
    if missing:
        return _fail(f"MANIFEST missing required fields: {sorted(missing)}")

    if not isinstance(manifest.get("version"), int):
        return _fail("MANIFEST 'version' must be an integer, got: " + repr(manifest.get("version")))

    # ── build() at module level ────────────────────────────────────────────────
    has_build = any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "build"
        for node in tree.body
    )
    if not has_build:
        return _fail("Module must define a top-level build() function")

    # ── Forbidden call patterns ────────────────────────────────────────────────
    hit = _first_forbidden(tree)
    if hit:
        return _fail(f"Forbidden call pattern detected: {hit!r}")

    # ── No bare top-level expressions ─────────────────────────────────────────
    err = _top_level_bare_call(tree)
    if err:
        return _fail(err)

    return ValidationResult(ok=True, metadata=manifest)


def dry_run(path: Path, *, timeout: float = 5.0) -> ValidationResult:
    """
    Stage 2: Execute build() in an isolated subprocess to catch runtime errors.

    This is a separate, optional step that supplements Stage 1 AST validation.
    """
    path = Path(path)
    module_name = path.stem
    script = (
        "import importlib.util, sys; "
        f"spec = importlib.util.spec_from_file_location({module_name!r}, {str(path)!r}); "
        "mod = importlib.util.module_from_spec(spec); "
        "spec.loader.exec_module(mod); "
        "mod.build()"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return _fail(f"Dry-run timed out after {timeout}s")
    except OSError as exc:
        return _fail(f"Dry-run process failed to start: {exc}")

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        return _fail(f"Dry-run exited {result.returncode}: {detail}")

    return ValidationResult(ok=True)
