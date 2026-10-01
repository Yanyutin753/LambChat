import React from "react";
import { modelIconSlugs } from "../../../agent/modelIcon";
import { ModelBrandPicker } from "./ModelBrandPicker";

interface ModelIconSelectProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}
export const ModelIconSelect = React.memo(function ModelIconSelect({
  value,
  onChange,
  placeholder = "",
}: ModelIconSelectProps) {
  return (
    <ModelBrandPicker
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      slugs={modelIconSlugs}
      kind="icon"
    />
  );
});
