# Role USD Quota Implementation Plan

> **For agentic workers:** Implement this plan in the current checkout; frontend work uses a separate agent after agreeing the API contract. All validation is serialized by the parent.

**Goal:** 可配置并统一执行每用户按角色的 USD 5 小时/周额度。

**Architecture:** RoleLimits 保存策略；模型协议共享准入层；Mongo 单用户原子账本；角色管理与用量浮层复用现有 UI。

**Tech Stack:** Python, PyMongo async, LangChain, React, TypeScript.

**Spec:** ../specs/2026-10-18-role-usd-quota-design.md

## Global Constraints

- Preserve concurrent dirty changes; no worktree, branch switch, commit or deployment.
- USD only; Independent first-use anchored five-hour and seven-day windows; null unconfigured, zero blocks.
- All tests/lint/build/format through scripts/run_validation.py; one worker; exit 75 is blocked.

## Review Focus

- Atomic reserve across both windows; retries and duplicate settlement never double debit.
- Missing usage, price and owner context cannot silently turn known user calls into free consumption.
- Detached recommendations and memory retain an explicit payer without inherited graph callbacks.
- Cancellation, late callbacks and window rollover preserve known charges and unknown holds.
- Existing role initialization/editing cannot erase budgets; UI remains usable without token stats.

## Tasks

- [x] RED tests for budget validation, multi-role policy, windows, UI/API contracts.
- [x] Role schema, durable ledger and own-account API.
- [x] Shared four-provider barrier with explicit detached payer propagation and recovery metadata.
- [x] Role editor/details, usage popup and five locale strings.
- [x] Real Mongo concurrent reservation and idempotent settlement tests; adapter/recovery/role tests.
- [x] Serial backend lint/type checks, frontend tests/lint/build, rendered UI checks; report proof boundaries.

## Verification Evidence

- Backend: 8111 passed, 81 skipped, 5 subtests passed; Ruff and Mypy passed.
- Frontend: full run exposed two affected failures; both fixed, then 9 related files / 50 tests passed. Lint and production build passed.
- Rendered local fixture: role budgets and usage popup checked in light/dark themes at desktop and 375px widths; input/popup hit tests passed with no horizontal overflow.
- No deployment, native-client build or paid live-provider acceptance was performed. Unsupported paid APIs without reliable USD pricing reject finite-quota users before invocation.

## Weekly Window Correction

- Start the weekly window on the first model call and retain its anchor for seven days, independently of the five-hour window. Viewing an unused or expired balance does not start a window.
- Cover crossing Monday, expiry, inactivity, restart, concurrent first use, user isolation and late settlement. Update all five locales and unused-window UI coverage.
- Prior verification above predates this correction; the initial RED attempt was blocked by the shared validation lock (exit 75).
- After all edits, verification acquired the shared slot: 90 backend tests (including real Mongo), 36 related frontend tests, Ruff, Mypy, frontend lint/build and diff whitespace checks passed.

## Comprehensive Audit and Reset Cards

- [x] Reproduce rollover CAS, stale role-cache, missing payer, synchronous bypass, unbounded provider overrides and repeated cancellation failures.
- [x] Add admin scoped reset and account-local generic reset cards with atomic idempotency/audit.
- [x] Distinguish exhausted/reserved/unknown UI, propagate error args and add five-language card controls.
- [x] Final serialized quota regressions, performance sample and rendered exhausted/reset-card/admin QA; unrelated full-suite failures recorded below.

The ack-loss/performance follow-up RED was blocked by an external validation owner (exit 75); do not claim those pre-fix assertions were observed.

### Final Audit Evidence (2026-10-18)

- Backend full regression: 8176 passed, 81 skipped, 5 subtests passed, with real Mongo quota integration enabled. Ruff and Mypy passed (612 files).
- Frontend full regression: 956 files passed, 2 failed (5534 tests passed, 5 failed). Two quota test expectations still used the earlier admin exhaustion-only policy; after correcting those fixtures and adding unknown-usage coverage, all 12 quota-related files / 108 tests passed. The remaining three failures are in the concurrent `useRightPanelState.test.tsx` work: missing i18n initialization exposes raw keys instead of the English button names it expects. Those unrelated files were preserved.
- Frontend lint, TypeScript/production build and whitespace checks passed. The subsequent preview-only reset fixture correction also passed its lint and rendered interaction checks.
- Local Mongo sample: 128 reserve-and-settle pairs, median 0.88 ms, p95 1.19 ms; exact USD totals, no remaining reservations or call records. This measures the local ledger, not provider/network or production load.
- Browser fixtures: desktop light and dark, 375px narrow layouts; visible popup/admin bodies, no horizontal overflow, and action hit tests passed. Card redemption refreshes balances/card count and returns to first-use timing; admin weekly reset preserves five-hour usage, and issuing a card refreshes the selected user's count. Weekly exhaustion and unknown-cost copy were checked separately.
- Local loading incident: the existing backend process had no quota routes in OpenAPI. After a graceful restart using its original environment, an authenticated desktop_dev quota request returned HTTP 200 in 9.37 ms. Invalid payloads and stalled auth/API requests now leave loading within 15 seconds and expose retry.
- No deployment, native client build or paid live-provider invoice/cancellation acceptance was performed. APIs without reliable USD tariffs reject finite-quota users before paid invocation. Codex alignment is limited to its public reset-consumption contract, not undocumented internal rules.

