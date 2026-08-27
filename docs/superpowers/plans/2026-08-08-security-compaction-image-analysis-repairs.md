# Security, Compaction, and Image Analysis Repairs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove confirmed secret-bearing logs, clear deleted compaction-model references, and stop malformed image data URLs before they reach a vision-model gateway.

**Architecture:** Keep each repair at its existing ownership boundary: channel and push modules own their log fields, the model route owns deletion cleanup through `SettingsService`, and the image-analysis tool owns preflight validation before `LLMClient`. Preserve the existing sandbox artifact-root repair and treat currently clean deployment/remotes as verification-only operational evidence.

**Tech Stack:** Python 3.12, FastAPI, LangChain Core, pytest, pytest-asyncio, Ruff, Docker Compose configuration.

## Global Constraints

- Never log Redis URLs, WebPush endpoints, Feishu WebSocket URLs, full image URLs, query strings, or base64 payloads.
- Do not rewrite Git history or alter the current credential-free `origin` remote.
- Do not add authentication requirements to the currently credential-free local Redis Compose service without a separate deployment decision.
- Use `SettingsService.set` for database-first setting updates, runtime refresh, and cross-instance pub/sub.
- Invalid image input is non-retryable; transient model failures keep the existing configured retry behavior.
- Preserve unrelated user changes and the existing `artifacts_root=work_dir` conversation-history repair.

---

### Task 1: Remove Secret-Bearing Runtime Logs

**Files:**
- Modify: `src/kernel/config/service.py:74-75`
- Modify: `src/api/routes/push.py:50-56`
- Modify: `src/infra/push/manager.py:64-81`
- Modify: `src/infra/channel/feishu/channel.py:440-472`
- Test: `tests/infra/test_push_manager.py`
- Test: `tests/infra/test_feishu_channel_dedupe.py`
- Create: `tests/kernel/config/test_sensitive_setting_logs.py`

**Interfaces:**
- Consumes: existing module loggers and the Feishu SDK `LogLevel` enum.
- Produces: logs containing operational status and exception class only; no secret-bearing values.

- [ ] **Step 1: Write failing startup and WebPush log tests**

```python
@pytest.mark.asyncio
async def test_initialize_settings_does_not_log_redis_url(monkeypatch, caplog):
    from src.infra.settings.service import SettingsService
    from src.kernel.config import service as config_service

    secret_url = "redis://user:secret@redis.example.test:6379/0"

    class FakeSettingsService:
        async def initialize(self):
            return None

        async def get_all(self, admin_mode=True, mask_sensitive=False):
            return {}

    fake_service = FakeSettingsService()
    monkeypatch.setattr(SettingsService, "get_instance", staticmethod(lambda: fake_service))
    monkeypatch.setattr(config_service, "_settings_service", None)
    monkeypatch.setattr(config_service.settings, "REDIS_URL", secret_url)
    monkeypatch.setattr(config_service.settings, "_vapid_keys_generated", False)

    await config_service.initialize_settings()

    assert secret_url not in caplog.text


@pytest.mark.asyncio
@patch("pywebpush.webpush")
async def test_send_push_error_log_omits_endpoint_and_exception_text(mock_webpush, caplog):
    endpoint = "https://push.example.test/subscription-secret"
    mock_webpush.side_effect = ConnectionError(f"failed endpoint={endpoint}")
    manager = PushManager()
    manager.storage.get_by_user = AsyncMock(return_value=[_make_subscription(endpoint)])
    with patch("src.infra.push.manager.settings", _fake_settings()):
        await manager.send_push_to_user("user-1", {"title": "Test"})
    assert endpoint not in caplog.text
    assert "ConnectionError" in caplog.text
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
uv run pytest tests/kernel/config/test_sensitive_setting_logs.py tests/infra/test_push_manager.py::test_send_push_error_log_omits_endpoint_and_exception_text -q
```

Expected: FAIL because startup logs the complete Redis URL and push failures log endpoint plus exception text.

- [ ] **Step 3: Write the failing Feishu SDK log-level test**

```python
@pytest.mark.asyncio
async def test_ws_client_disables_sdk_info_connection_url_logs(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, app_id, app_secret, **kwargs):
            captured.update(kwargs)
            self._reconnect_interval = None
            self._reconnect_nonce = None

        async def _disconnect(self):
            return None

    monkeypatch.setattr("lark_oapi.ws.Client", FakeClient)
    channel = _build_channel()
    channel._running = False

    await channel._run_ws_client(event_handler=object())

    assert captured["log_level"].name == "WARNING"
```

- [ ] **Step 4: Run the Feishu test and verify RED**

Run:

