import { Suspense, lazy } from "react";
import { LoadingSpinner } from "../../common/LoadingSpinner";

const LazySubagentPanelContent = lazy(() =>
  import("./SubagentPanelContent").then((module) => ({
    default: module.SubagentPanelContent,
  })),
);

export function DeferredSubagentPanelContent({ agentId }: { agentId: string }) {
  return (
    <Suspense
      fallback={
        <div className="flex h-full min-h-24 items-center justify-center">
          <LoadingSpinner size="sm" />
        </div>
      }
    >
      <LazySubagentPanelContent agentId={agentId} />
    </Suspense>
  );
}
