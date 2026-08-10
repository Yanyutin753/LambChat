# Model Selection Refresh Priority Design

## Problem

Refreshing chat can produce a different effective model because model selection is
assembled from several asynchronously loaded sources without one explicit priority
contract. The current default resolver validates the locally stored user preference,
but when that preference is absent or unavailable it chooses the first available
model instead of the administrator-configured initial model. Session restoration is
handled separately, which makes the complete refresh behavior difficult to verify.

## Required Priority

For an existing session, resolve the effective model in this order:

1. The model saved in the session's `agent_options`.
2. The authenticated user's personal default-model preference.
3. The initial model selected in system settings.
4. The first model in the available-model list as a final compatibility fallback.

For a new session, the first tier is absent, so resolution starts with the user's
personal preference.

Every candidate must resolve to one model in the current available-model list. A
deleted, disabled, or inaccessible candidate falls through to the next tier. Model
IDs are authoritative; a stored model value is a compatibility fallback for older
data or a changed ID only when it identifies exactly one available model. An
ambiguous value match falls through to the next priority tier.

## Data Sources

- Session preference: `agent_options.model_id` and `agent_options.model` returned by
  history/session restoration.
- User preference: `defaultModelId` and `defaultModel`, restored from authenticated
  user metadata into local storage before protected chat routes render.
- System preference: `default_model_id` returned by the available-model API. The
  corresponding model value is derived from the same available-model response.
- Availability boundary: the model list already filtered by the current user's role
  access for the active agent.

The settings context must expose the system default model ID as well as its value so
the client does not infer identity from a potentially duplicated model value.

## Client State and Loading Behavior

Model resolution will live in the existing pure `modelSelection.ts` module. Its
inputs will name each candidate by provenance (`session`, `user`, and `system`) so
callers cannot accidentally substitute current transient UI state for a persisted
preference.

On a refresh of an existing session, the UI may render a temporary selection while
history is loading, but the restored valid session candidate becomes authoritative
when it arrives. Later completion of model or settings requests must not overwrite a
valid restored session selection. For a new session, user preference is selected
first and system preference is used only when the user has no valid preference.

Session restoration is authoritative over defaults, but not over a newer explicit
user action. The chat caller will track whether the user selects a model after a
particular history load begins. If so, a late restoration result from that load must
not overwrite the user's newer choice. Starting a different session load resets this
interaction marker for that new target session.

A deliberate in-session model choice remains the current runtime selection. Once a
message is submitted, the existing chat request/session metadata path persists that
choice in `agent_options`; after refresh it therefore qualifies as the session tier.
Changing the user's personal default affects new sessions and does not replace the
model of an existing session.

## Failure and Compatibility Behavior

- An ID/value mismatch uses the valid ID and its canonical current value.
- If an ID is unavailable, its paired legacy value may still resolve before falling
  through to the next tier, but only when exactly one available model has that value.
  Zero or multiple matches are unresolved.
- A session candidate that is no longer accessible does not block fallback to the
  user or system candidate.
- Empty or malformed stored strings are treated as absent.
- If the available-model request has not completed, preserve the best candidate
  identifiers without selecting a different fallback. Reconcile once availability
  is known.
- If no models are available, retain empty selection behavior and do not manufacture
  an invalid model ID.

## Scope

This change is limited to frontend model selection and settings context wiring. It
does not change model permissions, backend model configuration, user metadata
storage, or when ordinary session metadata is persisted.

## Test Strategy

Add focused Vitest coverage for the pure resolver before changing production code:

- valid session model wins over different user and system models;
- valid user preference wins when no session model exists;
- valid system initial model wins when session and user preferences are absent;
- invalid candidates fall through one tier at a time;
- IDs win over legacy values and always return the canonical available value;
- duplicate legacy values do not select an arbitrary model ID;
- unresolved model-list loading preserves candidates without choosing the first
  model prematurely;
- an empty available list returns an empty/compatible selection safely.

Add integration-oriented source or component coverage for the settings/context and
chat caller wiring so future changes cannot omit the system default ID or reorder the
three persisted tiers. Cover a user model selection made while history is loading so
a late restore cannot overwrite it. Run the focused tests, the complete frontend
test suite, lint, and frontend build.

## Acceptance Criteria

- Refreshing an existing conversation keeps its valid saved model.
- A new conversation selects the user's valid personal default model.
- Without a valid personal default, a new conversation selects the valid system
  initial model rather than the first arbitrary model.
- Deleted, disabled, or unauthorized models fall back according to the documented
  priority without leaving an inconsistent ID/value pair.
- Automated regression tests cover the priority and asynchronous reconciliation
  rules.
