"""FastAPI data backend — historical queries (stub)."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Data Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/history/{metric}")
def get_history(metric: str, window: str = "60s") -> list:
    """Return historical data for metric. Stub returns empty list."""
    return []


def run(host: str = "127.0.0.1", port: int = 8003) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()
