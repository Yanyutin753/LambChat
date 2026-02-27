"""
Sync Conversation 工具

让 Agent 可以从之前的对话历史中恢复 write_file 创建的文件到新沙箱中。
由于每次对话沙箱都会被重新初始化，这个工具可以让 LLM 恢复之前写入的文件。
"""

import asyncio
import base64
import json
import logging
from typing import Any, Optional

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


def _get_from_config(runtime: ToolRuntime, key: str) -> Optional[Any]:
    """
    从 runtime.config 中获取配置值

    Args:
        runtime: LangChain ToolRuntime
        key: 配置键名（如 "backend", "messages"）

    Returns:
        配置值或 None
    """
    if runtime is None:
        return None

    # 方式1: 从 runtime.config["configurable"][key] 获取（主要方式）
    if hasattr(runtime, "config") and runtime.config:
        config = runtime.config
        if isinstance(config, dict):
            configurable = config.get("configurable", {})
            if isinstance(configurable, dict):
                value = configurable.get(key)
                if value is not None:
                    logger.debug(f"Got {key} from runtime.config['configurable']['{key}']")
                    return value
            # 也检查直接的键
            value = config.get(key)
            if value is not None:
                logger.debug(f"Got {key} from runtime.config['{key}']")
                return value

    # 方式2: 从 runtime 的 attributes 中获取
    if hasattr(runtime, "attributes"):
        value = runtime.attributes.get(key)
        if value is not None:
            logger.debug(f"Got {key} from runtime.attributes['{key}']")
            return value

    # 方式3: 从 configurable 属性获取
    if hasattr(runtime, "configurable"):
        configurable = runtime.configurable
        if isinstance(configurable, dict):
            value = configurable.get(key)
            if value is not None:
                logger.debug(f"Got {key} from runtime.configurable['{key}']")
                return value

    return None


def extract_write_operations_from_messages(messages: list) -> list[dict]:
    """
    从 messages 中提取所有成功的 write_file 工具调用

    只有当 write_file 工具返回成功结果时才会被提取。

    Args:
        messages: LangChain 消息列表

    Returns:
        list of {"file_path": str, "content": str}
    """
    # 第一步：收集所有 write_file 工具调用及其参数
    # key: tool_call_id, value: {"file_path": str, "content": str}
    pending_calls: dict[str, dict] = {}

    for msg in messages:
        # 检查 AIMessage 的 tool_calls
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tool_call in msg.tool_calls:
                if isinstance(tool_call, dict):
                    tool_name = tool_call.get("name", "")
                    if tool_name == "write_file":
                        tool_call_id = tool_call.get("id", "")
                        args = tool_call.get("args", {})
                        file_path = args.get("file_path", "")
                        content = args.get("content", "")
                        if file_path and content and tool_call_id:
                            pending_calls[tool_call_id] = {
                                "file_path": file_path,
                                "content": content,
                            }

    # 第二步：检查哪些工具调用有成功的返回结果
    # 收集成功的 tool_call_id（使用 list 保持顺序，后面的写入会覆盖前面的）
    successful_call_ids: list[str] = []
    seen_call_ids: set[str] = set()  # 用于去重，避免重复添加

    for msg in messages:
        # 检查 ToolMessage（工具返回结果）
        msg_type = getattr(msg, "type", "")
        if msg_type == "tool":
            tool_call_id = getattr(msg, "tool_call_id", "")
            if tool_call_id and tool_call_id in pending_calls:
                # 检查返回内容是否表示成功
                content = getattr(msg, "content", "")
                if content:
                    # 成功的写入通常返回类似 "Successfully wrote to /path/to/file" 或包含文件路径
                    # 检查是否包含错误标记
                    content_str = str(content).lower()
                    is_error = any(
                        err in content_str for err in ["error:", "failed", "exception", "not found"]
                    )
                    if not is_error and tool_call_id not in seen_call_ids:
                        successful_call_ids.append(tool_call_id)
                        seen_call_ids.add(tool_call_id)

    # 第三步：只返回成功的调用
    operations = []
    for call_id in successful_call_ids:
        if call_id in pending_calls:
            operations.append(pending_calls[call_id])

    return operations


