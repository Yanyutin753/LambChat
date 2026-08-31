# Stage 1: Build frontend
# bookworm-slim（glibc）而非 alpine（musl）：字体分包依赖 cn-font-split
# 的原生 FFI（koffi + libffi），musl 下无预编译且 glibc 的 libffi 无法加载
FROM node:20-bookworm-slim AS frontend-builder

RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app/frontend

# Copy package files
# pnpm-workspace.yaml：onlyBuiltDependencies 放行 cn-font-split/koffi 的
# 安装脚本（Rust 字体切割内核），缺失会导致 pnpm run build 失败
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml frontend/.npmrc ./

# Install dependencies
RUN pnpm install --frozen-lockfile

# Copy frontend source
COPY frontend/ ./

# Build frontend
RUN pnpm run build

# Stage 2: Runtime image
FROM python:3.12-slim

WORKDIR /app

# Install uv (Node.js not needed at runtime — e2b uses remote sandboxes)
# fonts-noto-cjk: PDF cover rendering (pypdfium2) substitutes system fonts
# for PDFs that don't embed CJK fonts — without this they render as tofu.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency files
COPY pyproject.toml uv.lock* README.md ./

# Install runtime dependencies into the image. Keep uv's download cache during
# builds so repeated image builds do not re-download unchanged wheels.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

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

EXPOSE 8000

ENV UV_PROJECT_ENVIRONMENT=/app/.venv

CMD ["/app/.venv/bin/python", "main.py"]
