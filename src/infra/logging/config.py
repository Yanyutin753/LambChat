"""
Logging Configuration - 日志配置

初始化日志系统，支持分模块级别配置。
"""

from __future__ import annotations

import logging
import sys
from typing import Dict

from src.infra.logging.filter import TraceFilter
from src.infra.logging.formatter import ColoredFormatter
from src.kernel.config import settings


def parse_log_levels(levels_str: str) -> Dict[str, str]:
    """
    解析分模块日志级别配置

    Args:
        levels_str: 配置字符串，格式 "module1=LEVEL1,module2=LEVEL2"

    Returns:
        模块到级别的映射字典

    Example:
        >>> parse_log_levels("src.infra.redis=DEBUG,src.agents=TRACE")
        {"src.infra.redis": "DEBUG", "src.agents": "TRACE"}
    """
    if not levels_str:
        return {}

    levels = {}
    for item in levels_str.split(","):
        item = item.strip()
        if "=" not in item:
            continue
        module, level = item.split("=", 1)
        levels[module.strip()] = level.strip().upper()

    return levels


def setup_logging() -> None:
    """
    初始化日志系统

    配置:
        - 控制台输出
        - 自动注入追踪上下文
        - 分模块日志级别
    """
    # 获取根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # 根设为最低，由 handler 控制

    # 清除现有处理器（避免重复）
    root_logger.handlers.clear()

    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    # 设置彩色格式化器
    formatter = ColoredFormatter(
        fmt=settings.LOG_FORMAT,
        datefmt=settings.LOG_DATE_FORMAT,
    )
    console_handler.setFormatter(formatter)

    # 添加追踪过滤器
    console_handler.addFilter(TraceFilter())

    # 添加处理器到根日志器
    root_logger.addHandler(console_handler)

    # 应用分模块日志级别
    module_levels = parse_log_levels(settings.LOG_LEVELS)
    for module, level in module_levels.items():
        logger = logging.getLogger(module)
        logger.setLevel(getattr(logging, level, logging.INFO))

    # 降低第三方库日志级别
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    获取日志器

    Args:
        name: 日志器名称，通常使用 __name__

    Returns:
        配置好的日志器
    """
    return logging.getLogger(name)
