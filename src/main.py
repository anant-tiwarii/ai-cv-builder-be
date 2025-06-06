from fastapi import FastAPI
from routes import health, auth, resume
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from middleware.auth import verify_token_middleware

app = FastAPI()

# Extremely permissive CORS setup for debugging
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins temporarily
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include your routers
app.include_router(health.router, tags=["health"])
app.include_router(auth.router, prefix="/auth", tags=["authentication"])
app.include_router(resume.router, prefix="/resume", tags=["resume"])
app.middleware("http")(verify_token_middleware)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

async def handler(request):
    return await app(request)