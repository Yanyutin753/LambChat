import type { Message } from "../../../types";
import type { ExternalNavigationTargetFile } from "./externalNavigationState";
import { parseProjectRevealSummary } from "../../chat/ChatMessage/items/revealPreviewData";
import { openSubagentPanelByAgentId } from "../../chat/ChatMessage/SubagentBlocks";
import { isPersistentToolPanelOpen } from "../../chat/ChatMessage/items/persistentToolPanelState";
import {
  createSubagentAnchorOwnerId,
  createSubagentPanelKey,
  createToolPartAnchorId,
} from "../../chat/ChatMessage/messagePartAnchors";

export interface ExternalNavigationMatch {
  messageIndex: number;
  partIndex: number;
  anchorId?: string;
  subagentChain?: string[];
}

type MessageWithOptionalId = Pick<Message, "parts"> &
  Partial<Pick<Message, "id">>;
type MessageWithOptionalIdAndRun = MessageWithOptionalId &
  Pick<Message, "runId">;

interface ScrollElementIntoViewWithRetriesOptions {
  getElement: () => {
    scrollIntoView: (args?: ScrollIntoViewOptions) => void;
    getBoundingClientRect?: () => DOMRect | { top: number };
  } | null;
  getScroller?: () => {
    scrollTop: number;
    clientHeight: number;
    scrollHeight: number;
    getBoundingClientRect: () => DOMRect | { top: number };
    scrollTo?: (options: ScrollToOptions) => void;
  } | null;
  schedule?: (callback: () => void) => number;
  cancelSchedule?: (handle: number) => void;
  maxAttempts?: number;
  topOffsetPx?: number;
  tolerancePx?: number;
  settleAttempts?: number;
  behavior?: ScrollBehavior;
  align?: ScrollLogicalPosition;
}

interface RevealPartMatch {
  partIndex: number;
  anchorId?: string;
  subagentChain?: string[];
}

export { createSubagentAnchorOwnerId, createToolPartAnchorId };

export function findMessageIndexForRunId(
  messages: Pick<Message, "runId">[],
  targetRunId: string | null | undefined,
): number {
  if (!targetRunId) {
    return -1;
  }

  for (let index = messages.length - 1; index >= 0; index--) {
    if (messages[index]?.runId === targetRunId) {
      return index;
    }
  }

  return -1;
}

export function alignElementInScroller({
  scroller,
  element,
  topOffsetPx,
  align = "start",
}: {
  scroller: {
    scrollTop: number;
    clientHeight: number;
    scrollHeight: number;
    getBoundingClientRect: () => DOMRect | { top: number };
  };
  element: {
    getBoundingClientRect: () => DOMRect | { top: number };
  };
  topOffsetPx: number;
  align?: ScrollLogicalPosition;
}): number {
  const scrollerRect = scroller.getBoundingClientRect();
  const elementRect = element.getBoundingClientRect();
  const elementHeight =
    "height" in elementRect && typeof elementRect.height === "number"
      ? elementRect.height
      : 0;
  const scrollerHeight =
    "height" in scrollerRect && typeof scrollerRect.height === "number"
      ? scrollerRect.height
      : scroller.clientHeight;
  const delta =
    align === "center"
      ? elementRect.top -
        scrollerRect.top -
        (scrollerHeight - elementHeight) / 2
      : elementRect.top - scrollerRect.top - topOffsetPx;
  const maxScrollTop = Math.max(
    0,
    scroller.scrollHeight - scroller.clientHeight,
  );
  return Math.min(maxScrollTop, Math.max(0, scroller.scrollTop + delta));
}

