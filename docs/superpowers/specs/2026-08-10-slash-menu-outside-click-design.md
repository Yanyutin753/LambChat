# Slash menu outside-click dismissal design

## Goal

Close the rich composer slash-command menu when the user presses any element
outside the menu. Preserve the typed slash token and allow the clicked control
to receive the same interaction normally.

## Behavior

- A mouse press inside the slash-command menu does not dismiss it before the
  selected item runs.
- A mouse press anywhere outside the menu, including elsewhere in the rich
  composer, dismisses the menu.
- Dismissal leaves the typed `/...` text unchanged.
- The dismissed token stays suppressed until its text changes or the editor no
  longer has a valid slash trigger. Moving the caret within the unchanged token
  must not reopen the menu. Escape uses the same stable suppression behavior.
- Existing keyboard navigation, Escape dismissal, selection, positioning, and
  accessibility behavior remain unchanged.

## Implementation

`SlashDropdownMenu` owns the portal element reference, so it will register a
document-level `mousedown` listener only while open. The listener ignores
events whose target is inside the portal menu and invokes a new `onDismiss`
callback for every other target. The effect will depend on both `open` and
`onDismiss`, ensuring a still-open menu always invokes the callback for the
latest slash context. It will remove the listener when the menu closes,
re-registers, or unmounts.

`SlashCommandPlugin` will implement `onDismiss` through the same state transition
as Escape: store the current stable token identity in `dismissedTokenRef`, then
clear the slash context. The identity consists of the text node, slash start,
and complete slash-word text, independent of the caret position within that
word. Editing the token changes the identity and allows matching to resume;
selection movement alone does not. Keeping token suppression in the plugin
prevents an editor selection update from immediately reopening the same
unchanged token.

No backdrop will be introduced, because outside controls must still receive the
original press. No shared click-outside hook will be added for this isolated
behavior change.

## Testing

A focused jsdom component test will verify:

- an outside `mousedown` calls `onDismiss`;
- a `mousedown` inside the portaled menu does not call `onDismiss`;
- the document listener is inactive while the menu is closed and is cleaned up
  when the component unmounts.

Rich composer integration tests will also verify:

- typing `/wri`, pressing elsewhere in the editor, and moving the selection
  within that unchanged token closes the menu, keeps it closed, and preserves
  the exact text;
- pressing and clicking a real outside button both dismisses the menu and lets
  the button handler run;
- the existing portaled-menu option test remains green, proving an internal
  `mousedown` still applies the selection before dismissal.

Focused tests run first, followed by the relevant rich composer test group and
the frontend build.
