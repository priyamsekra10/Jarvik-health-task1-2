from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Database settings
    DB_CONNECTION: str
    DB_HOST: str
    DB_PORT: int
    DB_DATABASE: str
    DB_USERNAME: str
    DB_PASSWORD: str
    
    # OpenAI settings
    OPENAI_API_KEY: str
    
    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()