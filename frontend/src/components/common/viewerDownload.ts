import i18n from "i18next";
import toast from "react-hot-toast";
import { isShellAvailable } from "../../services/tauri/sandboxShell";
import { saveDesktopFile } from "../../services/tauri/saveFile";
import {
  getOwnUploadFileUrl,
  resolveUploadFileUrl,
} from "../../services/api/uploadFileUrl";
import {
  buildUploadProxyUrl,
  isNativeAppRuntime,
} from "../../services/api/config";
import { fetchUploadFile } from "../documents/documentFetchCache";
import { bytesToBase64 } from "../../utils/bytesToBase64";

async function saveMobileFile(blob: Blob, fileName: string): Promise<void> {
  const { Filesystem, Directory } = await import("@capacitor/filesystem");
  const safeFileName = fileName.split(/[\\/]/).pop() || "download";
  const bytes = new Uint8Array(await blob.arrayBuffer());
  const written = await Filesystem.writeFile({
    path: safeFileName,
    data: bytesToBase64(bytes),
    directory: Directory.Documents,
    recursive: true,
  });

  const share = navigator.share;
  if (share && typeof File !== "undefined") {
    try {
      await share.call(navigator, {
        title: safeFileName,
        files: [new File([blob], safeFileName, { type: blob.type })],
      });
      return;
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
    }
  }
  window.open(written.uri, "_blank", "noopener,noreferrer");
}

function fileNameFromUrl(url: string): string {
  try {
    return (
      decodeURIComponent(
        new URL(url, window.location.href).pathname.split("/").pop() || "",
      ) || "download"
    );
  } catch {
    return "download";
  }
}

function triggerBrowserDownload(url: string, fileName?: string): void {
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName ?? "";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

/**
 * Prefetch the whole file and save it through the shell dialog or a blob
 * anchor. Native shells need this: their webview origin differs from the
 * real server, so a signed URL is cross-origin there and the `download`
 * attribute would be ignored (the webview would navigate instead).
 */
function downloadViaPrefetch(url: string, fileName?: string): Promise<void> {
  return fetchUploadFile(
    buildUploadProxyUrl(url, undefined, { force: true }) || url,
  )
    .then(async (response) => {
      const name = fileName || fileNameFromUrl(response.url || url);
      await downloadBlob(await response.blob(), name);
    })
    .catch(() => {
      toast.error(i18n.t("chat.message.downloadFailed"));
    });
}

export function downloadUrl(url: string, fileName?: string): Promise<void> {
  if (isShellAvailable()) {
    return downloadViaPrefetch(url, fileName);
  }
  if (getOwnUploadFileUrl(url)) {
    if (isNativeAppRuntime()) {
      return downloadViaPrefetch(url, fileName);
    }
    // Browser: hand the signed same-origin proxy URL straight to the native
    // download so the prompt appears immediately instead of after a full
    // in-memory prefetch. proxy=true keeps the final response same-origin,
    // which the `download` attribute needs to override inline disposition.
    return resolveUploadFileUrl(url)
      .then((signed) => {
        const target =
          buildUploadProxyUrl(signed, undefined, { force: true }) || signed;
        triggerBrowserDownload(target, fileName || fileNameFromUrl(signed));
      })
      .catch(() => {
        toast.error(i18n.t("chat.message.downloadFailed"));
      });
  }
  triggerBrowserDownload(url, fileName);
  return Promise.resolve();
}

export function downloadBlob(blob: Blob, fileName: string): Promise<void> {
  if (isShellAvailable()) {
    return saveDesktopFile(blob, fileName)
      .then(() => undefined)
      .catch(() => {
        toast.error(i18n.t("chat.message.downloadFailed"));
      });
  }
  if (isNativeAppRuntime()) {
    return saveMobileFile(blob, fileName).catch(() => {
      toast.error(i18n.t("chat.message.downloadFailed"));
    });
  }
  const url = URL.createObjectURL(blob);
  triggerBrowserDownload(url, fileName);
  // Browsers may consume the download after the click handler returns.
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
  return Promise.resolve();
}
