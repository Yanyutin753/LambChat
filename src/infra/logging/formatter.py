"""
Colored Formatter - 彩色日志格式化器

使用 colorama 实现日志级别的彩色输出。
"""

from __future__ import annotations

import logging
import sys

from colorama import Fore, Style, init

# 初始化 colorama（Windows 兼容）
init(autoreset=True)


class ColoredFormatter(logging.Formatter):
    """
    彩色日志格式化器

    根据日志级别自动着色，非 TTY 环境自动降级为纯文本。

    颜色映射:
        DEBUG: CYAN
        INFO: GREEN
        WARNING: YELLOW
        ERROR: RED
        CRITICAL: RED + BOLD
    """

    LEVEL_COLORS = {
        logging.DEBUG: Fore.CYAN,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.RED + Style.BRIGHT,
    }

    def __init__(self, fmt: str | None = None, datefmt: str | None = None):
        super().__init__(fmt, datefmt)
        self._is_tty = sys.stdout.isatty()

    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录，添加颜色"""
        # 保存原始 levelname
        original_levelname = record.levelname

        if self._is_tty:
            # 添加颜色
            color = self.LEVEL_COLORS.get(record.levelno, "")
            record.levelname = f"{color}{record.levelname}{Style.RESET_ALL}"

        result = super().format(record)

        # 恢复原始 levelname
        record.levelname = original_levelname

        return result
