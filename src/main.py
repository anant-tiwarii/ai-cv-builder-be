from fastapi import FastAPI
from routes import health, auth  # Keep absolute imports if you fixed the package structure
from config import settings
import uvicorn

app = FastAPI()

# Fix the tags parameter (remove quotes around brackets)
app.include_router(health.router, tags=["health"])
app.include_router(auth.router, prefix="/auth", tags=["authentication"])

# For local development, add this block
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3000)

# For DigitalOcean Cloud Functions
def handler(request):
    return app(request)