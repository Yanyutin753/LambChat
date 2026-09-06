/**
 * Uint8Array → base64（分块转字符串，避免 spread 展开超调用栈上限）。
 * WebView 内下载流逐块落盘（Filesystem 以 base64 为二进制载体）时使用。
 */
export function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  const step = 0x8000;
  for (let i = 0; i < bytes.length; i += step) {
    binary += String.fromCharCode(...bytes.subarray(i, i + step));
  }
  return btoa(binary);
}
