from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "CraftNest API"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    
    SECRET_KEY: str = "your-super-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    DATABASE_URL: str = "sqlite+aiosqlite:///./craftnest.db"
    TEST_DATABASE_URL: str = "sqlite+aiosqlite:///./test_craftnest.db"
    JWT_SECRET: str = "your-super-secret-key-change-in-production"
    JWT_REFRESH_SECRET: str = "your-super-refresh-secret-key-change-in-production"
    ENV: str = "development"
    CORS_ORIGINS: list[str] = [
        "https://localhost:8443",
        "http://127.0.0.1:5500",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://localhost:5173"
    ]
    TRUSTED_PROXY: bool = False


    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
