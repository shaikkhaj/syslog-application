"""Application settings loaded from environment variables / .env files."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration object.

    Values resolve in the standard pydantic-settings order: environment
    variables first, then the optional ``.env`` file, then defaults.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Application -----------------------------------------------------
    app_name: str = "Network Syslog Monitoring & Incident Correlation Platform"
    app_version: str = "0.1.0"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # PostgreSQL ------------------------------------------------------
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "syslog_user"
    postgres_password: str = "syslog_password"
    postgres_db: str = "syslog_db"
    # Optional full SQLAlchemy URL; when set it wins over POSTGRES_* values.
    database_url: str = ""

    # Redis -----------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"

    # Syslog listeners -------------------------------------------------
    syslog_listeners_enabled: bool = True
    syslog_udp_host: str = "0.0.0.0"
    syslog_udp_port: int = 514
    syslog_tcp_host: str = "0.0.0.0"
    syslog_tcp_port: int = 514
    # TLS transport (port 6514) is registered in a later phase.
    syslog_tls_enabled: bool = False
    syslog_tls_port: int = 6514
    syslog_queue_maxsize: int = 10_000
    syslog_max_message_bytes: int = 65_536
    syslog_worker_count: int = 4

    # Detection engine (Phase 2) ----------------------------------------
    detection_enabled: bool = True
    link_flap_window_seconds: int = 300
    link_flap_threshold: int = 4
    auth_failure_window_seconds: int = 300
    auth_failure_threshold: int = 5
    cpu_high_threshold_percent: int = 90
    memory_high_threshold_percent: int = 90

    # Correlation engine (Phase 3) ---------------------------------------
    correlation_enabled: bool = True
    correlation_window_seconds: int = 300
    correlation_min_match_score: float = 3.0
    correlation_weight_same_key: float = 5.0
    correlation_weight_same_device_interface: float = 4.0
    correlation_weight_same_device_event_type: float = 3.5
    correlation_weight_same_device_subsystem: float = 3.0
    correlation_weight_causal_chain: float = 3.0
    correlation_weight_shared_endpoint: float = 3.5
    correlation_weight_cross_device_same_type: float = 2.0
    correlation_critical_device_keywords: str = (
        "core,edge,aggregation,gateway,firewall,router,rtr"
    )
    correlation_score_alert_weight: float = 3.0
    correlation_score_severity_weight: float = 10.0
    correlation_score_frequency_weight: float = 4.0
    correlation_score_device_importance_weight: float = 15.0
    correlation_score_event_type_weight: float = 8.0
    correlation_score_duration_weight: float = 0.2

    def build_database_url(self) -> str:
        """Return the SQLAlchemy connection URL for PostgreSQL/SQLite."""
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a process-wide cached settings instance."""
    return Settings()
