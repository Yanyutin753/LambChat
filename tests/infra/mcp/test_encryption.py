"""MCP 加密模块测试。

覆盖：加解密往返、旧密钥向后兼容、硬过期、篡改检测、server secrets。
"""

import base64
import hashlib
import json

import pytest
from cryptography.fernet import Fernet

from src.infra.mcp import encryption
from src.infra.mcp.encryption import (
    ENCRYPTED_MARKER,
    DecryptionError,
    decrypt_server_secrets,
    decrypt_value,
    encrypt_server_secrets,
    encrypt_value,
    is_legacy_encrypted,
)
from src.kernel.config import settings


@pytest.fixture
def fresh_encryption(monkeypatch):
    """配置密钥并重置 Fernet 缓存，确保测试隔离。"""
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "test-secret-key-for-encryption-tests")
    monkeypatch.setattr(settings, "MCP_ENCRYPTION_SALT", "test-salt-16bytes-min")
    monkeypatch.setattr(settings, "MCP_ENCRYPTION_DISABLE_LEGACY", False)
    encryption._fernet_cache = None
    encryption._fernet_legacy_cache = None
    yield
    encryption._fernet_cache = None
    encryption._fernet_legacy_cache = None


def _legacy_encrypt(value: dict) -> dict:
    """用旧 SHA256 密钥加密，模拟 PR #52 之前的历史数据。"""
    key = hashlib.sha256(settings.JWT_SECRET_KEY.encode()).digest()
    fernet = Fernet(base64.urlsafe_b64encode(key))
    payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
    return {ENCRYPTED_MARKER: base64.b64encode(fernet.encrypt(payload)).decode()}


class TestEncryptDecryptRoundTrip:
    def test_dict_round_trip(self, fresh_encryption):
        secret = {"API_KEY": "sk-xxx", "TOKEN": "abc"}
        encrypted = encrypt_value(secret)
        assert ENCRYPTED_MARKER in encrypted
        assert "sk-xxx" not in str(encrypted)
        assert decrypt_value(encrypted) == secret

    def test_none_passthrough(self, fresh_encryption):
        assert encrypt_value(None) is None
        assert decrypt_value(None) is None

    def test_empty_dict_passthrough(self, fresh_encryption):
        assert encrypt_value({}) == {}
        assert decrypt_value({}) == {}

    def test_non_dict_passthrough(self, fresh_encryption):
        assert encrypt_value("string") == "string"
        assert decrypt_value("string") == "string"

    def test_plaintext_dict_passthrough(self, fresh_encryption):
        plain = {"key": "val"}
        assert decrypt_value(plain) == plain


class TestLegacyCompatibility:
    def test_legacy_encrypted_can_be_decrypted(self, fresh_encryption):
        secret = {"API_KEY": "legacy-key"}
        legacy = _legacy_encrypt(secret)
        assert decrypt_value(legacy) == secret

    def test_is_legacy_encrypted_true_for_legacy(self, fresh_encryption):
        assert is_legacy_encrypted(_legacy_encrypt({"k": "v"})) is True

    def test_is_legacy_encrypted_false_for_new(self, fresh_encryption):
        assert is_legacy_encrypted(encrypt_value({"k": "v"})) is False

    def test_is_legacy_encrypted_false_for_plaintext(self, fresh_encryption):
        assert is_legacy_encrypted({"k": "v"}) is False
        assert is_legacy_encrypted(None) is False

    def test_is_legacy_encrypted_false_for_garbage(self, fresh_encryption):
        assert is_legacy_encrypted({ENCRYPTED_MARKER: "not-valid-base64!!!"}) is False


class TestHardExpiry:
    def test_legacy_fallback_disabled_when_disable_legacy_true(self, fresh_encryption, monkeypatch):
        monkeypatch.setattr(settings, "MCP_ENCRYPTION_DISABLE_LEGACY", True)
        legacy = _legacy_encrypt({"k": "v"})
        with pytest.raises(DecryptionError):
            decrypt_value(legacy)

    def test_new_key_still_works_when_disable_legacy_true(self, fresh_encryption, monkeypatch):
        monkeypatch.setattr(settings, "MCP_ENCRYPTION_DISABLE_LEGACY", True)
        secret = {"k": "v"}
        assert decrypt_value(encrypt_value(secret)) == secret


class TestTamperDetection:
    def test_tampered_ciphertext_raises_decryption_error(self, fresh_encryption):
        encrypted = encrypt_value({"k": "v"})
        tampered = {ENCRYPTED_MARKER: encrypted[ENCRYPTED_MARKER][:-4] + "AAAA"}
        with pytest.raises(DecryptionError):
            decrypt_value(tampered)


class TestServerSecrets:
    def test_server_secrets_round_trip(self, fresh_encryption):
        server = {"env": {"KEY": "val"}, "headers": {"X-Header": "h"}, "name": "srv"}
        encrypted = encrypt_server_secrets(server)
        assert ENCRYPTED_MARKER in encrypted["env"]
        assert ENCRYPTED_MARKER in encrypted["headers"]
        assert encrypted["name"] == "srv"
        decrypted = decrypt_server_secrets(encrypted)
        assert decrypted["env"] == {"KEY": "val"}
        assert decrypted["headers"] == {"X-Header": "h"}

    def test_server_secrets_without_sensitive_fields(self, fresh_encryption):
        server = {"name": "srv", "url": "http://x"}
        encrypted = encrypt_server_secrets(server)
        assert encrypted == server
