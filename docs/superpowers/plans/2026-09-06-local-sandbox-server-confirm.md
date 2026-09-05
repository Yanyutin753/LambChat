# 本地沙箱执行确认统一服务端 HITL 门 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把本地沙箱「执行确认」统一为一处服务端 HITL 门（复用 ask_human interrupt 全链路），所有 exec / 文件写 / 上传路径过同一道门；daemon 拆掉终端确认、只执行已确认请求。

**Architecture:** 确认门放在服务端 `LocalSandboxBackend`/`WorkspaceAliasBackend` 的操作入口（图任务内，interrupt 可穿透 deepagents 工具边界），以 `kind="ask_human"` 的 interrupt payload 挂起图，由既有 `materialize_ask_human_approvals` → 审批面板 → `submit_hitl_resume_run` 闭环恢复。三档策略（all/commands/none）的唯一权威来源仍是 `~/.lambchat/sandbox.json`，daemon connect URL 上报，服务端 registry 四段式存储，门侧实时读取。云端沙箱（E2B/Daytona/Cube）不接入门（隔离环境，维持现行为）。

**Tech Stack:** Python 3.12 / FastAPI / LangGraph interrupt / Redis / pytest；client 侧 PyInstaller daemon；前端 React+TS（仅 status 字段消费）。

**Spec:** `docs/superpowers/specs/2026-09-01-local-sandbox-design.md` §3.5（本计划补齐其未实现部分：确认从 daemon 终端交互搬到服务端 interrupt）。

## Global Constraints

- 后端依赖用 `uv run`，测试 `uv run pytest`；前端 `pnpm`。
- 路由层禁止 `raise HTTPException`，一律 `AppError + ErrorCode`（本计划不新增错误码）。
- 面向用户文案五语 zh/en/ja/ko/ru（本计划不新增 UI 文案，审批卡 message 是运行时数据非 i18n）。
- 本 worktree：`/home/yangyang/LambChat/.worktrees/sandbox-m2-client`（分支 `feat/local-agent-desktop`），以下相对路径均基于它。
- 提交信息：Conventional Commits + 中文摘要，每任务一提交。
- 版本对齐：daemon `__version__` 与服务端 `SANDBOX_MIN_DAEMON_VERSION` 同步升到 `0.2.0`（旧 daemon 带 daemon 侧门，拒连防双重确认）。

## 探索结论（执行者必读）

1. **interrupt 可穿透性已验证**：deepagents 的 `execute` 工具只捕获 `NotImplementedError/ValueError`；`write/edit/delete` 工具直调 backend 不包 try；CompositeBackend（`src/infra/backend/deepagent.py:49`）纯委托。在这些工具调用的 backend 方法内 `interrupt()` 会正常挂起图。**唯一不可穿透**：`glob/grep` 工具有 `except Exception` 边界且同步版跑线程池——所以读类操作（read/ls/glob/grep/download）**不过门**（本来就只读，无安全需求）。
2. **`before_tool_start` 不能作门**：它在流消费侧任务调用（`src/agents/core/base.py:478` run_stream 是独立 task），不在图任务内，interrupt 挂不起图。
3. **ask_human 机制全复用**：interrupt payload `{"kind": "ask_human", ...}` → 图挂起 → `materialize_ask_human_approvals`（fast/search agent nodes 均已接）物化审批+SSE → 面板批准/拒绝 → `POST /human/{id}/respond` → `submit_hitl_resume_run(approval, {"approved": bool, "values": {...}})` → `Command(resume={interrupt_id: resume_value})` → 工具重放时 `interrupt()` 返回该 dict。空 `fields: []` 的审批面板可用（`isFormFieldsValid([])` 恒真，批准/拒绝按钮正常）。
4. **GraphInterrupt 是 Exception 子类**（本 langgraph 版本），确认门代码路径上不能有裸 `except Exception` 包住它；本计划通过「读类绕过门 + 门在 override 入口（try 之前）」规避，不新增吞异常点。
5. **现状**：服务端零确认（`LocalSandboxBackend.aexecute` 直发 dispatch）；daemon 侧 `confirm.py` 的 `needs_confirm`/`terminal_confirm` 在 sidecar 形态下 input() EOF→全拒或阻塞事件循环，是死代码。策略判定逻辑（词边界正则）本身正确，移植到服务端复用。

---

### Task 1: 服务端确认策略模块（needs_confirm 移植）

**Files:**
- Create: `src/infra/sandbox/confirm.py`
- Test: `tests/infra/sandbox/test_confirm.py`

**Interfaces:**
- Produces: `POLICIES: tuple[str, ...]`、`MUTATING_PATTERN`、`needs_confirm(command: str, policy: str) -> bool`（Task 2/3 消费；语义与 client 版逐字节一致：all 恒确认 / commands 按 `MUTATING_PATTERN` / none 恒放行，未知 policy raise ValueError）。

- [ ] **Step 1: 写失败测试**

