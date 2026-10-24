# Permission Boundaries Implementation Plan

> **For agentic workers:** Use the authorized parallel domain tasks below; the coordinator owns integration and all validation. Do not create worktrees or commit shared changes.

**Goal:** Resolve all findings in the 2026-10-24 permission audit, make capabilities consistent across HTTP, frontend and Agent tools, and verify denial before side effects.

**Architecture:** Keep the existing permission enum, role storage, ownership checks and FastAPI dependencies. Split administrative duties into explicit capabilities; migrate existing grants once without turning legacy permissions into permanent wildcard aliases. Treat system administration as an explicit protected capability and keep personal data owner-scoped.

**Tech Stack:** Python/FastAPI/Pydantic/MongoDB/Redis, React/TypeScript, pytest/Vitest.

**Spec:** `/Users/clivia/.codex/validation/permission-audit-20261024/report.md` (all 13 findings and 54 current permissions).

## Global Constraints

- Preserve shared uncommitted authentication changes. Current HEAD already equals fetched origin/develop; no rebase or checkout needed.
- All validation uses `python3 scripts/run_validation.py`, one worker/job, nonblocking; only coordinator runs it.
- User authorized direct implementation of the report; no additional design approval or deployment is requested.
- Keep current API paths except unsafe unused legacy direct Agent invocation, which must enter the protected submission flow or be removed after caller search.
- Keep old enum values parseable for migration but hide retired grants from the editable catalog. No runtime wildcard admin aliases.
- User-visible labels/descriptions and new errors cover zh/en/ja/ko/ru; reuse existing layout and theme components.
- Explicit `system:admin` marks highest-trust authority. Neither it nor any other administrator bypasses personal ownership.
- Delegated grants must be explicitly scoped and cannot grant system administration; never inherit grant authority merely from editing users or roles.
- Preserve explicit empty allowlists. No-role and invalid-role execution must fail closed; migrate old unrestricted model assignments to explicit state before using strict resolution.

## Shared Permission Contract

Keep existing enum members except hide legacy `chat:read`, `session:admin`, `skill:admin`, `role:manage` from the editable catalog after one-time migration.

New members (enum name = value):

```
SYSTEM_ADMIN=system:admin
USER_CREATE=user:create
USER_STATUS=user:status
USER_RESET_PASSWORD=user:reset_password
USER_ASSIGN_ROLES=user:assign_roles
ROLE_READ=role:read
ROLE_WRITE=role:write
ROLE_DELETE=role:delete
ROLE_GRANT=role:grant
SETTINGS_READ=settings:read
SETTINGS_SECURITY=settings:security
SETTINGS_RESET=settings:reset
MCP_SYSTEM_READ=mcp:system_read
MCP_SYSTEM_DELETE=mcp:system_delete
MCP_POLICY_MANAGE=mcp:policy_manage
MCP_EXPORT=mcp:export
FILE_READ=file:read
FILE_DELETE=file:delete
AGENT_CONFIG_READ=agent:config_read
AGENT_ASSIGN=agent:assign
MODEL_READ=model:read
MODEL_DELETE=model:delete
MODEL_ASSIGN=model:assign
PRICING_MANAGE=pricing:manage
PROJECT_READ=project:read
PROJECT_WRITE=project:write
PROJECT_DELETE=project:delete
MEMORY_READ=memory:read
MEMORY_WRITE=memory:write
MEMORY_DELETE=memory:delete
MEMORY_EXPORT=memory:export
SANDBOX_READ=sandbox:read
SANDBOX_EXECUTE=sandbox:execute
SANDBOX_MANAGE=sandbox:manage
PERSONA_PRESET_DELETE=persona_preset:delete
ENVVAR_REVEAL=envvar:reveal
NOTIFICATION_READ=notification:read
NOTIFICATION_DELETE=notification:delete
USAGE_QUOTA_MANAGE=usage:quota_manage
```

