interface CompressionRequest {
  file: File;
  maxDimension: number;
  targetSizeKB: number;
}

type CompressionResponse =
  | {
      ok: true;
      blob: Blob;
      mimeType: string;
      extension: string;
    }
  | {
      ok: false;
      code: "unsupported" | "failed";
      message: string;
    };

const INITIAL_QUALITY = 0.85;
const MIN_QUALITY = 0.2;
const MAX_ENCODE_ATTEMPTS = 4;

function post(response: CompressionResponse) {
  self.postMessage(response);
}

self.onmessage = async (event: MessageEvent<CompressionRequest>) => {
  if (
    typeof createImageBitmap !== "function" ||
    typeof OffscreenCanvas === "undefined"
  ) {
    post({
      ok: false,
      code: "unsupported",
      message: "Worker image APIs are unavailable",
    });
    return;
  }

  let bitmap: ImageBitmap | null = null;
  try {
    const { file, maxDimension, targetSizeKB } = event.data;
    bitmap = await createImageBitmap(file);
    let { width, height } = bitmap;
    if (width > maxDimension || height > maxDimension) {
      const ratio = Math.min(maxDimension / width, maxDimension / height);
      width = Math.round(width * ratio);
      height = Math.round(height * ratio);
    }

    const canvas = new OffscreenCanvas(width, height);
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Canvas 2D context is unavailable");
    context.drawImage(bitmap, 0, 0, width, height);

    if (file.type === "image/png") {
      const blob = await canvas.convertToBlob({ type: "image/png" });
      post({
        ok: true,
        blob,
        mimeType: "image/png",
        extension: ".png",
      });
      return;
    }

    const targetBytes = targetSizeKB * 1024;
    let low = MIN_QUALITY;
    let high = INITIAL_QUALITY;
    let smallest: Blob | null = null;
    let bestWithinTarget: Blob | null = null;

    for (let attempt = 0; attempt < MAX_ENCODE_ATTEMPTS; attempt += 1) {
      const quality = (low + high) / 2;
      const blob = await canvas.convertToBlob({
        type: "image/jpeg",
        quality,
      });
      if (!smallest || blob.size < smallest.size) smallest = blob;
      if (blob.size <= targetBytes) {
        bestWithinTarget = blob;
        low = quality;
      } else {
        high = quality;
      }
    }

    const blob = bestWithinTarget ?? smallest;
    if (!blob) throw new Error("Image encoding produced no output");
    post({
      ok: true,
      blob,
      mimeType: "image/jpeg",
      extension: ".jpg",
    });
  } catch (error) {
    post({
      ok: false,
      code: "failed",
      message:
        error instanceof Error ? error.message : "Image compression failed",
    });
  } finally {
    bitmap?.close();
  }
};