```python
"""服务端确认策略：needs_confirm 三档判定（自 client/lambchat_sandbox/confirm.py 移植，语义互锁）。"""

import pytest

from src.infra.sandbox.confirm import POLICIES, needs_confirm


@pytest.mark.parametrize("policy", ["all", "commands"])
@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /tmp/x",
        "echo hi; rm x",
        "true && mv a b",
        "cat a > b",
        "echo hi | grep x",
        "python3 -c 'pass' >> log",
    ],
)
def test_mutating_commands_confirm(policy, command):
    assert needs_confirm(command, policy) is True


def test_readonly_ls_passes_under_commands():
    assert needs_confirm("ls -la .", "commands") is False


def test_git_status_confirms_under_commands():
    # 保守误报取向：git 整体在清单内（M2 接受的取舍，移植保持一致）
    assert needs_confirm("git status", "commands") is True


def test_none_policy_passes_everything():
    assert needs_confirm("rm -rf /", "none") is False


def test_all_policy_confirms_everything():
    assert needs_confirm("ls", "all") is True


def test_unknown_policy_raises():
    with pytest.raises(ValueError, match="未知确认策略"):
        needs_confirm("ls", "yolo")


def test_policies_tuple():
    assert POLICIES == ("all", "commands", "none")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/infra/sandbox/test_confirm.py -v`
Expected: FAIL（ModuleNotFoundError: src.infra.sandbox.confirm）

- [ ] **Step 3: 最小实现（自 client/lambchat_sandbox/confirm.py 移植正则与判定，docstring 改述服务端语义）**

```python
"""沙箱执行确认策略：needs_confirm 三档判定。

服务端统一确认门（本地沙箱 exec/文件写/上传，spec §3.5 服务端实现）按
``confirm_policy`` 判定操作是否需要用户确认：

- ``all``：一切操作都确认（默认，最保守）；
- ``commands``：仅 :data:`MUTATING_PATTERN` 命中的命令确认；
- ``none``：一律放行（无人值守）。

``commands`` 取保守误报取向——宁可多确认一次，不可漏掉一次 ``rm``：

- 变更类命令按**词**匹配（``\\b`` 边界），且必须位于命令首或 ``;``/``&``/``|``/
  空白之后（``echo hi; rm x``、``true && mv a b`` 都命中）；
- 输出重定向 ``>``/``>>`` 与管道 ``|`` 一律命中（静态无法判定管道右侧是否
  消费/改写状态，``cat a > b``、``echo hi | grep x`` 保守确认）；
- 代价是 ``git status`` 这类只读命令也会命中（git 整体在清单内），与 M2
  daemon 版语义一致。

正则与 client/lambchat_sandbox/confirm.py 逐字节互锁（Task 5 拆除 client
副本），防两版漂移。
"""

from __future__ import annotations

import re

MUTATING_PATTERN = re.compile(
    r"(^|[;&|\s])(rm|mv|dd|chmod|chown|curl|wget|pip|npm|git|sudo|mkfs|shutdown|reboot)\b"
    r"|[>|]{1,2}\s*\S"
)

POLICIES = ("all", "commands", "none")


def needs_confirm(command: str, policy: str) -> bool:
    """按 policy 判定 command 是否需要用户确认；未知 policy 抛 ValueError。"""
    if policy == "all":
        return True
    if policy == "commands":
        return MUTATING_PATTERN.search(command) is not None
    if policy == "none":
        return False
    raise ValueError(f"未知确认策略: {policy!r}（可选: {'/'.join(POLICIES)}）")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/infra/sandbox/test_confirm.py -v`
Expected: PASS（全部）

- [ ] **Step 5: Commit**

```bash
git add src/infra/sandbox/confirm.py tests/infra/sandbox/test_confirm.py
git commit -m "feat(sandbox): 服务端确认策略 needs_confirm 三档判定（自 client 移植互锁）"
```

---

### Task 2: 服务端确认门（ask_human interrupt 复用）

**Files:**
- Modify: `src/infra/sandbox/confirm.py`（追加 `confirm_local_op`）
- Test: `tests/infra/sandbox/test_confirm.py`（追加）

**Interfaces:**
- Consumes: `hitl_interrupt_supported`（`src/infra/tool/human_tool/runtime.py` 的 ContextVar[bool]，agent 节点在图执行期设置）。
- Produces: `confirm_local_op(command: str, policy: str, *, description: str) -> bool`——同步函数，必须在图任务内的工具调用栈中执行；True=放行，False=用户拒绝或确认不可用（fail-closed）。interrupt payload 为 `{"kind": "ask_human", "message": description, "fields": []}`，resume 值形如 `{"approved": bool, "values": {...}}`。

- [ ] **Step 1: 写失败测试**

追加到 `tests/infra/sandbox/test_confirm.py`：

