# Memory Lifecycle Quality Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Work stays in the current local branch; preserve unrelated changes and do not create worktrees.
>
> **Latest user authorization:** After completing the memory work and validation, commit/push the scoped change, follow the repository server promotion process, and publish a new dev release. Earlier no-commit/no-deployment checkpoints below describe their historical authorization boundary.

**Goal:** Improve the complete existing memory lifecycle using repeatable real LLM evidence, preserving ownership and reducing repeated work.

**Architecture:** Keep existing backend, job leases, compaction agent and retrieval interfaces. Fix shared owners from failing behavior tests, then measure real sessions against a versioned corpus. Extend only the interfaces necessary to preserve facts and avoid redundant operations.

**Tech Stack:** Python, pytest, MongoDB, Redis, existing model client, FastAPI chat API.

**Spec:** `docs/superpowers/specs/2026-10-20-memory-lifecycle-quality.md`

## Global Constraints

- Preserve existing data and unrelated dirty files; no branch switching or stash. Commit/push/server promotion and a new dev release are authorized after completion and validation; exclude unrelated concurrent changes.
- All validation uses `python3 scripts/run_validation.py`; nonblocking lock, one worker, no retrying a busy slot.
- Real paid batches are sequential, frozen and non-replayable. Credentials and raw results stay outside the repository.
- Inspectable new conversations use `desktop_dev`; additional users/projects are owned evaluation fixtures.
- No absent cost or usage field is interpreted as zero; report unverified cases explicitly.

## Review Focus

- Near-identical vendor/person names and negations must not cause destructive fuzzy overwrites.
- Automatic extraction must not downgrade the protection of user-authored memories.
- Short follow-ups, old facts and multilingual content must retain enough retrieval context.
- Truncated/unavailable full content must not authorize destructive compaction.
- Concurrent updates, forgotten memories and source changes during a paid batch must stop stale effects.

## Task 1: Freeze acceptance and reproduce current defects

**Files:** Create `tests/fixtures/memory_lifecycle/v1.json`, `tests/infra/memory/native/test_quality_contract.py`; extend existing extraction and compaction tests where needed.

**Interfaces:** Consume existing retain, classification and ranking functions. Produce fixed scenarios and explicit failing regression cases, not new product behavior.

- [x] Prepare versioned multilingual, multi-user and multi-project cases with exact facts and unknown answers; freeze hashes immediately before the first real cohort.
- [x] Add initial tests for entity/number/negation preservation, relevant-result ordering, unchanged writes, source protection, preference scope and truncated compaction. These are written but have not run yet.
- [x] Run targeted tests through the shared lock and preserve actual RED output before production edits: 15 failed, 1 passed; private `initial-red.log` retained.
- [x] Locate local configuration and exercise isolated owned test identities without exposing credentials; original account data stays untouched.

## Task 2: Correct shared write and read behavior

**Files:** `src/infra/memory/client/native/backend.py`, `classification.py`, `search.py`, `src/infra/memory/tools.py`, `src/infra/memory/extraction.py`, `src/api/routes/memory.py`, associated tests.

**Interfaces:** Keep old calls compatible. Any internal provenance or preview argument must be forwarded by all callers and fake backends.

- [x] Prevent destructive matching based only on short-summary overlap; preserve explicit authorized updates. Deterministic regressions pass; real semantic consolidation remains in Task 4.
- [x] Preserve original source protection and separate Agent-created data from explicit manual authoring.
- [x] Skip unchanged content work without losing new authorized source references or scope changes; equality/no-op and concurrent source-union regressions pass.
- [x] Keep hybrid/local rerank order effective while enforcing hard ownership filters; preserve metadata priorities for overview/tied relevance.
- [x] Ensure API edits/imports update the same index/cache state as tool writes.
- [x] Run related tests serially; latest memory/middleware regression: 470 passed, 18 explicitly opt-in live cases skipped. This is not full project validation.

## Task 3: Reduce repeated maintenance without losing facts

**Files:** `src/infra/memory/extraction.py`, `compaction_agent.py`, `distributed.py`, `client/native/content.py`, `src/infra/chat/memory_context.py`, associated tests.

**Interfaces:** Preserve durable claim/lease and terminal-state contracts; reuse existing batch content hydration.

