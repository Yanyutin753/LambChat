export function computeFileHash(
  file: File,
  signal?: AbortSignal,
): Promise<string> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Upload was aborted", "AbortError"));
      return;
    }
    let worker: Worker;
    try {
      worker = new Worker(
        new URL("../workers/hashWorker.ts", import.meta.url),
        { type: "module" },
      );
    } catch (error) {
      reject(error);
      return;
    }
    const cleanup = () => {
      signal?.removeEventListener("abort", handleAbort);
      worker.terminate();
    };
    const handleAbort = () => {
      cleanup();
      reject(new DOMException("Upload was aborted", "AbortError"));
    };
    worker.onmessage = (e) => {
      cleanup();
      if (e.data.error) {
        reject(new Error(e.data.error));
      } else {
        resolve(e.data.hash);
      }
    };
    worker.onerror = (e) => {
      cleanup();
      reject(new Error(e.message));
    };
    signal?.addEventListener("abort", handleAbort, { once: true });
    worker.postMessage({ file });
  });
}
