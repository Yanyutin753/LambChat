# 聊天渠道接入

在 LambChat「设置 → 渠道」中添加渠道实例，为它选择 Agent、模型及项目，然后在对应平台向机器人发消息。聊天记录归属于创建该实例的 LambChat 用户，渠道中的外部用户 ID 不会切换 LambChat 账号。

## 渠道能力

| 渠道 | 接收方式 | 双向聊天所需凭据 |
| --- | --- | --- |
| 飞书 / Lark | SDK WebSocket 长连接 | App ID、App Secret，选择服务区域 |
| 微信 | iLink 长轮询 | 扫码登录取得 Bot Token |
| Telegram | Bot API `getUpdates` 长轮询 | Bot Token |
| Slack | Socket Mode | Bot Token（`xoxb-`）、App Token（`xapp-`） |
| Discord | Gateway WebSocket | Bot Token |
| 钉钉 | 企业应用机器人 Stream | Client ID、Client Secret、Corp ID |
| 企业微信 | 智能机器人 API 长连接 | Bot ID、Bot Secret |
| Webhook | 认证 HTTP JSON 回调 | Webhook Secret；需要回复时填写回复地址 |

Bark、ntfy、Gotify、Pushover、Server 酱和 PushPlus 保持通知推送用途。Slack、Discord、钉钉、企业微信的旧群机器人 Webhook 配置仍可用于单向通知；双向聊天需要表中的机器人凭据。

