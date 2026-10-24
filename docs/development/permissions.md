# Permission boundaries

Permissions are exact capabilities, combined across the account's current roles. The backend is authoritative; frontend controls and Agent tool discovery reflect the same contract. A hidden button or an earlier role snapshot never authorizes an operation. User-owned data additionally requires ownership, including for administrators.

## Administrative duties

| Duty | Capabilities |
| --- | --- |
| Highest-trust administration | `system:admin`; explicit delegation and account protection exceptions, not implicit access to private user content |
| Account operations | `user:read`, `user:create`, `user:write` (profile), `user:status`, `user:reset_password`, `user:assign_roles`, `user:delete` |
| Role operations | `role:read`, `role:write` (metadata and non-budget limits), `role:grant`, `role:delete` |
| Quotas and usage | `usage:read` (own), `usage:admin` (global reporting), `usage:quota_manage` (budget and reset operations) |
| Model configuration | `model:read`, `model:admin` (create/update), `model:delete`, `model:assign`, `pricing:manage` |
| Agent configuration | `agent:config_read`, `agent:admin` (configuration), `agent:assign` |
| System settings | `settings:read`, `settings:manage` (ordinary configuration), `settings:security`, `settings:reset` |
| System MCP | `mcp:system_read`, `mcp:admin` (configuration), `mcp:system_delete`, `mcp:policy_manage`, `mcp:export` |
| Notifications | `notification:read`, `notification:manage` (publish/update), `notification:delete` |

Role assignment is bounded by explicit `assignable_role_ids`. Permission delegation is bounded by `grantable_permissions` and the operator's own capabilities. Account takeover operations and role assignment also compare the effective model and Agent scope. An operator cannot reset credentials for an account with stronger authority. Mutations reload current authority under a shared, expiring lock. Removing the last active administrator who can log in is rejected.

Model access is explicit: `unrestricted_models=true` means unrestricted; an empty list, missing role, or absent mapping grants no models. A fallback model needs its own authorization. Agent/model assignment capabilities authorize configuration changes, not execution outside the operator's permitted scope.

## Personal resources and tools

Projects, memory, sessions, skills, teams, environment variables and scheduled tasks have separate read/write/delete capabilities. Memory export is separate. File reads/deletes and sandbox read/execute/manage are distinct; upload categories retain their existing individual grants. `envvar:reveal` additionally gates direct plaintext secret retrieval. Arbitrary sandbox execution can inspect variables injected into its own environment; assign `sandbox:execute` only to users trusted with those runtime credentials.

Private MCP editing requires the capability for its stored transport. Ordinary MCP read permission permits personal enablement preferences, not server configuration changes. System policy administration and credential export are separate. Responses mask URL credentials, paths and custom header values; exact export requires explicit authority. Model configuration also masks keys and custom header values.

Agent invocation reloads the account and validates enabled models and Agents. Delayed MCP calls and personal tools recheck current permissions at execution. The shared file backend enforces path-specific skill, memory, file and sandbox authority, including aggregate searches and transfers. Server-generated execution artifacts use narrowly scoped internal authority rather than granting model tools an exception.

## Migration and operation

The active permission catalog is defined by `Permission` in `src/kernel/types.py` and `get_permissions_response()` in `src/kernel/schemas/permission.py`. Frontend permission values and all five locale catalogs are contract-tested against it.

Startup performs the idempotent `permission_boundaries_v1` migration before readiness. Existing custom roles retain their prior effective capabilities through a one-time expansion; legacy unrestricted model access becomes an explicit stored flag. New roles default to no model access and no delegation scope. Review migrated custom roles and remove duties they should no longer hold. Migration failures prevent startup readiness.

Retired capabilities (`chat:read`, `session:admin`, `skill:admin`, `role:manage`) remain parseable for historical records but are absent from editable catalogs and never authorize requests. Legacy direct Agent chat routes have been removed; callers use the validated session-based chat API. Internal resolved model configuration and handoff accounting are excluded from session persistence and public serialization, including legacy sessions.
