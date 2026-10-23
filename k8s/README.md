# Kubernetes 发布

生产使用现有 hostNetwork API 双分片和独立 arq worker。数据库、Redis、Secret、
envFrom、Service 与入口 OpenResty 保持现有配置；`lambchat.yaml` 是通用部署示例，
不是生产双分片清单，不能直接覆盖生产。

发布入口现在由仓库维护：`scripts/update.sh`、`scripts/update-staging.sh`、
`scripts/update.py` 与 `scripts/publish_assets.py`。
将这四个文件一起部署到服务器同一目录，使用服务器已有的 Kubernetes 身份运行。
脚本不拉取或改写 Secret，不根据时间戳自动选择“最新”镜像。

```bash
KUBECTL='k3s kubectl' python3 k8s/scripts/update.py main-YYYYMMDD-HHMMSS
# 保持服务器原有入口；wrapper 默认使用 k3s kubectl
/data/lambchat-k8s/update.sh main-YYYYMMDD-HHMMSS
```

只传已经完成 CI 与 staging 验收的明确 tag。生产 namespace 默认 `lambchat`，
仅接受 `main-*`；镜像来自 `ghcr.io/yanyutin753/lambchat`。tag 必须保持不可变，
不要覆盖已发布 tag。执行前由发布者核对 tag 对应的源码与 CI。
旧入口不传参自动选择 latest 的行为已移除；生产和 staging 都必须显式传 tag。
新入口不调用服务器旧 `sync-manifest.py`；该脚本不能同时同步镜像和端口。
服务器含 Secret 的原始清单只在服务器私下备份，不能复制进仓库。

## 首次接入

- API Deployment 默认 `lambchat-a` / `lambchat-b`，各一个副本、一个应用容器。
  API 端口必须同时由 `PORT` 和名为 `http` 的 containerPort 声明。
- 两组端口分别为 `8011 ↔ 8013`、`8012 ↔ 8014`。首次接入用 `ss -ltnp`
  校准宿主端口；脚本同时检查同节点 Pod 声明并在本机尝试绑定备用端口。
  因此必须在实际 API 节点运行发布入口，不能从连接远端集群的笔记本直接执行。
  防火墙需要沿用当前来源限制，放行 NodePort DNAT 后的备用目标端口，不能开放给所有来源。
- Service 默认 `lambchat`，必须选择两个 API 分片并使用命名 targetPort `http`。
  OpenResty 继续访问 NodePort，不能绕过 Service 直接绑定某一分片。
- worker 默认 `lambchat-worker`，镜像必须包含 `/tmp/lambchat-worker.ready`
  的 PID 与更新时间约定，以及停止取新任务后最多 240 秒的排空逻辑。
  仅把 Kubernetes 宽限改成 300 秒不能实现排空。
- 发布机必须能够非交互执行 kubectl；发布锁固定为
  `/data/lambchat-k8s/deployment.lock`，所有发布入口共用。不得删除锁文件、后台排队或并行运行旧发布脚本。
- assets 缓存是宿主目录 `/data/lambchat-k8s/static-assets`，容器只读挂载到
  `/app/static/assets`。缓存必须能被镜像中的非 root 用户读取。发布时保留旧 hash 资源，
  不执行覆盖式同步或删除，避免旧页面切换路由、动态 import、字体加载时 404。
- 当前 assets 实现面向单节点 k3s；多节点必须先改为各节点都能读取的 RWX 存储或统一静态资源源站。
  脚本不自动把单节点 hostPath 当成集群共享存储。

## yang 单机容量（2026-10-21）

生产保持 2 个 API 分片，worker 从 2 个扩到 3 个；同一模板只新增 worker，不重启现有任务进程。
生产副本数保存在服务器私有清单，通用示例的 worker 副本数也同步为 3；发布脚本保留现有副本数。

