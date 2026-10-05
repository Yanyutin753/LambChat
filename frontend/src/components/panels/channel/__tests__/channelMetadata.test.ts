import { expect, test } from "vitest";
import i18n from "../../../../i18n";
import { localizeChannelMetadata } from "../channelMetadata";
import type { ChannelMetadata } from "../../../../types/channel";

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