```bash
uv run pytest tests/infra/test_feishu_channel_dedupe.py::test_ws_client_disables_sdk_info_connection_url_logs -q
```

Expected: FAIL because the SDK client currently receives `LogLevel.INFO`.

- [ ] **Step 5: Implement minimal log redaction**

```python
# src/kernel/config/service.py
logger.info("[Settings] Loaded %s settings into cache", loaded_count)

# src/api/routes/push.py
logger.info("Push subscription saved: user_id=%s", user.sub)

# src/infra/push/manager.py
logger.warning(
    "Failed to send push notification: error_type=%s",
    type(e).__name__,
)

# src/infra/channel/feishu/channel.py
log_level = lark.LogLevel.WARNING
logger.warning(
    "Feishu WebSocket error for user %s: error_type=%s",
    self.config.user_id,
    type(e).__name__,
)
```

Remove WebPush endpoints from both expired-subscription and generic-error log branches. Keep the endpoint only in the storage deletion call.

- [ ] **Step 6: Run focused tests and verify GREEN**

Run:

```bash
uv run pytest tests/kernel/config/test_sensitive_setting_logs.py tests/infra/test_push_manager.py tests/infra/test_feishu_channel_dedupe.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 1**

```bash
git add src/kernel/config/service.py src/api/routes/push.py src/infra/push/manager.py src/infra/channel/feishu/channel.py tests/kernel/config/test_sensitive_setting_logs.py tests/infra/test_push_manager.py tests/infra/test_feishu_channel_dedupe.py
git commit -m "fix: redact connection details from logs"
```

### Task 2: Clear Deleted Native-Memory Compaction Model References

**Files:**
- Modify: `src/api/routes/agent/model.py:234-280`
- Create: `tests/api/routes/test_model_delete_cleanup.py`

**Interfaces:**
- Consumes: `SettingsService.get_raw(key: str) -> Any` and `SettingsService.set(key: str, value: Any, user_id: str) -> SettingItem | None`.
- Produces: `_clear_deleted_compaction_model_reference(model_id: str, model_value: str) -> None`.

- [ ] **Step 1: Write failing cleanup tests**

```python
class FakeCollection:
    async def update_many(self, query, update):
        return SimpleNamespace(modified_count=0)


class FakeModelStorage:
    def __init__(self, model):
        self.model = model
        self.collection = FakeCollection()

    async def get(self, model_id):
        return self.model if model_id == self.model.id else None

    async def delete(self, model_id):
        return model_id == self.model.id

    def _get_collection(self):
        return self.collection


class FakeSettingsService:
    def __init__(self, reference):
        self.values = {"NATIVE_MEMORY_COMPACTION_MODEL_ID": reference}
        self.published_user_id = None

    async def get_raw(self, key):
        return self.values[key]

    async def set(self, key, value, user_id):
        self.values[key] = value
        self.published_user_id = user_id
        return SimpleNamespace(key=key, value=value)


class FakeAgentStorage:
    async def remove_model_from_all_roles(self, model_id):
        return 0


def install_delete_route_fakes(monkeypatch, storage, settings_service):
    async def invalidate_cache():
        return None

    monkeypatch.setattr(model_routes, "get_model_storage", lambda: storage)
    monkeypatch.setattr(
        "src.infra.agent.config_storage.get_agent_config_storage",
        lambda: FakeAgentStorage(),
    )
    monkeypatch.setattr(
        "src.infra.settings.service.get_settings_service",
        lambda: settings_service,
    )
    monkeypatch.setattr("src.infra.llm.models_service.invalidate_cache", invalidate_cache)


def admin_token():
    return TokenPayload(sub="admin-1", username="admin", roles=["admin"])


@pytest.mark.asyncio
@pytest.mark.parametrize("reference", ["model-id", "openai/deleted-model"])
async def test_delete_model_clears_matching_compaction_reference(monkeypatch, reference):
    settings_service = FakeSettingsService(reference)
    storage = FakeModelStorage(
        ModelConfig(id="model-id", value="openai/deleted-model", label="Deleted")
    )
    install_delete_route_fakes(monkeypatch, storage, settings_service)
    await model_routes.delete_model("model-id", admin_token())
    assert settings_service.values["NATIVE_MEMORY_COMPACTION_MODEL_ID"] == ""
    assert settings_service.published_user_id == "system:model-delete"


@pytest.mark.asyncio
async def test_delete_model_preserves_unrelated_compaction_reference(monkeypatch):
    settings_service = FakeSettingsService("other-model")
    storage = FakeModelStorage(
        ModelConfig(id="model-id", value="openai/deleted-model", label="Deleted")
    )
    install_delete_route_fakes(monkeypatch, storage, settings_service)
    await model_routes.delete_model("model-id", admin_token())
    assert settings_service.values["NATIVE_MEMORY_COMPACTION_MODEL_ID"] == "other-model"
