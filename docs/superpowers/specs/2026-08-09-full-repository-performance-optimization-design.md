# Full-Repository Performance Optimization Design

## Goal

Audit the complete LambChat codebase for meaningful performance problems, optimize the
highest-value findings without changing product behavior, and leave deterministic regression
guards plus a traceable audit report.

The audit covers Python backend code, React/TypeScript frontend code, storage and concurrency
paths, production bundle behavior, PWA caching, and build/test tooling. "Complete" means every
source area is included in the audit inventory; it does not mean applying every static lint
suggestion. A finding is changed only when evidence shows material runtime, network, memory, or
database-I/O benefit.

## Baseline and Confirmed Findings

The initial baseline on 2026-08-09 produced these measurements:

- `pnpm run build`: 39.38 seconds wall time and 3,162,728 KiB peak RSS.
- Initial eager JavaScript: about 644 KiB gzip, excluding CSS.
- PWA precache: 309 entries and 18,153.33 KiB.
- Multiple generated chunks exceed 1 MiB.
- Rollup reports a cross-chunk circular dependency involving `SubagentBlock.tsx`, the
  `SubagentBlocks.tsx` barrel, and external-navigation code.
- `uv run --no-sync pytest -q --durations=40`: 2,390 passed, 1 skipped in 68.84 seconds wall
  time and 841,488 KiB peak RSS.
- The repository has no unified performance benchmark or artifact-size budget.

Static and source inspection confirmed two backend I/O amplification patterns:

- Session history enumerates traces and awaits `read_trace_events_compat` once per trace, so
  MongoDB round trips grow with the number of runs.
- Team list hydration awaits one persona lookup per member and then hydrates teams serially,
  producing an N+1 query pattern.

Ruff's `ASYNC` and `PERF` rules report 48 findings. Those findings are audit inputs, not an
automatic edit list: many are timeout-parameter rules, comprehensions with negligible impact,
or intentional polling loops.

## Chosen Strategy

Use a hybrid, evidence-led program:

1. Inventory every source area with static checks and source inspection.
2. Measure production artifacts and representative critical paths.
3. Implement high-confidence improvements in ordered workstreams.
4. Add deterministic regression guards for the affected resource.
5. Record every finding and disposition in a repository audit report.

Static-only optimization was rejected because it rewards micro-edits without proving user
benefit. Critical-path-only profiling was rejected because it would not provide the requested
whole-repository coverage.

## Phase 0: Whole-Repository Inventory and Triage

Create the skeleton of `docs/performance-audit-2026-08-09.md` before the first optimization.
Populate its inventory and initial findings first, update it after every workstream, and finalize
it in workstream 4. This ordering ensures later workstreams are selected from a complete inventory
instead of discovering omitted areas after implementation.

The inventory has these explicit surfaces:

| Surface | Included paths and artifacts | Audit treatment |
| --- | --- | --- |
| Backend application | `src/**/*.py`, `main.py`, `run.py` | Async/blocking-I/O scan, repeated-I/O and allocation review, storage query/index review, runtime critical paths |
| Backend operational scripts | `scripts/**/*.py` | Blocking work, batch bounds, memory behavior, migration/verification scaling |
| Web frontend | `frontend/src/**/*.{ts,tsx,css}`, `frontend/vite.config.ts`, frontend scripts and manifests | Render/network review, lazy boundaries, worker/service-worker behavior, bundle graph and asset budgets |
| Native clients | `frontend/src-tauri/**`, Android app source/configuration, iOS App source/project configuration | Startup, packaging, bridge calls, duplicated assets, release-build configuration |
| Deployment and serving | `deploy/**`, `k8s/**`, `nginx/**`, container files | Compression, caching, worker/process settings, resource limits, health and proxy behavior |
| Documentation tooling | Docs build configuration, docs scripts, and package manifests | Build-time plugins, asset processing, duplicated heavy dependencies |
| Tests and build tooling | `tests/**`, frontend tests, `Makefile`, `pyproject.toml`, root/frontend/docs package manifests | Slow-test evidence, redundant work, missing deterministic performance guards |
| Static and binary assets | Frontend public assets and docs images | Size, duplication, precache and compression treatment only |

