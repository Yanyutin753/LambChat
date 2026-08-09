# Full-Repository Performance Optimization Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Audit every LambChat source surface, execute the approved independent performance plans, and publish verified before/after evidence with a disposition for every finding.

**Architecture:** Start with a repository-wide evidence ledger before changing production code. Execute frontend bundle/PWA, session-history, and team-persona plans as independent verified workstreams, add scoped plans for any new high-impact finding discovered by the inventory, then finalize deterministic budgets and the audit report.

**Tech Stack:** Python 3.12, Ruff, pytest, FastAPI, Motor/PyMongo, React 19, TypeScript, Vite, Vitest, Workbox, Capacitor, Tauri, Docker/Kubernetes/Nginx

---

## File structure

- Create `docs/performance-audit-2026-08-09.md`: authoritative coverage matrix, findings ledger, measurements, dispositions, and final evidence.
- Use `docs/superpowers/plans/2026-08-09-frontend-bundle-pwa-performance.md`: frontend artifact and PWA workstream.
- Use `docs/superpowers/plans/2026-08-09-session-history-loading.md`: already committed session-history workstream; do not duplicate it.
- Use `docs/superpowers/plans/2026-08-09-team-persona-batch-performance.md`: team/persona N+1 workstream.
- Modify `docs/performance-audit-2026-08-09.md` after every workstream and during final completion audit.

## Task 1: Establish the complete audit ledger before implementation

**Files:**
- Create: `docs/performance-audit-2026-08-09.md`
- Reference: `docs/superpowers/specs/2026-08-09-full-repository-performance-optimization-design.md`

- [ ] **Step 1: Capture branch and source inventory evidence**

Run:

```bash
git status --short --branch
git log -10 --oneline --decorate
rg --files \
  -g '!.venv/**' -g '!**/node_modules/**' -g '!**/dist/**' \
  -g '!**/build/**' -g '!**/coverage/**' \
  src scripts frontend/src frontend/scripts frontend/src-tauri \
  frontend/android/app frontend/ios/App deploy k8s nginx docs tests \
  Dockerfile Makefile pyproject.toml package.json pnpm-lock.yaml \
  frontend/package.json frontend/pnpm-lock.yaml frontend/vite.config.ts \
  frontend/vitest.config.ts \
  | sort
```

Expected: current branch/concurrent files are visible and every approved phase-0 surface has an inventory. Do not add or modify unrelated untracked files.

- [ ] **Step 2: Reproduce backend static and test baselines**

Run:

```bash
uv run ruff check src scripts main.py run.py \
  --select ASYNC,PERF --output-format concise
/usr/bin/time -v uv run --no-sync pytest -q --durations=40
```

Expected: the Ruff command may exit nonzero because findings are audit input; record every finding by subsystem. Pytest must pass, or exact failures and provenance must be recorded. Record wall time, peak RSS, and the slowest 40 tests.

- [ ] **Step 3: Reproduce frontend artifact and test baselines**

Run:

```bash
(cd frontend && /usr/bin/time -v pnpm run build)
(cd frontend && pnpm test)
(cd frontend && pnpm run lint)
```

Expected baseline: build completes, reports the known cross-chunk cycle and oversized chunks, and Workbox reports its precache entry/byte totals. Record eager entry/modulepreload gzip bytes, precache totals, build wall time/RSS, and all warnings. Tests and lint must pass or failures must be isolated.

- [ ] **Step 4: Inspect non-web source surfaces with explicit commands**

Run:

