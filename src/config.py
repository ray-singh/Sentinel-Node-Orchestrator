"""Configuration settings for Sentinel Node Orchestrator."""

from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Redis settings
    redis_url: str = "redis://localhost:6379"
    redis_max_connections: int = 50
    checkpoint_ttl_days: int = 7
    
    # Worker settings
    worker_id: str = "worker-0"
    worker_heartbeat_interval: int = 10  # seconds
    lease_duration: int = 300  # seconds
    max_task_attempts: int = 3
    
    # Rate limiting
    default_rate_limit: float = 100.0  # tokens
    rate_limit_refill_rate: float = 10.0  # tokens per second
    
    # Cost tracking
    default_cost_limit: float = 10.0  # USD per task
    
    # LLM settings
    openai_api_key: str = ""
    default_llm_model: str = "gpt-4o-mini"
    
    # Monitoring
    log_level: str = "INFO"
    enable_metrics: bool = True
    prometheus_port: int = 8001

    # Checkpoint encryption
    checkpoint_encryption_key: Optional[str] = None  # base64 urlsafe key for Fernet
    sensitive_checkpoint_fields: list[str] = ["task_params", "agent_state", "artifact_refs"]
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra fields from .env


# Global settings instance
settings = Settings()
