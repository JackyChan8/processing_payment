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


    class Config:
        """
        Конфигурация
        """

        env_file = ".env"
        env_file_encoding = "utf-8"


settings = AppSettings()
