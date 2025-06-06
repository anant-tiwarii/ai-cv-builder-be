from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from services.auth import get_auth_service

async def verify_token_middleware(request: Request, call_next):
    # Skip verification for non-protected routes
    if request.method == "OPTIONS" or request.url.path in ['/auth/verify-email', '/health']:
        return await call_next(request)

    try:
        # Extract token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            raise HTTPException(status_code=401, detail="Missing or invalid token")
        
        token = auth_header.split(' ')[1]
        
        # Validate token
        auth_service = get_auth_service()
        validation_result = auth_service.validate_token(token)

        if not validation_result["valid"]:
            raise HTTPException(status_code=401, detail="Invalid or expired session")

        response = await call_next(request)

        # If token was refreshed, add new tokens to response
        if validation_result["refreshed"]:
            response.headers["New-Access-Token"] = validation_result["access_token"]

        return response
        
    except HTTPException as e:
        return JSONResponse(
            status_code=e.status_code,
            content={"detail": str(e.detail)}
        )