本次参考的 [ZCode 源码快照](https://github.com/zai-org/ZCode/blob/29628c9acdb81b703bbd4080c207a0e7ce5e276e/packages/services/src/bots/botsService.ts#L728) 实际创建了 Telegram、Webhook、飞书/Lark 和微信适配器；Discord、企业微信适配器为 `null`，没有 Slack 和钉钉实现。LambChat 的 Slack、Discord、钉钉、企业微信聊天能力按各平台官方协议实现。飞书渠道可选择中国区飞书或国际版 Lark，HTTP API、长连接和流式卡片均使用所选区域的官方域名。

## 接收开关与访问范围

以下规则适用于 Telegram、Slack、Discord、钉钉、企业微信、Webhook 的通用聊天接入；飞书和微信沿用各自的既有配置。

- `receive_enabled`：是否接收消息。原有通知渠道默认关闭，手动打开后才建立接收连接；新 Webhook 实例默认打开。
- `allowed_sender_ids`：允许调用 Agent 的平台用户 ID，多个值以逗号或空白分隔。请填写稳定 ID，不要填写昵称。
- `allowed_chat_ids`：允许接收的会话/频道 ID。同样支持多个值。
- 同时填写用户和会话限制时，消息必须同时满足两项。两项都留空时使用 `default_chat_id` 作为会话限制；三项均为空则不启动接收。

只配置会话白名单意味着该会话内能触达机器人的用户都可使用此实例。需要仅自己使用时，应填写自己的 `allowed_sender_ids`。

同一用户在不同渠道实例、外部会话或 Slack 线程内使用独立上下文。向机器人发送 `/new` 可切换到新会话；不会删除旧聊天记录。工具需要审批时，请在 LambChat 中打开对应会话处理。此批新增接入处理文本消息，附件和平台交互卡片不属于其支持范围。

## 运行配置与项目

每个可对话渠道实例均可选择 Agent、模型、人格或团队，以及 **项目（Project）**。运行配置还可选择默认／本地／云端沙箱、本地机器、思考强度、代码执行与回复语言。选择默认选项可清除对应覆盖值。纯通知渠道不使用这些运行设置。

项目如果绑定了本地工作区，执行环境将固定为该工作区的机器与目录。界面会展示绑定关系并锁定相关选项；清除项目选择后即可重新选择环境。服务端校验项目归属并解析当前工作区，填写机器 ID 不会获得其他用户的机器访问权。

沙箱环境变量每行填写一个 `KEY=VALUE`。变量名仅含字母、数字与下划线，且不能以数字开头；值中的空格和额外等号会保留。已保存的值显示为 `***`：保留占位符即保留原值，替换占位符可修改值，删除整行可移除变量；清空编辑框会清除本渠道的全部环境变量覆盖。最多 50 个变量，每个值最多 16,000 字符，总计最多 64,000 字符。这些变量用于沙箱，不是模型提供商密钥。

**重置运行配置**会清除环境变量和常用运行参数覆盖；项目选择需要单独清除。修改从后续渠道运行起生效，已运行的任务保留原有配置。切换项目会在下一条消息到达时更新渠道会话的项目绑定；项目已删除时会阻止执行，需先修正配置，不会静默改用其他项目。`LAMBCHAT_WORKSPACE` 和 `LAMBCHAT_SHARED` 是沙箱保留变量，不能覆盖。

## 各平台设置

### 飞书、Lark 和微信

飞书可使用界面中的注册流程，或在飞书开放平台创建自建应用并开启机器人能力、消息事件订阅与长连接；填写 App ID、App Secret，按需求选择群聊是否必须 @。Lark 用户在相同面板中将「服务区域」切换为国际版 Lark，然后在 `open.larksuite.com` 手动创建应用并填写凭据；扫码注册仅适用于飞书。修改已保存实例的服务区域时，需要重新填写 App Secret。微信使用渠道页面的扫码登录，确认后自动填入 Token。

### Telegram

1. 通过 `@BotFather` 创建机器人，把 Bot Token 填入 LambChat。
2. 向机器人发送消息，取得自己的用户 ID 和目标 chat ID，配置访问范围后打开接收。
3. 同一个 Token 不要同时交给另一个长轮询进程。若此机器人已注册 Telegram Webhook，需要先自行移除后再使用长轮询；LambChat 不会替你删除已有 Webhook。
4. 在群内使用时，确认 Telegram 的机器人隐私设置允许机器人接收你计划处理的消息。

协议见 [Telegram Bot API：getUpdates](https://core.telegram.org/bots/api#getupdates)。

### Slack

1. 创建 Slack App，启用 Socket Mode，创建带 `connections:write` 的 App Token。
2. 为 Bot 配置 `chat:write`、`app_mentions:read`、`im:history`，安装到工作区，取得 Bot Token。
3. 订阅 `app_mention` 与 `message.im`，邀请机器人加入目标频道。
4. 在 LambChat 填入两个 Token、允许的成员/频道 ID，打开接收。私聊直接发送文字，频道内 @ 机器人；回复会进入原消息的线程。

协议见 [Slack Socket Mode](https://docs.slack.dev/apis/events-api/using-socket-mode/)。只填写 Incoming Webhook 地址时使用通知模式。

### Discord

1. 在 Developer Portal 创建应用和 Bot，取得 Bot Token。
2. 邀请机器人到服务器，授予查看频道、发送消息和读取消息历史的权限。
3. 填写 Bot Token、允许的用户/频道 ID，打开接收。群聊默认需要 @ 机器人；私聊直接发送文字。
4. 如需关闭 `require_mention`，先在 Developer Portal 开启 Message Content Intent。

协议见 [Discord Gateway](https://docs.discord.com/developers/events/gateway)。此接入面向单 Gateway 连接的机器人；需要分片的大型机器人不在当前范围。

### 钉钉

1. 创建企业内部应用机器人，启用 Stream 模式与机器人消息接收。
2. 填写 Client ID、Client Secret 及企业 Corp ID，使用成员的 `senderStaffId` 设置用户白名单。
3. 打开接收，在私聊中发送文字，或在企业群中 @ 机器人。收到的消息所属企业必须与 Corp ID 一致。
4. 群聊目标填写会话 ID；主动发送私聊时使用 `user:<staffId>`。旧群机器人 Webhook 地址及加签 Secret 仅用于其原有推送用途。

协议见 [钉钉 Stream 协议](https://opensource.dingtalk.com/developerpedia/docs/learn/stream/protocol/)。

### 企业微信

1. 在企业微信创建支持 API 长连接的智能机器人，取得 Bot ID、Bot Secret。
2. 在 LambChat 填写对应凭据、允许的用户/会话 ID，打开接收。
3. 向机器人发送文本消息。回复通过智能机器人的长连接发回。

协议参考 [企业微信官方智能机器人 Python SDK](https://github.com/WecomTeam/wecom-aibot-python-sdk)。普通群机器人的 Webhook 地址与智能机器人的 Bot ID/Secret 是两类配置，不能互相替代。

## 通用 Webhook

### 创建与验证

添加 Webhook 渠道，设置随机的 `webhook_secret`（16–256 个可见 ASCII 字符）以及用户/会话白名单。需要双向回复时填写 `webhook_url`，此地址必须是可访问的公网 HTTPS 端点。服务不会跟随重定向，也不会向回环、私网或其他非公网地址发送密钥。留空回复地址可接收消息，但无法把 Agent 回复送回外部系统。

保存后，从渠道实例信息或 `GET /api/channels/` 响应的 `instance_id` 取得实例 ID。调用地址：

```text
POST /api/channels/webhook/{instance_id}/callback
x-lambchat-bot-secret: <该实例的密钥>
Content-Type: application/json
```

该接口通过实例密钥认证，不使用 LambChat 用户的 Bearer Token；LambChat 账号始终由实例归属决定。

### 请求示例

下面的值都是占位示例，需要替换实例 ID、外部用户 ID，并将实际密钥放入环境变量 `LAMBCHAT_WEBHOOK_SECRET`。本机示例不要求对外开放开发服务。

```bash
curl --fail-with-body \
  'http://127.0.0.1:8000/api/channels/webhook/INSTANCE_ID/callback' \
  -H 'Content-Type: application/json' \
  -H "x-lambchat-bot-secret: ${LAMBCHAT_WEBHOOK_SECRET}" \
  --data '{"sender_id":"external-user-123","chat_id":"room-42","content":"你好","message_id":"event-0001"}'
```

| 字段 | 约束 |
| --- | --- |
| `sender_id` | 必填，外部用户 ID，1–256 字符 |
| `chat_id` | 可选，会话 ID，1–256 字符；省略时使用 `sender_id` |
| `content` | 必填，非空文本，最多 16000 字符；`/new` 开启新会话 |
| `message_id` | 必填，1–256 字符；在该实例中唯一，同一消息重试时保持不变 |
| `bot_id` | 可选；若填写，必须等于 URL 中的实例 ID |

也接受 `userId`、`chatId`、`text`、`messageId`/`id`、`botId` 作为上述字段的别名；不要同时提交同一字段的多个名称。`userId` 仅表示外部发送者。`user_id`、自定义租户信息、附件和其他额外字段都会被拒绝。完整请求体最大 64 KiB。

成功返回 HTTP `202` 与 `{"accepted":true}`。重复消息及被白名单忽略的消息也会确认，避免上游无效重试；这不代表 Agent 已完成。身份校验失败返回 `403`，正文不合法返回 `422`，超限返回 `413`，暂时无法接收返回 `503`。收到 `503` 时可退避后使用原 `message_id` 重试。

### 回复示例

LambChat 向保存的 `webhook_url` 发出 POST，同样携带 `x-lambchat-bot-secret`：

```json
{
  "type": "lambchat.bot.message",
  "botId": "INSTANCE_ID",
  "provider": "webhook",
  "chatId": "room-42",
  "text": "这里是 Agent 的回复",
  "sentAt": 1791158400000
}
```

接收端应验证密钥并返回 HTTP 2xx。`sentAt` 为 Unix 毫秒时间戳。密钥不会出现在 JSON 正文中，LambChat 租户 ID 也不会发送给回复端点。

## 验证接入

保存后，先从白名单用户发送一条文字，确认 LambChat 生成会话并能返回文本；继续发送第二条消息验证上下文，再发送 `/new`。同时用未允许的用户测试消息不会触发 Agent。多实例要分别核对 Agent、模型、项目和回复目标。

自动化测试覆盖协议消息、认证、隔离、去重和失败路径；真实 Token、应用发布范围、机器人权限与平台网络连通性仍需由配置者使用实际账号验证。没有配置凭据时，测试通过不代表已完成平台端联调。
