interface ClipboardImageRequest {
  source: string;
  mimeType: string;
}

type ClipboardImageResponse =
  | { ok: true; blob: Blob }
  | { ok: false; message: string };

self.onmessage = async (event: MessageEvent<ClipboardImageRequest>) => {
  try {
    const { source, mimeType } = event.data;
    const response = await fetch(source);
    const blob = await response.blob();
    if (blob.size <= 0 || blob.type !== mimeType) {
      throw new Error(
        "Embedded clipboard image is empty or has an invalid type",
      );
    }
    self.postMessage({ ok: true, blob } satisfies ClipboardImageResponse);
  } catch (error) {
    self.postMessage({
      ok: false,
      message:
        error instanceof Error
          ? error.message
          : "Clipboard image decode failed",
    } satisfies ClipboardImageResponse);
  }
};
