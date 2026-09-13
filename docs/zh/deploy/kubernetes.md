# Kubernetes 部署

使用提供的清单将 LambChat 部署到 Kubernetes 集群。该清单面向多副本应用
Pod，要求使用外部或托管的 MongoDB、Redis 和 S3 兼容对象存储。

## 快速开始

```bash
# 应用所有资源
kubectl apply -f k8s/lambchat.yaml

# 检查部署状态
kubectl get pods -n lambchat
kubectl get svc -n lambchat
```

::: tip
清单会从 `lambchat-secrets` Secret 读取敏感值（JWT 密钥、MCP 加密盐、数据库凭据、S3 密钥）。请将 `k8s/lambchat-secret.yaml.example` 复制为 `k8s/lambchat-secret.yaml`，填入你的值并 apply——Secret 不存在时 Pod 无法启动。
:::

## 架构

K8s 清单（`k8s/lambchat.yaml`）创建以下资源：

| 资源 | 名称 | 说明 |
|------|------|------|
| 命名空间 | `lambchat` | 所有资源的隔离命名空间 |
| Deployment | `lambchat` | LambChat API/Web Pod，每个 Pod 内嵌一个 arq worker |
| Service | `lambchat` | 应用服务 |

生产扩容时，请将 MongoDB 和 Redis 部署为托管服务或独立的高可用工作负载。
多副本部署不要使用每个 Pod 各自的本地上传目录；应配置 S3 兼容对象存储。

## 配置

### 环境变量

编辑 `k8s/lambchat.yaml` 中的 `lambchat` Deployment 设置环境变量：

```yaml
env:
  - name: JWT_SECRET_KEY
    value: "your-stable-secret-key"
  - name: MONGODB_URL
    value: "mongodb://mongo.example.internal:27017"
  - name: REDIS_URL
    value: "redis://redis.example.internal:6379/0"
  - name: LAMBCHAT_DISTRIBUTED_MODE
    value: "true"
  - name: TASK_BACKEND
    value: "arq"
  - name: ARQ_EMBEDDED_WORKER
    value: "true"
  - name: S3_ENABLED
    value: "true"
  - name: ENABLE_LOCAL_FILESYSTEM_FALLBACK
    value: "false"
  - name: APP_BASE_URL
    value: "https://lambchat.example.com"
```

对于敏感值，使用 Kubernetes Secrets：

```yaml
env:
  - name: JWT_SECRET_KEY
    valueFrom:
      secretKeyRef:
        name: lambchat-secrets
        key: jwt-secret-key
```

### Ingress

默认清单暴露 Kubernetes Service。对外发布应用时，请按你的 Ingress 控制器添加
Ingress：

**nginx Ingress 示例：**

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: lambchat-ingress
  namespace: lambchat
  annotations:
    nginx.ingress.kubernetes.io/proxy-buffering: "off"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "86400"
spec:
  tls:
    - hosts:
        - lambchat.example.com
      secretName: lambchat-tls
  rules:
    - host: lambchat.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: lambchat
                port:
                  number: 80
```

## 扩缩容

```bash
# 扩展对称 API/Web + 内嵌 arq worker Pod
kubectl scale deployment lambchat --replicas=3 -n lambchat
```

多副本部署需要共享后端服务：

- MongoDB：持久化应用数据。
- Redis：发布/订阅、WebSocket 路由、任务队列、分布式锁和缓存。
- S3 兼容对象存储：上传文件和生成产物。
- 稳定共享密钥，例如 `JWT_SECRET_KEY` 和 `MCP_ENCRYPTION_SALT`。

多副本部署应设置 `LAMBCHAT_DISTRIBUTED_MODE=true`。在该模式下，如果 API 或
worker 进程检测到随机生成的运行时密钥，或检测到本地上传存储配置，会在启动时
直接失败，避免副本间状态不一致。

默认清单使用对称应用 Pod：每个 `lambchat` Pod 同时处理 HTTP/WebSocket 请求，
并运行一个内嵌 arq worker。arq job、payload、取消信号和并发槽位都通过
Redis/MongoDB 协调，因此该拓扑支持分布式部署。如果你希望更强的资源隔离，可以
在 API Deployment 中设置 `ARQ_EMBEDDED_WORKER=false`，并通过
`arq src.infra.task.arq_worker.WorkerSettings` 单独运行 worker Pod。

运行多个应用 Pod 时，不要使用本地上传存储，也不要开启
`ENABLE_LOCAL_FILESYSTEM_FALLBACK=true`。

## 管理

```bash
# 查看 Pod
kubectl get pods -n lambchat

# 查看应用日志
kubectl logs -f deployment/lambchat -n lambchat

# 重启应用
kubectl rollout restart deployment/lambchat -n lambchat

# 删除所有资源
kubectl delete -f k8s/lambchat.yaml
```
