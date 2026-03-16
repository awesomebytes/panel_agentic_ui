"""FastAPI commands backend — allowlisted teleoperation actions."""
import time
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Commands Backend")

ALLOWED_ACTIONS = frozenset({"set_speed", "set_param", "estop", "resume", "go_home"})

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CommandBody(BaseModel):
    """Optional JSON body for command parameters."""

    params: dict[str, Any] = {}


@app.post("/command/{action}")
def post_command(action: str, body: CommandBody | None = None) -> dict[str, Any]:
    """Execute allowlisted command. Non-allowlisted actions return 403."""
    if action not in ALLOWED_ACTIONS:
        raise HTTPException(status_code=403, detail="Action not allowed")
    return {
        "status": "ok",
        "action": action,
        "ts": time.time(),
    }


def run(host: str = "127.0.0.1", port: int = 8002) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()
