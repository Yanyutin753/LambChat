const marker = "[activity log saved to:";
const removedReceipt = "[Unverified activity receipt removed.]";

/** Display projection only: provider reasoning signatures and replay messages stay intact. */
export function stripActivityReferences(
  content: string,
  streaming = false,
): string {
  const text = content.replace(
    /\[activity log saved to:[^\]]*(?:\]|$)/gi,
    removedReceipt,
  );
  if (streaming) {
    for (
      let size = Math.min(text.length, marker.length - 1);
      size > 0;
      size--
    ) {
      if (marker.startsWith(text.slice(-size).toLowerCase()))
        return text.slice(0, -size);
    }
  }
  return text;
}
