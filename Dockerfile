# Stage 1: Build frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# Copy package files
COPY frontend/package*.json ./

# Install dependencies
RUN npm ci --prefer-offline --no-audit

# Copy frontend source
COPY frontend/ ./

# Build frontend
RUN npm run build

# Stage 2: Runtime image
FROM python:3.12-slim

WORKDIR /app

# Install Node.js 20.x and build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    libffi-dev \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends \
    nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency files
COPY pyproject.toml uv.lock README.md ./

# Tell uv to put the venv outside /app (avoids permission issues)
ENV UV_PROJECT_ENVIRONMENT=/opt/app-venv

# Install dependencies (skip project itself and dev deps)
RUN uv sync --frozen --no-dev --no-install-project

# Copy source code
COPY src/ ./src/
COPY main.py ./

# Copy frontend static files
COPY --from=frontend-builder /app/frontend/dist ./static

# Create non-root user
RUN groupadd -r app && useradd -r -g app app && \
    mkdir -p /home/app/.cache && \
    chown -R app:app /home/app /opt/app-venv

# Switch to non-root user
USER app

ENV PATH="/opt/app-venv/bin:$PATH"

EXPOSE 8080

CMD ["python", "main.py"]
