"""Carry observed file versions through the existing trusted approval context."""

import hashlib
import json

from src.infra.backend.guarded_sandbox import GuardedSandboxBackend
from src.infra.backend.lazy_sandbox import LazySandboxBackend
from src.infra.backend.local import WorkspaceAliasBackend


def _batch_digest(calls):
    return hashlib.sha256(
        json.dumps(calls, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


async def _file_state(backend, calls, *, restoring=False):
    target = backend
    if isinstance(backend, LazySandboxBackend):
        target = await backend._ensure_ready() if restoring else backend._delegate
    if isinstance(target, WorkspaceAliasBackend):
        versions = target._file_versions
        resolve = target._strip_required
        conversation = target._conversation_id
        machine = target._machine_id
    elif isinstance(target, GuardedSandboxBackend):
        versions = target._versions
        resolve = target._path
        conversation = target._session_id
        machine = None
    else:
        return None
    paths = set()
    # An execution in the same batch invalidates earlier observations, even if it succeeds.
    if not any(call.get("name") == "execute" for call in calls):
        for call in calls:
            if call.get("name") not in {"write_file", "edit_file", "delete"}:
                continue
            args = call.get("args") or {}
            path = args.get("file_path", args.get("path"))
            if isinstance(path, str):
                if isinstance(backend, LazySandboxBackend):
                    path = backend._to_provider_path(path)
                paths.add(resolve(path))
    scope = [target._user_id, conversation, machine, target.work_dir, target.id]
    return scope, versions, paths


async def capture_file_confirmation(backend, calls):
    state = await _file_state(backend, calls)
    if state is None:
        return None
    scope, versions, paths = state
    return {
        "kind": "file_versions_v1",
        "scope": scope,
        "batch": _batch_digest(calls),
        "versions": {path: versions[path] for path in paths if path in versions},
    }


async def restore_file_confirmation(backend, calls, context):
    if context is None:
        return True
    if not isinstance(context, dict) or context.get("kind") != "file_versions_v1":
        return False
    state = await _file_state(backend, calls, restoring=True)
    if state is None:
        return False
    scope, versions, paths = state
    if context.get("scope") != scope or context.get("batch") != _batch_digest(calls):
        return False
    saved = context.get("versions")
    if not isinstance(saved, dict):
        return False
    for path in paths:
        if isinstance(saved.get(path), str):
            # The execution host still compares this original version before every commit.
            versions.setdefault(path, saved[path])
    return True
