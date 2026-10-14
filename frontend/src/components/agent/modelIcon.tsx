import React, { useMemo } from "react";
import { getModelIconUrl } from "./modelIcon";
import { AgentAvatar } from "../common/AgentAvatar";

export const ModelIconImg = React.memo(function ModelIconImg({
  model,
  provider,
  icon,
  size = 22,
}: {
  model: string;
  provider?: string;
  icon?: string;
  size?: number;
}) {
  const url = useMemo(
    () => getModelIconUrl(model, provider, icon),
    [model, provider, icon],
  );
  return (
    <AgentAvatar
      avatar={url}
      seed={provider || model}
      size={size}
      className="rounded-full"
    >
      {!url && (
        <span className="text-12 font-medium">
          {model.charAt(0).toUpperCase()}
        </span>
      )}
    </AgentAvatar>
  );
});
