# 沙箱配置

安全远程代码执行的沙箱设置。支持 Daytona、E2B 和 CubeSandbox 平台。

## 通用设置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `ENABLE_SANDBOX` | `false` | 启用沙箱执行。 |
| `SANDBOX_PLATFORM` | `daytona` | 沙箱平台：`daytona`、`e2b` 或 `cubesandbox`。 |
| `SANDBOX_GREP_TIMEOUT` | `30` | 沙箱 grep 命令超时时间（秒）。 |

## Daytona

| 变量名 | 默认值 | 敏感 | 说明 |
|--------|--------|------|------|
| `DAYTONA_API_KEY` | _(空)_ | 是 | Daytona API 密钥。 |
| `DAYTONA_SERVER_URL` | _(空)_ | 否 | Daytona 服务器 URL。 |
| `DAYTONA_TIMEOUT` | `180` | 否 | 命令超时时间（秒），默认 3 分钟。 |
| `DAYTONA_IMAGE` | _(空)_ | 否 | 使用的沙箱镜像/快照 ID。 |
| `DAYTONA_AUTO_STOP_INTERVAL` | `5` | 否 | 自动停止间隔（分钟）。 |
| `DAYTONA_AUTO_ARCHIVE_INTERVAL` | `5` | 否 | 自动归档间隔（分钟）。 |
| `DAYTONA_AUTO_DELETE_INTERVAL` | `1440` | 否 | 自动删除间隔（分钟），默认 24 小时。 |

## E2B

| 变量名 | 默认值 | 敏感 | 说明 |
|--------|--------|------|------|
| `E2B_API_KEY` | _(空)_ | 是 | E2B API 密钥。 |
| `E2B_TEMPLATE` | `base` | 否 | 沙箱模板名称。 |
| `E2B_TIMEOUT` | `3600` | 否 | 沙箱超时时间（秒），默认 1 小时。 |
| `E2B_AUTO_PAUSE` | `true` | 否 | 超时时暂停沙箱而非终止（保留状态）。 |
| `E2B_AUTO_RESUME` | `true` | 否 | 下次活动时自动恢复暂停的沙箱。 |

## CubeSandbox

CubeSandbox 通过原生 CubeSandbox Python SDK 支持。LambChat 使用 CubeSandbox 元数据维持稳定的用户与沙箱绑定：每个用户应保持一个运行中的沙箱，并在所有会话之间共享。

| 变量名 | 默认值 | 敏感 | 说明 |
|--------|--------|------|------|
| `CUBE_API_URL` | `http://127.0.0.1:3000` | 否 | CubeSandbox API 基础 URL。本地开发环境通常为 `http://127.0.0.1:13000`。 |
| `CUBE_TEMPLATE` | _(空)_ | 否 | 创建沙箱时使用的 CubeSandbox 模板 ID。 |
| `CUBE_TIMEOUT` | `3600` | 否 | 沙箱超时时间（秒）。 |
| `CUBE_PROXY_NODE_IP` | _(空)_ | 否 | SDK 访问沙箱数据面服务使用的代理节点 IP。 |
| `CUBE_PROXY_PORT_HTTP` | `80` | 否 | SDK 使用的 HTTP 代理端口。 |
| `CUBE_SANDBOX_DOMAIN` | `cube.app` | 否 | CubeSandbox 代理路由使用的沙箱域名后缀。 |
| `CUBE_REQUEST_TIMEOUT` | `120` | 否 | SDK 请求超时时间（秒）。值越小，对失效数据面连接失败越快；值越大，越能容忍较慢的本地启动。 |
| `CUBE_AUTO_PAUSE` | `true` | 否 | 在运行时支持时，超时后请求 CubeSandbox 暂停而非终止。 |
| `CUBE_AUTO_RESUME` | `true` | 否 | 在运行时支持时，请求 CubeSandbox 自动恢复已暂停的沙箱。 |

### 生命周期行为

当 `SANDBOX_PLATFORM=cubesandbox` 时，LambChat 对每个用户按以下顺序处理：

1. 进程内缓存的沙箱仍健康时直接复用。
2. 重连 MongoDB `user_sandbox_bindings` 记录。
3. 绑定缺失或不健康时，按 `metadata.user_id` 匹配列出 CubeSandbox 实例并复用健康的运行中沙箱。
4. 仅当没有可用的健康沙箱时才创建新沙箱。
5. 清理同一用户的重复运行中沙箱，保留选中的沙箱。

