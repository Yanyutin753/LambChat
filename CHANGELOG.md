# Changelog

## v2.7.0 (2026-08-28)

### ✨ New Features

- Add a production memory system: auto-capture of full exchanges with a daily cap, query-time relevance injection with write-time persistence (sent bytes == stored bytes), context-field scope filtering across recall/tools/API/panels, an opt-in VFS working-memory layer, embedding model hot-swap, and automatic vector index creation (#264).
- Fold assistant mid-run process output into a Codex-style status summary line with working/done states and design-aligned default expansion (#267).
- Add trace window pagination for session events to keep long sessions responsive.
- Add SEO foundations: a real sitemap, self-hosted fonts, compressed og images, HEAD request support, www 301, and hreflang with real paths (#258, #259, #260).
- Add Git-flow release infrastructure: a develop integration branch with dated images, a staging environment, and a main merge gate (#263); AGENTS.md becomes the single source of development conventions (#262).
- Add a running-state composer placeholder hinting that typed follow-ups queue as ordered steers.

### 🐛 Bug Fixes

- Fix previews and exports for networks that cannot reach object storage: every upload-file fetch (document/excalidraw/code previews, project reveal, ZIP export) retries once through the app proxy (`?proxy=true`) when the direct redirect target fails; image previews switch to blobs and video/audio/DXF gain fallback paths (#269).
- Fix the embedded arq worker silently dropping out of queue consumption after unsupervised future failures — workers are now supervised and restarted (#261).
- Fix GPT 401s from upstream key exhaustion by routing auth errors into the fallback chain (#252); stop sending the hardcoded 0.7 temperature so unset models use provider defaults (#250); split first-byte and total stream timeouts for unstable relays (#239); deduplicate replayed upstream response ids via UniqueResponseIdMiddleware (#245).
- Fix assistant-reply misalignment when resending the same user message (#247).
- Fix long-session open freezes caused by full prefetch and quadratic rebuilds (#248).
- Fix distributed-runtime configuration: connection settings are env-authoritative with masked alerts, and upload URLs follow the actual entry origin (#249, #253).
- Fix the /stream route being hijacked by a helper, with route-binding regression tests.
- Fix settings.set on unregistered keys no longer triggering cross-instance broadcasts.
- Fix streaming timers frozen behind a static elapsed value and align the collapse summary color with body text (#267).
- Fix share pages stuck in the sepia theme and add /fonts/ to the anonymous auth whitelist.

### ♻️ Refactors

- Unify scroll behavior and font styles (font-serif) across components; format the whole repository with ruff, docs code blocks included.

### 🧪 Tests & Infrastructure

- Add a production distributed regression suite (load balancing, auth, sessions, arq consumption, SSE/WS delivery, checkpoints, uploads, scheduled tasks); repair the CI reds from an escaped direct push and split oversized frontend hooks (#255, #257).

---

## v2.6.0 (2026-08-23)

### ✨ New Features

- Add Codex-style mid-run steering: queued bubbles in the chat flow, reworked queue chip interactions, persisted injection messages, and a fully decoupled steer event pipeline with idempotent delivery and cancellation.
- Add same-run HITL resume: ask_human interrupt mode with LangGraph suspend/breakpoint recovery, concurrency control, and full interrupt parity for Search and Team agents.
- Add session pin-to-top: pin toggle API and storage, pinned-first session ordering, right-click context menu on session items, and a task running indicator badge with WebSocket real-time status updates.
- Add message image gallery with adaptive grouped layout, markdown image sizing with zoom cursor, and shimmer animation for in-progress image generation frames.
- Add sepia eye-care theme alongside light/dark modes, accepted in profile metadata.
- Add LLM model adapters with streaming timeouts and retry logic, a global LLM_FALLBACK_MODEL fallback for stream-timeout failures, and alternate-model fallback when auto-summarization fails.
- Add message timeline rail with touch interaction, plus copy-feedback and chat layout polish.
- Add rich composer attachment handling: asynchronous image processing and upload stages with per-owner scoping.

### 🐛 Bug Fixes

- Fix attachment lifecycle end to end: claim attachments before persistence, harden rollback boundaries, guard upload tombstone dedupe races, preserve key collision objects and rejected drafts, isolate submitted drafts and upload aborts, and restore file paste uploads.
- Fix chat submit flush race by avoiding delayed flush waits, and dismiss the slash menu on outside press while keeping it closed.
- Fix steer reliability: write steer:message events at injection time for correct ordering, cancel stale queued steers before follow-up resend to stop double delivery, and stop run-level user:message dedup from dropping same-run steer messages.
- Fix approval handling: persist approval_required events to MongoDB via trace_id for history replay, support session-specific approval clearing, validate ask-human forms across steps, and stop rendering ask_human events as generic tool events.
- Fix model selection: preserve the chosen model across refresh, encode selection priority, expose system default model identity, and guard model restoration side effects.
- Fix scheduled tasks by anchoring message timestamps to run start for cache stability.
- Fix PWA to auto-activate a waiting service worker on page load.
- Fix LLM thinking-parameter handling by passing off/none explicitly with per-family gating (#211).
- Fix memory indexing scoring to include source type and stabilize message reference handling.

### ♻️ Refactors

- Delegate prompt caching to official provider/DeepAgents layers: remove cache-oriented prompt shaping and custom cache controls, adopt Codex-style context layering for cache-continuous prefixes.
- Move memory, skills, deferred-tool, and env-var key metadata out of the system prompt onto tool descriptions.
- Split oversized frontend hooks (steerMessage, draft submission, external navigation) to keep useAgent under 1000 lines, and restore backend module budgets.

### 🚀 Performance

- Improve provider prompt-cache hit rate (#214), stabilize cache prefixes across turns and restarts, and freeze the deferred-tool stub list at session scope.
- Cut chat latency: overlap task preflight, prepare agent dependencies concurrently, compact full history hydration, reduce session read round trips, and defer user message search indexing.
- Refresh stale MCP catalogs in the background and warm recent MCP users after startup; avoid re-renders on scroll range changes.

### 🧪 Tests & Infrastructure

- Add dated Docker image tags (main-YYYYMMDD plus build time) for image rollback.
- Make tests hermetic without Redis, stabilize timing-sensitive suites, and extend coverage for HITL, steer, pinning, and the image gallery.

---

## v2.5.6 (2026-08-09)

### ✨ New Features

- Add unified right sidebar UX with coordinated panel stack, responsive layout, and shared lifecycle management.
- Add race-safe session history snapshots with opt-in state, batched trace event reads, and navigation-before-load optimization.
- Add rich chat composer with atomic node contracts, inline skill nodes, long-text-as-file references, and input history with keyboard navigation.
- Add unified document viewer supporting DOCX, PDF, PPTX, and Excel previews with embedded OOXML worksheet image extraction.
- Add per-model cache rate display with aggregated usage metrics and provider-scoped prompt cache optimization.
- Add deferred conversation history access tools with per-run search projections, indexing, and authorized conversation search/paging.
- Link durable memories to conversation runs with lifecycle-preserved conversation refs.

### 🐛 Bug Fixes

- Fix mobile layout: standardize toolbar icon sizes, flatten tool console actions, contain nested file-panel rows, and compress preview headers.
- Fix deferred system tools: inject runtime correctly and exclude runtime from MCP call schema.
- Fix prompt cache: single middleware owner, provider-scoped options, and cache policy adaptation for latest models.
- Fix Excel preview: contain malformed drawings and position worksheet images correctly.
- Fix chat: include draft in long-text paste attachment and preserve workspace beside right panels.

### ♻️ Refactors

- Remove legacy todo middleware and isolate document viewer layout helpers.
- Place volatile prompt sections last and optimize cache breakpoints by provider.
- Migrate PPTX, PDF, and DOCX previews to a shared reader framework.

### 🧪 Tests & Infrastructure

- Add deterministic frontend artifact budgets and session event fake alignment with batch reads.
- Cover active panel escape behavior and chatInput focus/keyboard shortcut tests.
- Establish full repository performance audit with frontend shell and PWA precache budgeting.

---

## v2.5.5 (2026-08-09)

### ✨ New Features

- Add progressive tool and skill discovery with pinyin-aware search, deferred system tools, and runtime harness provider registration.
- Add provider-neutral lazy sandbox initialization, Search Agent on-demand sandbox startup, and sandbox ID visibility in readiness feedback.
- Add background artifact delivery and recommendation generation with persisted, run-scoped results.
- Improve project sharing and downloads, long-text composition, image tooling, and chat message presentation.

### 🐛 Bug Fixes

- Apply CJK Markdown delimiter parsing consistently across rendered chat content.
- Preserve structured DeepAgents backend failures and v0.7 tool-result compatibility.
- Harden sandbox creation, cancellation, event ordering, cleanup, and background task isolation.
- Redact sensitive paths and connection details, validate image data URLs, and close related security edge cases.

### ♻️ Refactors

- Migrate sandbox and skill backends to the DeepAgents v0.7 protocol while preserving legacy compatibility boundaries.
- Remove the legacy sandbox MCP transport and compact dynamic prompts and tool schemas.
- Split oversized backend modules and consolidate shared agent workflows.

### 🧪 Tests & Infrastructure

- Expand regression coverage for sandbox lifecycle, backend result formats, prompt discovery, background delivery, and Mongo-backed tests.
- Improve deterministic test configuration and runtime cleanup behavior.

---

## v2.5.4 (2026-07-12)

### ✨ New Features

- **Image Analysis Tool** — Dedicated image analysis tool with configurable model ID and settings.
- **Subagent Activity Logging** — Result handoff middleware with structured logging for subagent execution.
- **Skill Chips in Chat Messages** — Visual skill chips rendered in messages with enable/disable handling.
- **ToolArgsDisplay Component** — Rich rendering of tool-call arguments in the chat UI.
- **MCP Tools Inline Exposure** — Inline exposure for MCP tools with updated related policies.
- **Share Update Functionality** — Share dialog updates with improved privacy reminder coverage.
- **EvalItem Component** — Code preview integration into MessagePartRenderer for evaluation display.
- **Drag Overlay for File Uploads** — Drag overlay component in ChatInput for intuitive file drop.
- **Panel Search Input** — Integrated PanelSearchInput across selectors and dialogs for consistent search.
- **Enhanced Selector Modals & Skill Handling** — Improved skill selector, model selector, and persona picker UX.
- **Scheduled Task Panel Attachment Support** — Attach files to scheduled tasks with improved sidebar display.
- **Run Mode Popover Refactor** — Improved position logic and cleaner test coverage.
- **Team Agent Specialized Subagents** — Enhanced team agent with specialized subagents and main-agent context handling.
- **File Upload Dropdown Extraction** — File upload dropdown style logic extracted into a separate module for reuse.
- **Session ID Handling** — Session ID propagated across components and tests for better traceability.
- **i18n Updates** — Translations for channel status, instance count, and loading messages across multiple languages.

### 🐛 Bug Fixes

- Fix project preview height collapse in sidebar mode and tool panel iframe height chain.
- Fix SummaryItem missing text-xs and font-medium classes.
- Fix CI lint failures on PR #176.
- Fix scheduled task single-execution timeout default raised to 30 minutes.
- Fix cubesandbox dependency updated to v0.3.0, removing local path references.
- Fix chat useEffect dependency for availableRunSkills.
- Split useMessageScroll hook under 1000 lines for CI compliance.

### ♻️ Refactors

- Refactor theme colors and styles across components for consistency.
- Extract components from ChatInput.tsx and useAgent.ts to pass CI line-length checks.
- Refactor session workspace handling and improve internal tool configurations.
- Simplify skills_store `_is_skill_visible` to disabled_skills blacklist only — removed enabled_skills whitelist check to avoid blocking agent file access.
- Enhance message scroll settling with configurable fallback timeout and physical scroll recovery (`forceScrollerToPhysicalBottom`).
- Enhance SkillSkeletons with banner overlay pills, gradient direction fix, and closer alignment to real SkillBaseCard layout.
- Standardize panel skeleton card count and improve styling for collapsible sections.

### 🔒 Security

- ArtifactDeliveryMiddleware test coverage for delivery validation.

### 🧪 Tests

- Cancellation token usage and event handling tests.
- ArtifactDeliveryMiddleware functionality tests.
- Tool timeout prompt default updated to 3600s.
- Formatted sidebar chrome CSS tolerance in tests.
- Skills file payload build tests.
- Session management and session_id handling tests.
- emit_user_message enabled_skills tests.
- File upload dropdown style logic tests.

### 🔧 Infrastructure

- Trace event chunk storage and thinking chunk buffering for improved streaming UX.
- Sandbox management helper functions and re-export of `ensure_sandbox_mcp`.
- Core, infrastructure, sandbox, and tools setting definitions added.
- Scheduler timeout limits extended with improved task execution feedback.
- CI: track trace migration scripts.

---

## v2.5.3 (2026-06-21)

### ✨ New Features

- **Usage Dashboard Refresh** — Added trend cards, rankings, insights, and a structured usage log table.
- **Feishu Channel Refactor** — Split approval, collection, and event handling into dedicated modules.
- **Presentation & Usage Telemetry** — Expanded persisted trace metadata and usage rollups.

### 🐛 Bug Fixes

- Improve loading and skeleton states across agent, model, memory, skill, and usage panels.
- Add share dialog privacy reminder coverage.
- Harden scheduled task runtime and active goal behavior.

## v2.5.2 (2026-06-14)

### ✨ New Features

- **Web Push Notifications** — VAPID key management and public key endpoint (#web-push)
- **Scheduled Task Management Tools** — New tools for managing scheduled tasks
- **Persona Editor Enhancements** — ConfigPanelErrorCallout component and preset persistence
- **Memory Recall & Store** — New memory components with detailed UI and test coverage
- **Subagent Block** — Parts prop support for richer subagent rendering
- **i18n Updates** — Added 'loading' message and restored 'table' entry across multiple languages

### 🐛 Bug Fixes

- Improve markdown stripping in AskHumanItem
- Fix setPersonaPreset missing from useEffect dependencies in ChatAppContent

### 🔒 Security

- Web push notification VAPID key integration and test coverage

### ♻️ Refactors

- Refactor code structure for improved readability and maintainability
- Enhance loading spinner colors across multiple components

### 🧪 Tests

- Memory recall and tool argument tests
- VAPID public key endpoint test case

## v2.5.1 (2026-06-13)

### ✨ New Features

- **Mobile Support** — Capacitor integration for Android/iOS, native safe area support, file proxy streaming, pptx preview
- **Desktop Auto-Update** — One-click auto-update for Tauri (desktop) and Capacitor (mobile)
- **Native Notifications** — Push notification support for Android and Tauri
- **Memory Components** — Memory recall and store components with detailed UI
- **Scheduled Tasks** — Scheduler module with permission management and execution (#155)
- **Session Sidebar** — Full refactor with actions, effects hooks, channel delivery, and tool items (#156, #158)
- **Subagent Panel** — Footer with timestamp rendering, status indication styles
- **Shared UI Components** — Input component with leading icons, collapsible DetailSection, panel header improvements
- **Persona Preview** — Source view toggle, button style enhancements
- **Mark All Read** — Batch read with project and scheduled task filtering
- **Feishu** — Add recommendation_input to message handler
- **Image URL Conversion** — Support image_url to base64 in model profiles and middleware
- **File Preview** — Link interception logic, Virtuoso follow output
- **Distributed Runtime** — Validation and improved secret management
- **New Tool Items** — Sandbox MCP, Scheduled Tasks, Teams

### 🐛 Bug Fixes

- Fix 404 on shared page
- Fix chat scroll bottom lock
- Dedupe scheduled task fire slots and memory backend reset tasks
- Accept future awaitables in background scheduling and cleanup hooks
- Release background task references on shutdown
- Fix team list count awaitable handling
- Enhance ZIP member path validation
- Bound GitHub skill preview downloads
- Harden packaged app and CI release builds
- Share packaged frontend build correctly

### ♻️ Refactors

- Streamline skill handling by removing unused effectiveSkills computation
- Implement file streaming proxy for native app environments
- Optimize scheduler and improve OAuth reliability
- Improve panel dropdown accessibility and mobile responsiveness
- Consolidate panel header mobile density and overflow menu
- Enhance file type acceptance for images, videos, and audio

### 🧪 Tests

- Unit test for effective skills in chat skill selector
- Test stable skill list params prevent refetch loops
- Virtuoso follow output tests
- File preview link interception tests
- Subagent panel footer and style tests

### 📖 Documentation

- Update README and README_CN with scheduled tasks and task runtime details

### 🔧 Desktop

- Auto-clean app data (localStorage, webview cache) on version upgrade — ensures fresh state after install

---

## v2.5.0 (2026-06-04)

### ✨ New Features

- **Team Collaboration** — Full team management with CRUD API, role-based subagent dispatch, Team Builder UI, team picker modal, and agent collaboration pipeline
- **Multimodal Vision Support** — Image inlining via data URLs, multimodal model integration, optimized backend performance for vision tasks
- **Excalidraw Preview** — Full preview support with dark fullscreen viewer, card thumbnails, blob-URL rendering, and direct image loading
- **Image Generation & Editing** — Image generation with size normalization, image editing tool, standardized filename generation
- **Active Goal System** — Rubric-guided execution, goal tracking for Feishu agent execution
- **Agent Catalog** — Skill preferences, recommended questions, persona preset auto-switching
- **Distributed Architecture** — Consistent-hash node assignment, distributed connection checks
- **i18n** — Replace hardcoded strings with translation keys across frontend
- **Feishu Enhancements** — Media handling, deep linking support, enhanced channel registration
- **Tool Error Handling** — Robust tool error handling and refined chat UI
- **MCP Sidebar** — Expandable tool items, image generation in internal registry
- **Chat Toolbar** — Refactored toolbar with code text selection and native copy
- **Image Preview** — RevealPreviewHost image preview support
- **PWA Improvements** — Toast styles, icons, and provider labels
- **Client-side Pagination** — Selectors with accurate skill counts
- **Configurable Limits** — MCP, session, and event merger limits

### 🐛 Bug Fixes

- Fix Excalidraw thumbnail rendering for proper object-contain scaling
- Fix API request body replay logic in middleware
- Fix frontend race conditions in agent loading
- Fix Feishu lease release on cancelled startup
- Fix UI auto-preview on mobile devices
- Fix help menu visibility and message duplication
- Fix file reveal artifact deduplication in chat messages
- Fix team_id wiring through entire task submission pipeline
- Fix team builder stale references and default_member_id resolution
- Fix conditional S3 file deletion in session manager
- Fix shared content event upper bound removal

### ♻️ Refactors

- Enhance type safety, async task handling, and sandbox protocol standardization
- Optimize startup and task recovery with concurrency
- Improve robustness of backend protocols and sandbox tools
- Replace asyncio.to_thread with custom run_blocking_io utility
- Improve resource lifecycle management and agent routing logic
- Enhance arq worker executor resolution and concurrency cleanup
- Refactor team-based skill and persona constraints
- Optimize recommendation generation and system stability
- Refactor chat UI — tab bars as segmented controls, mobile UX, tool feedback
- Optimize postgres checkpointer and model configuration
- Improve api_key resolution and agent event handling

### 🎨 UI/UX

- Redesign tab bars as segmented controls
- Improve mobile UX and component usability
- Refine team list page with minimalist cards
- Update app icons
- Improve welcome page layout

### 🧪 Tests

- Comprehensive tests for various tools and configurations
- Regression tests for team and agent features
- Test cases for session cancellation, memory, storage limits
- Tests for Feishu handler, sender, registration, and manager
- Extensive API route tests and infrastructure tests

### 📦 Build

- Docker: optimize dependency installation and update entrypoint

### 📝 Documentation

- Overhaul README documentation and product presentation
- Add team UX theme styling design

---

## v2.4.1

Previous release.
