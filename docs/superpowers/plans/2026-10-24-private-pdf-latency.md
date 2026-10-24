# Private PDF latency implementation plan

Goal: reduce document parsing and model round trips without weakening private attachment access.
Architecture: reuse existing session-scoped attachment ID resolver and deferred tool manager; keep every file authorization and provider fallback. No new dependencies, parsing caches, or background warmup.
Spec: current user request. Prior production timing is separate context; receipt counts included external parsing and must not be presented as LLM-only calls.

- [x] Capture local real-model baseline with identical PDF/prompt/settings, new labeled desktop_dev sessions, serial validation lock.
- [x] TDD attachment_id input for document_parse. Reuse session ownership, active session, unique key, file ownership and deletion checks; never trust supplied URL. Retain bounded download and authorize_file_url; reject ambiguous/missing inputs, no sandbox copy.
- [x] TDD automatic discovery of authorized document_parse for supported document attachments. Search and Team callers, inherited subagent scope, disabled and absent tool policies remain authoritative. Attachment hint prefers direct parsing, downloads only for sandbox edits.
- [x] Review parser fast-path safety. Rejected custom local text-only detection after review found unbounded layout allocation and omitted shading. Keep configured MinerU/OCR semantics intact; optimize direct attachment delivery and tool discovery instead. Retain regression cases for text, scanned/mixed, annotated, encrypted, malformed, huge-coordinate and graphical PDFs.
- [x] Run serial checks: final PDF backend 171 passed, frontend 3 passed, owned Ruff checks passed. Full branch is not green: backend full interrupted after stall, frontend tests/typecheck/lint/build have failures in the shared checkout; see acceptance report. Preserve unrelated workspace changes.
- [x] Run same-condition real model PDF E2E after change (3 per model), inspect actual tool results/model settlements, verify owner/foreign/anonymous/share/revocation. Report both visible first text and substantive answer, parsing time and model call count. Retain sessions and revoke only temporary PATs.

Review focus: cross-session/foreign/deleting attachments; disabled tool exposure; mixed scanned PDFs; partial extraction and page range; real E2E provenance and no replay. Existing production metrics are a separate observation, not a matched local baseline. Do not claim production deployment without CI/staging/promotion.

Review ruling: removed the proposed local text extraction shortcut completely; it added PDF interpretation and resource-exhaustion risk for a small local parsing gain. Both review findings are avoided by preserving the existing provider path. Production uses MinerU cloud (historical parsing 7.781 s); the comparison environment was aligned with the same provider before the final baseline cohort. Preliminary local MarkItDown and connection-failure cohorts remain separate evidence.

Final real-provider evidence: `/Users/clivia/.codex/artifacts/lambchat-pdf-perf-20261024/acceptance.json`. Three new sessions per model: before vs final median visible text 26.0526 → 19.7245 seconds (GLM), 32.4174 → 29.8050 seconds (Flash). Actual LLM calls: before 3 each; final GLM [2,3,2], Flash [3,3,3]. Flash still performs redundant discovery, and its observed latency reduction is largely parser timing variation; no claim of stable Flash model-call improvement. Both after cohorts are retained. All six final calls used attachment IDs and produced correct answers; owner/foreign/anonymous/share/revocation and live missing/foreign/deleting-ID checks passed. Synthetic accounts disabled, copied model/parser credentials removed, owned API and tunnel stopped. Production unchanged.

Static reviewer found no important issues after removing the text shortcut. Final regression is serial; current shared permission work has six unrelated focused failures (one upload permission fixture, five memory-tool authority fixtures), so full-green status is not claimed.

Final tests adjusted two expectations: document guidance adds 176 characters while preserving sandbox constraints (policy budget 1700 → 1900; tool-schema budget unchanged), and inline filename is part of the translated tool label. Final PDF suite passed 171 backend + 3 frontend tests. Full gate remains blocked; no commit, push or deployment was performed.

Post-validation integration boundary: concurrent permission work changed Search/Team sandbox-confirm middleware after real E2E. PDF discovery calls remain intact. Source hashes and observed current hashes are saved in acceptance.json; do not reuse these results as full validation of the newer combined checkout.
