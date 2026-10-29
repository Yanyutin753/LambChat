import i18n from "i18next";
import toast from "react-hot-toast";
import { isShellAvailable } from "../../services/tauri/sandboxShell";
import { saveDesktopFile } from "../../services/tauri/saveFile";
import { getOwnUploadFileUrl } from "../../services/api/uploadFileUrl";
import { buildUploadProxyUrl } from "../../services/api/config";
import { fetchUploadFile } from "../documents/documentFetchCache";

export function downloadUrl(url: string, fileName?: string): Promise<void> {
  if (getOwnUploadFileUrl(url) || isShellAvailable()) {
    return fetchUploadFile(
      buildUploadProxyUrl(url, undefined, { force: true }) || url,
    )
      .then(async (response) => {
        const name =
          fileName ||
          decodeURIComponent(
            new URL(response.url || url, window.location.href).pathname
              .split("/")
              .pop() || "download",
          );
        await downloadBlob(await response.blob(), name);
      })
      .catch(() => {
        toast.error(i18n.t("chat.message.downloadFailed"));
      });
  }
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName ?? "";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
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
  const url = URL.createObjectURL(blob);
  downloadUrl(url, fileName);
  // Browsers may consume the download after the click handler returns.
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
  return Promise.resolve();
}
