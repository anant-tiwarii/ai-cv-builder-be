from datetime import datetime, timedelta, timezone
from utils.security import create_jwt_token, decode_jwt_token
from models.schemas import VerifyEmailRequest, TokenResponse
from services.database import get_db
from uuid import uuid4
from fastapi import HTTPException

ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_TTL = timedelta(days=30)


class AuthService:
    def __init__(self):
        self.db = get_db()
        self.users = self.db["userDetails"]
        self.sessions = self.db["sessions"]

    def _issue_tokens(self, email: str, custHash: str) -> TokenResponse:
        access_token = create_jwt_token(
            {"sub": email, "token_type": "access", "custHash": custHash},
            expires_delta=ACCESS_TOKEN_TTL,
        )
        refresh_token = create_jwt_token(
            {"sub": email, "token_type": "refresh", "custHash": custHash},
            expires_delta=REFRESH_TOKEN_TTL,
        )

        self.sessions.delete_many({"email": email})
        self.sessions.insert_one({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "email": email,
            "custHash": custHash,
            "created_at": datetime.now(timezone.utc),
        })

        return TokenResponse(access_token=access_token, refresh_token=refresh_token)

    def verify_email(self, data: VerifyEmailRequest, basic_auth_username: str):
        user = self.users.find_one({"email": data.email})

        if user:
            custHash = user["custHash"]
        else:
            custHash = str(uuid4())
            self.users.insert_one({
                "custHash": custHash,
                "email": data.email,
                "first_name": data.first_name,
                "last_name": data.last_name,
                "phone": data.phone,
            })

        return self._issue_tokens(data.email, custHash)

    def validate_token(self, token: str):
        try:
            token_data = decode_jwt_token(token)

            if token_data.get("token_type") == "access":
                session = self.sessions.find_one({"access_token": token})
                if session:
                    self.sessions.update_one(
                        {"access_token": token},
                        {"$set": {"last_used": datetime.now(timezone.utc)}}
                    )
                    return {"valid": True, "refreshed": False}

            session = self.sessions.find_one({"refresh_token": token})
            if session:
                new_access_token = create_jwt_token(
                    {
                        "sub": session["email"],
                        "token_type": "access",
                        "custHash": token_data["custHash"],
                    },
                    expires_delta=ACCESS_TOKEN_TTL,
                )

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

        if session["refresh_token"] == token:
            new_access_token = create_jwt_token(
                {
                    "sub": session["email"],
                    "token_type": "access",
                    "custHash": session["custHash"],
                },
                expires_delta=ACCESS_TOKEN_TTL,
            )

            self.sessions.update_one(
                {"refresh_token": token},
                {"$set": {"access_token": new_access_token}}
            )

            return {
                "message": "Access token refreshed",
                "access_token": new_access_token
            }

        self.sessions.delete_one({"_id": session["_id"]})
        return {"message": "Logged out successfully"}

    def refresh_token(self, refresh_token: str) -> TokenResponse:
        payload = decode_jwt_token(refresh_token)
        if payload.get("token_type") != "refresh":
            raise HTTPException(status_code=401, detail="Not a refresh token")
        if not self.sessions.find_one({"refresh_token": refresh_token}):
            raise HTTPException(status_code=401, detail="Session no longer active")
        return self._issue_tokens(payload["sub"], payload["custHash"])


def get_auth_service():
    return AuthService()
