# Optional Dev Update Channel Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline; user explicitly approved direct implementation and deployment.

**Goal:** Opt-in dev downloads and native updates without affecting stable users.
**Architecture:** Extend existing release selection, updater header and preference flow. Embed full release identity at build time; reuse native signature verification and package installers.
**Tech Stack:** FastAPI, packaging, React, Tauri updater, GitHub Actions.
**Spec:** ../specs/2026-10-16-dev-update-channel.md (approved 2026-10-16).

## Global Constraints

- Default stable; explicit device-local dev opt-in; no automatic downgrade.
- Preserve CI, artifact smoke and signature gates; dev manual GUI gate waived by user.
- No dependencies; tag-pinned downloads; one shared validation slot and one worker.
- Old dev.2 requires one manual reinstall; do not replace its tag.

## Review Focus

- dev.10 versus dev.9 and final versus same-core dev: version ordering tests.
- Partial release or invalid version: selector rejects before advertisement.
- Pending check during channel change: generation check discards stale response.
- Download/install channel change: store lock rejects changes while active.
- Explicit tag asset versus channel default: route tests keep tagged downloads exact.

### Task 1: Release selection and proxy

- [x] Add failing tests in tests/infra/test_github_client.py and tests/test_version_route.py for dev selection, readiness, ordering, default stable and header proxy.
- [x] Run targeted pytest via scripts/run_validation.py; confirm expected failure.
- [x] Add GitHubClient.get_channel_release(channel, force_refresh=False), channel-isolated caching and version route channel enum. Select ready dev-latest.json releases, stable latest.json releases for dev updater; retain stable legacy path.
- [x] Run targeted tests green.

### Task 2: Client channel and identity

- [x] Add failing tests for device preference default/persistence/busy lock, tag-pinned downloads and stale response rejection.
- [x] Embed RELEASE_TAG full version in Vite and Rust build; native comparator uses embedded identity.
- [x] Add shared channel store and selector to preferences/download page, five locale keys; route checks using header/query, guard late responses and lock during downloads/install.
- [x] Run focused frontend tests green.

### Task 3: Publish dev.3 safely

- [x] Add generator tests for dev-latest.json and no stable output; verify red.
- [x] Generate dev manifest only after all native jobs succeed, publish last as readiness marker. Set build number 3 and CI identity environment. Update AGENTS.md/CLIENT.md and changelog.
- [x] Run final pytest/frontend/lint/build through shared lock; review complete diff.

### Task 4: CI, deployment and release

- [x] Commit/push PR to develop, require green CI; staging deploy and smoke.
- [x] PR to main, require green CI; production deploy and smoke.
- [ ] Tag new v2.15.2-dev.4 at main merge; wait full native matrix and final publish.
- [ ] Verify stable isolation, dev API/manifest, tagged downloads and signatures; record runtime verification limits.
- [ ] Remove owned temporary resources and release validation lock.

Release recovery: dev.3 Windows asset publication failed because Python decoded UTF-8 GitHub metadata using Windows cp1252. Keep the existing tag immutable and leave its dev readiness marker absent; fix explicit UTF-8 decoding and ship dev.4 with incremented mobile build numbers.
