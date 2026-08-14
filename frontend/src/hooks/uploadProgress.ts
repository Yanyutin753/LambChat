export interface UploadProgressUpdate {
  progress: number;
  stage: "uploading" | "processing";
}

export interface UploadProgressController {
  report(progress: number): void;
  dispose(): void;
}

export function createUploadProgressController(
  onUpdate: (update: UploadProgressUpdate) => void,
  intervalMs = 100,
): UploadProgressController {
  let disposed = false;
  let processing = false;
  let lastEmitted: number | null = null;
  let pending: number | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const scheduleWindow = () => {
    timer = setTimeout(() => {
      timer = null;
      if (disposed || pending === null) return;
      const next = pending;
      pending = null;
      lastEmitted = next;
      onUpdate({ progress: next, stage: "uploading" });
      scheduleWindow();
    }, intervalMs);
  };

  return {
    report(rawProgress) {
      if (disposed || processing) return;
      const rounded = Math.round(rawProgress);
      if (rounded >= 100) {
        processing = true;
        pending = null;
        if (timer !== null) clearTimeout(timer);
        timer = null;
        lastEmitted = 99;
        onUpdate({ progress: 99, stage: "processing" });
        return;
      }

      const progress = Math.max(1, Math.min(99, rounded));
      if (progress === lastEmitted || progress === pending) return;
      if (timer === null) {
        lastEmitted = progress;
        onUpdate({ progress, stage: "uploading" });
        scheduleWindow();
        return;
      }
      pending = progress;
    },
    dispose() {
      disposed = true;
      pending = null;
      if (timer !== null) clearTimeout(timer);
      timer = null;
    },
  };
}
