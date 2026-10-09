"""Independent release signatures; platform metadata cannot authorize installation."""

import json
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

RELEASE_PUBLIC_KEY = bytes.fromhex(
    "89596186eda3639ecb3aa0e3e87c313168add1fc4ac0b2c2e984e2c334fc5362"
)
MANIFEST_NAME = "release-security.json"
SIGNATURE_NAME = "release-security.json.sig"
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_ASSET_BYTES = 1024 * 1024 * 1024


class ReleaseVerificationError(ValueError):
    """Missing, invalid, or stale independently signed release metadata."""


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate manifest field")
        result[key] = value
    return result


def _version(value):
    if (
        not isinstance(value, str)
        or len(value) > 32
        or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value)
    ):
        raise ValueError("Invalid release version")
    return tuple(int(part) for part in value.split("."))


def verify_release(
    payload: bytes, signature: bytes, *, version: str, asset_name: str, current_version: str
) -> dict:
    try:
        if len(payload) > MAX_MANIFEST_BYTES or len(signature) != 64:
            raise ValueError("Invalid signature envelope")
        Ed25519PublicKey.from_public_bytes(RELEASE_PUBLIC_KEY).verify(signature, payload)
        manifest = json.loads(payload, object_pairs_hook=_unique_fields)
        if not isinstance(manifest, dict) or set(manifest) != {
            "schema",
            "version",
            "commit",
            "assets",
        }:
            raise ValueError("Invalid release manifest")
        if type(manifest["schema"]) is not int or manifest["schema"] != 1:
            raise ValueError("Unsupported manifest schema")
        if manifest["version"] != version or _version(version) <= _version(
            current_version.lstrip("v")
        ):
            raise ValueError("Release version mismatch or rollback")
        if not isinstance(manifest["commit"], str) or not re.fullmatch(
            r"[0-9a-f]{40}", manifest["commit"]
        ):
            raise ValueError("Invalid release commit")
        assets = manifest["assets"]
        if not isinstance(assets, dict) or not assets or len(assets) > 128:
            raise ValueError("Invalid release assets")
        for name, asset in assets.items():
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,255}", name):
                raise ValueError("Invalid asset name")
            if not isinstance(asset, dict) or set(asset) != {"size", "sha256"}:
                raise ValueError("Invalid asset metadata")
            if type(asset["size"]) is not int or not 0 < asset["size"] <= MAX_ASSET_BYTES:
                raise ValueError("Invalid asset size")
            if not isinstance(asset["sha256"], str) or not re.fullmatch(
                r"[0-9a-f]{64}", asset["sha256"]
            ):
                raise ValueError("Invalid asset digest")
        if asset_name not in assets:
            raise ValueError("Selected platform asset is not signed")
        return assets[asset_name]
    except (InvalidSignature, ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise ReleaseVerificationError("Release signature verification failed") from exc