- [x] Measure unchanged extraction and compaction, then add content-version skip gates with durable success state. Real cohort 011 observed no new model call on the unchanged third pass; restart/partial-plan behavior has Mongo regressions.
- [x] Preserve new messages and corrective context using the existing recent-50-turn / 24,000-character input bound and unchanged-input fingerprint. No additional incremental truncation was introduced; preserving corrections takes priority over an unmeasured token saving.
- [x] Finish compaction protection and authorized source lineage. Incomplete-body refusal, final Mongo conditional writes, source transfer before redundant deletion, serialized same-actor tools and real compaction/forget cohort 019 are verified. Multi-row distributed atomicity is not claimed.
- [x] Avoid full-body/source-reference reads for metadata-only hints; preserve authorization checks. The 50k dataset's navigation snapshot is 750 characters; full content is loaded for actual recall or consolidation.
- [x] Exercise expiry, restart, delete-during-maintenance and repeated scheduling races. Mongo/Redis regressions cover recovery and fencing; real idle extraction027, reflection039 and compaction040 cover natural scheduling. Redis-to-Mongo atomicity is not claimed.

## Task 4: Real LLM lifecycle cohorts and final regression

**Files:** Add a small reusable real lifecycle runner after its assertion/journal tests are RED; use existing API/client patterns and the frozen fixture file. Save evidence outside the repository.

**Interfaces:** Sequential HTTP chat plus production extraction/recall/compaction/reflector; explicit identities, model/config fingerprint and per-call receipts. No hidden warmups or modified grading rules.

- [x] Baseline actual multi-turn chat, extraction and cross-session answers; keep every failed case.
- [x] Cover corrections, unknowns, mixed topics, all five locales, ownership and long-content preservation. Fresh041 passes all six strict-JSON questions; prior corpus failures remain unchanged.
- [x] Exercise real compaction/reflection and background idle scheduling separately from direct invocation; natural027/039/040 and explicit lifecycle cohorts are recorded separately.
- [x] Re-run affected behavior in new frozen cohorts after fixes; include unseen held-out variants without replaying started paid inputs.
- [x] Record per-stage latency, input/output/cache tokens and priced/unknown costs, plus avoidable call counts; receipts remain private and missing prices are never zero.
- [x] Complete backend memory regression and required lint/type checks only after coordinated edits are finished. Final077: 8808 passed /113 skipped; all620 backend source files type-check.
- [x] Review current diff, produce an inspectable report, and keep the goal active for any unmet requirement. Read-only review accepted the final scope and mechanical module split; server/release tasks below remain active.

## Task 5: Authorized server promotion and dev release

- [x] Finish coordinated backend/frontend checks and required release-version consistency. Local frontend full072 found two structural failures (5711 passed); both fixed and22 affected checks passed. ESLint/build, all scoped commit hooks and exact dev.3 workflow version preflight pass; actual submitted tree still requires full CI below.
- [ ] Commit/push only memory work and required build counters; preserve concurrent unrelated edits.
- [ ] PR to develop, pass CI, deploy staging and run a new real conversation.
- [ ] Promote develop to main, pass CI, deploy the server and complete deployment regressions.
- [ ] Create a fresh dev tag on the main merge commit; complete native builds, signing, artifact smoke and dev-latest.json readiness without changing the stable channel.
- [ ] Retain labeled acceptance results, remove temporary credentials/services and report actual production/release boundaries.


## Current checkpoint after cohorts 022–023

