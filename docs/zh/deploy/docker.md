# Docker 部署

推荐的 LambChat 生产环境部署方式。

## 快速开始

```bash
# 克隆仓库
git clone https://github.com/Yanyutin753/LambChat.git
cd LambChat

# 复制并编辑环境文件
cp deploy/.env.example .env
# 编辑 .env 填入你的配置

# 启动所有服务
docker compose -f deploy/docker-compose.yml up -d
```

## 架构

Docker Compose 启动三个服务：

| 服务 | 镜像 | 端口 | 说明 |
|------|------|------|------|
| `lambchat` | 自定义构建 | 8000 | LambChat 应用（FastAPI + 静态前端） |
| `mongo` | `mongo:7` | 27017 | MongoDB 数据库 |
| `redis` | `redis:7-alpine` | 6379 | Redis 缓存和发布/订阅 |

## 配置

### 环境变量

将 `deploy/.env.example` 复制为 `.env` 并配置：

```bash
# 必填：设置稳定的 JWT 密钥
JWT_SECRET_KEY=your-stable-secret-key

# 必填：设置你的 LLM 提供商
LLM_API_KEY=sk-your-api-key
LLM_API_BASE=https://api.openai.com/v1
LLM_MODEL=gpt-4o

# 可选：配置 MongoDB 认证
MONGODB_USERNAME=admin
MONGODB_PASSWORD=your-mongo-password

# 可选：配置 Redis 认证
REDIS_PASSWORD=your-redis-password
```

完整参考见[环境变量](/zh/env/app)。

### 反向代理

生产环境建议使用反向代理（nginx、Traefik、Caddy）并配置 SSL：

**nginx 示例：**

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

        # SSE 支持
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400s;
    }
}
```

使用反向代理时，设置 `APP_BASE_URL`：

```bash
APP_BASE_URL=https://lambchat.example.com
```

## 管理服务栈

```bash
# 启动服务
docker compose -f deploy/docker-compose.yml up -d

# 查看日志
docker compose -f deploy/docker-compose.yml logs -f lambchat

# 停止服务
docker compose -f deploy/docker-compose.yml down

# 重启应用（保留数据）
docker compose -f deploy/docker-compose.yml restart lambchat

# 代码变更后重新构建
docker compose -f deploy/docker-compose.yml up -d --build lambchat
```

## 数据持久化

Docker Compose 使用命名卷来持久化数据：

- `mongo_data` — MongoDB 数据
- `redis_data` — Redis 数据
- `uploads` — 上传的文件（本地存储模式）

这些卷在容器重启和重建时保持不变。