```bash
rg -n "invoke|Command::new|spawn|read_to_end|read_to_string|sleep|interval|timeout" \
  frontend/src-tauri -g '*.rs'
rg -n "minifyEnabled|shrinkResources|proguard|webContentsDebuggingEnabled|usesCleartextTraffic" \
  frontend/android/app
rg -n "WKWebView|URLSession|DispatchQueue|cache|timeout|background" frontend/ios/App
rg -n "gzip|brotli|cache|worker|timeout|keepalive|buffer|limit|resources|requests" \
  deploy k8s nginx -g '*.{yml,yaml,conf,sh,Dockerfile}'
rg -n "subprocess|asyncio|concurrent|ThreadPool|ProcessPool|read_bytes|read_text|glob|rglob" \
  scripts -g '*.py'
rg -n "manualChunks|minify|sourcemap|plugin|optimizeDeps|build" \
  docs -g '*.{ts,js,mjs,json}'
rg -n "worker|timeout|cache|compress|build|test|lint|dependency|scripts" \
  Dockerfile Makefile pyproject.toml package.json frontend/package.json \
  frontend/vite.config.ts frontend/vitest.config.ts
rg -n "vite|workbox|mermaid|katex|codemirror|sandpack|pdf|xlsx|tauri|capacitor" \
  pnpm-lock.yaml frontend/pnpm-lock.yaml docs/pnpm-lock.yaml
find frontend/public docs/images -type f -printf '%s %p\n' | sort -nr | head -n 100
```

Expected: each command yields either candidate evidence or a recorded “no material finding” disposition. Absence of a match alone is not enough; inspect the relevant entry/build/config files for each surface.

- [ ] **Step 5: Create the audit report with a nonempty row for every surface**

Create this structure with `apply_patch` and fill it with the captured evidence:

```markdown
# LambChat Performance Audit - 2026-08-09

## Measurement environment

| Item | Value |
| --- | --- |
| Commit | `<current HEAD>` |
| OS/runtime | `<uname, Python, Node, pnpm>` |
| Services/data | `<available services and dataset limits>` |

## Coverage matrix

| Surface | Paths inspected | Commands/evidence | Findings | Status |
| --- | --- | --- | --- | --- |
| Backend application | `src`, `main.py`, `run.py` | ... | ... | audited |
| Backend scripts | `scripts` | ... | ... | audited |
| Web frontend | `frontend/src`, Vite/scripts/manifests | ... | ... | audited |
| Native clients | Tauri, Android, iOS | ... | ... | audited |
| Deployment/serving | deploy, k8s, nginx | ... | ... | audited |
| Documentation tooling | docs config/scripts/manifests | ... | ... | audited |
| Tests/build tooling | tests, Makefile, manifests | ... | ... | audited |
| Static/binary assets | frontend public, docs images | ... | ... | audited |

## Baseline measurements

## Findings ledger

| ID | Surface | Evidence | Impact | Decision | Verification |
| --- | --- | --- | --- | --- | --- |

## Environment-dependent follow-up
```

Every finding uses exactly one decision: `optimized`, `already protected`, `deferred`, or `false positive`. Do not mark a coverage row audited without commands and inspected paths.

- [ ] **Step 6: Validate and commit the initial ledger**

Run:

```bash
rg -n "TBD|TODO|\.\.\." docs/performance-audit-2026-08-09.md
git diff --check -- docs/performance-audit-2026-08-09.md
```

Expected: no placeholders and no whitespace errors.

Commit:

```bash
git add docs/performance-audit-2026-08-09.md
git commit -m "docs: establish full repository performance audit"
```

## Task 2: Execute the frontend bundle and PWA plan

**Files:**
- Use: `docs/superpowers/plans/2026-08-09-frontend-bundle-pwa-performance.md`
- Modify: `docs/performance-audit-2026-08-09.md`

- [ ] **Step 1: Re-read current state and execute the frontend plan task-by-task**

Run `git status --short --branch` and `git log -5 --oneline` first. Then follow every RED/GREEN/commit step in the frontend plan. Do not touch session-history files owned by the concurrent plan.

- [ ] **Step 2: Add before/after artifact evidence to the ledger**

Record eager gzip bytes, Workbox entry/byte totals, build warnings, wall time, peak RSS, focused tests, and final build results. Mark each frontend finding with its disposition and commit the report update with the final frontend task.

## Task 3: Integrate rather than duplicate the session-history plan

**Files:**
- Use: `docs/superpowers/plans/2026-08-09-session-history-loading.md`
- Modify: `docs/performance-audit-2026-08-09.md`

- [ ] **Step 1: Determine whether concurrent history implementation already landed**

Run:

