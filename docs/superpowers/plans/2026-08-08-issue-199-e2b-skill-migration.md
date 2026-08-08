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
- Modify: `.gitignore`

- [ ] **Step 1: Write failing builder tests**

Import the script under pytest and use fake `Template`/builder objects. Assert it imports `Template` from `e2b`, starts from `code-interpreter-v1`, emits an apt command containing `ripgrep` and `librsvg2-bin`, installs the declared pip packages, and calls `Template.build` with a unique candidate tag, CPU/memory values, API key, and build logger. With a fake `SettingsService`, assert the CLI resolves `E2B_API_KEY` database-first and never prints it.

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

Add `.gitignore` exceptions for the tracked operational scripts in this plan. Use `from e2b import Template, default_build_logger`. Add `build_template()`, `build_candidate(candidate_tag, api_key)`, and an argparse CLI. Resolve the build key through `SettingsService.get_raw("E2B_API_KEY")`, which honors database-first configuration. Build under name `lambchat-prod` with a unique candidate tag such as `candidate-YYYYMMDDHHMMSS`; write a UUID `rollout_id`, the SDK-returned template/build IDs, and immutable reference to an ignored `workspace/e2b-rollouts/<candidate>.json` manifest, but never the API key. Keep `main()` as a thin async validation/CLI wrapper.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `uv run pytest tests/scripts/test_create_e2b_template.py -q`

- [ ] **Step 5: Commit**

```bash
git add .gitignore scripts/create_e2b_template.py tests/scripts/test_create_e2b_template.py
git commit -m "fix: make E2B template builder executable"
```

### Task 2: Add cleanup-safe manifest verification and effective-config guards

**Files:**
- Modify: `scripts/create_e2b_template.py`
- Modify: `tests/scripts/test_create_e2b_template.py`

- [ ] **Step 1: Write failing verifier tests**

Use a fake sandbox whose `commands.run` records calls. Assert `verify_manifest(path)` reads the immutable reference from the build manifest, checks `command -v rg`, `command -v rsvg-convert`, writes a tiny SVG, converts it to PNG, and validates a non-empty output. Assert `sandbox.kill()` runs in `finally` on success and command failure. Assert successful verification atomically writes `verified_at` and `verified_build_id` to the same manifest. A failed smoke test must leave those fields absent and cannot promote tags.

With fake `system_settings` storage and a temporary `.env`, test first-pin CAS, idempotent retry, rejection of a concurrent administrator value, and preservation of the original database-document existence/value plus env line. Test restore deletes a rollout-created database document when none existed, restores an existing document when it did, and refuses after a later edit. Test `verify_effective_configuration` and `record_health` reject any manifest/config mismatch. Test `promote_manifest` reads the reference only from the fully verified manifest.

- [ ] **Step 2: Run verifier tests and verify RED**

Run: `uv run pytest tests/scripts/test_create_e2b_template.py -q`

- [ ] **Step 3: Implement verification and explicit promotion**

Add `verify_manifest(manifest_path, api_key)` using `Sandbox.create(manifest["immutable_ref"], timeout=300, api_key=...)`. Run one shell command with `set -euo pipefail`, both `command -v` checks, a temporary SVG, `rsvg-convert`, and `test -s`. Kill the sandbox in `finally` and atomically update only that manifest on success.

Add async `pin_effective_configuration(manifest_path, env_file)` that treats MongoDB `system_settings.E2B_TEMPLATE` as authoritative and `.env` only as fallback. On the first pin it records, exactly once, whether a database document existed, its previous value/update metadata, the prior `.env` line, and the environment-file path. It then compare-and-swaps the database setting to the immutable candidate, aligns the `.env` fallback, publishes the setting change, and records `pinned_ref`. A second call is idempotent only when the manifest and both sources already equal the candidate; it must never overwrite the original rollback baseline. Any unrelated current value causes a conflict and abort.

Add the inverse `restore_effective_configuration(manifest_path)`, also compare-and-swap guarded: restore the saved database document or delete the rollout-created document when none existed, restore the saved `.env` fallback, publish the setting change, and refuse to overwrite a later administrator edit.

Add `verify_effective_configuration(manifest_path)` using `SettingsService.get_raw("E2B_TEMPLATE")`; it records `effective_ref_verified_at` only when the database-first value equals the manifest immutable reference. Add `record_health(manifest_path, health_url)` that performs the health request itself and records `health_checked_at` only after verified build, pin, and effective-config evidence all match. Add `promote_manifest(manifest_path, api_key)` that accepts no caller-provided template reference, refuses unless every preceding manifest field matches, and then calls `Template.assign_tags(manifest["immutable_ref"], "production", api_key=...)`.

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
- Modify: `.gitignore`

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