```

The fakes must implement the real route boundary: model lookup/deletion, fallback-reference `update_many`, role cleanup, settings get/set, and cache invalidation. Assertions target the resulting setting state, not mock call existence.

- [ ] **Step 2: Run the cleanup tests and verify RED**

Run:

```bash
uv run pytest tests/api/routes/test_model_delete_cleanup.py -q
```

Expected: FAIL because deleting a model never reads or clears `NATIVE_MEMORY_COMPACTION_MODEL_ID`.

- [ ] **Step 3: Implement the cleanup helper and route integration**

```python
async def _clear_deleted_compaction_model_reference(
    model_id: str,
    model_value: str,
) -> None:
    from src.infra.settings.service import get_settings_service

    service = get_settings_service()
    reference = str(await service.get_raw("NATIVE_MEMORY_COMPACTION_MODEL_ID") or "").strip()
    if reference not in {model_id, model_value}:
        return
    await service.set("NATIVE_MEMORY_COMPACTION_MODEL_ID", "", "system:model-delete")
```

Call the helper after role-reference cleanup and before model-cache invalidation so the setting refresh and model cache converge in the same request.

- [ ] **Step 4: Run model deletion and compaction fallback tests**

Run:

```bash
uv run pytest tests/api/routes/test_model_delete_cleanup.py tests/infra/memory/test_compaction_agent.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/api/routes/agent/model.py tests/api/routes/test_model_delete_cleanup.py
git commit -m "fix: clear deleted compaction model references"
```

### Task 3: Reject Malformed Image Data URLs Before Model Invocation

**Files:**
- Modify: `src/infra/tool/image_analysis_tool.py:35-305`
- Modify: `tests/infra/tool/test_image_analysis_tool.py`

**Interfaces:**
- Consumes: existing image attachment dictionaries with `url` or `data_url`.
- Produces: `_validate_image_data_url(value: str) -> tuple[str, int, str]`, returning MIME type, decoded byte length, and a short SHA-256 digest; raises `ValueError("invalid_image_data_url")` for malformed input.

- [ ] **Step 1: Write failing malformed-input tests**

```python
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "image_ref",
    [
        "data:text/plain;base64,aGVsbG8=",
        "data:image/png;base64,not-valid***",
        "data:image/png;base64,",
    ],
)
async def test_image_analyze_rejects_invalid_data_url_without_model_call(monkeypatch, image_ref):
    model = ModelConfig(
        id="vision-id",
        value="openai/gpt-4o-mini",
        label="Vision",
        profile=ModelProfile(supports_vision=True),
    )
    calls = 0

    class FailIfInvoked:
        async def ainvoke(self, messages, config=None):
            nonlocal calls
            calls += 1
            raise AssertionError("invalid input reached model")

    async def fake_get_model(**kwargs):
        return FailIfInvoked()

    monkeypatch.setattr(image_analysis_tool.settings, "IMAGE_ANALYSIS_MODEL_ID", "vision-id")
    monkeypatch.setattr(
        "src.infra.agent.model_storage.get_model_storage",
        lambda: _FakeStorage(model),
    )
    monkeypatch.setattr(image_analysis_tool.LLMClient, "get_model", fake_get_model)
    result = json.loads(
        await image_analysis_tool.image_analyze.coroutine(
            image_urls=[image_ref], prompt="Describe", runtime=_Runtime()
        )
    )
    assert result == {"error": "Invalid image data URL"}
    assert calls == 0
```

- [ ] **Step 2: Run malformed-input tests and verify RED**

Run:

```bash
uv run pytest tests/infra/tool/test_image_analysis_tool.py -k invalid_data_url -q
```

Expected: FAIL because malformed data URLs currently reach `llm.ainvoke` and may be retried.

- [ ] **Step 3: Write the failing valid-payload contract test**

```python
def test_validate_image_data_url_returns_safe_metadata():
    mime_type, decoded_size, digest = image_analysis_tool._validate_image_data_url(
        "data:image/png;base64,iVBORw0KGgo="
    )
    assert mime_type == "image/png"
    assert decoded_size == 8
    assert len(digest) == 12
    assert "iVBOR" not in digest
