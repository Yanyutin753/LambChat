# Long-text paste content design

## Problem

When the composer already contains a draft and the user pastes more than the
long-text threshold, LambChat currently creates a text attachment from only the
pasted fragment. The existing draft remains outside that attachment, so opening
or restoring the attachment does not show the complete composed text.

## Desired behavior

- Build the converted attachment from the complete post-paste composer value:
  text before the selection, followed by the pasted text, followed by text after
  the selection.
- Preserve normal paste replacement semantics when the user has selected text.
- Clear the composer after a successful conversion because the complete value is
  represented by the attachment.
- Keep existing behavior when conversion cannot start: insert the pasted text
  into the composer normally.
- Apply the same behavior to plain-text and HTML-to-Markdown paste paths.
- Keep the expanded composer behavior unchanged; it continues to accept long
  text as editable input without automatic conversion.

## Implementation boundary

Add a small pure function that derives the post-paste value from the current
input, pasted text, and selection range. The paste handler will pass that complete
value to the existing long-text conversion callback. The conversion hook will no
longer accept a separate value to preserve in the composer.

No upload API, attachment schema, threshold, or backend behavior changes are
required.

## Error handling

If attachment count validation fails, a conversion is already in progress, or
the callback otherwise declines conversion, the paste handler falls back to its
normal insertion path. Existing upload error handling remains unchanged.

## Test coverage

- Existing draft before the cursor is included before the pasted fragment.
- Existing draft after the cursor is included after the pasted fragment.
- Selected text is replaced by the pasted fragment.
- The long-text conversion callback receives the complete post-paste value for
  both plain-text and HTML paste paths.
- Existing long-text conversion and frontend checks continue to pass.
