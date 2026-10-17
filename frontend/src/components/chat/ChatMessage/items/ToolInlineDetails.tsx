import type { ReactNode } from "react";

export function ToolInlineDetails({ children }: { children: ReactNode }) {
  return <div className="tool-inline-details tool-readable">{children}</div>;
}
