# Kubernetes Deployment

Deploy LambChat to a Kubernetes cluster using the provided manifests. The provided
manifest is intended for multi-replica application pods and expects external or
managed MongoDB, Redis, and S3-compatible object storage.

## Quick Start

```bash
# Apply all resources
kubectl apply -f k8s/lambchat.yaml

# Check deployment status
kubectl get pods -n lambchat
kubectl get svc -n lambchat
```

::: tip
The manifest reads sensitive values (JWT secret, MCP encryption salt, database credentials, S3 keys) from the `lambchat-secrets` Secret. Copy `k8s/lambchat-secret.yaml.example` to `k8s/lambchat-secret.yaml`, fill in your values, and apply it — pods cannot start until the Secret exists.
:::

## Architecture

The K8s manifest (`k8s/lambchat.yaml`) creates:

| Resource | Name | Description |
|----------|------|-------------|
| Namespace | `lambchat` | Isolated namespace for all resources |
| Deployment | `lambchat` | LambChat API/web pods with an embedded arq worker per pod |
| Service | `lambchat` | Application service |

For production scaling, run MongoDB and Redis as managed services or separate
high-availability workloads. Do not use per-pod local uploads for multi-replica
deployments; configure S3-compatible object storage instead.

## Configuration

### Environment Variables

Edit the `lambchat` Deployment in `k8s/lambchat.yaml` to set environment variables:

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

For sensitive values, use Kubernetes Secrets:

```yaml
env:
  - name: JWT_SECRET_KEY
    valueFrom:
      secretKeyRef:
        name: lambchat-secrets
        key: jwt-secret-key
```

### Ingress

The default manifest exposes a Kubernetes Service. Add an Ingress that matches
your ingress controller when publishing the app externally:

**nginx Ingress example:**

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

## Scaling

```bash
# Scale symmetric API/web + embedded arq worker pods
kubectl scale deployment lambchat --replicas=3 -n lambchat
```

Multi-replica deployments require shared backing services:

- MongoDB for persistent application data.
- Redis for pub/sub, WebSocket routing, task queueing, distributed locks, and caches.
- S3-compatible object storage for uploads and generated artifacts.
- Stable shared secrets such as `JWT_SECRET_KEY` and `MCP_ENCRYPTION_SALT`.

Set `LAMBCHAT_DISTRIBUTED_MODE=true` for multi-replica deployments. In this mode
API and worker processes fail fast if generated runtime secrets or local upload
storage would make replicas inconsistent.

The default manifest uses symmetric application pods: each `lambchat` pod serves
HTTP/WebSocket traffic and also runs an embedded arq worker. This is distributed
safe because arq jobs, payloads, cancellation, and concurrency slots are
coordinated through Redis and MongoDB. If you want stricter resource isolation,
set `ARQ_EMBEDDED_WORKER=false` on the API Deployment and run separate worker
pods with `arq src.infra.task.arq_worker.WorkerSettings`.

Do not use local upload storage or `ENABLE_LOCAL_FILESYSTEM_FALLBACK=true` when
running more than one application pod.

## Managing

```bash
# View pods
kubectl get pods -n lambchat

# View application logs
kubectl logs -f deployment/lambchat -n lambchat

# Restart application
kubectl rollout restart deployment/lambchat -n lambchat

# Delete all resources
kubectl delete -f k8s/lambchat.yaml
```
