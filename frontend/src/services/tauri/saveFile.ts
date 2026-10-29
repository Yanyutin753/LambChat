/** Save downloaded bytes without relying on a WebView's browser download UI. */
export async function saveDesktopFile(
  blob: Blob,
  fileName: string,
): Promise<boolean> {
  const { invoke } = await import("@tauri-apps/api/core");
  // IPC headers must be ASCII; JSON escapes preserve Unicode filenames losslessly.
  const name = JSON.stringify(fileName).replace(
    /[\u007f-\uffff]/g,
    (char) => `\\u${char.charCodeAt(0).toString(16).padStart(4, "0")}`,
  );
  return invoke<boolean>("desktop_save_file", await blob.arrayBuffer(), {
    headers: { "x-file-name": name },
  });
}
