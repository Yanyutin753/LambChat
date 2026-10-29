import {
  getFileExtension,
  isImageFile,
  isVideoFile,
  isAudioFile,
  isCodeFile,
} from "../../components/documents/utils/fileTypeChecks";
import { invokeInShell } from "./sandboxShell";
import type { MessageAttachment } from "../../types";

export interface DesktopFile {
  token: string;
  path: string;
  name: string;
  size: number;
  modified: string;
}

const MIME: Record<string, string> = {
  heic: "image/heic",
  heif: "image/heif",
  avif: "image/avif",
  flac: "audio/flac",
  mkv: "video/x-matroska",
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  webp: "image/webp",
  tif: "image/tiff",
  tiff: "image/tiff",
  gif: "image/gif",
  svg: "image/svg+xml",
  bmp: "image/bmp",
  pdf: "application/pdf",
  txt: "text/plain",
  md: "text/markdown",
  csv: "text/csv",
  json: "application/json",
  mp4: "video/mp4",
  mov: "video/quicktime",
  webm: "video/webm",
  mp3: "audio/mpeg",
  wav: "audio/wav",
  m4a: "audio/mp4",
  ogg: "audio/ogg",
};
function mime(name: string): string {
  return (
    MIME[name.split(".").pop()?.toLowerCase() || ""] ||
    "application/octet-stream"
  );
}
export function desktopFileAttachment(
  file: DesktopFile,
  machineId: string,
): MessageAttachment {
  const mimeType = mime(file.name);
  const extension = getFileExtension(file.name);
  const type = isImageFile(extension)
    ? "image"
    : isVideoFile(extension) && !isCodeFile(extension)
      ? "video"
      : isAudioFile(extension)
        ? "audio"
        : "document";
  return {
    id: `local-${file.token}`,
    key: "",
    name: file.name,
    size: file.size,
    type,
    mimeType,
    localFile: { path: file.path, machineId, token: file.token },
  };
}
export function canUseLocalAttachment(
  attachment: MessageAttachment,
  mode: unknown,
  machineId: unknown,
): boolean {
  return (
    !!attachment.localFile &&
    mode === "local" &&
    !!machineId &&
    attachment.localFile.machineId === machineId
  );
}
export function pickDesktopFiles(title: string): Promise<DesktopFile[]> {
  return invokeInShell("desktop_pick_files", { title });
}
export async function readDesktopFile(
  token: string,
  maxBytes: number,
  signal: AbortSignal,
): Promise<File> {
  signal.throwIfAborted();
  const info = await invokeInShell<DesktopFile>("desktop_file_info", { token });
  signal.throwIfAborted();
  if (info.size <= 0 || info.size > maxBytes)
    throw new Error("file_size_limit");
  const parts: Uint8Array<ArrayBuffer>[] = [];
  for (let offset = 0; offset < info.size; ) {
    signal.throwIfAborted();
    const length = Math.min(1024 * 1024, info.size - offset);
    const bytes = await invokeInShell<number[]>("desktop_read_file_chunk", {
      token,
      offset,
      length,
      size: info.size,
      modified: info.modified,
    });
    signal.throwIfAborted();
    if (bytes.length !== length) throw new Error("file_changed");
    parts.push(new Uint8Array(bytes));
    offset += bytes.length;
  }
  return new File(parts, info.name, { type: mime(info.name) });
}
export function revealDesktopFile(token: string): Promise<void> {
  return invokeInShell("desktop_reveal_file", { token });
}

/** Only WebView2 File objects can grant a native receipt; never send a JS path. */
export async function resolveDroppedDesktopFiles(
  files: File[],
  signal?: AbortSignal,
): Promise<(DesktopFile | null)[] | null> {
  const webview = (
    window as unknown as {
      chrome?: {
        webview?: {
          postMessageWithAdditionalObjects?: (
            message: unknown,
            files: File[],
          ) => void;
        };
      };
    }
  ).chrome?.webview;
  if (!webview) return null;
  if (!webview.postMessageWithAdditionalObjects)
    throw new Error("file_drop_unavailable");
  signal?.throwIfAborted();
  const { listen } = await import("@tauri-apps/api/event");
  signal?.throwIfAborted();
  const requestId = crypto.randomUUID().replaceAll("-", "");
  return new Promise((resolve, reject) => {
    let stop: (() => void) | undefined;
    let done = false;
    const finish = (value: (DesktopFile | null)[] | null, error?: Error) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
      stop?.();
      if (error) reject(error);
      else resolve(value);
    };
    const abort = () =>
      finish(null, new DOMException("File drop cancelled", "AbortError"));
    const timer = setTimeout(
      () => finish(null, new Error("file_drop_unavailable")),
      3000,
    );
    signal?.addEventListener("abort", abort, { once: true });
    void listen<{
      requestId: string;
      files: (DesktopFile | null)[];
      error?: boolean;
    }>("desktop-drop-resolved", ({ payload }) => {
      if (payload.requestId !== requestId) return;
      if (
        payload.error ||
        !Array.isArray(payload.files) ||
        payload.files.length !== files.length
      )
        finish(null, new Error("file_drop_unavailable"));
      else finish(payload.files);
    })
      .then((unlisten) => {
        if (done) {
          unlisten();
          return;
        }
        stop = unlisten;
        webview.postMessageWithAdditionalObjects!(
          { kind: "lambchat-file-drop", requestId },
          files,
        );
      })
      .catch(() => finish(null, new Error("file_drop_unavailable")));
  });
}

/** Unknown defaults must never turn a restored original-path draft into an upload. */
export function resolveDesktopAttachmentEnvironment(input: {
  agent?: { supports_sandbox?: boolean };
  mode: unknown;
  selectedMachine: unknown;
  defaultMachineId: string | null;
  currentMachineId: string | null;
}): { mode: "pending" | "cloud" | "local"; machineId: string | null } {
  const pending = { mode: "pending" as const, machineId: null };
  if (!input.agent) return pending;
  if (!input.agent.supports_sandbox || input.mode === "cloud")
    return { mode: "cloud", machineId: null };
  if (input.mode !== "local") return pending;
  const machineId =
    typeof input.selectedMachine === "string" && input.selectedMachine
      ? input.selectedMachine
      : input.defaultMachineId;
  if (!machineId || !input.currentMachineId) return pending;
  return { mode: "local", machineId };
}