Generated or third-party trees (`.venv`, `node_modules`, `dist`, native build outputs, coverage and
cache directories) are not source-audited. Generated `dist` is still measured as an artifact,
and lockfiles are inspected for dependency/bundle consequences rather than reviewed line by line.
Markdown product content is not treated as executable code; its build configuration and asset
weight are included.

Every inventory row records its scan or measurement command, findings, and disposition. An empty
row is not coverage evidence.

## Workstream Boundaries and Order

After phase 0, the program has four ordered workstreams. Each workstream receives its own TDD
tasks and focused verification in the implementation plan. A later workstream must re-read the
current branch before editing because other work is being committed concurrently.

### 1. Frontend Loading, Bundling, and PWA Caching

The frontend workstream addresses confirmed build-output problems first:

- Import `openSubagentPanelByAgentId` directly from its defining module so navigation code does
  not traverse the `SubagentBlocks.tsx` barrel and form a cross-chunk cycle.
- Preserve route and feature-level lazy loading. Adjust manual chunking or module boundaries so
  Mermaid, KaTeX, document preview engines, CodeMirror, Sandpack, and similar optional features
  are not eagerly fetched solely because of chunk configuration.
- Restrict PWA precaching to the offline application shell and genuinely critical stable assets.
  Lazy feature assets use the existing runtime `StaleWhileRevalidate` cache when requested.
- Preserve the current offline fallback, navigation strategy, cache expiry, service-worker
  activation, and old-cache cleanup behavior.

Deterministic targets:

- No cross-chunk circular-dependency warning in the production build.
- Initial eager JavaScript is at most 500 KiB gzip, measured from the entry HTML's module script
  and modulepreload graph.
- The Workbox precache manifest totals at most 4 MiB of uncompressed build artifacts.
- Existing route and feature behavior remains unchanged.

The artifact checker uses one measurement protocol on every run:

- Parse the completed `dist/index.html`, collect the module entry script plus all
  `rel="modulepreload"` JavaScript URLs, resolve and deduplicate their files, gzip each file with
  Node `zlib.gzipSync` at level 9, and sum the compressed byte lengths.
- Install a pure Workbox `manifestTransform` helper in the Vite PWA configuration. It receives the
  exact manifest entries that will be injected, deduplicates entry URLs, resolves each URL under
  `dist`, and sums the on-disk uncompressed byte lengths. The helper returns the unchanged filtered
  manifest plus count/byte statistics, and the build fails when the approved precache budget is
  exceeded.
- Unit tests exercise HTML URL extraction, deduplication, missing-file errors, gzip calculation,
  and precache-manifest counting without requiring a production build. The production build is
  the integration check.

Build wall time and peak RSS remain trend measurements, not CI pass/fail gates, because shared
machine load makes them noisy. They must be reported before and after, and a regression above
10% requires investigation and explanation.

### 2. Session-History Critical Path

This workstream incorporates the separately reviewed
`docs/superpowers/specs/2026-08-09-session-history-loading-design.md` rather than creating a
competing history contract.

Its performance responsibilities are:

- Load session detail and full events concurrently on the frontend while keeping mark-read and
  feedback outside the stable-render critical path.
- Batch the matching trace and chunk reads so full history uses a constant number of collection
  queries instead of one query sequence per run.
- Keep complete-history display, active-user ordering, SSE replay, filters, limits,
  recommendations, legacy embedded events, chunked events, and mixed sessions compatible.

Deterministic targets:

- The optimized full-history storage path uses one matching-trace query and at most one chunk
  query, independent of run count.
- Query-count tests cover all-legacy, all-chunked, and mixed histories.
- Existing user-visible history and event ordering are byte-for-byte or structurally equivalent
  after normalization.

If the concurrent history work lands before this program reaches the workstream, the program
audits and verifies the landed implementation instead of duplicating it.

### 3. Backend N+1 and Concurrency Hotspots

The first confirmed target is team persona hydration:

- Add a bounded bulk persona lookup by unique valid preset IDs.
- Hydrate all teams from the resulting map while preserving team/member order and fallback
  metadata.
- Keep invalid IDs and individual missing presets non-fatal, matching current behavior.
- Use one persona query for a team list, independent of the number of teams and members.

Additional candidates from the whole-repository audit enter this workstream only when they meet
all of these gates:

1. The path performs repeated external I/O, significant CPU work, or unbounded allocation on a
   reachable operation.