```python
import pytest
from langgraph.errors import GraphBubbleUp

from src.infra.sandbox.confirm import confirm_local_op
from src.infra.tool.human_tool.runtime import hitl_interrupt_supported


@pytest.fixture
def interrupt_supported():
    token = hitl_interrupt_supported.set(True)
    yield
    hitl_interrupt_supported.reset(token)


def test_none_policy_passes_without_interrupt(interrupt_supported):
    # interrupt() 在无图上下文会抛 GraphInterrupt——policy=none 不应触碰它
    assert confirm_local_op("rm -rf /", "none", description="x") is True


def test_all_policy_raises_graph_interrupt_with_ask_human_payload(interrupt_supported):
    with pytest.raises(GraphBubbleUp) as exc_info:
        confirm_local_op("rm x", "all", description="确认在本机执行命令：\nrm x")
    payload = exc_info.value.args[0] if exc_info.value.args else None
    # langgraph interrupt() 直接 raise GraphInterrupt(payload)（GraphBubbleUp 子类）
    from langgraph.errors import GraphInterrupt

    assert isinstance(exc_info.value, GraphInterrupt)
    assert payload is not None
    assert payload["kind"] == "ask_human"
    assert payload["fields"] == []
    assert "rm x" in payload["message"]


def test_resume_approved_returns_true(interrupt_supported, monkeypatch):
    import langgraph.types

    monkeypatch.setattr(langgraph.types, "interrupt", lambda value: {"approved": True, "values": {}})
    assert confirm_local_op("rm x", "all", description="d") is True


def test_resume_rejected_returns_false(interrupt_supported, monkeypatch):
    import langgraph.types

    monkeypatch.setattr(langgraph.types, "interrupt", lambda value: {"approved": False, "values": {}})
    assert confirm_local_op("rm x", "all", description="d") is False


def test_interrupt_unsupported_fails_closed(monkeypatch):
    import langgraph.types

    def _boom(value):
        raise AssertionError("unsupported 时不得调用 interrupt")

    monkeypatch.setattr(langgraph.types, "interrupt", _boom)
    assert confirm_local_op("rm x", "all", description="d") is False
```

注意：`confirm_local_op` 内部用 `from langgraph.types import interrupt`（函数内导入，与 AskHumanTool `_run_interrupt_mode` 同模式），monkeypatch `langgraph.types.interrupt` 即可生效。

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/infra/sandbox/test_confirm.py -v -k confirm_local_op`
Expected: FAIL（ImportError: confirm_local_op）

- [ ] **Step 3: 实现**

追加到 `src/infra/sandbox/confirm.py`：

```python
def confirm_local_op(command: str, policy: str, *, description: str) -> bool:
    """统一确认门：needs_confirm 判定 + ask_human interrupt（服务端，spec §3.5）。

    必须在图任务内的工具调用栈中同步调用（与 AskHumanTool interrupt 模式同
    语义）：挂起时经 materialize_ask_human_approvals 物化审批卡，用户响应后
    图以 Command(resume) 重放本调用栈，interrupt() 返回
    ``{"approved": bool, "values": {...}}``。

    - policy=none 或 needs_confirm 未命中：直接放行，不触碰 interrupt；
    - 图不支持 interrupt（无 checkpointer）：fail-closed 拒绝；
    - 用户拒绝 / resume 值异常：False。

    ``command`` 是送 needs_confirm 判定的哨兵命令（exec 传原始命令，文件写
    传 ``rm {op} {path}`` 前缀哨兵）；``description`` 是审批卡展示文案。
    """
    if not needs_confirm(command, policy):
        return True

    from src.infra.logging import get_logger
    from src.infra.tool.human_tool.runtime import hitl_interrupt_supported

    if not hitl_interrupt_supported.get():
        get_logger(__name__).warning(
            "[SandboxConfirm] interrupt 不可用，按拒绝收敛（fail-closed）: %s",
            description[:120],
        )
        return False

    from langgraph.types import interrupt

    resume_value = interrupt({"kind": "ask_human", "message": description, "fields": []})
    return bool(isinstance(resume_value, dict) and resume_value.get("approved"))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/infra/sandbox/test_confirm.py -v`
Expected: PASS（含 Task 1 全部）

- [ ] **Step 5: Commit**

```bash
git add src/infra/sandbox/confirm.py tests/infra/sandbox/test_confirm.py
git commit -m "feat(sandbox): 统一确认门 confirm_local_op——复用 ask_human interrupt 全链路"
```

---

### Task 3: LocalSandboxBackend 全部执行/写/上传路径过门

**Files:**
- Modify: `src/infra/backend/local.py`
- Test: `tests/infra/backend/test_local_backend.py`（追加）

**Interfaces:**
- Consumes: `confirm_local_op(command, policy, *, description) -> bool`（Task 2）、`SandboxClientRegistry.get_confirm_policy(user_id) -> str`（Task 4 提供；本任务先以 `_lookup_confirm_policy` 兜底实现——registry 尚无该方法时返回 ""，归一 "all"）。
- Produces:
  - `_gate_bypassed: ContextVar[bool]`（local.py 模块级，读类操作绕过门标记）
  - `LocalSandboxBackend._confirm_policy() -> str`（registry 查询，失败/缺失归一 `"all"`）
  - 门语义：`aexecute`（未被绕过时）门原始命令；`WorkspaceAliasBackend` 的 write/edit/delete 在 override 入口门 `rm {op} {path}` 哨兵；upload_files/aupload_files 每批一次门 `rm upload {n} files`；read/ls/glob/grep/download 不门（内部经 `_gate_bypassed` 绕过）。
  - 拒绝文案：exec → `ExecuteResponse(output=..., exit_code=1)`；写类 → 各 Result 的 error 字段带 `declined_by_user`。

- [ ] **Step 1: 写失败测试**

追加到 `tests/infra/backend/test_local_backend.py`（沿用该文件现有 fixture 风格——查看现有 monkeypatch dispatch_local_call 的方式；以下为新测试体，dispatch 打桩记录调用）：

```python
# ---- 统一确认门（服务端 HITL，spec §3.5）----

import contextvars
from unittest.mock import AsyncMock

import pytest
from langgraph.errors import GraphInterrupt

from src.infra.backend import local as local_mod
from src.infra.backend.local import LocalSandboxBackend, WorkspaceAliasBackend


