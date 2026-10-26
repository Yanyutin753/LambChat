import i18n from "i18next";
import toast from "react-hot-toast";
import { getOwnUploadFileUrl } from "../../services/api/uploadFileUrl";
import { buildUploadProxyUrl } from "../../services/api/config";
import { fetchUploadFile } from "../documents/documentFetchCache";

export function downloadUrl(url: string, fileName?: string): void {
  if (getOwnUploadFileUrl(url)) {
    void fetchUploadFile(
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
        downloadBlob(await response.blob(), name);
      })
      .catch((error) => {
        console.warn("File download unavailable", error);
        toast.error(i18n.t("chat.message.downloadFailed"));
      });
    return;
  }
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName ?? "";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

export function downloadBlob(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob);
  downloadUrl(url, fileName);
  // Browsers may consume the download after the click handler returns.
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