Add a `.gitignore` exception for `scripts/migrate_docx_skill_paths.py`. Query only documents containing the exact old path, project `_id`, `file_path`, and `content`, and apply `.batch_size(100)`. Return counts for recognized, ambiguous, migrated, conflicted, and rolled_back without contents or user IDs. The CLI defaults to dry-run and requires `--apply`; any ambiguous count makes apply exit nonzero before writes.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `uv run pytest tests/scripts/test_migrate_docx_skill_paths.py -q`

- [ ] **Step 5: Commit**

```bash
git add .gitignore scripts/migrate_docx_skill_paths.py tests/scripts/test_migrate_docx_skill_paths.py
git commit -m "feat: detect legacy docx skill paths"
```

### Task 4: Add compare-and-swap backups and rollback

**Files:**
- Modify: `scripts/migrate_docx_skill_paths.py`
- Modify: `tests/scripts/test_migrate_docx_skill_paths.py`

- [ ] **Step 1: Write failing apply/rollback tests**

Assert apply requires a unique rollout manifest/ID, creates an idempotent `skill_migration_backups` record before source update, creates a TTL index on `expire_at` with `expireAfterSeconds=0`, and updates with `{"_id": id, "content": original}`. Assert the exact backup/source IDs changed by this apply are appended atomically to that rollout manifest. Assert a CAS miss increments `conflicted`. Assert rollback reads only IDs recorded in the supplied rollout manifest and restores only when the current content SHA-256 equals `migrated_content_hash`; later edits are reported and untouched. Assert backups from an earlier rollout ID are never selected. Assert a second apply has zero pending changes.

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/scripts/test_migrate_docx_skill_paths.py -q`

- [ ] **Step 3: Implement backups, CAS, and `--rollback`**

Use a stable migration-kind ID plus the unique `rollout_id` generated in the E2B build manifest. The backup unique key is migration-kind/rollout/collection/source ID. Set `expire_at=utc_now()+timedelta(days=30)`. Insert/upsert backup before each CAS update and append the changed backup/source ID to the manifest only after the source CAS succeeds. `--apply --manifest <path>` and `--rollback --manifest <path>` are mutually exclusive; rollback queries only the manifest's rollout ID and recorded IDs, then applies the migrated hash guard.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `uv run pytest tests/scripts/test_migrate_docx_skill_paths.py -q`

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_docx_skill_paths.py tests/scripts/test_migrate_docx_skill_paths.py
git commit -m "feat: migrate docx skill paths with rollback"
```

### Task 5: Propagate E2B settings in supported Compose deployment

**Files:**
- Modify: `deploy/docker-compose.yml`
- Modify: `deploy/.env.example`
- Create: `tests/deploy/test_docker_compose_sandbox_env.py`

- [ ] **Step 1: Write a failing Compose environment test**

Load `deploy/docker-compose.yml` with `yaml.safe_load` and assert the `lambchat` service passes both `E2B_API_KEY=${E2B_API_KEY:-}` and `E2B_TEMPLATE=${E2B_TEMPLATE:-base}`. Assert `deploy/.env.example` documents both variables without a real key.

- [ ] **Step 2: Run the test and verify RED**

Run: `uv run pytest tests/deploy/test_docker_compose_sandbox_env.py -q`

- [ ] **Step 3: Add only the required Compose environment mappings**

Add the two variables to `lambchat.environment` and safe placeholders to `deploy/.env.example`. Do not expose the host key in committed files.

- [ ] **Step 4: Run the test and verify GREEN**

Run: `uv run pytest tests/deploy/test_docker_compose_sandbox_env.py -q`

- [ ] **Step 5: Commit**

```bash
git add deploy/docker-compose.yml deploy/.env.example tests/deploy/test_docker_compose_sandbox_env.py
git commit -m "fix: pass E2B template settings to Compose"
```

### Task 6: Run repository verification and migration preflight

**Files:**
- Modify only if a regression is found: files from Tasks 1-5

- [ ] **Step 1: Run focused tests**

```bash
uv run pytest tests/scripts/test_create_e2b_template.py tests/scripts/test_migrate_docx_skill_paths.py tests/deploy/test_docker_compose_sandbox_env.py tests/infra/backend/test_e2b_glob.py -q
```

- [ ] **Step 2: Run Ruff**

```bash
uv run ruff check scripts/create_e2b_template.py scripts/migrate_docx_skill_paths.py tests/scripts/test_create_e2b_template.py tests/scripts/test_migrate_docx_skill_paths.py tests/deploy/test_docker_compose_sandbox_env.py
```

- [ ] **Step 3: Run the migration live dry-run**

Run: `uv run python scripts/migrate_docx_skill_paths.py`

