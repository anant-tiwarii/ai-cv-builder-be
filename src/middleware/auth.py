import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from services.auth import get_auth_service

PUBLIC_PATHS = {
    "/",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/auth/verify-email",
    "/auth/refresh",
}


async def verify_token_middleware(request: Request, call_next):
    if request.method == "OPTIONS" or request.url.path in PUBLIC_PATHS:
        return await call_next(request)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"detail": "Missing or invalid token"})

    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return JSONResponse(status_code=401, content={"detail": "Missing or invalid token"})

    try:
        validation_result = get_auth_service().validate_token(token)
    except Exception:
        logging.exception("Token validation failed")
        return JSONResponse(status_code=503, content={"detail": "Auth backend unavailable"})

    if not validation_result["valid"]:
        return JSONResponse(status_code=401, content={"detail": "Invalid or expired session"})

    response = await call_next(request)

    if validation_result.get("refreshed"):
        response.headers["New-Access-Token"] = validation_result["access_token"]
        response.headers["Access-Control-Expose-Headers"] = "New-Access-Token"

    return response
