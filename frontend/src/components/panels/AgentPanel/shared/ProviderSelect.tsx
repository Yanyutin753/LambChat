import React, { useEffect, useState } from "react";
import { modelApi } from "../../../../services/api/model";
import { PROVIDER_LABELS } from "./providerLabels";
import { ModelBrandPicker } from "../../ModelPanel/tabs/ModelBrandPicker";

interface ProviderSelectProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}
export const ProviderSelect = React.memo(function ProviderSelect({
  value,
  onChange,
  placeholder = "",
  className,
}: ProviderSelectProps) {
  const [providers, setProviders] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    modelApi
      .listProviders()
      .then((list) => setProviders(list.map((provider) => provider.value)))
      .catch(() => setProviders(Object.keys(PROVIDER_LABELS)))
      .finally(() => setLoading(false));
  }, []);
  return (
    <ModelBrandPicker
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      slugs={providers}
      kind="provider"
      loading={loading}
      className={className}
    />
  );
});
