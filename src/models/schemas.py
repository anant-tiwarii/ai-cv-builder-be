from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    first_name: str = Field(..., min_length=1)
    last_name: str | None = None
    phone: str | None = None

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"

class ATSResponse(BaseModel):
    is_resume: bool
    score: float | None = None
    breakdown: dict[str, float] | None = None
    feedback: str | None = None
    strengths: list[str] | None = None
    weaknesses: list[str] | None = None
    suggestions: list[str] | None = None

class ResumeScore(BaseModel):
    filename: str | None = None
    timestamp: datetime | None = None
    score: float
    breakdown: dict[str, float] | None = None

class Result(BaseModel):
    custHash: str
    results: list[ResumeScore] = []
