# Session-Sandbox 绑定实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现 Session ID 与 Daytona Sandbox ID 的绑定，通过 stop/start 管理沙箱生命周期。

**Architecture:** 新建 SessionSandboxManager 类管理 session-sandbox 绑定关系，沙箱存储在 session.metadata 中，对话结束时 stop 而非 delete，下次对话时从 stopped/archived 状态恢复。

**Tech Stack:** Python, Daytona SDK, MongoDB, Pydantic

---

## Task 1: 添加配置项

**Files:**
- Modify: `src/kernel/config.py`

**Step 1: 添加 SANDBOX_AUTO_STOP_INTERVAL 配置定义**

在 `SETTING_DEFINITIONS` 的 Sandbox Settings 部分添加：

```python
# 在 "DAYTONA_TIMEOUT" 之后添加
"SANDBOX_AUTO_STOP_INTERVAL": {
    "type": SettingType.NUMBER,
    "category": SettingCategory.SANDBOX,
    "description": "Sandbox auto-stop interval in minutes (stopped sandbox will be archived after this time)",
    "default": 5,
},
```

**Step 2: 在 Settings 类中添加属性**

在 `Settings` 类的 Sandbox Settings 部分（约第 585 行）添加：

```python
# 在 DAYTONA_TIMEOUT 之后添加
SANDBOX_AUTO_STOP_INTERVAL: int = 5  # minutes
```

**Step 3: 验证配置**

```bash
python -c "from src.kernel.config import settings; print(settings.SANDBOX_AUTO_STOP_INTERVAL)"
```

Expected: `5`

**Step 4: Commit**

```bash
git add src/kernel/config.py
git commit -m "feat(config): add SANDBOX_AUTO_STOP_INTERVAL setting"
```

---

## Task 2: 创建 SessionSandboxManager 类

**Files:**
- Create: `src/infra/sandbox/session_manager.py`

**Step 1: 创建 SessionSandboxManager 类**

