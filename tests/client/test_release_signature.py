"""Release metadata is trusted only after independent signature verification."""

import hashlib
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


@pytest.fixture
def signed_release(monkeypatch):
    from lambchat_sandbox import release_signature as module

    key = Ed25519PrivateKey.generate()
    monkeypatch.setattr(
        module, "RELEASE_PUBLIC_KEY", key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    )
    name = "lambchat-daemon-aarch64-apple-darwin"
    payload = json.dumps(
        {
            "schema": 1,
            "version": "2.14.5",
            "commit": "a" * 40,
            "assets": {name: {"size": 7, "sha256": hashlib.sha256(b"fixture").hexdigest()}},
        }
    ).encode()
    return module, key, name, payload


def test_signed_release_binds_version_asset_hash_and_size(signed_release):
    module, key, name, payload = signed_release
    result = module.verify_release(
        payload, key.sign(payload), version="2.14.5", asset_name=name, current_version="2.14.4"
    )
    assert result == {"size": 7, "sha256": hashlib.sha256(b"fixture").hexdigest()}


@pytest.mark.parametrize("attack", ["tamper", "key", "version", "platform", "rollback", "oversize"])
def test_release_verification_rejects_untrusted_or_replayed_metadata(signed_release, attack):
    module, key, name, payload = signed_release
    signature = key.sign(payload)
    version, current = "2.14.5", "2.14.4"
    if attack == "tamper":
        payload = payload.replace(b"2.14.5", b"9.99.9")
    if attack == "key":
        signature = Ed25519PrivateKey.generate().sign(payload)
    if attack == "version":
        version = "2.14.6"
    if attack == "platform":
        name = "lambchat-daemon-x86_64-pc-windows-msvc.exe"
    if attack == "rollback":
        current = "2.14.5"
    if attack == "oversize":
        payload = b" " * (2 * 1024 * 1024 + 1)
    with pytest.raises(module.ReleaseVerificationError):
        module.verify_release(
            payload, signature, version=version, asset_name=name, current_version=current
        )


def test_even_signed_duplicate_json_fields_are_rejected(signed_release):
    module, key, name, payload = signed_release
    payload = payload.replace(b'"schema": 1', b'"schema": 1, "schema": 1')
    with pytest.raises(module.ReleaseVerificationError):
        module.verify_release(
            payload, key.sign(payload), version="2.14.5", asset_name=name, current_version="2.14.4"
        )


def test_release_signer_round_trip_covers_actual_asset_bytes(signed_release, tmp_path):
    from cryptography.hazmat.primitives.serialization import NoEncryption, PrivateFormat

    from scripts.sign_release_assets import sign_release

    module, key, name, _ = signed_release
    (tmp_path / name).write_bytes(b"fixture")
    sign_release(
        tmp_path,
        "2.14.5",
        "a" * 40,
        key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()),
    )
    asset = module.verify_release(
        (tmp_path / module.MANIFEST_NAME).read_bytes(),
        (tmp_path / module.SIGNATURE_NAME).read_bytes(),
        version="2.14.5",
        asset_name=name,
        current_version="2.14.4",
    )
    assert asset["size"] == len((tmp_path / name).read_bytes())
    assert asset["sha256"] == hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()


def test_native_linux_and_daemon_pin_the_same_release_key():
    import re
    from pathlib import Path

    from lambchat_sandbox.release_signature import RELEASE_PUBLIC_KEY

    source = (
        Path(__file__).resolve().parents[2] / "frontend/src-tauri/src/release_signature.rs"
    ).read_text()
    declaration = re.search(r"const RELEASE_PUBLIC_KEY: \[u8; 32\] = \[(.*?)\];", source, re.S)
    assert declaration is not None
    assert (
        bytes(int(value, 16) for value in re.findall(r"0x([0-9a-f]{2})", declaration[1]))
        == RELEASE_PUBLIC_KEY
    )
