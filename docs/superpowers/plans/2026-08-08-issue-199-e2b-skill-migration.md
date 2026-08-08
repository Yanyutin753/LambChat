# Issue #199 E2B and Skill Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete issue #199 by making the E2B template build/verification path executable, safely migrating obsolete docx skill instructions, and rolling out a verified immutable template with rollback.

**Architecture:** Refactor the existing E2B build script into testable template/build/verify functions using the installed `e2b` SDK, and add a bounded dry-run-first MongoDB migration with compare-and-swap plus expiring backups. External rollout builds a uniquely tagged candidate, verifies its immutable build reference, pins `.env`, restarts only existing services, and restores the previous value on failed health checks.

**Tech Stack:** Python 3.12+, E2B SDK 2.x, Motor/MongoDB, pytest/pytest-asyncio, Ruff, zsh operational checks.

---

### Task 1: Repair and unit-test the E2B template builder

**Files:**
- Modify: `scripts/create_e2b_template.py`
- Create: `tests/scripts/test_create_e2b_template.py`

- [ ] **Step 1: Write failing builder tests**

Import the script under pytest and use fake `Template`/builder objects. Assert it imports `Template` from `e2b`, starts from `code-interpreter-v1`, emits an apt command containing `ripgrep` and `librsvg2-bin`, installs the declared pip packages, and calls `Template.build` with a unique candidate tag, CPU/memory values, API key, and build logger.

```python
def test_template_apt_step_installs_issue_199_commands():
    builder = _RecordingBuilder()
    build_template(builder)
    apt = next(cmd for cmd in builder.commands if "apt-get install" in cmd)
    assert "ripgrep" in apt
    assert "librsvg2-bin" in apt
```

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/scripts/test_create_e2b_template.py -q`

Expected: the current script fails because `e2b_code_interpreter` is unavailable or the testable functions do not exist.

- [ ] **Step 3: Refactor to minimal testable functions**

Use `from e2b import Template, default_build_logger`. Add `build_template()`, `build_candidate(candidate_tag, api_key)`, and an argparse CLI. Build under name `lambchat-prod` with a unique candidate tag such as `candidate-YYYYMMDDHHMMSS`; print the SDK-returned `template_id` and `build_id`, but never the API key. Keep `main()` as a thin validation/CLI wrapper.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `uv run pytest tests/scripts/test_create_e2b_template.py -q`

- [ ] **Step 5: Commit**

```bash
git add scripts/create_e2b_template.py tests/scripts/test_create_e2b_template.py
git commit -m "fix: make E2B template builder executable"
```

### Task 2: Add cleanup-safe immutable template verification

**Files:**
- Modify: `scripts/create_e2b_template.py`
- Modify: `tests/scripts/test_create_e2b_template.py`

- [ ] **Step 1: Write failing verifier tests**

Use a fake sandbox whose `commands.run` records calls. Assert `verify_template("lambchat-prod:<build_id>")` checks `command -v rg`, `command -v rsvg-convert`, writes a tiny SVG, converts it to PNG, and validates a non-empty output. Assert `sandbox.kill()` runs in `finally` on success and command failure. Assert a failed smoke test raises and cannot promote tags.

- [ ] **Step 2: Run verifier tests and verify RED**

Run: `uv run pytest tests/scripts/test_create_e2b_template.py -q`

- [ ] **Step 3: Implement verification and explicit promotion**

Add `verify_template(template_ref, api_key)` using `Sandbox.create(template_ref, timeout=300, api_key=...)`. Run one shell command with `set -euo pipefail`, both `command -v` checks, a temporary SVG, `rsvg-convert`, and `test -s`. Kill the sandbox in `finally`. Add `promote_template(template_ref, api_key)` calling `Template.assign_tags(template_ref, "production", api_key=...)`; never call it from build before verification/health gates.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `uv run pytest tests/scripts/test_create_e2b_template.py -q`

- [ ] **Step 5: Commit**

```bash
git add scripts/create_e2b_template.py tests/scripts/test_create_e2b_template.py
git commit -m "feat: verify E2B template candidates safely"
```

### Task 3: Implement dry-run-first docx skill path migration

**Files:**
- Create: `scripts/migrate_docx_skill_paths.py`
- Create: `tests/scripts/test_migrate_docx_skill_paths.py`

- [ ] **Step 1: Write failing recognition and rewrite tests**

Create fake async collections following `tests/infra/skill/test_legacy_migration_limits.py`. Cover normalized `SKILL.md` records in `skill_files` and `skill_marketplace_files`, legacy `system_skills.content`, and the exact obsolete path. Assert auxiliary/script files, missing `file_path`, and non-docx paths are ambiguous and block apply. Assert the canonical transfer block and placeholder are inserted exactly once.

```python
def test_rewrite_inserts_transfer_instructions_once():
    migrated = rewrite_skill_instructions(LEGACY_COMMAND)
    assert 'transfer_path' in migrated
    assert '/skills/docx/' in migrated
    assert '<transferred-docx-skill-dir>/scripts/office/validate.py' in migrated
    assert rewrite_skill_instructions(migrated) == migrated
```

- [ ] **Step 2: Run recognition tests and verify RED**

Run: `uv run pytest tests/scripts/test_migrate_docx_skill_paths.py -q`

- [ ] **Step 3: Implement bounded scan and dry-run report**

Query only documents containing the exact old path, project `_id`, `file_path`, and `content`, and apply `.batch_size(100)`. Return counts for recognized, ambiguous, migrated, conflicted, and rolled_back without contents or user IDs. The CLI defaults to dry-run and requires `--apply`; any ambiguous count makes apply exit nonzero before writes.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `uv run pytest tests/scripts/test_migrate_docx_skill_paths.py -q`

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_docx_skill_paths.py tests/scripts/test_migrate_docx_skill_paths.py
git commit -m "feat: detect legacy docx skill paths"
```

