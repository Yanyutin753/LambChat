# Chat channels

Add an instance under **Settings → Channels**, select its agent, model and project, and message its bot. Conversations belong to the LambChat user who created the instance. External sender IDs never select a different LambChat account.

## Available connections

| Channel | Inbound transport | Credentials for chat |
| --- | --- | --- |
| Feishu / Lark | SDK WebSocket | App ID, App Secret, selected service region |
| WeChat | iLink long polling | Bot Token obtained by scanning the login QR code |
| Telegram | Bot API `getUpdates` | Bot Token |
| Slack | Socket Mode | Bot Token (`xoxb-`), App Token (`xapp-`) |
| Discord | Gateway WebSocket | Bot Token |
| DingTalk | Enterprise app robot Stream | Client ID, Client Secret, Corp ID |
| WeCom | Smart robot API persistent connection | Bot ID, Bot Secret |
| Webhook | Authenticated HTTP JSON callback | Webhook Secret; reply URL to receive answers |

Bark, ntfy, Gotify, Pushover, ServerChan and PushPlus remain notification services. Existing Slack, Discord, DingTalk and WeCom incoming webhooks continue to support outgoing notifications; chat requires the bot credentials above.

The referenced [ZCode source snapshot](https://github.com/zai-org/ZCode/blob/29628c9acdb81b703bbd4080c207a0e7ce5e276e/packages/services/src/bots/botsService.ts#L728) implements Telegram, Webhook, Feishu/Lark and WeChat adapters. Discord and WeCom adapters are `null`; Slack and DingTalk are absent. LambChat implements those additional transports using their official protocols. Select Feishu (China) or Lark (International) in the Feishu panel. HTTP APIs, WebSocket connections and streaming cards all use that region's official domain.

## Receiving and access

The following settings apply to Telegram, Slack, Discord, DingTalk, WeCom and Webhook. Feishu and WeChat retain their existing settings.

- `receive_enabled` defaults to false for existing notification channels. Turn it on to receive messages. New generic Webhook instances default to true.
- `allowed_sender_ids` contains stable platform user IDs, separated by commas or whitespace. Display names are not IDs.
- `allowed_chat_ids` restricts the permitted conversations or channels.
- If both lists are set, both must match. If neither is set, `default_chat_id` becomes the chat restriction. Receiving cannot start when all three are empty.

Allowing only a chat permits its members who can reach the bot to use the instance. Set your own sender ID for personal access. Sessions are isolated by owner, channel instance, external chat and sender; Slack threads also have separate contexts. Send `/new` to start a fresh conversation without deleting history. Open the conversation in LambChat when a tool requires approval. These new adapters support text messages; attachments and interactive platform cards are outside their scope.

## Run configuration and projects

Each conversation-capable channel instance can choose its agent, model, persona or team, and **Project**. Run configuration additionally selects the default/local/cloud sandbox, local machine, thinking effort, code execution and response language. Choosing the default option removes that override. Notification-only channels do not use these settings.

A project linked to a local workspace fixes the run environment to that workspace’s machine and directory. The controls show this binding and remain locked until the project is cleared. The server verifies ownership and resolves the current workspace; entering a machine ID cannot grant access to another user’s machine.

Enter sandbox environment variables as one `KEY=VALUE` per line. Keys use letters, digits and underscores, starting with a letter or underscore. Values preserve spaces and additional equals signs. Saved values appear as `***`: keep this placeholder to retain a value, replace it to change the value, or delete its line to remove it. An empty editor clears all channel environment overrides. There are limits of 50 variables, 16,000 characters per value and 64,000 total characters. These are sandbox variables, not model-provider credentials.

**Reset run configuration** clears environment and common run overrides; project selection is cleared separately. Changes apply to subsequent channel runs. A task already running retains its configuration. Changing the selected project updates the channel session binding on its next message. A deleted project blocks execution until the configuration is corrected; the channel does not silently switch projects. `LAMBCHAT_WORKSPACE` and `LAMBCHAT_SHARED` are reserved sandbox variables.

## Platform setup

**Feishu / Lark / WeChat:** use the existing app-registration or QR-login controls. A manually created Feishu app needs bot capabilities, message events and a persistent connection, plus its App ID and App Secret. Select the desired group mention policy. For Lark, select the international region and manually enter credentials from an app created at `open.larksuite.com`; QR registration is Feishu-only. Changing a saved region requires entering the App Secret again. WeChat fills its token after QR confirmation.

**Telegram:** create a bot with `@BotFather`, enter its token, obtain your sender and chat IDs, configure access and turn on receiving. Do not share the token with a competing long-polling process. Remove an existing Telegram Webhook yourself before using long polling; LambChat does not remove it automatically. Group privacy settings determine which messages the bot receives. See [Telegram getUpdates](https://core.telegram.org/bots/api#getupdates).

**Slack:** enable Socket Mode, create an App Token with `connections:write`, and install a bot with `chat:write`, `app_mentions:read` and `im:history`. Subscribe to `app_mention` and `message.im`, invite the bot to its channels, and enter both tokens and allowed IDs in LambChat. Direct messages and channel mentions receive threaded replies. See [Slack Socket Mode](https://docs.slack.dev/apis/events-api/using-socket-mode/).

**Discord:** create an application and bot in the Developer Portal. Invite it with View Channels, Send Messages and Read Message History permissions. Enter its token and allowed IDs, then enable receiving. Group mentions are required by default; enable Message Content Intent before disabling `require_mention`. Bots requiring multiple Gateway shards are outside this adapter's scope. See [Discord Gateway](https://docs.discord.com/developers/events/gateway).

**DingTalk:** create an enterprise app robot with Stream enabled. Enter Client ID, Client Secret and Corp ID, allow staff IDs (`senderStaffId`), then enable receiving. Message the bot directly or mention it in a group. Incoming organization IDs must match Corp ID. Proactive direct-message targets use `user:<staffId>`; group targets use the conversation ID. See [DingTalk Stream](https://opensource.dingtalk.com/developerpedia/docs/learn/stream/protocol/).

**WeCom:** create an API smart robot with a persistent connection, then enter its Bot ID, Bot Secret and allowed sender/chat IDs. Enable receiving and send a text message. A legacy group-bot webhook is a different configuration and cannot replace smart-robot credentials. See the [official WeCom Python SDK](https://github.com/WecomTeam/wecom-aibot-python-sdk).

## Generic Webhook

Choose a random `webhook_secret` containing 16–256 visible ASCII characters and configure permitted IDs. To receive replies, set `webhook_url` to a public HTTPS endpoint. Redirects and non-public addresses are rejected. Leaving the URL empty permits inbound callbacks but cannot deliver replies to your external system.

After saving, obtain `instance_id` from the instance information or `GET /api/channels/`. The callback uses the instance's secret, not a LambChat Bearer token:

```text
POST /api/channels/webhook/{instance_id}/callback
x-lambchat-bot-secret: <instance secret>
Content-Type: application/json
```

Replace the example IDs and put your real secret in `LAMBCHAT_WEBHOOK_SECRET`. This local example requires no public development server:

```bash
curl --fail-with-body \
  'http://127.0.0.1:8000/api/channels/webhook/INSTANCE_ID/callback' \
  -H 'Content-Type: application/json' \
  -H "x-lambchat-bot-secret: ${LAMBCHAT_WEBHOOK_SECRET}" \
  --data '{"sender_id":"external-user-123","chat_id":"room-42","content":"Hello","message_id":"event-0001"}'
```

| Field | Contract |
| --- | --- |
| `sender_id` | Required external user ID, 1–256 characters |
| `chat_id` | Optional chat ID, 1–256 characters; defaults to `sender_id` |
| `content` | Required nonblank text, at most 16000 characters; `/new` resets context |
| `message_id` | Required, 1–256 characters, unique within the instance; reuse on retries |
| `bot_id` | Optional; must match the URL's instance ID if provided |

Aliases `userId`, `chatId`, `text`, `messageId`/`id` and `botId` are accepted; use only one name for each field. `userId` means the external sender. `user_id`, arbitrary tenant fields, attachments and other extra fields are rejected. The complete body must not exceed 64 KiB.

HTTP `202` with `{"accepted":true}` acknowledges a message, including duplicates and messages deliberately ignored by access rules. It does not mean the agent has finished. Authentication failure returns `403`, invalid input `422`, an oversized body `413`, and temporary inability to accept `503`. Back off and retry a `503` using the same message ID.

Replies POST to the saved URL with the same secret header and this JSON shape:

```json
{
  "type": "lambchat.bot.message",
  "botId": "INSTANCE_ID",
  "provider": "webhook",
  "chatId": "room-42",
  "text": "The agent's reply",
  "sentAt": 1791158400000
}
```

Verify the secret and return HTTP 2xx. `sentAt` is a Unix timestamp in milliseconds. Neither the secret nor the LambChat owner's user ID appears in the JSON body.

## Check your configuration

### Multiple replicas and server restarts

Receiving channels (Feishu, WeChat, Telegram, Slack, Discord, DingTalk, WeCom, and custom Webhook) persist messages in MongoDB before acknowledging receipt or advancing a polling cursor. Replicas share delivery records and processing leases. Messages in one conversation stay ordered, and a replica that loses ownership stops processing. Pending messages do not expire; completed deduplication records remain for seven days.

Connections retry after server restarts and network failures. Accepted deliveries retain their original run ID and use the normal conversation recovery mechanism. Saved Feishu streaming cards continue updating; WeCom uses the current connection; DingTalk uses its authenticated API when a temporary reply URL expires. Session mappings include the owner and channel instance, and an explicitly selected instance never falls back to another bot. Legacy Feishu/WeChat chat-only session mappings are not reused across tenants; earlier conversations remain in the web history.

Recovery requires shared MongoDB and Redis plus valid platform permissions. Notification-only channels have no inbound connection to reconnect. When a platform does not provide idempotent sends, a crash after it receives a reply but before LambChat records success can still cause a duplicate reply on retry. This is not an external exactly-once guarantee. Messages acknowledged by older versions before the durable inbox was deployed have no new recovery record.

Send a message from an allowed account, check the conversation and reply, send a second message to verify context, and try `/new`. Verify that an account outside your allowlist cannot start a run. Check each instance's agent, model, project and destination independently.

Automated tests cover protocol messages, authentication, isolation, deduplication and failure handling. Platform permissions, app publication, actual credentials and connectivity still require a test with your real account. Passing mocked protocol tests is not a claim that a real bot has been connected.
