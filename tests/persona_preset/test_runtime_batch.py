from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import pytest

from src.infra.persona_preset.manager import PersonaPresetManager
from src.kernel.exceptions import NotFoundError


def _preset(preset_id, **overrides):
    return {
        "id": preset_id,
        "scope": "user",
        "owner_user_id": "owner",
        "name": preset_id,
        "system_prompt": f"original system prompt {preset_id}",
        "skill_names": ["own", "missing-skill"] if preset_id == "a" else ["own-2"],
        "mcp_server_names": ["shared", "missing-mcp"]
        if preset_id == "a"
        else ["own-mcp", "shared"],
        "visibility": "private",
        "status": "published",
        "version": 1,
        **overrides,
    }


def _manager(docs):
    events = []

    async def increment(preset_id):
        events.append(("usage", preset_id))

    async def touch(*, user_id, preset_id):
        assert user_id == "owner"
        events.append(("touch", preset_id))

    storage = SimpleNamespace(
        get_by_ids=AsyncMock(
            side_effect=lambda ids: {pid: docs[pid] for pid in ids if pid in docs}
        ),
        get_by_id=AsyncMock(
            side_effect=AssertionError("batch startup must not point-read presets")
        ),
        increment_usage=AsyncMock(side_effect=increment),
        touch_user_preference=AsyncMock(side_effect=touch),
    )
    skills = SimpleNamespace(
        get_effective_skills=AsyncMock(return_value={"skills": {"own": {}, "own-2": {}}})
    )
    mcp = SimpleNamespace(get_visible_server_names=AsyncMock(return_value={"shared", "own-mcp"}))
    return PersonaPresetManager(storage=storage, skill_storage=skills, mcp_storage=mcp), events


@pytest.mark.parametrize("ids", [["a"], ["a", "b", "a"]])
async def test_runtime_batch_resolves_reads_once_and_preserves_member_order_and_usage(ids):
    manager, events = _manager({"a": _preset("a"), "b": _preset("b")})

    snapshots = await manager.use_presets(
        ids, user_id="owner", is_admin=False, user_roles=["researcher"]
    )

    assert [snapshot.preset_id for snapshot in snapshots] == ids
    assert [snapshot.system_prompt for snapshot in snapshots] == [
        f"original system prompt {pid}" for pid in ids
    ]
    assert events == [event for pid in ids for event in [("usage", pid), ("touch", pid)]]
    manager.storage.get_by_ids.assert_awaited_once_with(list(dict.fromkeys(ids)))
    manager.storage.get_by_id.assert_not_awaited()
    manager.skill_storage.get_effective_skills.assert_awaited_once_with("owner")
    expected_union = ["shared", "missing-mcp"] + (["own-mcp"] if "b" in ids else [])
    manager.mcp_storage.get_visible_server_names.assert_awaited_once_with(
        expected_union, user_id="owner", user_roles=["researcher"], is_admin=False
    )
    for snapshot in snapshots:
        if snapshot.preset_id == "a":
            assert snapshot.skill_names == ["own"]
            assert snapshot.missing_skill_names == ["missing-skill"]
            assert snapshot.mcp_server_names == ["shared"]
            assert snapshot.missing_mcp_server_names == ["missing-mcp"]
        else:
            assert snapshot.skill_names == ["own-2"]
            assert snapshot.mcp_server_names == ["own-mcp", "shared"]


@pytest.mark.parametrize(
    "hidden",
    [
        None,
        {"owner_user_id": "other"},
        {"scope": "global", "visibility": "private"},
        {"scope": "global", "visibility": "public", "status": "draft"},
    ],
)
async def test_runtime_batch_authorization_failure_preserves_successful_prefix(hidden):
    docs = {"a": _preset("a"), "last": _preset("last")}
    if hidden is not None:
        docs["hidden"] = _preset("hidden", **hidden)
    manager, events = _manager(docs)

    with pytest.raises(NotFoundError):
        await manager.use_presets(
            ["a", "a", "hidden", "last"],
            user_id="owner",
            is_admin=False,
            user_roles=["researcher"],
        )

    assert events == [("usage", "a"), ("touch", "a"), ("usage", "a"), ("touch", "a")]
    manager.storage.get_by_ids.assert_awaited_once_with(["a", "hidden", "last"])
    manager.storage.get_by_id.assert_not_awaited()
    manager.mcp_storage.get_visible_server_names.assert_awaited_once_with(
        ["shared", "missing-mcp"], user_id="owner", user_roles=["researcher"], is_admin=False
    )


async def test_runtime_batch_empty_or_unbound_presets_skip_optional_reads():
    manager, events = _manager({"plain": _preset("plain", skill_names=[], mcp_server_names=[])})

    assert await manager.use_presets([], user_id="owner", is_admin=False) == []
    manager.storage.get_by_ids.assert_not_awaited()
    snapshots = await manager.use_presets(["plain"], user_id="owner", is_admin=False)
    assert snapshots[0].skill_names == [] and snapshots[0].mcp_server_names == []
    manager.skill_storage.get_effective_skills.assert_not_awaited()
    manager.mcp_storage.get_visible_server_names.assert_not_awaited()
    assert events == [("usage", "plain"), ("touch", "plain")]


