"""
子代理共享提示词

主代理和子代理共用的子代理调用指南、系统提示词。
fast_agent / search_agent 均从此处导入，避免重复。
"""

# ---------------------------------------------------------------------------
# 共享 Workflow 段（fast_agent / search_agent 共用）
# ---------------------------------------------------------------------------

WORKFLOW_SECTION = """
## Workflow

### File Reveal (REQUIRED)
After creating/modifying files, MUST call `reveal_file` immediately. If the user asks to see/open/show a file, you MUST call `reveal_file`.
Returning only a file path is NOT sufficient. The user cannot directly access the isolated filesystem.
Call `write_file` first, wait for completion, then call `reveal_file` separately.

### Resource References in Documents (IMPORTANT)
When generating Markdown, HTML, or other documents that reference local resources (images, videos, audio, etc.), you MUST ensure those resources are accessible to the user:
1. Call `reveal_file` for each local resource file FIRST to upload it and get a publicly accessible URL.
2. Use the returned `url` (NOT the local file path) in your document's references.
3. NEVER use local sandbox paths (e.g., `/home/user/chart.png`, `./images/photo.jpg`) in document content — the user cannot access them.

Example:
```
# Wrong — user cannot see this image
![Sales Chart](./output/chart.png)

# Correct — reveal_file returns a URL, use that
# Step 1: reveal_file("/home/user/output/chart.png") → returns {"url": "https://..."}
# Step 2: ![Sales Chart](https://your-domain/api/upload/file/revealed_files/chart.png)
```

### Frontend Project Preview
For multi-file frontend projects, use `reveal_project(project_path, name, template?)` for browser preview.

### File Transfer
Different storage backends are routed by path prefix:
- `/skills/*` → skill store (MongoDB)
- Other paths → sandbox workspace (Daytona/E2B)

Tools:
- `transfer_file(src, dst)` — Transfer a **single** text file between any two backends (bidirectional).
- `transfer_path(src_dir, prefix)` — **Batch** transfer all files in a directory (bidirectional). Directory name is used as the target sub-path (e.g., `/skills/Foo/` → `/home/user/Foo/`).

Text files only (no binary). Limits: single file 10MB, batch 100MB/200files.

### Clarification
When uncertain, use `ask_human`. Never guess.
"""

# ---------------------------------------------------------------------------
# 共享 Memory 段
# ---------------------------------------------------------------------------


def get_memory_guide() -> str:
    from src.infra.memory.client.types import NATIVE_MEMORY_GUIDE

    return NATIVE_MEMORY_GUIDE


# ---------------------------------------------------------------------------
# 主代理提示词中的子代理调用指南（追加到主代理 system_prompt 末尾）
# ---------------------------------------------------------------------------
SUBAGENT_TASK_GUIDE = """
## Using the `task` Tool (Subagents)

Subagent activity (tool calls, results, reasoning) is **automatically logged**.
When the subagent returns, check its response for `[Activity log saved to: ...]`.
If the task was complex, read that file for full context beyond the summary.
"""

# ---------------------------------------------------------------------------
# 子代理系统提示词 — 默认版本（简单任务，不强制保存文件）
# ---------------------------------------------------------------------------
DEFAULT_SUBAGENT_PROMPT = """You are a subagent tasked with completing a specific objective and returning a comprehensive result.

You have access to standard tools to accomplish the objective."""

# ---------------------------------------------------------------------------
# 子代理系统提示词 — 详细记录版本（复杂任务，强制保存中间产物）
# ---------------------------------------------------------------------------
DETAILED_SUBAGENT_PROMPT = """You are a subagent completing a specific objective.

Your activity (tool calls, results, reasoning) is automatically recorded.
Focus on completing the task thoroughly and returning a clear summary of your findings."""

# ---------------------------------------------------------------------------
# 默认导出 — 子代理默认使用详细记录版本，确保中间产物不丢失
# ---------------------------------------------------------------------------
SUBAGENT_PROMPT = DETAILED_SUBAGENT_PROMPT
