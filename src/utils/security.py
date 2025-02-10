from datetime import datetime, timedelta
import jwt
from config import settings

def create_jwt_token(data: dict):
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    to_encode = data.copy()
    to_encode["exp"] = expire 
    return jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm
    )