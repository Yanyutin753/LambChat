# Memory Index ID Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove opaque internal memory IDs from the model-facing memory index while preserving useful relative-age and staleness metadata.

**Architecture:** Keep the existing `build_memory_index` selection, grouping, ordering, labeling, and cache flow unchanged. Narrow only the MongoDB projection and line formatter, with a deterministic output-level regression test that fixes the clock and exercises both same-day and stale entries.

**Tech Stack:** Python 3.12+, pytest, pytest-asyncio, Ruff

## Global Constraints

- Preserve memory selection, type grouping, ordering, labels, age calculation, staleness thresholds, cache behavior, and recall behavior.
- Do not change memory records, public memory APIs, recall-tool results, the Memory Space UI, or ID-based deletion and update operations.
- Follow strict RED-GREEN-REFACTOR: verify the new regression test fails before changing production code.
- Keep the change limited to the native memory index generator and its focused tests.

---

## File Structure

- Modify `tests/infra/memory/native/test_indexing.py`: add one output-level regression test for ID-free current and stale index entries.
- Modify `src/infra/memory/client/native/indexing.py`: stop projecting `memory_id` and render each line from its label plus optional age metadata only.

### Task 1: Render the Memory Index Without Internal IDs

**Files:**
- Modify: `tests/infra/memory/native/test_indexing.py`
- Modify: `src/infra/memory/client/native/indexing.py:61-128`

**Interfaces:**
- Consumes: `build_memory_index(backend, user_id: str) -> str` and its existing backend collection/cache contract.
- Produces: the same `build_memory_index` interface, with ID-free `<memory_index>` text.

- [ ] **Step 1: Add the output-level regression test**

Append this test to `tests/infra/memory/native/test_indexing.py`:

```python
@pytest.mark.asyncio
async def test_build_memory_index_omits_internal_ids_but_keeps_age_metadata(monkeypatch):
    class FakeCursor:
        def __init__(self, docs):
            self._docs = docs

        def sort(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        async def to_list(self, length):
            return self._docs[:length]

    class FakeCollection:
        def __init__(self, docs):
            self._docs = docs

        def find(self, *_args, **_kwargs):
            return FakeCursor(self._docs)

    class FakeBackend:
        _INDEX_CACHE_MAX_SIZE = 10

        def __init__(self, docs):
            self._collection = FakeCollection(docs)
            self._index_cache = {}

    now = datetime(2026, 4, 2, tzinfo=timezone.utc)
    monkeypatch.setattr("src.infra.memory.client.native.indexing.utc_now", lambda: now)
    docs = [
        {
            "memory_id": "fresh-private-id",
            "memory_type": "user",
            "title": "Current preference",
            "summary": "Current preference",
            "updated_at": now,
            "source": "manual",
            "access_count": 1,
        },
        {
            "memory_id": "stale-private-id",
            "memory_type": "user",
            "title": "Older preference",
            "summary": "Older preference",
            "updated_at": datetime(2026, 3, 1, tzinfo=timezone.utc),
            "source": "manual",
            "access_count": 1,
        },
    ]

    index = await build_memory_index(FakeBackend(docs), user_id="u1")

    assert index == (
        "<memory_index>\n"
        "\n## [user]\n"
        "- Current preference\n"
        "- Older preference (stale:32d)\n"
        "\n</memory_index>"
    )
```

This test catches any formatter that exposes `memory_id`, emits empty
parentheses for a same-day entry, or drops staleness metadata.

- [ ] **Step 2: Run the new test and verify RED**

Run:

```bash
uv run pytest tests/infra/memory/native/test_indexing.py::test_build_memory_index_omits_internal_ids_but_keeps_age_metadata -v
```

Expected: FAIL because the actual lines contain `fresh-` and `stale-`, the
first six characters of the two fixture IDs.

- [ ] **Step 3: Apply the minimal formatter and projection change**

In `src/infra/memory/client/native/indexing.py`, remove the unused field from
the projection:

```python
    projection = {
        "title": 1,
        "index_label": 1,
        "summary": 1,
        "updated_at": 1,
        "memory_type": 1,
        "source": 1,
        "access_count": 1,
    }
```

Replace the `short_id` formatting branch with this single output operation:

```python
            lines.append(f"- {display_title} ({age_str})" if age_str else f"- {display_title}")
```

Do not change the age calculation or any surrounding selection and cache
logic.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run:

```bash
uv run pytest tests/infra/memory/native/test_indexing.py::test_build_memory_index_omits_internal_ids_but_keeps_age_metadata -v
```

Expected: PASS.

- [ ] **Step 5: Run the complete indexing test file**

Run:

```bash
uv run pytest tests/infra/memory/native/test_indexing.py -v
```

Expected: all tests PASS, including the existing type-priority test.

- [ ] **Step 6: Run the native-memory regression suite and focused lint**

Run:

```bash
uv run pytest tests/infra/memory/native -q
uv run ruff check src/infra/memory/client/native/indexing.py tests/infra/memory/native/test_indexing.py
```

Expected: both commands exit successfully with no failures or Ruff errors.

- [ ] **Step 7: Review and commit the implementation**

Confirm the diff contains only the planned generator and test changes:

```bash
git diff --check
git diff -- src/infra/memory/client/native/indexing.py tests/infra/memory/native/test_indexing.py
```

Then commit only those files:

```bash
git add src/infra/memory/client/native/indexing.py tests/infra/memory/native/test_indexing.py
git commit -m "fix(memory): hide internal ids from index"
```
