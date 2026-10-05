"""Channel registry for auto-discovery of channel types.

Provides discovery mechanism for built-in channel implementations and
external plugins registered via entry points.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING, Any, Optional

from src.infra.logging import get_logger

if TYPE_CHECKING:
    from src.infra.channel.base import BaseChannel, UserChannelManager
    from src.kernel.schemas.channel import ChannelType

logger = get_logger(__name__)
# Internal modules to skip during discovery
_INTERNAL = frozenset(
    {"base", "registry", "manager", "outbound", "delivery", "fallback", "__init__"}
)


def discover_channel_modules() -> list[str]:
    """
    Return all built-in channel module names by scanning the package.

    Returns:
        List of module names that contain channel implementations.
    """
    import os

    import src.infra.channel as pkg

    # Get modules (files)
    modules = [
        name
        for _, name, ispkg in pkgutil.iter_modules(pkg.__path__)
        if name not in _INTERNAL and not ispkg
    ]

    # Also discover packages (directories with __init__.py) in the channel directory
    channel_dir = pkg.__path__[0]  # This is the channel directory itself
    for item in os.listdir(channel_dir):
        item_path = os.path.join(channel_dir, item)
        if os.path.isdir(item_path) and item not in _INTERNAL:
            init_file = os.path.join(item_path, "__init__.py")
            if os.path.exists(init_file):
                modules.append(item)

    return modules


def _defined_by_module(mod: Any, cls: type) -> bool:
    """类是否由该渠道模块（或其子模块，如 feishu 包内的 feishu.channel）定义。

    渠道模块普遍 from outbound/base 导入共享基类，dir() 扫描时这些导入名
    也是 BaseChannel 子类——不限定定义来源会把共享基类错认成渠道。
    """
    cls_module = getattr(cls, "__module__", "") or ""
    return cls_module == mod.__name__ or cls_module.startswith(mod.__name__ + ".")


def load_channel_class(module_name: str) -> Optional[type["BaseChannel"]]:
    """
    Import a channel module and return the BaseChannel subclass found.

    Args:
        module_name: Name of the channel module.

    Returns:
        The BaseChannel subclass, or None if not found.
    """
    from src.infra.channel.base import BaseChannel as _Base

    try:
        mod = importlib.import_module(f"src.infra.channel.{module_name}")
        for attr in dir(mod):
            obj = getattr(mod, attr)
            if (
                isinstance(obj, type)
                and issubclass(obj, _Base)
                and obj is not _Base
                and _defined_by_module(mod, obj)
            ):
                return obj
    except ImportError as e:
        logger.debug(f"Could not import channel module '{module_name}': {e}")
    except Exception as e:
        logger.warning(f"Error loading channel module '{module_name}': {e}")

    return None


def load_manager_class(module_name: str) -> Optional[type["UserChannelManager"]]:
    """
    Import a channel module and return the UserChannelManager subclass found.

    Args:
        module_name: Name of the channel module.

    Returns:
        The UserChannelManager subclass, or None if not found.
    """
    from src.infra.channel.base import UserChannelManager as _Manager

    try:
        mod = importlib.import_module(f"src.infra.channel.{module_name}")
        for attr in dir(mod):
            obj = getattr(mod, attr)
            if (
                isinstance(obj, type)
                and issubclass(obj, _Manager)
                and obj is not _Manager
                and _defined_by_module(mod, obj)
            ):
                return obj
    except ImportError as e:
        logger.debug(f"Could not import manager module '{module_name}': {e}")
    except Exception as e:
        logger.warning(f"Error loading manager from '{module_name}': {e}")

    return None


def discover_plugins() -> dict[str, type["BaseChannel"]]:
    """
    Discover external channel plugins registered via entry_points.

    Returns:
        Dictionary mapping plugin names to their channel classes.
    """
    plugins: dict[str, type["BaseChannel"]] = {}

    try:
        from importlib.metadata import entry_points

        for ep in entry_points(group="lambchat.channels"):
            try:
                cls = ep.load()
                plugins[ep.name] = cls
            except Exception as e:
                logger.warning(f"Failed to load channel plugin '{ep.name}': {e}")
    except Exception as e:
        logger.debug(f"Could not discover entry_points plugins: {e}")

    return plugins


def discover_all_channels() -> dict[str, type["BaseChannel"]]:
    """
    Return all available channels: built-in (pkgutil) merged with external (entry_points).

    Built-in channels take priority — an external plugin cannot shadow a built-in name.

    Returns:
        Dictionary mapping channel type values to their classes.
    """
    builtin: dict[str, type["BaseChannel"]] = {}

    for modname in discover_channel_modules():
        cls = load_channel_class(modname)
        if cls:
            # Use channel_type.value as the key for consistent lookup
            key = cls.channel_type.value
            builtin[key] = cls

    external = discover_plugins()
    # Also key external plugins by their channel_type.value
    external_keyed = {}
    for name, cls in external.items():
        key = cls.channel_type.value
        external_keyed[key] = cls

    shadowed = set(external_keyed) & set(builtin)
    if shadowed:
        logger.warning(f"Plugin(s) shadowed by built-in channels (ignored): {shadowed}")

    return {**external_keyed, **builtin}


def discover_all_managers() -> dict[str, type["UserChannelManager"]]:
    """
    Return all available channel managers.

    Returns:
        Dictionary mapping channel type values to their manager classes.
    """
    managers: dict[str, type["UserChannelManager"]] = {}

    for modname in discover_channel_modules():
        cls = load_manager_class(modname)
        if cls:
            # Use channel_type.value as the key for consistent lookup
            key = cls.channel_type.value
            managers[key] = cls

    return managers


class ChannelRegistry:
    """
    Registry for all available channel types.

    Provides a centralized registry for channel discovery and lookup.
    """

    _instance: Optional["ChannelRegistry"] = None
    _channels: dict[str, type["BaseChannel"]] = {}
    _managers: dict[str, type["UserChannelManager"]] = {}
    _initialized = False

    def __new__(cls) -> "ChannelRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def initialize(self) -> None:
        """Initialize the registry by discovering all channels."""
        if self._initialized:
            return

        self._channels = discover_all_channels()
        self._managers = discover_all_managers()
        self._initialized = True

        logger.info(f"Channel registry initialized: {list(self._channels.keys())}")

    def get_channel_class(self, channel_type: "ChannelType") -> Optional[type["BaseChannel"]]:
        """
        Get a channel class by type.

        Args:
            channel_type: The channel type enum value.

        Returns:
            The channel class, or None if not found.
        """
        return self._channels.get(channel_type.value)

    def get_manager_class(
        self, channel_type: "ChannelType"
    ) -> Optional[type["UserChannelManager"]]:
        """
        Get a manager class by channel type.

        Args:
            channel_type: The channel type enum value.

        Returns:
            The manager class, or None if not found.
        """
        return self._managers.get(channel_type.value)

    def get_all_channels(self) -> dict[str, type["BaseChannel"]]:
        """Get all registered channel classes."""
        return self._channels.copy()

    def get_all_managers(self) -> dict[str, type["UserChannelManager"]]:
        """Get all registered manager classes."""
        return self._managers.copy()

    def get_channel_metadata(self) -> list[dict]:
        """Get metadata for all registered channels."""
        return [cls.get_metadata() for cls in self._channels.values()]


def get_registry() -> ChannelRegistry:
    """Get the singleton channel registry instance."""
    registry = ChannelRegistry()
    registry.initialize()
    return registry
