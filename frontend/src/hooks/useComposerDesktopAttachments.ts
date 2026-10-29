import { useDroppedFiles } from "./useDroppedFiles";
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
  uploadFiles: (files: FileList | File[]) => void;
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
  const drop = useDroppedFiles({
    ...options,
    ...environment,
    receiveFiles: result.receiveFiles,
  });
  return {
    ...result,
    ...drop,
  };
}
