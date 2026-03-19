# Stage 1: Build frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# Use China mirrors
RUN npm config set registry https://registry.npmmirror.com

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

# Use China Debian mirror (HTTPS)
RUN sed -i 's|http://deb.debian.org|https://mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's|http://deb.debian.org|https://mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list 2>/dev/null || true

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

# Install uv with China mirror
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip install --no-cache-dir uv

# Copy dependency files
COPY pyproject.toml uv.lock* README.md ./

# Install dependencies directly (no venv) with China mirror
ENV UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
RUN uv sync --frozen --no-dev --no-cache

# Copy source code
COPY src/ ./src/
COPY main.py ./

# Copy frontend static files
COPY --from=frontend-builder /app/frontend/dist ./static

# Create non-root user and set up cache directory
RUN groupadd -r app && useradd -r -g app app && \
    mkdir -p /home/app/.cache && \
    chown -R app:app /home/app && \
    chown -R app:app /app

# Switch to non-root user
USER app

EXPOSE 8080

CMD ["uv", "run", "python", "main.py"]
