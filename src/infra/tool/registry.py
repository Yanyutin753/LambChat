"""
工具注册表

管理工具的注册和发现。
"""

from typing import Any, Callable, Optional


class ToolRegistry:
    """
    工具注册表

    管理所有可用工具的注册和发现。
    """

    def __init__(self):
        self._tools: dict[str, Callable] = {}
        self._tool_info: dict[str, dict] = {}

    def register(
        self,
        name: str,
        func: Callable,
        description: str = "",
        parameters: Optional[dict] = None,
    ) -> None:
        """注册工具"""
        self._tools[name] = func
        self._tool_info[name] = {
            "name": name,
            "description": description,
            "parameters": parameters or {},
        }

    def unregister(self, name: str) -> bool:
        """注销工具"""
        if name in self._tools:
            del self._tools[name]
            del self._tool_info[name]
            return True
        return False

    def get(self, name: str) -> Optional[Callable]:
        """获取工具"""
        return self._tools.get(name)

    def get_info(self, name: str) -> Optional[dict]:
        """获取工具信息"""
        return self._tool_info.get(name)

    def list_tools(self) -> list[dict]:
        """列出所有工具"""
        return list(self._tool_info.values())

    def has_tool(self, name: str) -> bool:
        """检查工具是否存在"""
        return name in self._tools

    async def execute(self, name: str, **kwargs: Any) -> Any:
        """执行工具"""
        tool = self.get(name)
        if not tool:
            raise ValueError(f"Tool '{name}' not found")

        result = tool(**kwargs)
        # 支持异步工具
        if hasattr(result, "__await__"):
            result = await result
        return result


# 全局工具注册表
_global_registry = ToolRegistry()


def get_global_registry() -> ToolRegistry:
    """获取全局工具注册表"""
    return _global_registry


def register_tool(
    name: str,
    description: str = "",
    parameters: Optional[dict] = None,
) -> Callable:
    """工具注册装饰器"""

    def decorator(func: Callable) -> Callable:
        _global_registry.register(name, func, description, parameters)
        return func

    return decorator
