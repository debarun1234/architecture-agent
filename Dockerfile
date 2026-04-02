# Use the official Python lightweight image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Create application directory
WORKDIR /app

# Install OS dependencies (including libpq for PostgreSQL if needed by asyncpg/psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code (we mount backend logic to root and serve frontend static files)
COPY backend/ /app/
COPY frontend/ /app/frontend/

# Ensure knowledge base JSONs are available for initial seeding if needed
COPY backend/knowledge_base/data/ /app/knowledge_base/data/

# Run the FastAPI server via Uvicorn
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port \"${PORT:-8000}\""]
