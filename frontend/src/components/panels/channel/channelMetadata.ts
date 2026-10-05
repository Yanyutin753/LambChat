import type { TFunction } from "i18next";
import type { ChannelMetadata } from "../../../types/channel";

/** Translate presentation only; preserve backend identifiers and config values. */
export function localizeChannelMetadata(
  metadata: ChannelMetadata,
  t: TFunction,
): ChannelMetadata {
  const base = `channel.catalog.providers.${metadata.channel_type}`;
  const translate = (key: string, fallback: string) =>
    t(`${base}.${key}`, { defaultValue: fallback });
  return {
    ...metadata,
    display_name: translate("name", metadata.display_name),
    description: translate("description", metadata.description),
    config_fields: metadata.config_fields.map((field) => {
      const key = `fields.${field.name}`;
      const translateField = (part: string, fallback = "") =>
        t(
          [`${base}.${key}.${part}`, `channel.catalog.commonFields.${field.name}.${part}`],
          { defaultValue: fallback },
        );
      return {
        ...field,
        title: translateField("title", field.title),
        description: translateField("description", field.description) || undefined,
        placeholder: translateField("placeholder", field.placeholder) || undefined,
        options: field.options?.map((option) => ({
          ...option,
          label: translate(
            `${key}.options.${String(option.value) || "plain"}`,
            option.label,
          ),
        })),
      };
    }),
    setup_guide: metadata.setup_guide.map((step, index) =>
      translate(`guide.${index}`, step),
    ),
  };
}
