# Workspace preview E2E

All commands use the non-blocking shared validation lock; no parallel workers.

Local daemon previews are included in the existing full suite:

```sh
python3 scripts/run_validation.py uv run python scripts/e2e_local_sandbox.py
```

Cloud previews use the real local FastAPI server and its configured cloud provider.
Set `E2E_WORKSPACE_TOKEN` privately to the existing test session owner's JWT.
The script writes and removes only a unique fixture directory, connects with
`create=False`, and never changes platform settings or invokes an LLM:

```sh
python3 scripts/run_validation.py uv run python scripts/e2e_workspace_preview.py --session-id TEST_SESSION_ID
python3 scripts/run_validation.py uv run python scripts/e2e_workspace_preview.py --session-id TEST_SESSION_ID --image-mib 24
```

Coverage: a valid PNG over 3 MiB, a ZIP containing two images, Unicode names,
`./` paths, an empty binary file, missing-file errors, SHA-256 equality and ZIP
entry CRC checks. Each read prints elapsed seconds and byte count. The larger
case transfers a PNG over 24 MiB and ZIP over 48 MiB, within the current cloud
upload cap. Timings depend on provider/network and do not prove a fixed SLA.

Browser E2E runs through Codex's CUA runtime (no separate browser driver dependency).
Load `frontend/scripts/e2e-workspace-preview.cua.js` into that runtime and call
`runWorkspaceBrowserE2E(tab, {pngName, zipName})` with an already-open workspace
tree containing the test files and an expanded directory. It asserts actual DOM
icon/name positions at each depth, decoded image dimensions, and a completed ZIP
download. Check the returned download against the fixture SHA-256 and `testzip()`.
For a UI-only streamed fixture server, set `PANEL_PREVIEW_WORKSPACE_FIXTURES` to
a directory containing the generated fixtures and start `pnpm preview:panels`.
This server emits raw chunks with backpressure; it never contacts a cloud provider.
Run sequentially at 390, 768 and 1280 px, in light and dark themes; capture the
workspace tree and loaded image after each run. Browser fixture checks prove UI
only; run the cloud API E2E separately to prove real CubeSandbox transport.

Over-limit files must return an explicit error; increasing transport limits needs
a corresponding larger E2E fixture. New clients request `stream=true`: binary
bytes are transferred incrementally with no JSON/base64 overhead, while legacy
clients retain their existing JSON contract. Streams use the shared
`S3_INTERNAL_UPLOAD_MAX_SIZE` cap; size preflight and runtime byte counting protect
known/unknown lengths. Truncation, midstream failures and cancellation must fail
or close the source. Browsers hold a Blob for the current preview; switching files
aborts the old request and revokes its object URL.
