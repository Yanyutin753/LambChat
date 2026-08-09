# Rich chat composer design

## Summary

Replace the chat textarea with a plain-text-first Lexical composer. Normal text,
line breaks, and Markdown remain ordinary editable text. Two non-editable inline
nodes add the requested rich behavior without introducing a formatting toolbar:

- a file-reference node for long pasted text converted into a `.txt` attachment;
- a skill-reference node for a Skill selected through the explicit slash-command
  flow or the Skill selector.

The nodes are part of the document flow, can be navigated around with the caret,
and synchronize with the attachment and per-run Skill state.

## User experience

### Normal writing

- The editor remains visually and behaviorally text-first.
- Typing, selecting, copying, pasting short text, line breaks, Markdown, IME
  composition, and send shortcuts retain their current behavior.
- No bold, italic, list, link, heading, or WYSIWYG toolbar is introduced.
- Inline nodes are atomic: their label cannot be partially edited, but the caret
  can move before or after them.
- Backspace or Delete removes a selected adjacent node as one unit.

### Long-text paste

- A plain-text or HTML-to-Markdown pasted fragment longer than the existing
  threshold is the only content written into the generated `.txt` file.
- Text already in the composer remains editable in place.
- The pasted selection is replaced at its exact document position by a
  file-reference node.
- With a non-collapsed selection, the selected content is replaced using normal
  paste semantics.
- The existing attachment card also remains visible above the composer.
- Expanded mode keeps the current policy of accepting long editable text without
  automatic conversion.

### File-reference node

- The node uses the current theme primary color, a file icon, readable label,
  visible keyboard focus, and states for uploading, ready, and failed.
- The label is `引用文件：<filename>` in Chinese and uses equivalent localized
  copy in every existing locale.
- Clicking a ready node opens the existing attachment preview.
- A failed node offers retry and remove actions. Retry reuses the locally cached
  file rather than reconstructing content from rendered text.
- Removing either the node or its attachment card removes the other from the
  active draft.
- Undo restores both the node and attachment-card state without re-uploading.
- Ordinary manual file, image, audio, and video uploads keep their current card
  behavior in this delivery. The node and command APIs remain generic so a later
  explicit "reference in composer" action can reuse them without an editor
  migration.

### Skill-reference node

- Selecting a Skill inserts the existing gradient Skill Chip at the current
  caret and removes the typed slash-command query.
- The caret lands after the inserted node so writing can continue immediately.
- A Skill may occur at most once in one draft. Re-selecting an existing Skill
  focuses its node instead of duplicating it.
- Removing the node disables that Skill for the current run; undo restores it.
- The toolbar Skill selector inserts at the most recent editor selection.
- Clicking a Skill node opens the existing Skill selector/details flow.
- The separate `ChatInputRunSkillsBar` is removed after feature parity is proven.

### Slash-command trigger

The Skill popup is explicitly invoked by a command slash, not by every slash in
the document.

- Trigger at the start of the document or immediately after whitespace/newline.
- Keep the popup active only while the caret remains inside the command token.
- Filter commands and Skills using characters typed after `/`.
- Arrow keys move the highlighted option; Enter or Tab inserts it; Escape closes
  the popup without destroying unrelated text.
- Slashes inside URLs, words, or existing text do not open the popup. If a
  command token gains a second slash (for example while typing a path), the
  popup closes and the text remains untouched.

## Technical approach

### Editor foundation

Use Lexical `0.49.x` with its official React bindings and a minimal plain-text
configuration:

- `LexicalComposer` owns one editor instance and one document state.
- `PlainTextPlugin`, `HistoryPlugin`, and `OnChangePlugin` provide the base
  editing surface.
- Custom commands and plugins replace textarea-specific cursor arithmetic.
- The normal and expanded surfaces are two layouts for the same editor instance;
  only one `ContentEditable` root is active at a time. Switching layout preserves
  document state and restores the latest selection.

Do not use `contentEditable` mutation outside Lexical or keep a second textarea
implementation as a long-term fallback. A short migration boundary may translate
legacy strings into the initial editor document.

### Document nodes

`FileReferenceNode` is an inline decorator node with these serialized fields:

- `version`;
- `referenceId`, a stable client-generated identifier;
- `fileName`;
- `category`;
- `status` (`uploading`, `ready`, or `failed`).

`SkillReferenceNode` is an inline decorator node with:

- `version`;
- `skillName`;
- `tags` used by the existing visual treatment.

