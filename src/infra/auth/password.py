"""
密码处理

提供密码哈希和验证功能。
"""

import bcrypt


def _truncate_password(password: str, max_bytes: int = 72) -> bytes:
    """
    安全截断密码到指定字节数，确保不在多字节字符中间截断

    Args:
        password: 明文密码
        max_bytes: 最大字节数（bcrypt 限制为 72 字节）

    Returns:
        截断后的密码字节
    """
    password_bytes = password.encode("utf-8")
    if len(password_bytes) <= max_bytes:
        return password_bytes

    # 安全截断：从 max_bytes 位置向前查找有效的 UTF-8 边界
    # UTF-8 多字节字符的第一个字节最高位为 11xxxxxx（不是 10xxxxxx）
    truncate_pos = max_bytes
    while truncate_pos > 0:
        byte = password_bytes[truncate_pos - 1]
        # 检查是否是 UTF-8 连续字节（10xxxxxx）
        if (byte & 0xC0) != 0x80:
            break
        truncate_pos -= 1

    return password_bytes[:truncate_pos]


def hash_password(password: str) -> str:
    """
    生成密码哈希

    Args:
        password: 明文密码

    Returns:
        哈希后的密码
    """
    # bcrypt has a 72 byte limit, truncate safely if necessary
    password_bytes = _truncate_password(password, 72)
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证密码

    Args:
        plain_password: 明文密码
        hashed_password: 哈希密码

    Returns:
        是否匹配
    """
    # Truncate safely to match hashing behavior
    password_bytes = _truncate_password(plain_password, 72)
    hashed_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hashed_bytes)