Expected for the currently configured database: zero matches and no writes. If ambiguous matches exist, stop rollout, repair them manually, and rerun dry-run; do not use `--apply` while ambiguity remains.

- [ ] **Step 4: Record preflight counts without applying yet**

Candidate build and smoke verification must succeed before any MongoDB write. Save only the aggregate recognized/ambiguous counts for the later rollout step.

### Task 7: Build, verify, migrate, switch, and promote one manifest-bound candidate

**Files:**
- Modify external/untracked configuration only after successful verification: `.env`

- [ ] **Step 1: Capture prior config and running service set**

Use `SettingsService.get_raw("E2B_TEMPLATE")` to record the database-first effective template without echoing other settings. Separately record the fallback `.env` line and running LambChat backend/worker process identifiers or container/service names using read-only commands. Do not start previously stopped services.

- [ ] **Step 2: Build a uniquely tagged candidate and manifest**

Run: `uv run python scripts/create_e2b_template.py build`

Capture the emitted manifest path. All subsequent commands accept that manifest path and no manually copied build reference.

- [ ] **Step 3: Verify the immutable candidate**

Run: `uv run python scripts/create_e2b_template.py verify --manifest '<manifest-path>'`

Expected: `rg`, `rsvg-convert`, and SVG conversion all pass; the temporary sandbox is killed.

- [ ] **Step 4: Apply the migration only after candidate verification**

If preflight reported recognized matches, run `uv run python scripts/migrate_docx_skill_paths.py --apply --manifest '<manifest-path>'`, then require a zero-match dry-run. If preflight was zero, skip writes. The script records the exact changed backup/source IDs in this rollout manifest so rollback is conditional and scoped.

- [ ] **Step 5: Pin `.env` and recreate only a running Compose app**

Select the environment file actually used by the detected runtime and run `uv run python scripts/create_e2b_template.py pin-config --manifest '<manifest-path>' --env-file '<env-file>'`; do not copy the build reference manually. This command compare-and-swaps the database-first `system_settings` value and aligns the `.env` fallback while preserving the first rollback baseline.

If `docker compose --env-file '<env-file>' -f deploy/docker-compose.yml ps --status running lambchat` shows the app running, first validate interpolation with `docker compose --env-file '<env-file>' -f deploy/docker-compose.yml config`, then use `docker compose --env-file '<env-file>' -f deploy/docker-compose.yml up -d --force-recreate --no-deps lambchat`; plain `restart` is forbidden because it does not reload environment. Run `uv run python scripts/create_e2b_template.py verify-effective --manifest '<manifest-path>'` to require the database-first value to equal the candidate, then run the health check.

If no app service is running, do not start one; the pinned setting applies on the next start. If a native `main.py` process is running without a supervisor, stop and ask for the exact restart mechanism rather than killing it heuristically; do not promote until the running process has been demonstrably restarted with the manifest reference.

- [ ] **Step 6: Roll back config and migrated data on failed health**

On any failure after migration apply, run `uv run python scripts/create_e2b_template.py restore-config --manifest '<manifest-path>'`, force-recreate the same Compose service with the same explicit `--env-file` when applicable, run `uv run python scripts/migrate_docx_skill_paths.py --rollback --manifest '<manifest-path>'`, verify effective configuration, recovery health, and migration counts, and stop. Do not assign the production tag.

- [ ] **Step 7: Record health and promote only through the manifest**

Run:

```bash
uv run python scripts/create_e2b_template.py record-health --manifest '<manifest-path>' --url 'http://127.0.0.1:8000/health'
uv run python scripts/create_e2b_template.py promote --manifest '<manifest-path>'
```

After promotion, query `Template.get_tags("lambchat-prod")` and require the `production` tag to resolve to the manifest's `build_id`; record only the non-secret IDs.

### Task 8: Final combined verification and issue closure

**Files:**
- No repository file changes expected

- [ ] **Step 1: Run combined #198/#199 tests and Ruff**

Use all focused commands from both plans, then run the broader affected suites:

```bash
uv run pytest tests/infra/mcp tests/infra/tool/test_mcp_client.py tests/scripts/test_check_tavily_usage.py tests/scripts/test_create_e2b_template.py tests/scripts/test_migrate_docx_skill_paths.py tests/deploy/test_docker_compose_sandbox_env.py tests/infra/backend/test_e2b_glob.py -q
uv run ruff check src/infra/mcp src/infra/tool/mcp_client.py scripts/check_tavily_usage.py scripts/create_e2b_template.py scripts/migrate_docx_skill_paths.py tests/infra/mcp tests/infra/tool/test_mcp_client.py tests/scripts tests/deploy/test_docker_compose_sandbox_env.py
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
