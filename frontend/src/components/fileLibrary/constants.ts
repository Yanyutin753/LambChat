import {
  FileText,
  Image,
  Video,
  Code2,
  FolderOpen,
  FileQuestion,
} from "lucide-react";

/* ── File type filter options ──────────────────────────── */

export const FILE_TYPE_FILTERS = [
  {
    key: "all",
    labelKey: "fileLibrary.types.all",
    icon: undefined as typeof Image | undefined,
  },
  { key: "document", labelKey: "fileLibrary.types.document", icon: FileText },
  { key: "image", labelKey: "fileLibrary.types.image", icon: Image },
  { key: "video", labelKey: "fileLibrary.types.video", icon: Video },
  { key: "code", labelKey: "fileLibrary.types.code", icon: Code2 },
  { key: "project", labelKey: "fileLibrary.types.project", icon: FolderOpen },
  { key: "other", labelKey: "fileLibrary.types.other", icon: FileQuestion },
] as const;

/* ── Sort options ──────────────────────────────────────── */

export const SORT_OPTIONS = [
  {
    key: "created_at",
    order: "desc" as const,
    labelKey: "fileLibrary.sort.newest",
  },
  {
    key: "created_at",
    order: "asc" as const,
    labelKey: "fileLibrary.sort.oldest",
  },
  {
    key: "file_name",
    order: "asc" as const,
    labelKey: "fileLibrary.sort.nameAsc",
  },
  {
    key: "file_name",
    order: "desc" as const,
    labelKey: "fileLibrary.sort.nameDesc",
  },
  {
    key: "file_size",
    order: "desc" as const,
    labelKey: "fileLibrary.sort.largest",
  },
  {
    key: "file_size",
    order: "asc" as const,
    labelKey: "fileLibrary.sort.smallest",
  },
] as const;

/* ── Misc ─────────────────────────────────────────────── */

export const VISIBLE_FILES_PER_SESSION = 3;
