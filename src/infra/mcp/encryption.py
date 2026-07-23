"""
MCP敏感字段加密模块

提供env和headers字段的加密/解密功能，使用Fernet对称加密。
"""

import base64
import hashlib
import json
from typing import Any, Optional

from cryptography.fernet import Fernet

from src.infra.logging import get_logger
from src.kernel.config import settings

logger = get_logger(__name__)

# 加密字段标识（用于区分加密和未加密的数据）
ENCRYPTED_MARKER = "__encrypted__"

# 密钥派生参数
_KDF_ITERATIONS = 100000  # PBKDF2 迭代次数


def _get_kdf_salt() -> bytes:
    """获取PBKDF2盐值，从配置读取并转换为bytes"""
    salt = settings.MCP_ENCRYPTION_SALT
    if not salt:
        raise RuntimeError("MCP_ENCRYPTION_SALT is not configured")
    return salt.encode("utf-8")


class DecryptionError(Exception):
    """解密失败异常"""

    pass


def _get_fernet_legacy() -> Fernet:
    """
    获取旧版Fernet加密实例（向后兼容）

    使用单次 SHA256 哈希派生密钥（PR #52 之前的方式）
    仅用于解密旧数据，不用于新加密。
    结果会被缓存。
    """
    global _fernet_legacy_cache
    if _fernet_legacy_cache is not None:
        return _fernet_legacy_cache

    key = hashlib.sha256(settings.JWT_SECRET_KEY.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(key)
    _fernet_legacy_cache = Fernet(fernet_key)
    return _fernet_legacy_cache


# 缓存 Fernet 实例，避免每次加解密都执行 PBKDF2（100K 迭次约 100ms CPU）
_fernet_cache: Optional[Fernet] = None
_fernet_legacy_cache: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    """
    获取Fernet加密实例，使用PBKDF2从JWT_SECRET_KEY派生密钥

    使用 PBKDF2-HMAC-SHA256 进行密钥派生，比单次 SHA256 更安全。
    结果会被缓存，避免重复执行昂贵的 KDF 计算。
    """
    global _fernet_cache
    if _fernet_cache is not None:
        return _fernet_cache

    # 使用 PBKDF2 派生 32 字节密钥
    key = hashlib.pbkdf2_hmac(
        "sha256",
        settings.JWT_SECRET_KEY.encode("utf-8"),
        _get_kdf_salt(),
        _KDF_ITERATIONS,
        dklen=32,
    )
    fernet_key = base64.urlsafe_b64encode(key)
    _fernet_cache = Fernet(fernet_key)
    return _fernet_cache


def encrypt_value(value: Any) -> Any:
    """
    加密敏感字段值

    Args:
        value: 要加密的值（通常是dict）

    Returns:
        加密后的值，如果是None则返回None

    Raises:
        RuntimeError: 加密失败时抛出异常
    """
    if value is None:
        return None

    if not isinstance(value, dict):
        return value

    if not value:  # 空字典
        return value

    try:
        fernet = _get_fernet()
        # 将dict序列化为JSON字符串
        import json

        json_str = json.dumps(value, ensure_ascii=False)
        # 加密
        encrypted_bytes = fernet.encrypt(json_str.encode("utf-8"))
        # 添加加密标识并编码为字符串
        return {ENCRYPTED_MARKER: base64.b64encode(encrypted_bytes).decode("utf-8")}
    except Exception as e:
        logger.error(f"加密失败: {e}")
        # 加密失败时抛出异常，避免敏感数据以明文形式存储
        raise RuntimeError(f"加密失败: {e}") from e


def decrypt_value(value: Any) -> Any:
    """
    解密敏感字段值

    支持两种格式：
    1. 加密格式: {"__encrypted__": "base64_encoded_data"}
    2. 明文格式: {"key": "value"}

    支持向后兼容：
    - 先尝试新密钥（PBKDF2）解密
    - 失败后尝试旧密钥（SHA256）解密

    Args:
        value: 要解密的值

    Returns:
        解密后的值，如果是None则返回None
    """
    if value is None:
        return None

    if not isinstance(value, dict):
        return value

    if not value:  # 空字典
        return value

    # 检查是否是加密格式
    if ENCRYPTED_MARKER in value:
        encrypted_str = value.get(ENCRYPTED_MARKER)
        if not encrypted_str:
            return value

        encrypted_bytes = base64.b64decode(encrypted_str.encode("utf-8"))

        # 先尝试新密钥（PBKDF2）
        try:
            fernet = _get_fernet()
            decrypted_bytes = fernet.decrypt(encrypted_bytes)
            return json.loads(decrypted_bytes.decode("utf-8"))
        except Exception:
            # 新密钥失败：若管理员已开启硬过期开关（MCP_ENCRYPTION_DISABLE_LEGACY=true），
            # 说明迁移完成，直接拒绝旧密钥回退，强制重新保存配置。
            disable_legacy = bool(getattr(settings, "MCP_ENCRYPTION_DISABLE_LEGACY", False))
            if disable_legacy:
                logger.error(
                    "旧密钥回退已被禁用（MCP_ENCRYPTION_DISABLE_LEGACY=true），"
                    "请重新保存该配置以迁移到 PBKDF2 加密",
                )
                raise DecryptionError("旧密钥回退已禁用，请重新保存该配置以使用新加密")
            # 旧密钥（SHA256）向后兼容回退
            try:
                fernet_legacy = _get_fernet_legacy()
                decrypted_bytes = fernet_legacy.decrypt(encrypted_bytes)
                logger.warning(
                    "使用已弃用的旧版 SHA256 密钥解密成功。"
                    "请重新保存此配置以迁移到更安全的 PBKDF2 加密。"
                    "旧密钥支持将在未来版本中移除。"
                )
                return json.loads(decrypted_bytes.decode("utf-8"))
            except Exception as e:
                # 两种密钥都失败
                logger.error("解密失败（尝试了新旧密钥）: %s", e)
                raise DecryptionError(f"解密失败: {e}") from e

    # 明文格式（向后兼容）
    return value


def is_legacy_encrypted(value: Any) -> bool:
    """判断 value 是否仍用旧 SHA256 密钥加密（新密钥解不开、旧密钥能解）。

    供迁移脚本精确识别待迁移记录，避免对已迁移或明文数据做无谓重写。
    两种密钥都解不开时返回 False（异常数据，交由调用方处理）。
    """
    if not isinstance(value, dict) or ENCRYPTED_MARKER not in value:
        return False
    encrypted_str = value.get(ENCRYPTED_MARKER)
    if not encrypted_str:
        return False
    try:
        encrypted_bytes = base64.b64decode(encrypted_str.encode("utf-8"))
    except Exception:
        return False
    try:
        _get_fernet().decrypt(encrypted_bytes)
        return False  # 新密钥能解 → 已迁移
    except Exception:
        pass
    try:
        _get_fernet_legacy().decrypt(encrypted_bytes)
        return True  # 旧密钥能解 → 待迁移
    except Exception:
        return False  # 都解不开 → 异常数据


def encrypt_server_secrets(server: dict[str, Any]) -> dict[str, Any]:
    """
    加密MCP服务器配置中的敏感字段

    Args:
        server: MCP服务器配置dict

    Returns:
        加密后的配置dict
    """
    result = server.copy()

    # 加密env
    if "env" in result and result["env"]:
        result["env"] = encrypt_value(result["env"])

    # 加密headers
    if "headers" in result and result["headers"]:
        result["headers"] = encrypt_value(result["headers"])

    return result


def decrypt_server_secrets(server: dict[str, Any]) -> dict[str, Any]:
    """
    解密MCP服务器配置中的敏感字段

    Args:
        server: MCP服务器配置dict

    Returns:
        解密后的配置dict
    """
    result = server.copy()

    # 解密env
    if "env" in result:
        result["env"] = decrypt_value(result.get("env"))

    # 解密headers
    if "headers" in result:
        result["headers"] = decrypt_value(result.get("headers"))

    return result
