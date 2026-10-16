import { useTranslation } from "react-i18next";
import { Select } from "../common/ui/Select";
import { setUpdateChannel, useUpdateChannel } from "../../utils/updateChannel";

export function UpdateChannelSelect() {
  const { t } = useTranslation();
  const { channel, busy } = useUpdateChannel();
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 py-3">
      <span className="text-14 text-theme-text">{t("update.channel")}</span>
      <Select
        ariaLabel={t("update.channel")}
        value={channel}
        disabled={busy}
        onChange={(value) => {
          if (value === "stable" || value === "dev") setUpdateChannel(value);
        }}
        options={[
          { value: "stable", label: t("update.channelStable") },
          { value: "dev", label: t("update.channelDev") },
        ]}
      />
      {channel === "dev" && (
        <p className="w-full text-12 text-theme-text-secondary">
          {t("update.channelDevHint")}
        </p>
      )}
    </div>
  );
}