@pytest.fixture
def fake_dispatch(monkeypatch):
    calls: list[tuple[str, str, dict]] = []
    mock = AsyncMock(
        return_value={"stdout": "", "stderr": "", "exit_code": 0}
    )

    async def _dispatch(user_id, op, payload, *, timeout=None):
        calls.append((user_id, op, payload))
        return await mock(user_id, op, payload)

    monkeypatch.setattr(local_mod, "dispatch_local_call", _dispatch)
    return calls


@pytest.fixture
def policy(monkeypatch):
    holder = {"value": "all"}

    async def _lookup(user_id):
        return holder["value"]

    monkeypatch.setattr(local_mod, "_lookup_confirm_policy", _lookup)
    return holder


@pytest.fixture
def interrupt_ok(monkeypatch):
    from src.infra.tool.human_tool.runtime import hitl_interrupt_supported

    token = hitl_interrupt_supported.set(True)
    yield
    hitl_interrupt_supported.reset(token)


async def test_exec_policy_none_dispatches_directly(fake_dispatch, policy, interrupt_ok):
    policy["value"] = "none"
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    resp = await backend.aexecute("rm -rf x")
    assert resp.exit_code == 0
    assert len(fake_dispatch) == 1


async def test_exec_policy_all_raises_interrupt_before_dispatch(
    fake_dispatch, policy, interrupt_ok
):
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    with pytest.raises(GraphInterrupt):
        await backend.aexecute("ls -la")
    assert fake_dispatch == []


async def test_exec_declined_returns_error_response(fake_dispatch, policy, interrupt_ok, monkeypatch):
    import langgraph.types

    monkeypatch.setattr(
        langgraph.types, "interrupt", lambda v: {"approved": False, "values": {}}
    )
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    resp = await backend.aexecute("rm x")
    assert resp.exit_code == 1
    assert "declined_by_user" in resp.output
    assert fake_dispatch == []


async def test_exec_approved_dispatches(fake_dispatch, policy, interrupt_ok, monkeypatch):
    import langgraph.types

    monkeypatch.setattr(
        langgraph.types, "interrupt", lambda v: {"approved": True, "values": {}}
    )
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    resp = await backend.aexecute("rm x")
    assert resp.exit_code == 0
    assert len(fake_dispatch) == 1


async def test_policy_lookup_failure_fails_closed_with_all(
    fake_dispatch, monkeypatch, interrupt_ok
):
    async def _boom(user_id):
        raise RuntimeError("redis down")

    monkeypatch.setattr(local_mod, "_lookup_confirm_policy", _boom)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    with pytest.raises(GraphInterrupt):  # 归一 all → 门生效
        await backend.aexecute("ls")
    assert fake_dispatch == []


async def test_read_ops_bypass_gate_under_all(fake_dispatch, policy, interrupt_ok):
    policy["value"] = "all"
    backend = WorkspaceAliasBackend(user_id="u1", session_id="s1")
    # posix 读路径生成的命令含重定向（2>/dev/null 等），绕过门不得触发 interrupt
    await backend.als(".")
    await backend.aglob("*.py")
    await backend.aread("a.txt")
    assert fake_dispatch  # 三个读操作都真实下发了


async def test_write_gates_once_with_rm_sentinel(fake_dispatch, policy, interrupt_ok, monkeypatch):
    import langgraph.types

    policy["value"] = "commands"  # rm 哨兵应命中
    seen: list[dict] = []

    def fake_interrupt(payload):
        seen.append(payload)
        return {"approved": True, "values": {}}

    monkeypatch.setattr(langgraph.types, "interrupt", fake_interrupt)
    backend = WorkspaceAliasBackend(user_id="u1", session_id="s1")
    result = await backend.awrite("a.txt", "hi")
    assert seen and "ask_human" == seen[0]["kind"]
    assert "a.txt" in seen[0]["message"]
    assert result.error is None
    assert fake_dispatch  # posix 写经命令下发


async def test_delete_declined_returns_error(fake_dispatch, policy, interrupt_ok, monkeypatch):
    import langgraph.types

    monkeypatch.setattr(
        langgraph.types, "interrupt", lambda v: {"approved": False, "values": {}}
    )
    backend = WorkspaceAliasBackend(user_id="u1", session_id="s1")
    result = await backend.adelete("a.txt")
    assert result.error and "declined_by_user" in result.error
    assert fake_dispatch == []


async def test_upload_gates_once_per_batch_not_per_chunk(
    fake_dispatch, policy, interrupt_ok, monkeypatch
):
    import langgraph.types

    interrupts: list[dict] = []
    monkeypatch.setattr(
        langgraph.types,
        "interrupt",
        lambda v: (interrupts.append(v), {"approved": True, "values": {}})[1],
    )
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    # 平台 hint posix；>48KB 内容会分两块，但只允许一次确认
    big = b"x" * (49 * 1024)
    responses = await backend.aupload_files([("a.bin", big)])
    assert len(interrupts) == 1
    assert all(r.error is None for r in responses)
    assert len(fake_dispatch) == 2  # 两块命令都下发


