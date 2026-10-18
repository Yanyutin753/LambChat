import type { CollapsibleStatus } from "../../../common/CollapsiblePill";
import { extractText } from "./toolUtils";

export function parseExecuteResult(result?: string | Record<string, unknown>) {
  if (!result)
    return { output: "", exitCode: null, truncated: false, failed: false };
  const raw = extractText(result);

  // Parse the status line appended by deepagents backend
  let exitCode: number | null = null;
  let truncated = false;
  let failed = raw.trimStart().startsWith("[MCP Tool Error]");
  const lines = raw.trimEnd().split("\n");

  for (let i = lines.length - 1; i >= 0; i--) {
    const line = lines[i];
    if (line.match(/^\[Command (succeeded|failed)/)) {
      failed ||= line.startsWith("[Command failed");
      lines.splice(i, 1);
      const codeMatch = line.match(/exit code (-?\d+)/);
      if (codeMatch) exitCode = parseInt(codeMatch[1], 10);
      break;
    } else if (line.match(/^\[Output was truncated/)) {
      lines.splice(i, 1);
      truncated = true;
    } else if (line.startsWith("[")) {
      // Might be a status line from a sub-step, stop parsing
      break;
    } else {
      break;
    }
  }

  return { output: lines.join("\n").trim(), exitCode, truncated, failed };
}

export function deriveExecuteStatus(props: {
  cancelled?: boolean;
  isPending?: boolean;
  awaitingConfirmation?: boolean;
  success?: boolean;
  result?: string | Record<string, unknown>;
}): CollapsibleStatus {
  if (props.cancelled) return "cancelled";
  if (props.isPending && props.awaitingConfirmation) return "idle";
  if (props.isPending) return "loading";
  const { exitCode, failed } = parseExecuteResult(props.result);
  if (
    props.success === false ||
    failed ||
    (exitCode !== null && exitCode !== 0)
  )
    return "error";
  if (props.success === true || exitCode === 0) return "success";
  return "idle";
}
