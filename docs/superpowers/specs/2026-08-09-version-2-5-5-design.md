# LambChat 2.5.5 Version Bump Design

## Goal

Prepare the repository metadata for LambChat `2.5.5`, commit the scoped changes,
and push the current `main` branch.

## Scope

Synchronize every release-bearing application version to `2.5.5`:

- Python package metadata and its `uv.lock` package entry.
- Frontend package metadata.
- Tauri configuration and Rust package metadata.
- Android `versionName` and monotonically increasing `versionCode` (`255`).
- iOS `MARKETING_VERSION` in both build configurations.
- Project citation metadata: set `version` to `2.5.5` and `date-released` to
  `2026-08-09`.
- A `## v2.5.5 (2026-08-09)` entry at the top of `CHANGELOG.md`, summarizing
  user-visible changes since the `v2.5.4` tag.
- The approved design and implementation plan that document the scoped release
  metadata change and its verification.

Unrelated internal schema versions, protocol versions, test fixtures, historical
documentation, and existing changelog entries remain unchanged.

## Implementation

Use direct, minimal edits to the existing metadata files. `uv.lock` is updated
only where it records the LambChat package version; dependency versions and
resolution data must not change. The repository does not track a Cargo lockfile,
so none will be created. The changelog groups the meaningful commits
since `v2.5.4` into concise feature, fix, refactor, and test/infrastructure
sections rather than reproducing the raw commit list.

## Validation

Run a repository-wide targeted search to prove all current release-bearing
locations use `2.5.5` and that stale `2.5.3`/`2.5.4` values remain only in
historical or non-release contexts. Parse JSON/TOML metadata where practical,
run the existing version-route tests, and inspect the final diff for scope.

## Delivery Boundaries

Create one scoped version-bump commit, including the approved design and
implementation plan, and push the current `main` branch. Do not create a
`v2.5.5` tag, publish a GitHub release, or manually trigger release workflows.