@tool
async def sync_conversation(
    target_dir: str = "restored_files",
    runtime: Optional[ToolRuntime] = None,
) -> str:
    """
    Restore files created by write_file tool from conversation history to sandbox.

    Since the sandbox is reinitialized for each conversation, this tool restores
    files that were previously written using the write_file tool.

    The tool scans the conversation history for successful write_file operations
    and recreates those files in the sandbox.

    Args:
        target_dir: Directory in sandbox to restore files to.
                    Files will be restored to: {target_dir}/{original_path}
                    Default: "restored_files"

    Returns:
        JSON with result information:
        - success: Whether the sync was successful
        - restored_count: Number of files restored
        - restored_files: List of restored file paths
        - error: Error message if failed
    """
    # 从 runtime.config 获取 sandbox backend
    backend = _get_from_config(runtime, "backend")

    if backend is None:
        result = {
            "success": False,
            "error": "Sandbox not initialized. This tool requires an active sandbox session.",
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    # 从 runtime.config 获取 messages
    messages = _get_from_config(runtime, "messages") or []

    try:
        # 从 messages 中动态提取 write_file 操作
        write_operations = extract_write_operations_from_messages(messages)

        if not write_operations:
            result = {
                "success": True,
                "restored_count": 0,
                "restored_files": [],
                "message": "No write_file operations found in conversation history.",
            }
            return json.dumps(result, ensure_ascii=False, indent=2)

        # 获取工作目录
        pwd_result = await backend.aexecute("pwd")
        if pwd_result.exit_code == 0:
            workspace_dir = pwd_result.output.strip()
        else:
            workspace_dir = "/"
            logger.warning(f"Failed to get pwd, using default: {workspace_dir}")

        # 收集需要创建的目录和文件（去重：同一文件路径只保留最后一次写入）
        dirs_to_create: set[str] = set()
        files_to_write: dict[str, tuple[str, str]] = {}  # full_path -> (content, original_path)

        for op in write_operations:
            original_path = op["file_path"]
            content = op["content"]

            # 保持原始路径完全一致，不加任何前缀
            # 例如: /home/daytona/hello_world.py -> /home/daytona/hello_world.py
            full_path = original_path

            # 收集目录
            dir_path = "/".join(full_path.split("/")[:-1])
            if dir_path:
                dirs_to_create.add(dir_path)

            # 去重：后面的写入会覆盖前面的
            files_to_write[full_path] = (content, original_path)

        # 创建所有目录
        if dirs_to_create:
            mkdir_cmd = f"mkdir -p {' '.join(sorted(dirs_to_create))}"
            mkdir_result = await backend.aexecute(mkdir_cmd)

            if mkdir_result.exit_code != 0:
                result = {
                    "success": False,
                    "error": f"Failed to create directories: {mkdir_result.output}",
                }
                return json.dumps(result, ensure_ascii=False, indent=2)

        # 并发写入文件
        async def write_single_file(full_path: str, content: str, original_path: str) -> dict:
            """写入单个文件"""
            try:
                content_b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
                write_result = await backend.aexecute(
                    f"echo '{content_b64}' | base64 -d > '{full_path}'"
                )

                if write_result.exit_code == 0:
                    return {
                        "success": True,
                        "original_path": original_path,
                        "restored_path": full_path,
                    }
                else:
                    return {
                        "success": False,
                        "path": original_path,
                        "error": write_result.output,
                    }
            except Exception as e:
                return {
                    "success": False,
                    "path": original_path,
                    "error": str(e),
                }

        # 并发执行所有写入操作
        write_tasks = [
            write_single_file(full_path, content, original_path)
            for full_path, (content, original_path) in files_to_write.items()
        ]
        write_results = await asyncio.gather(*write_tasks)

        # 收集结果
        restored_files = []
        failed_files = []
        for r in write_results:
            if r["success"]:
                restored_files.append(
                    {
                        "original_path": r["original_path"],
                        "restored_path": r["restored_path"],
                    }
                )
            else:
                failed_files.append(
                    {
                        "path": r["path"],
                        "error": r["error"],
                    }
                )

        # 构建结果
        success_count = len(restored_files)
        total_count = len(files_to_write)

        if failed_files:
            result = {
                "success": success_count > 0,  # 部分成功也算成功
                "restored_count": success_count,
                "total_count": total_count,
                "restored_files": restored_files,
                "failed_files": failed_files,
                "message": f"Restored {success_count}/{total_count} files. See failed_files for errors.",
            }
        else:
            result = {
                "success": True,
                "restored_count": success_count,
                "restored_files": restored_files,
                "message": f"Successfully restored {success_count} files to {workspace_dir}/{target_dir}/",
            }

        logger.info(f"Synced {success_count}/{total_count} write_file operations to sandbox")

    except Exception as e:
        logger.error(f"Failed to sync conversation: {e}", exc_info=True)
        result = {
            "success": False,
            "error": str(e),
        }

    return json.dumps(result, ensure_ascii=False, indent=2)


def get_sync_conversation_tool() -> BaseTool:
    """获取 sync_conversation 工具实例"""
    return sync_conversation
