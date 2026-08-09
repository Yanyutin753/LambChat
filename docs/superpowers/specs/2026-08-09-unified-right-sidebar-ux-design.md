# Unified Right Sidebar UX Design

## Goal

Make every right-side panel in LambChat feel like one predictable workspace. A
user should be able to inspect content, edit an object, follow a subagent, and
return to the prior context without panels overlapping, the chat becoming
unusable, or automatic behavior replacing work they deliberately opened.

The design covers both existing panel families:

- content and tool panels rendered through `ToolResultPanel`, including file
  previews, tool details, artifacts, message outline, scheduled tasks, thinking,
  and subagent activity;
- form and detail panels rendered through `EditorSidebar`, including agents,
  models, roles, users, teams, skills, MCP, channels, scheduled tasks, memories,
  marketplace previews, and personas.

Nested content inside either family is covered by the shared shell behavior but
does not become a separate top-level right panel.

## Current Problems

The two panel families currently manage width, overlays, history, and open state
independently. A 60% preview and a 30% editor can therefore be open together,
leaving about 10% of the app for the main workspace. The navigation sidebar then
uses a percentage threshold to compensate, rather than responding to the space
the user actually has.

The families also expose different interaction rules. A docked tool panel leaves
the main app interactive, while a docked editor places a blocking overlay across
it. Tool panels have partial history and view controls; editor panels do not.
Mobile panels mix bottom sheets and full-screen surfaces even when the tasks have
similar depth. Focus restoration, dialog semantics, touch target sizes, keyboard
resizing, and reduced-motion behavior are not consistently defined.

Only a running subagent currently auto-opens a content panel. Its suppression
logic knows about other content panels but not about open editor panels, so it
can still interrupt deliberate work in the other panel family.

## Considered Approaches

### 1. Surface polish only

Unify borders, shadows, headers, touch targets, and focus rings while keeping the
two state systems. This has low implementation risk but leaves overlapping
panels, inconsistent history, and disruptive automatic opening unresolved.

### 2. One coordinated right-panel lane

Keep the two specialized renderers, but put their lifecycle and presentation
under one coordinator. Only the top entry is visible; opening a new entry keeps
the previous entry mounted as navigable history. Shared responsive, focus,
resize, and automatic-opening policies apply to both renderers.

This is the chosen approach. It fixes the systemic problems without rewriting
every editor and preview into a new routing architecture.

### 3. Multi-tab, pinnable workspace

Turn the right side into a permanent IDE-style area with tabs and pinning. This
would support advanced comparison workflows, but introduces state persistence,
tab lifecycle, and small-screen complexity that the current product does not
need.

## Architecture

### Right-panel coordinator

Add a small external store for the top-level right-panel stack. Each mounted
panel registers a stable owner ID, a close callback, its opening trigger, whether
the opening was automatic, and its panel family. Registration makes that owner
the active entry. Earlier entries stay mounted but do not render their portal,
so local draft state and loaded preview state survive.

When the active entry closes or unmounts, the coordinator reveals the previous
registered entry. Only the active entry participates in layout compression,
scroll locking, Escape handling, or focus management. This removes the current
combined-width state entirely.

The coordinator exposes narrow operations rather than panel-specific content:

- register, update, and unregister an owner;
- determine whether an owner is active;
- determine whether a previous entry exists;
- close the active entry;
- report whether any deliberate panel is already open.

`EditorSidebar` and `ToolResultPanel` consume these operations internally, so
their existing call sites receive the behavior without duplicating coordination
logic. The persistent tool-panel store keeps its existing content-to-content
history. Its Back action has priority; after that history is exhausted, Back
returns through the shared cross-family stack.

### Responsive presentation policy

The coordinator has only one visible lane, and the shared panel hook derives one
of three presentations from the viewport:

- **Docked** at 1200px and above: the panel reserves space on the right and the
  main workspace remains interactive.
- **Overlay** from 640px through 1199px: the panel overlays the right side with a
  dimmed backdrop instead of squeezing the main workspace below a usable width.
- **Full screen** below 640px: every top-level right panel uses the available
  safe-area viewport. Long forms and previews no longer alternate unpredictably
  between a short sheet and a full-screen surface.

Presentation changes while a panel is open preserve its content and history.
Docked panels use no modal backdrop. Overlay and full-screen panels block the
background and use modal focus behavior.

### Width and navigation behavior

Preview and editor widths remain separate preferences because their content
needs differ. Defaults become less aggressive: approximately 48% for rich
content and 34% for forms. Stored values are sanitized and clamped against both
panel minimum width and a minimum usable main-workspace width. A stored width
from a larger display must not break a smaller display.

The resize rail becomes an accessible separator:

- pointer dragging gives immediate visual feedback;
- Left and Right arrows adjust in small steps, with Shift for larger steps;
- Home restores the panel-type default;
- double-click also restores the default;
- ARIA value attributes describe the current size.

The left navigation collapses temporarily only when the actual remaining docked
workspace width is below its usability threshold. This temporary state is never
persisted. A manual user override lasts for the current right-panel stack and is
cleared when the stack closes. Overlay and full-screen panels never change the
left navigation state.

## Interaction Rules

### Opening and navigation

- A deliberate user action always wins over automatic behavior.
- Opening a new top-level panel makes it the only visible right panel.
- If another panel was open, Back is visible and returns to it without losing
  its draft, scroll position, or already-loaded content.