export function scrollElementIntoViewWithRetries({
  getElement,
  getScroller,
  schedule = (callback) => requestAnimationFrame(callback),
  cancelSchedule = (handle) => cancelAnimationFrame(handle),
  maxAttempts = 12,
  topOffsetPx = 24,
  tolerancePx = 6,
  settleAttempts = 2,
  behavior = "auto",
  align = "start",
}: ScrollElementIntoViewWithRetriesOptions): () => void {
  let cancelled = false;
  let handle = 0;
  let attempt = 0;
  let settledCount = 0;
  let hasUsedSmoothBehavior = false;

  const tryScroll = () => {
    if (cancelled) {
      return;
    }

    const element = getElement();
    if (element) {
      const scroller = getScroller?.();
      const measureElement = element.getBoundingClientRect;
      if (scroller && measureElement) {
        const currentScrollTop = scroller.scrollTop;
        const nextScrollTop = alignElementInScroller({
          scroller,
          element: {
            getBoundingClientRect: measureElement.bind(element),
          },
          topOffsetPx,
          align,
        });
        const delta = Math.abs(nextScrollTop - currentScrollTop);

        if (delta <= tolerancePx) {
          settledCount += 1;
          if (settledCount >= settleAttempts) {
            return;
          }
        } else {
          settledCount = 0;
          const nextBehavior =
            behavior === "smooth" && hasUsedSmoothBehavior ? "auto" : behavior;
          hasUsedSmoothBehavior = true;
          if (scroller.scrollTo) {
            scroller.scrollTo({ top: nextScrollTop, behavior: nextBehavior });
          } else {
            scroller.scrollTop = nextScrollTop;
          }
        }
      } else {
        element.scrollIntoView({ behavior, block: align });
        return;
      }
    } else {
      settledCount = 0;
    }

    attempt += 1;
    if (attempt >= maxAttempts) {
      return;
    }

    handle = schedule(tryScroll);
  };

  tryScroll();

  return () => {
    cancelled = true;
    if (handle) {
      cancelSchedule(handle);
    }
  };
}

export function highlightElementForExternalNavigation({
  element,
  schedule = (callback, delayMs) => globalThis.setTimeout(callback, delayMs),
  cancelSchedule = (handle) => globalThis.clearTimeout(handle),
  durationMs = 1600,
}: {
  element: HTMLElement;
  schedule?: (
    callback: () => void,
    delayMs: number,
  ) => ReturnType<typeof setTimeout>;
  cancelSchedule?: (handle: ReturnType<typeof setTimeout>) => void;
  durationMs?: number;
}): () => void {
  const attributeName = "data-external-navigation-highlighted";
  element.setAttribute(attributeName, "true");

  const handle = schedule(() => {
    element.removeAttribute(attributeName);
  }, durationMs);

  return () => {
    cancelSchedule(handle);
    element.removeAttribute(attributeName);
  };
}

export function focusElementForExternalNavigation({
  element,
}: {
  element: HTMLElement;
}): void {
  if (typeof element.focus !== "function") {
    return;
  }

  if (element.tabIndex < 0 && !element.getAttribute("tabindex")) {
    element.setAttribute("tabindex", "-1");
  }

  element.focus({ preventScroll: true });
}

export function createExternalNavigationElementResolver({
  shouldTargetExactElement,
  scrollToMessageIndex,
  getExactElement,
  getFallbackElement,
}: {
  shouldTargetExactElement: boolean;
  scrollToMessageIndex: () => void;
  getExactElement: () => HTMLElement | null;
  getFallbackElement: () => HTMLElement | null;
}): () => HTMLElement | null {
  let hasResolvedTargetElement = false;

  return () => {
    if (!hasResolvedTargetElement) {
      scrollToMessageIndex();
    }

    const element = shouldTargetExactElement
      ? getExactElement()
      : getFallbackElement();

    if (element) {
      hasResolvedTargetElement = true;
    }

    return element;
  };
}

export function shouldKeepExternalNavigationPending({
  runMessageIndex: _runMessageIndex,
  matchedPartIndex: _matchedPartIndex,
}: {
  runMessageIndex: number;
  matchedPartIndex: number;
}): boolean {
  return false;
}

export function shouldDeferExternalNavigationScroll({
  runMessageIndex: _runMessageIndex,
  matchedPartIndex: _matchedPartIndex,
}: {
  runMessageIndex: number;
  matchedPartIndex: number;
}): boolean {
  return false;
}