```python
"""
Session-Sandbox 绑定管理器

管理 Session 与 Daytona Sandbox 的绑定关系：
- 沙箱存储在 session.metadata 中
- 对话结束时 stop 而非 delete
- 下次对话时从 stopped/archived 状态恢复
"""

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from daytona import CreateSandboxFromSnapshotParams, Daytona, DaytonaConfig

from src.infra.backend.daytona import DaytonaBackend
from src.infra.session.manager import SessionManager
from src.kernel.config import settings
from src.kernel.schemas.session import SessionUpdate

if TYPE_CHECKING:
    from deepagents.backends.protocol import SandboxBackendProtocol

logger = logging.getLogger(__name__)


class SessionSandboxManager:
    """管理 Session 与 Sandbox 的绑定关系"""

    def __init__(self):
        self._session_manager = SessionManager()
        self._daytona_client: Optional[Daytona] = None
        # 内存缓存: session_id -> (sandbox_id, backend)
        self._cache: dict[str, tuple[str, "SandboxBackendProtocol"]] = {}

    def _get_daytona_client(self) -> Daytona:
        """获取或创建 Daytona 客户端"""
        if self._daytona_client is None:
            config = DaytonaConfig(
                api_key=settings.DAYTONA_API_KEY,
                server_url=settings.DAYTONA_SERVER_URL,
            )
            self._daytona_client = Daytona(config)
        return self._daytona_client

    async def get_or_create(
        self,
        session_id: str,
        user_id: str,
    ) -> "SandboxBackendProtocol":
        """
        获取或创建沙箱

        流程：
        1. 检查内存缓存
        2. 检查 session.metadata 中的 sandbox_id
        3. 如果存在，查询 Daytona 状态
        4. Stopped/Archived → start() 恢复
        5. 不存在或恢复失败 → 创建新沙箱，覆盖绑定
        """
        # 1. 检查内存缓存
        if session_id in self._cache:
            sandbox_id, backend = self._cache[session_id]
            logger.debug(f"[SessionSandboxManager] Cache hit: session={session_id}, sandbox={sandbox_id}")
            return backend

        # 2. 从 session.metadata 获取 sandbox_id
        session = await self._session_manager.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        sandbox_id = session.metadata.get("sandbox_id") if session.metadata else None

        if sandbox_id:
            # 3. 查询 Daytona 状态
            state = await self._get_sandbox_state(sandbox_id)
            logger.info(f"[SessionSandboxManager] Found sandbox {sandbox_id} with state={state}")

            if state in ("stopped", "archived"):
                # 4. 尝试恢复
                try:
                    await self._start_sandbox(sandbox_id)
                    backend = await self._create_backend(sandbox_id)
                    self._cache[session_id] = (sandbox_id, backend)
                    await self._update_session_metadata(session_id, sandbox_id, "running")
                    logger.info(f"[SessionSandboxManager] Resumed sandbox {sandbox_id}")
                    return backend
                except Exception as e:
                    logger.warning(f"[SessionSandboxManager] Failed to resume sandbox {sandbox_id}: {e}")
                    # 恢复失败，创建新沙箱

            elif state == "running":
                # 沙箱已在运行，直接使用
                backend = await self._create_backend(sandbox_id)
                self._cache[session_id] = (sandbox_id, backend)
                return backend

            elif state == "destroyed":
                logger.info(f"[SessionSandboxManager] Sandbox {sandbox_id} was destroyed")
                # 沙箱已销毁，创建新沙箱

        # 5. 创建新沙箱并绑定
        return await self._create_and_bind(session_id, user_id)

    async def stop(self, session_id: str) -> bool:
        """
        停止沙箱（对话结束时调用）

        Returns:
            是否成功停止
        """
        if session_id not in self._cache:
            # 尝试从 session.metadata 获取
            session = await self._session_manager.get_session(session_id)
            if not session or not session.metadata:
                return False
            sandbox_id = session.metadata.get("sandbox_id")
            if not sandbox_id:
                return False
        else:
            sandbox_id, _ = self._cache[session_id]

        try:
            client = self._get_daytona_client()
            sandbox = client.get(sandbox_id)
            sandbox.stop(timeout=30)
            await self._update_session_metadata(session_id, sandbox_id, "stopped")
            logger.info(f"[SessionSandboxManager] Stopped sandbox {sandbox_id}")
            return True
        except Exception as e:
            logger.error(f"[SessionSandboxManager] Failed to stop sandbox {sandbox_id}: {e}")
            return False

    async def _get_sandbox_state(self, sandbox_id: str) -> str:
        """查询沙箱状态: running / stopped / archived / destroyed"""
        try:
            client = self._get_daytona_client()
            sandbox = client.get(sandbox_id)
            # state 是 SandboxState 枚举，转换为小写字符串
            state = str(sandbox.state).lower()
            return state
        except Exception as e:
            # 如果沙箱不存在，返回 destroyed
            if "not found" in str(e).lower():
                return "destroyed"
            raise

    async def _start_sandbox(self, sandbox_id: str) -> None:
        """启动沙箱"""
        client = self._get_daytona_client()
        sandbox = client.get(sandbox_id)
        sandbox.start(timeout=60)

    async def _create_backend(self, sandbox_id: str) -> "SandboxBackendProtocol":
        """为已存在的沙箱创建 backend 包装"""
        client = self._get_daytona_client()
        sandbox = client.get(sandbox_id)
        return DaytonaBackend(sandbox=sandbox)

    async def _create_and_bind(
        self,
        session_id: str,
        user_id: str,
    ) -> "SandboxBackendProtocol":
        """创建新沙箱并绑定到 session（替换旧的）"""
        client = self._get_daytona_client()

        # 创建带 auto_stop_interval 的沙箱
        params = CreateSandboxFromSnapshotParams(
            auto_stop_interval=settings.SANDBOX_AUTO_STOP_INTERVAL,
            language="python",
        )
        sandbox = client.create(params)
        backend = DaytonaBackend(sandbox=sandbox)

        # 更新 session metadata（覆盖旧的 sandbox_id）
        await self._update_session_metadata(session_id, sandbox.id, "running", is_new=True)

        # 更新内存缓存
        self._cache[session_id] = (sandbox.id, backend)

        logger.info(
            f"[SessionSandboxManager] Created sandbox {sandbox.id} for session {session_id}"
        )

        return backend

    async def _update_session_metadata(
        self,
        session_id: str,
        sandbox_id: str,
        state: str,
        is_new: bool = False,
    ) -> None:
        """更新 session metadata"""
        now = datetime.now().isoformat()
        metadata = {
            "sandbox_id": sandbox_id,
            "sandbox_state": state,
            "sandbox_last_used_at": now,
        }
        if is_new:
            metadata["sandbox_created_at"] = now

        await self._session_manager.update_session(
            session_id,
            SessionUpdate(metadata=metadata),
        )

    def clear_cache(self, session_id: str) -> None:
        """清除内存缓存（用于测试或强制刷新）"""
        self._cache.pop(session_id, None)
```