```

Add an async image-analysis test with `image_url_to_base64=True` that captures the final `HumanMessage`, builds the provider request payload through `ChatOpenAI._get_request_payload`, and independently base64-decodes its literal data URL with `validate=True`.

- [ ] **Step 4: Run the contract tests and verify RED**

Run:

```bash
uv run pytest tests/infra/tool/test_image_analysis_tool.py -k "safe_metadata or provider_payload" -q
```

Expected: FAIL because `_validate_image_data_url` and the provider-payload regression do not exist.

- [ ] **Step 5: Implement strict validation and safe diagnostics**

```python
_IMAGE_DATA_URL_RE = re.compile(
    r"^data:(image/[A-Za-z0-9.+-]+);base64,([A-Za-z0-9+/]*={0,2})$",
    re.IGNORECASE,
)


def _validate_image_data_url(value: str) -> tuple[str, int, str]:
    match = _IMAGE_DATA_URL_RE.fullmatch(value.strip())
    if not match:
        raise ValueError("invalid_image_data_url")
    mime_type = match.group(1).lower()
    try:
        decoded = base64.b64decode(match.group(2), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("invalid_image_data_url") from exc
    if not decoded or len(decoded) > get_image_download_max_bytes():
        raise ValueError("invalid_image_data_url")
    return mime_type, len(decoded), hashlib.sha256(decoded).hexdigest()[:12]
```

Before `build_human_message`, validate every attachment `data_url` and every `url` beginning with `data:`. On failure return `{"error": "Invalid image data URL"}` immediately. Log only `reference_kind`, MIME, decoded length, and digest at DEBUG level.

- [ ] **Step 6: Run image-analysis tests and verify GREEN**

Run:

```bash
uv run pytest tests/infra/tool/test_image_analysis_tool.py tests/infra/agent/test_image_url_middleware.py tests/agents/core/test_node_utils_multimodal.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

```bash
git add src/infra/tool/image_analysis_tool.py tests/infra/tool/test_image_analysis_tool.py
git commit -m "fix: validate image data URLs before analysis"
```

### Task 4: Verify Conversation Persistence and Credential-Free Repository State

**Files:**
- Verify only: `src/infra/backend/deepagent.py`
- Verify only: `src/infra/backend/e2b.py`
- Verify only: `deploy/docker-compose.yml`
- Verify only: `.env.example`

**Interfaces:**
- Consumes: existing `create_sandbox_backend` and E2B diagnostic behavior.
- Produces: verification evidence and an operational rotation checklist; no forced deployment-auth redesign.

- [ ] **Step 1: Run the existing conversation-history regressions**

Run:

```bash
uv run pytest tests/infra/backend/test_deepagents_protocol_compat.py::test_sandbox_backend_anchors_artifacts_at_work_dir tests/infra/backend/test_deepagents_protocol_compat.py::test_e2b_execute_surfaces_command_stderr_on_failure -q
```

Expected: PASS.

- [ ] **Step 2: Scan tracked deployment and Git configuration without printing values**

Run:

```bash
git ls-files -z deploy '.env*' '*.yml' '*.yaml' | xargs -0 -r rg -l 'https?://[^/@[:space:]]+:[^/@[:space:]]+@'
git remote | while IFS= read -r name; do git remote get-url "$name" | sed -E 's#(https?://)[^/@]+@#\1***@#'; done
```

Expected: no tracked credential-bearing URL and a sanitized credential-free `origin`. If a real credential-bearing value is found, stop and report the exact file path without printing the value before modifying deployment behavior.

- [ ] **Step 3: Run focused backend verification**

Run:

```bash
uv run pytest tests/kernel/config/test_sensitive_setting_logs.py tests/infra/test_push_manager.py tests/infra/test_feishu_channel_dedupe.py tests/api/routes/test_model_delete_cleanup.py tests/infra/memory/test_compaction_agent.py tests/infra/tool/test_image_analysis_tool.py tests/infra/agent/test_image_url_middleware.py tests/infra/backend/test_deepagents_protocol_compat.py -q
uv run ruff check src/kernel/config/service.py src/api/routes/push.py src/infra/push/manager.py src/infra/channel/feishu/channel.py src/api/routes/agent/model.py src/infra/tool/image_analysis_tool.py tests/kernel/config/test_sensitive_setting_logs.py tests/infra/test_push_manager.py tests/infra/test_feishu_channel_dedupe.py tests/api/routes/test_model_delete_cleanup.py tests/infra/tool/test_image_analysis_tool.py
```

Expected: all tests pass and Ruff reports `All checks passed!`.

- [ ] **Step 4: Record operational handoff**

The final response must state that code changes do not rotate already exposed credentials. List Feishu app secret, Redis credentials if the deployed environment uses them, WebPush/VAPID private key, deployment secret-store values, and any historical Git credential as rotation targets. State that previously unpersisted messages cannot be recovered.