### Follow-up: Complete Regression and Compact Error State

- Fixed the three right-panel failures by initializing real i18n and resolving accessible button names through translations; retained the original draft and panel-reopening assertions. Observed all three fail before the fix and pass afterward.
- Quota/card expiry now triggers a refresh, including deadlines crossed while a response is in flight. A bounded set of already-refreshed deadlines prevents repeated stale responses from causing a request loop. Failed reads disable redemption from retained card data.
- Account changes remount the usage component and abort prior quota requests. GET validates card structures; reset/issue/consume acknowledgements are validated before clearing retry identities. New expiry, account-switch, invalid-card and invalid-acknowledgement cases were observed RED, then GREEN.
- Simplified the unavailable state to an inline short label plus retry, in all five locales. Browser fixtures confirmed desktop light and 375px dark layouts: visible, not busy, same-row alignment, no horizontal overflow, and retry hit testing. Card redemption, admin weekly reset and issuing a card all refreshed their displayed values.
- Final backend regression: **8176 passed, 81 skipped, 5 subtests passed** with real Mongo quota/reset integration enabled; Ruff and Mypy (612 files) passed. Backend source did not change after this run.
- Final frontend regression: **958 files / 5553 tests passed**, zero failures. Full frontend lint and TypeScript/production build passed; eager JS and precache remained inside existing performance budgets. An earlier frontend run was stopped to incorporate the review finding; these totals refer to the completed final run.
- Independent read-only review found the delayed-delivery expiry race; its focused recheck found no remaining issue after the fix. No deployment, native build or paid-provider invoice acceptance was performed.

## 2026-10-18 · 真实供应商与设置页收尾

- [x] 在隔离本地 MongoDB/Redis/服务中复制 desktop_dev 与现有 GLM-5.3 配置，显式 max_tokens=2048 限制验收成本。原开发账号未发卡、重置或修改额度。
- [x] 7 次完整供应商调用的原始 Token 与价目表独立 Decimal 复算，总计 $0.01660848；各原周期纳美元账本一致。另一次生成中途取消未回完整用量，保留 $0.0137698 预占和未知标记，不补零或冒充最终账单。
- [x] 实测 SSE 断线重连不增加模型调用、额度拦截发生在供应商调用前、两会话竞争只准入一次、重置后同 run 恢复及取消后人工继续只有实际新增调用扣减。
- [x] 根据 [Z.ai 官方 FAQ](https://docs.z.ai/devpack/faq) 增加 5 小时/周卡。周手动重置或周卡兑换同时恢复 5 小时，只耗一张周卡，从操作时刻重算周期；5 小时卡不改变周额度。自然到期仍独立首次使用，不推断自然周联动。旧无类型卡保留耗尽后兑换兼容。
- [x] 设置新增“额度与重置卡”，复用同一组件与更新事件；无卡显示 0。额度优先，Token 明细默认收起，五语同步。
- [x] 实际界面兑换周卡与设置中的 5 小时卡；管理员发卡、用量结算、兑换完成和主服务重连均自动刷新。
- [x] 验收中间件在实际已提交兑换后仅丢弃一次成功响应。界面保留独立重试，实际请求复用相同 key/creditId；没有多耗卡或第二次重开周期。新增 regression 先观察 RED 后补修；只读独立复核确认恢复缺陷关闭。
- [x] 后端全量 8183 passed / 81 skipped / 5 subtests passed；状态接口等价简化后补跑 39 项相关回归。Ruff、格式检查、Mypy 612 文件通过。前端最终 12 文件 / 107 相关测试、全仓 lint、TypeScript/Vite/PWA build 通过。
- [ ] 全量前端 RED 批次的范围外 filePathPillLabels 截断断言仍未处理；遵照用户“不要管其他人”，保留并发 UI 改动。该批次本次引入的导航 fixture、重试及后端行数失败均已通过后续相关回归。

真实原始记录与截图：`/Users/clivia/.cache/lambchat/quota-real-20261018-a/`；完整可读报告：`/Users/clivia/.codex/visualizations/2026/10/18/01a14e1e-ba9c-7622-80a4-cd5cc7e6cbd4/quota-real-acceptance/acceptance.md`。已开始的付费 cohort 不得自动重放。仅验当前供应商，不替代发票核销、其它模型、生产负载或原生客户端验收。


## 2026-10-18 用户调整：每次调用前按已结算费用检查

- 用户要求不再因缺少可靠定价或 token 上限而阻止调用。模型及独立付费 API 在每次实际调用前检查用户两个周期的已结算 USD 用量，任一达到上限则停止；调用后逐次结算。
- 删除最坏情况 token 费用预估；未知费用保留审计标记但不阻止后续调用，也不按零费用认证。旧预占支持迟到结算，但不计入准入与剩余额度。窗口、重置、取消、重复结算与用户隔离机制保留。
- 同步调整回归覆盖：缺 token 上限、未知定价、流式/非流式逐次检查、并发超额后停止、未知记录迟到结算及跨窗口 CAS。
- 本轮尝试通过共享入口运行定向测试时退出 75（验证锁占用），未排队或重试；测试、lint 及真实供应商验收均未执行，未重启本地服务，不能视为已验证或已生效。
- 边界：进行中及并发调用可能超额；未知价格/用量无法由此保证美元账单上限。前文有关预占及拒绝未知价格的记录描述旧行为，以本节及更新后的设计为准。
