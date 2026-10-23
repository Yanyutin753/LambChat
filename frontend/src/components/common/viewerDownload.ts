import {
  needsUploadFileCapability,
  resolveUploadFileUrl,
} from "../../services/api/uploadFileUrl";

export function downloadUrl(url: string, fileName?: string): void {
  if (needsUploadFileCapability(url)) {
    void resolveUploadFileUrl(url)
      .then((resolved) => downloadUrl(resolved, fileName))
      .catch((error) => console.warn("File download unavailable", error));
    return;
  }
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName ?? "";
  anchor.click();
}

export function downloadBlob(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob);
  downloadUrl(url, fileName);
  URL.revokeObjectURL(url);
}
