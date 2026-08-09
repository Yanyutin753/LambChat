# LambChat Performance Audit - 2026-08-09

This report is the evidence ledger for the repository-wide performance review. It is updated after each implementation workstream. A decision of `optimized` means the finding has been selected for optimization; the Verification column distinguishes scheduled work from completed proof.

## Measurement environment

| Item | Value |
| --- | --- |
| Commit | `20c1b68a` on `perf/full-repository-performance` |
| OS/runtime | Linux WSL2 6.6.87.2, Python 3.13.5, Node 20.20.0, pnpm 10.32.1 |
| Dependency state | `uv sync` and `pnpm install --frozen-lockfile` completed in the isolated worktree |
| Services/data | Test fakes and repository fixtures only; no production MongoDB, Redis, object store, device, browser trace, or production-sized dataset was available |

## Coverage matrix

| Surface | Paths inspected | Commands/evidence | Findings | Status |
| --- | --- | --- | --- | --- |
| Backend application | `src`, `main.py`, `run.py` | Ruff `ASYNC`/`PERF` scan; complete pytest suite with slow-test timings; targeted reads of session, team, Feishu, MCP, upload, storage, and background-task paths | B-001 through B-007 | audited |
| Backend scripts | `scripts` | Async, subprocess, concurrency, filesystem, and glob scan; inspected E2B configuration publication path | S-001 | audited |
| Web frontend | `frontend/src`, `frontend/scripts`, `frontend/vite.config.ts`, manifests and lockfile | Timed production build; full Vitest and ESLint; exact level-9 gzip calculation from emitted `index.html`; Workbox output and chunk warning inspection | F-001 through F-004 | audited |
| Native clients | `frontend/src-tauri`, `frontend/android/app`, `frontend/ios/App`, Capacitor and Tauri configs | Rust process/filesystem scan; Android release shrink settings; iOS networking/background scan; native entry/config inspection | N-001, N-002 | audited |
| Deployment/serving | `Dockerfile`, `deploy`, `k8s`, `nginx` | Resource, timeout, buffering, compression, cache, worker, and build scans; full Docker, compose, Kubernetes, and Nginx config inspection | D-001, D-002 | audited |
| Documentation tooling | `docs/.vitepress`, root documentation manifest and lockfile, `docs/images` | Vite/VitePress plugin and build scan; config and dependency inspection; asset-size inventory | DOC-001 | audited |
| Tests/build tooling | `tests`, `Makefile`, `pyproject.toml`, root and frontend manifests, Vite and Vitest configs, lockfiles | Full backend/frontend tests; frontend lint/build; build/test script and dependency inspection | T-001 | audited |
| Static/binary assets | `frontend/public`, `docs/images` | Sorted byte-size inventory and aggregate totals | A-001 | audited |

## Baseline measurements

### Backend

| Metric | Baseline |
| --- | --- |
| Full suite | 2,390 passed, 1 skipped, 41 warnings |
| Pytest-reported duration | 39.54 seconds |
| Timed wall clock | 46.98 seconds |
| Peak RSS | 834,536 KiB |
| Slowest test | task-manager recovery service, 4.95 seconds |
| Other material slow tests | S3 streaming retry cases, 2.20 to 2.60 seconds; cancellation 2.01 seconds; Feishu off-loop import 1.98 seconds |
| Ruff performance/async candidates | 49 total: 17 `ASYNC109`, 1 `ASYNC110`, 3 `ASYNC240`, 3 `PERF102`, 24 `PERF401`, 1 `PERF403` |

The complete backend suite is a correctness and trend baseline, not a production latency benchmark. Repository fixtures do not reproduce production database cardinality, network latency, or concurrent traffic.

### Frontend

| Metric | Baseline |
| --- | --- |
| Full suite | 278 test files and 1,043 tests passed |
| ESLint | Exit 0 with 4 existing unused-variable warnings in `longTextConversion.ts` |
| Production build | 7,579 modules; Vite build 39.41 seconds; timed wall clock 54.92 seconds |
| Build peak RSS | 3,138,080 KiB |
| Eager JavaScript | 2,241,945 raw bytes; 642,459 gzip bytes at level 9 |
| Eager entry | 1,016,759 raw bytes; 303,533 gzip bytes |
| Eager Mermaid vendor chunk | 682,779 raw bytes; 171,536 gzip bytes |
| Workbox precache | 309 entries; 18,153.33 KiB |
| Service worker | 28.14 KiB raw; 9.24 KiB gzip |

The eager JavaScript budget is 500 KiB gzip and the precache budget is 4 MiB raw. Both budgets fail at baseline.

### Other surfaces

| Metric | Baseline |
| --- | --- |
| Frontend public assets | 37 files; 2,312,293 bytes |
| Documentation images | 35 files; 1,078,609 bytes |
| Largest public asset | `icons/og-image.png`, 708,744 bytes |
| Android release shrink | `minifyEnabled false`; no `shrinkResources` setting |
| Deployment protection | Nginx gzip level 4, immutable `/assets` and `/icons` caching, upstream keepalive 32, and SSE buffering disabled |
| Container resources | Compose application memory limit 2 GiB; Kubernetes requests 200m CPU/512 MiB and limits 2 CPU/4 GiB |

## Findings ledger

