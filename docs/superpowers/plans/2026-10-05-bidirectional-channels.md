# Bidirectional channels implementation plan

> **For agentic workers:** Use the executing-plans workflow for shared runtime/integration and isolated parallel provider work. The user has authorized implementation of all ZCode channels plus DingTalk, WeCom, Slack and Discord.

**Goal:** Receive authorized chat messages, execute the configured LambChat agent, and reply on Telegram, DingTalk, WeCom, Slack, Discord and a generic Webhook, preserving WeChat and Feishu/Lark.

**Architecture:** Existing outbound configuration remains valid with `receive_enabled=false`. New receiving configurations use one shared lifecycle, credential-scoped Redis lease, bounded dispatch, message deduplication and tenant/instance/sender-scoped sessions. Platform transports authenticate outbound connections; generic Webhook authenticates each callback using its per-instance secret. The page shows supported capabilities; configuration explicitly controls whether receiving is enabled.

**Tech stack:** Python 3.12, httpx, aiohttp, Redis, existing TaskManager and ChannelStorage; React metadata-driven forms and five locales.

**Spec:** User's October 5 request and approved scope: all common chat platforms plus all existing ZCode providers. Reference source pinned at zai-org/ZCode 29628c9acdb81b703bbd4080c207a0e7ce5e276e. ZCode's Discord and WeCom providers are null; these and DingTalk/Slack use official platform protocols.

## Constraints

- Work only in isolated LambChat-channel-icons checkout; preserve concurrent settings-page changes in main checkout.
- Preserve old webhook sending and stored secrets. Opt-in receiving requires a sender/chat allowlist; empty lists do not open the owner's agent to strangers.
- Use real capabilities, no fabricated receive labels. Feishu includes Lark through a persisted region selection, used consistently by HTTP, WebSocket and CardKit APIs.
- No public service/firewall setup. Deployment is authorized only after the local/CI/staging gates below. Generic Webhook requires an existing reachable endpoint supplied by the user.
- Tests first; no credentials in logs; no LLM attribution in commits. Five locales for every field, description and guide.

## Shared runtime and Telegram

Files: `src/infra/channel/chat.py`, `chat_handler.py`, `chat_lease.py`, `telegram.py`, `tests/infra/test_chat_channels.py`, `test_telegram_bidirectional.py`.

- [x] Add failing authorization, duplicate-message, queue-limit, stop-cancellation and owner-token lease tests.
- [x] Implement ChatConfig(receive_enabled,allowed_sender_ids,allowed_chat_ids) and ChatChannel.start/stop/queue supervision. Redis lease ownership is checked before renewal/release; losing lease cancels the reader.
- [x] Bind handlers to the actual channel instance. Session identity includes owner, platform, instance, external chat, sender and thread; /new uses a new UUID.
- [x] Submit through existing TaskManager with configured agent/model/project/persona/team, tag channel delivery, send final reply and approval hints without automatically approving actions.
- [x] Telegram: test getMe/getUpdates parsing, bot filtering, offset persistence after processing, authorized DM/group replies, text chunking, failure retry. Never delete an existing Telegram webhook automatically.

## Platform transports (independent)

Files: `dingtalk.py`, `wecom.py`, `slack.py`, `discord.py`, dedicated protocol helpers and `tests/infra/test_*_bidirectional.py`.

Interface: `ChatChannel._validate_inbound_config() -> bool`, `_run_inbound() -> None`, `_send_reply(chat_id,content,**metadata) -> bool`, `enqueue_inbound(message) -> bool`. The message contains sender_id, chat_id, content, message_id, optional metadata. Transport ACKs only after acceptance; heartbeat runs independently of inference.

- [x] DingTalk: gateway ticket connection, system ACK, corporate identity validation, message ACK and temporary session webhook reply.
- [x] WeCom: authenticated aibot_subscribe, application heartbeat ACK, callback parsing, req_id-correlated final stream reply and proactive send.
- [x] Slack: app-token Socket Mode connection, envelope ACK, bot/edited-event filtering, bot-token threaded reply.
- [x] Discord: Identify, heartbeat/ACK, Resume, fatal close handling, message intents/mentions, bot filtering and mention-safe replies.
- [x] For each, retain original outgoing webhook code and test both modes.

## Generic Webhook

Files: `webhook.py`, `src/api/routes/channel_webhook.py`, dedicated tests; integration in channel enums/storage/API main/frontend.

- [x] Test callback secret rejection, malformed/oversized input, disabled instances, unknown instances and cross-tenant spoofing.
- [x] Resolve configuration by opaque instance ID with authoritative owner fields. Require unique match and fresh secret; compare in constant time.
- [x] Normalize documented JSON payload, deduplicate message_id and enqueue through shared handler. Protect outbound URL from SSRF and do not follow redirects.
- [x] Document reply JSON and callback path; register router before generic dynamic channel routes.

## Integration and verification

- [x] Encrypt newly introduced credential fields; authoritative owner fields override nested configuration values.
- [x] Add all five language descriptions, fields/options/guides, Webhook icon and proper capability labels.
- [x] Run protocol tests and handler integration tests, then backend/full frontend suites, lint, format, mypy, typecheck/build and budgets.
- [x] Review authorization, credential ownership, reconnect, cleanup, session isolation and old config compatibility. No live-provider success claim without real credentials.
- [ ] Integrate into feat/notification-channels and update PR769. The user subsequently authorized merge to develop, staging verification, promotion to main and production deployment after all gates pass.


## Expanded runtime scope (user-approved)

- [x] All chat channels expose project, model, persona/team and shared runtime settings: default/local/cloud sandbox, explicit machine, thinking intensity, code interpreter and reply language.
- [x] Store per-channel KEY=VALUE variables encrypted, mask each value on GET/list, preserve masked edits, support deletion/reset and reject reserved sandbox contract keys.
- [x] Resolve project workspace and machine from owner-authorized project metadata. Missing projects fail closed; the next channel message updates session project binding.
- [x] Keep environment secrets out of task options/checkpoints; persist only an owner-scoped channel reference and resolve variables onto each run's private backend delegate.
- [x] Search and Team agents honor local/cloud selection; refresh global variables without dropping run overrides; prompt only includes channel variable names.
- [x] Persist non-secret runtime metadata before launch, including existing sessions and explicit clears, so approval/recovery preserves environment and project settings.
- [x] Match every channel executor to the current TaskExecutor keyword contract, including MCP whitelist, resume payload and base URL.
- [x] Add real local sandbox E2E for concurrent channel environments and a subsequent ordinary execution with no residual variables.
- [ ] Finish all local gates; merge reviewed PR769 only after green CI.
- [ ] Deploy exact develop image, verify staging with a real conversation, then promote reviewed develop to main through PR.
- [ ] Deploy exact main image; require every production disttest result to pass and retain previous image tag for rollback.
