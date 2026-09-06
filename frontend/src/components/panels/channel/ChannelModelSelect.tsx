/**
 * Model selector for channel configuration.
 * Fetches user's available models and renders a select dropdown.
 * Uses model.id (DB ID) so the backend resolves provider/key/config.
 */
import { useState, useEffect } from "react";
import { Cpu } from "lucide-react";
import { useTranslation } from "react-i18next";
import { modelApi } from "../../../services/api/model";
import type { ModelOption } from "../../../services/api/model";
import { GlassSelect } from "../../common/GlassSelect";

interface ChannelModelSelectProps {
  value: string | null | undefined;
  onChange: (modelId: string | null) => void;
}

export function ChannelModelSelect({
  value,
  onChange,
}: ChannelModelSelectProps) {
  const { t } = useTranslation();
  const [models, setModels] = useState<ModelOption[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    modelApi
      .listAvailable()
      .then((res) => {
        setModels(res.models || []);
      })
      .catch(() => {
        setModels([]);
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="es-field">
      <label className="es-label">
        <div className="flex items-center gap-1.5">
          <Cpu size={14} />
          {t("channel.model", "Model")}
        </div>
      </label>
      <GlassSelect
        value={value || ""}
        onChange={(v) => onChange(v || null)}
        disabled={loading}
        placeholder={
          loading
            ? t("common.loading", "Loading...")
            : t("channel.defaultModel", "Default Model")
        }
        options={models.map((model) => ({
          value: model.id,
          label: (
            <>
              <span className="font-serif">{model.label}</span>
              <span className="opacity-60"> ({model.value})</span>
            </>
          ),
        }))}
      />
      <p className="es-hint">
        {t(
          "channel.modelHint",
          "Select which model this channel uses. Uses the model's configured provider and API key.",
        )}
      </p>
    </div>
  );
}