- Six-month capacity: 1k/10k/50k owned records plus 1k foreign records, actual Mongo/store/recall, deterministic 1536-d vectors; 6/6 selected hits per tier and no ownership leaks. This is not real embedding or a semantic accuracy score.
- 019: one new focused paid case passed, 17 runner checks passed, 27 cases unselected. Original 016–018 failures preserved. Actual compaction 3→1 retained both origins; deletion suppressed both old sources with zero new extraction calls.
- Scheduler fixes: real Mongo RED 4 fairness failures, 5 unavailable-session failures, 1 foreign-owner claim failure and 1 invalid-watermark failure; targeted GREEN 96 passed. Candidate filtering is before the cap; final leases and owner checks remain authoritative.
- Production read-only snapshot: Qwen/Qwen3-Embedding-0.6B, 1024 dimensions, SiliconFlow, Qdrant; 785 Mongo memories, 784 vectors, 24 owner groups, largest owner 108, 30 records at least 180 days old. Qdrant has 48 points without Mongo rows; no cleanup or production writes were performed.
- 022: actual production embedding provider, isolated Mongo/local in-memory Qdrant; 56 successful HTTP requests, 1444 known prompt tokens, 8 frozen queries across two engines all top-1 (16/16), zero scope leaks. Dataset has 49 rows; query vectors were precomputed for search timing. All 56 usage entries settled with unknown prices, not zero cost.
- 023: two full LLM cases passed: same-name project isolation (45/120 days) and English preference recalled in Chinese. All six saved memories have 1024-dimensional vectors; 17 observed LLM calls ended. Main LLM is the existing local configured provider, not a copy of production LLM settings. Explicit Phase 1 invocation does not prove natural periodic execution.
- 020 retains two strict JSON-format failures despite correct fact fields; Japanese case passed. 021 retains a pre-HTTP missing-owner setup failure. No started paid cohort was replayed, and old grading rules remain unchanged.
- Hot-enable jobs now register at boot with runtime enable predicates. Real-Mongo/local-Qdrant regressions reproduce empty/partial ANN candidate omissions and verify authoritative Mongo fallback. These are local fixes, not deployed production behavior.
- Legacy deletion can recover exact successful owned retain receipts from inline/chunked/serialized events when no other source exists; parsing and failure boundaries have real-Mongo tests. Production has 47 automatic memories without direct origins or extraction-job associations; none of five sampled rows yielded a matching historical receipt. Recovery of these rows is not claimed, and partially known legacy lineage remains open.
- Current related regression: 687 passed /29 opt-in cases skipped, 23.74s, all local Mongo gates enabled. Changed backend Ruff and targeted Mypy pass. No frontend changes after earlier 46 tests/build/lint. Production embedding credentials were used only through an external private four-field profile, then deleted; isolated copied settings were removed.
- Remaining work stays explicit above: natural periodic real-LLM execution, real embedding at 50k/concurrent load, durable failed cleanup, remaining frozen semantic cases, partial historical lineage and final coordinated whole-project validation. No worktree, branch switch, commit, push or deployment.

## Next bounded acceptance: real-clock idle extraction

- New immutable v11 uses a Quick source chat (no direct memory tools), durable studio facts, then a Chinese query from a fresh execution chat. It runs alone in an isolated database, with a 60-second idle window and 3-second periodic interval; production settings remain untouched.
- Passive APScheduler execution receipts prove real scheduled fire times. The source must remain memory-free before the idle boundary; the owned extraction job must finish with the original session watermark and exactly one extraction model call. Two subsequent real ticks must leave the job unchanged and add no model calls.
- Extraction receipts are identified by exact first-system-prompt equality; quoted user text cannot spoof the phase. No extraction control endpoint, synthetic timestamp aging, manual scheduler execution or patched clock is used by the paid acceptance.
- Observer tests first failed because the helper did not exist; after implementation, 21 helper/runner tests pass. The fake-clock observer unit test is only scaffolding verification, not natural runtime evidence.
- Paid cohort 027 passed: 18 passed /28 unselected, 140.19s. The actual periodic scheduler began the one extraction model call 2.054s after the 60s idle threshold; pre-idle memory count was zero. Two subsequent real ticks left the completed job unchanged and added no calls. The fresh Chinese query returned Cedar Loom / Tuesday /27 exactly; independent DB audit found one 1024-dimensional memory. Four observed LLM calls all ended, prices unknown. Copied sensitive settings were cleaned. This proves the shortened real-clock extraction path, not production default timing, natural compaction/reflection or high-load performance.
- Fresh cohort 028 is terminal: 1 failed /19 passed /26 unselected, 405.70s. Unadopted proposal correctly remains unknown; January/February policy thresholds are 99/129. Quoted-instruction answer correctly gives Alder/42/null but adds prose after JSON, failing the original strict grader. Preserve that failure; offline JSON-prefix inspection is not a pass. Existing generic format policy is present in the actual system message and was insufficient. No new claim that format compliance is fixed.
- 028 also exposes overlapping foreground/background supplier and security memories; exact-body protection intentionally does not semantically overwrite them. Avoiding this redundant capture without losing new facts is a remaining efficiency task. The original source/case files remain unchanged; the private production embedding profile was deleted after completion.

## Index backfill completion protection

- Unit and real isolated Redis RED: six failures prove skipped, expired and replaced backfills could certify completion. Existing lock release was already owner-checked; the completion marker was not.
- Skip results now leave completion unset. A short Redis Lua compare-and-set publishes completion only under the current lease token. No queue, new dependency or change to existing indexed data was added.
- GREEN: 23 related tests passed, including actual Redis lease expiry, takeover, skipped/successful backfill and transport failure. Vector-store Mypy and changed-file Ruff pass. Latest full related regression: 699 passed /30 opt-in skipped, 26.53s, with all Mongo gates and real Redis enabled. No paid/test process remains active; copied credentials were removed. Whole-project/client gates and the remaining lifecycle work are not thereby complete.

## Resource cleanup recovery

