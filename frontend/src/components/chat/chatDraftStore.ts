import { useCallback, useState, useSyncExternalStore } from "react";
import toast from "react-hot-toast";
import i18n from "../../i18n";
import { API_BASE } from "../../services/api/config";
import { getStoredServerUrl } from "../../services/api/serverUrlStore";
import type { MessageAttachment } from "../../types";
import type {
  ComposerSnapshot,
  SerializedComposerNode,
} from "./richComposer/composerTypes";
import { projectComposerSnapshot } from "./richComposer/composerProjection";

interface ChatDraft {
  composer?: ComposerSnapshot;
  attachments: MessageAttachment[];
}

const emptyDraft: ChatDraft = { attachments: [] };
const drafts = new Map<string, ChatDraft>();
const listeners = new Set<() => void>();

export function getChatDraftKey(
  userId: string | undefined,
  sessionId: string | null,
): string | undefined {
  if (!userId) return undefined;
  let server = API_BASE;
  try {
    server = getStoredServerUrl() || server;
  } catch {
    /* Storage may be unavailable. */
  }
  return `chatDraft:${JSON.stringify([server, userId, sessionId])}`;
}

function isNode(value: unknown): value is SerializedComposerNode {
  if (!value || typeof value !== "object") return false;
  const node = value as SerializedComposerNode;
  return (
    typeof node.type === "string" &&
    (node.status === undefined ||
      ["uploading", "ready", "failed"].includes(node.status)) &&
    [node.text, node.referenceId, node.fileName, node.skillName].every(
      (value) => value === undefined || typeof value === "string",
    ) &&
    (node.tags === undefined ||
      (Array.isArray(node.tags) &&
        node.tags.every((tag) => typeof tag === "string"))) &&
    (node.children === undefined ||
      (Array.isArray(node.children) && node.children.every(isNode)))
  );
}

function isAttachment(value: unknown): value is MessageAttachment {
  if (!value || typeof value !== "object") return false;
  const attachment = value as MessageAttachment;
  return (
    [attachment.id, attachment.key, attachment.name, attachment.mimeType].every(
      (value) => typeof value === "string",
    ) &&
    [
      attachment.url,
      attachment.localOriginalText,
      attachment.composerReferenceId,
      attachment.uploadError,
    ].every((value) => value === undefined || typeof value === "string") &&
    ["image", "video", "audio", "document"].includes(attachment.type) &&
    typeof attachment.size === "number" &&
    Number.isFinite(attachment.size) &&
    attachment.size >= 0
  );
}

export function readChatDraft(key?: string): ChatDraft {
  if (!key) return emptyDraft;
  const cached = drafts.get(key);
  if (cached) return cached;
  let draft = emptyDraft;
  try {
    const stored = JSON.parse(localStorage.getItem(key) || "null");
    if (stored?.version === 1 && Array.isArray(stored.attachments)) {
      const composer =
        stored.composer?.version === 1 &&
        isNode(stored.composer.editorState?.root)
          ? (stored.composer as ComposerSnapshot)
          : undefined;
      draft = {
        composer,
        attachments: stored.attachments
          .filter(isAttachment)
          .map((attachment: MessageAttachment) => ({
            ...attachment,
            // A page reload cannot resume an upload from a serialized File.
            ...(attachment.isUploading
              ? { isUploading: false, uploadError: "interrupted" }
              : {}),
            ...(attachment.url?.startsWith("blob:") ? { url: undefined } : {}),
          })),
      };
    }
  } catch {
    /* Ignore corrupt or unavailable storage; editing must still work. */
  }
  drafts.set(key, draft);
  return draft;
}

export function updateChatDraft(
  key: string | undefined,
  update: (draft: ChatDraft) => ChatDraft,
): void {
  if (!key) return;
  const next = update(readChatDraft(key));
  drafts.set(key, next);
  try {
    if (
      (!next.composer || projectComposerSnapshot(next.composer).isEmpty) &&
      !next.attachments.length
    ) {
      localStorage.removeItem(key);
    } else {
      localStorage.setItem(key, JSON.stringify({ version: 1, ...next }));
    }
  } catch {
    toast.error(i18n.t("chat.draftSaveFailed"), {
      id: "chat-draft-save-failed",
    });
  }
  for (const listener of listeners) listener();
}

export function subscribeChatDraft(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useChatDraftAttachments(key?: string) {
  const [local, setLocal] = useState<MessageAttachment[]>([]);
  const attachments = useSyncExternalStore(
    subscribeChatDraft,
    useCallback(() => readChatDraft(key).attachments, [key]),
  );
  const setAttachments = useCallback(
    (
      update:
        | MessageAttachment[]
        | ((current: MessageAttachment[]) => MessageAttachment[]),
    ) => {
      if (!key) {
        setLocal(update);
        return;
      }
      updateChatDraft(key, (draft) => ({
        ...draft,
        attachments:
          typeof update === "function" ? update(draft.attachments) : update,
      }));
    },
    [key],
  );
  return [key ? attachments : local, setAttachments] as const;
}
