from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    mongodb_uri: str
    db_name: str
    mongodb_password: str
    mongodb_username: str
    basic_auth_username: str
    basic_auth_password: str
    jwt_secret_key: str
    jwt_algorithm: str
    jwt_expire_minutes: int

    class Config:
        env_file = ".env"

settings = Settings()