# Dockerfile
FROM python:3.10-slim

# 1) Set working dir
WORKDIR /app

# 2) Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3) Copy all of src/ into /app/
COPY src/ .

# 4) (Optional) copy any other root‑level files if you need them
#    (e.g. README.md, fly.toml—though not strictly required at runtime)

# 5) Expose port
EXPOSE 8000

# 6) Run the app. Now `/app/main.py` and `/app/routes/health.py` exist.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