**Step 2: 验证语法**

```bash
python -m py_compile src/infra/sandbox/session_manager.py
```

Expected: No output (success)

**Step 3: Commit**

```bash
git add src/infra/sandbox/session_manager.py
git commit -m "feat(sandbox): add SessionSandboxManager for session-sandbox binding"
```

---

## Task 3: 导出 SessionSandboxManager

**Files:**
- Modify: `src/infra/sandbox/__init__.py`

**Step 1: 添加导出**

```python
"""
Sandbox 模块

提供统一的 Sandbox 管理，支持 Runloop、Daytona、Modal 平台。
"""

from .base import (
    DaytonaConfig,
    ModalConfig,
    RunloopConfig,
    SandboxConfig,
    SandboxFactory,
    get_sandbox_config_from_settings,
    get_sandbox_from_settings,
)
from .session_manager import SessionSandboxManager

__all__ = [
    # 配置类
    "SandboxConfig",
    "RunloopConfig",
    "DaytonaConfig",
    "ModalConfig",
    # 工厂
    "SandboxFactory",
    "get_sandbox_config_from_settings",
    "get_sandbox_from_settings",
    # Session 绑定管理
    "SessionSandboxManager",
]
```

**Step 2: 验证导入**

```bash
python -c "from src.infra.sandbox import SessionSandboxManager; print(SessionSandboxManager)"
```

Expected: `<class 'src.infra.sandbox.session_manager.SessionSandboxManager'>`

**Step 3: Commit**

```bash
git add src/infra/sandbox/__init__.py
git commit -m "feat(sandbox): export SessionSandboxManager from module"
```

---

## Task 4: 修改 agent_node 使用 SessionSandboxManager

**Files:**
- Modify: `src/agents/search_agent/nodes.py`

**Step 1: 修改导入部分**

在文件顶部的导入区域，添加 `SessionSandboxManager`：

```python
# 找到这行（约第 23 行）：
from src.infra.sandbox import get_sandbox_from_settings

# 替换为：
from src.infra.sandbox import SessionSandboxManager
```

**Step 2: 修改沙箱创建逻辑**

找到 `agent_node` 函数中的沙箱创建代码（约第 77-79 行）：

```python
# 原代码：
if settings.ENABLE_SANDBOX:
    backend = get_sandbox_from_settings()
    sandbox_id = SandboxFactory.get_sandbox_id(backend)

# 替换为：
sandbox_manager = None
sandbox_id = None

if settings.ENABLE_SANDBOX:
    sandbox_manager = SessionSandboxManager()
    backend = await sandbox_manager.get_or_create(
        session_id=state.get("session_id", str(uuid.uuid4())),
        user_id=context.user_id or "default",
    )
    sandbox_id = backend.id
```

**Step 3: 修改 finally 块中的沙箱关闭逻辑**

找到 finally 块（约第 376-381 行）：

