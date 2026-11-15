from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", extra="ignore", env_file_encoding="utf-8"
    )
    database_url: str = ""
    jwt_secret: str = ""
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = ""
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    model_threads: int = 2
    worker_poll_seconds: float = 2
    job_lease_seconds: int = 180
    inference_concurrency: int = 1
    storage_dir: Path = ROOT / "runtime"
    models_dir: Path = ROOT / "models"
    token_hours: int = 8
    max_upload_mb: int = 16

    def check_secrets(self):
        if len(self.jwt_secret) < 32 or "CHANGE_ME" in self.jwt_secret:
            raise RuntimeError(
                "请先运行 scripts/setup.ps1 生成本地密钥，然后配置 .env。"
            )
        if not self.database_url or "CHANGE_ME" in self.database_url:
            raise RuntimeError("请先在 .env 中填写 DATABASE_URL（MySQL开发库连接）。")


@lru_cache
def get_settings():
    return Settings()
