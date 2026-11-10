import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { assistantApi } from "../../../services/api/assistant";
import { loadAssistantChoices } from "../../assistants/assistantChoices";
import { Button, FormField, Select, type SelectOption } from "../../common/ui";

export function ChannelAssistantSelect({
  value,
  onChange,
  disabled = false,
}: {
  value?: string | null;
  onChange: (value: string | null) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const [options, setOptions] = useState<SelectOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(false);
    void loadAssistantChoices(
      async (skip) => {
        const result = await assistantApi.list(skip, 100);
        return { items: result.assistants, total: result.total };
      },
      () => active,
    )
      .then((items) => {
        if (active) setOptions(items);
      })
      .catch(() => {
        if (active) setError(true);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [retry]);
  return (
    <FormField
      label={t("assistants.channelBinding")}
      hint={t("assistants.channelBindingHint")}
    >
      <Select
        ariaLabel={t("assistants.channelBinding")}
        value={value ?? ""}
        disabled={disabled || loading}
        options={[
          { value: "", label: t("assistants.noChannelBinding") },
          ...(value && !options.some((option) => option.value === value)
            ? [
                {
                  value,
                  label: t("assistants.unavailableSelection"),
                  disabled: true,
                },
              ]
            : []),
          ...options,
        ]}
        onChange={(next) => onChange(next || null)}
      />
      {error && (
        <div className="flex items-center gap-2 text-12 text-theme-error">
          <span>{t("common.loadFailed")}</span>
          <Button
            disabled={disabled}
            onClick={() => setRetry((old) => old + 1)}
          >
            {t("common.refresh")}
          </Button>
        </div>
      )}
    </FormField>
  );
}
