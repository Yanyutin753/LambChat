# Rich composer file paste repair design

## Problem

The textarea-to-Lexical composer migration removed the `usePasteHandler`
integration that uploaded files from `clipboardData.files`. The new
`LongTextPastePlugin` deliberately declines clipboard payloads containing files,
but no other Lexical plugin handles them. As a result, pasting screenshots,
images, or other files into the chat composer does nothing.

## Desired behavior

- Restore the previous file-paste behavior for every file type supported by the
  existing upload flow, including images.
- When a clipboard payload contains one or more files, prevent the browser's
  default paste behavior, validate the attachment count, and upload all files.
- When the same clipboard payload also contains text or HTML, files take
  precedence and the accompanying text is not inserted. This matches the former
  textarea behavior.
- A rejected attachment-count validation consumes the file paste without
  inserting fallback text or starting an upload.
- Text-only paste, including existing long-text conversion, remains unchanged.
- The normal and expanded composer layouts use the same behavior because they
  share one Lexical editor instance.

## Technical approach

Add a focused Lexical file-paste plugin and register it alongside the existing
composer plugins. The plugin handles `PASTE_COMMAND` at high priority, inspects
`clipboardData.files`, and returns `false` immediately when there are no files so
Lexical and `LongTextPastePlugin` retain ownership of text paste.

For a file payload, the plugin prevents the default event, invokes the supplied
attachment-count validator, and forwards the original file collection to the
existing `uploadFiles` callback only when validation succeeds. `ChatInput` passes
the same `validateCount` and `uploadFiles` functions already used by drag-and-drop
and the attachment picker. File category detection, image compression, size
validation, upload progress, errors, and attachment rendering therefore remain
inside `useFileUpload` and do not change.

Expose the two callbacks through a small `filePaste` option on
`RichChatComposer`; do not restore textarea event handling or add a second upload
implementation.

## Event ordering

The file-paste plugin owns any clipboard payload containing files and reports the
Lexical command as handled. The long-text plugin continues to ignore file
payloads and handles only text/HTML. This preserves file-first behavior without
making plugin registration order observable.

## Testing

Add editor-level Vitest coverage that proves:

- a pasted image prevents default behavior and reaches the upload callback;
- multiple pasted files are forwarded together;
- a clipboard payload containing both a file and text uploads only the file;
- failed count validation prevents upload while still consuming the paste;
- text-only paste is not intercepted by the file plugin.

Run the focused rich-composer paste tests, related chat input tests, the complete
frontend Vitest suite, frontend lint, and the production build.

## Scope

This repair changes only paste routing in the rich composer. It does not change
upload APIs, attachment limits, accepted file types, long-text thresholds,
message serialization, drag-and-drop behavior, or attachment UI.
