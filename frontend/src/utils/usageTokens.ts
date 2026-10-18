/** Reported counts do not certify billing or cache denominators. */
export function reportedTokenCount(
  value: unknown,
  field: string,
  unknownFields: readonly string[] | null = [],
): number | null {
  return typeof value === "number" &&
    Number.isFinite(value) &&
    value >= 0 &&
    !unknownFields?.includes(field)
    ? value
    : null;
}
