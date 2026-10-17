# Quick Search Handoff Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement inline.

**Goal:** Quick 自动在同一对话、同一轮任务中交给 Search 完成执行。

**Architecture:** Quick 返回内部交接结果；基础流跳过交接阶段终态，公共执行入口顺序切换 Search。按 run 持久化实际 Agent 和用量，复用现有审批、取消及历史事件。

**Tech Stack:** Python / LangGraph / React / TypeScript / Vitest / pytest。

**Spec:** `docs/superpowers/specs/2026-10-17-quick-search-handoff-design.md`

## Global Constraints

- 保留当前分支及所有已有改动，不创建 worktree、不 stash。
- 所有验证使用 `python3 scripts/run_validation.py`，worker=1；锁占用即退出。
- 同一 session/run/trace，保持权限、persona、附件和工具限制；五种 locale 同步。

## Review Focus

- 交接与取消竞争：取消后不得启动 Search。
- 审批恢复：恢复 Search，不重新选择路由；用量只累计一次。
- Checkpoint：Quick 交接不得留下无对应结果的 tool call 或重复用户消息。
- 模型 fallback：保持交接工具协议及工具能力边界。
- 过期 run：不得覆盖新一轮执行配置或使用旧交接信息。

## Tasks

- [x] 写 Quick 节点、真实检查点、执行交接、取消和恢复测试。初始 RED 已执行：5 failed / 1 passed；后续新增用例因共享锁阻塞尚未运行。
- [x] 修改 Quick 的 prompt/node/state、模型重试工具绑定和基础流终态处理；实现服务端交接与 run 级实际 Agent 解析。
- [x] 接上 Search 用量承接、审批和重启恢复；保留累计值优先级。
- [x] 新增 status 里程碑的前端解析和共享 pill 展示，更新五语及回放测试。
- [x] 复核统一验证中的受影响测试、格式/类型检查及前端构建，确认当前相关源码与该次状态一致。
- [ ] 使用真实模型和浏览器完成 Quick 接力、停止、审批及重启验收；共享名额占用，尚未启动。
- [x] 独立静态代码审查；两个 P1 已修复，新增重启及累计用量回归已在后续统一验证中通过。

## Verification handoff

首次实现时，前端 TDD 命令通过共享锁返回 75；依仓库协作规则立即停止验证，没有重试、排队或绕过锁。未重启本地后端或使用其他会话正在验收的账号/任务。后续统一验证结果见下方更新；尚无本功能真实模型与浏览器操作验收结论。

统一验证需覆盖：`tests/agents/quick_agent/`、`tests/api/routes/test_quick_search_handoff.py`、`tests/infra/agent/test_handoff.py`、`tests/infra/task/test_handoff_recovery.py`、既有 Base 取消/用量、node_utils 用量、LLM retry、HITL/recovery、chat Goal/base_url/memory 测试；前端 `agentHandoff.test.ts`、事件处理/历史回放/消息渲染及 build/lint。

## Review ledger

- P1 修复（待验证）：Quick 先以稳定 ID 写入用户消息，正常 Search 复用 ID；重启只追加恢复指令并恢复原附件，避免交接启动窗口丢请求。
- P1 修复（待验证）：重启读取同 trace 最后累计用量，与初始 Quick 计数按字段取较大值；恢复不再用初始 Quick 快照覆盖 Search 已记录的消耗。
- 停止与权限：接力前后检查取消信号，按当前 run/状态更新元数据，并再次校验目标权限；显式关闭阶段流，恢复同 trace 请求上下文。

## 2026-10-17 统一验证复核

- 来源：对话「排查并修复 Goal 与定时任务竞态」的私有验证目录 `~/.cache/lambchat/desktop-dev-goal/verification-20261017-first-grade-v3/`。
- `backend-final.log` / `backend-final.xml`：7480 passed、4 skipped、5 subtests passed，126.20 秒。4 skip 为当前 macOS 上的 3 个 Windows ACL 用例和缺凭据的 E2B 云测；Windows 用例另有原生机器结果，不计作本功能真实模型验收。
- 从该 JUnit 筛出 Quick、handoff、HITL、token carry 与 Base 取消相关 76 项，0 failure / 0 error / 0 skip。覆盖共享图上下文与稳定 ID 去重、交接前取消、Search 取消清理、审批选实际执行者、重启附件及累计值、连续恢复与幂等金额落库。
- 已核对 `backend-verified-source.json`：Quick node/state、Base、node_utils、Search node、handoff helper、HITL、recovery 的当前 SHA256 与该次全量快照一致。随后改动仅涉及下述执行入口 guard 及新增/扩展测试，需补对应验证，不能把旧全量结果当作新状态全量结果。
- 全仓 Ruff 首次发现用量测试 import 格式问题，已由统一对话通过共享入口修复；其后全仓 Ruff 通过。
- Mypy 报执行入口三处 `run_id: Any | None` 传给字符串接口。新增 `test_handoff_requires_a_persistable_run_id` 已真实 RED（1 failed / 5 passed），再增加非空字符串校验，避免缺运行 ID 时进入取消检查、持久化和 Search 接力。
- 将已有累计金额落库测试扩为两种路径：原 HITL，以及 Quick→Search→多次 HITL（含零新增调用）。手算断言保持 input=350 / output=35 / total=385 / cache_read=60 / cost_usd=0.000366，重复 upsert 同一 trace 不加倍。
- 本轮受影响回归命令被共享锁以 75 拦截；不排队、不重试。新 guard、扩展金额测试的 GREEN、最终 Mypy，以及前端全量/lint/build 由统一对话补齐；本对话未重复启动这些检查。

## 2026-10-17 后续统一验证复核

- 同一统一验证目录的 `backend-post-memory.xml` 已包含并通过 `test_handoff_requires_a_persistable_run_id`、两种 `test_restart_preserves_handoff_request_files_and_latest_usage` 和两种 `test_repeated_hitl_resumes_store_one_cumulative_usage_record`。Quick/handoff/恢复及累计落库新相关用例筛选 21 项，0 failure / 0 error。
- `mypy-post-memory.log`：604 source files，无错误；`ruff-post-memory.log`：通过。执行入口 guard、恢复 helper 与新增/扩展测试的当前 SHA256 均匹配 `real-goal-source-start.json`。
- `frontend-final.log`：935 个测试文件、5266 项测试通过；`frontend-lint-final.log` 和 `frontend-build-final.log` 已完成。已核对 Quick 里程碑解析、回放测试、渲染、折叠及五语源码的当前 SHA256 均匹配统一对话后续源码快照。
- 最新后端全量结果为 7485 passed、12 failed、4 skipped、5 subtests passed。12 项失败集中于 `test_subagent_activity_references.py` 的伪造活动日志路径校验，统一对话及对应模块所有者正在修复；不能将该批次称为全量通过。
- 真实验收准备位于仓库外 `~/.cache/lambchat/quick-handoff-live-20261017/`：独立 loopback 8018、真实 desktop_dev/glm-5.3、MongoDB/Redis、正常持久化文件后端、观察模型原始用量；可仅重启本验收进程，保留原账号与对话。脚本尚未启动，不能当作真实验收结果。
- 启动该验收的共享入口实际退出 75：`LambChat validation slot is busy`。占用者为统一对话的真实 Goal 任务。依规范未排队、未重试、未并行启动，未重启任何后端；Quick 真实模型与浏览器的上下文、停止、审批及重启结果仍待验收。