当时 yang 为 8 vCPU / 15.6 GiB 内存：CPU 约 6%，可用内存约 8.8 GiB，
过去 24 小时 5 分钟平均 CPU 峰值约 24%、最低可用内存约 6.1 GiB。
API 每个约 502 MiB、worker 每个空闲约 292 MiB；这些是观测值，不是任务高峰内存预算。
worker 单个上限 3 GiB，仍需为数据库、其他现有服务及发布临时副本留余量，不据此继续盲目扩容。

hostNetwork 下每个 API 分片只能有 1 个副本；不能直接把 `lambchat-a/b` 的 replicas 改成 2，
否则同机端口冲突。更多 API 需要独立分片和备用端口对，并同步发布入口、Service、监控与回归调用方。
同一台 yang 上增加 Pod 可分散进程负载，不能抵御宿主机故障，也不增加物理 CPU 或内存。

## 更新与回滚

1. 非阻塞获取部署锁；读取所有目标原始配置，确认所有 Deployment 和 Pod 已就绪，
   Service 选择器正确、备用端口可绑定，并直接通过 NodePort 检查 `/ready`、HTML 和其 JavaScript 资源。
   公网 `/health` 可能是 OpenResty 本地静态应答，不能用来证明后端可用。
   任一预检失败，不滚动任何 Deployment。
2. 先发布目标镜像静态资源，并保留当前资源，确保混合版本期间两种 HTML 都能加载资源。
3. 按 `a → b → worker` 串行发布。API 通过一次原子 patch 同时修改 image、PORT 和命名端口，
   使用 `maxSurge=1` / `maxUnavailable=0`，新 Pod `/ready` 启动并连续可用后才终止旧 Pod。
4. API 旧 Pod 在 `preStop` 等待 10 秒，使 terminating Endpoint 的摘流传播到入口；
   Kubernetes 宽限 150 秒覆盖 uvicorn 默认 120 秒退出窗口。liveness 也使用命名端口。
   worker 使用 PID 与文件更新时间探针、300 秒宽限及相同的先增后减策略。
5. 每个目标都等待 rollout、就绪；Pod 模板改变时再等待旧 Pod 真正退出，避免下次发布复用仍被旧进程占用的端口。
   重复发布相同镜像时，未改变模板的 worker 保持运行，不等待不会退出的现有 Pod。
6. 任一步失败，恢复所有已尝试修改的 Deployment 的相关原始字段，并逐个确认回滚就绪。
   回滚期间先保留 `maxSurge=1` / `maxUnavailable=0` 恢复原 Pod 模板，原版本就绪后才恢复原滚动策略。
   正向 patch 检查快照 generation；回滚检查字段仍为本脚本写入值并以当前 generation 再次保护。
   发现外部并发修改时保留现场、报告回滚不完整，不用旧快照覆盖其他人的变更。
   不用 `rollout undo` 猜测上一修订；不恢复或覆盖 Secret、envFrom 和无关配置。
   回滚失败明确报出目标，退出失败状态，不能继续宣称发布成功。

不要在旧部署入口与新入口之间同时发布。手工改 Deployment 前也要确认没有发布正在运行。
共享资源采用增量保留，失败发布不会删除新资源；清理旧资源属于独立维护任务，必须考虑仍打开的旧页面。
长于退出窗口的 SSE / WebSocket 仍可能重新连接；真正用户无感还依赖原 run、事件游标和客户端重连恢复。
不可对可能已经执行的 POST 或工具调用盲目重放。

## 自定义实例与 staging

```bash
KUBECTL='k3s kubectl' python3 k8s/scripts/update.py develop-YYYYMMDD-HHMMSS \
  --namespace lambchat-staging \
  --api lambchat-staging:8021:8023 \
  --worker lambchat-staging-worker \
  --service lambchat-staging
```

`--api DEPLOYMENT:PORT1:PORT2` 可以重复。目标资源必须已经存在并满足上述约定，
包括独立 worker；脚本不创建环境、不复制生产凭据。

已有 staging 如果只有 hostNetwork `8021`、OpenResty 直连该端口，先创建版本化的 staging Service：
选择器 `app=lambchat-staging`，命名 targetPort `http`，NodePort `30082`。
确认当前 Pod 已声明命名端口后，让测试站点 OpenResty 从 `8021` 改指本机 `30082`，
先用原 Pod 验证 `/ready` 与实际 HTML，再执行 `8021 ↔ 8023` 发布。
避免在发布中同时迁移入口和应用版本。

