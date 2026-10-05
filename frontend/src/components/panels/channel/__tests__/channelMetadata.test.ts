import { beforeAll, expect, test } from "vitest";
import i18n, { i18nReady } from "../../../../i18n";
import { localizeChannelMetadata } from "../channelMetadata";
import type { ChannelMetadata } from "../../../../types/channel";

beforeAll(async () => {
  await i18nReady;
  await i18n.loadLanguages(["zh", "ja", "ko", "ru"]);
});

const metadata: ChannelMetadata = {
  channel_type: "gotify",
  display_name: "Gotify",
  description: "Backend description",
  icon: "bell",
  capabilities: [],
  config_schema: {},
  requires_webhook: false,
  requires_websocket: false,
  setup_guide: ["Backend step"],
  config_fields: [
    {
      name: "priority",
      title: "Priority",
      type: "select",
      default: "5",
      options: [
        { value: 3, label: "Low (3)" },
        { value: 5, label: "Default (5)" },
      ],
    },
  ],
};

test.each(["zh", "en", "ja", "ko", "ru"])(
  "%s translates presentation without changing config values or API metadata",
  (locale) => {
    const original = structuredClone(metadata);
    const translated = localizeChannelMetadata(
      metadata,
      i18n.getFixedT(locale),
    );
    expect(translated.description).not.toBe(metadata.description);
    expect(translated.setup_guide[0]).not.toBe(metadata.setup_guide[0]);
    expect(
      translated.config_fields[0].options?.map((option) => option.value),
    ).toEqual([3, 5]);
    expect(translated.config_fields[0].default).toBe("5");
    expect(metadata).toEqual(original);
    const catalog = i18n.getResource(
      locale,
      "translation",
      "channel.catalog.providers",
    );
    expect(Object.keys(catalog).sort()).toEqual(
      Object.keys(
        i18n.getResource("en", "translation", "channel.catalog.providers"),
      ).sort(),
    );
  },
);

test("unknown channels and fields retain server text", () => {
  const unknown = {
    ...metadata,
    channel_type: "future-channel",
  } as unknown as ChannelMetadata;
  expect(localizeChannelMetadata(unknown, i18n.getFixedT("zh"))).toEqual(
    unknown,
  );
});

test.each(["zh", "en", "ja", "ko", "ru"])(
  "%s renders shared receiving fields with access guidance",
  (locale) => {
    const translated = localizeChannelMetadata(
      {
        ...metadata,
        config_fields: [
          { name: "receive_enabled", title: "SERVER_TITLE", type: "toggle" },
          { name: "allowed_sender_ids", title: "SERVER_TITLE", type: "text" },
          { name: "allowed_chat_ids", title: "SERVER_TITLE", type: "text" },
        ],
      },
      i18n.getFixedT(locale),
    );
    for (const field of translated.config_fields) {
      expect(field.title).not.toBe("SERVER_TITLE");
      expect(field.description).toBeTruthy();
    }
    expect(translated.config_fields[1].placeholder).toBeTruthy();
  },
);

test.each(["zh", "en", "ja", "ko", "ru"])(
  "%s covers bidirectional provider credentials and setup guides",
  (locale) => {
    const requiredFields = {
      telegram: ["bot_token", "default_chat_id", "parse_mode"],
      slack: ["webhook_url", "bot_token", "app_token", "default_chat_id"],
      discord: ["webhook_url", "bot_token", "default_chat_id", "require_mention"],
      dingtalk: ["webhook_url", "secret", "client_id", "client_secret", "corp_id"],
      wecom: ["webhook_url", "bot_id", "bot_secret"],
      webhook: ["webhook_url", "webhook_secret"],
    };
    for (const [provider, fields] of Object.entries(requiredFields)) {
      const catalog = i18n.getResource(locale, "translation", `channel.catalog.providers.${provider}`);
      expect(catalog?.description, provider).toBeTruthy();
      expect(Object.keys(catalog?.guide ?? {}).length, provider).toBeGreaterThanOrEqual(3);
      for (const field of fields) {
        const title = catalog?.fields?.[field]?.title ?? i18n.getResource(locale, "translation", `channel.catalog.commonFields.${field}.title`);
        expect(title, `${provider}.${field}`).toBeTruthy();
      }
    }
  },
);