export function shouldScrollExternalNavigationFallbackToMessage({
  runMessageIndex,
  matchedPartIndex,
}: {
  runMessageIndex: number;
  matchedPartIndex: number;
}): boolean {
  return runMessageIndex !== -1 && matchedPartIndex === -1;
}

export function ensureSubagentPanelsOpen(
  subagentChain: string[] | undefined,
): void {
  if (!subagentChain?.length) {
    return;
  }

  const deepestAgentId = subagentChain[subagentChain.length - 1];
  if (
    deepestAgentId &&
    isPersistentToolPanelOpen(createSubagentPanelKey(deepestAgentId))
  ) {
    return;
  }

  for (const agentId of subagentChain) {
    if (!openSubagentPanelByAgentId(agentId)) {
      break;
    }
  }
}

function parseRevealFileResult(
  result: string | Record<string, unknown> | undefined,
): {
  fileKey?: string;
  fileName?: string;
  originalPath?: string;
} | null {
  if (!result) {
    return null;
  }

  try {
    const parsed =
      typeof result === "string"
        ? (JSON.parse(result) as Record<string, unknown>)
        : result;

    if ("key" in parsed || "name" in parsed || "_meta" in parsed) {
      const meta =
        parsed._meta && typeof parsed._meta === "object"
          ? (parsed._meta as Record<string, unknown>)
          : null;
      return {
        fileKey: typeof parsed.key === "string" ? parsed.key : undefined,
        fileName: typeof parsed.name === "string" ? parsed.name : undefined,
        originalPath: typeof meta?.path === "string" ? meta.path : undefined,
      };
    }

    const file =
      parsed.type === "file_reveal" &&
      parsed.file &&
      typeof parsed.file === "object"
        ? (parsed.file as Record<string, unknown>)
        : null;

    if (!file) {
      return null;
    }

    return {
      fileKey: typeof file.s3_key === "string" ? file.s3_key : undefined,
      originalPath: typeof file.path === "string" ? file.path : undefined,
    };
  } catch {
    return null;
  }
}

function normalizePathForMatching(
  value: string | null | undefined,
): string | undefined {
  if (typeof value !== "string") {
    return undefined;
  }

  const normalized = value
    .trim()
    .replace(/\\/g, "/")
    .replace(/\/+/g, "/")
    .replace(/\/$/, "");

  return normalized || undefined;
}

function getPathBasename(value: string | null | undefined): string | undefined {
  const normalized = normalizePathForMatching(value);
  if (!normalized) {
    return undefined;
  }

  const segments = normalized.split("/");
  return segments[segments.length - 1] || undefined;
}

function pathsMatch(
  left: string | null | undefined,
  right: string | null | undefined,
): boolean {
  const normalizedLeft = normalizePathForMatching(left);
  const normalizedRight = normalizePathForMatching(right);

  if (!normalizedLeft || !normalizedRight) {
    return false;
  }

  return normalizedLeft === normalizedRight;
}

function matchesRevealFilePart(
  part: NonNullable<Message["parts"]>[number],
  targetFile: ExternalNavigationTargetFile,
): boolean {
  if (part.type !== "tool" || part.name !== "reveal_file") {
    return false;
  }

  const parsedResult = parseRevealFileResult(part.result);
  const argPath =
    typeof part.args.path === "string" ? part.args.path : undefined;
  const resultPath = parsedResult?.originalPath;
  const targetPath = targetFile.originalPath;
  const resultKey = parsedResult?.fileKey?.trim();
  const targetKey = targetFile.fileKey?.trim();
  const resultName =
    parsedResult?.fileName?.trim() ??
    getPathBasename(resultPath) ??
    getPathBasename(argPath);
  const targetName = targetFile.fileName?.trim();

  if (targetKey) {
    return !!resultKey && targetKey === resultKey;
  }

  if (targetPath) {
    return Boolean(
      pathsMatch(targetPath, argPath) || pathsMatch(targetPath, resultPath),
    );
  }

  if (targetName) {
    return !!resultName && targetName === resultName;
  }

  return false;
}

