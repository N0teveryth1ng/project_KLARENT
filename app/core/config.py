from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def default_test_database_url(self) -> str:
        """Construct a PostgreSQL URL for the test database using the
        psycopg2 driver and the credential defaults defined above.
        This is used when the test suite does not provide an explicit
        TEST_DATABASE_URL environment variable.
        """
        return (
            f"postgresql+psycopg2://{self.postgres_user}"
            f":{self.postgres_password}@localhost:5432/{self.postgres_db}"
        )

    app_name: str = "agent-reliability-lab"
    debug: bool = True
    secret_key: str = "change-me-in-production"

    # Default development DB (SQLite). Production can override via env.
    database_url: str = "sqlite:///./test.db"

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
