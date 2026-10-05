# Channel Distributed Safety Implementation Plan

> **For agentic workers:** Use executing-plans to implement and verify the tasks below sequentially.

**Goal:** All receiving channels recover across connection loss and server restart without losing accepted messages or sharing another tenant's conversation; publish a verified release.

**Architecture:** Retain the existing provider transports and task recovery machinery. Persist accepted inbound work before acknowledgement, fence processing with owner-checked Redis leases, and retain the original run identity for reply recovery. Stateless notification adapters use the same explicit instance routing rules.

**Tech Stack:** Python 3.12, asyncio, Redis, MongoDB, arq, pytest.

**Spec:** User request in this task; repository AGENTS.md governs verification, deployment, and release.

## Constraints

- No real messages to third-party contacts during tests.
- Redis failure must not silently authorize duplicate execution.
- No claim of exactly-once delivery where a provider lacks idempotent sends: an ambiguous provider response remains a documented boundary.
- Explicit instance selection must never fall back to another bot.
- Preserve recoverable task identity on reconnect; transport shutdown is not user cancellation.
- Red test before each behavioral fix, then targeted tests and full repository gates.

## 1. Ownership and lifecycle

Files: `src/infra/channel/chat.py`, `weixin/channel.py`, `feishu/channel.py`, `feishu/manager.py`, `outbound.py`.

- [x] Reproduce Weixin processing after lease loss in `tests/infra/test_weixin_restart_safety.py`; verify failure, cancel and join work on lost renewal, verify green.
- [x] Add generic/Feishu tests that block one dispatch and queue another, revoke the reader lease, and assert the old owner cannot continue.
- [x] Serialize overlapping manager reloads; test two blocked concurrent reloads leave one managed reader.
- [x] Test transient startup/rebalance errors recover without editing configuration; retain retry loops after exceptions.

## 2. Tenant isolation and exact routing

Files: `base.py`, `feishu/manager.py`, `feishu/handler_helpers.py`, `feishu/handler.py`, `weixin/handler.py`.

- [x] Add tests for equal chat IDs across users and channel instances, concurrent `/new`, and an absent explicitly selected bot.
- [x] Scope session identity by user and instance with collision-resistant encoding; use random IDs for `/new` and avoid overwriting its mapping during initialization.
- [x] Return unavailable for absent explicit instances and route connection-bound outbound messages to the current owner.

## 3. Durable accepted messages and reconnect

Files: shared channel persistence/dispatch helper, `chat.py`, `chat_handler.py`, `weixin/channel.py`, `weixin/handler.py`, `feishu/channel.py`, `feishu/handler.py`.

- [x] Add isolated MongoDB and Redis tests: persist acceptance, destroy the processing object, construct a new owner, recover the pending item; successful completion prevents duplicate processing.
- [x] Persist normalized input before provider acknowledgement/cursor advancement. Keep pending input until completed; renew processing claims atomically and replay on startup.
- [x] Persist run identity before submitting work; on replay reattach to its existing task and reuse task recovery instead of submitting a second user message.
- [x] Keep reply target/context and output checkpoint through reconnect; propagate send failures rather than marking work successful.
- [x] Test each provider's ACK/offset/sequence boundary, and task continuation across restart.

## 4. Verification and release

- [x] Run all channel tests, isolated Redis concurrency/restart tests, full lint, typecheck, frontend/backend tests and build.
- [x] Independent review; fix all important findings before merging.
- [x] Inspect latest releases and bump all seven required version locations consistently.
- [ ] Commit changes, PR to develop, await all CI gates, deploy staging and run a real conversation plus channel restart/failover smoke.
- [ ] PR develop to main, await green CI, deploy production and run `/root/disttest/run-all.sh`.
- [ ] Tag the verified main merge commit and complete App Release artifact checks. Desktop updater publication waits for required macOS/Windows real-device verification.

## Verification record

- Isolated MongoDB/Redis tests cover journaled acceptance, same-millisecond ordering, stale owners, lease loss, failed dispatch, and retry ordering.
- Two subprocess integration tests cover SIGKILL recovery and concurrent replica acceptance; these do not send messages to external providers.
- Frontend: 822 files / 4206 tests passed, lint and build passed.
- Local sandbox: 45/45 functional checks and 50/50 with stress passed.
- Repository-wide pre-commit encountered existing formatting drift in 184 unrelated files; those formatter-only edits were reverted. All hooks pass for this change set.
- External send success followed by a crash before checkpoint remains an ambiguous delivery boundary when provider idempotency is unavailable; documented in both channel guides.
- Final backend verification: 5624 passed, 18 skipped; all channel tests passed; full Ruff and Mypy passed (557 source files). Backend package and frontend production builds passed.
