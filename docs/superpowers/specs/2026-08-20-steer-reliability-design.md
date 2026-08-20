# Steer 消息可靠性设计

## 目标

让运行中插话在重复文本、快速连续发送、取消竞态、任务刚结束、SSE 重连、模型调用失败和进程重启等情况下保持可预测，并让用户始终知道消息处于什么状态。

## 方案

每条 steer 使用稳定的 `message_id`，后端队列保存 `{id, content, created_at}`，队列操作返回明确状态。前端以 ID 建立状态机：`pending → delivered`，或 `pending → deferred/failed/cancelled`；只有服务端明确返回任务已结束时才转普通消息。事件携带 `message_id` 和 `run_id`，客户端按 ID 幂等处理并拒绝旧会话/旧 run 事件。

队列优先使用 Redis 列表和带 TTL 的 inflight lease，领取、确认、失败回滚均在队列抽象内完成；Redis 不可用时降级为带锁内存实现，继续支持本地开发。

## API 与事件

- `POST /sessions/{id}/steer` 接受可选 `message_id`，返回 `accepted`, `message_id`, `queued`；重复相同 ID 返回同一接受结果，不重复入队。
- `DELETE /sessions/{id}/steer` 按 `message_id` 取消，兼容旧客户端按 `message` 取消。
- `steer:message` 携带 `message_id`, `content`, `run_id`；重复事件不重复渲染。

## 验证

增加前后端测试覆盖 ID 幂等、重复文本、取消/领取竞态、失败回滚、旧事件隔离、网络失败不误发送，以及现有流式回放和构建检查。