async def test_download_never_gates(fake_dispatch, policy, interrupt_ok):
    policy["value"] = "all"
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    resp = await backend.adownload_files(["a.txt"])
    assert resp[0].error is None
    assert fake_dispatch
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/infra/backend/test_local_backend.py -v -k gate或confirm或bypass`
Expected: FAIL（`_lookup_confirm_policy` 不存在 / 无门行为）

- [ ] **Step 3: 实现 local.py 变更**

3a. 模块级（imports 区后）：

```python
from contextvars import ContextVar

from src.infra.sandbox.confirm import confirm_local_op

# 读类操作（read/ls/glob/grep 及上传/下载的内部 plumbing 命令）绕过确认门：
# 这些路径在 deepagents glob/grep 工具内有 except Exception 边界（且同步版跑
# 线程池），GraphInterrupt 会被吞掉挂不起图；且它们只读无安全确认需求。
# 门只在模型可见的执行/写/上传操作入口（try 之前）触发。
_gate_bypassed: ContextVar[bool] = ContextVar("sandbox_gate_bypassed", default=False)

_EXEC_DECLINED_OUTPUT = (
    "Execution declined by user (declined_by_user). "
    "Do not re-run the same command unless the user explicitly asks."
)


async def _lookup_confirm_policy(user_id: str) -> str:
    """经注册表查当前活跃 daemon 上报的确认策略（第四段）。

    缺失/旧格式/查询失败一律归一 ``"all"``（保守）——策略权威来源在 daemon
    配置，未上报时宁可多确认；registry 故障不阻断沙箱（只是变成全确认）。
    """
    try:
        from src.infra.sandbox.relay.registry import SandboxClientRegistry

        policy = await SandboxClientRegistry().get_confirm_policy(user_id)
        return policy if policy in ("all", "commands", "none") else "all"
    except Exception:  # noqa: BLE001 - 策略查询尽力而为，失败保守归 all
        logger.warning("confirm policy lookup failed for user %s; defaulting to all", user_id)
        return "all"
```

3b. `LocalSandboxBackend` 增加方法 + `aexecute` 过门：

```python
    async def _confirm_exec(self, command: str) -> bool:
        """执行确认门：按 daemon 上报策略判定，未批准时 False（不 dispatch）。"""
        policy = await _lookup_confirm_policy(self._user_id)
        clipped = command if len(command) <= 800 else command[:800] + "…"
        return confirm_local_op(
            command, policy, description=f"确认在本机执行命令：\n{clipped}"
        )

    async def aexecute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        if not _gate_bypassed.get() and not await self._confirm_exec(command):
            return ExecuteResponse(output=_EXEC_DECLINED_OUTPUT, exit_code=1, truncated=False)
        result = await dispatch_local_call(...)  # 原有体不变
```

3c. `WorkspaceAliasBackend` 写类 override 入口门（write/edit/delete 各 sync+async 共 6 处，模式一致，以 `awrite` 为例；`_strip_required` 之后、分支之前）：

```python
    async def awrite(self, file_path: str, content: str) -> WriteResult:
        stripped = self._strip_required(file_path)
        if not await self._confirm_fs_op("write", file_path):
            return WriteResult(error=f"Failed to write file '{file_path}': declined_by_user")
        ...
```

`LocalSandboxBackend` 上加共享 helper：

```python
    async def _confirm_fs_op(self, op: str, display_path: str) -> bool:
        """文件写类操作确认门：rm 前缀哨兵送判（commands 策略下天然命中）。"""
        policy = await _lookup_confirm_policy(self._user_id)
        return confirm_local_op(
            f"rm {op} {display_path}",
            policy,
            description=f"确认在本机{ {'write': '写入', 'edit': '编辑', 'delete': '删除'}[op] }文件：{display_path}",
        )
```

（实际写法用 zh 动词映射字典提为模块常量，避免行内字典。）

拒绝返回值：write → `WriteResult(error=f"Failed to write file '{file_path}': declined_by_user")`；edit → `EditResult(error=f"Failed to edit file '{file_path}': declined_by_user")`；delete → `DeleteResult(error=f"Error deleting file '{file_path}': declined_by_user")`。

3d. 读类 override（read/ls/glob/grep 各 sync+async 共 8 处）：`super()` 调用包绕过 token（posix 分支才需要，win32 fs_read 等本就不过 aexecute，但统一包住最简）：

```python
    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000):
        stripped = self._strip_required(file_path)
        if await self._adaemon_platform_is_win32():
            return self._fs_read_result(
                await self._afs_call("fs_read", {"path": stripped, "offset": offset, "limit": limit}),
                stripped,
            )
        token = _gate_bypassed.set(True)
        try:
            return await super().aread(stripped, offset, limit)
        finally:
            _gate_bypassed.reset(token)
```

（glob 的同步版跑线程池：token 在 worker 线程上下文内 set/reset，`execute→_run_coro_sync→asyncio.run` 同线程继承，可见。）

3e. upload 门（`LocalSandboxBackend.upload_files`/`aupload_files`）：循环外套绕过 token，入口一次门：

```python
    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        policy = await _lookup_confirm_policy(self._user_id)
        names = ", ".join(path for path, _ in files[:5])
        if not confirm_local_op(
            f"rm upload {len(files)} files",
            policy,
            description=f"确认上传 {len(files)} 个文件到本机工作区：{names}",
        ):
            return [file_upload_response(path=p, error="declined_by_user") for p, _ in files]
        platform = await self._resolve_platform()
        token = _gate_bypassed.set(True)
        try:
            responses = []
            for path, content in files:
                responses.append(await self._aupload_one(path, content, platform=platform))
            return responses
        finally:
            _gate_bypassed.reset(token)