RED now proves seven failures: unavailable/unsupported body stores silently certify long writes or deletes; body cleanup loses its reference after metadata deletion; cleanup preparation cannot fail safely; false vector-delete results are forgotten.

Keep the existing APIs and body keys. Before deletion, persist owner-scoped resource references in `memory_resource_cleanup`; do not copy facts, embeddings or credentials. Shared body cleanup also records an intent before attempting physical deletion, covering updates/imports that already call it. A bounded periodic job retries persisted intents after restart, independently of automatic extraction/compaction preferences. Before touching resources, check current Mongo ownership/references; preserve in-use bodies, and reconcile a recreated memory's current vector instead of deleting it. Use versioned acknowledgements so a stale cleanup cannot erase a newly queued intent. Missing/unsupported body stores must raise the existing unavailable error. Tests cover failed stores, recovery, tenant isolation, active references, resurrection, unknown writes and scheduling.

This does not assert a Mongo-to-external-store transaction. A crash before an update/import reaches shared cleanup, or an uncommitted staged-body crash, remains a separate recovery gap; deletion prepares its references before removing metadata. Do not widen success claims beyond these boundaries.

- Initial RED7 confirms unavailable/unsupported body stores, lost body cleanup references and lost vector failures. Shared helpers now fail closed; Mongo stores only owner/resource references. Failed/cancelled async store initialization can retry after recovery. Owner-filtered Qdrant delete was independently RED before fixing.
- Actual Mongo/Qdrant tests cover restart, unknown delete commit, preserved live bodies, separate tenant namespaces, recreated memory repair, versioned acknowledgements, bounded100-job retries and backoff. Native/API replacement cleanup failures must still invalidate cache and update the current vector. Final deletion guard is checked again after intent preparation; review feedback reproduced the missing check before the fix.
- Independent read-only review found two additional queue races: a prepared vector intent could be acknowledged before metadata deletion; overlapping workers could acknowledge while a stale deletion was still in flight. Both have failing Mongo regressions. Prepared intents now retain their deletion revision, and foreground/background share a five-minute renewable atomic per-resource claim. Acknowledgement checks version, token and expiry. Late uncertain results restore absent repair work without replacing a newer intent. Cleanup repair also refuses a current cross-owner ID collision.
- The final review also reproduced a foreground post-delete read failure/cancellation that could lose repair work after takeover. Shared processing now persists pending repair before propagating either failure. All22 focused cleanup Mongo tests pass; the related regression is735 passed /30 opt-in skipped (28.10s), and shared-store callers add83 passed. Independent final review accepted this documented scope by code inspection; it did not rerun these tests. No new paid calls or production writes occurred. Known remaining whole-goal work includes legacy startup pruning's direct metadata deletion, update/import pre-cleanup interruption, staged-body crash recovery and general index-write repair; global cross-owner point-ID design is not claimed solved.

## Atomic replacement cleanup references

1. RED six real-Mongo cases: Native/API update/import interruption before cleanup registration, and overlapping replacements retaining both obsolete body keys.
2. A shared Mongo expression appends the actual current body reference to `_content_cleanup` atomically with pointer replacement. Preserve pending references through import replacement; literal-escape all user fields.
3. Existing cleanup pass transfers bounded pending references to durable tasks before removing exact array entries; explicit deletion prepares pending references too. Preserve owner checks, CAS guards and current-body protection.
4. Verify interruption, unknown commit, concurrent append/transfer/delete, tenant isolation and literal content; then adapt mocks and run coordinated related regression, lint/types and independent review. Uncommitted staged-body recovery remains separate.

- Six real-Mongo interruption/concurrent-replacement cases: RED6, then GREEN6. Index discovery RED examined unrelated rows; partial index now bounds examined documents in the50k fixture. Cross-row transfer-cap RED reproduced122 transferred resources; fixed global100 cap.
- Unknown commit/cancellation matrix:12 cases. Native/API update cache invalidation failures reproduced before fixing; import already had finally-based invalidation. Cleanup focused47 passed before one additional successful-transfer/concurrent-append test. Related regression34:809 passed /30 opt-in skipped,32.31s, all Mongo/Redis/bulk gates enabled. Regression33 had721 passed /46 skipped because a separate Mongo fixture gate was missing; no skipped case was reported as passing, and regression34 enables that gate.
- Independent read-only review accepted the atomic reference change and later cache-exception adjustment. No tests were run by the reviewer, no new paid cohorts were started, and no production writes occurred. Remaining staged-body/startup-prune/general-vector-repair scope stays open.
- Final cleanup focused48 passed (7.32s), including an additional successful transfer with concurrent append; product source unchanged after regression34. Final9changed Python files Ruff lint/format check,3source-file Mypy and git diff --check pass. Earlier frontend checks do not establish current whole-project/client verification.

