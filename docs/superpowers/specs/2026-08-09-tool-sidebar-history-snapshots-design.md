# Tool Sidebar History Snapshots Design

## Goal

Restore the right sidebar exactly when a user opens a nested tool or preview node and then navigates back. The restored node must keep its content, expansion state, and scroll positions even when the originating chat message has scrolled outside the virtualized message list. Pending tools must continue to stream and show their final result while the sidebar remains open or is later restored from history.

## User-visible contract

- Opening sidebar node B from node A records A before B replaces it.
- Returning from B to A restores A's latest content instead of an empty panel.
- Expandable sections, file-tree folders, and other `aria-expanded` controls return to their recorded state.
- Every scrollable region inside A returns to its recorded horizontal and vertical position.
- Restoration is applied before the panel content becomes visible, so users do not see a jump from the default state.
- A pending tool continues to show progress and receives its streamed result when its source message is outside the Virtuoso render range.
- The behavior covers generic tools, MCP tools, file and project reveals, block previews, and attachment previews that participate in sidebar history.
- Explicit close, session change, or page reload starts a new sidebar-history lifetime and discards stale snapshots.

## Root cause

The generic tool result panel is backed by `toolCallPanelStore`, but `ToolCallItem` currently deletes that entry whenever React unmounts the message item. Virtuoso intentionally unmounts messages outside its render range, so ordinary chat scrolling can erase the data used by an open sidebar. Because off-screen `ToolCallItem` instances are not rendered, later stream events also cannot repopulate the panel through that component.

Sidebar history currently stores only a restore callback containing a state object or React node. Navigating away unmounts the previous panel subtree. Restoring it creates a fresh subtree, which resets component-local expansion state and DOM scroll positions.

## Considered approaches

### 1. Live data cache plus generic view snapshots (selected)

Keep tool-call data independently of rendered chat rows and capture a panel's interactive DOM state when it enters history. Restore the state while panel content is masked. This preserves the existing sidebar lifecycle, avoids retaining expensive editors and previews in the background, and applies to existing panel types through one shared mechanism.

### 2. Keep every historical panel mounted

This preserves all React state automatically, but hidden document viewers, code editors, media, iframes, and subscriptions continue consuming memory and CPU. Long navigation chains would degrade the chat experience.

### 3. Lift every panel component's local state into typed stores

This gives explicit state ownership but requires invasive changes across every current and future tool panel. It is easy for a new expandable element or nested scroller to miss the persistence contract.

## Architecture

### Durable tool-call data

`toolCallPanelStore` becomes a cache whose entries are not deleted merely because a virtualized `ToolCallItem` unmounts. A message-level synchronization function traverses current message parts, including nested subagents, and refreshes cached tool-call records independently of which rows Virtuoso renders. The synchronization runs from the chat data owner when messages change, so `tool:start`, partial updates, cancellation, and `tool:result` all reach an open panel.

Cache cleanup follows the conversation lifecycle rather than the component lifecycle: switching sessions clears obsolete entries. This avoids retaining tool data indefinitely while preserving it during ordinary scrolling and sidebar navigation.

### Sidebar view snapshots

Each active right panel exposes its root and stable registry key to a shared snapshot registry. Immediately before `pushCurrentPanelToHistory` records the panel restore callback, it also captures:

- `scrollTop` and `scrollLeft` for the panel body and nested scrollable descendants;
- boolean state of `aria-expanded` controls and native `details` elements;
- stable locators based first on explicit snapshot keys and otherwise on deterministic DOM paths inside the panel root.

The history entry owns this immutable UI snapshot. On back navigation, the entry first restores its panel data, then makes the snapshot pending for that panel key.

`ToolResultPanel` consumes the pending snapshot during its first-paint mask. It restores expansion state through the controls' public interaction path, waits for the resulting layout, restores nested scroll positions, and only then reveals the content. A bounded layout retry handles lazy preview content whose scroll extent becomes available shortly after mount. Missing or changed elements are ignored individually so one stale locator cannot prevent the rest of the panel from returning.

### History lifecycle

Snapshots are scoped to the current in-memory sidebar history. Going deeper creates a new immutable entry; going back consumes the latest entry. Explicit sidebar close clears the whole chain. Session changes clear history, panel data, and pending snapshot work. A history restore never pushes another history entry.

## Data flow

1. Chat messages change because history loaded or a stream event arrived.
2. The chat data owner synchronizes all tool parts into `toolCallPanelStore`.
3. A user opens node A; its panel subscribes to the durable tool record where applicable.
4. The user opens node B from A.
5. Sidebar history captures A's restore callback and current view snapshot, then opens B.
6. The user presses Back.
7. History restores A's panel data and marks A's view snapshot pending.
8. A mounts with content hidden, applies expansion and scroll state, then becomes visible.
9. Later stream updates continue updating A through the durable store, regardless of Virtuoso visibility.

## Error handling and accessibility

- Snapshot capture and restoration are best-effort and never block opening or closing a panel.
- Invalid scroll values are clamped by the browser; missing elements are skipped.
- Expansion restoration uses actual buttons rather than mutating ARIA attributes, keeping React state and accessibility state aligned.
- Hidden first-paint content retains the existing busy indication and is revealed after restoration or after the bounded retry expires.
- Restored inactive panels are not kept mounted, so focus trapping and right-panel coordination remain unchanged.

## Testing

Tests will be added before production changes and will prove:

- unmounting a virtualized tool row no longer deletes the cached panel result;
- message-level synchronization updates a pending off-screen tool to success with its final result;
- nested subagent tool parts are synchronized;
- a history entry records and restores expansion plus nested scroll state;
- restoration replays expansion before scroll and tolerates missing nodes;
- back navigation restores the correct snapshot for multiple history nodes in LIFO order;
- explicit close and session change clear history and cached tool data;
- existing automatic-opening, panel registry, streaming, and right-panel coordination tests remain green.

## Non-goals

- Persisting sidebar navigation history across a full page reload.
- Keeping every historical preview mounted in the background.
- Changing the visual design or the existing automatic-open policy.
