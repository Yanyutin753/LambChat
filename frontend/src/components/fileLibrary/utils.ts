import type { RevealedFileItem } from "../../services/api";
import { formatFileSize } from "../documents/utils";

/* ── Time formatting ──────────────────────────────────── */

export function formatTimeAgo(
  t: (key: string, opts?: Record<string, unknown>) => string,
  isoString: string,
): string {
  const diffMs = Date.now() - new Date(isoString).getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return t("fileLibrary.timeAgo.justNow");
  if (diffMin < 60)
    return t("fileLibrary.timeAgo.minutesAgo", { count: diffMin });
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return t("fileLibrary.timeAgo.hoursAgo", { count: diffHr });
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 30) return t("fileLibrary.timeAgo.daysAgo", { count: diffDay });
  return t("fileLibrary.timeAgo.monthsAgo", {
    count: Math.floor(diffDay / 30),
  });
}

/* ── File extension ───────────────────────────────────── */

export function getExt(name: string): string {
  const idx = name.lastIndexOf(".");
  return idx > 0 ? name.slice(idx + 1).toUpperCase() : "";
}

/* ── Build metadata line ──────────────────────────────── */

export function buildMeta(
  file: RevealedFileItem,
  t: (key: string, opts?: Record<string, unknown>) => string,
): string {
  const isProject = file.file_type === "project";
  const ext = isProject ? "" : getExt(file.file_name);
  const parts: string[] = [];
  if (!isProject && file.file_size > 0)
    parts.push(formatFileSize(file.file_size));
  if (ext) parts.push(ext);
  parts.push(formatTimeAgo(t, file.created_at));
  return parts.join(" \u00B7 ");
}
