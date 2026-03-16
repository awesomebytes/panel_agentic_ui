"""SQLite audit log — log_action, get_recent, and a FastAPI endpoint."""
import json
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

try:
    import aiosqlite

    HAS_AIOSQLITE = True
except ImportError:
    HAS_AIOSQLITE = False

_DB_PATH = Path(__file__).resolve().parent / "audit.db"
_INITIALIZED = False


def _ensure_schema_sync(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            action TEXT NOT NULL,
            user TEXT NOT NULL,
            details TEXT NOT NULL
        )
        """
    )
    conn.commit()


def _ensure_schema() -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return
    with sqlite3.connect(_DB_PATH) as conn:
        _ensure_schema_sync(conn)
    _INITIALIZED = True


def log_action(action: str, user: str, details: dict[str, Any]) -> None:
    """Store audit entry to SQLite."""
    import time

    _ensure_schema()
    ts = time.time()
    details_json = json.dumps(details)
    with sqlite3.connect(_DB_PATH) as conn:
        conn.execute(
            "INSERT INTO audit_log (ts, action, user, details) VALUES (?, ?, ?, ?)",
            (ts, action, user, details_json),
        )
        conn.commit()


def get_recent(limit: int = 100) -> list[dict[str, Any]]:
    """Return recent audit entries, newest first."""
    _ensure_schema()
    with sqlite3.connect(_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT ts, action, user, details
            FROM audit_log
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
    return [
        {
            "ts": row["ts"],
            "action": row["action"],
            "user": row["user"],
            "details": json.loads(row["details"]),
        }
        for row in rows
    ]


async def log_action_async(action: str, user: str, details: dict[str, Any]) -> None:
    """Async variant using aiosqlite if available."""
    import time

    if not HAS_AIOSQLITE:
        log_action(action, user, details)
        return
    _ensure_schema()
    ts = time.time()
    details_json = json.dumps(details)
    async with aiosqlite.connect(_DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO audit_log (ts, action, user, details) VALUES (?, ?, ?, ?)",
            (ts, action, user, details_json),
        )
        await conn.commit()


async def get_recent_async(limit: int = 100) -> list[dict[str, Any]]:
    """Async variant using aiosqlite if available."""
    if not HAS_AIOSQLITE:
        return get_recent(limit)
    _ensure_schema()
    async with aiosqlite.connect(_DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """
            SELECT ts, action, user, details
            FROM audit_log
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
    return [
        {
            "ts": row["ts"],
            "action": row["action"],
            "user": row["user"],
            "details": json.loads(row["details"]),
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# FastAPI app — GET /audit/recent?limit=50
# ---------------------------------------------------------------------------

app = FastAPI(title="Audit Log Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/audit/recent")
async def get_recent_endpoint(
    limit: int = Query(default=50, ge=1, le=1000),
) -> list[dict[str, Any]]:
    """Return the *limit* most recent audit log entries, newest first."""
    return await get_recent_async(limit)


def run(host: str = "127.0.0.1", port: int = 8005) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()