## 验证

排查 trace“零事件”时，不要只统计父文档的 `events` 数组：关闭 legacy 双写后，正文保存在
`trace_event_chunks`，父数组为空是预期状态。先核对 `event_count`，再使用
`TraceStorage.read_trace_events_compat(trace_id)` 读取实际事件；该入口兼容旧数组与分块存储。
`status=error` 应结合实际 error 事件和 `metadata.error_code` 判断，不能从空父数组推断事件丢失。

原生记忆的检索状态可在鉴权后的 `/api/memory/` 响应 `search_status` 中查看。
Qdrant 模式不需要 Mongo Atlas 索引；自建 Mongo 不支持 Search 时保留 Python 余弦检索，
`mongodb_index=unavailable`、`fallback=cosine` 明确反映该状态。

所有本地验证通过项目共享锁串行运行：

```bash
python3 scripts/run_validation.py uv run pytest tests/infra/deploy/ -q
```

上线前在 staging 验证完整链路：持续轮询首页和鉴权 API，保持实际对话 SSE、通知 WebSocket、
上传与下载，同时发布两次，覆盖端口往返切换。保持旧页面打开，在混合版本和发布完成后触发旧 hash
动态加载，检查内容类型与响应体，不能只看 HTTP 200。运行中任务跨 worker 滚动必须保留相同 run 身份、
无重复工具副作用。观察新 Pod 在 Ready 前没有流量、worker 探针确实反映消费循环。

分别注入 API-b 未就绪、worker 未就绪、patch 拒绝、资源发布失败，确认之前已更新目标均恢复原配置，
至少一个 API 一直可用；第二个发布进程必须立即因锁忙退出。发布后核对每个 Deployment 的 image、
实际 Pod imageID、端口、就绪状态与遗留 terminating Pod，再运行现有分布式回归。
单测覆盖脚本决策；不能替代这些真实入口、应用和故障注入证据。


## 本地沙箱文件流与滚动发布

`nginx/nginx.conf` 的 `/api/sandbox/` 配置须同步到源站与边缘站点，保留各站点的
稳定 Service upstream。关闭请求/响应缓冲与 `proxy_next_upstream`，不能让代理
重放已经开始的文件 POST。修改前备份站点配置，先 `nginx -t`，再平滑 reload；
staging 的 SSE、双向传输和中断验收通过后再同步生产。
仅二进制回传子路径关闭代理 body 上限，避免默认 50MB/100MB 限制截断大文件；
后端继续按 `S3_INTERNAL_UPLOAD_MAX_SIZE` 和帧预算流式校验，普通 JSON 回传不放开。

代理 upstream 的 `keepalive_timeout` 应短于源站的空闲连接时限：当前 uvicorn
默认 5 秒，模板使用 4 秒。空闲连接时限与 `proxy_read_timeout`、工具总执行时限
独立；不通过缩短工具时限修复代理连接复用问题。

daemon 2.14.3 及更早版本的流式接口不携带机器身份。非 legacy 机器在下发流式
操作前检查版本，自动降级现有分块通道；回传的所有者与机器校验继续保留。
文件流连续 60 秒无进展会显式失败，不再占满 600 秒总时限。此限制只用于文件流，
不用于 `exec` 或运行中的长工具。新 daemon 在流式回传失败后补发错误终态。

滚动更新保证新请求仍有 Ready 副本可接入；已有 SSE/POST 仍可能因连接关闭而
中断。调用入队前最多等待 2 秒吸收 daemon 重连的短暂离线窗口；超出窗口仍返回
原离线错误，不重放已经下发的调用，不更换指定机器。文件流中断必须补错误哨兵，
HTTP 请求体完整接收后才发布 EOF 成功；
目录传输有失败或跳过时 `success=false`，不将缺失文件作为完整交付。
