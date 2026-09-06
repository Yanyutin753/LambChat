import { Brain, Zap, Settings, Monitor, Laptop, type LucideIcon } from "lucide-react";
import { Permission, type FileCategory } from "../../types";

export const FILE_CATEGORY_PERMISSIONS: Record<FileCategory, Permission> = {
  image: Permission.FILE_UPLOAD_IMAGE,
  video: Permission.FILE_UPLOAD_VIDEO,
  audio: Permission.FILE_UPLOAD_AUDIO,
  document: Permission.FILE_UPLOAD_DOCUMENT,
};

export const ICON_MAP: Record<string, LucideIcon> = {
  Brain,
  Zap,
  Settings,
  Monitor,
  Laptop,
};

/** When pasted text exceeds this length, auto-convert to a .txt file upload. */
export const PASTE_TEXT_THRESHOLD = 3000;
