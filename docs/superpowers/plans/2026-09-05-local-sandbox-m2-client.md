# 本地沙箱 M2（客户端 daemon）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付真实可跑的本地沙箱 daemon（`client/lambchat_sandbox/`）：登录配对、SSE 通道常驻、tool_call 在本机受控执行并回传，外加四项服务端硬化，最终真机端到端冒烟。

**Architecture:** daemon 是无界面常驻进程：`login` 用账号密码换 PAT（一次性、scope 仅 `sandbox:execute`）→ `run` 连接服务端 `/api/sandbox/channel`（SSE），收到 `tool_call` 后按确认策略决定是否放行，经子进程在 `data_root` 下按会话映射的工作目录里执行，结果 POST 回 `/api/sandbox/results`；断线指数退避重连，退出时 POST `/api/sandbox/offline` 立即下线。服务端（M1 已交付）不动，仅加四项硬化（T7）。

**Tech Stack:** Python 3.12（同一 uv 工程）、httpx（主依赖，已有）、subprocess/os/asyncio（stdlib）。**零新增第三方依赖**。

**Spec:** `docs/superpowers/specs/2026-09-01-local-sandbox-design.md` §4（本地 daemon）+ M1 计划"M2 留存"清单的四个服务端项 + M1 真机冒烟的断连窗口观察。

## Global Constraints

- **零新增第三方依赖**（httpx 已是主依赖 pyproject:27；keyring 不引入）。
- daemon 代码在 `client/lambchat_sandbox/`（新顶层目录），**不得 import `src/` 任何模块**（spec §2 核心原则：客户端与服务平台仅经 HTTP API 交互）。
- 测试放 `tests/client/`（沿用仓库 pytest `testpaths=["tests"]` 约定；pyproject `[tool.pytest.ini_options]` 的 `pythonpath` 追加 `"client"`——T1 做）。服务端硬化测试进既有 tests/ 结构。
- 服务端改动遵守 M1 全部约束：AppError/ErrorCode、无 HTTPException、五语 i18n、Conventional Commits 中文。
- 与 spec 的已裁决偏差（记入 ledger）：① PAT 存储 = `~/.lambchat/pat` 0600 文件（spec §4.1 写 keyring；PAT 是可撤销单 scope 令牌非密码，0600 文件安全性同级，keyring 留作可选增强，避免新依赖）；② 配置项 v2 精简为 `server_url` / `data_root` / `confirm_policy`（spec §4 的 `roots` 多目录白名单依赖直接文件操作，M1 实现走 exec 后工作区收敛为 data_root 单根，roots 回归 M3 前端配对 UI 时再做）；③ 确认策略 M2 为**终端交互确认**（daemon 是前台 CLI；spec §3.5 的网页 HITL 确认是 M3）。

## File Structure

```
client/__init__.py                     # 空包标记（import client.lambchat_sandbox 兼容）
client/lambchat_sandbox/__init__.py
client/lambchat_sandbox/config.py      # SandboxConfig 加载/保存（~/.lambchat/sandbox.json）
client/lambchat_sandbox/auth.py        # PAT 存储（keyring 可选 → 0600 文件兜底）+ login 配对
client/lambchat_sandbox/transport.py   # ChannelClient：SSE 连接/解析/重连/结果回传/offline
client/lambchat_sandbox/executor.py    # 子进程执行 + 虚拟 cwd → data_root 会话目录映射
client/lambchat_sandbox/confirm.py     # 确认策略（all/commands/none）+ 终端 y/N
client/lambchat_sandbox/audit.py       # JSONL 审计（~/.lambchat/audit/{session}.jsonl）
client/lambchat_sandbox/daemon.py      # 主循环：wire 全部组件
client/lambchat_sandbox/cli.py         # argparse 入口：login/status/run/audit
client/lambchat_sandbox/__main__.py    # from .cli import main; main()
tests/client/test_config.py
tests/client/test_auth.py
tests/client/test_transport.py
tests/client/test_executor.py
tests/client/test_confirm.py
tests/client/test_audit.py
tests/client/test_daemon.py
tests/api/routes/test_sandbox_routes.py        # 改：offline 端点 + 陈旧请求丢弃
tests/infra/sandbox/relay/test_dispatch.py     # 改：req 含 ts
tests/infra/backend/test_local_backend.py      # 改：download 用 stdout 字段
src/api/routes/sandbox.py              # 改：offline 端点、channel 丢陈旧
src/infra/sandbox/relay/dispatch.py    # 改：req 加 ts
src/infra/backend/local.py             # 改：download 解码仅用 stdout
pyproject.toml                          # 改：pythonpath += "client"
.env.example                            # 改：SANDBOX_RESULTS_MAX_BYTES
src/kernel/config/base.py              # 改：SANDBOX_RESULTS_MAX_BYTES = 2097152
```

