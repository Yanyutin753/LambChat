# Native updater version binding Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Publish v2.15.3-dev.2 whose Windows/macOS updater signatures match the complete announced version.
**Architecture:** Sign the final updater assets with Tauri CLI --app-version; reject inconsistent manifests before publication. Verify with the actual tauri-plugin-updater and run isolated native installation checks.
**Tech Stack:** Existing Python, Tauri/Rust, GitHub Actions, PowerShell.
**Spec:** User request to fix updating, add verification tests, merge main and release dev.2; AGENTS.md and CLIENT.md.

## Global Constraints

- Preserve the five existing dirty style/test files, current branch and user data; no stash or worktree.
- Core platform version remains 2.15.3; Android versionCode 21503002 and iOS build 2.
- Never overwrite ready dev.1 or disable signed-version verification.
- All local validation uses scripts/run_validation.py with one worker/job.
- Tag only a main merge commit after CI; keep stable channel unchanged.

## Review Focus

- Core-only signatures must fail for a dev announcement on all three updater platforms.
- Full dev signatures must pass native verification; payload tampering and wrong dev number must fail.
- Same-core dev.1 to dev.2 must replace binaries, preserve app data and avoid update loops.
- Stable manifests must retain compatibility with existing canonical signature names.
- Missing/malformed signatures or incomplete platforms must never produce a ready manifest.

## Task 1: Signing and publication contract

- [x] Add failing Python cases for version mismatch, malformed/missing metadata and valid stable/dev versions.
- [x] Run focused RED, add strict manifest validation and full-version signing of canonical final artifacts.
- [x] Bump platform build numbers and document the invariant.

## Task 2: Native verification and installation gates

- [x] Add public, test-only signer fixtures and a mock-runtime harness using actual Update.verify/install.
- [x] Observe rejection of dev.1's core-only signature, then run valid/invalid native cases.
- [x] Add Windows stable/dev.1 installation regression and macOS temporary App replacement checks.
- [x] Run these gates for Windows and both macOS architectures before upload/readiness.

## Task 3: Integration and release

- [x] Complete all changes, review, then serialize focused/full tests, lint/build and hooks.
- [x] PR develop (#961), validate staging, PR main (#962), wait exact-source CI, tag v2.15.3-dev.2 at 4c3b9cca4e68e22f550f31150d8c736f4de547cf.
- [ ] Wait all platform/native/signature gates; verify published signatures, channels and actual download validation.

## Release-gate correction

- Both macOS architectures passed native upgrades from v2.15.2 and dev.1 in run 39411638244.
- The Windows gate initially compared the NSIS application with the portable EXE. Tauri patches `__TAURI_BUNDLE_TYPE_VAR_UNK` to `..._NSS` while packaging and restores the portable EXE afterwards, so those hashes differ by design.
- Run 39418714981 demonstrated that the installed program equals the real NSIS payload, with successful native installation, data preservation and daemon startup. The corrected gate authenticates the candidate before extracting that payload as its hash reference.
- [ ] Promote the corrected verification and retry the still-unready dev.2 from the protected main workflow. Keep the tag and all product builds/signing manifests bound to the original source; pin the repaired validation to the workflow commit. Never overwrite a ready marker or tag.
