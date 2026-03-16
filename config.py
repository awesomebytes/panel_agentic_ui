"""Application configuration via environment variables."""
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All configuration via env vars with sensible defaults."""
    model_config = {"env_prefix": "MONITOR_"}

    # Panel server
    panel_address: str = "127.0.0.1"
    panel_port: int = 5006

    # FastAPI backends
    telemetry_port: int = 8001
    commands_port: int = 8002
    data_port: int = 8003
    prometheus_port: int = 8004

    # External services
    prometheus_url: str = "http://localhost:9090"

    # LLM
    llm_provider: str = "anthropic"  # "anthropic" or "openai"
    llm_model: str = "claude-sonnet-4-20250514"
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # GitHub
    github_token: str = ""
    github_repo: str = ""

    # Paths
    base_dir: Path = Path(".")
    widgets_dir: Path = Path("widgets")
    chats_dir: Path = Path("chats")
    notes_dir: Path = Path("notes")
    layout_file: Path = Path("layout.json")

    # Testing
    test_mode: bool = False

    # Cookie secret
    cookie_secret: str = ""


settings = Settings()