---

### Task 1: client 骨架 + 配置模块

**Files:**
- Create: `client/__init__.py`（空）、`client/lambchat_sandbox/__init__.py`（空）、`client/lambchat_sandbox/config.py`
- Modify: `pyproject.toml`（`[tool.pytest.ini_options]` `pythonpath = [".", "client"]`）
- Test: `tests/client/test_config.py`

**Interfaces:**
- Produces:

```python
@dataclass
class SandboxConfig:
    server_url: str = "http://127.0.0.1:8000"
    data_root: Path = Path.home() / ".lambchat" / "workspaces"
    confirm_policy: str = "all"          # all | commands | none

def config_path() -> Path                # ~/.lambchat/sandbox.json
def load_config(path: Path | None = None) -> SandboxConfig      # 不存在返回默认值；坏 JSON 抛 ConfigError
def save_config(cfg: SandboxConfig, path: Path | None = None) -> None  # 写 JSON（mkdir -p 父目录）
class ConfigError(Exception)
```

- [ ] **Step 1: 修改 pyproject** `[tool.pytest.ini_options]` 的 `pythonpath = [".", "client"]`（保留原有 "."）。
- [ ] **Step 2: 写失败测试**（tmp_path 隔离，monkeypatch HOME 或显式传 path——本模块全部显式传 path，不碰真实 HOME）

```python
"""SandboxConfig 加载/保存/校验。"""
import json

import pytest

from lambchat_sandbox.config import ConfigError, SandboxConfig, load_config, save_config


def test_load_missing_returns_default(tmp_path):
    cfg = load_config(tmp_path / "sandbox.json")
    assert cfg.server_url == "http://127.0.0.1:8000"
    assert cfg.confirm_policy == "all"


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "nested" / "sandbox.json"
    save_config(SandboxConfig(server_url="https://lc.example", confirm_policy="none"), p)
    assert json.loads(p.read_text())["server_url"] == "https://lc.example"
    assert load_config(p).confirm_policy == "none"


def test_load_invalid_confirm_policy_rejected(tmp_path):
    p = tmp_path / "sandbox.json"
    p.write_text(json.dumps({"confirm_policy": "yolo"}))
    with pytest.raises(ConfigError):
        load_config(p)


def test_load_broken_json_raises(tmp_path):
    p = tmp_path / "sandbox.json"
    p.write_text("{not json")
    with pytest.raises(ConfigError):
        load_config(p)
```

- [ ] **Step 3: 跑测试确认失败**：`uv run pytest tests/client/test_config.py -v` → FAIL（ModuleNotFoundError）。
- [ ] **Step 4: 实现 config.py**（dataclass + json，load 时校验 confirm_policy ∈ {all, commands, none}、server_url 以 http(s) 开头，违反抛 ConfigError）。
- [ ] **Step 5: 跑测试通过 + 既有测试不回归**（pythonpath 改动影响面：`uv run pytest tests -q` 快速全量）。
- [ ] **Step 6: Commit** `feat(sandbox): client 配置模块与 pytest 路径接入`

---

### Task 2: PAT 存储 + login 配对 CLI

**Files:**
- Create: `client/lambchat_sandbox/auth.py`、`client/lambchat_sandbox/cli.py`、`client/lambchat_sandbox/__main__.py`
- Test: `tests/client/test_auth.py`

**Interfaces:**
- Produces:

```python
PAT_FILE = Path.home() / ".lambchat" / "pat"
def store_pat(token: str, path: Path | None = None) -> None   # 0600 文件（keyring 可用则优先 keyring，失败静默落文件）
def load_pat(path: Path | None = None) -> str | None
def clear_pat(path: Path | None = None) -> None
async def pair(server_url: str, username: str, password: str) -> str
    # POST {server}/api/auth/login -> access_token；POST {server}/api/auth/pat
    # body {"name": "sandbox-daemon", "scopes": ["sandbox:execute"]} -> token；store_pat 后返回
    # 登录失败抛 AuthError（含服务端 detail.code），建 PAT 失败抛 AuthError
class AuthError(Exception)
```

