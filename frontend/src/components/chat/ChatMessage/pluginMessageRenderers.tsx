import { AlertCircle, Plug } from "lucide-react";
import { type ReactElement } from "react";
import type { PluginMessagePart } from "../../../types";
import type { CorePluginMessageRendererContribution } from "../../../extensions/coreContributions";

export interface PluginMessageRendererProps {
  part: PluginMessagePart;
  contribution: CorePluginMessageRendererContribution;
}

export interface PluginMessageUnavailableProps {
  part: PluginMessagePart;
  reason: "not_declared" | "not_registered";
}

export function PluginMessageUnavailable({
  part,
  reason,
}: PluginMessageUnavailableProps): ReactElement {
  return (
    <div className="rounded-xl border border-theme-border bg-theme-bg-card px-3.5 py-3 text-sm text-theme-text-secondary">
      <div className="flex items-center gap-2 text-theme-text-primary">
        <AlertCircle size={15} className="shrink-0 text-amber-500" />
        <span className="font-medium">
          Plugin message renderer unavailable
        </span>
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <span className="inline-flex items-center gap-1">
          <Plug size={12} />
          <span className="font-mono">{part.plugin_id}</span>
        </span>
        <span className="font-mono">{part.renderer}</span>
        <span>
          {reason === "not_declared"
            ? "The plugin is disabled or did not declare this renderer."
            : "The renderer is not registered in this build."}
        </span>
      </div>
    </div>
  );
}

export const PLUGIN_MESSAGE_RENDERERS: Record<
  string,
  (props: PluginMessageRendererProps) => ReactElement | null
> = {};
