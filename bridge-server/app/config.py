from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    paytmmoney_api_key: str
    paytmmoney_api_secret: str
    paytmmoney_access_token: str = ""
    paytmmoney_mode: Literal["live", "mock"] = "live"

    indmoney_access_token: str = ""
    indmoney_mode: Literal["live", "mock"] = "mock"

    # INDstocks REST token automation (scripts/indmoney_login.py). client_id
    # is the static x-api-key shown after TOTP setup at indstocks.com/app/
    # api-trading/access-tokens; totp_setup_key is the TOTP shared secret
    # (shown once, at enrollment) used to compute a valid code locally,
    # exactly like an authenticator app — not the OTP itself, no interactive
    # SMS/app step needed. Deliberately NOT storing the account MPIN here:
    # /generate/token also requires it, but that's a real trading-account
    # credential (unlike this derived, revocable TOTP secret), so the login
    # script prompts for it interactively each run instead — see
    # docs/tasks/indmoney-totp-login.md for the tradeoff this was weighed
    # against (planning-phase2.md §9's "no storing broker login credentials").
    indmoney_client_id: str = ""
    indmoney_totp_setup_key: str = ""

    refresh_interval_minutes: int = 20
    fx_manual_rate: float | None = None

    @field_validator("fx_manual_rate", mode="before")
    @classmethod
    def blank_to_none(cls, v):
        return None if v == "" else v

    database_path: str = "vantage.db"
    cors_origin: str = "http://localhost:5173"

    # Task 28d — WAL + busy_timeout is SQLite's own documented mechanism for
    # concurrent readers/writers (a scheduled job and a live panel session
    # both touching the DB at once); see docs/tasks/28d-concurrency-wal.md.
    sqlite_busy_timeout_ms: int = 5000

    # Task 27 — daily digest email. Blank smtp_host disables sending (the
    # scheduled job still runs, logs a clear "SMTP not configured" failure,
    # and exercises the dead-man's-switch path) rather than crashing the
    # scheduler on a fresh checkout with no mail setup yet.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    digest_from_email: str = ""
    digest_recipient_email: str = ""
    digest_send_hour: int = 7
    digest_send_minute: int = 0

    # Task 28a — one-shot Claude Code runner. Bare "claude" resolves via PATH
    # for local dev; overridable in case bridge-server is ever launched as a
    # service with a different PATH than an interactive shell's.
    claude_cli_path: str = "claude"

    # Task 28b — where the agent's own --mcp-config points to reach task 26's
    # Vantage MCP server (always this same process, just needs its own port).
    bridge_server_port: int = 8000


settings = Settings()
