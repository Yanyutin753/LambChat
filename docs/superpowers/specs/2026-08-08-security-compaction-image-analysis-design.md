# Security, Compaction, and Image Analysis Repair Design

## Objective

Repair the confirmed credential exposure and stale model-reference defects, preserve the existing sandbox conversation-history fix, and make image analysis reject malformed image references before a model gateway receives them.

## Scope

This change covers four bounded areas:

1. Remove sensitive connection details from application and Feishu SDK logs.
2. Remove literal deployment credentials and document required local values without shipping usable secrets.
3. Clear the native-memory compaction model setting when its referenced model is deleted.
4. Validate image data URLs and add safe boundary diagnostics before invoking the configured vision model.

Credential rotation, deployed log deletion, and recovery of conversation messages that were never persisted are operational tasks. They are not performed by this code change.

## Security Logging and Deployment Configuration

Application startup must not log `REDIS_URL`. WebPush subscription and delivery logs may include the authenticated user ID, HTTP status, and exception class, but must not include subscription endpoints or exception text that can echo an endpoint.

The Feishu WebSocket SDK currently logs its credential-bearing connection URL at INFO level. LambChat will construct the SDK client at WARNING level and will log only the exception class for connection failures. Existing lifecycle messages that contain user IDs and retry counts remain available.

The current tracked `deploy/docker-compose.yml` Redis URL contains no embedded username or password, `.env.example` contains only local-development placeholders, and the current `origin` remote is a credential-free HTTPS URL. This work will verify those properties without introducing a new Redis authentication requirement, rewriting remotes, or rewriting Git history. Credentials found in the deployed environment or older history remain rotation targets.

## Deleted Compaction Model References

The model deletion route will retain its existing deletion, fallback-reference cleanup, role cleanup, and model-cache invalidation. It will additionally inspect `NATIVE_MEMORY_COMPACTION_MODEL_ID` through `SettingsService`. When the setting equals either the deleted model ID or the deleted model value, the route will set the setting to the intentional empty value using the service API.

Using `SettingsService.set` preserves the existing database-first configuration contract, refreshes the current process, and publishes the change to other instances. The existing compaction-model runtime fallback remains a second line of defense if a stale value is introduced through another path.

## Conversation-History Persistence

The existing sandbox `CompositeBackend` behavior that anchors `artifacts_root` at the sandbox work directory remains unchanged. Regression verification will cover the writable artifact root and surfaced E2B command diagnostics. No migration or fabricated recovery will be attempted for messages that failed to persist before the fix.

## Image Analysis Validation

Image analysis will validate every internally produced or caller-supplied data URL before model invocation. A valid value must:

- use the `data:` scheme;
- declare an `image/*` MIME type;
- include the `;base64,` delimiter;
- contain syntactically valid base64; and
- decode to non-empty bytes within the existing image-size limit.

Malformed data URLs will produce a stable tool error and will not invoke the model or enter the three-attempt retry loop. Ordinary HTTP(S), upload-storage, and sandbox file references will continue through their existing download and compression paths.

Safe diagnostics may record reference kind, normalized MIME type, encoded length, decoded length, and a short SHA-256 digest. Diagnostics must never include the full URL, query string, data URL, base64 payload, Feishu connection URL, or WebPush endpoint.

A request-contract regression test will verify that the final LangChain/OpenAI-style image block contains a decodable data URL. This establishes whether LambChat emitted a valid payload; failures after that boundary can then be attributed to the LangChain adapter or model gateway using captured exception class and provider metadata without exposing content.

## Error Handling

- Invalid image input is non-retryable and returns a clear, bounded error.
- Transient model invocation errors retain the configured retry behavior.
- Setting cleanup uses the existing service path so refresh and pub/sub behavior remain consistent.
- Logs preserve operational status while removing secret-bearing values.
- Deployment startup fails clearly when a required credential is missing instead of silently using a repository default.

## Test Strategy

All behavior changes follow red-green-refactor:

- logging tests assert that representative Redis, WebPush, and Feishu secret values never appear in captured records;
- a value-redacted repository scan verifies that tracked Compose configuration and current remotes contain no embedded credential;
- model-route tests assert that matching compaction references are cleared and unrelated values are preserved;
- image-analysis tests assert that malformed data URLs never call the model, valid data URLs decode, and request payloads retain the expected MIME type and bytes;
- existing compaction fallback and sandbox artifact-root regression tests remain green.

Focused pytest and Ruff checks will run first, followed by the smallest broader backend suite warranted by the changed modules.

## Operational Handoff

The delivery report will separately list actions that require platform ownership:

1. rotate Feishu app secrets and any leaked WebSocket credentials or tokens;
2. rotate Redis and WebPush/VAPID secrets implicated by logs or tracked configuration;
3. replace deployment secrets in the target secret manager or environment;
4. invalidate exposed Git credentials if historical or alternate remotes contained them;
5. rebuild and redeploy the backend, then verify new logs contain no sensitive values.
