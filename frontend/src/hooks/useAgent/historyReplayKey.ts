/** Type and length prefixes keep tuple boundaries unambiguous without serializing primitive keys. */
export function historyReplayKey(...values: unknown[]): string {
  let result = "";
  for (const value of values) {
    const type = value === null ? "null" : typeof value;
    const text =
      type === "object" || type === "function"
        ? JSON.stringify(value)
        : String(value);
    const encoded = text ?? "undefined";
    result += type + ":" + encoded.length + ":" + encoded;
  }
  return result;
}
