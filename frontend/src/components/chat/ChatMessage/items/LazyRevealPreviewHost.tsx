import { lazy, Suspense, useSyncExternalStore, type ComponentProps } from "react";
import {
  getRevealPreviewTabs,
  subscribeActiveRevealPreviewState,
} from "./activeRevealPreviewStore";
import type { RevealPreviewHost as PreviewHost } from "./RevealPreviewHost";

const RevealPreviewHost = lazy(() =>
  import("./RevealPreviewHost").then((module) => ({ default: module.RevealPreviewHost })),
);

export function LazyRevealPreviewHost(props: ComponentProps<typeof PreviewHost>) {
  const tabs = useSyncExternalStore(
    subscribeActiveRevealPreviewState,
    getRevealPreviewTabs,
    getRevealPreviewTabs,
  );
  if (!props.preview && tabs.length === 0) return null;
  return (
    <Suspense fallback={null}>
      <RevealPreviewHost {...props} />
    </Suspense>
  );
}
