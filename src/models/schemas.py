from pydantic import BaseModel, EmailStr, Field
from typing import Optional

class VerifyEmailRequest(BaseModel):
    email: EmailStr
    first_name: str = Field(..., min_length=1)
    last_name: str | None = None
    phone: str | None = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class ATSResponse(BaseModel):
    is_resume: bool
    score: float | None= None
    feedback: str | None= None
    strengths: list[str] | None= None
    weaknesses: list[str] | None= None
    suggestions: list[str] | None= None

class Result(BaseModel):
    custHash: str
    result: dict[str, dict[str, float]]