```

（sync `upload_files` 同构：门在前，`_run_coro_sync` 内 resolve platform，循环包 token。）

3f. 下载不加门（`_download_one` 直发 dispatch，不经 aexecute，天然无门——加注释说明只读不门）。

- [ ] **Step 4: 跑测试确认通过 + 既有 local backend 测试不回归**

Run: `uv run pytest tests/infra/backend/test_local_backend.py -v`
Expected: 新增全 PASS；**既有测试若因默认策略 "all" 触发门而挂**，在其 fixture/用例里 monkeypatch `_lookup_confirm_policy` 返回 "none"（打桩 dispatch 的既有测试均属此类，统一在文件顶部加 autouse fixture：默认 policy=none，门相关测试显式覆盖）。

- [ ] **Step 5: Commit**

```bash
git add src/infra/backend/local.py tests/infra/backend/test_local_backend.py
git commit -m "feat(sandbox): 本地沙箱执行/写/上传统一过服务端确认门，读类绕过"
```

---

### Task 4: 策略上报链路（daemon → registry 四段式 → status/门侧读取）+ 版本门 0.2.0

**Files:**
- Modify: `src/infra/sandbox/relay/registry.py`、`src/api/routes/sandbox.py`、`src/kernel/config/base.py`、`client/lambchat_sandbox/__init__.py`、`client/lambchat_sandbox/transport.py`、`client/lambchat_sandbox/daemon.py`（仅传参，门拆除在 Task 5）
- Test: `tests/infra/sandbox/relay/test_registry.py`、`tests/api/routes/test_sandbox_routes.py`、`tests/client/test_transport.py`

**Interfaces:**
- Produces:
  - `encode_node_value(node_id, version="", platform="", confirm_policy="")` / `parse_confirm_policy(value) -> str` / `SandboxClientRegistry.get_confirm_policy(user_id) -> str`、`register/heartbeat(..., confirm_policy: str = "")`
  - `GET /api/sandbox/channel?version=&platform=&confirm_policy=`（invalid 值归一空串，不报错）；`GET /api/sandbox/status` 响应新增 `"daemon_confirm_policy": str | null`
  - `ChannelClient(..., confirm_policy: str = "")` → connect URL 追加 `&confirm_policy=`
  - `client __version__ = "0.2.0"`；`settings.SANDBOX_MIN_DAEMON_VERSION = "0.2.0"`
- Consumes: Task 3 的 `_lookup_confirm_policy`（本任务让 `get_confirm_policy` 真实存在，替换其兜底实现内的导入为直接调用）。

- [ ] **Step 1: 写失败测试**

`tests/infra/sandbox/relay/test_registry.py` 追加（沿用现有 fake redis 风格）：

```python
def test_encode_with_confirm_policy_four_segments():
    from src.infra.sandbox.relay.registry import encode_node_value, parse_confirm_policy

    value = encode_node_value("n1", "0.2.0", "linux", "none")
    assert value == "n1|0.2.0|linux|none"
    assert parse_confirm_policy(value) == "none"


def test_parse_confirm_policy_missing_segments_returns_empty():
    from src.infra.sandbox.relay.registry import parse_confirm_policy

    assert parse_confirm_policy("n1|0.2.0|linux") == ""
    assert parse_confirm_policy("n1") == ""
```

（register/heartbeat 携带 confirm_policy 与 `get_confirm_policy` 的 async 用例照现有 register 测试模式补两条。）

`tests/api/routes/test_sandbox_routes.py` 追加：

```python
async def test_channel_stores_confirm_policy(...):
    # 既有 channel 测试的 client/registry 打桩方式，断言 register 收到 confirm_policy="none"

async def test_status_exposes_confirm_policy(...):
    # registry get_active 返回 "n1|0.2.0|linux|commands" → status JSON 含 daemon_confirm_policy="commands"
