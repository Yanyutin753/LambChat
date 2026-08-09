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

### Frontend after bundle/PWA optimization

| Metric | Result | Change from baseline |
| --- | --- | --- |
| Full suite | 282 test files and 1,060 tests passed | 17 deterministic regression tests added |
| PWA/cache compatibility | 6 files and 18 tests passed | Navigation fallback and runtime-cache exclusions preserved |
| Production build | 7,580 modules; timed wall clock 43.61 seconds | 20.6 percent lower wall time; trend only |
| Build peak RSS | 3,151,016 KiB | 0.4 percent higher; within host variance |
| Eager JavaScript | 471,443 gzip bytes | 171,016 bytes and 26.6 percent lower; passes 512,000-byte gate |
| Workbox precache | 62 entries; 4,087,514 raw bytes | 247 fewer entries and about 78 percent fewer bytes; passes 4,194,304-byte gate |
| Build warnings | No cross-chunk cycle; generic large-lazy-chunk warning remains | Cycle removed; optional heavy features remain runtime-loaded |
| Lint | Exit 0 with the same 4 existing warnings | No new lint warning |

Mermaid, CodeMirror, Sandpack, KaTeX font files, and the social preview image are not promoted into the eager/precache paths. Fonts and other lazy static assets remain covered by the service worker's bounded `StaleWhileRevalidate` runtime cache. The offline document, web manifest, favicon, declared application icons, entry graph, and first-level route shells remain precached.

### Session-history loading after optimization

| Metric/invariant | Result |
| --- | --- |
| Database reads for a multi-run snapshot | One trace query plus one chunk query, independent of the number of returned traces |
| Legacy/chunk compatibility | Mixed legacy prefixes and chunk events are merged once in sequence order |
| Active run race | Running trace contributes only its user message and returns `stream_run_id`; terminal trace returns the complete snapshot |
| Frontend critical path | Session metadata and events load concurrently; mark-read and feedback no longer gate the stable message reveal |
| Stale work isolation | History HTTP requests use a per-load abort controller; SSE uses a generation plus local abort controller |
| User-visible ordering | Same-run user is installed atomically before the streaming assistant target, with duplicate suppression |
| Navigation | URL changes before awaiting history loading |
| Focused backend verification | 45 passed in 0.57 seconds |
| Focused frontend verification | 6 files and 41 tests passed |
| Integrated frontend verification | 283 files and 1,069 tests passed; production budget build passed |

The post-integration frontend artifact budgets remain green at 471,475 eager gzip bytes and 62 precache entries totaling 4,088,516 raw bytes.

### Team persona hydration after optimization

| Metric/invariant | Result |
| --- | --- |
| Persona reads for a team list | One MongoDB `find` with `$in`, independent of team/member count |
| Duplicate IDs | Deduplicated in first-seen order before the storage call |
| Direct storage bound | At most 4,000 valid, unique ObjectIds; empty/all-invalid input performs zero queries |
| Compatibility fallback | Missing/invalid presets preserve original member metadata; bulk lookup failure returns the original teams |
| Runtime validation | Active-member validation retains its per-member `get_by_id` behavior and still filters missing presets |
| Focused verification | 4 storage query-bound tests and 4 team hydration tests passed |
| Team/persona verification | 58 tests passed |
| Integrated backend verification | Ruff and Mypy passed; 2,407 tests passed and 1 skipped in 40.68 seconds |

The integrated backend run used 47.61 seconds wall time and 838,488 KiB peak RSS. Compared with baseline, those host-level measurements are effectively unchanged and are treated as trend data; the deterministic improvement is the constant database query count.

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
| F-001 | Web chunk graph | Production build reported a cross-chunk circular dependency around `openSubagentPanelByAgentId` and `SubagentBlocks.tsx` | Could produce fragile initialization order and prevented a clean build signal | optimized | Direct defining-module import plus deferred heavy panel content; final build has no circular warning |
| F-002 | Web initial load | Mermaid was forced into an eager modulepreload; eager JavaScript was 642,459 gzip bytes, including 171,536 bytes for Mermaid | Initial download, parse, and evaluation exceeded the 500 KiB budget | optimized | Mermaid, CodeMirror, and Sandpack manual promotion removed; final eager graph is 471,443 gzip bytes |
| F-003 | PWA install/update | Workbox precached 309 entries totaling 18,153.33 KiB | Large first install and service-worker update transfer exceeded the 4 MiB budget | optimized | Route-shell manifest transform produces 62 entries and 4,087,514 bytes; deterministic build gate passes |
| F-004 | Frontend quality signal | ESLint emits four existing unused-variable warnings while returning success | No measured runtime cost; warning noise can hide future findings | deferred | Not performance-significant and outside this optimization scope |
| B-001 | Session history reads | Baseline history assembly performed per-trace compatibility reads; summary fallback also called `get_first_trace_event` inside its loop | Trace/chunk query count could grow with returned runs | optimized | Batched compatibility read uses one trace query and one chunk query; race-safe snapshot and 45 focused tests pass |
| B-002 | Team persona hydration | Display hydration previously awaited persona `get_by_id` inside nested team/member loops | Database query count and latency grew with returned member count | optimized | One bounded `get_by_ids` call hydrates the complete list; ordering, deduplication, fallback, and 4,000-ID bound tests pass; runtime validation remains intentionally separate |
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
| A-001 | Static assets | Public assets total 2.31 MiB; the 708,744-byte social image is the largest | Assets are costly only when fetched or precached; the baseline PWA policy precached too broadly | optimized | F-003 leaves non-shell assets in bounded runtime caching while preserving source quality |

## Environment-dependent follow-up

- Re-run database query-count and latency measurements against representative production cardinality after the deterministic fake-backed query-count tests pass.
- Profile Android signed release size and cold start on supported devices before enabling R8/resource shrinking; retain required Capacitor and plugin rules.
- Compare browser cold-load and service-worker update traces over a throttled connection after artifact budgets pass.
- Treat wall time and RSS as trend evidence. Repeated measurements are required before attributing a change larger than 10 percent to code rather than host variance.
