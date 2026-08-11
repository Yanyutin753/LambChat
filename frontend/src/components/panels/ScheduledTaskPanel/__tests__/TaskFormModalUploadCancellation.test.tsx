/** @vitest-environment jsdom */

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const { abortUpload, checkFile, getConfig, uploadFile } = vi.hoisted(() => ({
  abortUpload: vi.fn(),
  checkFile: vi.fn(),
  getConfig: vi.fn(),
  uploadFile: vi.fn(),
}));

vi.mock("../../../../hooks/useAuth", () => ({
  useAuth: () => ({ hasPermission: () => true }),
}));

vi.mock("../../../../services/api", async (importOriginal) => {
  const original =
    await importOriginal<typeof import("../../../../services/api")>();
  return {
    ...original,
    uploadApi: {
      ...original.uploadApi,
      checkFile,
      getConfig,
      uploadFile,
    },
  };
});

vi.mock("../../../../services/api/personaPreset", () => ({
  personaPresetApi: { list: vi.fn().mockResolvedValue({ presets: [] }) },
}));

vi.mock("../../../../services/api/team", () => ({
  teamApi: { list: vi.fn().mockResolvedValue({ teams: [] }) },
}));

vi.mock("../../../common/EditorSidebar", () => ({
  EditorSidebar: ({
    children,
    footer,
  }: {
    children: React.ReactNode;
    footer: React.ReactNode;
  }) => (
    <div>
      {children}
      {footer}
    </div>
  ),
}));

import { TaskFormModal } from "../TaskFormModal";

class HashWorkerStub {
  onmessage: ((event: MessageEvent<{ hash: string }>) => void) | null = null;
  onerror: ((event: ErrorEvent) => void) | null = null;

  postMessage(): void {
    queueMicrotask(
      () =>
        this.onmessage?.({ data: { hash: "scheduled-hash" } } as MessageEvent<{
          hash: string;
        }>),
    );
  }

  terminate(): void {}
}

beforeEach(() => {
  vi.stubGlobal("Worker", HashWorkerStub);
  abortUpload.mockReset();
  checkFile.mockReset().mockResolvedValue({ exists: false });
  getConfig.mockReset().mockResolvedValue({ uploadLimits: null });
  uploadFile.mockReset().mockImplementation(() => {
    let rejectUpload!: (error: Error) => void;
    const promise = new Promise<never>((_resolve, reject) => {
      rejectUpload = reject;
    });
    abortUpload.mockImplementationOnce(() =>
      rejectUpload(new Error("Upload was aborted")),
    );
    return { promise, abort: abortUpload };
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

test("scheduled-task upload cancellation aborts the request owned by its real upload controller", async () => {
  const { container } = render(
    <TaskFormModal
      task={null}
      agents={[
        {
          id: "default",
          name: "Default",
          description: "Default agent",
          version: "1",
        },
      ]}
      availableModels={null}
      defaultAgentId="default"
      onSave={vi.fn().mockResolvedValue(undefined)}
      onClose={vi.fn()}
    />,
  );

  const input = container.querySelector<HTMLInputElement>('input[type="file"]');
  expect(input).not.toBeNull();
  fireEvent.change(input!, {
    target: {
      files: [
        new File(["pending"], "pending.pdf", { type: "application/pdf" }),
      ],
    },
  });

  const fileName = await screen.findByText("pending.pdf");
  await waitFor(() => expect(uploadFile).toHaveBeenCalledOnce());
  const card = fileName.closest(".attachment-card-enter");
  expect(card).not.toBeNull();
  fireEvent.click(within(card as HTMLElement).getByRole("button"));

  expect(abortUpload).toHaveBeenCalledOnce();
  await waitFor(() =>
    expect(screen.queryByText("pending.pdf")).not.toBeInTheDocument(),
  );
});

test("cancelling while the dedupe check is pending never starts an invisible upload", async () => {
  let resolveCheck!: (result: { exists: false }) => void;
  checkFile.mockImplementationOnce(
    () =>
      new Promise<{ exists: false }>((resolve) => {
        resolveCheck = resolve;
      }),
  );

  const { container } = render(
    <TaskFormModal
      task={null}
      agents={[
        {
          id: "default",
          name: "Default",
          description: "Default agent",
          version: "1",
        },
      ]}
      availableModels={null}
      defaultAgentId="default"
      onSave={vi.fn().mockResolvedValue(undefined)}
      onClose={vi.fn()}
    />,
  );

  const input = container.querySelector<HTMLInputElement>('input[type="file"]');
  fireEvent.change(input!, {
    target: {
      files: [
        new File(["pending-check"], "pending-check.pdf", {
          type: "application/pdf",
        }),
      ],
    },
  });

  const fileName = await screen.findByText("pending-check.pdf");
  await waitFor(() => expect(checkFile).toHaveBeenCalledOnce());
  const card = fileName.closest(".attachment-card-enter");
  fireEvent.click(within(card as HTMLElement).getByRole("button"));
  expect(screen.queryByText("pending-check.pdf")).not.toBeInTheDocument();

  await act(async () => {
    resolveCheck({ exists: false });
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

  expect(uploadFile).not.toHaveBeenCalled();
  expect(abortUpload).not.toHaveBeenCalled();
});