## Durable vector write repair

1. RED six real Mongo/Qdrant cases: five mutation entries lose failed index writes, and a full stale ANN result hides a more relevant newly committed memory.
2. Atomically set `_vector_pending` with mutation revision in each entry. Reuse vector cleanup claims for synchronization; preserve existing preparing deletion intents, leases, retry backoff and owner guards. Clear marker only after current-row write and post-check; keep uncertainty retryable.
3. Discover bounded pending work through a partial index. Merge visible pending Mongo-vector candidates into ANN ranking, excluding their stale ANN scores. No new model calls or embedding generation.
4. Verify actual transport failure/restart, unknown commit, cancellation, deletion interleaves, changed revisions, filtering and bounded scans; then coordinated related gates and independent read-only review. Historical unmarked gaps and general cross-store atomicity remain explicit limitations.

- Initial6 real-Mongo/Qdrant RED failures fixed; expanded False/OSError/CancelledError + five-entry matrix, unknown metadata commit, prepared deletion, backoff, late update/delete, owner/project/type/context cases. Native unknown insert skipped invalidation, and pre/post-write guard cancellation leaked resources: RED3, then guarded durable rollback/cache compensation.
- Simulated stale Atlas candidate RED fixed by exact Mongo fallback when visible pending vectors exist. This is not a live Atlas-service test. No LLM retry or re-embedding is introduced.
- Independent review RED2 reproduced discovery starvation behind100queued blockers and conflicting duplicate snapshots; lookup excludes queued identities before limit100, and pending snapshot wins ID merge. Follow-up RED1 reproduced a downgraded replacement omitted from pending topN; ordinary candidates now recheck pending status before merge. Final read-only review accepted the documented scope; reviewer ran no validation.
- New50k-noise explain case checks discovery<=100docs and owned pending search<=2docs/3keys. Targeted final vector+search59 passed; all related regression35:843passed30opt-in skipped39.97s. Final6file Ruff lint/format pass; Mypy4sources pass after a dict annotation. No new paid/production writes. Staged hard-crash recovery, legacy startup pruning, unmarked historical/backend-switch writes, global point IDs, real50k embedding/concurrency and whole-project/client gates remain open.

## Legacy startup cleanup recovery

1. RED6 actual Mongo/local Qdrant cases: orphan body/vector resources; journal failure removes mainrow; concurrent manual replacement unprotected; unbounded startup; unresolved identity destroyed;50k-noise discovery scans unrelated rows.
2. Replace direct delete_many with partial-indexed, owner/ID/source/revision conditional deletion, max100 per invocation, forget_sources=False. Reuse existing resource preparation and retry claims; preserve unresolved identities.
3. Registered periodic resource handler resumes bounded legacy pruning when memory is enabled, even when automatic extraction is disabled. Global memory off does not initiate retirement, but existing durable resource tasks continue. Failures retain records or durable resource refs; per-record failures cannot stop unrelated selected records.
4. Verify existing lifecycle callers, failed stores, unknown delete outcomes, direct registered-handler resume, full related gates and independent read-only review. No production cleanup/deployment is performed.

- Initial RED6 -> GREEN6. Reused logicalID/missingrevision inventory race RED1 -> add actual Mongo _id to final query. Slotted MongoDBStore instance patch caused2 fixture failures in directed117cases; corrected to class patch, not a product change. Expanded legacy11 passed, including separate-owner failures and unknown before/after delete recovery.
- Global-off policy RED1 -> periodic handler does not initiate retirement when ENABLE_MEMORY is false, but existing resource tasks continue. Test verifies37remaining until re-enabled, with extraction still off; new global-off case preserves legacy row/body/vector while completing explicit queued work. Legacy total12cases.
- Shared unknown-delete cache path RED4 (OSError/CancelledError x before/aftercommit) -> invalidate owner cache/rethrow around metadata deletion. Final focused80passed10.29s. Initial fullreg36:854passed before global-off/cache additions; final fullreg37:857passed30opt-in skipped47.03s, all local Mongo/Redis/50krestore gates enabled.
- Final4file Ruff lint/format,2source Mypy and diff checks pass. Independent reviewer accepted original deletion/query changes, then the global-off policy and unknown-cache adjustment, without test execution. No new paid cohorts, model calls, production writes or frontend changes. Whole goal remains active.
