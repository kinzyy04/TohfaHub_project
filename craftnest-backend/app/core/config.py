from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "CraftNest API"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    
    SECRET_KEY: str = "your-super-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/craftnest"
    TEST_DATABASE_URL: str | None = None
    JWT_SECRET: str = "your-super-secret-key-change-in-production"
    JWT_REFRESH_SECRET: str = "your-super-refresh-secret-key-change-in-production"
    ENV: str = "development"
    CORS_ORIGINS: list[str] = ["https://localhost:8443", "http://127.0.0.1:5500"]
    TRUSTED_PROXY: bool = False


    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