- cli.py（argparse，main() 返回退出码）：`login`（交互式输 username/password，getpass；`--server` 覆盖配置并保存）、`status`（GET /api/sandbox/status 带 PAT，打印 JSON）、`run`（T6 接入，本任务先占位打印 "daemon 未实现" 返回 1）、`logout`（clear_pat）。
- [ ] **Step 1: 写失败测试**：store/load/clear 往返（显式 tmp path）；pair 用 httpx.MockTransport 假造 login/pat 两跳（成功路径 + invalid_credentials 抛 AuthError + 断言 PAT 请求体 scopes）。keyring 分支测试：monkeypatch `lambchat_sandbox.auth.keyring` 为 None 强制走文件路径。
- [ ] **Step 2: 确认失败** → **Step 3: 实现**（keyring `try: import keyring except ImportError: keyring = None`；文件分支 `os.chmod(path, 0o600)`；httpx.AsyncClient）→ **Step 4: 通过** → **Step 5: Commit** `feat(sandbox): PAT 存储与 login 配对 CLI`

---

### Task 3: transport（SSE 客户端 + 结果回传 + 重连）

**Files:**
- Create: `client/lambchat_sandbox/transport.py`
- Test: `tests/client/test_transport.py`

**Interfaces:**
- Consumes: 服务端契约（M1 已实测）：`GET /api/sandbox/channel` SSE 帧 `event: hello|tool_call` + `: heartbeat` 注释行；`POST /api/sandbox/results/{call_id}` body `{"stage","status","stdout","stderr","exit_code","error"}`；`POST /api/sandbox/offline`（T7 服务端补）。
- Produces:

```python
@dataclass
class ToolCall:
    call_id: str; op: str; payload: dict; timeout: float

class ChannelClient:
    def __init__(self, server_url: str, pat: str, *, client: httpx.AsyncClient | None = None)
    async def connect(self) -> AsyncIterator[ToolCall]     # 产出 tool_call；hello 返回前先 yield 出去交给 on_hello 回调？→ 简化：connect 返回 (hello_data, async_iterator)
    async def post_result(self, call_id: str, body: dict) -> None
    async def post_offline(self) -> None                   # 优雅退出通知
    async def close(self) -> None
def backoff_delay(attempt: int) -> float                   # 1,2,4,...封顶 60，±20% 抖动；纯函数可测
```

- 实现要点：`httpx.AsyncClient(timeout=None)` + `client.stream("GET", ...)` + `aiter_lines()` 解析 `event:`/`data:` 对（`data:` 可能跨行时合并——M1 服务端 json.dumps 单行，按单行处理并在解析失败时跳过该帧）；401/403 抛 `TransportAuthError`（不重连，提示重新 login）；网络错误由调用方（daemon）捕获后按 backoff 重连。
- [ ] **Step 1: 写失败测试**：httpx.MockTransport 假 SSE 流（hello + 两条 tool_call + 心跳注释）断言迭代产出与 hello 回传；backoff_delay 序列（1,2,4,8,...,60 封顶，抖动界内）；post_result/post_offline 的请求体与路径断言；401 抛 TransportAuthError。
- [ ] **Step 2-4: RED → 实现 → GREEN** → **Step 5: Commit** `feat(sandbox): daemon 传输层（SSE 通道客户端）`

---

### Task 4: executor（子进程执行 + 工作区映射）

**Files:**
- Create: `client/lambchat_sandbox/executor.py`
- Test: `tests/client/test_executor.py`

**Interfaces:**
- Produces:

```python
MAX_OUTPUT_BYTES = 256 * 1024
def map_workspace(virtual_cwd: str, data_root: Path) -> Path
    # "/workspace/{sid}" -> data_root/sid；非法（非 /workspace/ 前缀、含 ..、sid 含 /）抛 ExecutorError
class Executor:
    def __init__(self, data_root: Path)
    def execute(self, command: str, virtual_cwd: str, timeout: float) -> dict
        # {status: "ok"|"error", stdout, stderr, exit_code}；mkdir -p 工作区；subprocess.run(shell=True,
        # start_new_session=True)；超时 kill 整个进程组（os.killpg）后返回 status=error, error="timeout"；
        # stdout/stderr 各截断 256KB（尾部保留，头部加 "...[truncated]"）
```

