"""
Search Agent 系统提示词
- SANDBOX_SYSTEM_PROMPT: 沙箱模式，独立远程存储
- DEFAULT_SYSTEM_PROMPT: 非沙箱模式，统一路径管理

角色身份通过 SectionPromptMiddleware 独立注入（见 persona.py），
基础提示词只包含能力描述，保证全局 KV 缓存稳定。
"""

SANDBOX_SYSTEM_PROMPT = """## Storage Architecture (CRITICAL)

| System | Paths | Access |
|--------|-------|--------|
| Sandbox Local | current session workspace (`work_dir`) | shell commands and file tools |
| Remote Storage | `/skills/` | read/write/edit_file tools |

`/skills/` is virtual remote storage, not a sandbox filesystem path. Use file tools for `/skills/`; never shell-access it (`python /skills/x.py`, `cat /skills/x.md`, `cp /skills/* .`). The sandbox local path is provided at runtime as `Current session workspace`; use that session-id-specific workspace for shell commands, file tools, and absolute upload paths. To run skill code, transfer it into the current session workspace with `transfer_file`/`transfer_path`, then execute the copied file.

## URL File Upload
Use `upload_url_to_sandbox(url, file_path)` to download URLs to sandbox. `file_path` must be absolute inside the current session workspace.
"""

SANDBOX_RUNTIME_SECTION = """## Sandbox Runtime

Current session workspace: `{work_dir}`

This is the initial/default working directory for this session and is derived from the session id. Use this absolute directory for shell-created files, file tools, and absolute `upload_url_to_sandbox` paths. Keep this runtime value out of durable docs unless the user specifically asks for internal paths.
"""

DEFAULT_SYSTEM_PROMPT = """## File System
| Path | Purpose |
|------|---------|
| `/workflow/<session-id>` | Current session workflow files |
| `/skills/` | Skill library (editable, virtual — DB-backed) |

The default persistent file workspace is scoped by the current session id. Use the current session workflow for new files unless the user explicitly asks to work in an existing path.

`/skills/` is virtual storage, not a real filesystem directory. Use `ls`, `read_file`, `write_file`, and `edit_file` for skills; never shell-access `/skills/` (`ls -la /skills/`, `cat /skills/x.md`, `python /skills/x.py`). To execute a skill script, first copy it into the current session workflow or the sandbox session workspace via `transfer_file`/`transfer_path`.
"""

DEFERRED_TOOL_GUIDE = ""
