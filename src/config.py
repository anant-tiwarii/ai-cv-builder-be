from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_name: str
    mongodb_password: str
    mongodb_username: str
    mongodb_host: str = "ai-cv-db.audhy.mongodb.net"
    basic_auth_username: str
    basic_auth_password: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 15
    gemini_apikey: str
    gemini_model: str = "gemini-3.6-flash"

    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()
