"""FastAPI Prometheus proxy (stub)."""
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Prometheus Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/metrics/query")
def query_metrics(
    q: str = "",
    start: str | None = None,
    end: str | None = None,
    step: str | None = None,
) -> dict[str, Any]:
    """PromQL query endpoint. Stub returns empty result."""
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [],
        },
    }


def run(host: str = "127.0.0.1", port: int = 8004) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()