2. A focused test or reproducible measurement demonstrates the amplification.
3. The proposed change preserves ordering, authorization, cancellation, error isolation, and
   compatibility.
4. Concurrency has a configured or data-independent bound; the optimization must not create one
   task per untrusted item.

Comprehension rewrites and similar micro-optimizations are deferred unless profiling shows they
matter in a hot loop.

### 4. Regression Budgets and Audit Report Finalization

Add deterministic checks that protect the resources optimized above:

- A frontend artifact-budget checker reads the completed production output and reports eager
  entry/preload gzip size, precache entry count, and precache byte total.
- Backend tests assert collection-call counts for batched history and persona hydration.
- Existing behavior tests protect ordering, compatibility, error handling, and cancellation.
- Wall-clock and memory baselines are recorded for trend comparison but not enforced as flaky CI
  thresholds.

Finalize the audit ledger created in phase 0. It retains the explicit inventory table and groups
findings by backend API/agents/storage/tasks, frontend loading/rendering/network/PWA, native
clients, deployment/serving, operational scripts, docs tooling, assets, and test/build tooling.
Every finding has evidence, impact, disposition, and verification. Allowed dispositions are:

- optimized;
- already protected or already bounded;
- deferred because measured benefit is insufficient or risk exceeds benefit;
- false positive.

The report separates code completion from environment-dependent profiling that requires a
production-sized MongoDB dataset or deployed telemetry.

## Data Flow and Compatibility Invariants

Optimization must not change these contracts:

- Existing public API shapes remain additive or unchanged.
- Session history remains complete; no pagination, truncation, or "load older" interaction is
  introduced.
- Legacy embedded events, chunked events, and mixed migrations produce the same normalized event
  order.
- Recommendation compatibility events and active-run SSE reconstruction remain supported.
- Team and member order, missing-persona fallbacks, role/model permissions, and ownership checks
  remain intact.
- Background work remains bounded, nonblocking, drainable at shutdown, and failure-isolated.
- PWA navigation retains an offline fallback; optional assets may move from precache to runtime
  cache but remain available after first use.

No database migration, persistent frontend cache, dependency replacement, or feature removal is
part of this design.

## Error and Race Handling

- Batch reads return results in caller-defined order rather than database natural order.
- Missing or invalid IDs retain existing fallback behavior instead of failing the entire batch.
- A failed batch query follows the current endpoint/storage error contract; it is not silently
  converted into a successful empty result when the current code propagates failure.
- History cancellation and stale-request guards follow the separate history design.
- Service-worker upgrades keep `cleanupOutdatedCaches`; runtime cache misses fall back to the
  network and existing offline response behavior.
- Concurrent branch changes are treated as user work. Before every edit batch, inspect status and
  recent commits, preserve uncommitted files, and adapt rather than overwrite.

## Testing Strategy

All implementation follows red-green-refactor:

1. Add a focused failing regression or budget test and observe the intended failure.
2. Make the smallest production change that passes it.
3. Refactor only with the focused suite green.

Frontend coverage includes:

- direct-import/cycle source behavior;
- lazy feature boundaries and unchanged route behavior;
- PWA shell precache and runtime-cache routing;
- deterministic artifact-budget calculation;
- the complete session-history UX cases defined by the history spec.

Backend coverage includes:

- one bulk persona query with duplicate, missing, and invalid IDs;
- stable team/member ordering and metadata fallback;
- constant history query counts and complete event compatibility;
- bounded worker behavior for any additional concurrency optimization.

Verification order for each workstream is focused tests, then the relevant lint/type/build checks.
Final verification runs:

```bash
cd frontend && pnpm test
cd frontend && pnpm run lint
cd frontend && pnpm run build
uv run --no-sync pytest
make check-all
```

The final report repeats the production build and pytest measurements using the same commands as
the baseline and records any environmental limitations.

## Completion Criteria

The program is complete only when:

1. Every phase-0 inventory row contains current evidence and is represented in the audit report.
2. Every identified candidate has evidence and a disposition.
3. All confirmed high-priority findings in this design are optimized or proven already resolved
   by concurrent work.
4. Artifact and query-count regression guards pass.
5. Focused and full verification passes, or any unrelated/environmental failure is isolated with
   reproducible evidence.
6. Before/after bundle, precache, build, pytest, and relevant query-count results are reported.
