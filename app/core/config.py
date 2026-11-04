from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    
    app_name: str = "agent-reliability-lab"
    debug: bool = False
    secret_key: str = "change-me-in-production"
    
    database_url: str = "postgresql://postgres:postgres@localhost:5432/agent_reliability_lab"
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "agent_reliability_lab"
    
    redis_url: str = "redis://localhost:6379/0"
    
    browser_headless: bool = True
    browser_timeout: int = 30000
    
    max_retries: int = 3
    retry_backoff_base: int = 2
    
    artifacts_dir: str = "./artifacts"


settings = Settings()