async def test_runtime_batch_mcp_failure_keeps_missing_and_usage_semantics():
    manager, events = _manager({"a": _preset("a"), "b": _preset("b")})
    manager.mcp_storage.get_visible_server_names.side_effect = RuntimeError("MCP unavailable")

    snapshots = await manager.use_presets(
        ["a", "b"], user_id="owner", is_admin=False, user_roles=["researcher"]
    )

    assert all(snapshot.mcp_server_names == [] for snapshot in snapshots)
    assert snapshots[0].missing_mcp_server_names == ["shared", "missing-mcp"]
    assert snapshots[1].missing_mcp_server_names == ["own-mcp", "shared"]
    assert events == [("usage", "a"), ("touch", "a"), ("usage", "b"), ("touch", "b")]
    assert manager.mcp_storage.get_visible_server_names.await_count == 1


async def test_runtime_batch_skill_failure_is_raised_after_prior_unbound_usage():
    manager, events = _manager(
        {"plain": _preset("plain", skill_names=[], mcp_server_names=[]), "a": _preset("a")}
    )
    manager.skill_storage.get_effective_skills.side_effect = RuntimeError("skills unavailable")

    with pytest.raises(RuntimeError, match="skills unavailable"):
        await manager.use_presets(
            ["plain", "a", "plain"], user_id="owner", is_admin=False, user_roles=["researcher"]
        )

    assert events == [("usage", "plain"), ("touch", "plain")]
    manager.mcp_storage.get_visible_server_names.assert_not_awaited()


async def test_runtime_batch_does_not_reuse_preset_or_permissions_across_requests():
    docs = {"a": _preset("a")}
    manager, _events = _manager(docs)
    first = await manager.use_presets(["a"], user_id="owner", is_admin=False)
    docs["a"]["system_prompt"] = "updated original system prompt"
    second = await manager.use_presets(["a"], user_id="owner", is_admin=False)

    assert first[0].system_prompt == "original system prompt a"
    assert second[0].system_prompt == "updated original system prompt"
    assert manager.storage.get_by_ids.await_count == 2
    assert manager.skill_storage.get_effective_skills.await_count == 2
    assert manager.mcp_storage.get_visible_server_names.await_count == 2


async def test_runtime_batch_chunks_all_ids_and_preserves_duplicate_tail_usage():
    ids = [f"preset-{index}" for index in range(205)]
    docs = {pid: _preset(pid, skill_names=[], mcp_server_names=[]) for pid in ids}
    manager, events = _manager(docs)
    manager.storage.get_by_ids.side_effect = lambda batch: {pid: docs[pid] for pid in batch[:100]}
    requested = [*ids, ids[-1]]

    snapshots = await manager.use_presets(requested, user_id="owner", is_admin=False)

    assert [snapshot.preset_id for snapshot in snapshots] == requested
    assert events == [event for pid in requested for event in [("usage", pid), ("touch", pid)]]
    assert manager.storage.get_by_ids.await_args_list == [
        call(ids[:100]),
        call(ids[100:200]),
        call(ids[200:]),
    ]
    manager.skill_storage.get_effective_skills.assert_not_awaited()
    manager.mcp_storage.get_visible_server_names.assert_not_awaited()


async def test_runtime_batch_accepts_uppercase_id_and_keeps_original_usage_argument():
    canonical = "abcdef0123456789abcdef01"
    requested = canonical.upper()
    manager, events = _manager({})
    manager.storage.get_by_ids.return_value = {
        canonical: _preset(canonical, skill_names=[], mcp_server_names=[])
    }
    manager.storage.get_by_ids.side_effect = None

    snapshots = await manager.use_presets([requested], user_id="owner", is_admin=False)

    assert snapshots[0].preset_id == canonical
    manager.storage.get_by_ids.assert_awaited_once_with([requested])
    assert events == [("usage", requested), ("touch", requested)]


async def test_runtime_batch_storage_failure_keeps_successful_prior_chunk_usage():
    ids = [f"preset-{index}" for index in range(101)]
    docs = {pid: _preset(pid, skill_names=[], mcp_server_names=[]) for pid in ids}
    manager, events = _manager(docs)
    manager.storage.get_by_ids.side_effect = [
        {pid: docs[pid] for pid in ids[:100]},
        RuntimeError("preset storage unavailable"),
    ]

    with pytest.raises(RuntimeError, match="preset storage unavailable"):
        await manager.use_presets(ids, user_id="owner", is_admin=False)

    assert events == [event for pid in ids[:100] for event in [("usage", pid), ("touch", pid)]]
    manager.mcp_storage.get_visible_server_names.assert_not_awaited()
