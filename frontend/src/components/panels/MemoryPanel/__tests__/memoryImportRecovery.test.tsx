/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { createInstance } from "i18next";
import en from "../../../../i18n/locales/en.json";
import zh from "../../../../i18n/locales/zh.json";
import ja from "../../../../i18n/locales/ja.json";
import ko from "../../../../i18n/locales/ko.json";
import ru from "../../../../i18n/locales/ru.json";
import { MemoryPanel } from "../index";
import {
  MemoryImportError,
  type MemoryImportProgress,
} from "../../../../services/api/memory";

const { list, importAll, errorToast, successToast, t } = vi.hoisted(() => ({
  list: vi.fn(),
  importAll: vi.fn(),
  errorToast: vi.fn(),
  successToast: vi.fn(),
  t: (key: string, options?: Record<string, unknown>) =>
    options?.imported !== undefined ? `${key}:${options.imported}` : key,
}));
vi.mock("../../../../services/api/memory", async (original) => ({
  ...(await original<typeof import("../../../../services/api/memory")>()),
  memoryApi: { list, importAll },
}));
vi.mock("react-i18next", async (original) => ({
  ...(await original<typeof import("react-i18next")>()),
  useTranslation: () => ({ t }),
}));
vi.mock("react-hot-toast", () => ({
  default: { error: errorToast, success: successToast },
}));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

const upload = (container: HTMLElement) =>
  fireEvent.change(container.querySelector('input[type="file"]')!, {
    target: {
      files: [
        {
          text: async () =>
            JSON.stringify({ memories: [{ content: "Durable policy." }] }),
        },
      ],
    },
  });

test.each(Object.entries({ en, zh, ja, ko, ru }))(
  "%s resolves memory import messages with real locale resources",
  async (lng, translation) => {
    const instance = createInstance();
    await instance.init({
      lng,
      fallbackLng: false,
      resources: { [lng]: { translation } },
    });
    for (const key of ["memory.importChecking", "memory.importProgress"]) {
      expect(instance.exists(key)).toBe(true);
      const message = instance.t(key, { processed: 1000, total: 50000 });
      expect(message).toContain("1000");
      expect(message).toContain("50000");
    }
    expect(instance.exists("memory.importPartialError")).toBe(true);
    expect(
      instance.t("memory.importPartialError", { imported: 1000 }),
    ).toContain("1000");
  },
);

test("import progress is visible and a partial failure refreshes confirmed data without a success toast", async () => {
  list.mockResolvedValue({ memories: [], total: 0 });
  let finish!: () => void;
  let progress!: (value: MemoryImportProgress) => void;
  importAll.mockImplementation(async (_data, report) => {
    progress = report;
    report({ phase: "checking", processed: 0, total: 2001 });
    await new Promise<void>((resolve) => {
      finish = resolve;
    });
    throw new MemoryImportError(
      { success: true, imported: 1000, created: 1000, overwritten: 0 },
      new Error("response lost"),
    );
  });
  const { container } = render(<MemoryPanel />);
  await screen.findByText("memory.empty");
  upload(container);
  expect(await screen.findByRole("status")).toHaveTextContent(
    "memory.importChecking",
  );
  expect(screen.getByRole("button", { name: "memory.import" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "memory.import" }));
  expect(importAll).toHaveBeenCalledTimes(1);
  // User-facing progress is fed only from completed service batches.
  const { act } = await import("@testing-library/react");
  act(() => progress({ phase: "importing", processed: 1000, total: 2001 }));
  expect(screen.getByRole("status")).toHaveTextContent("memory.importProgress");
  act(() => finish());
  await waitFor(() =>
    expect(errorToast).toHaveBeenCalledWith("memory.importPartialError:1000"),
  );
  expect(successToast).not.toHaveBeenCalled();
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "memory.importPartialError:1000",
  );
  await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
  expect(screen.queryByRole("status")).toBeNull();
});

test("a preflight failure uses the ordinary error and performs no result refresh", async () => {
  list.mockResolvedValue({ memories: [], total: 0 });
  importAll.mockRejectedValue(new Error("foreign project"));
  const { container } = render(<MemoryPanel />);
  await screen.findByText("memory.empty");
  upload(container);
  await waitFor(() =>
    expect(errorToast).toHaveBeenCalledWith("memory.importError"),
  );
  expect(successToast).not.toHaveBeenCalled();
  expect(list).toHaveBeenCalledTimes(1);
});
