"""云端沙箱自愈：暂停/断连类错误的识别、唤醒与单次重试。

E2B 的沙箱 timeout 是绝对倒计时（Cube 是空闲计时），长任务 run 中途到点
会被平台暂停（保留内存快照）。auto_resume 只能救「下一次请求」——正在执行
的那条命令仍会以异常收场，把原始错误直接抛给模型会浪费自愈轮次。

本模块把「沙箱级错误」与「命令级错误」区分开：前者先显式唤醒沙箱再重试
一次，对模型完全透明；后者（超时、退出码、参数错误等）原样抛出，绝不
重试——命令可能已在远端执行，重跑有副作用。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from src.infra.logging import get_logger

logger = get_logger(__name__)

_T = TypeVar("_T")

# 判定为「沙箱被暂停/断连」的异常特征（子串匹配，大小写不敏感）。
# 这些状态下命令根本没有执行到，重试无副作用。
_RETRYABLE_PATTERN_TOKENS: tuple[str, ...] = (
    "sandbox is paused",
    "sandbox paused",
    "paused sandbox",
    "is paused",
    "connection refused",
    "connection reset",
    "connection closed",
    "connection aborted",
    "connection error",
    "failed to connect",
    "connect error",
    "econnrefused",
    "econnreset",
    "econnaborted",
    "broken pipe",
    "remote end closed",
    "unexpected eof",
    "eof occurred",
    "went away",
    "unreachable",
    "no route to host",
    "bad gateway",
    "service unavailable",
)

# 连续沙箱级失败达到该次数后，在错误输出中附加「别再重试」的指引，
# 避免模型把剩余预算烧在必败调用上。
_EXHAUSTED_THRESHOLD = 3

UNAVAILABLE_GUIDANCE = (
    "The sandbox appears unavailable (paused beyond retention or recycled). "
    "Retrying immediately is unlikely to help; a fresh sandbox will be created "
    "on the next message."
)

# 沙箱被平台回收、manager 重建新沙箱后挂载的一次性提示。由 backend 的
# aexecute 前缀到首个命令输出，让模型知道旧沙箱文件已丢失并向用户说明。
SANDBOX_REPLACED_NOTICE = (
    "[sandbox] The previous sandbox expired and was recycled by the provider; "
    "a fresh sandbox has been created. Files created in the old sandbox are no "
    "longer present — mention this to the user if they ask about missing files."
)


def is_retryable_sandbox_error(exc: BaseException) -> bool:
    """判断异常是否为「沙箱暂停/断连」类、可安全唤醒重试的错误。

    命令超时（"timeout"/"timed out"）被显式排除：命令可能仍在远端执行，
    重跑有重复副作用。
    """
    if isinstance(exc, ConnectionError):
        return True
    text = str(exc).lower()
    if not text:
        return False
    if "timeout" in text or "timed out" in text:
        return False
    return any(token in text for token in _RETRYABLE_PATTERN_TOKENS)


class SandboxHeal:
    """对单个沙箱 backend 的操作做「唤醒 + 单次重试」包装。

    记录连续沙箱级失败次数：重试后仍失败才计数，任何一次成功即清零。
    达到阈值后 ``exhausted`` 为真，调用方可据此附加停止重试的指引。
    """

    def __init__(
        self,
        *,
        wake: Callable[[], None],
        sandbox_id: Callable[[], str] | str,
    ) -> None:
        self._wake = wake
        self._sandbox_id = sandbox_id
        self.consecutive_failures = 0

    @property
    def exhausted(self) -> bool:
        return self.consecutive_failures >= _EXHAUSTED_THRESHOLD

    def _describe_sandbox(self) -> str:
        try:
            sandbox_id = self._sandbox_id() if callable(self._sandbox_id) else self._sandbox_id
        except Exception:
            sandbox_id = "unknown"
        return str(sandbox_id)

    def run(self, op: str, fn: Callable[[], _T]) -> _T:
        """执行一次 SDK 调用；沙箱级错误先唤醒再重试一次。"""
        try:
            result = fn()
        except Exception as exc:
            if not is_retryable_sandbox_error(exc):
                raise
            logger.warning(
                "sandbox op %s hit sandbox-level error (%s); waking sandbox %s and retrying once",
                op,
                type(exc).__name__,
                self._describe_sandbox(),
            )
            try:
                self._wake()
            except Exception as wake_exc:
                logger.warning(
                    "sandbox wake failed for %s: %s; retrying anyway",
                    self._describe_sandbox(),
                    wake_exc,
                )
            result = self._retry_after_wake(op, fn)
        self.consecutive_failures = 0
        return result

    def _retry_after_wake(self, op: str, fn: Callable[[], _T]) -> _T:
        try:
            return fn()
        except Exception:
            self.consecutive_failures += 1
            logger.error(
                "sandbox op %s still failing after wake (consecutive=%d)",
                op,
                self.consecutive_failures,
            )
            raise

    async def arun(self, op: str, fn: Callable[[], Any], wake: Callable[[], Any]) -> Any:
        """async 版 run：协程调用同样享受唤醒 + 单次重试。"""
        try:
            result = await fn()
        except Exception as exc:
            if not is_retryable_sandbox_error(exc):
                raise
            logger.warning(
                "sandbox op %s hit sandbox-level error (%s); waking sandbox %s and retrying once",
                op,
                type(exc).__name__,
                self._describe_sandbox(),
            )
            try:
                await wake()
            except Exception as wake_exc:
                logger.warning(
                    "sandbox wake failed for %s: %s; retrying anyway",
                    self._describe_sandbox(),
                    wake_exc,
                )
            result = await self._aretry_after_wake(op, fn)
        self.consecutive_failures = 0
        return result

    async def _aretry_after_wake(self, op: str, fn: Callable[[], Any]) -> Any:
        try:
            return await fn()
        except Exception:
            self.consecutive_failures += 1
            logger.error(
                "sandbox op %s still failing after wake (consecutive=%d)",
                op,
                self.consecutive_failures,
            )
            raise
