const MAX_DIMENSION = 1920;
const TARGET_SIZE_KB = 1024;
const INITIAL_QUALITY = 0.85;
const MIN_QUALITY = 0.2;
const QUALITY_STEP = 0.1;
const SMALL_FILE_THRESHOLD_KB = 200;

export interface CompressOptions {
  /** Max width/height in px (default 1920) */
  maxDimension?: number;
  /** Target file size in KB (default 1024) */
  targetSizeKB?: number;
  /** Skip compression if file is already under this size in KB (default 200) */
  skipBelowKB?: number;
  /** Abort in-flight worker compression. */
  signal?: AbortSignal;
  /** Compatibility behavior when worker image APIs are unavailable. */
  fallback?: "original" | "main-thread";
}

type CompressionWorkerResponse =
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

/**
 * Compress an image file using Canvas API.
 * - GIF files are passed through as-is (compression would destroy animation).
 * - PNG files keep PNG format (preserve transparency).
 * - Other images (JPEG, WebP, BMP, etc.) are output as JPEG.
 */
export async function compressImageFile(
  file: File,
  options?: CompressOptions,
): Promise<File> {
  const {
    maxDimension = MAX_DIMENSION,
    targetSizeKB = TARGET_SIZE_KB,
    skipBelowKB = SMALL_FILE_THRESHOLD_KB,
    signal,
    fallback = "original",
  } = options ?? {};

  if (signal?.aborted) throw createAbortError();

  // Skip tiny files
  if (file.size < skipBelowKB * 1024) return file;

  // Skip GIF — canvas encoding destroys animation
  if (file.type === "image/gif") return file;

  // Skip SVG — vector format, canvas rasterization is undesirable
  if (file.type === "image/svg+xml") return file;

  try {
    const response = await compressImageInWorker(file, {
      maxDimension,
      targetSizeKB,
      signal,
    });
    if (response.ok) {
      if (response.blob.size >= file.size) return file;
      return blobToFile(
        response.blob,
        replaceExtension(file.name, response.extension),
        response.mimeType,
      );
    }
  } catch (error) {
    if (isAbortError(error)) throw error;
  }
  if (fallback === "main-thread") {
    return compressImageOnMainThread(file, { maxDimension, targetSizeKB });
  }
  return file;
}

function compressImageInWorker(
  file: File,
  options: {
    maxDimension: number;
    targetSizeKB: number;
    signal?: AbortSignal;
  },
): Promise<CompressionWorkerResponse> {
  return new Promise((resolve, reject) => {
    let worker: Worker;
    try {
      worker = new Worker(
        new URL("../workers/imageCompressionWorker.ts", import.meta.url),
        { type: "module" },
      );
    } catch (error) {
      reject(error);
      return;
    }

    const cleanup = () => {
      options.signal?.removeEventListener("abort", handleAbort);
      worker.terminate();
    };
    const handleAbort = () => {
      cleanup();
      reject(createAbortError());
    };

    worker.onmessage = (event: MessageEvent<CompressionWorkerResponse>) => {
      cleanup();
      resolve(event.data);
    };
    worker.onerror = (event) => {
      cleanup();
      reject(new Error(event.message || "Image compression worker failed"));
    };
    options.signal?.addEventListener("abort", handleAbort, { once: true });
    worker.postMessage({
      file,
      maxDimension: options.maxDimension,
      targetSizeKB: options.targetSizeKB,
    });
  });
}

async function compressImageOnMainThread(
  file: File,
  options: { maxDimension: number; targetSizeKB: number },
): Promise<File> {
  const { maxDimension, targetSizeKB } = options;
  const bitmap = await createImageBitmap(file);
  let { width, height } = bitmap;

  // Only downscale if exceeding max dimension
  if (width > maxDimension || height > maxDimension) {
    const ratio = Math.min(maxDimension / width, maxDimension / height);
    width = Math.round(width * ratio);
    height = Math.round(height * ratio);
  }

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return file;

  ctx.drawImage(bitmap, 0, 0, width, height);
  bitmap.close();

  // Determine output MIME type
  const isPng = file.type === "image/png";
  const mimeType = isPng ? "image/png" : "image/jpeg";

  // For PNG, quality param is ignored by toBlob; just do one pass
  if (isPng) {
    const blob = await canvasToBlob(canvas, mimeType, 1);
    if (!blob) return file;
    // If PNG got bigger after resize, keep original
    if (blob.size >= file.size) return file;
    return blobToFile(blob, replaceExtension(file.name, ".png"), mimeType);
  }

  // JPEG / others: iteratively reduce quality
  const targetBytes = targetSizeKB * 1024;
  let quality = INITIAL_QUALITY;

  while (quality >= MIN_QUALITY) {
    const blob = await canvasToBlob(canvas, mimeType, quality);
    if (!blob) return file;

    if (blob.size <= targetBytes || quality <= MIN_QUALITY) {
      // If compressed version is bigger (e.g. tiny original), keep original
      if (blob.size >= file.size) return file;
      const ext = file.name.match(/\.[^.]+$/)?.[0] || ".jpg";
      return blobToFile(blob, replaceExtension(file.name, ext), mimeType);
    }
    quality -= QUALITY_STEP;
  }

  return file;
}

function createAbortError(): DOMException {
  return new DOMException("Image compression aborted", "AbortError");
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function canvasToBlob(
  canvas: HTMLCanvasElement,
  mimeType: string,
  quality: number,
): Promise<Blob | null> {
  return new Promise((resolve) => {
    canvas.toBlob((blob) => resolve(blob), mimeType, quality);
  });
}

function blobToFile(blob: Blob, name: string, mimeType: string): File {
  return new File([blob], name, { type: mimeType, lastModified: Date.now() });
}

function replaceExtension(filename: string, ext: string): string {
  return filename.replace(/\.[^.]+$/, "") + ext;
}
