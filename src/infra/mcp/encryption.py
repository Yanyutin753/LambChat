"""
MCP敏感字段加密模块

提供env和headers字段的加密/解密功能，使用Fernet对称加密。
"""

import base64
import logging
from typing import Any

from cryptography.fernet import Fernet

from src.kernel.config import settings

logger = logging.getLogger(__name__)

# 加密字段标识（用于区分加密和未加密的数据）
ENCRYPTED_MARKER = "__encrypted__"


def _get_fernet() -> Fernet:
    """获取Fernet加密实例，使用JWT_SECRET_KEY派生密钥"""
    # Fernet密钥必须是32字节并使用base64编码
    # 使用JWT_SECRET_KEY的SHA256哈希来派生密钥
    import hashlib

    key = hashlib.sha256(settings.JWT_SECRET_KEY.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(key)
    return Fernet(fernet_key)


def encrypt_value(value: Any) -> Any:
    """
    加密敏感字段值

    Args:
        value: 要加密的值（通常是dict）

    Returns:
        加密后的值，如果是None则返回None
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
        # 加密失败时返回原值（不应该发生）
        return value


def decrypt_value(value: Any) -> Any:
    """
    解密敏感字段值

    支持两种格式：
    1. 加密格式: {"__encrypted__": "base64_encoded_data"}
    2. 明文格式: {"key": "value"}

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

        try:
            fernet = _get_fernet()
            # 解码
            encrypted_bytes = base64.b64decode(encrypted_str.encode("utf-8"))
            # 解密
            decrypted_bytes = fernet.decrypt(encrypted_bytes)
            # 反序列化为dict
            import json

            return json.loads(decrypted_bytes.decode("utf-8"))
        except Exception as e:
            logger.error(f"解密失败: {e}")
            # 解密失败时返回原值
            return value

    # 明文格式（向后兼容）
    return value


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
