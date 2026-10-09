"""Sign immutable release asset hashes with the separately managed release key."""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "client"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from lambchat_sandbox.release_signature import MANIFEST_NAME, SIGNATURE_NAME, verify_release


def sign_release(directory: Path, version: str, commit: str, private_key: bytes) -> None:
    key = load_pem_private_key(private_key, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("An Ed25519 release key is required")
    assets = {}
    for path in sorted(directory.iterdir()):
        if path.name in {MANIFEST_NAME, SIGNATURE_NAME, "latest.json"}:
            continue
        if path.is_symlink() or not path.is_file():
            raise ValueError("Release assets must be regular files")
        with path.open("rb") as stream:
            assets[path.name] = {
                "sha256": hashlib.file_digest(stream, "sha256").hexdigest(),
                "size": path.stat().st_size,
            }
    if not assets:
        raise ValueError("No release assets to sign")
    payload = json.dumps(
        {"schema": 1, "version": version, "commit": commit, "assets": assets},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    signature = key.sign(payload)
    # Refuse publication when the CI secret differs from the client's pinned public key.
    verify_release(
        payload, signature, version=version, asset_name=next(iter(assets)), current_version="0.0.0"
    )
    (directory / MANIFEST_NAME).write_bytes(payload)
    (directory / SIGNATURE_NAME).write_bytes(signature)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    credential = os.environ.get("DEVICE_RELEASE_SIGNING_KEY")
    if not credential:
        raise SystemExit("DEVICE_RELEASE_SIGNING_KEY is required")
    sign_release(args.directory, args.version.removeprefix("v"), args.commit, credential.encode())
