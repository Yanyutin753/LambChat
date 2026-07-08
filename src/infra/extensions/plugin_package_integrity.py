"""Integrity summaries for local folder-based plugin packages."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

IGNORED_PACKAGE_PARTS = {"__pycache__", "node_modules", ".git", ".pytest_cache"}
SIGNATURE_FILENAMES = ("plugin-signature.json", "signature.json", "SIGNATURE")


@dataclass(frozen=True)
class PluginPackageIntegrity:
    algorithm: str
    package_sha256: str
    file_count: int
    total_bytes: int
    signed: bool
    signature_status: str
    signature_path: str | None
    notes: list[str]

    def model_dump(self) -> dict[str, object]:
        return {
            "algorithm": self.algorithm,
            "package_sha256": self.package_sha256,
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
            "signed": self.signed,
            "signature_status": self.signature_status,
            "signature_path": self.signature_path,
            "notes": list(self.notes),
        }


def build_package_integrity(package_root: Path) -> PluginPackageIntegrity:
    root = package_root.resolve()
    file_entries: list[dict[str, str | int]] = []
    file_count = 0
    total_bytes = 0
    if root.is_dir() and not root.is_symlink():
        for path in sorted(root.rglob("*")):
            if _skip_path(path):
                continue
            if not path.is_file() or path.is_symlink():
                continue
            resolved = path.resolve()
            try:
                relative = resolved.relative_to(root)
            except ValueError:
                continue
            content = path.read_bytes()
            relative_path = "/".join(relative.parts)
            file_count += 1
            total_bytes += len(content)
            file_entries.append(
                {
                    "path": relative_path,
                    "bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            )
    encoded = json.dumps(file_entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature_path = _signature_path(root)
    signed = signature_path is not None
    return PluginPackageIntegrity(
        algorithm="sha256:sorted-file-list-v1",
        package_sha256=hashlib.sha256(encoded).hexdigest(),
        file_count=file_count,
        total_bytes=total_bytes,
        signed=signed,
        signature_status="present_unverified" if signed else "unsigned",
        signature_path=str(signature_path) if signature_path is not None else None,
        notes=[
            "Package hash is computed from sorted relative file paths, byte sizes, and file SHA-256 values.",
            "Signature verification is reserved for a future signed-package phase; unsigned local packages remain disabled until reviewed.",
        ],
    )


def _skip_path(path: Path) -> bool:
    return any(part in IGNORED_PACKAGE_PARTS for part in path.parts)


def _signature_path(root: Path) -> Path | None:
    for name in SIGNATURE_FILENAMES:
        candidate = (root / name).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        if candidate.is_file() and not candidate.is_symlink():
            return candidate
    return None
