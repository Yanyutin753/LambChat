import JSZip from "jszip";
import { buildUploadProxyUrl } from "../services/api/config";
import { fetchUploadFile } from "../components/documents/documentFetchCache";

export interface ExportProjectZipOptions {
  /** Reject before creating the ZIP if any binary URL cannot be downloaded. */
  failOnBinaryError?: boolean;
  /** Resource guards for browser and mobile WebView ZIP generation. */
  maxBinaryFiles?: number;
  maxBinaryBytes?: number;
  maxBinaryFileBytes?: number;
  binaryConcurrency?: number;
  binaryTimeoutMs?: number;
}

const DEFAULT_MAX_BINARY_FILES = 50;
const DEFAULT_MAX_BINARY_BYTES = 100 * 1024 * 1024;
const DEFAULT_MAX_BINARY_FILE_BYTES = 25 * 1024 * 1024;
const DEFAULT_BINARY_CONCURRENCY = 3;
const DEFAULT_BINARY_TIMEOUT_MS = 30_000;

function positiveInteger(value: number | undefined, fallback: number): number {
  return Number.isInteger(value) && value !== undefined && value > 0
    ? value
    : fallback;
}

async function readResponseWithinLimit(
  response: Response,
  maxBytes: number,
): Promise<Uint8Array> {
  const contentLength = Number(response.headers.get("content-length"));
  if (Number.isFinite(contentLength) && contentLength > maxBytes) {
    throw new Error("Binary file exceeds ZIP download limit");
  }

  if (!response.body) {
    const buffer = new Uint8Array(await response.arrayBuffer());
    if (buffer.byteLength > maxBytes) {
      throw new Error("Binary file exceeds ZIP download limit");
    }
    return buffer;
  }

  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let totalBytes = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      totalBytes += value.byteLength;
      if (totalBytes > maxBytes) {
        await reader.cancel();
        throw new Error("Binary file exceeds ZIP download limit");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }

  const result = new Uint8Array(totalBytes);
  let offset = 0;
  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return result;
}

export async function exportProjectZip(
  files: Record<string, string>,
  projectName: string,
  binaryFiles?: Record<string, string>,
  options: ExportProjectZipOptions = {},
): Promise<void> {
  const zip = new JSZip();

  // 添加文本文件
  for (const [path, content] of Object.entries(files)) {
    const normalizedPath = path.startsWith("/") ? path.slice(1) : path;
    if (normalizedPath) {
      zip.file(normalizedPath, content);
    }
  }

  // 添加二进制文件（从 OSS URL 拉取）
  if (binaryFiles) {
    const resourceGuardsEnabled =
      options.failOnBinaryError === true ||
      options.maxBinaryFiles !== undefined ||
      options.maxBinaryBytes !== undefined ||
      options.maxBinaryFileBytes !== undefined ||
      options.binaryTimeoutMs !== undefined;
    const allEntries = Object.entries(binaryFiles);
    const maxFiles = resourceGuardsEnabled
      ? positiveInteger(options.maxBinaryFiles, DEFAULT_MAX_BINARY_FILES)
      : allEntries.length;
    const maxBytes = resourceGuardsEnabled
      ? positiveInteger(options.maxBinaryBytes, DEFAULT_MAX_BINARY_BYTES)
      : Number.MAX_SAFE_INTEGER;
    const maxFileBytes = Math.min(
      resourceGuardsEnabled
        ? positiveInteger(
            options.maxBinaryFileBytes,
            DEFAULT_MAX_BINARY_FILE_BYTES,
          )
        : Number.MAX_SAFE_INTEGER,
      maxBytes,
    );
    const concurrency = Math.min(
      positiveInteger(options.binaryConcurrency, DEFAULT_BINARY_CONCURRENCY),
      8,
    );
    const timeoutMs = resourceGuardsEnabled
      ? positiveInteger(options.binaryTimeoutMs, DEFAULT_BINARY_TIMEOUT_MS)
      : undefined;
    if (options.failOnBinaryError && allEntries.length > maxFiles) {
      throw new Error(`Binary ZIP limit exceeded: at most ${maxFiles} files`);
    }

    const entries = allEntries.slice(0, maxFiles);
    const failedPaths = allEntries.slice(maxFiles).map(([path]) => path);
    let nextIndex = 0;
    let downloadedBytes = 0;

    const downloadWorker = async () => {
      while (nextIndex < entries.length) {
        const index = nextIndex;
        nextIndex += 1;
        const [path, sourceUrl] = entries[index];
        const controller = new AbortController();
        const timeoutId = timeoutMs
          ? window.setTimeout(() => controller.abort(), timeoutMs)
          : undefined;
        try {
          const readUrl = buildUploadProxyUrl(sourceUrl) || sourceUrl;
          const response = await fetchUploadFile(readUrl, {
            signal: controller.signal,
          });
          if (!response.ok) throw new Error("Binary download failed");
          const remainingBytes = Math.max(maxBytes - downloadedBytes, 0);
          const buffer = await readResponseWithinLimit(
            response,
            Math.min(maxFileBytes, remainingBytes),
          );
          if (downloadedBytes + buffer.byteLength > maxBytes) {
            throw new Error("Binary ZIP exceeds total download limit");
          }
          downloadedBytes += buffer.byteLength;
          const normalizedPath = path.startsWith("/") ? path.slice(1) : path;
          if (normalizedPath) zip.file(normalizedPath, buffer);
        } catch {
          // Best-effort callers keep the previous behavior; strict callers reject below.
          failedPaths.push(path);
        } finally {
          if (timeoutId !== undefined) window.clearTimeout(timeoutId);
        }
      }
    };

    await Promise.all(
      Array.from(
        { length: Math.min(concurrency, entries.length) },
        downloadWorker,
      ),
    );

    if (options.failOnBinaryError && failedPaths.length > 0) {
      const fileLabel = failedPaths.length === 1 ? "file" : "files";
      throw new Error(
        `Failed to download ${
          failedPaths.length
        } binary ${fileLabel}: ${failedPaths.join(", ")}`,
      );
    }
  }

  const blob = await zip.generateAsync({ type: "blob" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const safeProjectName =
    projectName.normalize("NFC").replace(/[^\p{L}\p{M}\p{N}_-]/gu, "_") ||
    "project";
  a.download = `${safeProjectName}.zip`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