### Task 4: Add compare-and-swap backups and rollback

**Files:**
- Modify: `scripts/migrate_docx_skill_paths.py`
- Modify: `tests/scripts/test_migrate_docx_skill_paths.py`

- [ ] **Step 1: Write failing apply/rollback tests**

Assert apply creates an idempotent `skill_migration_backups` record before source update, creates a TTL index on `expire_at` with `expireAfterSeconds=0`, and updates with `{"_id": id, "content": original}`. Assert a CAS miss increments `conflicted`. Assert rollback restores only when the current content SHA-256 equals `migrated_content_hash`; later edits are reported and untouched. Assert a second apply has zero pending changes.

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/scripts/test_migrate_docx_skill_paths.py -q`

- [ ] **Step 3: Implement backups, CAS, and `--rollback`**

Use a stable migration ID and an idempotent unique key of migration/collection/source ID. Set `expire_at=utc_now()+timedelta(days=30)`. Insert/upsert backup before each CAS update. Rollback reads backups in bounded batches and uses the migrated hash guard. Make `--apply` and `--rollback` mutually exclusive.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `uv run pytest tests/scripts/test_migrate_docx_skill_paths.py -q`

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_docx_skill_paths.py tests/scripts/test_migrate_docx_skill_paths.py
git commit -m "feat: migrate docx skill paths with rollback"
```

### Task 5: Run repository verification before external changes

**Files:**
- Modify only if a regression is found: files from Tasks 1-4

- [ ] **Step 1: Run focused tests**

```bash
uv run pytest tests/scripts/test_create_e2b_template.py tests/scripts/test_migrate_docx_skill_paths.py tests/infra/backend/test_e2b_glob.py -q
```

- [ ] **Step 2: Run Ruff**

```bash
uv run ruff check scripts/create_e2b_template.py scripts/migrate_docx_skill_paths.py tests/scripts/test_create_e2b_template.py tests/scripts/test_migrate_docx_skill_paths.py
```

- [ ] **Step 3: Run the migration live dry-run**

Run: `uv run python scripts/migrate_docx_skill_paths.py`

Expected for the currently configured database: zero matches and no writes. If ambiguous matches exist, stop rollout, repair them manually, and rerun dry-run; do not use `--apply` while ambiguity remains.

- [ ] **Step 4: Apply only when recognized matches exist**

Run: `uv run python scripts/migrate_docx_skill_paths.py --apply`

Then rerun dry-run and require zero matches. When the initial live dry-run is zero, skip `--apply`; automated tests are the rollback evidence.

### Task 6: Build, verify, switch, and promote the E2B candidate

**Files:**
- Modify external/untracked configuration only after successful verification: `.env`

- [ ] **Step 1: Capture prior config and running service set**

Read `E2B_TEMPLATE` without echoing other `.env` values. Record running LambChat backend/worker process identifiers or container/service names using read-only commands. Do not start previously stopped services.

- [ ] **Step 2: Build a uniquely tagged candidate**

Run: `uv run python scripts/create_e2b_template.py build`

Capture the returned immutable reference `lambchat-prod:<build_id>`.

- [ ] **Step 3: Verify the immutable candidate**

Run: `uv run python scripts/create_e2b_template.py verify --template-ref 'lambchat-prod:<build_id>'`

Expected: `rg`, `rsvg-convert`, and SVG conversion all pass; the temporary sandbox is killed.

- [ ] **Step 4: Pin `.env` and restart only the recorded service set**

Update only the `E2B_TEMPLATE=` line to the immutable reference. Restart the same backend/worker services using their existing supervisor/Compose/systemd/dev command. Verify `http://127.0.0.1:8000/health` or the configured health endpoint and confirm workers reconnect.

- [ ] **Step 5: Roll back on failed health**

On any failure, restore the exact prior `E2B_TEMPLATE`, restart the recorded service set again, verify recovery, and stop. Do not assign the production tag.

- [ ] **Step 6: Promote only after healthy restart**

Run: `uv run python scripts/create_e2b_template.py promote --template-ref 'lambchat-prod:<build_id>'`

### Task 7: Final combined verification and issue closure

**Files:**
- No repository file changes expected

- [ ] **Step 1: Run combined #198/#199 tests and Ruff**

Use all focused commands from both plans, then run the broader affected suites:

```bash
uv run pytest tests/infra/mcp tests/infra/tool/test_mcp_client.py tests/scripts/test_create_e2b_template.py tests/scripts/test_migrate_docx_skill_paths.py tests/infra/backend/test_e2b_glob.py -q
uv run ruff check src/infra/mcp src/infra/tool/mcp_client.py scripts/create_e2b_template.py scripts/migrate_docx_skill_paths.py tests/infra/mcp tests/infra/tool/test_mcp_client.py tests/scripts
```

- [ ] **Step 2: Re-fetch issues immediately before writing**

```bash
gh issue view 198 --repo Yanyutin753/LambChat --json state,comments,updatedAt,url
gh issue view 199 --repo Yanyutin753/LambChat --json state,comments,updatedAt,url
```

- [ ] **Step 3: Post verification evidence and close #198/#199**

Summarize code commits, test counts, sanitized Tavily usage probe, E2B immutable build reference, smoke-test commands, health result, and Mongo migration counts. Never include secrets. Close only after all acceptance criteria pass.

- [ ] **Step 4: Confirm the remaining open issue list**

Run: `gh issue list --repo Yanyutin753/LambChat --state open --limit 100`

Confirm #158 remains open as an empty bug-collection tracker and #203 remains an enhancement request; do not close either as a code bug.
