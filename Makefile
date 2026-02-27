.PHONY: help install dev build clean docker-up docker-down docker-logs docker-build test lint format check-all frontend-dev frontend-build frontend-install

# 默认目标
help:
	@echo "LambAgent - Makefile 快捷命令"
	@echo ""
	@echo "安装依赖:"
	@echo "  make install          - 安装 Python 后端依赖"
	@echo "  make frontend-install - 安装前端依赖"
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
	@echo "  make build-all        - 构建前后端"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-up        - 启动 Docker 容器"
	@echo "  make docker-down      - 停止 Docker 容器"
	@echo "  make docker-logs      - 查看 Docker 日志"
	@echo "  make docker-build     - 构建 Docker 镜像"
	@echo "  make docker-restart   - 重启 Docker 容器"
	@echo ""
	@echo "代码质量:"
	@echo "  make lint             - 运行 Ruff 代码检查"
	@echo "  make format           - 格式化代码"
	@echo "  make test             - 运行测试"
	@echo "  make check-all        - 运行所有检查（lint + test）"
	@echo ""
	@echo "清理:"
	@echo "  make clean            - 清理缓存和临时文件"
	@echo "  make clean-all        - 深度清理（包括 node_modules, .venv）"

# 安装依赖
install:
	@echo "📦 安装 Python 依赖..."
	uv sync

frontend-install:
	@echo "📦 安装前端依赖..."
	cd frontend && npm install

install-all: install frontend-install
	@echo "✅ 所有依赖安装完成"

# 开发运行
dev:
	@echo "🚀 启动后端开发服务器..."
	python main.py

frontend-dev:
	@echo "🎨 启动前端开发服务器..."
	cd frontend && npm run dev

dev-all:
	@echo "🚀 启动前后端开发服务器..."
	@make -j2 dev frontend-dev

# 构建
build:
	@echo "🔨 构建后端..."
	uv build

frontend-build:
	@echo "🔨 构建前端..."
	cd frontend && npm run build

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

docker-restart: docker-down docker-up
	@echo "🔄 Docker 容器已重启"

# 代码质量
lint:
	@echo "🔍 运行代码检查..."
	uv run ruff check .

format:
	@echo "✨ 格式化代码..."
	uv run ruff format .

test:
	@echo "🧪 运行测试..."
	uv run pytest

check-all: lint test
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
