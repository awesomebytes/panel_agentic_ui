"""FastAPI backends for telemetry, commands, data, and Prometheus."""
from .audit import get_recent, log_action
from .commands import app as commands_app
from .data import app as data_app
from .prometheus import app as prometheus_app
from .telemetry import app as telemetry_app

__all__ = [
    "commands_app",
    "data_app",
    "prometheus_app",
    "telemetry_app",
    "log_action",
    "get_recent",
]