```bash
git log --oneline --all -- \
  src/infra/session/trace_event_chunks.py \
  src/infra/session/trace_storage.py \
  frontend/src/hooks/useAgent.ts
rg -n "read_trace_events_batch_compat|include_active_user_message|history_mode|stream_run_id" \
  src frontend/src tests
```

Expected: either the plan is unimplemented, partially implemented, or complete. Record the exact commit/file evidence.

- [ ] **Step 2: Execute only missing tasks from the committed history plan**

If incomplete, follow its TDD and commit steps exactly. If complete, run its focused and integrated verification instead of rewriting it. Preserve full-history and active-user/SSE invariants.

- [ ] **Step 3: Update the audit ledger**

Record trace and chunk query counts, compatibility cases, focused test output, and whether the work was implemented here or verified from concurrent commits.

## Task 4: Execute the team persona batching plan

**Files:**
- Use: `docs/superpowers/plans/2026-08-09-team-persona-batch-performance.md`
- Modify: `docs/performance-audit-2026-08-09.md`

- [ ] **Step 1: Re-read current state and execute the team plan task-by-task**

Inspect current status/history, then follow every RED/GREEN/commit step in the team plan. Preserve missing-persona fallback and team/member order.

- [ ] **Step 2: Add query-count evidence to the ledger**

Record the pre-change N+1 behavior, post-change single-query behavior, focused tests, and full backend verification.

## Task 5: Plan any additional material findings discovered in phase 0

**Files:**
- Modify: `docs/performance-audit-2026-08-09.md`
- Create only if required: `docs/superpowers/plans/2026-08-09-<scoped-hotspot>-performance.md`

- [ ] **Step 1: Apply the approved evidence gate to every remaining candidate**

A candidate requires implementation only when it has repeated external I/O, significant CPU or allocation on a reachable operation, reproducible evidence, preserved semantics, and bounded concurrency. Comprehension-only Ruff findings do not qualify without profiling evidence.

- [ ] **Step 2: Write and review a scoped addendum plan for every qualifying candidate**

Do not improvise production edits from the ledger. For each qualifying candidate, create an exact-file TDD plan using the same required header, run the plan-document review loop, then execute it before finalization.

- [ ] **Step 3: Assign a defensible disposition to every non-implemented candidate**

Record evidence for `already protected`, `deferred`, or `false positive`. “Not enough time” and “not inspected” are not valid dispositions.

## Task 6: Final integrated verification and completion audit

**Files:**
- Modify: `docs/performance-audit-2026-08-09.md`
- Verify: every file and plan referenced above

- [ ] **Step 1: Run focused budget and query-count suites**

Use the exact focused commands in the frontend, history, team, and any addendum plans. Expected: all pass and deterministic budgets meet the approved targets.

- [ ] **Step 2: Repeat before/after measurements with the baseline commands**

```bash
(cd frontend && /usr/bin/time -v pnpm run build)
/usr/bin/time -v uv run --no-sync pytest -q --durations=40
```

Record eager gzip bytes, precache totals, warnings, build/test wall time, peak RSS, and slowest tests. Explain any wall-time or RSS regression over 10%; these trend metrics are not flaky CI gates.

- [ ] **Step 3: Run repository-wide checks**

```bash
(cd frontend && pnpm test)
(cd frontend && pnpm run lint)
(cd frontend && pnpm run build)
make lint
make typecheck
uv run --no-sync pytest
make check-all
```

Expected: all commands exit 0. If concurrent or environment failures occur, prove provenance with focused suites and retain the full acceptance criterion.

- [ ] **Step 4: Complete the report and requirement-by-requirement audit**

Confirm every coverage row is nonempty, every finding has one disposition, all confirmed high-priority findings are optimized or proven resolved, budget/query-count guards pass, and environment-dependent work is clearly separate.

- [ ] **Step 5: Inspect final state and commit report-only completion updates**

```bash
git status --short --branch
git diff --check
git log -15 --oneline --decorate
```

Commit only the report changes belonging to this workstream:

```bash
git add docs/performance-audit-2026-08-09.md
git commit -m "docs: complete LambChat performance audit"
```
