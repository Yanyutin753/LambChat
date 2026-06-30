.PHONY: help install install-pnpm dev build clean docker-up docker-down docker-logs docker-build docker-workflow-acceptance test lint format typecheck check-all pre-commit install-hooks frontend-dev frontend-build frontend-build-smoke frontend-install

# 默认目标
help:
	@echo "LambAgent - Makefile 快捷命令"
	@echo ""
	@echo "安装依赖:"
	@echo "  make install-pnpm     - 检查并安装 pnpm"
	@echo "  make install          - 安装 Python 后端依赖"
	@echo "  make frontend-install - 安装前端依赖（含 pnpm 检查）"
	@echo "  make install-all      - 安装所有依赖"
	@echo ""
	@echo "开发运行:"
	@echo "  make dev              - 启动后端开发服务器"
	@echo "  make frontend-dev     - 启动前端开发服务器"
	@echo "  make dev-all          - 同时启动前后端"
	@echo ""
	@echo "构建:"
	@echo "  make build            - 构建后端"
	@echo "  make frontend-build   - 构建前端"
	@echo "  make frontend-build-smoke - Build frontend without PWA injection"
	@echo "  make build-all        - 构建前后端"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-up        - 启动 Docker 容器"
	@echo "  make docker-down      - 停止 Docker 容器"
	@echo "  make docker-logs      - 查看 Docker 日志"
	@echo "  make docker-build     - 构建 Docker 镜像"
	@echo "  make docker-workflow-acceptance - Run live Workflow plugin acceptance"
	@echo "  make docker-restart   - 重启 Docker 容器"
	@echo ""
	@echo "代码质量:"
	@echo "  make pre-commit       - 运行所有 pre-commit hooks（ruff、prettier 等）"
	@echo "  make install-hooks    - 安装 pre-commit git hooks"
	@echo "  make lint             - 运行 Ruff 代码检查"
	@echo "  make format           - 格式化代码"
	@echo "  make typecheck        - 运行 Mypy 类型检查"
	@echo "  make test             - 运行测试"
	@echo "  make check-all        - 运行所有检查（pre-commit + typecheck + test）"
	@echo ""
	@echo "清理:"
	@echo "  make clean            - 清理缓存和临时文件"
	@echo "  make clean-all        - 深度清理（包括 node_modules, .venv）"

# 安装依赖
install-pnpm:
	@echo "📦 检查 pnpm..."
	@which pnpm > /dev/null 2>&1 || (echo "安装 pnpm..." && npm install -g pnpm)
	@echo "✅ pnpm 已就绪 ($(shell pnpm --version))"

install:
	@echo "📦 安装 Python 依赖..."
	uv sync

frontend-install: install-pnpm
	@echo "📦 安装前端依赖..."
	cd frontend && pnpm install

install-all: install frontend-install install-hooks
	@echo "✅ 所有依赖安装完成"

# 开发运行
dev:
	@echo "🚀 启动后端开发服务器..."
	uv run python main.py

frontend-dev:
	@echo "🎨 启动前端开发服务器..."
	cd frontend && pnpm run dev

dev-all:
	@echo "🚀 启动前后端开发服务器..."
	@echo "🌐 前端开发地址: http://127.0.0.1:3001"
	@echo "🌐 后端开发地址: http://127.0.0.1:8000"
	@FRONTEND_DEV_URL=http://127.0.0.1:3001 make -j2 dev frontend-dev

# 构建
build:
	@echo "🔨 构建后端..."
	uv build

frontend-build:
	@echo "🔨 构建前端..."
	cd frontend && pnpm run build

frontend-build-smoke:
	@echo "Build frontend smoke bundle without PWA injection..."
	cd frontend && pnpm run build:smoke

build-all: build frontend-build
	@echo "✅ 构建完成"

# Docker 操作
docker-up:
	@echo "🐳 启动 Docker 容器..."
	docker-compose up -d

docker-down:
	@echo "🛑 停止 Docker 容器..."
	docker-compose down

docker-logs:
	@echo "📄 Docker 日志 (Ctrl+C 退出)..."
	docker-compose logs -f

docker-build:
	@echo "🔨 构建 Docker 镜像..."
	docker-compose build

docker-workflow-acceptance:
	@echo "Run live Workflow plugin acceptance..."
	python scripts/workflow_container_acceptance.py

docker-restart: docker-down docker-up
	@echo "🔄 Docker 容器已重启"

# 代码质量
install-hooks:
	@echo "🪝 安装 pre-commit git hooks..."
	uv run pre-commit install
	@echo "✅ pre-commit hooks 已安装，每次 git commit 会自动检查"

pre-commit:
	@echo "🪝 运行所有 pre-commit hooks..."
	uv run pre-commit run --all-files

lint:
	@echo "🔍 运行代码检查..."
	uv run ruff check .

format:
	@echo "✨ 格式化代码..."
	uv run ruff format .

typecheck:
	@echo "🔬 运行 Mypy 类型检查..."
	uv run mypy src/

test:
	@echo "🧪 运行测试..."
	uv run pytest

check-all: pre-commit typecheck test
	@echo "✅ 所有检查通过"

# 清理
clean:
	@echo "🧹 清理缓存和临时文件..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.log" -delete
	rm -rf htmlcov/ .coverage dist/ build/
	@echo "✅ 清理完成"

clean-all: clean
	@echo "🧹 深度清理..."
	rm -rf .venv/
	rm -rf frontend/node_modules/
	rm -rf node_modules/
	@echo "⚠️  需要重新运行 'make install-all' 安装依赖"
