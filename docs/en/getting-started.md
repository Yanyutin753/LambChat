# Getting Started

## Prerequisites

- Python 3.12+
- Node.js 18+ (for frontend build)
- MongoDB
- Redis

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/Yanyutin753/LambChat.git
cd LambChat
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your configuration
```

See [Environment Variables](/en/env/app) for a complete reference.

### 3. Run with Docker (Recommended)

```bash
docker compose -f deploy/docker-compose.yml up -d
```

See [Docker Deployment](/en/deploy/docker) for details.

### 4. Run from source

**Backend:**

```bash
make install   # Install Python dependencies
make dev       # Start backend dev server on port 8000
```

**Frontend:**

```bash
cd frontend
pnpm install
pnpm dev       # Start frontend dev server on port 3001
```

The frontend dev server proxies API requests to the backend automatically.

## Architecture

```
LambChat
├── src/               # Python backend (FastAPI)
│   ├── agents/        # Agent implementations
│   ├── api/           # API routes
│   ├── infra/         # Core services (auth, LLM, MCP, storage)
│   ├── kernel/        # Schemas, config, constants
│   └── skills/        # Built-in skills
├── frontend/          # React frontend (Vite)
│   └── src/
│       ├── components/
│       ├── hooks/
│       ├── services/
│       └── i18n/      # Internationalization
├── deploy/            # Docker deployment configs
├── k8s/               # Kubernetes manifests
└── docs/              # Documentation (VitePress)
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.12, FastAPI, Uvicorn |
| Agent Runtime | LangGraph |
| Frontend | React 19, Vite 6, TypeScript, TailwindCSS |
| Database | MongoDB (primary), Redis (cache/pubsub) |
| Optional DB | PostgreSQL (checkpoint store) |
| Object Storage | S3-compatible (AWS, Aliyun, MinIO) |
| Sandbox | Daytona or E2B |
| Auth | JWT, OAuth, bcrypt |
| Tracing | LangSmith |
