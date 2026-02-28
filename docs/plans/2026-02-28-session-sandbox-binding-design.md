# Session-Sandbox 绑定设计

## 概述

实现 Session ID 与 Daytona Sandbox ID 的绑定，通过 stop/start 管理沙箱生命周期，实现沙箱复用而非每次创建/销毁。

## 背景

当前架构每次对话都创建新沙箱，对话结束后删除。这种方式：
- 增加启动延迟（每次都要创建沙箱）
- 丢失沙箱中的文件状态（用户需要手动 sync_conversation）

## 目标

- Session 绑定一个持久化沙箱
- 对话结束后 stop 沙箱（不删除）
- 下次对话时检查状态，从 Stopped/Archived 恢复
- 沙箱自动归档时间：5 分钟（可配置）

## 架构

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│   agent_node    │────▶│ SessionSandboxManager │────▶│ SessionManager  │
└─────────────────┘     └──────────────────────┘     └─────────────────┘
                                 │
                                 ▼
                        ┌──────────────────────┐
                        │   Daytona Client     │
                        │  (create/stop/start) │
                        └──────────────────────┘
```

## 核心组件

### SessionSandboxManager

位置：`src/infra/sandbox/session_manager.py`

```python
class SessionSandboxManager:
    """管理 Session 与 Sandbox 的绑定关系"""

    async def get_or_create(self, session_id: str, user_id: str) -> SandboxBackendProtocol:
        """
        获取或创建沙箱
        - 检查 session.metadata 中的 sandbox_id
        - 如果存在，查询 Daytona 状态
        - Stopped/Archived → start() 恢复
        - 不存在或恢复失败 → 创建新沙箱，覆盖绑定
        """

    async def stop(self, session_id: str) -> bool:
        """
        停止沙箱（对话结束时调用）
        - 调用 Daytona sandbox.stop()
        - 不删除，保留状态
        """

    async def get_sandbox_state(self, sandbox_id: str) -> str:
        """查询沙箱状态: running / stopped / archived / destroyed"""
```

## 数据存储

### Session metadata 结构

```json
{
  "sandbox_id": "sb_xxx",
  "sandbox_state": "stopped",
  "sandbox_created_at": "2024-01-01T00:00:00Z",
  "sandbox_last_used_at": "2024-01-01T00:05:00Z"
}
```

## 状态流转

```
                    ┌─────────────────────────────────────┐
                    │                                     │
                    ▼                                     │
┌─────────┐    ┌─────────┐    ┌──────────┐    ┌─────────┴─┐
│ Create  │───▶│ Running │───▶│ Stopped  │───▶│ Archived  │
└─────────┘    └─────────┘    └──────────┘    └───────────┘
                    ▲                                 │
                    │                                 │
                    └─────────── start() ─────────────┘

         (5分钟后自动归档)
```

## 配置

```python
# settings.py
SANDBOX_AUTO_STOP_INTERVAL: int = 5  # 分钟，自动归档时间
```

## 错误处理

| 场景 | 处理方式 |
|------|----------|
| 沙箱被外部删除/destroyed | 创建新沙箱，覆盖 metadata 中的 sandbox_id |
| start() 恢复失败 | 创建新沙箱，覆盖 metadata 中的 sandbox_id |
| Daytona API 超时 | 重试 3 次，失败则创建新沙箱并覆盖 |
| session 不存在 | 抛出 SessionNotFoundError |

## 修改文件清单

1. **新增**：`src/infra/sandbox/session_manager.py` - SessionSandboxManager 类
2. **修改**：`src/infra/sandbox/__init__.py` - 导出 SessionSandboxManager
3. **修改**：`src/agents/search_agent/nodes.py` - 使用 SessionSandboxManager
4. **修改**：`src/kernel/config.py` - 添加 SANDBOX_AUTO_STOP_INTERVAL 配置