- Escape closes only the active entry. It never closes multiple hidden entries
  through competing document listeners.
- Opening the same logical persistent content toggles it closed instead of
  adding duplicate history.
- Route or parent-state changes may unmount stale entries; the next valid entry
  then becomes active automatically.

### Automatic subagent opening

Automatic opening remains available as a convenience, but follows an
interruptibility policy:

- desktop only;
- running subagents only;
- at most once for each subagent run;
- only when no deliberate right panel is open;
- never replaces or covers a panel the user selected;
- closing an auto-opened panel suppresses reopening for that run;
- manual opening remains available after suppression;
- automatic opening does not steal keyboard focus.

Suppression and the once-per-run marker are keyed by the subagent panel key, not
one global boolean shared by unrelated runs.

### Header and actions

Both panel families use the same information order: Back, icon/status, title and
subtitle, contextual actions, view action where supported, and Close. Header
controls use the shared toolbar button primitive.

On touch layouts, every control has at least a 44 by 44 pixel hit area and at
least 8 pixels of separation where adjacent actions could be confused. Long
titles truncate visually while retaining an accessible full label. Loading and
status changes are exposed without moving the action controls.

Center/full-screen actions remain available only for content that supports those
views. Editors do not gain decorative view modes solely for visual parity.

### Focus, semantics, and motion

The docked presentation is a labelled complementary region and does not trap
focus. Overlay and full-screen presentations use labelled dialog semantics,
contain focus, and make the background inert. A deliberate opening moves focus
to the panel's first meaningful control; an automatic opening does not.

Closing returns focus to the element that opened the active entry when that
element still exists. Back returns focus within the restored panel. All icon
buttons have localized accessible names and visible `focus-visible` treatment.

Opening, closing, resizing, and presentation transitions honor
`prefers-reduced-motion`. Content remains visible while presentation changes;
the existing delayed-opacity loading treatment must not blank already-ready
content during a resize or breakpoint change.

## Data and Event Flow

1. A caller sets an editor open or requests persistent content as it does today.
2. The shared renderer registers its stable owner and captures the current
   trigger element.
3. The coordinator promotes that owner and notifies both panel renderers and the
   app shell.
4. Only the active owner invokes the shared panel hook with `open: true`.
5. The hook selects docked, overlay, or full-screen presentation and applies the
   corresponding layout, scroll, focus, and width policy.
6. The app shell derives temporary left-navigation collapse from the active
   docked panel's measured width and current viewport.
7. Close, Back, unmount, or route change removes the active entry; the
   coordinator restores the next valid entry and focus target.

Width changes use the existing right-panel width-change event so the app shell
can recalculate without coupling to either renderer. The event payload should
include the active panel family and effective docked width, avoiding DOM queries
that add two unrelated percentages.

## Failure and Edge Handling

- Invalid or obsolete stored widths fall back to the relevant default and are
  rewritten only after a valid user resize.
- If an opener unmounts, focus falls back to the restored panel or the main
  application landmark.
- A panel whose parent closes while hidden unregisters cleanly and is skipped by
  history.
- Multiple close requests are idempotent; callbacks execute at most once for a
  stack transition.
- A breakpoint change during pointer resize cancels the resize safely and clears
  cursor and selection overrides.
- Fullscreen document APIs still take precedence over Escape so the browser can
  leave native fullscreen before the panel closes.
- Existing content errors stay inside their panel; the shared shell must not
  convert a failed preview into an empty or closed workspace.

## Testing Strategy

Use TDD for each behavior group.

### Coordinator unit tests

- only one registered owner is active;
- closing or unmounting the active owner reveals the prior valid owner;
- duplicate registration does not duplicate history;
- automatic entries cannot displace deliberate entries;
- close callbacks and focus targets are handled idempotently.

### Presentation and width unit tests

- viewport ranges select docked, overlay, and full-screen modes;
- stored widths are parsed and clamped against panel and main-workspace minimums;
- left navigation collapses from available pixels only in docked mode;
- user override and automatic restoration apply to one panel stack;
- keyboard resize and reset produce valid widths.

### Shared component tests

- both renderers register with the coordinator and render only while active;
- Back crosses tool history and then cross-family history correctly;
- Escape affects only the active panel;
- docked surfaces are non-modal; overlay/full-screen surfaces are modal;
- manual close restores focus and automatic open does not steal it;
- buttons expose localized names, visible focus styles, and mobile touch sizes;
- reduced-motion removes nonessential entrance animation.

### Auto-open tests

- one running subagent auto-opens once on desktop when the lane is empty;
- mobile, completed, failed, previously opened, dismissed, and occupied-lane
  cases do not auto-open;
- manual opening still works after automatic suppression;
- an open editor counts as an occupied deliberate lane.

### Regression and integration checks

Run focused Vitest tests first, then the full frontend test suite, lint, and
production build. Validate representative consumers from every group at desktop
wide, desktop compact, and mobile widths: a tool result, file preview, outline,
subagent, model editor, skill editor, MCP detail, scheduled-task form, memory
detail, and persona preview. Verify light/dark themes, keyboard-only operation,
safe areas, and no combined right-panel compression.

## Non-goals

- No persistent tabs, pinning, split comparison, or drag reordering.
- No rewrite of individual form or preview content unrelated to its shell.
- No change to backend APIs or stored domain data.
- No visual rebrand; existing theme tokens and shared primitives remain the
  source of color and typography.
