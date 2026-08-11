export type ClipboardFileResult =
  | { kind: "files"; files: File[] }
  | { kind: "invalid-image" }
  | { kind: "none" };

type ClipboardFileData = Pick<DataTransfer, "files" | "getData">;

const EMBEDDED_IMAGE_PATTERN =
  /^data:(image\/(?:png|jpeg|gif|webp));base64,([a-z0-9+/=\s]+)$/i;
const IMAGE_MARKUP_PATTERN = /<img\b/i;
const IMAGE_TAG_PATTERN = /<img\b(?:[^>"']|"[^"]*"|'[^']*')*>/gi;
const SOURCE_ATTRIBUTE_PATTERN =
  /\bsrc\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))/i;

const IMAGE_EXTENSIONS: Record<string, string> = {
  "image/png": "png",
  "image/jpeg": "jpg",
  "image/gif": "gif",
  "image/webp": "webp",
};

function decodeEmbeddedImage(source: string): File | null {
  const match = source.match(EMBEDDED_IMAGE_PATTERN);
  if (!match) return null;

  const mimeType = match[1].toLowerCase();
  try {
    const decoded = atob(match[2].replace(/\s/g, ""));
    if (!decoded) return null;
    const bytes = Uint8Array.from(decoded, (character) =>
      character.charCodeAt(0),
    );
    return new File([bytes], `pasted-image.${IMAGE_EXTENSIONS[mimeType]}`, {
      type: mimeType,
    });
  } catch {
    return null;
  }
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
      const recovered = decodeEmbeddedImage(source);
      if (recovered) return { kind: "files", files: [recovered] };
    }
    if (IMAGE_MARKUP_PATTERN.test(html)) return { kind: "invalid-image" };
  }

  if (nativeFiles.length > 0) return { kind: "invalid-image" };
  return { kind: "none" };
}