Both nodes implement JSON import/export and plain-text clipboard export. Unknown
or invalid node versions degrade to readable text instead of making the draft
unloadable.

### Draft projections

The Lexical document is the source of truth for content order and active rich
references. A serializer produces three projections:

1. `message`: normal text plus a readable `[引用文件：<filename>]` marker at
   each file node position;
2. `attachments`: ready attachment records referenced by active file nodes plus
   ordinary card-only attachments;
3. `enabledSkills`: unique Skill names in document order.

Local node metadata, upload state, and cached source text are stripped before the
API request. Sending stays disabled while any active referenced attachment is
uploading or failed.

### Attachment registry and undo

Use a draft-scoped registry keyed by `referenceId` to hold the generated `File`,
upload handle, final `MessageAttachment`, and active state.

- Inserting or restoring a file node marks the registry entry active.
- Removing the node marks it inactive and excludes it from display and submit,
  but retains its local/uploaded resource while the draft history can undo it.
- Removing the attachment card dispatches the same editor command as deleting
  the node.
- Undo/redo reconciliation derives active state from the editor document.
- Inactive remote uploads are deleted when the draft is sent, cleared, or
  discarded. Active submitted attachments are retained by the existing session
  lifecycle.
- Upload failure keeps the registry entry and node in a retryable failed state.

### Existing feature migration

- Replace textarea offsets in mention and slash detection with Lexical range
  selection and text-before-caret helpers.
- Keep persona/team selection behavior unchanged: their command query is removed
  and the existing external selection callback runs.
- Replace `useTextareaResize` with content-based editor sizing while preserving
  the existing maximum height and expand affordance.
- Store a versioned editor JSON snapshot in input history. Existing string
  history entries import as plain text.
- `pendingInput` imports as plain text at the current document end.
- Selection-action prompts insert plain text at the current document end using
  an editor command.
- Drag-and-drop and ordinary file paste retain their current upload behavior.

## Accessibility and visual rules

- Use semantic labels in every locale; never communicate node type or failure by
  color alone.
- Provide visible focus and selected states with at least the existing theme
  contrast requirements.
- Preserve native text selection semantics around nodes and announce insertion,
  upload failure, retry, and removal through an ARIA live region.
- Keep node targets usable on touch screens without increasing line height enough
  to make ordinary paragraphs feel like a form toolbar.
- Respect reduced-motion settings; only short color/opacity transitions are used.

## Error handling

- Failure to initialize Lexical reports through the application error boundary
  and preserves the last serialized draft snapshot.
- A declined attachment-count validation leaves the pasted text editable rather
  than discarding it.
- An upload failure leaves a retryable node and never implies the file will be
  sent.
- A missing attachment-registry entry renders the file node as failed and allows
  removal; it is excluded from submission.
- Invalid stored JSON falls back to the stored plain-text projection.

## Testing strategy

### Pure tests

- slash trigger boundaries for document start, whitespace, URLs, words, and
  paths;
- document serialization into message, attachments, and unique Skills;
- versioned history migration and invalid snapshot fallback;
- node-to-registry reconciliation and inactive-resource cleanup decisions.

### Editor behavior tests

- ordinary typing and Markdown remain plain text;
- IME composition does not submit or corrupt adjacent nodes;
- long plain-text and HTML paste upload only the pasted fragment;
- insertion and selection replacement preserve surrounding prose;
- left/right navigation, Backspace/Delete, undo, and redo around both node types;
- slash popup keyboard control and exact query replacement;
- Skill selector insertion at the latest caret and duplicate prevention;
- upload ready, failed, retry, preview, removal, and undo states;
- attachment-card removal removes the matching node;
- normal/expanded layout switching preserves document, selection, and nodes;
- legacy string history and `pendingInput` import correctly.

### Integration verification

- focused Vitest suites during TDD;
- complete frontend tests;
- ESLint and TypeScript/Vite production build;
- manual browser checks on desktop and narrow mobile viewport for IME, touch,
  scrolling, focus, paste, and expanded composer transitions.

## Delivery boundaries

Included:

- Lexical plain-text composer foundation;
- file-reference nodes for converted long-text paste;
- inline Skill nodes and explicit slash popup;
- attachment/Skill synchronization, undo, serialization, history migration, and
  normal/expanded composer parity.

Excluded:

- general WYSIWYG formatting or a formatting toolbar;
- automatic inline references for every manually uploaded attachment;
- collaborative editing;
- backend attachment-schema changes beyond accepting the existing serialized
  message and attachment payloads.
