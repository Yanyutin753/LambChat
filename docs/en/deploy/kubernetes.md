# Kubernetes Deployment

Deploy LambChat to a Kubernetes cluster using the provided manifests.

## Quick Start

```bash
# Apply all resources
kubectl apply -f k8s/lambchat.yaml

# Check deployment status
kubectl get pods -n lambchat
kubectl get svc -n lambchat
kubectl get ingress -n lambchat
```

## Architecture

The K8s manifest (`k8s/lambchat.yaml`) creates:

| Resource | Name | Description |
|----------|------|-------------|
| Namespace | `lambchat` | Isolated namespace for all resources |
| Deployment | `mongodb` | MongoDB 7 standalone |
| Deployment | `redis` | Redis 7 standalone |
| Deployment | `lambchat` | LambChat application |
| Service | `mongo-svc` | MongoDB ClusterIP (port 27017) |
| Service | `redis-svc` | Redis ClusterIP (port 6379) |
| Service | `lambchat-svc` | LambChat ClusterIP (port 8000) |
| Ingress | `lambchat-ingress` | Traefik IngressRoute for HTTP |

## Configuration

### Environment Variables

Edit the `lambchat` Deployment in `k8s/lambchat.yaml` to set environment variables:

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

For sensitive values, use Kubernetes Secrets:

```yaml
env:
  - name: LLM_API_KEY
    valueFrom:
      secretKeyRef:
        name: lambchat-secrets
        key: llm-api-key
```

### Ingress

The default manifest uses Traefik IngressRoute. Adapt it for your ingress controller:

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
                name: lambchat-svc
                port:
                  number: 8000
```

## Scaling

```bash
# Scale the application
kubectl scale deployment lambchat --replicas=3 -n lambchat
```

::: warning
When scaling to multiple replicas, ensure session affinity is configured if using local file storage. For production, use S3 storage (`S3_ENABLED=true`) instead of local storage.
:::

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