- [ ] **Step 1: 写失败测试**（真实子进程）：echo 往返 exit_code/stdout；cwd 映射（写文件到 $PWD 验证落在 data_root/sid）；`cd ..` 逃逸不影响（shell cwd 就是工作区，子进程理论可逃逸——M2 接受，M3 HITL 治理，测试只锁映射正确性）；`sleep 5` + timeout=0.3 → 进程被杀、status=error；路径非法（"/etc"、"…"、"…/…"）抛 ExecutorError；输出超限截断（python3 -c 打印 300KB）。
- [ ] **Step 2-4: RED → 实现 → GREEN** → **Step 5: Commit** `feat(sandbox): daemon 执行器（工作区映射 + 子进程隔离超时）`

---

### Task 5: 确认策略 + 审计

**Files:**
- Create: `client/lambchat_sandbox/confirm.py`、`client/lambchat_sandbox/audit.py`
- Test: `tests/client/test_confirm.py`、`tests/client/test_audit.py`

**Interfaces:**
- Produces:

```python
MUTATING_PATTERN = re.compile(r"(^|[;&|\s])(rm|mv|dd|chmod|chown|curl|wget|pip|npm|git|sudo|mkfs|shutdown|reboot)\b|[>|]{1,2}\s*\S")
def needs_confirm(command: str, policy: str) -> bool
    # all → True；commands → MUTATING_PATTERN 命中；none → False；未知 policy 抛 ValueError
def terminal_confirm(command: str, *, input_fn=input) -> bool   # y/Y/yes → True，其余 False（可注入 input_fn 测）
class Auditor:
    def __init__(self, root: Path)               # ~/.lambchat/audit
    def log(self, session_id: str, event: dict) -> None   # 追加 JSONL，自动补 ts；失败吞异常（审计不阻断执行）
```

- [ ] **Step 1: 写失败测试**：needs_confirm 三策略 × 若干命令（`echo hi` / `rm -rf /tmp/x` / `cat a > b` / `git status`）；terminal_confirm（注入 input_fn="y"/"n"/"x"）；Auditor 追加两行可 json.loads 且含 ts、坏路径不抛。
- [ ] **Step 2-4: RED → 实现 → GREEN** → **Step 5: Commit** `feat(sandbox): 确认策略与 JSONL 审计`

---

### Task 6: daemon 主循环

**Files:**
- Create: `client/lambchat_sandbox/daemon.py`；Modify: `cli.py`（`run` 接入）
- Test: `tests/client/test_daemon.py`

**Interfaces:**
- Consumes: T2 load_pat、T3 ChannelClient/backoff_delay、T4 Executor、T5 needs_confirm/terminal_confirm/Auditor、T1 SandboxConfig
- Produces:

```python
async def run_daemon(cfg: SandboxConfig, *, pat: str, confirm_fn=terminal_confirm, client_factory=None,
                     executor: Executor | None = None, auditor: Auditor | None = None) -> None
# 单次连接处理 handler(channel, ...)：逐 ToolCall → auditor.log(received) →
#   needs_confirm 且 confirm_fn 为 False → post_result(done, status=error, error="declined_by_user") 并审计 declined
#   否则 post_result(ack) → executor.execute → post_result(done, stdout/stderr/exit_code/status) → 审计 executed
# 外层重连循环：TransportAuthError 直接抛（提示重 login）；其他异常 backoff_delay(n) 重试，Ctrl-C/SIGTERM → post_offline + close + 审计 shutdown
```

- [ ] **Step 1: 写失败测试**（注入 fake client_factory/executor/confirm_fn/内存 Auditor）：放行路径断言 ack→execute→done 顺序与 payload；拒绝路径断言 declined_by_user；confirm 抛异常不断连；ack 后执行超时 → done(status=error, error="timeout")。
- [ ] **Step 2-4: RED → 实现 → GREEN** → **Step 5: `PYTHONPATH=client uv run python -m lambchat_sandbox --help` 手验 CLI** → **Step 6: Commit** `feat(sandbox): daemon 主循环（配对执行审计重连一体化）`

---

### Task 7: 服务端硬化四小项

