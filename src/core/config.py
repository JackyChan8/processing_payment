from pydantic import SecretStr
from pydantic_settings import BaseSettings


class AppSettings(BaseSettings):
    """
    Settings Class
    """

    # Application
    APP_NAME: str
    APP_VERSION: str
    APP_SUMMARY: str
    APP_DESCRIPTION: str
    APP_SWAGGER_PATH: str

    # Security
    API_KEY: SecretStr

    # Postgres
    POSTGRES_HOST: str
    POSTGRES_PORT: int
    POSTGRES_USER: str
    POSTGRES_DB: str
    POSTGRES_PASSWORD: SecretStr

    # RabbitMQ
    RABBITMQ_HOST: str
    RABBITMQ_USER: str
    RABBITMQ_PASSWORD: SecretStr
    RABBITMQ_PORT: int
    RABBITMQ_MANAGEMENT_PORT: int

    # Workers
    CONSUMER_PREFETCH: int = 20
    CONSUMER_GRACEFUL_TIMEOUT_SECONDS: float = 30
    MAX_ATTEMPTS: int = 3
    RETRY_BASE_DELAY_SECONDS: float = 5
    PROCESSING_SECONDS: int = 60
    GATEWAY_MIN_DELAY_SECONDS: float = 2
    GATEWAY_MAX_DELAY_SECONDS: float = 5
    GATEWAY_SUCCESS_RATE: float = 0.9
    WEBHOOK_SECRET: SecretStr
    WEBHOOK_TIMEOUT_SECONDS: float = 5
    WEBHOOK_ALLOW_PRIVATE_NETWORKS: bool = False
    OUTBOX_BATCH_SIZE: int = 200
    OUTBOX_POLL_INTERVAL_SECONDS: float = 0.2
    OUTBOX_RETENTION_HOURS: int = 24
    OUTBOX_CLEANUP_INTERVAL_SECONDS: int = 300

    # Logs
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "logs"
    LOG_FILENAME: str = "app.log"
    LOG_PER_PROCESS: bool = False
    LOG_QUEUE_SIZE: int = 100000
    LOG_BACKUP_DAYS: int = 14
    LOG_CONSOLE: bool = False

    def build_postgres_url(self, protocol_db: str = "postgresql+asyncpg") -> str:
        """
        Генерирования ссылки Postgres
        """
        return (
            f"{protocol_db}://"
            f"{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD.get_secret_value()}@"
            f"{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    def build_rabbitmq_url(self) -> str:
        """
        Генерирования ссылки RabbitMQ
        """
        return (
            "amqp://"
            f"{self.RABBITMQ_USER}:{self.RABBITMQ_PASSWORD.get_secret_value()}@"
            f"{self.RABBITMQ_HOST}:{self.RABBITMQ_PORT}/"
        )

    class Config:
        """
        Конфигурация
        """

        env_file = ".env"
        env_file_encoding = "utf-8"


settings = AppSettings()
