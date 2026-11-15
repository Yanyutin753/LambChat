/** BOM takes precedence over response charset, as with Windows-generated scripts. */
export function decodePreviewText(
  bytes: Uint8Array,
  charset = "utf-8",
  truncated = false,
): string | null {
  const encoding =
    bytes[0] === 255 && bytes[1] === 254
      ? "utf-16le"
      : bytes[0] === 254 && bytes[1] === 255
        ? "utf-16be"
        : charset;
  try {
    const text = new TextDecoder(encoding, { fatal: true }).decode(bytes, {
      stream: truncated,
    });
    // Preserve tabs/newlines; control bytes indicate a binary file.
    for (const char of text) {
      const code = char.charCodeAt(0);
      if (code < 32 && ![9, 10, 12, 13].includes(code)) return null;
    }
    return text;
  } catch {
    return null;
  }
}

export function formatHexPreview(bytes: Uint8Array): string {
  const lines: string[] = [];
  for (let offset = 0; offset < bytes.length; offset += 16) {
    const row = Array.from(bytes.subarray(offset, offset + 16));
    const hex = row
      .map((byte) => byte.toString(16).padStart(2, "0"))
      .join(" ")
      .padEnd(47);
    const ascii = row
      .map((byte) =>
        byte >= 32 && byte <= 126 ? String.fromCharCode(byte) : ".",
      )
      .join("");
    lines.push(`${offset.toString(16).padStart(8, "0")}  ${hex}  ${ascii}`);
  }
  return lines.join("\n");
}
