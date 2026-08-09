import { useCallback, useMemo, useReducer } from "react";
import {
  createDraftAttachmentState,
  reduceDraftAttachments,
  selectActiveAttachments,
  selectSubmitAttachments,
  type DraftAttachmentAction,
  type DraftAttachmentResource,
} from "./draftAttachmentRegistry";

export function useDraftAttachmentRegistry() {
  const [state, dispatch] = useReducer(
    reduceDraftAttachments,
    undefined,
    createDraftAttachmentState,
  );
  const insert = useCallback(
    (resource: DraftAttachmentResource) =>
      dispatch({ type: "insert", resource }),
    [],
  );
  const reconcileActive = useCallback(
    (activeReferenceIds: string[]) =>
      dispatch({ type: "reconcile-active", activeReferenceIds }),
    [],
  );
  const act = useCallback(
    (action: DraftAttachmentAction) => dispatch(action),
    [],
  );

  return {
    state,
    dispatch: act,
    insert,
    reconcileActive,
    activeAttachments: useMemo(() => selectActiveAttachments(state), [state]),
    submitAttachments: useMemo(() => selectSubmitAttachments(state), [state]),
  };
}
