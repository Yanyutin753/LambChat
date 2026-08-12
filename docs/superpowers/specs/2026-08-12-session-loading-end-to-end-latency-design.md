# Session Loading End-to-End Latency Design

## Goal

Make opening an existing conversation visibly complete as soon as its full
history is available, while reducing the database and HTTP work triggered by
the surrounding application. The work covers the slow requests observed in
the browser trace: session detail and lists, history events, mark-read,
feedback, teams, and settings.

The product continues to load and display complete conversation history. This
design does not introduce history truncation, pagination, a "load older"
control, or a stale persistent browser cache.

## Observed behavior

The production browser trace showed:

- a 93.2 KiB history response taking 3.91 seconds;
- 4-5 KiB session lists taking 2.38-2.84 seconds;
- session detail, mark-read, and feedback requests taking about one second;
- team and settings responses taking more than four seconds; and
- multiple requests for the same session detail during one navigation.

The durations are too large to be explained by response size. Current route
implementations also show latency accumulating across multiple database
operations: session lists read the favorites project, then count, then fetch;
feedback reads items, count, and statistics serially; history reads the
session before reading trace parents and chunks. The frontend adds redundant
session-detail requests for SEO and keeps the real message list covered during
the post-settle observation window.

## Chosen approach

Keep the existing public API contracts and shorten their critical paths. Use
query concurrency where operations are independent, owner-scoped atomic
updates where a read only exists to authorize a write, database-side filtering
for an active trace, and narrowly invalidated in-process caching only for the
stable settings snapshot. Remove redundant frontend reads by routing session
titles through the existing title event cache. Reveal history after the first
physical-bottom settle while continuing layout recovery invisibly.

This approach is preferred over a new bootstrap endpoint because it improves
the independent settings and team endpoints too, avoids coupling unrelated
responses, and can be delivered as small regression-tested changes. A Redis
or materialized-history cache is out of scope because current evidence does
not justify the consistency and permission complexity.

## Global invariants

- Complete terminal history remains present, ordered, and untruncated.
- Legacy embedded events, chunked events, and mixed migrated traces remain
  readable.
- An active run contributes its persisted user message to the initial snapshot
  and receives assistant/tool lifecycle data through the existing SSE replay.
- Session ownership is checked before returning data or mutating state.
- A stale or aborted history load cannot overwrite the active conversation.
- Settings changes remain coherent across application instances through the
  existing Redis pub/sub channel.
- No optimization may make a hidden or unauthorized session observable.

## Backend design

### Session detail and list queries

`GET /api/sessions/{session_id}` starts the session lookup and favorites
project lookup concurrently. Both operations depend only on authenticated
user input. The route awaits both, verifies ownership, and only then returns
the normalized session. Concurrency changes timing, not authorization order or
response shape.

For ordinary session lists (`favorites_only=false`), the route starts the
favorites project lookup and the storage list operation concurrently. Storage
executes `count_documents` and the bounded, sorted page query concurrently.
After both route-level operations complete, the route normalizes returned
metadata with the favorites project ID. A favorites-only request first resolves
the favorites project ID because that ID is part of its database predicate,
then runs count and page reads concurrently.

Query-plan validation covers these shapes:

- user plus active status ordered by `updated_at`;
- user plus project ordered by `updated_at`;
- user plus the unclassified/scheduled-task exclusions ordered by
  `updated_at`; and
- user-only recent conversations ordered by `updated_at`.

Existing indexes are reused when their execution plans avoid blocking sorts
and broad document scans. A new index is added only when a focused
`explain("executionStats")` fixture demonstrates that an existing shape cannot
use an appropriate index. Index creation remains idempotent through the
existing storage initialization path.

### Owner-scoped mark-read

The normal mark-read path becomes one atomic update constrained by both the
canonical session identifier and `user_id`. UUID/custom IDs and legacy
ObjectId-backed sessions are included in the same bounded predicate when the
identifier is a valid ObjectId.

`matched_count > 0` is success even when `unread_count` was already zero. On a
miss only, the route performs the existing session lookup so it can preserve
the current 404-versus-403 behavior. The common authorized path therefore
uses one database round trip without weakening ownership checks.

### Feedback aggregation

Feedback items, total count, and rating statistics are independent reads over
the same immutable query parameters. `FeedbackManager.list_feedback` starts
all three with `asyncio.gather` and constructs the unchanged
`FeedbackListResponse` after they complete. An error still fails the request;
partial feedback data is never returned.

### Team list

The team storage query preserves pinned/favorite ordering. After resolving the
user preference arrays, one aggregation pipeline uses `$facet` to return both
the total count and the requested page. The page branch retains the current
computed `is_pinned`/`is_favorite` fields, sort, skip, and bounded limit. The
manager continues to hydrate all member persona metadata with one batch
lookup. Empty results avoid the persona query.

This removes the standalone team count query without changing pagination or
preference semantics.

### Settings snapshot cache

`SettingsService` caches the fully assembled `get_all` result by
`(admin_mode, mask_sensitive)`. Concurrent cache misses share one in-flight
task so a slow database cannot trigger a thundering herd. Returned values are
deep copies so callers cannot mutate cached `SettingItem` objects.