**Files:**
- Modify: `src/api/routes/sandbox.py`、`src/infra/sandbox/relay/dispatch.py`、`src/infra/backend/local.py`、`src/kernel/config/base.py`、`.env.example`
- Test: `tests/api/routes/test_sandbox_routes.py`、`tests/infra/sandbox/relay/test_dispatch.py`、`tests/infra/backend/test_local_backend.py`（各追加用例）

**Interfaces / 四项：**
1. **offline 端点**：`POST /api/sandbox/offline`（`require_pat_only("sandbox:execute")`）→ `registry.unregister(user.sub, 当前 client_id)`（从 get_active 取）→ 返回 `{"status": "offline"}`。收敛 M1 冒烟实证的断连窗口。
2. **陈旧请求丢弃**：dispatch 的 req 加 `"ts": time.time()`；`channel_frames` 下发前解析 ts，`time.time() - ts > settings.SANDBOX_LOCAL_ACK_TIMEOUT` 的请求丢弃（continue，不 yield）并打 debug 日志。dispatch 测试补 req["ts"] 断言；channel 测试补陈旧/新鲜两分支。
3. **results 上限**：`SANDBOX_RESULTS_MAX_BYTES: int = 2097152`（base.py + .env.example）；results 端点 `len(await request.body())` 超限 → `AppError(ErrorCode.SANDBOX_PAYLOAD_TOO_LARGE)`。
4. **download 解码修正**：local.py 的 `_download_response`/download 路径改为**只取 stdout 字段**（不经 aexecute 的 stdout+stderr 合并 output）——executor 返回 dict 含独立 stdout 字段时直接用；测试：stderr 非污染不混入 base64。

- 每项独立 RED→GREEN；全部完成后 `uv run pytest tests/api tests/infra -q` 回归。
- [ ] **Commit** `feat(sandbox): 服务端硬化——offline 通知/陈旧请求丢弃/结果上限/download 解码修正`

---

### Task 8: 真机端到端冒烟（真 daemon 替换模拟器）

**Files:** 无新代码；产出冒烟记录 `docs/superpowers/plans/2026-09-05-local-sandbox-m2-smoke.md`

- [ ] **Step 1: 起环境**：mongod（`~/.local/opt/mongodb/bin/mongod --dbpath /tmp/m1-mongo-data --fork --logpath /tmp/m1-mongod.log`）+ `uv run python main.py`（后台）。
- [ ] **Step 2: 配对**：`PYTHONPATH=client uv run python -m lambchat_sandbox login`（m1_smoke 账号）→ `status` 断言 online:false → `run` 后台起 → `status` 断言 online:true。
- [ ] **Step 3: 真实往返**：`uv run python -c` 调 `dispatch_local_call` 与 `LocalSandboxBackend.aexecute`（exec + `aread` 继承文件读），断言落点在 `~/.lambchat/workspaces/{sid}`（执行 `pwd > marker.txt` 后检查文件存在）。
- [ ] **Step 4: 确认与拒绝**：policy=all 下 dispatch `touch confirm-test`（MUTATING 命中）→ 终端输入 y 放行、再发一次输入 n → 断言 declined_by_user。
- [ ] **Step 5: 优雅退出**：SIGTERM → 立即（<2s）`status` online:false（offline 端点生效，对照 M1 的 15-35s 窗口）。
- [ ] **Step 6: 审计核对**：`~/.lambchat/audit/*.jsonl` 含 received/allowed/declined/executed 事件。
- [ ] **Step 7: 关环境 + 写冒烟记录 + Commit** `docs(sandbox): M2 真机冒烟记录`

## Self-Review 记录

- **Spec 覆盖**：spec §4.1 目录=全部文件；§4.2 执行/确认= T4/T5；§4.3 协议消费= T3；§4.5 CLI= T2/T6；M1"M2 留存"的服务端四项= T7（daemon 契约 stderr 独立字段在 T4 返回结构天然满足，local.py 侧由第 4 项闭环）；HITL 网页确认、Tauri、前端=M3（不在本计划）。
- **三条已裁决偏差**见 Global Constraints（keyring→0600 文件、roots→data_root、终端确认）。
- **类型一致性**：ToolCall(call_id/op/payload/timeout) 与 M1 服务端帧字段一致（timeout 已实测在帧里）；post_result body 键与 results 端点模型一致；map_workspace 的 virtual_cwd 约定与 local.py aexecute 的 `cwd: /workspace/{session_id}` 一致。
