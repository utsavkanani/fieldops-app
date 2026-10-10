from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    # Matches compose.yaml; override with DATABASE_URL in the environment or .env.
    database_url: str = "mysql+asyncmy://gsd:gsd@127.0.0.1:3306/gsd"


settings = Settings()
