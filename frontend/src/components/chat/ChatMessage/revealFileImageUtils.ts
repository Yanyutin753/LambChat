import type { MessagePart } from "../../../types";
import { isImageFile } from "../../documents/utils";
import { getFullUrl } from "../../../services/api/config";

export interface RevealFileImageInfo {
  id: string;
  src: string;
  fileName: string;
}

/**
 * Detects whether a MessagePart is a reveal_file containing an image.
 * Returns image metadata if it is an image, null otherwise.
 *
 * Handles both new format (result: { key, url, name, type }) and
 * old format (result: { file: { path, s3_url } }).
 */
export function isRevealFileImagePart(
  part: MessagePart,
): RevealFileImageInfo | null {
  if (part.type !== "tool" || part.name !== "reveal_file") return null;
  if (!part.result || !part.success) return null;

  try {
    let result: Record<string, unknown>;
    if (typeof part.result === "object") {
      result = part.result as Record<string, unknown>;
    } else {
      let jsonStr: string = part.result;
      const m = part.result.match(/content='(.+?)'(\s|$)/);
      if (m) jsonStr = m[1].replace(/\\'/g, "'");
      result = JSON.parse(jsonStr);
    }

    // New format: { key, url, name, type: "image" }
    if ("key" in result && "url" in result && "type" in result) {
      const r = result as {
        key: string;
        url: string;
        name: string;
        type: string;
      };
      if (r.type === "image" && r.url) {
        return {
          id: part.id || `reveal-${r.key}`,
          src: getFullUrl(r.url),
          fileName: r.name || "image",
        };
      }
      return null;
    }

    // Old format: { type: "file_reveal", file: { path, s3_url } }
    if ("type" in result && result.type === "file_reveal") {
      const file = result.file as Record<string, unknown> | undefined;
      if (!file) return null;
      const path = (file.path as string) || "";
      const s3Url = (file.s3_url as string) || "";
      const ext = path.split(".").pop()?.toLowerCase() || "";
      if (!isImageFile(ext) || !s3Url) return null;
      return {
        id: part.id || `reveal-${path}`,
        src: getFullUrl(s3Url),
        fileName: path.split("/").pop() || "image",
      };
    }

    return null;
  } catch {
    return null;
  }
}
