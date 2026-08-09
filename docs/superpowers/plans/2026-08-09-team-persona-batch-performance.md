# Team Persona Batch Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace team-list persona N+1 reads with one bounded MongoDB query while preserving team/member order and missing-persona fallback behavior.

**Architecture:** Add a bounded `PersonaPresetStorage.get_by_ids` map lookup, then hydrate a list of teams from that single map. Keep runtime member validation separate because it intentionally filters invalid active members, while display hydration remains best-effort and never fails an otherwise valid team response.

**Tech Stack:** Python 3.12, FastAPI service layer, Motor/PyMongo, Pydantic, pytest, unittest.mock

---

## File structure

- Modify `src/infra/persona_preset/storage.py`: bounded unique ObjectId normalization and one-query bulk lookup returning a string-ID map.
- Modify `tests/persona_preset/test_storage_visibility.py`: bulk lookup query-count, invalid-ID, deduplication, and bound tests.
- Modify `src/infra/team/manager.py`: pure map-based member hydration and one batch lookup for one or many teams.
- Modify `tests/unit/infra/test_team_manager.py`: single-query list hydration, ordering, fallback, duplicate-ID, and failure-isolation tests.
- Modify `docs/performance-audit-2026-08-09.md`: before/after query evidence and disposition.

## Task 1: Add a bounded persona bulk lookup

**Files:**
- Modify: `tests/persona_preset/test_storage_visibility.py`
- Modify: `src/infra/persona_preset/storage.py`

- [ ] **Step 1: Write failing storage tests**

Add a fake collection/cursor that records `find` calls and returns documents in database order. Use real ObjectId strings:

```python
@pytest.mark.asyncio
async def test_get_by_ids_uses_one_bounded_query_and_returns_id_map() -> None:
    first = ObjectId()
    second = ObjectId()
    calls: list[tuple[dict, dict | None]] = []

    class _Cursor:
        async def to_list(self, *, length: int):
            assert length == 2
            return [
                {"_id": second, "name": "Second"},
                {"_id": first, "name": "First"},
            ]

    class _Collection:
        def find(self, query, projection=None):
            calls.append((query, projection))
            return _Cursor()

    storage = PersonaPresetStorage()
    storage._collection = _Collection()

    result = await storage.get_by_ids(
        [str(first), "invalid", str(second), str(first)]
    )

    assert list(result) == [str(second), str(first)]
    assert result[str(first)]["name"] == "First"
    assert len(calls) == 1
    assert calls[0][0] == {"_id": {"$in": [first, second]}}
```

Add tests that an empty/all-invalid input does not call `find`, and an input longer than `PERSONA_PRESET_BATCH_LOOKUP_LIMIT` sends no more than that many ObjectIds.

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest tests/persona_preset/test_storage_visibility.py \
  -k "get_by_ids" -v
```

Expected: FAIL because `get_by_ids` and its bound do not exist.

- [ ] **Step 3: Implement bounded normalization and lookup**

At module level:

```python
PERSONA_PRESET_BATCH_LOOKUP_LIMIT = 4_000
```

The value matches the maximum team list surface: 200 teams times 20 members. Add:

```python
async def get_by_ids(self, preset_ids: list[str]) -> dict[str, dict[str, Any]]:
    object_ids: list[ObjectId] = []
    seen: set[ObjectId] = set()
    for value in preset_ids:
        try:
            object_id = ObjectId(str(value))
        except Exception:
            continue
        if object_id in seen:
            continue
        seen.add(object_id)
        object_ids.append(object_id)
        if len(object_ids) >= PERSONA_PRESET_BATCH_LOOKUP_LIMIT:
            break

    if not object_ids:
        return {}

    cursor = self.collection.find({"_id": {"$in": object_ids}})
    docs = await cursor.to_list(length=len(object_ids))
    return {
        str(doc["_id"]): self._to_model_dict(doc)
        for doc in docs
        if doc.get("_id") is not None
    }
```

Do not catch MongoDB errors here; the manager's best-effort display hydration owns that fallback. This keeps storage failures observable and avoids silent empty success at the storage boundary.

- [ ] **Step 4: Run focused and existing persona storage tests**

```bash
uv run pytest tests/persona_preset/test_storage_visibility.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/infra/persona_preset/storage.py tests/persona_preset/test_storage_visibility.py
git commit -m "perf: batch persona preset lookups"
```

## Task 2: Hydrate all team-list members from one persona map

**Files:**
- Modify: `tests/unit/infra/test_team_manager.py`
- Modify: `src/infra/team/manager.py`

- [ ] **Step 1: Extend the fixture without weakening validation tests**

Keep `get_by_id = AsyncMock(...)` because `validate_team_members` still uses it. Add:

```python
pm.storage.get_by_ids = AsyncMock(return_value={})
```

Update display-hydration tests to configure/assert `get_by_ids`; do not globally replace validation-path `get_by_id` expectations.

- [ ] **Step 2: Write a failing one-query list hydration test**

```python
@pytest.mark.asyncio
async def test_list_teams_hydrates_all_members_with_one_persona_query(
    manager, mock_storage, mock_persona_manager
):
    first_id = str(ObjectId())
    second_id = str(ObjectId())
    teams = [
        _make_team(
            team_id="team-1",
            members=[
                TeamMemberResponse(
                    member_id="m-1",
                    persona_preset_id=first_id,
                    role_name="Fallback 1",
                ),
                TeamMemberResponse(
                    member_id="m-2",
                    persona_preset_id=second_id,
                    role_name="Fallback 2",
                ),
            ],
        ),
        _make_team(
            team_id="team-2",
            members=[
                TeamMemberResponse(
                    member_id="m-3",
                    persona_preset_id=first_id,
                    role_name="Fallback 3",
                )
            ],
        ),
    ]
    mock_storage.list_teams = AsyncMock(return_value=(teams, 2))
    mock_persona_manager.storage.get_by_ids = AsyncMock(
        return_value={
            first_id: {"name": "Researcher", "avatar": "r.png", "tags": ["r"]},
            second_id: {"name": "Builder", "avatar": None, "tags": ["b"]},
        }
    )

    result = await manager.list_teams(owner_user_id="user-1")

    mock_persona_manager.storage.get_by_ids.assert_awaited_once_with(
        [first_id, second_id]
    )
    assert [team.id for team in result.teams] == ["team-1", "team-2"]
    assert [member.member_id for member in result.teams[0].members] == ["m-1", "m-2"]
    assert result.teams[1].members[0].role_name == "Researcher"