The cache has no time-based stale window. It is synchronously invalidated
after a successful local `set`, single-key reset, reset-all, or environment
initialization write. A remote settings pub/sub message invalidates the cache
before refreshing the process-local runtime setting. Shutdown clears cached
values and cancels no completed caller work.

### Active history projection

The trace snapshot query still observes trace status and chronological order
once. Completed traces retain their complete legacy event arrays and complete
chunk reads. For the one active running trace identified by
`active_run_id`, MongoDB projects only `user:message` entries from an embedded
legacy array. Chunk reads use a separate bounded active-trace query whose
projection filters each chunk's events to `user:message` before the data
crosses the database connection.

Completed trace chunks remain a single batch query. The completed and active
chunk queries may run concurrently after the parent snapshot is known. Mixed
legacy/chunk prefix handling, sequence ordering, recommendation synthesis,
event filters, explicit limits, and terminal-transition/SSE snapshot semantics
remain unchanged.

The active path must prove that thousands of `message:chunk`, tool, and agent
events are neither transferred into Python nor visited by the Python
reconstruction loop merely to be discarded. Terminal paths must prove exact
full-event equality with the existing compatibility reader.

### Compact full-history transport

The events endpoint gains an additive `compact_message_chunks` option that
defaults to false. The frontend history loader enables it; existing API
consumers continue receiving raw event granularity.

When enabled, the response assembler merges only consecutive
`message:chunk` events belonging to the same trace, run, depth, and agent,
with no intervening semantic event. Their content is concatenated exactly in
sequence order. The merged event retains the final chunk's timestamp and
sequence as the replay baseline. A chunk carrying additional data outside the
known routing/content fields is not merged. Thinking, tool, artifact, agent,
approval, usage, error, cancellation, goal, recommendation, metadata, and done
events are never compacted or reordered.

This changes transport granularity, not conversation history: reconstructed
message text, parts, tool boundaries, timestamps used for SSE deduplication,
and all user-visible content remain identical. It removes the JSON and
frontend loop overhead of thousands of token-sized events without truncating
the conversation.

### Timing evidence

The existing `X-Process-Time` header remains the authoritative whole-request
server duration. The affected routes add bounded `Server-Timing` metrics for
their major internal phases, using stable names without session IDs, user IDs,
query values, exception bodies, or other sensitive data. At minimum:

- session routes: `session`, `favorites`, `page`, and `count`;
- events: `session`, `trace_parents`, `trace_chunks`, and `assemble`;
- teams: `preferences`, `page`, and `personas`; and
- settings: `settings_db` or `settings_cache`.

Metrics are diagnostic only and do not change error handling. Browser and
server logs can therefore distinguish backend work from proxy/network delay
after deployment.

## Frontend design

### Critical-request scheduling

Opening a conversation gives session detail and compact full-history events
the highest application priority and starts them together. Mark-read and
feedback remain nonblocking. Initial sidebar data that is already visible may
load concurrently, but hidden panels, closed dialogs, background refreshes,
and speculative second pages do not start while the essential history pair is
pending.

The implementation uses explicit component state and existing browser task
primitives rather than a global request queue. Once history is committed,
deferred visible work resumes. Failure of a deferred request remains isolated
from the conversation load.

### Remove duplicate session-title reads

`useAgent.loadHistory` publishes `sessionData.name` through the existing
`dispatchSessionTitleUpdated` helper as soon as the current request is known
not to be stale. `ChatPageSEO` reads the existing title cache and listens for
that event. It no longer issues its own initial `sessionApi.get` request or the
three-second polling request.

Direct navigation remains covered because `ChatAppContent` performs the same
history load and publishes the title. If history fails, SEO retains the
localized default title rather than starting an independent request. Generated
titles continue to use the same cache/event path.

No generic long-lived GET cache is introduced. Different list filters continue
to produce distinct requests. Identical session-detail reads within one
navigation disappear at their source instead of sharing abort behavior across
unrelated consumers.

The global settings hook also coalesces its mount and `auth:login` triggers
through one in-flight promise/request generation. A completed authentication
transition may start one fresh read; repeated events for the same authenticated
generation do not. Stale settings results cannot overwrite a later login or
logout state.

### Session-list request audit

Each list-owning surface is mounted only when visible or explicitly opened.
The project sidebar loads sessions only for expanded/visible project sections;
the recent-chats dialog loads pages only while open; its intersection sentinel
may fetch the next page only after the first page establishes `has_more` and
the sentinel is actually inside the dialog scroll root. Existing filters and
deduplication remain unchanged.

Tests assert that closed dialogs and collapsed project groups make zero list
requests, a reset produces one first-page request, and one visible sentinel
transition produces at most one next-page request. Background soft refreshes
coalesce while one equivalent refresh is pending.

### Parsing and reconstruction work

`sessionApi.getEvents` sends `compact_message_chunks=true` only for full chat
history hydration. Preview, notification, sharing, and raw event consumers keep
their existing request semantics unless separately proven compatible.