function matchesRevealProjectPart(
  part: NonNullable<Message["parts"]>[number],
  targetFile: ExternalNavigationTargetFile,
): boolean {
  if (part.type !== "tool" || part.name !== "reveal_project") {
    return false;
  }

  const projectPathFromArgs =
    typeof part.args.project_path === "string"
      ? part.args.project_path
      : undefined;
  const { projectName, projectPath } = parseProjectRevealSummary({
    args: part.args,
    result: part.result,
    parseErrorMessage: "",
  });
  const targetPath = targetFile.originalPath;
  const targetName = targetFile.fileName?.trim();
  const resultName =
    projectName?.trim() ||
    (typeof part.args.name === "string" ? part.args.name.trim() : undefined) ||
    getPathBasename(projectPathFromArgs) ||
    getPathBasename(projectPath);

  if (targetName && resultName) {
    return targetName === resultName;
  }

  return Boolean(
    targetPath &&
      (pathsMatch(targetPath, projectPathFromArgs) ||
        pathsMatch(targetPath, projectPath)),
  );
}

function findRevealPartMatchInParts(
  parts: NonNullable<Message["parts"]>,
  targetFile: ExternalNavigationTargetFile,
  anchorOwnerId?: string,
  subagentChain: string[] = [],
): RevealPartMatch | null {
  for (let partIndex = parts.length - 1; partIndex >= 0; partIndex--) {
    const part = parts[partIndex];
    const matched =
      targetFile.source === "reveal_project"
        ? matchesRevealProjectPart(part, targetFile)
        : matchesRevealFilePart(part, targetFile);

    if (matched) {
      return {
        partIndex,
        ...(anchorOwnerId
          ? {
              anchorId: createToolPartAnchorId(anchorOwnerId, partIndex),
            }
          : {}),
        ...(subagentChain.length > 0
          ? {
              subagentChain: [...subagentChain],
            }
          : {}),
      };
    }

    if (part.type === "subagent" && part.parts?.length) {
      const nestedMatch = findRevealPartMatchInParts(
        part.parts,
        targetFile,
        createSubagentAnchorOwnerId(part.agent_id),
        [...subagentChain, part.agent_id],
      );
      if (nestedMatch) {
        return nestedMatch;
      }
    }
  }

  return null;
}

export function findRevealPartMatchInMessage(
  message: MessageWithOptionalId | null | undefined,
  targetFile: ExternalNavigationTargetFile | null | undefined,
): RevealPartMatch | null {
  if (!message?.parts?.length || !targetFile) {
    return null;
  }

  return findRevealPartMatchInParts(message.parts, targetFile, message.id);
}

export function findMessageIndexForExternalNavigation(
  messages: MessageWithOptionalId[],
  targetFile: ExternalNavigationTargetFile | null | undefined,
): ExternalNavigationMatch | null {
  if (!targetFile) {
    return null;
  }

  for (
    let messageIndex = messages.length - 1;
    messageIndex >= 0;
    messageIndex--
  ) {
    const partMatch = findRevealPartMatchInMessage(
      messages[messageIndex],
      targetFile,
    );
    if (partMatch) {
      return {
        messageIndex,
        ...partMatch,
      };
    }
  }

  return null;
}

export function findRevealPartIndexInMessage(
  message: MessageWithOptionalId | null | undefined,
  targetFile: ExternalNavigationTargetFile | null | undefined,
): number {
  return findRevealPartMatchInMessage(message, targetFile)?.partIndex ?? -1;
}

export function findExternalNavigationMatchForRunId(
  messages: MessageWithOptionalIdAndRun[],
  targetRunId: string | null | undefined,
  targetFile: ExternalNavigationTargetFile | null | undefined,
): ExternalNavigationMatch | null {
  if (!targetRunId || !targetFile) {
    return null;
  }

  for (
    let messageIndex = messages.length - 1;
    messageIndex >= 0;
    messageIndex--
  ) {
    if (messages[messageIndex]?.runId !== targetRunId) {
      continue;
    }

    const partMatch = findRevealPartMatchInMessage(
      messages[messageIndex],
      targetFile,
    );
    if (partMatch) {
      return {
        messageIndex,
        ...partMatch,
      };
    }
  }

  return null;
}
