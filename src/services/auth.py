from datetime import datetime, timedelta, timezone
from utils.security import create_jwt_token, decode_jwt_token
from models.schemas import VerifyEmailRequest, TokenResponse
from config import settings
from services.database import get_db
from uuid import uuid4
from jose import jwt, JWTError
from fastapi import HTTPException, status

class AuthService:
    def __init__(self):
        self.db = get_db()
        self.users = self.db["userDetails"]
        self.sessions = self.db["sessions"]
        self.jwt_secret_key = settings.jwt_secret_key
        self.jwt_algorithm = settings.jwt_algorithm

    def verify_email(self, data: VerifyEmailRequest, basic_auth_username: str):
        # Check if user exists
        user = self.users.find_one({"email": data.email})

        custHash = str(uuid4())
        
        if not user:
            # Create new user
            user_data = {
                "custHash": custHash,
                "email": data.email,
                "first_name": data.first_name,
                "last_name": data.last_name,
                "phone": data.phone,
            }
            self.users.insert_one(user_data)
        else:
            custHash = user["custHash"]
        
        # Generate tokens
        access_token = create_jwt_token(
            {"sub": data.email, "token_type": "access", "custHash": custHash},
            expires_delta=timedelta(minutes=15)
        )

        refresh_token = create_jwt_token(
            {"sub": data.email, "token_type": "refresh", "custHash": custHash},
            expires_delta=timedelta(days=30)
        )
        
        # Store session information
        session_data = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "email": data.email,
            "created_at": datetime.now(timezone.utc),
        }

        # Remove any existing sessions for the user
        self.sessions.delete_many({"email": data.email})

        # Insert new session
        self.sessions.insert_one(session_data)
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer"
        )

    def validate_token(self, token: str):
        try:
            # First, try decoding as an access token
            token_data = decode_jwt_token(token)

            if token_data["token_type"] == "access":
                session = self.sessions.find_one({"access_token": token})
                if session:
                    self.sessions.update_one(
                        {"access_token": token},
                        {"$set": {"last_used": datetime.now(timezone.utc)}}
                    )
                    return {"valid": True, "refreshed": False}

            # If access token is invalid, try using the refresh token
            session = self.sessions.find_one({"refresh_token": token})
            if session:
                new_access_token = create_jwt_token(
                    {"sub": session["email"], "token_type": "access", "custHash": token_data["custHash"]},
                    expires_delta=timedelta(minutes=15)
                )

                # Update session with new access token
                self.sessions.update_one(
                    {"refresh_token": token},
                    {"$set": {"access_token": new_access_token}}
                )

                return {"valid": True, "refreshed": True, "access_token": new_access_token}

            return {"valid": False}

        except Exception as e:
            return {"valid": False, "error": str(e)}

    def handle_token(self, token: str):
        session = self.sessions.find_one({
            "$or": [
                {"access_token": token},
                {"refresh_token": token}
            ]
        })
        
        if not session:
            return {"message": "No active session found"}
        
        # If refresh token is used, generate new access token
        if session["refresh_token"] == token:
            new_access_token = create_jwt_token(
                {"sub": session["email"], "token_type": "access"},
                expires_delta=timedelta(minutes=15)
            )
            
            self.sessions.update_one(
                {"refresh_token": token},
                {"$set": {"access_token": new_access_token}}
            )
            
            return {
                "message": "Access token refreshed",
                "access_token": new_access_token
            }
        
        # If access token is used, proceed with logout
        self.sessions.delete_one({"_id": session["_id"]})
        return {"message": "Logged out successfully"}

    def refresh_token(self, refresh_token: str) -> TokenResponse:
        try:
            # Verify the refresh token
            payload = jwt.decode(refresh_token, self.jwt_secret_key, algorithms=[self.jwt_algorithm])
            
            # Generate new tokens
            access_token = self.create_access_token(payload)
            new_refresh_token = self.create_refresh_token(payload)
            
            return TokenResponse(
                access_token=access_token,
                refresh_token=new_refresh_token
            )
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )

def get_auth_service():
    return AuthService()