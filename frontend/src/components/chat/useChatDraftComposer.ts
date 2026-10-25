import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import {
  readChatDraft,
  subscribeChatDraft,
  updateChatDraft,
} from "./chatDraftStore";
import type { ComposerSnapshot } from "./richComposer/composerTypes";
import type { RichChatComposerHandle } from "./richComposer/RichChatComposer";
import { projectComposerSnapshot } from "./richComposer/composerProjection";

export function useChatDraftComposer(
  key: string | undefined,
  composerRef: { current: RichChatComposerHandle | null },
) {
  const snapshot = useSyncExternalStore(
    subscribeChatDraft,
    useCallback(() => readChatDraft(key).composer, [key]),
  );
  const [initialDraft] = useState(snapshot);
  const [initialProjection] = useState(
    () => initialDraft && projectComposerSnapshot(initialDraft),
  );
  const lastSnapshot = useRef(snapshot);
  useEffect(() => {
    // A failed send can arrive after the user has returned to this conversation.
    if (snapshot && snapshot !== lastSnapshot.current) {
      lastSnapshot.current = snapshot;
      composerRef.current?.restoreSnapshot(snapshot);
    }
  }, [snapshot, composerRef]);
  const saveDraft = useCallback(
    (composer: ComposerSnapshot) => {
      lastSnapshot.current = composer;
      updateChatDraft(key, (draft) => ({ ...draft, composer }));
    },
    [key],
  );
  return { initialDraft, initialProjection, saveDraft };
}