Existing `user:write` edits account profile only; `role:write` edits metadata, `role:grant` edits authority; `usage:admin` is global read; `model:admin`, `agent:admin`, `mcp:admin` maintain their configurations; other capabilities are separate, not implied. `feedback:read` is global read and `feedback:admin` removes feedback. Existing personal write/delete permissions remain independent. No separate install/run/public-share permission unless an actual caller requires it; install requires marketplace:read AND skill:write.

Role schemas gain explicit `grantable_permissions` and `assignable_role_ids` arrays; TokenPayload carries their union loaded from current roles. A non-system administrator must possess the granted permission AND have it in grantable_permissions; role assignment must use an allowed role ID. Scopes themselves require grant authority and may not exceed the caller's scope. Protect superior accounts and self-escalation; serialize changes affecting highest-trust accounts to preserve a usable administrator.

## Review Focus

- Empty vs absent assignments, extra unconfigured roles, and deleted roles must not unlock all models/Agents.
- Lowered permissions must also affect Agent tools, delayed discovery and background/recovery execution before new side effects.
- A read-only account must not write/delete via indirect routes such as project cascades, skill installation or old chat endpoints.
- A delegated account manager must not modify credentials, status or roles of a superior account or escalate itself.
- Existing role migration must be idempotent, apply to custom roles and preserve administrator access without broadening read-only grants.

## Tasks

### Task 1: Catalog, migration and shared authority (coordinator)

- [ ] Write denial/catalog/migration tests first and run RED with the shared validation lock.
- [ ] Add enum and metadata, hide retired grants, migrate existing role grants once; add personal capability defaults based on existing write/read access.
- [ ] Split model/Agent/MCP/settings/pricing/usage/notification duties and redact credentials in read views.
- [ ] Make model authorization explicit and Agent execution validate its allowed scope in all entry paths.
- [ ] Run targeted and full required verification serially after integration.

### Task 2: Delegated account/role authority (domain agent)

- [ ] Tests first: role assignment self-escalation, grant ceiling, protected targets, last-admin and internal-field rejection.
- [ ] Implement user and role request/response schemas, dependencies, scoped delegation and consistent rejection before persistence.
- [ ] Preserve concurrent edits in user storage; do not rewrite shared authentication changes.
- [ ] Return files, test cases and review concerns. Coordinator runs all validation.

### Task 3: Personal capabilities and Agent tools (domain agent)

- [ ] Tests first for no-permission/owner/non-owner HTTP and tool use.
- [ ] Enforce sessions, projects, teams, memories, files, bookmarks, marketplace installation, persona deletion, sandbox capabilities and chat continuation controls.
- [ ] Share current-user permission checks between tool discovery and execution; remove chat:write substitutions for team/persona permissions.
- [ ] Retain all ownership checks, share revocation and personal preference behavior.
- [ ] Return changed files/test cases; coordinator runs validation.

### Task 4: Frontend and five-language contract (domain agent)

- [ ] Add TS enum and current-authority response fields matching this contract.
- [ ] Update routes, menus and operation controls for all split administrative and personal capabilities, including user form field authorization and grant-scope editing.
- [ ] Update all five locale labels/descriptions using the existing translation structure, retire obsolete editable catalog entries.
- [ ] Add focused behavior/contract tests; coordinator runs validation after all code is integrated.

### Task 5: Integration and verification (coordinator)

- [ ] Review all report findings against final code, callers, fixtures and migrations.
- [ ] Run focused backend/frontend tests, backend tests, frontend tests, Ruff/Mypy, frontend lint/typecheck/build, localization/catalog parity and diff checks through one validation slot, serially.
- [ ] Inspect responsive access-control forms and disabled/empty/error states where local environment supports it; run Impeccable if installed, otherwise DESIGN.md checklist.
- [ ] Fresh independent code review of the authorization change; resolve correctness/security findings and rerun affected checks.
- [ ] Record exact passed/failed/blocked checks and remaining operational migration/deployment limitations outside the repository; do not deploy or commit unrelated changes.
