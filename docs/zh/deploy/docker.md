# Docker 部署

Docker Compose 适合在单台主机上运行单个应用副本。多副本或分布式生产部署请使用
Kubernetes 或其他编排系统，并配置共享 MongoDB、Redis 和 S3 兼容对象存储。

## 快速开始

```bash
# 克隆仓库
git clone https://github.com/Yanyutin753/LambChat.git
cd LambChat

# 复制并编辑环境文件（Compose 从 deploy/ 目录读取 .env）
cp deploy/.env.example deploy/.env
# 编辑 deploy/.env 填入你的配置

# 启动所有服务
docker compose -f deploy/docker-compose.yml up -d
```

## 架构

Docker Compose 为单节点服务栈启动三个服务：

| 服务 | 镜像 | 端口 | 说明 |
|------|------|------|------|
| `lambchat` | `ghcr.io/yanyutin753/lambchat:latest` | 8000 | LambChat 应用（FastAPI + 静态前端） |
| `mongodb` | `mongo:8.2.5` | 127.0.0.1:27017 | MongoDB 数据库 |
| `redis` | `redis:alpine` | 127.0.0.1:6379 | Redis 缓存和发布/订阅 |

MongoDB 和 Redis 端口绑定在 `127.0.0.1`，不会暴露给其他主机访问。

## 配置

### 环境变量

将 `deploy/.env.example` 复制为 `deploy/.env`。Compose 文件会从其中读取以下变量：

```bash
# E2B 沙箱（可选）
E2B_API_KEY=your_e2b_api_key
E2B_TEMPLATE=base

# 可选调优项
LLM_MODEL_CACHE_SIZE=50
SESSION_MAX_EVENTS_PER_TRACE=10000
```

`REDIS_URL` 和 `MONGODB_URL` 已预设为服务栈内的 Redis 和 MongoDB 服务。其他环境变量（如 `JWT_SECRET_KEY`——稳定的 JWT 密钥，不设置则每次重启自动生成，导致已登录用户失效；`MCP_ENCRYPTION_SALT`——稳定的 MCP 加密盐值，不设置则每次重启自动生成，导致已保存的 MCP 配置失效）默认未接线——需要在 `deploy/docker-compose.yml` 的 `lambchat` 服务 `environment` 段中添加：

```yaml
    environment:
      # 推荐：保持登录会话在重启后仍然有效
      - JWT_SECRET_KEY=your-stable-secret-key
      # 推荐：保持已保存 MCP 配置在重启后仍可解密
      - MCP_ENCRYPTION_SALT=your-stable-encryption-salt
```

::: tip
LLM 模型通过部署后的 **模型配置 UI** 添加，无需在环境变量中配置。详见[模型配置](/zh/env/llm)。
:::

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

请求内生成的文件 URL 会自动跟随访问入口（`X-Forwarded-Host`/`Host` + `X-Forwarded-Proto`），多域名入口部署无需额外配置。`APP_BASE_URL` 仅在无请求上下文时兜底，**后台任务生成文件 URL 的场景（定时任务附件、消息拦截落盘等）建议配置**：

```bash
APP_BASE_URL=https://lambchat.example.com
```

> **升级说明（连接类配置迁移 env）**：数据库连接（`MONGODB_*`/`POSTGRES_*`/`REDIS_*`/`CHECKPOINT_PG_*`）、对象存储（`S3_*`）与 `ENABLE_POSTGRES_STORAGE` 等连接类配置现在**启动时以环境变量为唯一权威**——此前通过设置面板修改过这些配置的部署，升级后需将面板值迁移到 env/compose 并重启，否则启动日志会出现 `env-authoritative` 告警且面板值不生效。设置面板中的行为类配置（超时、开关等）不受影响。

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

# 更新到最新发布的镜像
docker compose -f deploy/docker-compose.yml pull lambchat
docker compose -f deploy/docker-compose.yml up -d lambchat
```

## 数据持久化

Docker Compose 使用命名卷和绑定挂载来持久化数据：

- `mongodb-data` — MongoDB 数据
- `redis-data` — Redis 数据
- `lamb-data` — LambChat 应用数据（`/app/data`）
- `./workspace` — Agent 工作区（绑定挂载，解析到 `deploy/` 下）
- `./uploads` — 本地存储模式下的上传文件（绑定挂载，解析到 `deploy/` 下）

这些卷在容器重启和重建时保持不变。

使用本地 `uploads` 卷时，不要把 `lambchat` Compose 服务扩展为多个副本。多副本
部署需要共享对象存储（`S3_ENABLED=true`），并使用不会冲突固定容器名和主机端口的
负载均衡服务。