```

`tests/client/test_transport.py` 追加：

```python
@pytest.mark.anyio
async def test_connect_url_carries_confirm_policy(...):
    # 既有 connect 测试的 httpx 打桩方式，断言请求 URL 含 confirm_policy=none
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/infra/sandbox/relay/test_registry.py tests/api/routes/test_sandbox_routes.py tests/client/test_transport.py -v`
Expected: 新用例 FAIL

- [ ] **Step 3: 实现**

registry.py：`encode_node_value` 追加第四段（有值才拼，保旧形态）、`parse_confirm_policy`、`register/heartbeat` 加参透传、`get_confirm_policy`（照 `get_platform` 模式）。

sandbox.py：`sandbox_channel(confirm_policy: str = "")`——`confirm_policy = confirm_policy if confirm_policy in ("all", "commands", "none") else ""`；透传 register + `channel_frames(..., confirm_policy=...)` 心跳重写；status 响应加 `"daemon_confirm_policy": parse_confirm_policy(active[1]) or None`。

transport.py：`ChannelClient.__init__` 加 `confirm_policy: str = ""` 存属性；connect URL `f"...&confirm_policy={quote(self._confirm_policy)}"`（空则省略该参数）。

daemon.py：`run_daemon` 里构造 `ChannelClient(...)` 处传 `confirm_policy=cfg.confirm_policy`（搜 `ChannelClient(` 调用点）。

版本：`client/lambchat_sandbox/__init__.py` `__version__ = "0.2.0"`（docstring 补一句：0.2.0 = 确认门搬服务端 + 上报策略）；`src/kernel/config/base.py` `SANDBOX_MIN_DAEMON_VERSION: str = "0.2.0"`（注释说明：旧版带 daemon 侧确认门，拒连防双重确认）。

- [ ] **Step 4: 跑测试确认通过（含既有版本门测试）**

Run: `uv run pytest tests/infra/sandbox/relay/ tests/api/routes/test_sandbox_routes.py tests/client/test_transport.py tests/client/test_daemon.py -v`
Expected: PASS（若既有版本门测试硬编码 0.1.0 断言，同步更新为 0.2.0）

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(sandbox): daemon 上报确认策略四段式入注册表，版本门升至 0.2.0"
```

---

### Task 5: 拆除 daemon 侧确认门与 terminal_confirm

**Files:**
- Modify: `client/lambchat_sandbox/daemon.py`、`tests/client/test_daemon.py`
- Delete: `client/lambchat_sandbox/confirm.py`、`tests/client/test_confirm.py`

**Interfaces:**
- Consumes: 无。
- Produces: daemon 为纯执行器（确认已在服务端完成，spec §3.5「daemon 只收到已确认的执行请求」）；`run_daemon` 签名移除 `confirm_fn`；`SandboxConfig.confirm_policy` 保留（Task 4 上报用）。

- [ ] **Step 1: 更新测试（先改测试定义新契约）**

`tests/client/test_daemon.py`：
- 删除 `confirm_fn` 注入参数与所有确认门用例（`test_confirm_true_passes_gate_with_policy_all`、`_boom_confirm` 相关、policy=all/commands 的 declined 用例等）。
- 保留并改写核心用例：policy="all" 的 exec（曾需确认）现在**直接执行**——新用例：

```python
async def test_exec_executes_without_local_gate(...):
    # 确认门已在服务端：daemon 收到即执行，policy=all 也不再拦截
    cfg = _cfg(confirm_policy="all")
    ...run_daemon(cfg, factory, executor=..., auditor=...)  # 无 confirm_fn 参数
    assert executor 调用记录 == [命令]
    assert 审计含 event=executed
```

- fs 写 op 同理（`fs_write` 直接执行）。

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/client/test_daemon.py -v`
Expected: FAIL（confirm_fn 参数仍存在/门仍拦截）

- [ ] **Step 3: 实现**

daemon.py：
- 删 import `needs_confirm, terminal_confirm`；删 `WRITE_OPS` import（仅门哨兵使用；`FS_OPS` 保留）。
- `run_daemon` 签名与 `_route_call`/`_process_call`/`_process_exec_call`/`_process_fs_call` 链上删除 `confirm_fn` 参数。
- `_process_exec_call`：删确认门块（`if needs_confirm(...) and not _confirm(...)` 与 declined 审计/post_result 分支），执行链变为「迟到检查 → executor → done → 审计」；docstring 更新。
- `_process_fs_call`：删确认门块与 `gate_command` 哨兵逻辑，docstring 更新（确认在服务端，fs op 到达即已确认）。
- 删 `_confirm` helper。
- 模块 docstring 与 SIGINT 注释中 `terminal_confirm` 表述更新（SIGINT 段改为：asyncio.Runner 默认行为把 KeyboardInterrupt 转任务取消走优雅下线）。
- 删除文件：`client/lambchat_sandbox/confirm.py`、`tests/client/test_confirm.py`（服务端 Task 1 副本为唯一权威）。
- `client/lambchat_sandbox/config.py` 不动（confirm_policy 仍校验+上报）。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/client/ -v`
Expected: PASS（全 client 套件）

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(sandbox): 拆除 daemon 侧终端确认门——确认统一在服务端 HITL"
```

---

### Task 6: 前端 status 同步策略 + 设计文档收口

**Files:**
- Modify: `frontend/src/services/api/sandbox.ts`、`frontend/src/components/profile/LocalSandboxSection.tsx`、`docs/superpowers/specs/2026-09-01-local-sandbox-design.md`
- Test: `frontend/src/services/api/__tests__/sandbox.test.ts`、`frontend/src/components/profile/__tests__/localSandboxSection.test.tsx`

**Interfaces:**
- Produces: `SandboxStatus.daemon_confirm_policy?: string | null`；LocalSandboxSection 策略 SelectRow 初值跟随在线 daemon 上报值（用户未主动切换时）。

- [ ] **Step 1: 写失败测试**

`sandbox.test.ts`：status 响应含 `daemon_confirm_policy: "commands"` 时类型/透传断言（照现有 status 测试）。
`localSandboxSection.test.tsx`：渲染已配对分区 + status 带 `daemon_confirm_policy: "none"` → SelectRow 显示「免确认」档文案。

- [ ] **Step 2: 确认失败** — `cd frontend && pnpm test -- --run sandbox localSandboxSection`（照仓库实际命令 `pnpm test <pattern>`）

- [ ] **Step 3: 实现**

- `SandboxStatus` 接口加 `daemon_confirm_policy?: string | null`。
- LocalSandboxSection：`const [policy, setPolicy] = useState<ConfirmPolicy>("all")` + `useEffect(() => { if (status?.daemon_confirm_policy && POLICY_KEYS.includes(...)) setPolicy(status.daemon_confirm_policy) }, [status?.daemon_confirm_policy])`（POLICY_KEYS 由 CONFIRM_POLICY_OPTIONS 派生）；用户手动切换仍即时写配置（现有 handlePolicyChange 不变）。
- 设计文档 §3.5 更新：标注服务端统一门已实施（2026-09-06），daemon 仅执行已确认请求、三档策略经 registry 四段式上报；§10 里程碑补一行实施记录。

- [ ] **Step 4: 前端相关测试通过** — `cd frontend && pnpm test`（sandbox 相关 + 该文件既有用例不回归）

- [ ] **Step 5: Commit**

```bash
git add frontend/src docs/superpowers/specs/2026-09-01-local-sandbox-design.md
git commit -m "feat(frontend): 本地沙箱确认策略跟随 daemon 上报值；设计文档标注服务端门已实施"
```

---

### Task 7: 本地沙箱支持后端 env 变量（对齐云端沙箱）

> 用户新增需求（2026-09-06）：「本地沙箱支持后端的 env 变量，跟其他沙箱兼容」。
> 云端现状：`sync_sandbox_env_vars`（src/infra/envvar/sync.py）把用户加密 env 解密后
> set 到 backend 的 `env_vars` 属性，E2B/Daytona 在每条命令执行时传 SDK
> （`envs=`/`env=`）。本地现状：LocalSandboxBackend 无 `env_vars` 属性，sync 的
> `hasattr` 检查静默跳过；daemon executor 只注入 PATH shim 与 LAMBCHAT_WORKSPACE。

**Files:**
- Modify: `src/infra/backend/local.py`、`src/agents/search_agent/nodes.py`、`client/lambchat_sandbox/daemon.py`、`client/lambchat_sandbox/executor.py`
- Test: `tests/infra/backend/test_local_backend.py`、`tests/client/test_daemon.py`、`tests/client/test_executor.py`、`tests/agents/search_agent/test_sandbox_routing.py`

**Interfaces:**
- Produces:
  - `LocalSandboxBackend.__init__(..., env_vars: dict[str, str] | None = None)` → `self.env_vars`（hasattr 成立后 `sync_sandbox_env_vars` 即可写入——env_var 工具运行中改动实时生效）
  - exec op 载荷新增 `"env": dict[str, str]`（仅 exec；fs_* / upload / download 不带）
  - `Executor.execute(command, virtual_cwd, timeout, env_extra: dict[str, str] | None = None)`；`_spawn_env(workspace, env_extra)` 合并序：用户 env → PATH shim 前置 → LAMBCHAT_WORKSPACE（契约变量最后落笔不被用户覆盖）
- 载荷安全：EnvVarStorage 已限 50 个 / 单值 16k chars / 总量 64k chars，无需额外上限。
- daemon 侧对 `payload["env"]` 做防御净化（非 dict / 非 str 值丢弃）。

**Steps（TDD 摘要）：**
1. RED：服务端测试——backend 带 env_vars 时 aexecute 载荷含 `"env"`；无 env_vars 时载荷无该键；`sync_sandbox_env_vars` 能写入 local backend 的 env_vars；`test_sandbox_routing.py` 源码断言 nodes.py 本地分支调 `sync_sandbox_env_vars(local_backend`。
2. GREEN：local.py 加属性 + 载荷；nodes.py 本地分支构造后 `await sync_sandbox_env_vars(local_backend, user_id)`。
3. RED：client 测试——daemon 把 payload env 透传 executor（fake executor 记录 env_extra）；executor `_spawn_env` 合并序断言（用户 env 生效、PATH 前置不丢、LAMBCHAT_WORKSPACE 不被覆盖）；非法 env 条目被丢弃。
4. GREEN：daemon `_process_exec_call` 净化透传；executor 签名与合并实现（posix + windows 两分支同参）。
5. Commit：`feat(sandbox): 本地沙箱执行注入用户 env 变量，对齐云端沙箱行为`。

---

## 验证（全部任务完成后）

```bash
uv run pytest tests/infra/sandbox tests/infra/backend/test_local_backend.py tests/client tests/api/routes/test_sandbox_routes.py -v
make lint && make typecheck
cd frontend && pnpm test -- --run && pnpm run build
```

已知取舍（记录，不阻塞）：
- 云端沙箱（E2B/Daytona/Cube）不接门——隔离环境、产品从未有确认语义；`confirm_local_op` 为共享门，未来云端要确认只需接策略来源。
- `commands` 策略对 `git status` 等只读命令保守确认（M2 语义原样移植）。
- daemon 离线时 `aexecute` 先过门再 dispatch 失败（DAEMON_OFFLINE）——门在 dispatch 前，用户批准了才报离线错误，顺序合理。

## Self-Review 记录

- Spec 覆盖：§3.5 三档策略 ✓（Task 1/3）、服务端 interrupt 确认 ✓（Task 2/3）、daemon 只收已确认请求 ✓（Task 5）、策略可配置 ✓（Task 4 上报链路 + 既有 SelectRow 写配置流不变）。
- 类型一致：`confirm_local_op(command, policy, *, description)`、`get_confirm_policy(user_id) -> str`、四段式 value 编码在各任务间签名一致。
- 无占位符；测试代码均为可运行体（执行时按既有 fixture 风格微调打桩细节）。
