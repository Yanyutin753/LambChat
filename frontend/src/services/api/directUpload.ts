import i18n from "i18next";
import { parseErrorDetail, translateApiError } from "../../utils/backendErrors";
import { authenticatedRequest } from "./authenticatedRequest";
import { getFullUrl } from "./config";
import type { UploadHandle, UploadOptions } from "./upload";
import type { UploadResult } from "../../types";

interface DirectTicket {
  mode: "direct";
  id: string;
  part_size: number;
  part_count: number;
  first_part_url?: string;
}

function aborted(): DOMException {
  return new DOMException("Upload was aborted", "AbortError");
}

async function request(
  path: string,
  init: RequestInit,
  timeoutMs = 0,
): Promise<Response> {
  const deadline = new AbortController();
  const timer = timeoutMs
    ? setTimeout(() => deadline.abort(), timeoutMs)
    : undefined;
  try {
    const target = `/api/upload/direct${path}`;
    const response = await authenticatedRequest(getFullUrl(target) || target, {
      credentials: "include",
      ...init,
      signal: timeoutMs ? deadline.signal : init.signal,
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      const { code, message, args } = parseErrorDetail(data);
      throw Object.assign(
        new Error(
          translateApiError(
            code,
            message || response.statusText,
            args,
            i18n.t.bind(i18n),
          ),
        ),
        { status: response.status, code },
      );
    }
    return response;
  } finally {
    clearTimeout(timer);
  }
}

export function uploadDirect(
  file: File,
  options: UploadOptions,
  fallback: () => UploadHandle,
): UploadHandle {
  const controller = new AbortController();
  const partsController = new AbortController();
  const activeParts = new Set<XMLHttpRequest>();
  const loadedParts = new Map<number, number>();
  let loadedBytes = 0;
  let proxy: UploadHandle | undefined;
  let ticket: DirectTicket | undefined;
  let settled = false;
  let cleanupPromise: Promise<void> | undefined;

  const cleanup = (): Promise<void> => {
    if (!ticket) return Promise.resolve();
    cleanupPromise ??= request(
      `/${ticket.id}`,
      {
        method: "DELETE",
        keepalive: true,
      },
      10_000,
    )
      .then(() => undefined)
      .catch((error) => {
        console.warn(
          "Direct upload cleanup will be retried by the server",
          error,
        );
      });
    return cleanupPromise;
  };

  const putPart = (url: string, blob: Blob, offset: number): Promise<void> =>
    new Promise((resolve, reject) => {
      if (partsController.signal.aborted) {
        reject(aborted());
        return;
      }
      const part = new XMLHttpRequest();
      activeParts.add(part);
      const finished = () => activeParts.delete(part);
      part.addEventListener("loadend", finished, { once: true });
      part.open("PUT", url);
      // Only the scoped URL authorizes this request; do not send application credentials.
      part.upload.addEventListener("progress", (event) => {
        reportPartProgress(offset, Math.min(event.loaded, blob.size));
      });
      part.addEventListener("load", () => {
        finished();
        if (part.status >= 200 && part.status < 300) resolve();
        else
          reject(
            Object.assign(new Error(i18n.t("fileUpload.uploadFailed")), {
              status: part.status,
            }),
          );
      });
      part.addEventListener("error", () => {
        finished();
        reject(
          Object.assign(new Error(i18n.t("fileUpload.uploadFailed")), {
            status: 0,
            directNetworkFailure: true,
          }),
        );
      });
      part.addEventListener("abort", () => {
        finished();
        reject(aborted());
      });
      part.timeout = 120_000;
      part.addEventListener("timeout", () => {
        finished();
        reject(
          Object.assign(new Error(i18n.t("fileUpload.uploadFailed")), {
            status: 408,
            directNetworkFailure: true,
          }),
        );
      });
      part.send(blob);
    });

  const reportPartProgress = (offset: number, bytes: number) => {
    // Retries and out-of-order parts must not move the progress bar backwards.
    const previous = loadedParts.get(offset) ?? 0;
    loadedBytes += Math.max(0, bytes - previous);
    loadedParts.set(offset, Math.max(previous, bytes));
    options.onProgress?.(
      Math.min(99, Math.floor((loadedBytes * 100) / file.size)),
      loadedBytes,
      file.size,
    );
  };

  const abortParts = () => {
    partsController.abort();
    for (const part of activeParts) part.abort();
  };

  const promise = (async (): Promise<UploadResult> => {
    try {
      // Keep initialization alive until its ID arrives, so cancel can clean it up.
      let initialized: DirectTicket | { mode: "proxy" };
      try {
        const response = await request(
          "",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              name: file.name,
              size: file.size,
              mime_type: file.type || "application/octet-stream",
            }),
          },
          60_000,
        );
        initialized = await response.json();
      } catch (error) {
        // Older servers retain uploads during independent client/server upgrades.
        if (![404, 405].includes((error as { status?: number }).status ?? 0))
          throw error;
        initialized = { mode: "proxy" };
      }
      if (initialized.mode === "direct") ticket = initialized;
      if (controller.signal.aborted) throw aborted();
      if (initialized.mode === "proxy") {
        proxy = fallback();
        const result = await proxy.promise;
        if (controller.signal.aborted) throw aborted();
        return result;
      }
      const uploadPart = async (number: number) => {
        const offset = (number - 1) * initialized.part_size;
        const blob = file.slice(offset, offset + initialized.part_size);
        for (let attempt = 0; ; attempt++) {
          if (partsController.signal.aborted) throw aborted();
          try {
            let url =
              number === 1 && attempt === 0
                ? initialized.first_part_url
                : undefined;
            if (!url) {
              const signed = await request(
                `/${initialized.id}/parts/${number}`,
                {
                  method: "POST",
                  signal: partsController.signal,
                },
              );
              url = (await signed.json()).url;
            }
            if (!url) throw new Error(i18n.t("fileUpload.uploadFailed"));
            await putPart(url, blob, offset);
            break;
          } catch (error) {
            if (partsController.signal.aborted) throw aborted();
            const status = (error as { status?: number }).status ?? 0;
            if (
              attempt >= 2 ||
              (![0, 403, 408, 429].includes(status) && status < 500)
            )
              throw error;
          }
        }
        reportPartProgress(offset, blob.size);
      };
      let nextNumber = 1;
      let partError: unknown;
      const worker = async () => {
        while (
          !partsController.signal.aborted &&
          nextNumber <= initialized.part_count
        ) {
          const number = nextNumber++;
          try {
            await uploadPart(number);
          } catch (error) {
            if (!partsController.signal.aborted) {
              partError = error;
              abortParts();
            }
            return;
          }
        }
      };
      // Keep small uploads sequential; bound large transfers to three active requests.
      await Promise.all(
        Array.from({ length: initialized.part_count >= 3 ? 3 : 1 }, worker),
      );
      if (controller.signal.aborted) throw aborted();
      if (partError) throw partError;
      options.onProgress?.(100, file.size, file.size);
      const monitoring = new AbortController();
      let progressTimer: ReturnType<typeof setTimeout> | undefined;
      const pollProcessing = async () => {
        try {
          const status = await request(`/${initialized.id}`, {
            method: "GET",
            signal: monitoring.signal,
          });
          const { progress } = await status.json();
          if (!monitoring.signal.aborted && typeof progress === "number") {
            options.onProcessingProgress?.(Math.max(0, Math.min(99, progress)));
          }
        } catch {
          // Completion remains authoritative if optional progress polling fails.
        }
        if (!monitoring.signal.aborted) {
          progressTimer = setTimeout(() => {
            void pollProcessing();
          }, 500);
        }
      };
      let result;
      try {
        const completing = request(`/${initialized.id}/complete`, {
          method: "POST",
          signal: controller.signal,
        });
        if (options.onProcessingProgress) void pollProcessing();
        const completed = await completing;
        result = await completed.json();
      } finally {
        monitoring.abort();
        clearTimeout(progressTimer);
      }
      if (controller.signal.aborted) throw aborted();
      return {
        key: result.key,
        url: result.url,
        name: result.name,
        type: result.type,
        mimeType: result.mimeType ?? result.mime_type ?? "",
        size: result.size,
      };
    } catch (error) {
      await cleanup();
      if (controller.signal.aborted) throw aborted();
      if (
        (error as { directNetworkFailure?: boolean }).directNetworkFailure &&
        !proxy
      ) {
        options.onProgress?.(0, 0, file.size);
        proxy = fallback();
        try {
          const result = await proxy.promise;
          if (controller.signal.aborted) throw aborted();
          return result;
        } catch (proxyError) {
          if (controller.signal.aborted) throw aborted();
          throw proxyError;
        }
      }
      throw error;
    } finally {
      settled = true;
    }
  })();

  return {
    promise,
    abort() {
      if (settled) return;
      controller.abort();
      abortParts();
      proxy?.abort();
      void cleanup();
    },
  };
}
