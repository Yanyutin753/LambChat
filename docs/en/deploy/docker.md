# Docker Deployment

The recommended way to deploy LambChat in production.

## Quick Start

```bash
# Clone the repository
git clone https://github.com/Yanyutin753/LambChat.git
cd LambChat

# Copy and edit environment file
cp deploy/.env.example .env
# Edit .env with your configuration

# Start all services
docker compose -f deploy/docker-compose.yml up -d
```

## Architecture

Docker Compose starts three services:

| Service | Image | Port | Description |
|---------|-------|------|-------------|
| `lambchat` | Custom build | 8000 | LambChat application (FastAPI + static frontend) |
| `mongo` | `mongo:7` | 27017 | MongoDB database |
| `redis` | `redis:7-alpine` | 6379 | Redis cache & pub/sub |

## Configuration

### Environment Variables

Copy `deploy/.env.example` to `.env` and configure:

```bash
# Required: Set a stable JWT secret
JWT_SECRET_KEY=your-stable-secret-key

# Required: Set your LLM provider
LLM_API_KEY=sk-your-api-key
LLM_API_BASE=https://api.openai.com/v1
LLM_MODEL=gpt-4o

# Optional: Configure MongoDB auth
MONGODB_USERNAME=admin
MONGODB_PASSWORD=your-mongo-password

# Optional: Configure Redis auth
REDIS_PASSWORD=your-redis-password
```

See [Environment Variables](/en/env/app) for the complete reference.

### Reverse Proxy

For production, use a reverse proxy (nginx, Traefik, Caddy) with SSL:

**nginx example:**

```nginx
server {
    listen 443 ssl http2;
    server_name lambchat.example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE support
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400s;
    }
}
```

When using a reverse proxy, set `APP_BASE_URL`:

```bash
APP_BASE_URL=https://lambchat.example.com
```

## Managing the Stack

```bash
# Start services
docker compose -f deploy/docker-compose.yml up -d

# View logs
docker compose -f deploy/docker-compose.yml logs -f lambchat

# Stop services
docker compose -f deploy/docker-compose.yml down

# Restart application (preserves data)
docker compose -f deploy/docker-compose.yml restart lambchat

# Rebuild after code changes
docker compose -f deploy/docker-compose.yml up -d --build lambchat
```

## Data Persistence

Docker Compose uses named volumes for data persistence:

- `mongo_data` — MongoDB data
- `redis_data` — Redis data
- `uploads` — Uploaded files (local storage mode)

These volumes persist across container restarts and recreations.
