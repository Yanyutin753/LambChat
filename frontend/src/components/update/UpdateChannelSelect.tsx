import { useId } from "react";
import { useTranslation } from "react-i18next";
import { setUpdateChannel, useUpdateChannel } from "../../utils/updateChannel";
import "./update-channel.css";

export function UpdateChannelSelect() {
  const { t } = useTranslation();
  const { channel, busy } = useUpdateChannel();
  const id = useId();
  return (
    <div className="update-channel-control">
      <span id={id} className="text-12 text-theme-text-secondary">
        {t("update.channel")}
      </span>
      <fieldset
        className="update-channel-options"
        aria-labelledby={id}
        aria-describedby={channel === "dev" ? `${id}-hint` : undefined}
        disabled={busy}
      >
        {(["stable", "dev"] as const).map((value) => (
          <label key={value} className="update-channel-option">
            <input
              className="sr-only"
              type="radio"
              name={id}
              value={value}
              checked={channel === value}
              onChange={() => setUpdateChannel(value)}
            />
            <span>
              {t(
                value === "stable"
                  ? "update.channelStable"
                  : "update.channelDev",
              )}
            </span>
          </label>
        ))}
      </fieldset>
      {channel === "dev" && (
        <p
          id={`${id}-hint`}
          className="update-channel-hint text-12 text-theme-text-secondary"
        >
          {t("update.channelDevHint")}
        </p>
      )}
    </div>
  );
}
