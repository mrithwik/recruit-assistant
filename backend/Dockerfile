# Build context is the repo root (see docker-compose.yml) — pyproject.toml
# lives there and points setuptools at backend/ for the actual package.
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY backend/ backend/

RUN pip install --no-cache-dir -e .

WORKDIR /app/backend

# DATA_DIR/SQLITE_PATH are relative to this WORKDIR by default (see
# app/config.py) — docker-compose.yml mounts a named volume here so
# candidates/resumes/the SQLite db survive a container restart.
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
