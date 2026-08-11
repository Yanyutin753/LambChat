import { readFileSync } from "node:fs";

const removalPaths = [
  "../ChatInputAttachments.tsx",
  "../ChatInput.tsx",
  "../../../hooks/useLongTextConversion.ts",
  "../../panels/ScheduledTaskPanel/TaskFormModal.tsx",
] as const;

test.each(removalPaths)(
  "%s keeps uploaded draft removal local-only",
  (relativePath) => {
    const source = readFileSync(new URL(relativePath, import.meta.url), "utf8");

    expect(source).not.toContain("uploadApi.deleteFile");
  },
);
