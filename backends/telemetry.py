"""FastAPI telemetry backend — CPU, memory, disk, network via psutil."""
import time
from typing import Any

import psutil
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Telemetry Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/telemetry/cpu")
def get_cpu() -> dict[str, Any]:
    """Return CPU usage per core and system load average."""
    cores: list[float] = psutil.cpu_percent(percpu=True)
    try:
        load: list[float] = list(psutil.getloadavg())
    except OSError:
        load = [0.0, 0.0, 0.0]  # Windows or unsupported
    return {
        "cores": cores,
        "load": load,
        "ts": time.time(),
    }


@app.get("/telemetry/memory")
def get_memory() -> dict[str, Any]:
    """Return virtual memory stats."""
    mem = psutil.virtual_memory()
    return {
        "total": mem.total,
        "used": mem.used,
        "percent": mem.percent,
    }


@app.get("/telemetry/disk")
def get_disk() -> dict[str, Any]:
    """Return disk usage for root filesystem."""
    usage = psutil.disk_usage("/")
    return {
        "total": usage.total,
        "used": usage.used,
        "percent": usage.percent,
    }


@app.get("/telemetry/network")
def get_network() -> dict[str, Any]:
    """Return network I/O counters."""
    io = psutil.net_io_counters()
    if io is None:
        return {"bytes_sent": 0, "bytes_recv": 0}
    return {
        "bytes_sent": io.bytes_sent,
        "bytes_recv": io.bytes_recv,
    }


def run(host: str = "127.0.0.1", port: int = 8001) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()