| ID | Surface | Evidence | Impact | Decision | Verification |
| --- | --- | --- | --- | --- | --- |
| F-001 | Web chunk graph | Production build reports a cross-chunk circular dependency around `openSubagentPanelByAgentId` and `SubagentBlocks.tsx` | Can produce fragile initialization order and prevents a clean build signal | optimized | Scheduled by the frontend bundle/PWA plan; baseline warning reproduced |
| F-002 | Web initial load | Mermaid is forced into an eager modulepreload; eager JavaScript is 642,459 gzip bytes, including 171,536 bytes for Mermaid | Initial download, parse, and evaluation exceed the 500 KiB budget | optimized | Scheduled by the frontend bundle/PWA plan; exact emitted-file calculation captured |
| F-003 | PWA install/update | Workbox precaches 309 entries totaling 18,153.33 KiB | Large first install and service-worker update transfer exceeds the 4 MiB budget | optimized | Scheduled by the frontend bundle/PWA plan; Workbox baseline captured |
| F-004 | Frontend quality signal | ESLint emits four existing unused-variable warnings while returning success | No measured runtime cost; warning noise can hide future findings | deferred | Not performance-significant and outside this optimization scope |
| B-001 | Session run summaries | `list_run_summaries` calls `get_first_trace_event` inside the trace loop when preview data is absent | Up to one extra trace/chunk read per returned run | optimized | Scheduled by the existing session-history plan; query-count proof required |
| B-002 | Team persona hydration | `_hydrate_member_roles` and active-member validation call persona `get_by_id` inside member loops | Database query count grows with member count | optimized | Scheduled by the team persona batching plan; single-query proof required |
| B-003 | Local-reference upload fallback | `_resolve_local_references` awaits upload work sequentially for each bounded local reference | Independent backend/storage I/O can add linearly to reveal-file latency | optimized | Qualifies for a scoped phase-5 TDD addendum; upload limit provides a concurrency bound |
| B-004 | Ruff comprehension suggestions | 31 `PERF` findings are local loop/comprehension rewrites without profiling evidence | Likely negligible compared with I/O and may reduce readability for async cursors | deferred | Full static scan recorded; evidence gate rejects speculative mechanical rewrites |
| B-005 | Ruff timeout-name rule | 17 `ASYNC109` findings are API parameters named `timeout` | Naming does not itself create a performance defect | false positive | Call sites use explicit timeout machinery; no blocking operation is implied by the parameter name |
| B-006 | Feishu WebSocket wait loop | Ruff reports `ASYNC110` for one-second sleep polling while the connection is active | Shutdown can wait up to one second, but the sleep yields and does not consume CPU | deferred | Existing behavior is bounded and non-busy; no user-visible latency reproduction |
| B-007 | Async filesystem helpers | Three `ASYNC240` findings cover small rollout metadata/path checks and path manipulation around already offloaded file I/O | Possible event-loop stalls depend on filesystem latency and file size | deferred | No production trace or reproducible latency evidence; reveal-file content I/O already uses `run_blocking_io` |
| S-001 | Maintenance scripts | Script scan found async entry points and synchronous manifest/env reads in deployment utilities | Operator-only paths can block their own event loop but do not affect application request latency | deferred | Files are bounded configuration artifacts; no repeated service-path execution |
| N-001 | Android release package | Release build disables code minification and does not enable resource shrinking | Potentially larger installation package and slower cold start | deferred | Requires signed release artifact and device/profile baseline unavailable in this environment |
| N-002 | Tauri upgrade cleanup | Desktop startup reads a small version marker and clears webview data only after version changes | One-time upgrade work, not steady-state startup work | already protected | Guarded by version comparison; no process spawning or repeated runtime scan found |
| D-001 | Nginx serving | Gzip, immutable hashed-asset caching, connection reuse, and disabled SSE buffering are configured | Avoids repeated transfer, connection, and streaming-buffer overhead | already protected | Direct config inspection in `nginx/nginx.conf` |
| D-002 | Container deployment | Multi-stage image, frozen dependency installs, uv cache mount, health probes, and explicit resource bounds are present | Build reuse and runtime resource containment are configured | already protected | Direct inspection of Docker, Compose, and Kubernetes manifests |
| DOC-001 | Documentation build | VitePress excludes plans, superpowers artifacts, and images from source-page processing; local search is the only material build plugin | No independent hot path or duplicate heavy plugin found | already protected | Config and lockfile inspection; documentation images are not part of frontend app precache |
| T-001 | Tests/build tooling | Full suites pass and build scripts use deterministic uv/pnpm entry points | Provides reproducible regression gates; wall/RSS remain trend metrics | already protected | Baseline commands completed successfully |
| A-001 | Static assets | Public assets total 2.31 MiB; the 708,744-byte social image is the largest | Assets are costly only when fetched or precached; current PWA policy precaches too broadly | optimized | Addressed through F-003 runtime caching; source image quality is preserved |

## Environment-dependent follow-up

- Re-run database query-count and latency measurements against representative production cardinality after the deterministic fake-backed query-count tests pass.
- Profile Android signed release size and cold start on supported devices before enabling R8/resource shrinking; retain required Capacitor and plugin rules.
- Compare browser cold-load and service-worker update traces over a throttled connection after artifact budgets pass.
- Treat wall time and RSS as trend evidence. Repeated measurements are required before attributing a change larger than 10 percent to code rather than host variance.
