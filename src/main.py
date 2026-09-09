import logging

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from middleware.auth import verify_token_middleware
from routes import health, auth, resume

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="AI CV Builder API")

# Registered first so CORSMiddleware ends up outermost and 401s still carry CORS headers.
app.middleware("http")(verify_token_middleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # cannot be True alongside a wildcard origin
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["New-Access-Token"],
)

app.include_router(health.router, tags=["health"])
app.include_router(auth.router, prefix="/auth", tags=["authentication"])
app.include_router(resume.router, prefix="/resume", tags=["resume"])

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
