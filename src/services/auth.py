from utils.security import create_jwt_token
from models.schemas import VerifyEmailRequest, TokenResponse
from config import settings
from services.database import get_db
from uuid import uuid4
from fastapi import HTTPException

class AuthService:
    def __init__(self):
        self.db = get_db()
        self.users = self.db["userDetails"]

    def verify_email(self, data: VerifyEmailRequest, basic_auth_username: str):
        # Check if user exists
        user = self.users.find_one({"email": data.email})
        
        if not user:
            # Create new user
            user_data = {
                "custHash": str(uuid4()),
                "email": data.email,
                "first_name": data.first_name,
                "last_name": data.last_name,
                "phone": data.phone,
                "userType": "standard"
            }
            self.users.insert_one(user_data)
        
        # Generate token
        return TokenResponse(
            access_token=create_jwt_token({"sub": data.email}),
            token_type="bearer"
        )

def get_auth_service():
    return AuthService()