```

Import `ObjectId` in the test module. Add tests proving:

- duplicate preset IDs are passed once in first-seen order;
- missing IDs retain each member's stored `role_name`, `role_avatar`, and `role_tags`;
- invalid IDs remain unchanged;
- a raised bulk lookup logs and returns every original team/member instead of failing the list.

- [ ] **Step 3: Run tests and verify RED**

```bash
uv run pytest tests/unit/infra/test_team_manager.py \
  -k "list_teams_hydrates_all_members or bulk_persona" -v
```

Expected: FAIL because list hydration still calls `get_by_id` once per member.

- [ ] **Step 4: Implement pure map hydration and a batch wrapper**

Refactor the existing reconstruction into a synchronous helper:

```python
@staticmethod
def _hydrate_team_from_personas(
    team: TeamResponse,
    personas: dict[str, dict],
) -> TeamResponse:
    members: list[TeamMemberResponse] = []
    for member in team.members:
        preset = personas.get(member.persona_preset_id)
        if not preset:
            members.append(member)
            continue
        members.append(
            TeamMemberResponse(
                member_id=member.member_id,
                persona_preset_id=member.persona_preset_id,
                agent_id=member.agent_id,
                model_id=member.model_id,
                role_name=preset.get("name", member.role_name),
                role_avatar=preset.get("avatar", member.role_avatar),
                role_tags=preset.get("tags", member.role_tags),
                role_instructions=member.role_instructions,
                position=member.position,
                enabled=member.enabled,
            )
        )
    return team.model_copy(update={"members": members})
```

Add:

```python
async def _hydrate_teams_member_display_metadata(
    self,
    teams: list[TeamResponse],
) -> list[TeamResponse]:
    preset_ids: list[str] = []
    seen: set[str] = set()
    for team in teams:
        for member in team.members:
            preset_id = member.persona_preset_id
            if preset_id and preset_id not in seen:
                seen.add(preset_id)
                preset_ids.append(preset_id)

    try:
        personas = await self.persona_manager.storage.get_by_ids(preset_ids)
    except Exception:
        logger.warning("Failed to batch hydrate team persona metadata", exc_info=True)
        return teams

    return [self._hydrate_team_from_personas(team, personas) for team in teams]
```

Implement the single-team wrapper through the same path:

```python
async def _hydrate_member_display_metadata(self, team: TeamResponse) -> TeamResponse:
    return (await self._hydrate_teams_member_display_metadata([team]))[0]
```

Change `list_teams` to call `_hydrate_teams_member_display_metadata(teams)` once and return that list. Do not parallelize with one task per member; the goal is one database query and bounded memory.

- [ ] **Step 5: Run focused tests and verify GREEN**

```bash
uv run pytest tests/unit/infra/test_team_manager.py \
  -k "hydrate or list_teams or missing_presets" -v
```

Expected: all selected tests PASS.

- [ ] **Step 6: Run the complete team/persona suites**

```bash
uv run pytest \
  tests/unit/infra/test_team_manager.py \
  tests/unit/infra/test_team_storage.py \
  tests/persona_preset \
  tests/api/test_team_routes.py -v
```

Expected: PASS. If older display tests mock only `get_by_id`, update them to mock `get_by_ids` while leaving validation tests unchanged.

- [ ] **Step 7: Commit**

```bash
git add src/infra/team/manager.py tests/unit/infra/test_team_manager.py
git commit -m "perf: hydrate team personas in one batch"
```

## Task 3: Verify query bounds, compatibility, and report evidence

**Files:**
- Modify: `docs/performance-audit-2026-08-09.md`
- Verify: all files above

- [ ] **Step 1: Run focused query-count regression tests**

```bash
uv run pytest \
  tests/persona_preset/test_storage_visibility.py -k "get_by_ids" -v
uv run pytest \
  tests/unit/infra/test_team_manager.py -k "hydrate or list_teams" -v
```

Expected: one persona collection `find` for valid list hydration, zero for empty/all-invalid input, and no call count growth with repeated members.

- [ ] **Step 2: Run backend quality and full test checks**

```bash
make lint
make typecheck
uv run --no-sync pytest
```

Expected: all exit 0.

- [ ] **Step 3: Update the audit ledger**

Record the source evidence for the previous nested serial awaits, the new constant query count, the 4,000-ID bound, preserved ordering/fallback tests, and full-suite results. Mark this finding `optimized`.

- [ ] **Step 4: Commit report update**

```bash
git add docs/performance-audit-2026-08-09.md
git commit -m "docs: record team persona query optimization"
```
