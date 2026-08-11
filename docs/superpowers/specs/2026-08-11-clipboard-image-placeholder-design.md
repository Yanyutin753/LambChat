# Clipboard Image Placeholder Repair Design

**Date:** 2026-08-11
**Status:** Approved

## Problem

Some browsers, webviews, remote desktops, and clipboard managers expose a copied image as a virtual `File` whose filename is stale, MIME type is empty, and size is zero. The rich composer currently treats any non-empty `clipboardData.files` list as authoritative. `useFileUpload` then renders an attachment card before checking whether the file has bytes, so users can see a misleading historical filename such as `bpm_r5.bin` with `0 B` even though no usable image was supplied.

The same missing lower-bound validation affects chat file selection, page drag-and-drop, and scheduled-task attachments. The backend upload route also accepts a zero-byte stream if a client bypasses the frontend. Separately, an image copied as HTML with an embedded `data:image/...` source can fall through to long-text conversion and become a `.txt` attachment.

## Chosen Approach

Use three coordinated layers:

1. A shared frontend file validator rejects zero-byte files before temporary attachment state is created. Every consumer of `useFileUpload` receives the same behavior.
2. A clipboard normalizer prefers valid native files, recovers embedded `data:image/...` HTML into a real image `File`, and marks inaccessible image placeholders as handled errors so they cannot fall through to long-text conversion.
3. The backend rejects zero-byte uploads before deduplication or object storage writes.

This is preferred over a paste-only patch, which would leave drag-and-drop and file selection unsafe, and over a backend-only patch, which would still render a misleading local attachment card.

## Frontend File Validation

`useFileUpload` will expose one validation path used by `uploadFile` and `uploadFiles`. A file is invalid when `size <= 0`. Invalid files never create a temporary attachment, start hashing, call the check endpoint, or start an upload request.

The user receives a localized `fileUpload.emptyFile` message in all five existing locales. Batch uploads reject only invalid members and continue uploading valid members, matching the existing per-file handling of oversized files.

Upper-bound checks remain unchanged. A missing MIME type alone is not globally rejected because legitimate files may lack a browser-provided type; clipboard-specific logic handles the ambiguous zero-byte `.bin` case.

## Clipboard Normalization

A focused pure module will classify `DataTransfer` clipboard content and return one of:

- `files`: one or more non-empty native files, preserving their original names and types;
- `files`: a recovered image created from an embedded `data:image/<supported-type>;base64,...` HTML source;
- `invalid-image`: image markup or file placeholders exist, but no non-empty image bytes are available;
- `none`: no file or image payload exists, so normal text/HTML paste behavior may continue.

Native non-empty files take precedence over HTML. Zero-byte native placeholders do not block recovery from a valid embedded data image. Recovered image names use a deterministic `pasted-image.<extension>` format derived from the MIME type.

Remote `http(s)` images and `blob:` URLs are not fetched automatically. A blob URL copied from another document is generally unreadable in the receiving document, while arbitrary remote fetching would add privacy, SSRF, CORS, and authentication ambiguity. These cases produce the localized `fileUpload.clipboardImageUnavailable` message.

The rich-composer `FilePastePlugin` and legacy `usePasteHandler` both use the classifier. They consume `invalid-image` events and show the error instead of allowing the content to become a long-text `.txt` attachment. The long-text plugin remains responsible only for actual textual content.

## Backend Validation

The bounded spooling helper rejects an upload whose final byte count is zero with HTTP 400 and the stable detail `File is empty`. This occurs before hash lookup, deduplication, object-storage upload, and file-record creation. Because avatar and other upload flows have separate readers and semantics, this change is scoped to the general `/api/upload/file` attachment route that exhibits the bug.

## Error Handling and State

- Invalid clipboard placeholders never appear as attachment cards.
- Valid files in a mixed batch still upload when another member is empty.
- An inaccessible pasted image produces one toast and no text insertion, attachment card, hash worker, or network request.
- A valid embedded data image produces a normal image attachment and does not trigger long-text conversion.
- Backend rejection remains a final defense for non-browser and stale clients.

## Testing

Frontend unit tests cover the clipboard classifier for valid native images, zero-byte stale placeholders, embedded data images, inaccessible remote/blob image markup, and ordinary text. Hook/component tests prove that invalid files do not create attachment state or call upload APIs, mixed batches keep valid files, both paste paths consume invalid images, and embedded data images reach the file upload callback.

Backend tests prove that the shared `_spool_upload_file_limited` guard rejects empty general-file and avatar uploads while preserving existing bounded streaming behavior and purpose-specific error messages. Focused frontend and backend suites run first, followed by frontend lint/build and the relevant backend route suite. Full-suite results remain distinct from focused verification.

## Non-Goals

- Persisting or restoring draft attachments across browser restarts.
- Fetching arbitrary remote image URLs from pasted HTML.
- Changing content-hash deduplication for non-empty files.
- Refactoring unrelated avatar, feedback, skill, or profile upload flows.
