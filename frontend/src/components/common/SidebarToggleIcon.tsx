import { PanelLeft } from "lucide-react";
import { InteractiveIcon } from "./InteractiveIcon";

export function SidebarToggleIcon({
  className = "size-4",
}: {
  className?: string;
}) {
  return (
    <InteractiveIcon>
      <PanelLeft className={className} aria-hidden="true" />
    </InteractiveIcon>
  );
}
