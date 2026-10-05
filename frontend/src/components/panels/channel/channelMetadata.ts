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
      return {
        ...field,
        title: translate(`${key}.title`, field.title),
        description:
          field.description === undefined
            ? undefined
            : translate(`${key}.description`, field.description),
        placeholder:
          field.placeholder === undefined
            ? undefined
            : translate(`${key}.placeholder`, field.placeholder),
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
