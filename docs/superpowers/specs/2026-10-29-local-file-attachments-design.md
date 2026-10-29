# Desktop local file attachments

The user selected direct references to original files, without copying. Desktop drag/drop and the native file picker use the same attachment flow. In a desktop session bound to this machine's local sandbox, adding a file records its absolute path and machine identity without uploading or hashing bytes. Existing local sandbox absolute-path operations keep their execution approval policy. Cloud sessions and web clients upload files through the existing cloud compression pipeline.

## Approaches

- Direct references (selected): immediate attachment, no duplicate disk or network I/O; moving/deleting the original makes the reference unavailable, and agent edits affect the original.
- Workspace copies (rejected): stable snapshots, but copies large files and changes the user's intended original-file workflow.
- Always upload (rejected): preserves cross-device URLs but repeats the slow local upload/download cycle.

## Boundaries

Local references carry a machine ID and never masquerade as HTTP URLs or object-store keys. Submission rejects a different machine, cloud/no-sandbox mode, and unknown/offline target machines. A reference does not grant new daemon permissions. Model context presents the path as untrusted data and uses existing read/edit/image tools; image inspection still transfers necessary bytes to the model and retains server compression.

Native reads used to promote a draft to cloud resolve only opaque receipts created by native selection/drop. Read chunks are bounded and detect changes during upload. Local card clicks reveal the selected original in the system file manager. Missing files and references on other devices show an error instead of empty cloud previews.

Switching the draft to cloud (or an execution environment unable to use this machine) uploads its local references before allowing send. Previously sent messages are not batch-uploaded. Clipboard blobs without a real path retain the existing upload flow. Mobile clients retain uploads because they do not host this desktop daemon.

Preserve account isolation, draft restoration, follow-up/steer attachments, cancellation, upload limits, five locales, current shared branch and shared validation lock. No new dependencies or daemon protocol changes. This change is separate from already published dev.3.
