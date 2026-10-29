import { useState, type DragEvent } from "react";
import { useSandboxStatus } from "./useSandboxStatus";
import {
  useDesktopAttachments,
  type DesktopAttachmentOptions,
} from "./useDesktopAttachments";
import { isShellAvailable } from "../services/tauri/sandboxShell";
import { resolveDesktopAttachmentEnvironment } from "../services/tauri/desktopFiles";

type Options = Omit<
  DesktopAttachmentOptions,
  "mode" | "machineId" | "currentMachineId" | "onLocalMachine"
> & {
  agent?: { supports_sandbox?: boolean };
  mode: unknown;
  selectedMachine: unknown;
  onToggleAgentOption?: (key: string, value: boolean | string | number) => void;
  uploadFiles: (files: FileList) => void;
};

export function useComposerDesktopAttachments(options: Options) {
  const status = useSandboxStatus({ enabled: isShellAvailable() });
  const environment = resolveDesktopAttachmentEnvironment({
    ...options,
    ...status,
  });
  const result = useDesktopAttachments({
    ...options,
    ...environment,
    currentMachineId: status.currentMachineId,
    onLocalMachine: (machine) => {
      if (options.selectedMachine !== machine)
        options.onToggleAgentOption?.("sandbox_machine_id", machine);
    },
  });
  const [isDraggingOver, setIsDraggingOver] = useState(false);
  return {
    ...result,
    isDraggingOver,
    handleDragOver: (event: DragEvent) => {
      event.preventDefault();
      setIsDraggingOver(true);
    },
    handleDragLeave: (event: DragEvent) => {
      event.preventDefault();
      setIsDraggingOver(false);
    },
    handleDrop: (event: DragEvent) => {
      event.preventDefault();
      setIsDraggingOver(false);
      if (isShellAvailable()) return;
      const files = event.dataTransfer?.files;
      if (files?.length && options.validateCount(files.length))
        options.uploadFiles(files);
    },
  };
}