```python
# 原代码：
finally:
    # 关闭 sandbox（无论成功失败都要关闭）
    try:
        if sandbox_id:
            await SandboxFactory.close_sandbox(sandbox_id)
    except Exception as e:
        logger.warning(f"Failed to close sandbox: {e}")

# 替换为：
finally:
    # 停止 sandbox（无论成功失败都要停止，但保留状态）
    try:
        if sandbox_manager and state.get("session_id"):
            await sandbox_manager.stop(state.get("session_id"))
    except Exception as e:
        logger.warning(f"Failed to stop sandbox: {e}")
```

**Step 4: 移除不再需要的导入**

移除 `SandboxFactory` 的导入（如果不再使用）：

```python
# 删除这行（如果存在）：
from src.infra.sandbox.base import SandboxFactory
```

**Step 5: 验证语法**

```bash
python -m py_compile src/agents/search_agent/nodes.py
```

Expected: No output (success)

**Step 6: Commit**

```bash
git add src/agents/search_agent/nodes.py
git commit -m "feat(agent): use SessionSandboxManager for sandbox lifecycle"
```

---

## Task 5: 集成测试

**Files:**
- Create: `tests/test_session_sandbox_manager.py`

**Step 1: 创建测试文件**

```python
"""
SessionSandboxManager 集成测试

注意：这些测试需要 Daytona API 配置，标记为 integration 测试。
"""

import pytest

from src.infra.sandbox import SessionSandboxManager
from src.kernel.config import settings


@pytest.mark.skipif(
    not settings.DAYTONA_API_KEY,
    reason="DAYTONA_API_KEY not configured",
)
class TestSessionSandboxManager:
    """集成测试（需要真实 Daytona API）"""

    @pytest.mark.asyncio
    async def test_create_and_stop_sandbox(self, tmp_session):
        """测试创建和停止沙箱"""
        manager = SessionSandboxManager()

        # 创建沙箱
        backend = await manager.get_or_create(tmp_session, "test_user")
        assert backend is not None
        assert backend.id

        sandbox_id = backend.id

        # 停止沙箱
        result = await manager.stop(tmp_session)
        assert result is True

        # 再次获取应该恢复沙箱
        backend2 = await manager.get_or_create(tmp_session, "test_user")
        assert backend2.id == sandbox_id

        # 清理
        await manager.stop(tmp_session)


@pytest.fixture
async def tmp_session():
    """创建临时测试 session"""
    from src.infra.session.manager import SessionManager
    from src.kernel.schemas.session import SessionCreate

    manager = SessionManager()
    session = await manager.create_session(
        SessionCreate(name="test_session"),
        user_id="test_user",
    )

    yield session.id

    # 清理
    await manager.delete_session(session.id)
```

**Step 2: 运行测试（可选，需要 Daytona 配置）**

```bash
pytest tests/test_session_sandbox_manager.py -v -m "not skipif"
```

**Step 3: Commit**

```bash
git add tests/test_session_sandbox_manager.py
git commit -m "test(sandbox): add integration tests for SessionSandboxManager"
```

---

## Task 6: 最终验证

**Step 1: 运行完整测试套件**

```bash
pytest tests/ -v --ignore=tests/test_session_sandbox_manager.py
```

Expected: All tests pass

**Step 2: 启动服务验证**

```bash
# 启动服务
python -m uvicorn src.api.main:app --reload

# 检查日志，确认无启动错误
```

**Step 3: Final Commit**

```bash
git add -A
git commit -m "feat(sandbox): complete session-sandbox binding implementation"
```

---

## 修改文件清单

| 文件 | 操作 |
|------|------|
| `src/kernel/config.py` | Modify - 添加 SANDBOX_AUTO_STOP_INTERVAL |
| `src/infra/sandbox/session_manager.py` | Create - SessionSandboxManager 类 |
| `src/infra/sandbox/__init__.py` | Modify - 导出 SessionSandboxManager |
| `src/agents/search_agent/nodes.py` | Modify - 使用 SessionSandboxManager |
| `tests/test_session_sandbox_manager.py` | Create - 集成测试 |
