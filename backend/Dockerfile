# FastAPI backend image.
# Builds the app package and runs it with uvicorn on port 8000.
FROM python:3.11-slim

# Faster, cleaner Python in containers.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first (better layer caching). pyproject drives the deps.
COPY pyproject.toml ./
COPY app ./app
RUN pip install --upgrade pip && pip install .

EXPOSE 8000

# On startup the app creates and seeds the schema (init_db + seed_if_empty).
# Point DATABASE_URL at RDS Postgres via the environment (see docker-compose).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
