import JSZip from "jszip";
import { buildUploadProxyUrl } from "../services/api/config";

export interface ExportProjectZipOptions {
  /** Reject before creating the ZIP if any binary URL cannot be downloaded. */
  failOnBinaryError?: boolean;
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
    const failedPaths = (
      await Promise.all(
        Object.entries(binaryFiles).map(async ([path, url]) => {
          try {
            const readUrl = buildUploadProxyUrl(url) || url;
            const resp = await fetch(readUrl);
            if (!resp.ok) return path;
            const buffer = await resp.arrayBuffer();
            const normalizedPath = path.startsWith("/") ? path.slice(1) : path;
            if (normalizedPath) {
              zip.file(normalizedPath, buffer);
            }
            return null;
          } catch {
            // 跳过下载失败的二进制文件
            return path;
          }
        }),
      )
    ).filter((path): path is string => path !== null);

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
  a.download = `${projectName.replace(
    /[^a-zA-Z0-9_\u4e00-\u9fa5-]/g,
    "_",
  )}.zip`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
