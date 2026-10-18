import { useCallback, useState } from "react";
import { activateRightPanelByKey } from "../components/common/rightPanelCoordinator";

/** An open request also reveals an already mounted, collapsed or background tab. */
export function useRightPanelState<T>(registryKey: string, closedValue: T) {
  const [value, setValue] = useState<T>(closedValue);
  const setPanelValue = useCallback(
    (next: T) => {
      setValue(next);
      if (!Object.is(next, closedValue)) activateRightPanelByKey(registryKey);
    },
    [registryKey, closedValue],
  );
  return [value, setPanelValue] as const;
}
