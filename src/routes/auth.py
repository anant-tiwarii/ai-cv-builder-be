from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials, HTTPBearer, HTTPAuthorizationCredentials
from services.auth import AuthService, get_auth_service
from models.schemas import VerifyEmailRequest, TokenResponse
from config import settings

router = APIRouter()
security = HTTPBasic()
bearer = HTTPBearer()

def validate_basic_auth(credentials: HTTPBasicCredentials = Depends(security)):
    if (credentials.username != settings.basic_auth_username or 
        credentials.password != settings.basic_auth_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

@router.post("/verify-email", response_model=TokenResponse)
async def verify_email(
    request: VerifyEmailRequest,
    service: AuthService = Depends(get_auth_service),
    auth_user: str = Depends(validate_basic_auth)
):
    return service.verify_email(request, auth_user)

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    service: AuthService = Depends(get_auth_service)
):
    return service.refresh_token(credentials.credentials)

@router.post("/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    service: AuthService = Depends(get_auth_service)
):
    token = credentials.credentials
    result = service.handle_token(token)
    return result