History reconstruction still commits the complete message list once. It does
not perform per-event React state updates, and it preserves Virtuoso
virtualization. A performance regression fixture reconstructs a long response
with at least 15,000 raw-equivalent chunks and asserts exact output equality
between raw and compact inputs; wall-clock values are reported for diagnostics
rather than used as a flaky CI threshold.

### Position history at the bottom once

The conversation skeleton is visible only while essential session/events data
has not been reconstructed and committed. Once the complete message list is
available, Virtuoso renders with its last item aligned to the viewport end and
the history-load transition issues one immediate `scrollToIndex` call for the
last message with `align: "end"` and `behavior: "auto"`.

History loading does not enter a separate recovery phase, cover the rendered
conversation with an overlay, or run the generic multi-attempt bottom recovery
loop. Late image, Markdown, or tool-card layout changes may be handled by
Virtuoso's normal layout behavior, but they do not trigger custom repeated
scroll corrections. User-requested bottom scrolling, streaming follow output,
external navigation, and unexpected top-jump recovery retain their existing
paths because they are not history initialization.

Empty and failed histories perform no one-shot scroll. A missing Virtuoso ref
simply skips the initial command; `initialTopMostItemIndex` remains the mount
fallback and no timer or animation is started.

## Error handling and concurrency

- `asyncio.gather` operations are request-scoped; a failure preserves the
  endpoint's existing failure status rather than returning partial data.
- Cache in-flight tasks are removed after success or failure. A failed settings
  load is never cached.
- Settings invalidation is idempotent and safe before service initialization.
- History request IDs, abort signals, and SSE generations remain the authority
  for suppressing stale updates.
- Timing instrumentation records phase duration in `finally` paths without
  logging payloads or exception text.
- Atomic owner-scoped writes use matched documents, not modified documents, to
  distinguish authorization from an idempotent update.

## Test strategy

Every production change follows red-green-refactor.

Backend tests cover:

- concurrent session/favorites and count/page start barriers;
- favorites-only predicate ordering;
- owner-scoped UUID and legacy ObjectId mark-read, idempotent success, 404,
  and 403;
- concurrent feedback reads and failure propagation;
- team `$facet` totals, preference ordering, pagination, and zero persona query
  for an empty page;
- settings cache hit, shared in-flight miss, deep-copy isolation, local and
  pub/sub invalidation, and failed-load retry;
- active legacy/chunk projections excluding non-user data before Python
  assembly;
- compact message-chunk transport preserving exact reconstructed output,
  semantic event boundaries, and final replay timestamps;
- terminal and mixed-storage full-history equality, ordering, filters, limits,
  recommendations, and snapshot transition behavior; and
- `Server-Timing` names and absence of sensitive values.

Frontend tests cover:

- one session-detail request per direct navigation and sidebar selection;
- title publication from the current history request and stale-request
  suppression;
- no SEO polling request;
- one global settings request per authenticated generation;
- zero session-list requests from closed/collapsed surfaces and bounded
  pagination requests from visible surfaces;
- compact history requested only by chat hydration and exact raw-versus-compact
  reconstruction equality;
- exactly one non-animated last-item alignment after history commits;
- no history recovery overlay or history-specific multi-attempt loop;
- user-requested bottom scrolling, unexpected top-jump recovery, and empty
  history behavior remain unchanged; and
- complete message reconstruction with existing race and SSE tests unchanged.

Focused tests run after each TDD cycle. Final verification runs the affected
backend suites, affected frontend suites, frontend lint and production build,
then `make check-all`. A live authenticated deployment check compares the
browser's total duration, `X-Process-Time`, and `Server-Timing` values before
and after deployment. Repository verification cannot by itself certify the
production database or proxy latency.

## Success criteria

- Complete history has the same user-visible messages, parts, ordering, and
  active-run replay behavior as before.
- One navigation produces only the history loader's session-detail request;
  SEO produces none.
- The active-run snapshot transfers only its user message from the active
  trace while completed traces remain complete.
- Terminal history transports consecutive message chunks compactly while
  reconstructing byte-for-byte identical message content and semantic parts.
- Session page/count and feedback item/count/stats execute in one concurrent
  phase where their predicates allow it.
- Team total and page data come from one aggregation query.
- Repeated settings reads avoid MongoDB until an explicit local or remote
  invalidation.
- Real messages appear immediately after history reconstruction and receive one
  non-animated last-item alignment without a visible recovery phase.
- Hidden/closed frontend surfaces issue no data requests, duplicate settings
  triggers coalesce, and speculative list pages wait until the history critical
  path is complete.
- Focused tests, frontend build/lint, and `make check-all` pass, with any
  environment-only limitation reported separately.

## Non-goals

- History pagination, truncation, or progressive partial rendering.
- A new bootstrap endpoint or GraphQL layer.
- Redis history caching or materialized conversation snapshots.
- Changing authentication, RBAC, session visibility, team ownership, or
  settings permission policy.
- Tuning production MongoDB topology, storage class, region placement, or
  proxy configuration without deployment evidence.
