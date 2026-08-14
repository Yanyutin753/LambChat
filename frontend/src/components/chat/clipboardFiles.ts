export type ClipboardFileResult =
  | { kind: "files"; files: File[] }
  | {
      kind: "embedded-image";
      source: string;
      mimeType: EmbeddedImageMimeType;
    }
  | { kind: "invalid-image" }
  | { kind: "none" };

export type EmbeddedImageMimeType =
  | "image/png"
  | "image/jpeg"
  | "image/gif"
  | "image/webp";

type ClipboardFileData = Pick<DataTransfer, "files" | "getData">;

type ClipboardImageWorkerResponse =
  | { ok: true; blob: Blob }
  | { ok: false; message: string };

const EMBEDDED_IMAGE_PATTERN =
  /^data:(image\/(?:png|jpeg|gif|webp));base64,([a-z0-9+/=\s]+)$/i;
const IMAGE_MARKUP_PATTERN = /<img\b/i;
const IMAGE_TAG_PATTERN = /<img\b(?:[^>"']|"[^"]*"|'[^']*')*>/gi;
const SOURCE_ATTRIBUTE_PATTERN =
  /\bsrc\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))/i;

const IMAGE_EXTENSIONS: Record<EmbeddedImageMimeType, string> = {
  "image/png": "png",
  "image/jpeg": "jpg",
  "image/gif": "gif",
  "image/webp": "webp",
};

function classifyEmbeddedImage(
  source: string,
): { source: string; mimeType: EmbeddedImageMimeType } | null {
  const match = source.match(EMBEDDED_IMAGE_PATTERN);
  if (!match) return null;
  if (!match[2].replace(/\s/g, "")) return null;
  return {
    source,
    mimeType: match[1].toLowerCase() as EmbeddedImageMimeType,
  };
}

function getClipboardImageSources(html: string): string[] {
  return (html.match(IMAGE_TAG_PATTERN) ?? []).flatMap((tag) => {
    const match = tag.match(SOURCE_ATTRIBUTE_PATTERN);
    const source = match?.[1] ?? match?.[2] ?? match?.[3];
    return source ? [source] : [];
  });
}

export function classifyClipboardFiles(
  clipboardData: ClipboardFileData,
): ClipboardFileResult {
  const nativeFiles = Array.from(clipboardData.files);
  const usableNativeFiles = nativeFiles.filter((file) => file.size > 0);
  if (usableNativeFiles.length > 0) {
    return { kind: "files", files: usableNativeFiles };
  }

  const html = clipboardData.getData("text/html");
  if (html) {
    for (const source of getClipboardImageSources(html)) {
      const embedded = classifyEmbeddedImage(source);
      if (embedded) return { kind: "embedded-image", ...embedded };
    }
    if (IMAGE_MARKUP_PATTERN.test(html)) return { kind: "invalid-image" };
  }

  if (nativeFiles.length > 0) return { kind: "invalid-image" };
  return { kind: "none" };
}

export async function decodeEmbeddedClipboardImage(
  source: string,
  mimeType: EmbeddedImageMimeType,
  signal?: AbortSignal,
): Promise<File> {
  const embedded = classifyEmbeddedImage(source);
  if (!embedded || embedded.mimeType !== mimeType) {
    throw new Error("Unsupported embedded clipboard image");
  }
  if (signal?.aborted) throw createAbortError();

  let blob: Blob;
  try {
    blob = await decodeEmbeddedImageInWorker(source, mimeType, signal);
  } catch (error) {
    if (isAbortError(error)) throw error;
    blob = await decodeEmbeddedImageLocally(source, mimeType, signal);
  }

  if (blob.size <= 0 || blob.type !== mimeType) {
    throw new Error("Embedded clipboard image is empty or has an invalid type");
  }
  return new File([blob], `pasted-image.${IMAGE_EXTENSIONS[mimeType]}`, {
    type: mimeType,
  });
}

function decodeEmbeddedImageInWorker(
  source: string,
  mimeType: EmbeddedImageMimeType,
  signal?: AbortSignal,
): Promise<Blob> {
  return new Promise((resolve, reject) => {
    let worker: Worker;
    try {
      worker = new Worker(
        new URL("../../workers/clipboardImageWorker.ts", import.meta.url),
        { type: "module" },
      );
    } catch (error) {
      reject(error);
      return;
    }

    const cleanup = () => {
      signal?.removeEventListener("abort", handleAbort);
      worker.terminate();
    };
    const handleAbort = () => {
      cleanup();
      reject(createAbortError());
    };
    worker.onmessage = (event: MessageEvent<ClipboardImageWorkerResponse>) => {
      cleanup();
      if (event.data.ok) resolve(event.data.blob);
      else reject(new Error(event.data.message));
    };
    worker.onerror = (event) => {
      cleanup();
      reject(new Error(event.message || "Clipboard image worker failed"));
    };
    signal?.addEventListener("abort", handleAbort, { once: true });
    worker.postMessage({ source, mimeType });
  });
}

async function decodeEmbeddedImageLocally(
  source: string,
  mimeType: EmbeddedImageMimeType,
  signal?: AbortSignal,
): Promise<Blob> {
  const response = signal
    ? await fetch(source, { signal })
    : await fetch(source);
  const blob = await response.blob();
  if (blob.type !== mimeType) {
    throw new Error("Embedded clipboard image has an invalid type");
  }
  return blob;
}

function createAbortError(): DOMException {
  return new DOMException("Clipboard image decode aborted", "AbortError");
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
