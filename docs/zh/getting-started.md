# 快速开始

## 前置条件

- Python 3.12+
- Node.js 18+（用于前端构建）
- MongoDB
- Redis

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/Yanyutin753/LambChat.git
cd LambChat
```

### 2. 配置环境

```bash
cp .env.example .env
# 编辑 .env 填入你的配置
```

完整的环境变量参考请见[环境变量](/zh/env/app)。

### 3. 使用 Docker 运行（推荐）

```bash
docker compose -f deploy/docker-compose.yml up -d
```

详见 [Docker 部署](/zh/deploy/docker)。

### 4. 从源码运行

**后端：**

```bash
make install   # 安装 Python 依赖
make dev       # 启动后端开发服务器（端口 8000）
```

**前端：**

```bash
cd frontend
pnpm install
pnpm dev       # 启动前端开发服务器（端口 3001）
```

前端开发服务器会自动将 API 请求代理到后端。

## 技术栈

| 组件 | 技术 |
|------|------|
| 后端 | Python 3.12, FastAPI, Uvicorn |
| Agent 运行时 | LangGraph |
| 前端 | React 19, Vite 6, TypeScript, TailwindCSS |
| 数据库 | MongoDB（主数据库）, Redis（缓存/发布订阅） |
| 可选数据库 | PostgreSQL（检查点存储） |
| 对象存储 | S3 兼容（AWS、阿里云、MinIO） |
| 沙箱 | Daytona 或 E2B |
| 认证 | JWT, OAuth, bcrypt |
| 链路追踪 | LangSmith |
