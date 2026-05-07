# Kubernetes 部署

使用提供的清单将 LambChat 部署到 Kubernetes 集群。

## 快速开始

```bash
# 应用所有资源
kubectl apply -f k8s/lambchat.yaml

# 检查部署状态
kubectl get pods -n lambchat
kubectl get svc -n lambchat
kubectl get ingress -n lambchat
```

## 架构

K8s 清单（`k8s/lambchat.yaml`）创建以下资源：

| 资源 | 名称 | 说明 |
|------|------|------|
| 命名空间 | `lambchat` | 所有资源的隔离命名空间 |
| Deployment | `mongodb` | MongoDB 7 单节点 |
| Deployment | `redis` | Redis 7 单节点 |
| Deployment | `lambchat` | LambChat 应用 |
| Service | `mongo-svc` | MongoDB ClusterIP（端口 27017） |
| Service | `redis-svc` | Redis ClusterIP（端口 6379） |
| Service | `lambchat-svc` | LambChat ClusterIP（端口 8000） |
| Ingress | `lambchat-ingress` | Traefik IngressRoute |

## 配置

### 环境变量

编辑 `k8s/lambchat.yaml` 中的 `lambchat` Deployment 设置环境变量：

```yaml
env:
  - name: JWT_SECRET_KEY
    value: "your-stable-secret-key"
  - name: MONGODB_URL
    value: "mongodb://mongo_lambchat:mongo_lambchat_123@mongo-svc:27017"
  - name: REDIS_URL
    value: "redis://redis-svc:6379/0"
  - name: APP_BASE_URL
    value: "https://lambchat.example.com"
```

对于敏感值，使用 Kubernetes Secrets：

```yaml
env:
  - name: LLM_API_KEY
    valueFrom:
      secretKeyRef:
        name: lambchat-secrets
        key: llm-api-key
```

### Ingress

默认清单使用 Traefik IngressRoute。根据你的 Ingress 控制器进行调整：

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
                name: lambchat-svc
                port:
                  number: 8000
```

## 扩缩容

```bash
# 扩展应用副本数
kubectl scale deployment lambchat --replicas=3 -n lambchat
```

::: warning
扩展到多个副本时，如果使用本地文件存储，需确保配置了会话亲和性。生产环境建议使用 S3 存储（`S3_ENABLED=true`）而非本地存储。
:::

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