CubeSandbox 偶尔会在控制面将沙箱报告为 `running`，但数据面返回 `504 Gateway Time-out`。当 LambChat 无法创建会话工作目录或执行命令时，会将其视为不健康，然后回退到另一个已有沙箱或创建新沙箱。

### 生产迁移

LambChat 按用户和平台存储沙箱绑定。新记录使用：

- `sandboxes.e2b`
- `sandboxes.cubesandbox`

较旧的生产记录可能只有 `sandbox_id`、`sandbox_state` 等顶层字段。当 `SANDBOX_PLATFORM=e2b` 时，这些旧的顶层记录会出于向后兼容被视为 E2B 绑定。下次成功复用时，LambChat 会将同一沙箱写入 `sandboxes.e2b`，因此现有 E2B 沙箱会继续使用而不会重建。

将用户或部署从 `e2b` 切换到 `cubesandbox` 时，会在 `sandboxes.cubesandbox` 下创建或复用 CubeSandbox 绑定，不覆盖 `sandboxes.e2b`。切回 `e2b` 时会重新读取 E2B 槽位。

应继续使用 E2B 的生产部署请保持：

```bash
SANDBOX_PLATFORM=e2b
```

除非确实希望这些用户开始使用 CubeSandbox，否则不要设置 `SANDBOX_PLATFORM=cubesandbox`。两个平台具有独立的沙箱 ID 和独立的生命周期 API。

### 性能说明

- 冷启动创建 CubeSandbox 的耗时取决于模板和本地运行时恢复时间。本地测试中通常约 20-30 秒。
- 同一用户的新会话通常应复用同一沙箱，避免冷启动。
- 重复沙箱清理不在关键缓存命中路径上执行，复用可在后台清理完成前返回。
- `CubeSandboxBackend` 使用 `CUBE_TIMEOUT` 作为命令执行超时，并缓存重复文件写入的父目录创建。
- 会话管理器在当前后端进程中缓存已成功准备的会话工作目录。后端重启后会重新执行 `mkdir -p`，仍然安全。

### 控制台与 API 检查

集成本地 CubeSandbox 开发环境时：

```bash
# CubeSandbox Web UI
open http://127.0.0.1:12088

# 从 Cube API 列出沙箱
curl http://127.0.0.1:13000/sandboxes
```

有用的检查：

- 选中的沙箱的 `metadata.user_id` 应等于 LambChat 用户 ID。
- 一个用户通常应只有一个健康的 `running` 沙箱。
- 如果沙箱显示为 `running` 但命令执行返回 504，请在 CubeSandbox 中终止它，或让 LambChat 在下次初始化沙箱时替换它。

## 示例

### Daytona（自托管）

```bash
ENABLE_SANDBOX=true
SANDBOX_PLATFORM=daytona
DAYTONA_API_KEY=your_daytona_api_key
DAYTONA_SERVER_URL=https://daytona.example.com
DAYTONA_TIMEOUT=180
```

### E2B（云服务）

```bash
ENABLE_SANDBOX=true
SANDBOX_PLATFORM=e2b
E2B_API_KEY=your_e2b_api_key
E2B_TEMPLATE=base
E2B_TIMEOUT=3600
```

### CubeSandbox（本地开发）

```bash
ENABLE_SANDBOX=true
SANDBOX_PLATFORM=cubesandbox
CUBE_API_URL=http://127.0.0.1:13000
CUBE_TEMPLATE=tpl-your-template-id
CUBE_PROXY_NODE_IP=127.0.0.1
CUBE_PROXY_PORT_HTTP=11080
CUBE_SANDBOX_DOMAIN=cube.app
CUBE_TIMEOUT=3600
CUBE_REQUEST_TIMEOUT=120
CUBE_AUTO_PAUSE=true
CUBE_AUTO_RESUME=true
```

::: info
`DAYTONA_AUTO_*_INTERVAL` 设置控制沙箱生命周期管理以优化资源使用。沙箱会根据这些间隔自动停止、归档和最终删除。
:::

::: tip
对于 CubeSandbox，请根据本地运行时调整 `CUBE_REQUEST_TIMEOUT`。值越小，失效沙箱失败越快；值越大，可减少本地恢复较慢时的误判失败。
:::
