import { extractText } from "./toolUtils";

export interface ParsedResult {
  task: Record<string, unknown> | null;
  preview: Record<string, unknown> | null;
  message: string;
  tasks: Array<Record<string, unknown>>;
  isList: boolean;
  /** Populated when the result is a rejection response like {success:false, reason:"rejected"} */
  rejection: {
    reason: string;
    message: string;
    preview: Record<string, unknown> | null;
  } | null;
}

export function parseResult(
  result: string | Record<string, unknown> | undefined,
): ParsedResult {
  const empty: ParsedResult = {
    task: null,
    preview: null,
    message: "",
    tasks: [],
    isList: false,
    rejection: null,
  };
  if (!result) return empty;

  const text = extractText(result);
  if (!text) return empty;

  try {
    const obj = JSON.parse(text);

    if (obj && typeof obj === "object") {
      // ── Rejection shape: {success:false, action:"not_created", reason, preview, message} ──
      if (
        obj.success === false &&
        typeof obj.reason === "string" &&
        !obj.task
      ) {
        return {
          task: null,
          preview: null,
          message: "",
          tasks: [],
          isList: false,
          rejection: {
            reason: obj.reason,
            message: String(obj.message || ""),
            preview:
              obj.preview && typeof obj.preview === "object"
                ? (obj.preview as Record<string, unknown>)
                : null,
          },
        };
      }

      // create/update/delete returns { task, preview, message }
      if (obj.task && typeof obj.task === "object") {
        return {
          task: obj.task as Record<string, unknown>,
          preview: (obj.preview as Record<string, unknown>) || null,
          message: String(obj.message || ""),
          tasks: [],
          isList: false,
          rejection: null,
        };
      }
      // list returns an array or { tasks: [...] }
      if (Array.isArray(obj)) {
        return {
          task: null,
          preview: null,
          message: "",
          tasks: obj,
          isList: true,
          rejection: null,
        };
      }
      if (Array.isArray(obj.tasks)) {
        return {
          task: null,
          preview: null,
          message: "",
          tasks: obj.tasks,
          isList: true,
          rejection: null,
        };
      }
      // single task from get/detail
      if (obj.id && obj.name) {
        return {
          task: obj as Record<string, unknown>,
          preview: null,
          message: "",
          tasks: [],
          isList: false,
          rejection: null,
        };
      }
    }
  } catch {
    // not JSON
  }

  return { ...empty, message: text };
}

